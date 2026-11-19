// POST /api/odhlaseni — drop the session row and blank the cookie.
// POST /api/odhlaseni {"vsude": true} — drop EVERY session of this account:
// a phone left in a workshop, a shared computer, a login link that went to
// the wrong inbox. Without it the only way out was waiting up to 90 days.

import { ctiRelaci, cookieHlavicka, otisk, STARA_RELACE } from "../../spolecne.js";

export async function onRequestPost(context) {
  const { request, env, data } = context;
  let vsude = false;
  try {
    vsude = (await request.json()).vsude === true;
  } catch {
    // No body: the ordinary logout of this device.
  }
  const token = ctiRelaci(request, env);
  if (vsude && data.uzivatel) {
    await env.DB.prepare("DELETE FROM relace WHERE uzivatel_id = ?")
      .bind(data.uzivatel.id).run();
  } else if (token) {
    await env.DB.prepare("DELETE FROM relace WHERE otisk_tokenu = ?")
      .bind(await otisk(token)).run();
  }
  const hlavicky = new Headers({ "Content-Type": "application/json; charset=utf-8" });
  hlavicky.append("Set-Cookie", cookieHlavicka("", 0, request, env));
  // A session still under the old name goes too (see spolecne.js).
  hlavicky.append("Set-Cookie", `${STARA_RELACE}=; HttpOnly; Secure; SameSite=Lax; Path=/; Max-Age=0`);
  return new Response(JSON.stringify({ stav: "odhlaseno", vsude: vsude && Boolean(data.uzivatel) }), {
    status: 200, headers: hlavicky,
  });
}
