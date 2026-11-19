// POST /api/navsteva {stranka} — one anonymous page view.
//
// Counts only. No cookie, no IP, no account: the row is (day, page, count),
// so the review can see how many people reached the landing screen versus
// how many created an account, and the privacy policy stays true — this
// is not tracking, it is a tally mark. Unauthenticated on purpose: the
// visitors we care about are the ones without an account yet. Bots
// inflate it; a product with real customers does not decide on this
// number alone. A network address counts at most LIMIT_IP views an hour
// (ochrana.js, a digest in D1, not the address): a script cannot inflate the
// funnel or spend the account's D1 writes.

import { json } from "../../spolecne.js";
import { adresaKlienta, vLimitu } from "../../ochrana.js";

const LIMIT_IP = 30;

const STRANKY = new Set(["uvod", "cenik", "prihlaseni"]);

export async function onRequestPost(context) {
  const { env, request } = context;
  let telo;
  try {
    telo = await request.json();
  } catch {
    return json({ chyba: "Neplatný požadavek." }, 400);
  }
  const stranka = String((telo && telo.stranka) || "uvod");
  if (!STRANKY.has(stranka)) return json({ chyba: "Neznámá stránka." }, 422);
  if (!(await vLimitu(env, "navsteva_ip", adresaKlienta(request, env), LIMIT_IP, 3600))) {
    return json({ chyba: "Příliš mnoho požadavků." }, 429);
  }
  const den = new Date().toISOString().slice(0, 10);
  await env.DB.prepare(
    "INSERT INTO navstevy (den, stranka, pocet) VALUES (?, ?, 1) " +
    "ON CONFLICT(den, stranka) DO UPDATE SET pocet = pocet + 1"
  ).bind(den, stranka).run();
  return json({ ok: true });
}
