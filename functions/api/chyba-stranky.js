// POST /api/chyba-stranky {obrazovka, misto} — one script error, counted.
// Infrastruktura šablony (NEUPRAVOVAT V PRODUKTU), veřejný endpoint.
//
// A tally mark like /api/navsteva: (day, screen, place in our code, count),
// no message, no cookie, no account, no IP. Unauthenticated on purpose — the
// login screen breaks too. The client (web/simtegen.js) sends each place
// once per page load, at most five. Values that do not look like ours —
// a screen id, a file name and a line — become "jine", and past
// MAX_RADKU rows a day everything new lands in "jine" too: a stranger can
// inflate the count, never grow the table without bound or write text into it.
// Per network address at most LIMIT_IP marks an hour (ochrana.js): the
// client sends five per page load, a script sending thousands would only
// cost D1 writes for every product on the account.

import { json } from "../../spolecne.js";
import { adresaKlienta, vLimitu } from "../../ochrana.js";

const LIMIT_IP = 60;

const MAX_RADKU = 200;
const OBRAZOVKA = /^[a-z0-9][a-z0-9_-]{0,39}$/;
const MISTO = /^[A-Za-z0-9._-]{1,60}\.(?:js|html|mjs):\d{1,6}$/;

export async function onRequestPost(context) {
  const { env, request } = context;
  let telo;
  try {
    telo = await request.json();
  } catch {
    return json({ chyba: "Neplatný požadavek." }, 400);
  }
  if (!(await vLimitu(env, "chyba_ip", adresaKlienta(request, env), LIMIT_IP, 3600))) {
    return json({ chyba: "Příliš mnoho požadavků." }, 429);
  }
  let obrazovka = OBRAZOVKA.test(String((telo && telo.obrazovka) || "")) ? String(telo.obrazovka) : "jine";
  let misto = MISTO.test(String((telo && telo.misto) || "")) ? String(telo.misto) : "jine";
  const den = new Date().toISOString().slice(0, 10);
  const radku = await env.DB.prepare("SELECT COUNT(*) AS n FROM chyby_stranek WHERE den = ?").bind(den).first();
  if (radku && radku.n >= MAX_RADKU) {
    obrazovka = "jine";
    misto = "jine";
  }
  await env.DB.prepare(
    "INSERT INTO chyby_stranek (den, obrazovka, misto, pocet) VALUES (?, ?, ?, 1) " +
    "ON CONFLICT(den, obrazovka, misto) DO UPDATE SET pocet = pocet + 1"
  ).bind(den, obrazovka, misto).run();
  return json({ ok: true });
}
