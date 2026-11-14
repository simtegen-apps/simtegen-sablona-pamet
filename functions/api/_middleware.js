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
//   POST /api/overeni     → a NEW account takes the label of its link
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
//
// And the protection every product needs whatever its own code says
// (bezpečnostní kontrola 7. 11. 2026) — here because this file reaches
// every product on its next build, the product's handlers do not:
//
//   any write          → refused from a foreign Origin (or Sec-Fetch-Site):
//                        every product is "the same site" under
//                        simtegen.com, so SameSite=Lax alone lets a
//                        compromised sibling post with our customer's
//                        cookie; and a text/plain or urlencoded body is
//                        refused where JSON is expected — request.json()
//                        parses text/plain too, and a plain HTML form on any
//                        page can send both without asking the browser first
//   POST /api/prihlaseni → limits per network address, per mailbox (plus
//                        addressing folded) and per product, counted in D1
//                        (ochrana.js, migration 0940); and outside
//                        development mode (VYVOJ=ano) an answer carrying the
//                        link is replaced by a 503 — an older product's
//                        handler fell back to the link whenever the mail
//                        settings went missing
//   /api/overeni       → in a product whose handler still logs in on GET,
//                        GET only shows the confirmation page and its POST is
//                        handed to that handler (mail scanners open links)
//   every answer       → nosniff, no-store, a CSP for data, HSTS
//   sessions           → renewed at most 90 days from the login; a session
//                        under the old cookie name moves to the product's
//                        new one (__Host-relace) and the old one is cleared
//
// And the customer's language (migration 0950, batch B 14. 11. 2026) — the
// product's prihlaseni.js gets context.data.jazyk (the page's, else the
// browser's, only among the languages the product declares) for the login
// mail; the language rides on the link and onto the new account like the
// source label; /api/ja answers it in X-SimteGen-Jazyk-Uctu for a product
// that speaks more than one, and the page corrects it via /api/jazyk.

import { RELACE_COOKIE, cookieHlavicka } from "../../spolecne.js";
import {
  adresaKlienta, adresaProPocitani, jazykZadosti, jazykyZeStranky, potvrzeniPrihlaseni, tokenZPotvrzeni,
  vLimitu, vyvoj,
} from "../../ochrana.js";
import * as overeniProduktu from "./overeni.js";

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

async function odkazPredOverenim(context, token) {
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
// The same read gives the languages the product speaks (simtegen-jazyky):
// the login mail goes in the customer's, and /api/ja tells the page which
// language the account has (batch B, 14. 11. 2026).
let nazevProduktu = null;
let jazykyProduktu = null;

async function nactiStranku(context) {
  if (nazevProduktu !== null) return;
  const stranka = await context.env.ASSETS.fetch(new URL("/", context.request.url));
  const html = stranka.ok ? await stranka.text() : "";
  const m = html.match(/<meta\s+name=["']application-name["']\s+content=["']([^"'<>]{1,60})["']/i);
  nazevProduktu = m ? m[1].trim() : "";
  jazykyProduktu = jazykyZeStranky(html);
}

async function nactiNazev(context) {
  await nactiStranku(context);
  return nazevProduktu;
}

async function nactiJazyky(context) {
  await nactiStranku(context);
  return jazykyProduktu;
}

// The language onto the login link, and from the link onto the account it
// creates — the same path as the source label above, and like it never the
// customer's problem when it fails (before migration 0950 it always does).
async function jazykOdkazu(context, token) {
  if (!/^[0-9a-f]{64}$/.test(token)) return null;
  return context.env.DB.prepare(
    "SELECT email, jazyk FROM prihlasovaci_odkazy WHERE otisk_tokenu = ? AND pouzito = 0"
  ).bind(await otisk(token)).first();
}

async function zapisJazyk(context, email, odkaz, odpoved) {
  const { env, data } = context;
  if (email && data.jazyk && odpoved.ok) {
    await env.DB.prepare(
      "UPDATE prihlasovaci_odkazy SET jazyk = ? WHERE id = (SELECT MAX(id) FROM prihlasovaci_odkazy WHERE email = ?)"
    ).bind(data.jazyk, email).run();
  } else if (odkaz && odkaz.jazyk && odpoved.status === 303) {
    await env.DB.prepare(
      "UPDATE uzivatele SET jazyk = ? WHERE email = ? AND jazyk IS NULL"
    ).bind(odkaz.jazyk, odkaz.email).run();
  }
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
  // The account's language, for a product that speaks more than one: the
  // page corrects it through /api/jazyk when it differs ("" = not set yet).
  let jazyk = null;
  try {
    if ((await nactiJazyky(context)).length > 1) {
      const radek = await context.env.DB.prepare("SELECT jazyk FROM uzivatele WHERE id = ?")
        .bind(data.uzivatel.id).first();
      jazyk = radek ? String(radek.jazyk || "") : null;
    }
  } catch {
    // Before migration 0950: the page simply does not ask.
  }
  if (!ukazka && jazyk === null) return odpoved;
  const nova = new Response(odpoved.body, odpoved);
  if (ukazka) nova.headers.set("X-SimteGen-Ukazkova-Data", ukazka);
  if (jazyk !== null) nova.headers.set("X-SimteGen-Jazyk-Uctu", jazyk);
  return nova;
}

// ── Sliding login ─────────────────────────────────────────────────────
// A login used to end 30 days after the link, however often the customer
// came back — the mechanic who opens the app every morning was asked for a
// new link once a month, in the middle of work. Now every API call made in
// the session's second half renews it to 30 days from now; a session is
// never older than 90 days (then one new link: a stolen cookie must not
// live for a year). At most one write per session per two weeks, so no
// cost on ordinary calls. Here and not in the product's spolecne.js: this
// file is refreshed in every product on its next build, together with the
// manifest wording that the policy prints ("30 dní od posledního použití,
// nejdéle 90 dní").
const DEN_S = 86400;
const RELACE_DNI = 30;
const RELACE_NEJDELE_DNI = 90;
const STARA_RELACE = "relace";
const SMAZAT_STAROU = `${STARA_RELACE}=; HttpOnly; Secure; SameSite=Lax; Path=/; Max-Age=0`;

function ctiCookie(request, nazev) {
  const hlavicka = request.headers.get("Cookie") || "";
  for (const cast of hlavicka.split(";")) {
    const [k, ...v] = cast.trim().split("=");
    if (k === nazev) return v.join("=");
  }
  return null;
}

function jmenoRelace(request, env) {
  // The product's own helper decides: "relace" in a product built before
  // the prefix, "__Host-relace" in the template — and plain "relace" there
  // too on a local http run in development mode (spolecne.js).
  return String(cookieHlavicka("x", 0, request, env)).split("=")[0] || RELACE_COOKIE;
}

async function relaceVOdpovedi(context, odpoved) {
  const { request, env, data } = context;
  const nazev = jmenoRelace(request, env);
  const novy = ctiCookie(request, nazev);
  const stary = nazev !== STARA_RELACE ? ctiCookie(request, STARA_RELACE) : null;
  let vysledek = odpoved;
  const pridej = (cookie) => {
    if (vysledek === odpoved) vysledek = new Response(odpoved.body, odpoved);
    vysledek.headers.append("Set-Cookie", cookie);
  };
  // The old name goes whenever it shows up next to a product that moved
  // on — it is either this customer's session (moved below) or a cookie
  // somebody else planted.
  if (stary) pridej(SMAZAT_STAROU);
  // Logout, account deletion and a fresh login set their own cookie.
  if (!data.uzivatel || odpoved.headers.has("Set-Cookie")) return vysledek;
  const token = novy || stary;
  if (!token) return vysledek;
  const otiskTokenu = await otisk(token);
  const radek = await env.DB.prepare(
    "SELECT expirace, vytvoreno FROM relace WHERE otisk_tokenu = ?"
  ).bind(otiskTokenu).first();
  const nyni = Math.floor(Date.now() / 1000);
  if (!radek || radek.expirace <= nyni) return vysledek;
  let expirace = Number(radek.expirace);
  // A demo account lives 24 hours by design: moved, never renewed.
  const ukazka = String(data.uzivatel.email || "").endsWith(UKAZKOVY_UCET);
  if (!ukazka && expirace - nyni <= (RELACE_DNI / 2) * DEN_S) {
    const nova = Math.min(nyni + RELACE_DNI * DEN_S, Number(radek.vytvoreno) + RELACE_NEJDELE_DNI * DEN_S);
    if (nova > expirace) {
      await env.DB.prepare(
        "UPDATE relace SET expirace = ? WHERE otisk_tokenu = ? AND expirace < ?"
      ).bind(nova, otiskTokenu, nova).run();
      expirace = nova;
    }
  }
  if (novy && expirace === Number(radek.expirace)) return vysledek;
  pridej(cookieHlavicka(token, expirace - nyni, request, env));
  return vysledek;
}

// ── Protection ────────────────────────────────────────────────────────
const BEZ_TELA = new Set(["GET", "HEAD", "OPTIONS"]);
// Bodies a plain HTML form on any page can send without the browser
// asking first (no CORS preflight) and that request.json() would still
// parse or a handler might take as data. multipart stays allowed (a file
// upload); the Origin check covers it.
const FORMULAROVE = new Set(["text/plain", "application/x-www-form-urlencoded"]);
const EMAIL = /^[^\s@]{1,64}@[^\s@]{1,189}\.[^\s@]{2,}$/;
const HODINA_S = 3600;
const NEJDE_EMAIL = "Přihlašování e-mailem teď nefunguje. Zkuste to prosím později, nebo nám chybu nahlaste.";
// Every refusal here carries a `kod` besides the Czech sentence: a page in
// another language shows SimteGen.chyba(data) — its own words for the code
// (web/simtegen.js, sg.chyba.*) — never the Czech text.

function odpovedJson(telo, status, hlavicky = {}) {
  return new Response(JSON.stringify(telo), {
    status, headers: { "Content-Type": "application/json; charset=utf-8", ...hlavicky },
  });
}

function cislo(hodnota, vychozi) {
  const n = Number.parseInt(String(hodnota ?? ""), 10);
  return Number.isFinite(n) && n > 0 ? n : vychozi;
}

function zCiziStranky(request, url) {
  // Origin is what browsers send on every POST; Sec-Fetch-Site where an
  // older one does not. A request with neither is no browser (SimteGen's
  // own signed calls, curl) — and cookies ride only in browsers.
  const puvod = request.headers.get("Origin");
  if (puvod) return puvod !== url.origin;
  const stranka = request.headers.get("Sec-Fetch-Site");
  if (stranka) return stranka !== "same-origin" && stranka !== "none";
  return false;
}

async function brzdaPrihlaseni(context) {
  // Before the product's handler: a request over a limit never creates a
  // link or reaches the mail service. The limits are per hour; the global
  // one (LIMIT_PRIHLASENI_HODINA) keeps a script with many addresses from
  // spending the firm's mail quota — and its name — for every product.
  const { request, env } = context;
  const moc = (zprava, kod = "moc_pokusu") => odpovedJson({ chyba: zprava, kod }, 429,
    { "Retry-After": String(HODINA_S) });
  if (!(await vLimitu(env, "prihlaseni_ip", adresaKlienta(request, env),
    cislo(env.LIMIT_PRIHLASENI_IP, 10), HODINA_S))) {
    return moc("Příliš mnoho pokusů. Zkuste to prosím za hodinu.");
  }
  let email = "";
  try {
    email = String((await request.clone().json()).email || "").trim().toLowerCase();
  } catch {
    return null; // the handler answers a body that is not JSON
  }
  if (!EMAIL.test(email)) return null; // the handler refuses it; nothing goes out
  if (!(await vLimitu(env, "prihlaseni_adresa", adresaProPocitani(email), 3, HODINA_S))) {
    return moc("Příliš mnoho pokusů. Zkuste to prosím za hodinu.");
  }
  if (!(await vLimitu(env, "prihlaseni_produkt", "vse", cislo(env.LIMIT_PRIHLASENI_HODINA, 200), HODINA_S))) {
    return moc("Přihlašovacích e-mailů je teď příliš mnoho. Zkuste to prosím za chvíli.", "moc_emailu");
  }
  try {
    // Expired links go when new ones are asked for (the policy promises 24
    // hours) — a product nobody logs into must not keep them forever.
    await env.DB.prepare(
      "DELETE FROM prihlasovaci_odkazy WHERE expirace < ? OR pouzito = 1"
    ).bind(Math.floor(Date.now() / 1000) - 23 * HODINA_S).run();
  } catch {
    // housekeeping, never the customer's problem
  }
  if (email.endsWith(".invalid") && !vyvoj(env)) {
    // A reserved domain can never receive mail: no send, no bounce on the
    // firm's sender. It answers like the real thing, so SimteGen's check
    // after a deploy (overeni.py, kontrola@ukazka.invalid) sees what a
    // customer would get — including the 503 of a product whose mail
    // settings went missing — and never a link.
    if (!env.RESEND_API_KEY || !env.EMAIL_ODESILATEL) return odpovedJson({ chyba: NEJDE_EMAIL, kod: "email_nejde" }, 503);
    return odpovedJson({ stav: "odeslano" }, 200);
  }
  return null;
}

async function bezOdkazu(odpoved, env) {
  // The handler's answer, unless it carries the link outside development
  // mode. Whatever the product's code does with missing mail settings, a
  // login link only ever leaves by e-mail.
  if (vyvoj(env) || !(odpoved.headers.get("Content-Type") || "").includes("json")) return odpoved;
  let telo;
  try {
    telo = await odpoved.clone().json();
  } catch {
    return odpoved;
  }
  if (telo && typeof telo === "object" && ("odkaz" in telo || telo.stav === "vyvojovy_rezim")) {
    return odpovedJson({ chyba: NEJDE_EMAIL, kod: "email_nejde" }, 503);
  }
  return odpoved;
}

function zabezpec(odpoved, env) {
  // Every /api/ answer: the browser must not guess a type, keep a copy,
  // render data as a page or (outside development mode) try plain http.
  // A product's handler that chose its own Cache-Control, CSP or Referrer
  // policy keeps it; an HTML answer (the login confirmation) brings its own.
  const vysledek = new Response(odpoved.body, odpoved);
  const h = vysledek.headers;
  h.set("X-Content-Type-Options", "nosniff");
  if (!h.has("Referrer-Policy")) h.set("Referrer-Policy", "strict-origin-when-cross-origin");
  if (!h.has("Cache-Control")) h.set("Cache-Control", "no-store");
  if (!h.has("Content-Security-Policy") && !(h.get("Content-Type") || "").startsWith("text/html")) {
    h.set("Content-Security-Policy", "default-src 'none'; frame-ancestors 'none'");
  }
  if (!vyvoj(env)) h.set("Strict-Transport-Security", "max-age=31536000");
  return vysledek;
}

// ── Invoice orders: customers in Czechia only, for now ───────────────
// (batch B, 14. 11. 2026). The web order is an invoice from a Czech firm in
// Kč, paid by bank transfer with a variable symbol. A customer abroad needs
// another VAT regime (reverse charge with a VAT ID in the EU, the customer's
// country's VAT through OSS for a consumer, none at all outside the EU), a
// payment the bank can match without the symbol and an invoice in their
// language — none of that exists yet. So a foreign order is refused here,
// in every product (each one's objednavka.js is its own and old), and the
// page says so before the customer fills anything in (web/simtegen.js);
// customers abroad subscribe in the Android app, where Google Play sells
// and handles the tax. Cloudflare's country of the connection; none (a
// local run, Tor, unknown) is let through — the order still needs a login
// and the firm issues the invoice, never the customer.
function objednavkaMimoCesko(request) {
  const zeme = request.cf && request.cf.country;
  if (typeof zeme !== "string" || !/^[A-Z]{2}$/.test(zeme) || zeme === "XX" || zeme === "T1" || zeme === "CZ") {
    return null;
  }
  return odpovedJson({
    chyba: "Objednávka na fakturu je zatím jen pro zákazníky v Česku.", kod: "objednavka_jen_cesko",
  }, 422);
}

export async function onRequest(context) {
  return zabezpec(await obsluz(context), context.env);
}

async function obsluz(context) {
  const { request, env } = context;
  const url = new URL(request.url);
  const cesta = url.pathname;
  if (!BEZ_TELA.has(request.method)) {
    if (zCiziStranky(request, url)) {
      return odpovedJson({ chyba: "Požadavek z cizí stránky jsme odmítli.", kod: "cizi_stranka" }, 403);
    }
    const typ = (request.headers.get("Content-Type") || "").split(";")[0].trim().toLowerCase();
    // The login confirmation is the one real form (ochrana.js).
    if (FORMULAROVE.has(typ) && cesta !== "/api/overeni") {
      return odpovedJson({ chyba: "Požadavek musí být ve formátu JSON.", kod: "format" }, 415);
    }
  }

  // A product whose handler still logs in on GET (built before the
  // confirmation page): GET shows the page, the page's POST goes to that
  // handler as the GET it understands.
  const stareOvereni = cesta === "/api/overeni" && typeof overeniProduktu.onRequestPost !== "function";
  if (stareOvereni && request.method === "GET") {
    const token = url.searchParams.get("token") || "";
    return /^[0-9a-f]{64}$/.test(token) ? potvrzeniPrihlaseni(token) : context.next();
  }
  let tokenOvereni = null;
  let predat = null;
  if (cesta === "/api/overeni" && request.method === "POST") {
    tokenOvereni = await tokenZPotvrzeni(request.clone());
    if (stareOvereni) {
      const cil = new URL("/api/overeni", url);
      cil.searchParams.set("token", tokenOvereni);
      predat = new Request(cil.toString(), { method: "GET", headers: request.headers });
    }
  }

  if (request.method === "POST" && cesta === "/api/prihlaseni") {
    const zastaveno = await brzdaPrihlaseni(context);
    if (zastaveno) return zastaveno;
  }
  if (request.method === "POST" && cesta === "/api/objednavka") {
    const mimo = objednavkaMimoCesko(request);
    if (mimo) return mimo;
  }

  // The body is the handler's to read; a copy is taken before it does.
  const kopie = request.method === "POST" && (cesta === "/api/prihlaseni" || cesta === "/api/navsteva")
    ? request.clone() : null;
  let odkaz = null;
  let odkazJazyk = null;
  let emailJazyk = "";
  if (tokenOvereni) {
    try {
      odkaz = await odkazPredOverenim(context, tokenOvereni);
    } catch {
      // Before the migration, or a bad token: the handler decides, not us.
    }
    try {
      odkazJazyk = await jazykOdkazu(context, tokenOvereni);
    } catch {
      // Before migration 0950: the account stays Czech, as before.
    }
  }
  if (request.method === "POST" && cesta === "/api/prihlaseni") {
    try {
      context.data.produkt = (await nactiNazev(context)) || undefined;
    } catch {
      // Without a name the mail says "Váš přihlašovací odkaz", as before.
    }
    try {
      // The page may say which language it shows (the template's login form
      // does); otherwise the browser's, like the page's own choice.
      let zadany = "";
      try {
        const telo = await request.clone().json();
        zadany = String(telo.jazyk || "");
        emailJazyk = String(telo.email || "").trim().toLowerCase();
      } catch {
        // the handler answers a body that is not JSON
      }
      context.data.jazyk = jazykZadosti(await nactiJazyky(context), zadany, request.headers.get("Accept-Language"));
    } catch {
      // Czech, as before.
    }
  }
  let odpoved = predat ? await context.next(predat) : await context.next();
  if (request.method === "POST" && cesta === "/api/prihlaseni") {
    odpoved = await bezOdkazu(odpoved, env);
  }
  try {
    await zapis(context, kopie, odkaz, odpoved);
  } catch {
    // See the header: never the customer's problem.
  }
  try {
    await zapisJazyk(context, emailJazyk, odkazJazyk, odpoved);
  } catch {
    // Same rule: a language not remembered is Czech mail, not a failed login.
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
      vysledek = await relaceVOdpovedi(context, vysledek);
    } catch {
      // A login that is not renewed today is renewed tomorrow.
    }
  }
  return vysledek;
}
