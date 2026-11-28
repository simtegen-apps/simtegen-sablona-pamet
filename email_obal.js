// The product's mails to its customers in the product's own dress.
//
// Every mail goes out as multipart: the text part is what it always was
// (the record — § 1837 l "textual form", the words the tests pin), and this
// builds the HTML part from THAT text, line for line: no new sentences, the
// legal ones byte-identical. A customer knows the product, not the firm, so
// the head is the product's name with its colour square; SimteGen signs
// small at the foot.
//
// Lives OUTSIDE functions/ like spolecne.js: everything under functions/ is
// a route candidate, and a helper that suddenly answers HTTP requests is a
// bug nobody looks for. The mails the template repo's workflows send (trial
// reminders, invoices, payments) are built by .github/nastroje/email_obal.py
// — the same markup, keep the two in step (tests/test_email_obal.py
// compares them).
//
// Mail clients are not browsers: tables, inline styles, one system font,
// no CSS variables, web fonts, scripts, SVG or data: URIs (Gmail and
// Outlook strip or block them). Everything that comes from data — the
// product's name, billing details, the firm's answer to a report — is
// escaped; only links this code was handed as links become anchors.

// The logo travels inside the mail as an inline attachment (cid:), not as an
// address on the web: a remote image tells whoever hosts it who opened the
// mail and when — the owner's call (24. 11. 2026). 180 × 37 px on white,
// shown at 90 px; white because clients that invert colours in dark mode
// would lose a transparent ink logo. The same bytes as PRILOHA_LOGA in
// .github/nastroje/email_obal.py and znacka/email/simtegen-logo-180.png in
// the SimteGen repo (tests/test_email_obal.py compares all three).
export const LOGO_CID = "simtegen-logo";
export const LOGO_SIMTEGEN = `cid:${LOGO_CID}`;
export const PRILOHA_LOGA = {
  filename: "simtegen-logo.png",
  content_id: LOGO_CID,
  content: "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",
};

const PISMO = "Arial, Helvetica, sans-serif";
const PAPIR = "#f6f4ef";
const LIST = "#ffffff";
const LINKA = "#dcd8cf";
const INKOUST = "#141414";
const DRUHOTNY = "#5e5c57";

const PODPIS = { cs: "aplikace od SimteGen", en: "an app by SimteGen" };
// The login link's button. The only words the HTML adds, and they are a
// control's label, not a sentence: the Czech one is the button the link
// opens on (ochrana.potvrzeniPrihlaseni), the English one the verb of the
// English subject ("your sign-in link").
export const PRIHLASIT = { cs: "Přihlásit se", en: "Sign in" };

export function escapuj(hodnota) {
  return String(hodnota === undefined || hodnota === null ? "" : hodnota)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
}

// "#abc" / "#aabbcc" → "#aabbcc"; anything else → the ink. The value lands
// in an attribute and a style, so a pattern, not a trust.
export function hexBarva(barva) {
  const s = String(barva || "").trim();
  if (/^#[0-9a-fA-F]{6}$/.test(s)) return s.toLowerCase();
  if (/^#[0-9a-fA-F]{3}$/.test(s)) return ("#" + s.slice(1).split("").map((c) => c + c).join("")).toLowerCase();
  return INKOUST;
}

// The light-theme --barva-produktu from web/produkt.css (the first :root —
// the dark one sits in @media below it; kontrola_manifestu allows nothing
// else in the file). Null when the file does not say: the mail is in ink.
export function barvaZCss(css) {
  const blok = /:root\s*\{([^}]*)\}/.exec(String(css || ""));
  const m = blok && /--barva-produktu\s*:\s*(#[0-9a-fA-F]{6}|#[0-9a-fA-F]{3})\s*;/.exec(blok[1]);
  return m ? hexBarva(m[1]) : null;
}

// Only absolute https links become anchors: the login link (our origin),
// the product's own address from its manifest. Never whitespace, quotes
// or angle brackets — escaped anyway, refused first.
function odkazOk(url) {
  return /^https:\/\/[^\s"'<>\\]+$/.test(String(url || ""));
}

function odstavec(radky) {
  return `<p style="margin:0 0 16px 0;font-family:${PISMO};font-size:15px;line-height:22px;color:${INKOUST};">`
    + radky.join("<br>") + "</p>";
}

function tlacitkoHtml(url, popisek) {
  const h = escapuj(url);
  return `<table role="presentation" cellpadding="0" cellspacing="0" border="0" style="margin:0 0 12px 0;">`
    + `<tr><td bgcolor="${INKOUST}" style="background-color:${INKOUST};">`
    + `<a href="${h}" style="display:inline-block;padding:14px 28px;font-family:${PISMO};font-size:15px;`
    + `font-weight:bold;line-height:20px;color:${PAPIR};text-decoration:none;">${escapuj(popisek)}</a>`
    + "</td></tr></table>"
    // The same link as text under the button: a client that drops the
    // button's styling, or a customer who copies links by hand, still has it.
    + `<p style="margin:0 0 16px 0;font-family:${PISMO};font-size:13px;line-height:20px;color:${DRUHOTNY};`
    + `word-break:break-all;"><a href="${h}" style="color:${DRUHOTNY};text-decoration:underline;">${h}</a></p>`;
}

function odkazHtml(url) {
  const h = escapuj(url);
  return `<a href="${h}" style="color:${INKOUST};text-decoration:underline;word-break:break-all;">${h}</a>`;
}

// The text part, paragraph by paragraph (blank line = paragraph, newline =
// <br>). A line that is exactly the button's link becomes the button; a
// line that is exactly one of `odkazy` becomes an anchor showing itself.
function teloHtml(text, tlacitko, odkazy) {
  const tlacitkoUrl = tlacitko && odkazOk(tlacitko.odkaz) ? tlacitko.odkaz : null;
  const jine = new Set((odkazy || []).filter(odkazOk));
  const vystup = [];
  const odstavce = String(text || "").replace(/\r\n?/g, "\n").trim().split(/\n{2,}/);
  for (const kus of odstavce) {
    let radky = [];
    for (const radek of kus.split("\n")) {
      const cisty = radek.trim();
      if (tlacitkoUrl && cisty === tlacitkoUrl) {
        if (radky.length) vystup.push(odstavec(radky));
        radky = [];
        vystup.push(tlacitkoHtml(tlacitkoUrl, tlacitko.popisek));
      } else if (jine.has(cisty)) {
        radky.push(odkazHtml(cisty));
      } else {
        radky.push(escapuj(radek));
      }
    }
    if (radky.length) vystup.push(odstavec(radky));
  }
  return vystup.join("\n");
}

function hlavickaHtml(produkt, barva) {
  if (!produkt) return "";
  return `<tr><td style="padding:24px 32px 4px 32px;">`
    + `<table role="presentation" cellpadding="0" cellspacing="0" border="0"><tr>`
    + `<td valign="middle" style="padding:0 10px 0 0;">`
    + `<table role="presentation" cellpadding="0" cellspacing="0" border="0"><tr>`
    + `<td width="12" height="12" bgcolor="${barva}" style="width:12px;height:12px;background-color:${barva};`
    + `font-size:0;line-height:0;">&nbsp;</td></tr></table></td>`
    + `<td valign="middle" style="font-family:${PISMO};font-size:18px;line-height:24px;font-weight:bold;`
    + `color:${INKOUST};">${escapuj(produkt)}</td>`
    + "</tr></table></td></tr>";
}

function patickaHtml(jazyk) {
  return `<tr><td style="padding:8px 32px 24px 32px;">`
    + `<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"><tr>`
    + `<td style="border-top:1px solid ${LINKA};padding:16px 0 0 0;">`
    + `<img src="${LOGO_SIMTEGEN}" width="90" alt="SimteGen" style="display:block;width:90px;max-width:90px;`
    + `height:auto;border:0;outline:none;text-decoration:none;font-family:${PISMO};font-size:13px;`
    + `font-weight:bold;color:${INKOUST};">`
    + `<p style="margin:8px 0 0 0;font-family:${PISMO};font-size:12px;line-height:18px;color:${DRUHOTNY};">`
    + `${PODPIS[jazyk]}</p>`
    + "</td></tr></table></td></tr>";
}

// { predmet, text, produkt, barva, jazyk, tlacitko: {odkaz, popisek}, odkazy }
// → the whole HTML document. `text` is the mail's text part, unchanged.
export function htmlEmailu({ predmet, text, produkt, barva, jazyk, tlacitko, odkazy } = {}) {
  const j = jazyk === "en" ? "en" : "cs";
  const nazev = String(produkt || "").trim();
  return `<!doctype html>\n<html lang="${j}">\n<head>\n<meta charset="utf-8">\n`
    + `<meta name="viewport" content="width=device-width, initial-scale=1">\n`
    + `<meta name="color-scheme" content="light">\n<meta name="supported-color-schemes" content="light">\n`
    + `<title>${escapuj(predmet)}</title>\n</head>\n`
    + `<body style="margin:0;padding:0;background-color:${PAPIR};">\n`
    + `<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" bgcolor="${PAPIR}" `
    + `style="background-color:${PAPIR};"><tr><td align="center" style="padding:24px 12px;">\n`
    + `<table role="presentation" width="600" cellpadding="0" cellspacing="0" border="0" bgcolor="${LIST}" `
    + `style="width:100%;max-width:600px;background-color:${LIST};border:1px solid ${LINKA};">\n`
    + hlavickaHtml(nazev, hexBarva(barva)) + "\n"
    + `<tr><td style="padding:20px 32px 8px 32px;">\n${teloHtml(text, tlacitko, odkazy)}\n</td></tr>\n`
    + patickaHtml(j) + "\n"
    + "</table>\n</td></tr></table>\n</body>\n</html>\n";
}
