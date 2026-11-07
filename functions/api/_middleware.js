// simtegen-zdroje — ze šablony, NEUPRAVOVAT V PRODUKTU (stavba ho obnoví).
//
// Where a customer came from, without touching the product's own code and
// without storing anything in the browser. Every link SimteGen places (an
// ad, a catalogue entry) carries ?utm_source=…&utm_campaign=…; the browser
// sends the page's full address as Referer on same-origin calls
// (Referrer-Policy strict-origin-when-cross-origin in web/_headers), so the
// label is there when the page asks for a login link or counts a visit.
//
//   POST /api/prihlaseni  → the label goes onto the login link row
//   GET  /api/overeni     → a NEW account takes the label of its link
//                           (first touch; an older account keeps its own)
//   POST /api/navsteva    → one more visit for that source (numbers only)
//
// It writes after the product's handler and only on success. The login
// link is read BEFORE: the handler deletes a used link straight away.
// Anything that goes wrong here is swallowed: the customer's login already
// happened, and attribution is a nicety, never a reason for a failed
// request. Before the
// 0910_zdroje migration exists the columns are missing and every write
// fails — silently, by the same rule.
//
// The same file carries the trial (migration 0920_konverze), for the same
// reason — it reaches every product without touching the product's code:
//
//   GET /api/ja → the trial end the PRODUCT computed (context.data.predplatne,
//                 set by its own session middleware) goes into zkusebni_doba,
//                 for the Upominky workflow and the metrics; and the answer
//                 gets a header X-SimteGen-Ukazkova-Data saying whether this
//                 account may load sample data (nabidka) or has them (nahrana),
//                 so web/simtegen.js knows without a second request.
//
// Trial end is copied, never recomputed: the products differ (14-day trial,
// a trial owned by the shop rather than the person), and only their own
// predplatne.js knows. A member who does not pay for the subscription is
// marked platce: false by the product and is left out.

const ZNAK = /[^a-z0-9._-]/g;

function stitek(hodnota) {
  const s = String(hodnota || "").trim().toLowerCase().replace(ZNAK, "-").replace(/-+/g, "-").slice(0, 40);
  return s.replace(/^-|-$/g, "");
}

function zdrojZ(referer) {
  try {
    const parametry = new URL(referer).searchParams;
    const zdroj = stitek(parametry.get("utm_source"));
    return zdroj ? { zdroj, kampan: stitek(parametry.get("utm_campaign")) } : null;
  } catch {
    return null;
  }
}

async function otisk(token) {
  // The same digest as spolecne.js — tokens are stored only hashed.
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(token));
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

async function odkazPredOverenim(context) {
  const token = new URL(context.request.url).searchParams.get("token") || "";
  if (!/^[0-9a-f]{64}$/.test(token)) return null;
  const odkaz = await context.env.DB.prepare(
    "SELECT email, zdroj, kampan FROM prihlasovaci_odkazy WHERE otisk_tokenu = ? AND pouzito = 0"
  ).bind(await otisk(token)).first();
  if (!odkaz || !odkaz.zdroj) return null;
  // First touch: an account that already exists keeps what it has.
  const ucet = await context.env.DB.prepare("SELECT 1 FROM uzivatele WHERE email = ?").bind(odkaz.email).first();
  return ucet ? null : odkaz;
}

async function zapis(context, kopie, odkaz, odpoved) {
  const { request, env } = context;
  const url = new URL(request.url);
  if (kopie && url.pathname === "/api/navsteva" && odpoved.ok) {
    const z = zdrojZ(request.headers.get("Referer"));
    if (!z) return;
    await env.DB.prepare(
      "INSERT INTO zdroje_navstev (den, zdroj, kampan, pocet) VALUES (?, ?, ?, 1) " +
      "ON CONFLICT(den, zdroj, kampan) DO UPDATE SET pocet = pocet + 1"
    ).bind(new Date().toISOString().slice(0, 10), z.zdroj, z.kampan).run();
  } else if (kopie && url.pathname === "/api/prihlaseni" && odpoved.ok) {
    const z = zdrojZ(request.headers.get("Referer"));
    if (!z) return;
    const email = String((await kopie.json()).email || "").trim().toLowerCase();
    await env.DB.prepare(
      "UPDATE prihlasovaci_odkazy SET zdroj = ?, kampan = ? " +
      "WHERE id = (SELECT MAX(id) FROM prihlasovaci_odkazy WHERE email = ?)"
    ).bind(z.zdroj, z.kampan, email).run();
  } else if (odkaz && odpoved.status === 303) {
    // The account this very link has just created (it did not exist a
    // moment ago — odkazPredOverenim checked).
    await env.DB.prepare(
      "UPDATE uzivatele SET zdroj = ?, kampan = ? WHERE email = ? AND zdroj IS NULL"
    ).bind(odkaz.zdroj, odkaz.kampan, odkaz.email).run();
  }
}

const UKAZKOVY_UCET = "@ukazka.invalid";

// ── The product's name for the login e-mail ──────────────────────────
// "Váš přihlašovací odkaz" from an unknown sender looked like phishing next
// to the customer's other mail; the subject now names the product. The
// name is the page's <meta name="application-name"> (CI requires it on
// every page), read once per worker from the static index and handed to
// the handler as context.data.produkt — the product's prihlaseni.js uses
// it when present (template; older products get their subject line
// rewritten by the build, stavitel._NAZEV_V_EMAILU).
let nazevProduktu = null;

async function nactiNazev(context) {
  if (nazevProduktu !== null) return nazevProduktu;
  const stranka = await context.env.ASSETS.fetch(new URL("/", context.request.url));
  const html = stranka.ok ? await stranka.text() : "";
  const m = html.match(/<meta\s+name=["']application-name["']\s+content=["']([^"'<>]{1,60})["']/i);
  nazevProduktu = m ? m[1].trim() : "";
  return nazevProduktu;
}

async function zapisZkusebni(context) {
  const { env, data } = context;
  const p = data.predplatne;
  if (!p || p.stav !== "zkusebni" || p.platce === false) return;
  // The template answers the trial end in plati_do, a product with a
  // separate trial date in zkusebni_do (Pneusklad); either is unix seconds.
  const konec = Math.floor(Number(p.zkusebni_do || p.plati_do));
  if (!Number.isFinite(konec) || konec <= 0) return;
  // Written only when it changed: one cheap no-op on every other /api/ja.
  await env.DB.prepare(
    "INSERT INTO zkusebni_doba (uzivatel_id, konec, zapsano) VALUES (?, ?, unixepoch()) " +
    "ON CONFLICT(uzivatel_id) DO UPDATE SET konec = excluded.konec, zapsano = excluded.zapsano " +
    "WHERE zkusebni_doba.konec != excluded.konec"
  ).bind(data.uzivatel.id, konec).run();
}

async function stavUkazky(context) {
  const { env, data, request } = context;
  const radek = await env.DB.prepare(
    "SELECT po FROM ukazkova_data WHERE uzivatel_id = ?"
  ).bind(data.uzivatel.id).first();
  if (radek) return "nahrana";
  // Offered only where the product ships sample data (play/ukazka.json,
  // published as /ukazka.json). The product itself decides WHEN to show the
  // button — in its empty state; this only says whether it can work.
  const soubor = await env.ASSETS.fetch(new URL("/ukazka.json", request.url));
  return soubor.ok ? "nabidka" : null;
}

async function sJa(context, odpoved) {
  const { data } = context;
  if (!data.uzivatel || String(data.uzivatel.email || "").endsWith(UKAZKOVY_UCET)) return odpoved;
  try {
    await zapisZkusebni(context);
  } catch {
    // Before the 0920 migration, or a product state of an odd shape.
  }
  let ukazka = null;
  try {
    ukazka = await stavUkazky(context);
  } catch {
    // Same: no table yet means no sample data, not a broken /api/ja.
  }
  if (!ukazka) return odpoved;
  const nova = new Response(odpoved.body, odpoved);
  nova.headers.set("X-SimteGen-Ukazkova-Data", ukazka);
  return nova;
}

// ── Sliding login ─────────────────────────────────────────────────────
// A login used to end 30 days after the link, however often the customer
// came back — the mechanic who opens the app every morning was asked for a
// new link once a month, in the middle of work. Now every API call made in
// the session's second half renews it to 30 days from now; a session is
// never older than a year (then one new link). At most one write per
// session per two weeks, so no cost on ordinary calls. Here and not in the
// product's spolecne.js: this file is refreshed in every product on its
// next build, together with the manifest wording that the policy prints
// ("30 dní od posledního použití, nejdéle rok").
const DEN_S = 86400;
const RELACE_DNI = 30;
const RELACE_NEJDELE_DNI = 365;

function cookieRelace(request) {
  const hlavicka = request.headers.get("Cookie") || "";
  for (const cast of hlavicka.split(";")) {
    const [k, ...v] = cast.trim().split("=");
    if (k === "relace") return v.join("=");
  }
  return null;
}

async function prodluzRelaci(context, odpoved) {
  const { request, env, data } = context;
  // Logout, account deletion and a fresh login set their own cookie; a demo
  // account lives 24 hours by design.
  if (!data.uzivatel || odpoved.headers.has("Set-Cookie")
      || String(data.uzivatel.email || "").endsWith(UKAZKOVY_UCET)) return odpoved;
  const token = cookieRelace(request);
  if (!token) return odpoved;
  const otiskTokenu = await otisk(token);
  const radek = await env.DB.prepare(
    "SELECT expirace, vytvoreno FROM relace WHERE otisk_tokenu = ?"
  ).bind(otiskTokenu).first();
  const nyni = Math.floor(Date.now() / 1000);
  if (!radek || radek.expirace - nyni > (RELACE_DNI / 2) * DEN_S) return odpoved;
  const nova = Math.min(nyni + RELACE_DNI * DEN_S, Number(radek.vytvoreno) + RELACE_NEJDELE_DNI * DEN_S);
  if (nova <= radek.expirace) return odpoved;
  await env.DB.prepare(
    "UPDATE relace SET expirace = ? WHERE otisk_tokenu = ? AND expirace < ?"
  ).bind(nova, otiskTokenu, nova).run();
  const vysledek = new Response(odpoved.body, odpoved);
  vysledek.headers.append("Set-Cookie",
    `relace=${token}; HttpOnly; Secure; SameSite=Lax; Path=/; Max-Age=${nova - nyni}`);
  return vysledek;
}

export async function onRequest(context) {
  const { request } = context;
  const cesta = new URL(request.url).pathname;
  // The body is the handler's to read; a copy is taken before it does.
  const kopie = request.method === "POST" && (cesta === "/api/prihlaseni" || cesta === "/api/navsteva")
    ? request.clone() : null;
  let odkaz = null;
  if (request.method === "GET" && cesta === "/api/overeni") {
    try {
      odkaz = await odkazPredOverenim(context);
    } catch {
      // Before the migration, or a bad token: the handler decides, not us.
    }
  }
  if (request.method === "POST" && cesta === "/api/prihlaseni") {
    try {
      context.data.produkt = (await nactiNazev(context)) || undefined;
    } catch {
      // Without a name the mail says "Váš přihlašovací odkaz", as before.
    }
  }
  const odpoved = await context.next();
  try {
    await zapis(context, kopie, odkaz, odpoved);
  } catch {
    // See the header: never the customer's problem.
  }
  let vysledek = odpoved;
  if (request.method === "GET" && cesta === "/api/ja" && odpoved.ok) {
    try {
      vysledek = await sJa(context, odpoved);
    } catch {
      // The product's answer, untouched, rather than none.
    }
  }
  if (vysledek.ok) {
    try {
      vysledek = await prodluzRelaci(context, vysledek);
    } catch {
      // A login that is not renewed today is renewed tomorrow.
    }
  }
  return vysledek;
}
