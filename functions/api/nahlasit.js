// POST /api/nahlasit {text, kontext} — nahlášení chyby BEZ přihlášení.
// Infrastruktura šablony (NEUPRAVOVAT V PRODUKTU), veřejný endpoint.
//
// Kdo se nedokáže přihlásit, je přesně ten, kdo potřebuje nahlásit chybu —
// a statická stránka účty nemá vůbec. Nic se tu neukládá: hlášení odejde
// šifrovaně firmě (schranka_sifra.js) a hotovo. Odpověď v aplikaci tu proto
// není; kdo ji chce, napíše do zprávy kontakt.
//
// Brzda proti spamu bez databáze: nejvýš LIMIT hlášení za hodinu na jedno
// datové centrum (Cache API). Hrubé, ale bez osobních údajů — a SimteGen má
// vlastní strop na počet nových hlášení za den.

import { jsonOdpoved, ocistiKontext, zrcadliHlaseni, MIN_DELKA, MAX_DELKA } from "../../schranka_sifra.js";

const LIMIT = 10;

async function vLimitu() {
  try {
    const hodina = Math.floor(Date.now() / 3600000);
    const klic = new Request(`https://limit.simtegen.invalid/nahlasit/${hodina}`);
    const ulozeno = await caches.default.match(klic);
    const pocet = ulozeno ? Number(await ulozeno.text()) || 0 : 0;
    if (pocet >= LIMIT) return false;
    await caches.default.put(klic, new Response(String(pocet + 1), {
      headers: { "Cache-Control": "max-age=3600" },
    }));
    return true;
  } catch {
    return true;
  }
}

export async function onRequestPost(context) {
  const { request, env } = context;
  let telo;
  try {
    telo = await request.json();
  } catch {
    return jsonOdpoved({ chyba: "Neplatný požadavek." }, 400);
  }
  const text = String((telo && telo.text) || "").trim();
  if (text.length < MIN_DELKA) return jsonOdpoved({ chyba: "Napište nám prosím, o co jde." }, 422);
  if (text.length > MAX_DELKA) {
    return jsonOdpoved({ chyba: `Zpráva je moc dlouhá (max ${MAX_DELKA} znaků).` }, 422);
  }
  if (!(await vLimitu())) {
    return jsonOdpoved({ chyba: "Teď přijímáme hodně hlášení — zkuste to prosím za hodinu." }, 429);
  }
  const cislo = await zrcadliHlaseni(env, "Hlášení (bez přihlášení)", {
    zdroj: "bez_prihlaseni", text, kontext: ocistiKontext(telo.kontext),
  });
  return jsonOdpoved({ stav: "prijato", predano: Boolean(cislo) });
}
