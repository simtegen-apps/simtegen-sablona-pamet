// simtegen-jazyk — ze šablony, NEUPRAVOVAT V PRODUKTU (stavba ho obnoví).
//
// POST /api/jazyk {jazyk} — the language the customer uses the app in,
// remembered on the account (migration 0950), so the mails the firm sends
// later (trial end, renewal, an answer to a report — upominky.py) come in
// it. web/simtegen.js calls it only when the page's language differs from
// the account's (X-SimteGen-Jazyk-Uctu on /api/ja): the customer switched
// in Účet, or the account was made before the language was remembered.

import { json } from "../../spolecne.js";
import { JAZYKY_SABLONY } from "../../ochrana.js";

export async function onRequestPost(context) {
  const { request, env, data } = context;
  if (!data.uzivatel) return json({ chyba: "Nejste přihlášeni.", kod: "neprihlasen" }, 401);
  let telo;
  try {
    telo = await request.json();
  } catch {
    return json({ chyba: "Tělo požadavku musí být JSON.", kod: "format" }, 400);
  }
  const jazyk = String((telo && telo.jazyk) || "");
  if (!JAZYKY_SABLONY.includes(jazyk)) return json({ chyba: "Tenhle jazyk aplikace neumí.", kod: "jazyk" }, 422);
  await env.DB.prepare("UPDATE uzivatele SET jazyk = ? WHERE id = ?").bind(jazyk, data.uzivatel.id).run();
  return json({ jazyk });
}
