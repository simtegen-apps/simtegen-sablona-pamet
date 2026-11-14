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
//   - it names this product and a time: valid PLATNOST_S seconds back and
//     only BUDOUCNOST_S ahead (a time in the future would stretch the window),
//     and once — the signature's digest goes into pouzite_podpisy (migration
//     0940) BEFORE the session exists, and the table's key refuses a second
//     insert, so two requests racing with one signature cannot both win;
//   - the session lasts RELACE_S, not the customers' 30 days;
//   - the address is @ukazka.invalid, so metrics, reminders and payments
//     already treat it as no customer (the same domain the demo accounts use).
// Same text is built by SimteGen's overeni.zprava_prihlaseni().

import * as klice from "../../schranka_klic.js";
import { cookieHlavicka, json, novyToken, otisk, ted } from "../../spolecne.js";

const KONTROLA = "kontrola@ukazka.invalid";
const PLATNOST_S = 120;
const BUDOUCNOST_S = 5; // clock skew between the mini PC and Cloudflare
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
  if (cas > ted() + BUDOUCNOST_S) return json({ chyba: "Podpis je z budoucnosti." }, 403);
  if (ted() - cas > PLATNOST_S) return json({ chyba: "Podpis je starý." }, 403);
  if (!(await podpisSedi(telo))) return json({ chyba: "Podpis nesedí." }, 403);

  // Once per signature: insert first, the PRIMARY KEY is the check.
  try {
    await env.DB.batch([
      env.DB.prepare("DELETE FROM pouzite_podpisy WHERE vyprsi < ?").bind(ted()),
      env.DB.prepare("INSERT INTO pouzite_podpisy (otisk, vyprsi) VALUES (?, ?)")
        .bind(await otisk(podpis), cas + PLATNOST_S + 60),
    ]);
  } catch {
    return json({ chyba: "Podpis už byl použit." }, 403);
  }

  await env.DB.prepare(
    "INSERT INTO uzivatele (email) VALUES (?) ON CONFLICT(email) DO NOTHING"
  ).bind(KONTROLA).run();
  const uzivatel = await env.DB.prepare("SELECT id FROM uzivatele WHERE email = ?").bind(KONTROLA).first();

  const token = novyToken();
  await env.DB.batch([
    // Older check sessions go: there is only ever one look in progress.
    env.DB.prepare("DELETE FROM relace WHERE uzivatel_id = ?").bind(uzivatel.id),
    env.DB.prepare("INSERT INTO relace (otisk_tokenu, uzivatel_id, expirace) VALUES (?, ?, ?)")
      .bind(await otisk(token), uzivatel.id, ted() + RELACE_S),
  ]);
  return json({ stav: "prihlaseno" }, 200, { "Set-Cookie": cookieHlavicka(token, RELACE_S, request, env) });
}
