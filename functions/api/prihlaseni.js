// POST /api/prihlaseni {email} — request a one-time login link.
//
// No passwords anywhere in the product: the email inbox is the identity.
// Development mode (VYVOJ=ano: preview deployments, local tests) hands the
// link back in the response — that keeps the whole flow testable end to end
// with zero mail infrastructure. Anywhere else the link only ever goes by
// e-mail: production WITHOUT the mail settings answers 503 instead of
// falling back to the response, because a link in the response is a login
// as anyone whose address you know. functions/api/_middleware.js enforces
// the same rule over any product's handler, and limits requests per
// network address, per mailbox and per product before this runs.

import { json, novyToken, otisk, ted, ODKAZ_TRVANI } from "../../spolecne.js";
import { prihlasovaciEmail } from "../../ochrana.js";

const EMAIL = /^[^\s@]{1,64}@[^\s@]{1,189}\.[^\s@]{2,}$/;

export async function onRequestPost(context) {
  const { request, env } = context;
  let telo;
  try {
    telo = await request.json();
  } catch {
    return json({ chyba: "Tělo požadavku musí být JSON.", kod: "format" }, 400);
  }
  const email = String(telo.email || "").trim().toLowerCase();
  if (!EMAIL.test(email)) {
    return json({ chyba: "Zadejte prosím platnou e-mailovou adresu.", kod: "email_neplatny" }, 422);
  }

  // Three links per hour per address: enough for a confused customer,
  // useless for turning us into someone's spam cannon.
  const pocet = await env.DB.prepare(
    "SELECT COUNT(*) AS n FROM prihlasovaci_odkazy WHERE email = ? AND vytvoreno > ?"
  ).bind(email, ted() - 3600).first();
  if (pocet.n >= 3) {
    return json({ chyba: "Příliš mnoho pokusů. Zkuste to prosím za hodinu.", kod: "moc_pokusu" }, 429);
  }

  const vyvoj = env.VYVOJ === "ano";
  if (!vyvoj && (!env.RESEND_API_KEY || !env.EMAIL_ODESILATEL)) {
    // Before any link exists: there is no way to deliver it.
    return json({
      chyba: "Přihlašování e-mailem teď nefunguje. Zkuste to prosím později, nebo nám chybu nahlaste.",
      kod: "email_nejde",
    }, 503);
  }

  const token = novyToken();
  await env.DB.prepare(
    "INSERT INTO prihlasovaci_odkazy (otisk_tokenu, email, expirace) VALUES (?, ?, ?)"
  ).bind(await otisk(token), email, ted() + ODKAZ_TRVANI).run();

  const odkaz = `${new URL(request.url).origin}/api/overeni?token=${token}`;

  if (vyvoj) {
    return json({
      stav: "vyvojovy_rezim",
      odkaz,
      upozorneni: "Vývojový režim — odkaz je v odpovědi. "
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
      // The product's name and the customer's language from the template
      // middleware (application-name, simtegen-jazyky + the page / browser).
      ...prihlasovaciEmail(context.data.produkt, odkaz, context.data.jazyk),
    }),
  });
  if (!odpoved.ok) {
    return json({ chyba: "Odeslání e-mailu se nepodařilo. Zkuste to prosím znovu.", kod: "email_neodeslan" }, 502);
  }
  return json({ stav: "odeslano" });
}
