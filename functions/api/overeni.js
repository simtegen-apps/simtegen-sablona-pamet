// /api/overeni?token=... — the link from the email.
//
// GET only shows a page with a "Přihlásit se" button (ochrana.js); the
// button's POST verifies the token, creates the account on first login,
// opens a session and redirects home. Why two steps: mail scanners and
// link previews open every link with GET, and a GET that logged in spent
// the customer's one-time link before the customer ever clicked it. The
// e-mailed link itself did not change.

import {
  cookieHlavicka, novyToken, otisk, ted, RELACE_TRVANI,
} from "../../spolecne.js";
import { potvrzeniPrihlaseni, tokenZPotvrzeni } from "../../ochrana.js";

const TOKEN = /^[0-9a-f]{64}$/;

function chybova() {
  return new Response(
    "Přihlašovací odkaz je neplatný nebo vypršel. Nechte si prosím poslat nový.",
    { status: 403, headers: { "Content-Type": "text/plain; charset=utf-8" } },
  );
}

export async function onRequestGet(context) {
  const token = new URL(context.request.url).searchParams.get("token") || "";
  if (!TOKEN.test(token)) return chybova();
  // No database here: a GET must not change anything, and a page for a
  // spent link costs nothing — the POST tells the truth.
  return potvrzeniPrihlaseni(token);
}

export async function onRequestPost(context) {
  const { request, env } = context;
  const token = await tokenZPotvrzeni(request);
  const domu = new URL("/", request.url).toString();
  if (!TOKEN.test(token)) return chybova();

  const digest = await otisk(token);
  const odkaz = await env.DB.prepare(
    "SELECT id, email FROM prihlasovaci_odkazy " +
    "WHERE otisk_tokenu = ? AND pouzito = 0 AND expirace > ?"
  ).bind(digest, ted()).first();
  if (!odkaz) return chybova();

  // Single-use before anything else, and conditional: of two requests that
  // both read the link as unused (a double click, a replay racing the
  // customer), only the one whose UPDATE changed the row goes on.
  const spotrebovano = await env.DB.prepare(
    "UPDATE prihlasovaci_odkazy SET pouzito = 1 WHERE id = ? AND pouzito = 0"
  ).bind(odkaz.id).run();
  if (!spotrebovano.meta || spotrebovano.meta.changes !== 1) return chybova();

  await env.DB.prepare(
    "INSERT INTO uzivatele (email) VALUES (?) ON CONFLICT(email) DO NOTHING"
  ).bind(odkaz.email).run();
  const uzivatel = await env.DB.prepare(
    "SELECT id FROM uzivatele WHERE email = ?"
  ).bind(odkaz.email).first();

  const relaceToken = novyToken();
  await env.DB.prepare(
    "INSERT INTO relace (otisk_tokenu, uzivatel_id, expirace) VALUES (?, ?, ?)"
  ).bind(await otisk(relaceToken), uzivatel.id, ted() + RELACE_TRVANI).run();

  // Login is the housekeeping moment: cheap, and guarantees the retention
  // promises in the policy without needing any scheduler.
  await env.DB.batch([
    env.DB.prepare(
      "DELETE FROM prihlasovaci_odkazy WHERE expirace < ? OR pouzito = 1"
    ).bind(ted() - 23 * 3600),
    env.DB.prepare("DELETE FROM relace WHERE expirace < ?").bind(ted()),
  ]);

  return new Response(null, {
    status: 303,
    headers: {
      Location: domu,
      "Set-Cookie": cookieHlavicka(relaceToken, RELACE_TRVANI, request, env),
    },
  });
}
