// Subscription state, read-only from the app's point of view.
//
// Money never flows through a product: the owner invoices the customer,
// sees the payment in the bank and marks it with the "Predplatne" workflow,
// which writes plati_do into the predplatne table. This module only answers
// "is this account paid up?" — three states, nothing else to get wrong:
//
//   zkusebni  — no paid period, account younger than ZKUSEBNI_DNI
//   aktivni   — plati_do lies in the future
//   vyprselo  — neither
//
// Lives OUTSIDE functions/ like spolecne.js: everything under functions/ is
// a route candidate.

import { json, ted } from "./spolecne.js";

export const ZKUSEBNI_DNI = 30;

function dni(sekundy) {
  return Math.max(0, Math.ceil(sekundy / 86400));
}

export async function stavPredplatneho(env, uzivatel) {
  const radek = await env.DB.prepare(
    "SELECT u.vytvoreno, p.plati_do FROM uzivatele u " +
    "LEFT JOIN predplatne p ON p.uzivatel_id = u.id WHERE u.id = ?"
  ).bind(uzivatel.id).first();
  if (!radek) return { stav: "vyprselo", plati_do: null, dni_zbyva: 0 };

  const nyni = ted();
  const zkusebniDo = radek.vytvoreno + ZKUSEBNI_DNI * 86400;
  if (radek.plati_do && radek.plati_do > nyni) {
    return { stav: "aktivni", plati_do: radek.plati_do, dni_zbyva: dni(radek.plati_do - nyni) };
  }
  if (zkusebniDo > nyni) {
    return { stav: "zkusebni", plati_do: zkusebniDo, dni_zbyva: dni(zkusebniDo - nyni) };
  }
  return { stav: "vyprselo", plati_do: radek.plati_do || zkusebniDo, dni_zbyva: 0 };
}

// For PRODUCT routes only — never for account, export, deletion or login:
// the customer's rights do not expire with the subscription. Returns the
// Response to send (402) or null to carry on. Usage at the top of a handler:
//
//   const stop = vyzadujPredplatne(context); if (stop) return stop;
export function vyzadujPredplatne(context) {
  const p = context.data.predplatne;
  if (p && p.stav !== "vyprselo") return null;
  return json({ chyba: "Předplatné vypršelo.", predplatne: p || null }, 402);
}
