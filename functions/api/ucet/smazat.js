// POST /api/ucet/smazat — the GDPR erasure right, self-service and
// immediate. Same introspection as the export, so a new app table is
// covered by construction; login links go by email (they predate the
// account id), the account row goes last.
//
// Foreign keys: a product may link two of its own tables without ON DELETE
// CASCADE (an item pointing at its category). The tables come back in
// creation order, so the parent's DELETE would run first and fail on the
// child that still points at it — and the whole erasure would roll back.
// `defer_foreign_keys` moves the check to the end of the batch (D1 runs a
// batch as one transaction), when every row of the account is gone.
//
// Reports are also mirrored as issues in the product's public repo
// (schranka_sifra.js): encrypted, but still the customer's words. After
// the rows are gone the issues are closed and their body replaced with a
// neutral sentence; the firm's mailbox sees that sentence and drops its
// own decrypted copy (schranka.py). Best effort: without the token (a
// preview) or with GitHub down the account is still erased here.

import { cookieHlavicka, json, tabulkySUzivatelem } from "../../../spolecne.js";

// The sentence the firm's mailbox recognises — keep it in step with
// schranka.SMAZANO in SimteGen.
const SMAZANO = "Smazáno na žádost zákazníka.";
// Subrequests per invocation are limited on Workers; the cap leaves room
// for the rest. Five reports an hour (hlaseni.js) keeps real accounts well
// below it.
const MAX_ISSUES = 40;

export async function onRequestPost(context) {
  const { env, data, request } = context;
  if (!data.uzivatel) return json({ chyba: "Nejste přihlášeni." }, 401);

  let issues = [];
  try {
    const radky = await env.DB.prepare(
      "SELECT issue_cislo FROM hlaseni WHERE uzivatel_id = ? AND issue_cislo IS NOT NULL ORDER BY id DESC LIMIT ?"
    ).bind(data.uzivatel.id, MAX_ISSUES).all();
    issues = radky.results.map((r) => Number(r.issue_cislo)).filter((n) => Number.isInteger(n) && n > 0);
  } catch {
    issues = []; // a product without the mailbox table
  }

  const prikazy = [env.DB.prepare("PRAGMA defer_foreign_keys = ON")];
  for (const nazev of await tabulkySUzivatelem(env)) {
    prikazy.push(
      env.DB.prepare(`DELETE FROM "${nazev}" WHERE uzivatel_id = ?`)
        .bind(data.uzivatel.id)
    );
  }
  prikazy.push(
    env.DB.prepare("DELETE FROM prihlasovaci_odkazy WHERE email = ?")
      .bind(data.uzivatel.email),
    env.DB.prepare("DELETE FROM uzivatele WHERE id = ?").bind(data.uzivatel.id),
  );
  await env.DB.batch(prikazy);

  await Promise.allSettled(issues.map((cislo) => vymazIssue(env, cislo)));

  return json({ stav: "smazano" }, 200, { "Set-Cookie": cookieHlavicka("", 0, request, env) });
}

async function vymazIssue(env, cislo) {
  // The same token the report was mirrored with: a repo secret scoped to
  // this product when the owner set one, else the shared org secret.
  if (!env.GITHUB_ISSUES_TOKEN || !env.GITHUB_REPO) return;
  await fetch(`https://api.github.com/repos/${env.GITHUB_REPO}/issues/${cislo}`, {
    method: "PATCH",
    headers: {
      Authorization: `Bearer ${env.GITHUB_ISSUES_TOKEN}`,
      Accept: "application/vnd.github+json",
      "X-GitHub-Api-Version": "2022-11-28",
      "User-Agent": "simtegen-vymaz",
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ body: SMAZANO, state: "closed", state_reason: "not_planned" }),
  });
}
