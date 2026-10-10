// /api/hlaseni — the product's mailbox.
//
// GET  → the signed-in customer's own reports, newest first, with answers.
// POST → {text, kontext}: store the report, then mirror it as an issue in
//        the product's GitHub repo — ENCRYPTED (schranka_sifra.js), because
//        the repo is public; the issue carries only the report number and a
//        block only SimteGen can open. No account details even inside it.
//        The firm's triage reads issues; the customer never leaves the app.
//        Mirroring is best effort: a failed GitHub call must not lose the
//        report.
//
// Not gated by the subscription: reporting a problem is a right, not a
// feature. Rate-limited per account so a stuck retry loop cannot flood
// the repo.

import { json, ted } from "../../spolecne.js";
import { ocistiKontext, zrcadliHlaseni, MIN_DELKA, MAX_DELKA } from "../../schranka_sifra.js";

const MAX_ZA_HODINU = 5;

export async function onRequestGet(context) {
  const { env, data } = context;
  if (!data.uzivatel) return json({ chyba: "Nejste přihlášeni." }, 401);
  const radky = await env.DB.prepare(
    "SELECT id, text, stav, odpoved, vytvoreno, zmeneno FROM hlaseni " +
    "WHERE uzivatel_id = ? ORDER BY id DESC LIMIT 50"
  ).bind(data.uzivatel.id).all();
  return json({ hlaseni: radky.results });
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
  const text = String((telo && telo.text) || "").trim();
  if (text.length < MIN_DELKA) return json({ chyba: "Napište nám prosím, o co jde." }, 422);
  if (text.length > MAX_DELKA) {
    return json({ chyba: `Zpráva je moc dlouhá (max ${MAX_DELKA} znaků).` }, 422);
  }

  const nedavno = await env.DB.prepare(
    "SELECT COUNT(*) AS n FROM hlaseni WHERE uzivatel_id = ? AND vytvoreno > ?"
  ).bind(data.uzivatel.id, ted() - 3600).first();
  if (nedavno && nedavno.n >= MAX_ZA_HODINU) {
    return json({ chyba: "Za poslední hodinu jste poslali hodně zpráv — zkuste to prosím později." }, 429);
  }

  const vlozeno = await env.DB.prepare(
    "INSERT INTO hlaseni (uzivatel_id, text) VALUES (?, ?) RETURNING id, vytvoreno"
  ).bind(data.uzivatel.id, text).first();

  let zrcadlo = false;
  const cislo = await zrcadliHlaseni(env, `Hlášení #${vlozeno.id}`, {
    zdroj: "ucet", id: vlozeno.id, text, kontext: ocistiKontext(telo.kontext),
  });
  if (cislo) {
    await env.DB.prepare("UPDATE hlaseni SET issue_cislo = ? WHERE id = ? AND uzivatel_id = ?")
      .bind(cislo, vlozeno.id, data.uzivatel.id).run();
    zrcadlo = true;
  }
  return json({ id: vlozeno.id, stav: "nove", zrcadlo });
}
