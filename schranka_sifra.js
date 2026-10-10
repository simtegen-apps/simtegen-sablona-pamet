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

export async function zrcadliHlaseni(env, nadpis, obsah) {
  // Both come from the deploy workflow (org secret + repository name). A
  // preview deployment has neither, so test reports never reach the firm.
  if (!env.GITHUB_ISSUES_TOKEN || !env.GITHUB_REPO) return null;
  try {
    const sifra = await zasifruj(obsah);
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
