// POST /api/odhlaseni — drop the session row and blank the cookie.

import { ctiCookie, cookieHlavicka, json, otisk, RELACE_COOKIE } from "../../spolecne.js";

export async function onRequestPost(context) {
  const { request, env } = context;
  const token = ctiCookie(request, RELACE_COOKIE);
  if (token) {
    await env.DB.prepare("DELETE FROM relace WHERE otisk_tokenu = ?")
      .bind(await otisk(token)).run();
  }
  return json({ stav: "odhlaseno" }, 200, { "Set-Cookie": cookieHlavicka("", 0) });
}
