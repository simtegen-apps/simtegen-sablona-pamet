// POST /api/provoz — daily counts for the firm's operations watch.
// Infrastruktura šablony (NEUPRAVOVAT V PRODUKTU): stavitel soubor při každé
// stavbě obnoví.
//
// Why: the firm's watch used to see only whether the product answers. How
// many login links went out, how many accounts appeared, how many reports
// and page errors came in — the signals of something going wrong at scale —
// were invisible until a customer complained. SimteGen (hlidac.py) asks
// here once a day and compares the numbers with the product's usual ones.
//
// What keeps this endpoint harmless:
//   - it answers with aggregate integers only: no address, no id, no text,
//     no time of any single event — nothing that identifies a customer;
//   - the firm's own accounts (@ukazka.invalid: the check account, demo
//     accounts) are left out, so they neither count nor can be counted;
//   - the request is signed by the key that lives only on the firm's machine
//     (RSASSA-PKCS1-v1_5 / SHA-256, verified with KLIC_ODPOVEDI in
//     schranka_klic.js — the public half, nothing secret on Cloudflare); the
//     signed text names its purpose, so no other signed request of the firm
//     passes as this one, and the other way round;
//   - it names this product and a time: valid PLATNOST_S seconds back and
//     at most BUDOUCNOST_S ahead (clock skew), never longer;
//   - it reads, never writes.
// Same text is built by SimteGen's hlidac.zprava().

import * as klice from "../../schranka_klic.js";
import { json, ted } from "../../spolecne.js";

const PLATNOST_S = 120;
const BUDOUCNOST_S = 30;
const DEN_S = 86400;
const DNU = 14;
const FIRMA = "%@ukazka.invalid";

function bajty(base64) {
  const s = atob(base64);
  const out = new Uint8Array(s.length);
  for (let i = 0; i < s.length; i++) out[i] = s.charCodeAt(i);
  return out;
}

export function zprava({ repo, cas }) {
  return new TextEncoder().encode(`provoz\nrepo=${repo}\ncas=${cas}`);
}

async function podpisSedi(telo) {
  try {
    const klic = await crypto.subtle.importKey(
      "jwk", klice.KLIC_ODPOVEDI, { name: "RSASSA-PKCS1-v1_5", hash: "SHA-256" }, false, ["verify"],
    );
    return await crypto.subtle.verify("RSASSA-PKCS1-v1_5", klic, bajty(telo.podpis), zprava(telo));
  } catch {
    return false;
  }
}

// One count per 24-hour window back from `t`: index 0 is the last 24 hours,
// 1..DNU the windows before. null when the table is not there (a product
// whose migrations have not caught up) — unknown, never a made-up zero.
async function poOknech(dotaz, t) {
  try {
    const { results } = await dotaz.bind(t, t - DEN_S * (DNU + 1), FIRMA).all();
    const out = new Array(DNU + 1).fill(0);
    for (const r of results || []) {
      const k = Math.floor(Number(r.k));
      if (k >= 0 && k <= DNU) out[k] += Number(r.n) || 0;
    }
    return out;
  } catch {
    return null;
  }
}

// The day tables (navstevy, chyby_stranek) count per UTC day; their window
// 0 is yesterday, the last whole day — today's half day would look like a drop.
async function poDnech(dotaz, t) {
  const den = (k) => new Date((t - DEN_S * (k + 1)) * 1000).toISOString().slice(0, 10);
  try {
    const { results } = await dotaz.bind(den(DNU), den(-1)).all();
    const index = new Map(Array.from({ length: DNU + 1 }, (_, k) => [den(k), k]));
    const out = new Array(DNU + 1).fill(0);
    for (const r of results || []) {
      if (index.has(r.den)) out[index.get(r.den)] += Number(r.n) || 0;
    }
    return out;
  } catch {
    return null;
  }
}

// Only the last 24 hours: login links are deleted once used and sessions on
// logout, so older windows would undercount. SimteGen keeps their history.
async function zaDen(dotaz, t) {
  try {
    const radek = await dotaz.bind(t - DEN_S, FIRMA).first();
    return Number((radek && radek.n) || 0);
  } catch {
    return null;
  }
}

export async function onRequestPost(context) {
  const { request, env } = context;
  // 404, not 503: the UAT check counts any 5xx as a crash of the endpoint,
  // and a product built before the answer key simply has nothing to say.
  if (!klice.KLIC_ODPOVEDI || !env.GITHUB_REPO) {
    return json({ chyba: "Počty pro provoz tu nejsou zapnuté." }, 404);
  }
  let telo;
  try {
    telo = await request.json();
  } catch {
    return json({ chyba: "Neplatný požadavek." }, 400);
  }
  const { repo, cas, podpis } = telo || {};
  if (typeof repo !== "string" || !Number.isInteger(cas) || typeof podpis !== "string") {
    return json({ chyba: "Neplatný požadavek." }, 400);
  }
  if (repo.toLowerCase() !== String(env.GITHUB_REPO).toLowerCase()) {
    return json({ chyba: "Požadavek patří jinému produktu." }, 403);
  }
  const t = ted();
  if (t - cas > PLATNOST_S || cas - t > BUDOUCNOST_S) return json({ chyba: "Podpis je mimo čas." }, 403);
  if (!(await podpisSedi(telo))) return json({ chyba: "Podpis nesedí." }, 403);

  const { DB } = env;
  const ucty = await poOknech(DB.prepare(
    "SELECT CAST((? - vytvoreno) / 86400 AS INTEGER) AS k, COUNT(*) AS n FROM uzivatele " +
    "WHERE vytvoreno > ? AND email NOT LIKE ? GROUP BY k"
  ), t);
  // mimo-uzivatele: one number over all accounts for the firm's watch — no row leaves
  const hlaseni = await poOknech(DB.prepare(
    "SELECT CAST((? - h.vytvoreno) / 86400 AS INTEGER) AS k, COUNT(*) AS n FROM hlaseni h " +
    "JOIN uzivatele u ON u.id = h.uzivatel_id WHERE h.vytvoreno > ? AND u.email NOT LIKE ? GROUP BY k"
  ), t);
  const chyby = await poDnech(DB.prepare(
    "SELECT den, SUM(pocet) AS n FROM chyby_stranek WHERE den >= ? AND den < ? GROUP BY den"
  ), t);
  const navstevy = await poDnech(DB.prepare(
    "SELECT den, SUM(pocet) AS n FROM navstevy WHERE den >= ? AND den < ? GROUP BY den"
  ), t);
  const odkazy = await zaDen(DB.prepare(
    "SELECT COUNT(*) AS n FROM prihlasovaci_odkazy WHERE vytvoreno > ? AND email NOT LIKE ?"
  ), t);
  const prihlaseni = await zaDen(DB.prepare(
    "SELECT COUNT(*) AS n FROM relace r JOIN uzivatele u ON u.id = r.uzivatel_id " +
    "WHERE r.vytvoreno > ? AND u.email NOT LIKE ?"
  ), t);

  const prvni = (rada) => (rada ? rada[0] : null);
  const zbytek = (rada) => (rada ? rada.slice(1) : null);
  return json({
    pocty: { odkazy, ucty: prvni(ucty), prihlaseni, hlaseni: prvni(hlaseni),
             chyby: prvni(chyby), navstevy: prvni(navstevy) },
    predtim: { ucty: zbytek(ucty), hlaseni: zbytek(hlaseni), chyby: zbytek(chyby), navstevy: zbytek(navstevy) },
  }, 200, { "Cache-Control": "no-store" });
}
