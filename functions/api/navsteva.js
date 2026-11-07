// POST /api/navsteva {stranka} — one anonymous page view.
//
// Counts only. No cookie, no IP, no account: the row is (day, page, count),
// so the review can see how many people reached the landing screen versus
// how many created an account, and the privacy policy stays true — this
// is not tracking, it is a tally mark. Unauthenticated on purpose: the
// visitors we care about are the ones without an account yet. Bots
// inflate it; a product with real customers does not decide on this
// number alone.

import { json } from "../../spolecne.js";

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
  const den = new Date().toISOString().slice(0, 10);
  await env.DB.prepare(
    "INSERT INTO navstevy (den, stranka, pocet) VALUES (?, ?, 1) " +
    "ON CONFLICT(den, stranka) DO UPDATE SET pocet = pocet + 1"
  ).bind(den, stranka).run();
  return json({ ok: true });
}
