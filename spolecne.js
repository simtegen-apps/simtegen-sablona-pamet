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

export const RELACE_COOKIE = "relace";
export const RELACE_TRVANI = 30 * 24 * 3600; // matches manifest: 30 days
export const ODKAZ_TRVANI = 3600; // link valid 1 hour; rows purged after 24 h

export function cookieHlavicka(token, maxAge) {
  // HttpOnly: the frontend never reads the session token — it only asks
  // /api/ja who it is. SameSite=Lax also blanks the cookie on cross-site
  // POSTs, which is the v1 CSRF story.
  return (
    `${RELACE_COOKIE}=${token}; HttpOnly; Secure; SameSite=Lax; ` +
    `Path=/; Max-Age=${maxAge}`
  );
}

export async function nactiUzivatele(request, env) {
  const token = ctiCookie(request, RELACE_COOKIE);
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
