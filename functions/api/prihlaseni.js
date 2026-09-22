// POST /api/prihlaseni {email} — request a one-time login link.
//
// No passwords anywhere in the product: the email inbox is the identity.
// Without RESEND_API_KEY (typically preview deployments, or production
// before the sending domain exists) the link comes back in the response —
// that keeps the whole flow testable end to end with zero mail
// infrastructure, at the price that such a deployment must never be treated
// as a real login boundary. The response says so explicitly.

import { json, novyToken, otisk, ted, ODKAZ_TRVANI } from "../../spolecne.js";

const EMAIL = /^[^\s@]{1,64}@[^\s@]{1,189}\.[^\s@]{2,}$/;

export async function onRequestPost(context) {
  const { request, env } = context;
  let telo;
  try {
    telo = await request.json();
  } catch {
    return json({ chyba: "Tělo požadavku musí být JSON." }, 400);
  }
  const email = String(telo.email || "").trim().toLowerCase();
  if (!EMAIL.test(email)) {
    return json({ chyba: "Zadejte prosím platnou e-mailovou adresu." }, 422);
  }

  // Three links per hour per address: enough for a confused customer,
  // useless for turning us into someone's spam cannon.
  const pocet = await env.DB.prepare(
    "SELECT COUNT(*) AS n FROM prihlasovaci_odkazy WHERE email = ? AND vytvoreno > ?"
  ).bind(email, ted() - 3600).first();
  if (pocet.n >= 3) {
    return json({ chyba: "Příliš mnoho pokusů. Zkuste to prosím za hodinu." }, 429);
  }

  const token = novyToken();
  await env.DB.prepare(
    "INSERT INTO prihlasovaci_odkazy (otisk_tokenu, email, expirace) VALUES (?, ?, ?)"
  ).bind(await otisk(token), email, ted() + ODKAZ_TRVANI).run();

  const odkaz = `${new URL(request.url).origin}/api/overeni?token=${token}`;

  if (!env.RESEND_API_KEY || !env.EMAIL_ODESILATEL) {
    return json({
      stav: "vyvojovy_rezim",
      odkaz,
      upozorneni: "Odesílání e-mailů není nastavené — odkaz je v odpovědi. "
        + "Toto nasazení neslouží jako skutečné přihlášení.",
    });
  }

  const odpoved = await fetch("https://api.resend.com/emails", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${env.RESEND_API_KEY}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      from: env.EMAIL_ODESILATEL,
      to: [email],
      subject: "Váš přihlašovací odkaz",
      text:
        "Dobrý den,\n\npro přihlášení otevřete tento odkaz (platí 1 hodinu):\n"
        + `${odkaz}\n\nPokud jste o přihlášení nežádali, e-mail ignorujte.\n`,
    }),
  });
  if (!odpoved.ok) {
    return json({ chyba: "Odeslání e-mailu se nepodařilo. Zkuste to prosím znovu." }, 502);
  }
  return json({ stav: "odeslano" });
}
