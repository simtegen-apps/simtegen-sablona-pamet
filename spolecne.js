// Shared helpers for the Pages Functions. Lives OUTSIDE functions/ on
// purpose: everything under functions/ is a route candidate, and a helper
// module that suddenly answers HTTP requests is a bug nobody looks for.

const KODOVAC = new TextEncoder();

export async function otisk(token) {
  // Tokens are stored only as SHA-256 digests — a leaked database must not
  // be a bag of valid logins.
  const digest = await crypto.subtle.digest("SHA-256", KODOVAC.encode(token));
  return [...new Uint8Array(digest)]
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

export function novyToken() {
  const bajty = new Uint8Array(32);
  crypto.getRandomValues(bajty);
  return [...bajty].map((b) => b.toString(16).padStart(2, "0")).join("");
}

export function ted() {
  // Unix seconds, matching the INTEGER columns in db/migrace.
  return Math.floor(Date.now() / 1000);
}

export function json(telo, status = 200, hlavicky = {}) {
  return new Response(JSON.stringify(telo), {
    status,
    headers: { "Content-Type": "application/json; charset=utf-8", ...hlavicky },
  });
}

export function ctiCookie(request, nazev) {
  const cookies = request.headers.get("Cookie") || "";
  for (const kus of cookies.split(";")) {
    const [k, ...v] = kus.trim().split("=");
    if (k === nazev) return v.join("=");
  }
  return null;
}

// __Host-: the browser accepts this cookie only from this exact host, over
// HTTPS, for Path=/ and without Domain. Every product lives under
// *.simtegen.com and counts as the "same site" for SameSite; a plain name
// could be planted (Domain=simtegen.com) by any sibling host that went
// bad, logging a customer into someone else's account.
export const RELACE_COOKIE = "__Host-relace";
// The name before the prefix. Read on local runs (below) and, until
// STARA_RELACE_DO, wherever a product switched from it — so a switch does
// not log everyone out; functions/api/_middleware.js moves such a session
// to the new name and clears the old one on the first API call.
export const STARA_RELACE = "relace";
const STARA_RELACE_DO = Date.UTC(2026, 11, 8) / 1000;
// 30 days from the link; functions/api/_middleware.js renews it on use (sliding,
// at most 90 days) — the manifest says "30 dní od posledního použití".
export const RELACE_TRVANI = 30 * 24 * 3600;
export const ODKAZ_TRVANI = 3600; // link valid 1 hour; rows purged after 24 h

function mistniVyvoj(request, env) {
  // wrangler pages dev on this machine (acceptance tests, personas) speaks
  // plain http://127.0.0.1, where a __Host- cookie (Secure) is not
  // reliably stored. Only there, and only in development mode, the session
  // goes without the prefix and without Secure.
  if (!request || !env || env.VYVOJ !== "ano") return false;
  const url = new URL(request.url);
  return url.protocol === "http:" && ["127.0.0.1", "localhost", "[::1]"].includes(url.hostname);
}

export function cookieHlavicka(token, maxAge, request, env) {
  // HttpOnly: the frontend never reads the session token — it only asks
  // /api/ja who it is. SameSite=Lax blanks the cookie on cross-site POSTs;
  // functions/api/_middleware.js also refuses a foreign Origin, because
  // Lax does not separate sibling products on one registrable domain.
  if (mistniVyvoj(request, env)) {
    return `${STARA_RELACE}=${token}; HttpOnly; SameSite=Lax; Path=/; Max-Age=${maxAge}`;
  }
  return (
    `${RELACE_COOKIE}=${token}; HttpOnly; Secure; SameSite=Lax; ` +
    `Path=/; Max-Age=${maxAge}`
  );
}

export function ctiRelaci(request, env) {
  const token = ctiCookie(request, RELACE_COOKIE);
  if (token) return token;
  if (mistniVyvoj(request, env) || ted() < STARA_RELACE_DO) return ctiCookie(request, STARA_RELACE);
  return null;
}

export async function nactiUzivatele(request, env) {
  const token = ctiRelaci(request, env);
  if (!token) return null;
  const radek = await env.DB.prepare(
    "SELECT u.id, u.email FROM relace r JOIN uzivatele u ON u.id = r.uzivatel_id " +
    "WHERE r.otisk_tokenu = ? AND r.expirace > ?"
  ).bind(await otisk(token), ted()).first();
  return radek || null;
}

export async function tabulkySUzivatelem(env) {
  // Every app table carries uzivatel_id (CI enforces it), so export and
  // deletion can be generic: introspect instead of maintaining a list that
  // would drift the first time a builder adds a table.
  const tabulky = await env.DB.prepare(
    "SELECT name FROM sqlite_master WHERE type = 'table' " +
    "AND name NOT LIKE 'sqlite_%' AND name NOT LIKE '_cf%' " +
    "AND name != 'd1_migrations'"
  ).all();
  const vysledek = [];
  for (const { name } of tabulky.results) {
    const sloupce = await env.DB.prepare(`PRAGMA table_info("${name}")`).all();
    if (sloupce.results.some((s) => s.name === "uzivatel_id")) {
      vysledek.push(name);
    }
  }
  return vysledek;
}
