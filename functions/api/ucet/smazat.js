// POST /api/ucet/smazat — the GDPR erasure right, self-service and
// immediate. Same introspection as the export, so a new app table is
// covered by construction; login links go by email (they predate the
// account id), the account row goes last.

import { cookieHlavicka, json, tabulkySUzivatelem } from "../../../spolecne.js";

export async function onRequestPost(context) {
  const { env, data } = context;
  if (!data.uzivatel) return json({ chyba: "Nejste přihlášeni." }, 401);

  const prikazy = [];
  for (const nazev of await tabulkySUzivatelem(env)) {
    prikazy.push(
      env.DB.prepare(`DELETE FROM "${nazev}" WHERE uzivatel_id = ?`)
        .bind(data.uzivatel.id)
    );
  }
  prikazy.push(
    env.DB.prepare("DELETE FROM prihlasovaci_odkazy WHERE email = ?")
      .bind(data.uzivatel.email),
    env.DB.prepare("DELETE FROM uzivatele WHERE id = ?").bind(data.uzivatel.id),
  );
  await env.DB.batch(prikazy);

  return json({ stav: "smazano" }, 200, { "Set-Cookie": cookieHlavicka("", 0) });
}
