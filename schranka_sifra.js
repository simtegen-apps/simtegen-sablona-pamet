// Šifrování hlášení a jejich předání firmě — infrastruktura šablony.
// NEUPRAVOVAT V PRODUKTU: stavitel soubor při každé stavbě obnoví.
//
// Hlášení se zrcadlí jako issue v repozitáři produktu, a ten je veřejný
// (org secrets na Free plánu dosáhnou jen do veřejných rep). Text proto
// nikdy neodchází čitelný: zašifruje se veřejným klíčem SimteGenu
// (schranka_klic.js, zapisuje ho stavba) a issue nese jen nečitelný blok.
// Rozšifrovat ho umí jen SimteGen na mini PC. Bez klíče text neodchází
// vůbec — issue jen oznámí, že hlášení existuje.
//
// RSA-OAEP se SHA-256 přes WebCrypto (Workers i prohlížeč); text se krájí
// na kusy, které 3072bitový klíč unese (384 − 2·32 − 2 = 318 bajtů).

import { KLIC_SCHRANKY } from "./schranka_klic.js";

const ZACATEK = "-----SIMTEGEN SIFRA v1-----";
const KONEC = "-----KONEC SIFRY-----";
const KUS = 318;

export const MIN_DELKA = 3;
export const MAX_DELKA = 2000;

export function jsonOdpoved(telo, status = 200) {
  return new Response(JSON.stringify(telo), {
    status,
    headers: { "Content-Type": "application/json; charset=utf-8", "Cache-Control": "no-store" },
  });
}

function base64(bajty) {
  let s = "";
  for (const b of bajty) s += String.fromCharCode(b);
  return btoa(s);
}

export async function zasifruj(obsah) {
  if (!KLIC_SCHRANKY) return null;
  const klic = await crypto.subtle.importKey(
    "jwk", KLIC_SCHRANKY, { name: "RSA-OAEP", hash: "SHA-256" }, false, ["encrypt"],
  );
  const data = new TextEncoder().encode(JSON.stringify(obsah));
  const radky = [];
  for (let i = 0; i < data.length; i += KUS) {
    const sifra = await crypto.subtle.encrypt({ name: "RSA-OAEP" }, klic, data.slice(i, i + KUS));
    radky.push(base64(new Uint8Array(sifra)));
  }
  return `${ZACATEK}\n${radky.join("\n")}\n${KONEC}`;
}

// What the app attaches on its own (web/simtegen.js): technical facts that
// help find the bug, nothing about the person. Anything else is dropped, and
// every value is cut short — the endpoint trusts nobody's shape.
export function ocistiKontext(kontext) {
  const k = kontext && typeof kontext === "object" ? kontext : {};
  const kratke = (v, n) => (typeof v === "string" ? v.slice(0, n) : "");
  return {
    verze: kratke(k.verze, 20),
    obrazovka: kratke(k.obrazovka, 60),
    okno: kratke(k.okno, 20),
    prohlizec: kratke(k.prohlizec, 200),
    chyby: Array.isArray(k.chyby) ? k.chyby.slice(-5).map((c) => kratke(c, 200)) : [],
  };
}

// Who wrote it, without saying who: a pseudonymous fingerprint of the account
// (stable per product, no e-mail, no id the firm could look up), whether it
// pays, and how old it is. Inside the cipher only. The firm's support agent
// weighs reports by it — two "customers" asking for the same thing must not
// be one person with two trial accounts, and a paying customer who cannot
// work comes first. Declared in the manifest (GitHub, zásady). A product
// without accounts (static template) or a missing table just sends nothing.
async function ucetHlaseni(env, id) {
  if (!env.DB || !Number.isInteger(id)) return null;
  try {
    // The report row names its own account (hlaseni.uzivatel_id).
    const u = await env.DB.prepare(
      "SELECT h.uzivatel_id, u.vytvoreno FROM hlaseni h JOIN uzivatele u ON u.id = h.uzivatel_id WHERE h.id = ?"
    ).bind(id).first();
    if (!u) return null;
    const ted = Math.floor(Date.now() / 1000);
    let plati = false;
    try {
      const p = await env.DB.prepare("SELECT plati_do FROM predplatne WHERE uzivatel_id = ?")
        .bind(u.uzivatel_id).first();
      plati = Boolean(p && p.plati_do && p.plati_do > ted);
    } catch {
      plati = false; // a product without the subscription module
    }
    const digest = await crypto.subtle.digest(
      "SHA-256", new TextEncoder().encode(`${env.GITHUB_REPO || ""}:ucet:${u.uzivatel_id}`));
    const otisk = [...new Uint8Array(digest)].slice(0, 8).map((b) => b.toString(16).padStart(2, "0")).join("");
    return { otisk, plati, dni: Math.max(0, Math.floor((ted - u.vytvoreno) / 86400)) };
  } catch {
    return null;
  }
}

export async function zrcadliHlaseni(env, nadpis, obsah) {
  // Both come from the deploy workflow (org secret + repository name). A
  // preview deployment has neither, so test reports never reach the firm.
  if (!env.GITHUB_ISSUES_TOKEN || !env.GITHUB_REPO) return null;
  try {
    const ucet = obsah && obsah.id ? await ucetHlaseni(env, obsah.id) : null;
    const sifra = await zasifruj(ucet ? { ...obsah, ucet } : obsah);
    const telo = sifra
      ? `Hlášení z aplikace. Text je šifrovaný — číst ho umí jen SimteGen.\n\n${sifra}`
      : "Hlášení z aplikace. Text zůstal jen v aplikaci (produkt ještě nemá klíč schránky).";
    const odpoved = await fetch(`https://api.github.com/repos/${env.GITHUB_REPO}/issues`, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${env.GITHUB_ISSUES_TOKEN}`,
        Accept: "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "simtegen-schranka",
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ title: nadpis, body: telo, labels: ["hlaseni"] }),
    });
    if (!odpoved.ok) return null;
    const issue = await odpoved.json();
    return issue.number || null;
  } catch {
    return null;
  }
}
