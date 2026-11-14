// simtegen-ochrana — ze šablony, NEUPRAVOVAT V PRODUKTU (stavba ho obnoví).
//
// Abuse limits and the login confirmation page, shared by the template's
// Functions. Outside functions/ for the same reason as spolecne.js:
// everything under functions/ is a route candidate. A file of its own and
// not part of spolecne.js because spolecne.js is the PRODUCT's file (seeded
// once, then the builder's): the infrastructure handlers that use these
// helpers are refreshed into products built long ago, and an import of a
// name their old spolecne.js does not export would break the whole
// Functions bundle on deploy. This file travels with them.

const KODOVAC = new TextEncoder();

// ── The customer's language (batch B, 14. 11. 2026) ──────────────────
// The languages the template speaks; a product says which of them it does
// in <meta name="simtegen-jazyky"> (no meta = Czech only). The choice is
// the page's (web/simtegen.js vyberJazyk): the language asked for, then the
// browser's in order (Slovak reads Czech), then English if the product has
// it — so the login mail matches the screen the customer is looking at.
export const JAZYKY_SABLONY = ["cs", "en"];

export function jazykyZeStranky(html) {
  const m = String(html || "").match(/<meta\s+name=["']simtegen-jazyky["']\s+content=["']([^"'<>]*)["']/i);
  const jazyky = m ? m[1].split(/[\s,]+/).filter((j) => JAZYKY_SABLONY.includes(j)) : [];
  return jazyky.includes("cs") ? jazyky : ["cs", ...jazyky];
}

export function jazykZadosti(jazyky, zadany, acceptLanguage) {
  if (jazyky.length < 2) return "cs";
  if (jazyky.includes(zadany)) return zadany;
  for (const kus of String(acceptLanguage || "").split(",")) {
    let j = kus.split(";")[0].trim().toLowerCase().split("-")[0];
    if (j === "sk") j = "cs";
    if (jazyky.includes(j)) return j;
  }
  return jazyky.includes("en") ? "en" : "cs";
}

// The login mail. Czech word for word as the template always wrote it (the
// build swaps an older product's own copy of that text for this call —
// stavitel._EMAIL_JAZYK); English for a customer reading the app in English.
export function prihlasovaciEmail(produkt, odkaz, jazyk) {
  if (jazyk === "en") {
    return {
      subject: produkt ? `${produkt}: your sign-in link` : "Your sign-in link",
      text: "Hello,\n\nto sign in" + (produkt ? ` to ${produkt}` : "")
        + ", open this link (valid for 1 hour):\n"
        + `${odkaz}\n\nIf you did not ask to sign in, ignore this e-mail.\n`,
    };
  }
  return {
    subject: produkt ? `${produkt}: přihlašovací odkaz` : "Váš přihlašovací odkaz",
    text: "Dobrý den,\n\npro přihlášení" + (produkt ? ` do služby ${produkt}` : "")
      + " otevřete tento odkaz (platí 1 hodinu):\n"
      + `${odkaz}\n\nPokud jste o přihlášení nežádali, e-mail ignorujte.\n`,
  };
}

export function vyvoj(env) {
  // Development mode is an explicit opt-in (preview deployments and local
  // runs set VYVOJ=ano), never the absence of production settings: a
  // renamed or deleted mail variable must not quietly turn a live product
  // into one that hands out login links.
  return Boolean(env) && env.VYVOJ === "ano";
}

async function sha256(text) {
  const digest = await crypto.subtle.digest("SHA-256", KODOVAC.encode(text));
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

export function adresaKlienta(request, env) {
  // Cloudflare sets CF-Connecting-IP and a client cannot override it on
  // the edge. Without it in production every caller shares one bucket
  // (fail closed); without it in development mode this is a local run
  // (acceptance tests, personas — one machine, many accounts): null, and
  // vLimitu skips the per-address limit, the per-product ones still count.
  const ip = request.headers.get("CF-Connecting-IP");
  if (ip) return ip;
  return vyvoj(env) ? null : "neznama";
}

export function adresaProPocitani(email) {
  // One mailbox, one budget: "jan+1@", "jan+2@" … all land in jan@, so a
  // script cannot bomb one inbox (or farm trial accounts) by varying the
  // tag. Gmail also ignores dots. Only for COUNTING — the link still goes
  // to exactly the address the customer typed.
  const [mistni, domena] = String(email || "").trim().toLowerCase().split("@");
  if (!mistni || !domena) return String(email || "").trim().toLowerCase();
  let jmeno = mistni.split("+")[0];
  let kde = domena;
  if (kde === "googlemail.com") kde = "gmail.com";
  if (kde === "gmail.com") jmeno = jmeno.replace(/\./g, "");
  return `${jmeno}@${kde}`;
}

// One counter row per (kind, key, window). The key is a digest that
// includes the window number, so the same address gives a different key
// every window: nothing here links one hour to the next, and rows are
// deleted shortly after their window ends (uklid). An IP address or e-mail
// is never stored as such.
export async function vLimitu(env, druh, hodnota, max, oknoS) {
  if (hodnota === null) return true; // see adresaKlienta
  try {
    const nyni = Math.floor(Date.now() / 1000);
    const okno = Math.floor(nyni / oknoS);
    const klic = (await sha256(`${druh}|${okno}|${hodnota}`)).slice(0, 32);
    const radek = await env.DB.prepare(
      "INSERT INTO limity (druh, klic, okno, pocet, vyprsi) VALUES (?, ?, ?, 1, ?) " +
      "ON CONFLICT(druh, klic, okno) DO UPDATE SET pocet = pocet + 1 RETURNING pocet"
    ).bind(druh, klic, okno, (okno + 1) * oknoS).first();
    if (Math.random() < 0.05) await uklid(env, nyni);
    return Boolean(radek) && Number(radek.pocet) <= max;
  } catch {
    // Fail closed: a limit we cannot count is a limit we cannot keep. A
    // broken table means "try later" for a moment, never an open door for
    // a script while nobody looks.
    return false;
  }
}

async function uklid(env, nyni) {
  // Housekeeping without a scheduler: a few percent of counted requests
  // sweep the windows that are over.
  await env.DB.prepare("DELETE FROM limity WHERE vyprsi < ?").bind(nyni - 60).run();
}

const HTML_ZNAKY = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" };

export function potvrzeniPrihlaseni(token) {
  // The e-mailed link only shows this page; the login happens on the
  // button's POST. Mail scanners and link previews open links with GET —
  // with a GET that logs in, they spent the customer's link before the
  // customer clicked it. The token is checked (format) by the caller.
  const t = String(token).replace(/[&<>"']/g, (z) => HTML_ZNAKY[z]);
  const html = `<!doctype html>
<html lang="cs">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex">
<title>Přihlášení</title>
<link rel="stylesheet" href="/styl.css">
<link rel="stylesheet" href="/produkt.css">
</head>
<body>
<main class="obsah">
<section class="karta">
<h1>Přihlášení</h1>
<p>Přihlášení dokončíte tlačítkem níže.</p>
<form method="post" action="/api/overeni">
<input type="hidden" name="token" value="${t}">
<button type="submit" class="tlacitko plne">Přihlásit se</button>
</form>
</section>
</main>
</body>
</html>
`;
  return new Response(html, {
    status: 200,
    headers: {
      "Content-Type": "text/html; charset=utf-8",
      // Styles only from this site, the form only back here, never in a
      // frame. same-origin, not no-referrer: with no-referrer the browser
      // sends "Origin: null" on the form's POST and the origin check in
      // functions/api/_middleware.js would refuse our own button.
      "Content-Security-Policy": "default-src 'none'; style-src 'self'; font-src 'self'; img-src 'self'; "
        + "form-action 'self'; frame-ancestors 'none'; base-uri 'none'",
      "Referrer-Policy": "same-origin",
      "Cache-Control": "no-store",
      "X-Robots-Tag": "noindex",
    },
  });
}

export async function tokenZPotvrzeni(request) {
  // The confirmation form posts urlencoded; a script may post JSON.
  const typ = (request.headers.get("Content-Type") || "").split(";")[0].trim().toLowerCase();
  try {
    if (typ === "application/json") {
      const telo = await request.json();
      return String((telo && telo.token) || "");
    }
    const formular = await request.formData();
    return String(formular.get("token") || "");
  } catch {
    return "";
  }
}
