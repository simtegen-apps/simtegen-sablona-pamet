// simtegen-odchody — ze šablony, NEUPRAVOVAT V PRODUKTU (stavba ho obnoví).
//
// POST /api/odchod {duvod} — why this customer did not go on, one tap.
//
// Why: the monthly review could say THAT customers left (diagnoses
// odchazeji, bez_platby) and never WHY — the experiment it proposed was a
// guess. A lost customer is gone in a week; one question at the moment the
// trial or the paid period ran out is the only time anyone asks.
//
// What is stored: one more mark in odchody (day, channel, reason) — a tally,
// no account, no text (migration 0960). That this account already answered
// for this period sits in upominky (key "odchod_<period end>"), so the
// question goes away and one account cannot count twice; the answer itself
// is not kept with the account. The policy says so (stavitel adds the
// sentence to the upominky entity of every product with the migration).
//
// Only when it makes sense to ask: signed in, not a demo account, and the
// trial or subscription has run out (the product's own predplatne state) —
// anything else is 409, never a mark. The reason must be one of DUVODY.

import { json } from "../../spolecne.js";

export const DUVODY = ["cena", "malo_pouziti", "chyba", "chybi_funkce", "jiny_nastroj", "jine"];
const UKAZKOVY_UCET = "@ukazka.invalid";

// The "answered" key for the period that ran out, or null when there is
// nothing to ask about. Shared with the middleware, which tells the page.
export function znackaOdchodu(predplatne) {
  const p = predplatne;
  if (!p || p.stav !== "vyprselo" || p.platce === false) return null;
  const konec = Math.floor(Number(p.zkusebni_do || p.plati_do)) || 0;
  return "odchod_" + konec;
}

export async function onRequestPost(context) {
  const { env, data, request } = context;
  const uzivatel = data.uzivatel;
  if (!uzivatel) return json({ chyba: "Nejste přihlášeni.", kod: "neprihlasen" }, 401);
  if (String(uzivatel.email || "").endsWith(UKAZKOVY_UCET)) return json({ ok: true });
  const znacka = znackaOdchodu(data.predplatne);
  if (!znacka) return json({ chyba: "Teď není na co se ptát.", kod: "odchod_neni" }, 409);
  let telo;
  try {
    telo = await request.json();
  } catch {
    telo = {};
  }
  const duvod = DUVODY.includes(telo && telo.duvod) ? telo.duvod : null;
  if (!duvod) return json({ chyba: "Neznámý důvod.", kod: "odchod_duvod" }, 400);
  // Claim first: only the request that wrote the key counts the mark.
  const zapis = await env.DB.prepare(
    "INSERT OR IGNORE INTO upominky (uzivatel_id, druh) VALUES (?, ?)"
  ).bind(uzivatel.id, znacka).run();
  if (!zapis.meta || zapis.meta.changes !== 1) return json({ ok: true, uz: true });
  const platil = await env.DB.prepare("SELECT 1 AS x FROM platby WHERE uzivatel_id = ? LIMIT 1")
    .bind(uzivatel.id).first();
  await env.DB.prepare(
    "INSERT INTO odchody (den, kanal, duvod, pocet) VALUES (?, ?, ?, 1) " +
    "ON CONFLICT(den, kanal, duvod) DO UPDATE SET pocet = pocet + 1"
  ).bind(new Date().toISOString().slice(0, 10), platil ? "po_predplatnem" : "po_zkusebni", duvod).run();
  return json({ ok: true });
}
