// /api/hlaseni — the product's mailbox.
//
// GET  → the signed-in customer's own reports, newest first, with answers.
// POST → {text}: store the report, then mirror it as an issue in the
//        product's GitHub repo WITHOUT the account (no e-mail, no id of the
//        user — only the report number). The firm's triage reads issues;
//        the customer never leaves the app. Mirroring is best effort: a
//        failed GitHub call must not lose the report.
//
// Not gated by the subscription: reporting a problem is a right, not a
// feature. Rate-limited per account so a stuck retry loop cannot flood
// the repo.

import { json, ted } from "../../spolecne.js";

const MIN_DELKA = 3;
const MAX_DELKA = 2000;
const MAX_ZA_HODINU = 5;

export async function onRequestGet(context) {
  const { env, data } = context;
  if (!data.uzivatel) return json({ chyba: "Nejste přihlášeni." }, 401);
  const radky = await env.DB.prepare(
    "SELECT id, text, stav, odpoved, vytvoreno, zmeneno FROM hlaseni " +
    "WHERE uzivatel_id = ? ORDER BY id DESC LIMIT 50"
  ).bind(data.uzivatel.id).all();
  return json({ hlaseni: radky.results });
}

export async function onRequestPost(context) {
  const { env, data, request } = context;
  if (!data.uzivatel) return json({ chyba: "Nejste přihlášeni." }, 401);

  let telo;
  try {
    telo = await request.json();
  } catch {
    return json({ chyba: "Neplatný požadavek." }, 400);
  }
  const text = String((telo && telo.text) || "").trim();
  if (text.length < MIN_DELKA) return json({ chyba: "Napište nám prosím, o co jde." }, 422);
  if (text.length > MAX_DELKA) {
    return json({ chyba: `Zpráva je moc dlouhá (max ${MAX_DELKA} znaků).` }, 422);
  }

  const nedavno = await env.DB.prepare(
    "SELECT COUNT(*) AS n FROM hlaseni WHERE uzivatel_id = ? AND vytvoreno > ?"
  ).bind(data.uzivatel.id, ted() - 3600).first();
  if (nedavno && nedavno.n >= MAX_ZA_HODINU) {
    return json({ chyba: "Za poslední hodinu jste poslali hodně zpráv — zkuste to prosím později." }, 429);
  }

  const vlozeno = await env.DB.prepare(
    "INSERT INTO hlaseni (uzivatel_id, text) VALUES (?, ?) RETURNING id, vytvoreno"
  ).bind(data.uzivatel.id, text).first();

  let zrcadlo = false;
  const cislo = await zrcadliDoIssue(env, vlozeno.id, text);
  if (cislo) {
    await env.DB.prepare("UPDATE hlaseni SET issue_cislo = ? WHERE id = ?")
      .bind(cislo, vlozeno.id).run();
    zrcadlo = true;
  }
  return json({ id: vlozeno.id, stav: "nove", zrcadlo });
}

async function zrcadliDoIssue(env, id, text) {
  // Both come from the deploy workflow (org secret + repository name). A
  // preview deployment has neither, so test reports never reach the firm.
  if (!env.GITHUB_ISSUES_TOKEN || !env.GITHUB_REPO) return null;
  try {
    const odpoved = await fetch(`https://api.github.com/repos/${env.GITHUB_REPO}/issues`, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${env.GITHUB_ISSUES_TOKEN}`,
        Accept: "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "simtegen-schranka",
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        title: `Hlášení #${id}`,
        // The customer's text is the whole body; no account details.
        body: `${text}\n\n---\nZe schránky produktu, hlášení č. ${id}. Odpověď: komentář začínající „odpoved:“.`,
        labels: ["hlaseni"],
      }),
    });
    if (!odpoved.ok) return null;
    const issue = await odpoved.json();
    return issue.number || null;
  } catch {
    return null;
  }
}
