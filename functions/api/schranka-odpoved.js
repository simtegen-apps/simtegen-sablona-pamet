// POST /api/schranka-odpoved — odpověď firmy k hlášení zákazníka.
// Infrastruktura šablony (NEUPRAVOVAT V PRODUKTU): stavitel soubor při každé
// stavbě obnoví.
//
// Odpověď dřív chodila jen veřejným komentářem „odpoved: …“ na issue
// (workflow Odpoved ji zapsal sem). Repo je veřejné, takže kdokoli mohl
// číst, co firma zákazníkovi napsala — a odpověď často jmenuje zakázku,
// auto nebo člověka z hlášení. Teď ji SimteGen pošle přímo sem po HTTPS,
// podepsanou klíčem, který je jen na mini PC; ověřuje se veřejnou polovinou
// (KLIC_ODPOVEDI v schranka_klic.js, zapisuje ji stavba). Na Cloudflare
// tedy není tajemství, které by šlo ukrást, a GitHub text nevidí vůbec.
//
// Podepsaný text jmenuje repo, číslo hlášení, stav a čas: zachycenou odpověď
// nejde přehrát na hlášení jiného produktu ani o den později. Stejný text
// skládá odpovedi.zprava() v SimteGenu.

import * as klice from "../../schranka_klic.js";
import { json, ted } from "../../spolecne.js";

const STAVY = new Set(["vyrizuje_se", "vyrizeno", "odlozeno"]);
const PLATNOST_S = 600;
const MAX_DELKA = 2000;

function bajty(base64) {
  const s = atob(base64);
  const out = new Uint8Array(s.length);
  for (let i = 0; i < s.length; i++) out[i] = s.charCodeAt(i);
  return out;
}

export function zprava({ repo, id, stav, cas, text }) {
  return new TextEncoder().encode(`schranka-odpoved\nrepo=${repo}\nid=${id}\nstav=${stav}\ncas=${cas}\n${text}`);
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
  // Namespace import: a product whose key file predates the answer key
  // still builds — it just refuses answers until its next build.
  if (!klice.KLIC_ODPOVEDI || !env.GITHUB_REPO) {
    // 404, not 503: the UAT check counts any 5xx as a crash of the endpoint.
    return json({ chyba: "Odpovědi firmy tu nejsou zapnuté." }, 404);
  }
  let telo;
  try {
    telo = await request.json();
  } catch {
    return json({ chyba: "Neplatný požadavek." }, 400);
  }
  const { repo, id, stav, text, cas, podpis } = telo || {};
  if (typeof repo !== "string" || !Number.isInteger(id) || id <= 0 || !STAVY.has(stav)
      || typeof text !== "string" || !text.trim() || text.length > MAX_DELKA
      || !Number.isInteger(cas) || typeof podpis !== "string") {
    return json({ chyba: "Neplatný požadavek." }, 400);
  }
  if (repo.toLowerCase() !== String(env.GITHUB_REPO).toLowerCase()) {
    return json({ chyba: "Odpověď patří jinému produktu." }, 403);
  }
  if (Math.abs(ted() - cas) > PLATNOST_S) return json({ chyba: "Podpis je starý." }, 403);
  if (!(await podpisSedi(telo))) return json({ chyba: "Podpis nesedí." }, 403);

  // mimo-uzivatele: firma odpovídá na hlášení podle jeho čísla, ne za přihlášeného; pustí ji jen podpis
  const zapis = await env.DB.prepare("UPDATE hlaseni SET odpoved = ?, stav = ?, zmeneno = ? WHERE id = ?")
    .bind(text, stav, ted(), id).run();
  if (!zapis.meta || !zapis.meta.changes) return json({ chyba: "Hlášení neexistuje." }, 404);
  return json({ stav: "zapsano" });
}
