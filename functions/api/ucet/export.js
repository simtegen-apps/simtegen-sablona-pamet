// GET /api/ucet/export — the GDPR data-portability right, self-service.
//
// Generic over every table with a uzivatel_id column (CI guarantees app
// tables have one), so a builder adding a table cannot silently make the
// export incomplete. Sessions and login links are excluded: they hold only
// token digests, which are security plumbing, not the customer's data.

import { json, tabulkySUzivatelem } from "../../../spolecne.js";

const TECHNICKE = new Set(["relace", "prihlasovaci_odkazy"]);

export async function onRequestGet(context) {
  const { env, data } = context;
  if (!data.uzivatel) return json({ chyba: "Nejste přihlášeni." }, 401);

  const ucet = await env.DB.prepare(
    "SELECT email, vytvoreno FROM uzivatele WHERE id = ?"
  ).bind(data.uzivatel.id).first();

  const tabulky = {};
  for (const nazev of await tabulkySUzivatelem(env)) {
    if (TECHNICKE.has(nazev)) continue;
    const radky = await env.DB.prepare(
      `SELECT * FROM "${nazev}" WHERE uzivatel_id = ?`
    ).bind(data.uzivatel.id).all();
    tabulky[nazev] = radky.results;
  }

  return json({ ucet, data: tabulky }, 200, {
    "Content-Disposition": 'attachment; filename="moje-data.json"',
  });
}
