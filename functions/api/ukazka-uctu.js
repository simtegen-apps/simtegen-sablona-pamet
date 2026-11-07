// /api/ukazka-uctu — sample data in the customer's OWN account, on request,
// removable with one tap. Template infrastructure (NEUPRAVOVAT V PRODUKTU).
//
// An empty app on the first login scares people off: there is nothing to
// look at, so nothing shows what the product is for. The product's empty
// state offers a button (data-ukazkova-data); web/simtegen.js drives it:
//
//   POST {akce: "nahrat"}    → the steps of /ukazka.json (the product's
//                              play/ukazka.json, the same invented data the
//                              store screenshots and the demo account use),
//                              after a snapshot of every table's last rowid
//   (the page replays the steps through the product's own API — so the
//    rows are exactly what the product itself would write)
//   POST {akce: "hotovo"}    → the snapshot after; the rows of THIS account
//                              between the two are the sample data
//   POST {akce: "odstranit"} → deletes exactly those rows and the record
//
// Why rowid ranges and not a flag on every row: the data shape is the
// product's, and a column in every product table would be a change in
// every product. The range is filtered by uzivatel_id, so another
// customer's rows written in the same second are never touched, and the
// customer's own rows from before the load (rowid ≤ before) neither. The
// rows carry the account's uzivatel_id like anything else, so export and
// account deletion include them by construction.
//
// The replay may only CREATE through the product's API: steps aimed at the
// template's endpoints (reports, orders, payments, the account itself) are
// dropped — sample data must never mail anyone, open an issue or touch money.

import { json, tabulkySUzivatelem } from "../../spolecne.js";

// The template's own tables are never sample data. Money first: a payment
// verified on page load during the replay must not be "removed with the
// sample". relace has no uzivatel_id rows to snapshot that matter.
const NIKDY = new Set(["relace", "predplatne", "platby", "play_nakupy",
  "zkusebni_doba", "upominky", "ukazkova_data"]);
const SABLONOVA_API = /^\/api\/(?:hlaseni|nahlasit|objednavka|play|ucet|prihlaseni|overeni|odhlaseni|ukazka|ukazka-uctu|ukazkova-data|navsteva|ja)(?:[/?]|$)/;
const DEMO = "@ukazka.invalid";

async function tabulky(env) {
  return (await tabulkySUzivatelem(env)).filter((t) => !NIKDY.has(t));
}

// Last rowid of every product table. Whole table, not just this account:
// the next row anyone inserts gets a higher one.
async function snimek(env) {
  const vysledek = {};
  for (const nazev of await tabulky(env)) {
    try {
      // mimo-uzivatele: the highest rowid of the whole table is the boundary; rows are filtered by account on delete.
      const radek = await env.DB.prepare(`SELECT COALESCE(MAX(rowid), 0) AS m FROM "${nazev}"`).first();
      vysledek[nazev] = Number(radek.m) || 0;
    } catch {
      // WITHOUT ROWID table: no range to keep, so never sample data.
    }
  }
  return vysledek;
}

function cti(text) {
  try {
    const hodnota = JSON.parse(text || "{}");
    return hodnota && typeof hodnota === "object" ? hodnota : {};
  } catch {
    return {};
  }
}

async function nahrat(context) {
  const { env, data, request } = context;
  let ukazka = null;
  try {
    const odpoved = await env.ASSETS.fetch(new URL("/ukazka.json", request.url));
    ukazka = odpoved.ok ? await odpoved.json() : null;
  } catch {
    ukazka = null;
  }
  const kroky = (ukazka && Array.isArray(ukazka.kroky) ? ukazka.kroky : []).filter((k) => {
    const [metoda, cesta] = String((k && k.pozadavek) || "").split(" ");
    return (metoda === "POST" || metoda === "GET") && /^\/api\//.test(cesta || "") && !SABLONOVA_API.test(cesta);
  });
  if (!kroky.length) return json({ chyba: "Ukázková data tu nejsou." }, 404);
  const pred = await snimek(env);
  try {
    await env.DB.prepare(
      "INSERT INTO ukazkova_data (uzivatel_id, pred) VALUES (?, ?)"
    ).bind(data.uzivatel.id, JSON.stringify(pred)).run();
  } catch {
    // The primary key: a second tap, or data already loaded.
    return json({ chyba: "Ukázková data už v účtu máte." }, 409);
  }
  return json({ kroky });
}

async function hotovo(context) {
  const { env, data } = context;
  const po = await snimek(env);
  await env.DB.prepare(
    "UPDATE ukazkova_data SET po = ? WHERE uzivatel_id = ? AND po IS NULL"
  ).bind(JSON.stringify(po), data.uzivatel.id).run();
  return json({ stav: "nahrana" });
}

async function odstranit(context) {
  const { env, data } = context;
  const radek = await env.DB.prepare(
    "SELECT pred, po FROM ukazkova_data WHERE uzivatel_id = ?"
  ).bind(data.uzivatel.id).first();
  if (!radek) return json({ stav: "nic" });
  const pred = cti(radek.pred);
  // Never finished (the page closed mid-load): the boundary is now — the
  // customer could not have added anything of their own in between from
  // this page, which was loading.
  const po = radek.po ? cti(radek.po) : await snimek(env);
  const zname = new Set(await tabulky(env));
  const prikazy = [];
  // Newest tables first: children usually come after their parents, and a
  // child row goes before the row it points to.
  for (const nazev of Object.keys(pred).reverse()) {
    const od = Number(pred[nazev]);
    const doRowid = Number(po[nazev]);
    if (!zname.has(nazev) || !Number.isFinite(od) || !Number.isFinite(doRowid) || doRowid <= od) continue;
    prikazy.push(env.DB.prepare(
      `DELETE FROM "${nazev}" WHERE uzivatel_id = ? AND rowid > ? AND rowid <= ?`
    ).bind(data.uzivatel.id, od, doRowid));
  }
  prikazy.push(env.DB.prepare("DELETE FROM ukazkova_data WHERE uzivatel_id = ?").bind(data.uzivatel.id));
  await env.DB.batch(prikazy);
  return json({ stav: "odstranena" });
}

export async function onRequestPost(context) {
  const { data, request } = context;
  if (!data.uzivatel) return json({ chyba: "Nejste přihlášeni." }, 401);
  if (String(data.uzivatel.email || "").endsWith(DEMO)) {
    return json({ chyba: "Ukázka už ukázková data má." }, 409);
  }
  let telo;
  try {
    telo = await request.json();
  } catch {
    return json({ chyba: "Neplatný požadavek." }, 400);
  }
  const akce = telo && telo.akce;
  try {
    if (akce === "nahrat") return await nahrat(context);
    if (akce === "hotovo") return await hotovo(context);
    if (akce === "odstranit") return await odstranit(context);
  } catch {
    // Before the 0920 migration the table is missing: say so plainly.
    return json({ chyba: "Ukázková data teď nejdou zpracovat. Zkuste to prosím později." }, 503);
  }
  return json({ chyba: "Neznámá akce." }, 422);
}
