// /api/objednavka — ordering a subscription from inside the app.
//
// The legal shape comes from the terms (čl. 3 and 4): the customer sees the
// scope, length and total price, presses a button labelled "Objednávka
// zavazující k platbě", and — being a consumer — may tick a SEPARATE
// consent to start the paid service before the 14-day withdrawal window
// closes (§ 1837 l). Without that tick a consumer's paid period starts
// only after 14 days; a business customer has no such window.
//
// Money still never flows through the app: the customer gets a
// confirmation "in textual form" (the § 1837 l record), the operator a
// copy with the billing details. The GitHub mirror carries only the order
// number, months and the variant's id — no account, no billing data — and
// is what the firm (SimteGen) reacts to: it dispatches the Faktura
// workflow, which reads the billing details from THIS database and mails
// the invoice.
//
// The variant comes from the approved price list (web/cenik.json, written
// by SimteGen, never by the builder), not from the request: the issue is
// public and the mails go out under the firm's name, so the customer's
// string must never reach either. The request only names which item. The
// price too: the total is months × the item's monthly price in that list,
// and the number the page sends is only compared with it — a mismatch (a
// page loaded before a price change, or a request someone wrote by hand) is
// a 409, never a confirmation of a price the firm did not approve.
//
// GET → the signed-in customer's own orders.

import { json, ted } from "../../spolecne.js";
import { htmlEmailu, PRILOHA_LOGA } from "../../email_obal.js";

const MAX_FAKTURACE = 600;

export async function onRequestGet(context) {
  const { env, data } = context;
  if (!data.uzivatel) return json({ chyba: "Nejste přihlášeni." }, 401);
  const radky = await env.DB.prepare(
    "SELECT id, mesice, varianta, cena_czk, spotrebitel, souhlas_zahajeni, stav, vytvoreno " +
    "FROM objednavky WHERE uzivatel_id = ? ORDER BY id DESC LIMIT 20"
  ).bind(data.uzivatel.id).all();
  return json({ objednavky: radky.results });
}

export async function onRequestPost(context) {
  const { env, data, request } = context;
  if (!data.uzivatel) return json({ chyba: "Nejste přihlášeni." }, 401);

  let telo;
  try {
    telo = await request.json();
  } catch {
    return json({ chyba: "Neplatný požadavek." }, 400);
  }
  const mesice = Number(telo && telo.mesice);
  if (!Number.isInteger(mesice) || mesice < 1 || mesice > 24) {
    return json({ chyba: "Zvolte délku předplatného 1–24 měsíců." }, 422);
  }
  const cenik = await nactiCenik(env, request);
  const varianta = variantaZCeniku(cenik, telo && telo.varianta);
  if (varianta === undefined) {
    return json({ chyba: "Tuhle variantu předplatného v ceníku nemáme — obnovte prosím stránku." }, 422);
  }
  const mesicne = mesicniCena(cenik, varianta);
  const cena = mesicne === null ? null : mesicne * mesice;
  const zadana = telo && telo.cena_czk;
  if (cena !== null && zadana !== undefined && zadana !== null && Math.round(Number(zadana)) !== cena) {
    return json({ chyba: "Ceník se mezitím změnil — obnovte prosím stránku a zkontrolujte cenu.", kod: "cenik_zmenen" },
      409);
  }
  const fakturace = String((telo && telo.fakturace) || "").trim();
  if (fakturace.length < 3) {
    return json({ chyba: "Vyplňte prosím fakturační údaje (název nebo jméno, adresa, IČO máte-li)." }, 422);
  }
  if (fakturace.length > MAX_FAKTURACE) {
    return json({ chyba: `Fakturační údaje jsou moc dlouhé (max ${MAX_FAKTURACE} znaků).` }, 422);
  }
  const spotrebitel = Boolean(telo && telo.spotrebitel);
  const souhlas = Boolean(telo && telo.souhlas_zahajeni);

  const otevrena = await env.DB.prepare(
    "SELECT COUNT(*) AS n FROM objednavky WHERE uzivatel_id = ? AND stav IN ('nova', 'fakturovana')"
  ).bind(data.uzivatel.id).first();
  if (otevrena && otevrena.n > 0) {
    return json({ chyba: "Máte už rozpracovanou objednávku — počkejte prosím na fakturu." }, 409);
  }

  const vlozeno = await env.DB.prepare(
    "INSERT INTO objednavky (uzivatel_id, mesice, varianta, cena_czk, fakturace, spotrebitel, " +
    "souhlas_zahajeni, souhlas_cas) VALUES (?, ?, ?, ?, ?, ?, ?, ?) RETURNING id, vytvoreno"
  ).bind(
    data.uzivatel.id, mesice, varianta ? varianta.id : null, cena,
    fakturace, spotrebitel ? 1 : 0, souhlas ? 1 : 0, souhlas ? ted() : null,
  ).first();

  const cislo = await zrcadliDoIssue(env, vlozeno.id, mesice, varianta && varianta.id);
  if (cislo) {
    await env.DB.prepare("UPDATE objednavky SET issue_cislo = ? WHERE id = ? AND uzivatel_id = ?")
      .bind(cislo, vlozeno.id, data.uzivatel.id).run();
  }
  // The product's name and colour from the template middleware
  // (application-name, web/produkt.css) — the head of the HTML part.
  const emaily = await posliEmaily(env, data.uzivatel.email, {
    id: vlozeno.id, mesice, varianta: varianta && varianta.nazev, cena, fakturace, spotrebitel, souhlas,
  }, { produkt: data.produkt, barva: data.barva });
  return json({ id: vlozeno.id, stav: "nova", zrcadlo: Boolean(cislo), emaily });
}

async function nactiCenik(env, request) {
  // The approved price list as deployed with this version of the page.
  try {
    const odpoved = await env.ASSETS.fetch(new URL("/cenik.json", request.url));
    const cenik = odpoved.ok ? await odpoved.json() : null;
    return cenik && Array.isArray(cenik.polozky) ? cenik : null;
  } catch {
    return null;
  }
}

const nazevPolozky = (p) => String((p.nazev && typeof p.nazev === "object" ? p.nazev.cs : p.nazev) || "");

// undefined = the request named a variant the list does not have; null =
// none named (or no list yet: nothing to check it against, so nothing is
// relayed — the firm invoices the approved recommendation and refuses a
// price that does not match it). Matched by id, or by the Czech name an
// older product page still sends.
function variantaZCeniku(cenik, volba) {
  const chtena = typeof volba === "string" ? volba.trim() : "";
  if (!chtena || !cenik) return null;
  const polozka = cenik.polozky.find((p) => p && typeof p.id === "string" &&
    /^[a-z0-9-]{1,40}$/.test(p.id) && (p.id === chtena || nazevPolozky(p) === chtena));
  return polozka ? { id: polozka.id, nazev: nazevPolozky(polozka).slice(0, 80) || polozka.id } : undefined;
}

// The monthly whole-crown price of the ordered item (the named variant,
// else the recommendation — what the firm invoices), or null when the list
// cannot say: no list, no price in crowns, not whole crowns, or a unit that
// is not "per month" (a yearly price, per user…). Then the order carries no
// price and the firm invoices from its own approved pricing, as before.
function mesicniCena(cenik, varianta) {
  if (!cenik) return null;
  const id = varianta ? varianta.id : "doporuceni";
  const polozka = cenik.polozky.find((p) => p && p.id === id) || (varianta ? null : cenik.polozky[0]);
  if (!polozka || !polozka.ceny) return null;
  const kc = Number(String(polozka.ceny.CZK ?? "").replace(",", "."));
  if (!Number.isInteger(kc) || kc <= 0) return null;
  const jednotka = String((polozka.jednotka && typeof polozka.jednotka === "object"
    ? polozka.jednotka.cs : polozka.jednotka) || "")
    .normalize("NFKD").replace(/[\u0300-\u036f]/g, "").toLowerCase();
  if (/uzivatel|slot|zaznam|kredit|kus|polozk|rok|rocn/.test(jednotka)) return null;
  if (jednotka && !jednotka.includes("mes")) return null;
  return kc;
}

async function zrcadliDoIssue(env, id, mesice, varianta) {
  if (!env.GITHUB_ISSUES_TOKEN || !env.GITHUB_REPO) return null;
  try {
    const odpoved = await fetch(`https://api.github.com/repos/${env.GITHUB_REPO}/issues`, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${env.GITHUB_ISSUES_TOKEN}`,
        Accept: "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "simtegen-objednavka",
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        title: `Objednávka #${id}`,
        body: `Předplatné na ${mesice} měs.${varianta ? ` (${varianta})` : ""}. ` +
              "Fakturační údaje jsou v databázi produktu; fakturu vystaví firma (workflow Faktura).",
        labels: ["objednavka"],
      }),
    });
    if (!odpoved.ok) return null;
    const issue = await odpoved.json();
    return issue.number || null;
  } catch {
    return null;
  }
}

async function posliEmaily(env, zakaznik, o, znacka = {}) {
  // Two mails: the operator gets the order (with billing details), the
  // customer gets the confirmation in textual form. Without Resend both
  // are skipped and the caller reports it — the order itself is stored.
  // Each also carries an HTML part built from its own text (email_obal.js):
  // the text stays the record, the billing details are escaped there.
  if (!env.RESEND_API_KEY || !env.EMAIL_ODESILATEL) return false;
  const kontakt = env.KONTAKT_EMAIL || env.EMAIL_ODESILATEL;
  const shrnuti = `Předplatné na ${o.mesice} měsíců` + (o.varianta ? ` (${o.varianta})` : "")
    + (o.cena ? `, cena ${o.cena} Kč` : "") + `, objednávka č. ${o.id}.`;
  const souhlasText = o.spotrebitel
    ? (o.souhlas
      ? "Udělil(a) jste výslovný souhlas se zahájením poskytování placené služby před uplynutím " +
        "14denní lhůty pro odstoupení a byl(a) jste poučen(a), že tím právo na odstoupení ztrácíte " +
        "(§ 1837 písm. l) občanského zákoníku)."
      : "Souhlas se zahájením před uplynutím 14denní lhůty jste neudělil(a) — placená služba začne " +
        "po uplynutí 14 dnů; do té doby můžete odstoupit bez sankce.")
    : "";
  const zpravy = [
    {
      to: [kontakt],
      subject: `Objednávka č. ${o.id} — ${o.mesice} měs.`,
      text: `${shrnuti}\n\nFakturační údaje:\n${o.fakturace}\n\nE-mail účtu: ${zakaznik}\n` +
            `Spotřebitel: ${o.spotrebitel ? "ano" : "ne"}; souhlas se zahájením: ${o.souhlas ? "ano" : "ne"}.\n` +
            "Fakturu vystaví firma sama; až platba přijde, řekni ARGOvi „zaplaceno“.",
    },
    {
      to: [zakaznik],
      subject: "Potvrzení objednávky předplatného",
      text: `Dobrý den,\n\ndostali jsme vaši objednávku. ${shrnuti}\n\nFakturu vám pošleme e-mailem; ` +
            "zaplacené období uvidíte v aplikaci u účtu.\n" + (souhlasText ? `\n${souhlasText}\n` : "") +
            "\nObchodní podmínky a odstoupení od smlouvy: viz odkazy v aplikaci.\n",
    },
  ];
  let ok = true;
  for (const zprava of zpravy) {
    try {
      const html = htmlEmailu({ predmet: zprava.subject, text: zprava.text, jazyk: "cs", ...znacka });
      const odpoved = await fetch("https://api.resend.com/emails", {
        method: "POST",
        headers: { Authorization: `Bearer ${env.RESEND_API_KEY}`, "Content-Type": "application/json" },
        body: JSON.stringify({ from: env.EMAIL_ODESILATEL, ...zprava, html, attachments: [PRILOHA_LOGA] }),
      });
      ok = ok && odpoved.ok;
    } catch {
      ok = false;
    }
  }
  return ok;
}
