// POST /api/kontrolni-prihlaseni — the firm's check account signs in after
// a deploy. Infrastruktura šablony (NEUPRAVOVAT V PRODUKTU): stavitel soubor
// při každé stavbě obnoví.
//
// Why: the check after a deploy (SimteGen overeni.py) used to see only the
// signed-out app — production login goes by e-mail, so the screens customers
// actually live in were never looked at after a release; a regression there
// waited for the first customer to hit it. Now SimteGen signs in here as ONE
// fixed account and looks.
//
// What keeps this from being a back door:
//   - the account is fixed in this file (KONTROLA); the request cannot name
//     any other — whatever goes wrong, nobody becomes a customer;
//   - the request is signed by the key that lives only on the mini PC
//     (RSASSA-PKCS1-v1_5 / SHA-256, verified with KLIC_ODPOVEDI in
//     schranka_klic.js — the public half, nothing secret on Cloudflare); the
//     signed text names its purpose, so a signed answer to a report can never
//     pass as a login and the other way round;
//   - it names this product and a time: valid PLATNOST_S seconds, and once —
//     a session already opened at or after that time spends the signature;
//   - the session lasts RELACE_S, not the customers' 30 days;
//   - the address is @ukazka.invalid, so metrics, reminders and payments
//     already treat it as no customer (the same domain the demo accounts use).
// Same text is built by SimteGen's overeni.zprava_prihlaseni().

import * as klice from "../../schranka_klic.js";
import { cookieHlavicka, json, novyToken, otisk, ted } from "../../spolecne.js";

const KONTROLA = "kontrola@ukazka.invalid";
const PLATNOST_S = 120;
const RELACE_S = 900;

function bajty(base64) {
  const s = atob(base64);
  const out = new Uint8Array(s.length);
  for (let i = 0; i < s.length; i++) out[i] = s.charCodeAt(i);
  return out;
}

export function zprava({ repo, cas }) {
  return new TextEncoder().encode(`kontrolni-prihlaseni\nrepo=${repo}\ncas=${cas}`);
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

export async function onRequestPost(context) {
  const { request, env } = context;
  // 404, not 503: the UAT check counts any 5xx as a crash of the endpoint,
  // and a product built before the answer key simply has no check login.
  if (!klice.KLIC_ODPOVEDI || !env.GITHUB_REPO) {
    return json({ chyba: "Kontrolní přihlášení tu není zapnuté." }, 404);
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
    return json({ chyba: "Přihlášení patří jinému produktu." }, 403);
  }
  if (Math.abs(ted() - cas) > PLATNOST_S) return json({ chyba: "Podpis je starý." }, 403);
  if (!(await podpisSedi(telo))) return json({ chyba: "Podpis nesedí." }, 403);

  await env.DB.prepare(
    "INSERT INTO uzivatele (email) VALUES (?) ON CONFLICT(email) DO NOTHING"
  ).bind(KONTROLA).run();
  const uzivatel = await env.DB.prepare("SELECT id FROM uzivatele WHERE email = ?").bind(KONTROLA).first();
  // Once per signature: a session of the check account opened at or after
  // the signed time means this very signature was used already.
  const pouzito = await env.DB.prepare(
    "SELECT 1 FROM relace WHERE uzivatel_id = ? AND vytvoreno >= ?"
  ).bind(uzivatel.id, cas).first();
  if (pouzito) return json({ chyba: "Podpis už byl použit." }, 403);

  const token = novyToken();
  await env.DB.batch([
    // Older check sessions go: there is only ever one look in progress.
    env.DB.prepare("DELETE FROM relace WHERE uzivatel_id = ?").bind(uzivatel.id),
    env.DB.prepare("INSERT INTO relace (otisk_tokenu, uzivatel_id, expirace) VALUES (?, ?, ?)")
      .bind(await otisk(token), uzivatel.id, ted() + RELACE_S),
  ]);
  return json({ stav: "prihlaseno" }, 200, { "Set-Cookie": cookieHlavicka(token, RELACE_S) });
}
