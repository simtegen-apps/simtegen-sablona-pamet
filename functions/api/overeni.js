// GET /api/overeni?token=... — the link from the email. Verifies the token,
// creates the account on first login, opens a session, redirects home.

import {
  cookieHlavicka, novyToken, otisk, ted, RELACE_TRVANI,
} from "../../spolecne.js";

export async function onRequestGet(context) {
  const { request, env } = context;
  const token = new URL(request.url).searchParams.get("token") || "";
  const domu = new URL("/", request.url).toString();

  const chybova = () => new Response(
    "Přihlašovací odkaz je neplatný nebo vypršel. Nechte si prosím poslat nový.",
    { status: 403, headers: { "Content-Type": "text/plain; charset=utf-8" } },
  );

  if (!/^[0-9a-f]{64}$/.test(token)) return chybova();

  const digest = await otisk(token);
  const odkaz = await env.DB.prepare(
    "SELECT id, email FROM prihlasovaci_odkazy " +
    "WHERE otisk_tokenu = ? AND pouzito = 0 AND expirace > ?"
  ).bind(digest, ted()).first();
  if (!odkaz) return chybova();

  // Single-use before anything else: a replayed link must find it spent.
  await env.DB.prepare(
    "UPDATE prihlasovaci_odkazy SET pouzito = 1 WHERE id = ?"
  ).bind(odkaz.id).run();

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
      "Set-Cookie": cookieHlavicka(relaceToken, RELACE_TRVANI),
    },
  });
}
