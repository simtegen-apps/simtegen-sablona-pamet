// POST /api/nahlasit {text, kontext} — nahlášení chyby BEZ přihlášení.
// Infrastruktura šablony (NEUPRAVOVAT V PRODUKTU), veřejný endpoint.
//
// Kdo se nedokáže přihlásit, je přesně ten, kdo potřebuje nahlásit chybu —
// a statická stránka účty nemá vůbec. Nic se tu neukládá: hlášení odejde
// šifrovaně firmě (schranka_sifra.js) a hotovo. Odpověď v aplikaci tu proto
// není; kdo ji chce, napíše do zprávy kontakt.
//
// Brzda proti spamu: nejvýš LIMIT_IP hlášení za hodinu z jedné adresy
// a LIMIT_CELKEM za hodinu celkem, počítané v D1 (ochrana.js — otisk, ne
// IP adresa). Dřív to bylo počítadlo v cache jednoho datového centra, které
// skript obešel přes jiné a které při chybě pustilo všechno; teď platí
// všude a při chybě raději odmítne. SimteGen má navíc vlastní strop na
// počet nových hlášení za den.

import { jsonOdpoved, ocistiKontext, zrcadliHlaseni, MIN_DELKA, MAX_DELKA } from "../../schranka_sifra.js";
import { adresaKlienta, vLimitu } from "../../ochrana.js";

const LIMIT_IP = 5;
const LIMIT_CELKEM = 30;

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
  if (!(await vLimitu(env, "nahlasit_ip", adresaKlienta(request, env), LIMIT_IP, 3600))
      || !(await vLimitu(env, "nahlasit", "vse", LIMIT_CELKEM, 3600))) {
    return jsonOdpoved({ chyba: "Teď přijímáme hodně hlášení — zkuste to prosím za hodinu." }, 429);
  }
  const cislo = await zrcadliHlaseni(env, "Hlášení (bez přihlášení)", {
    zdroj: "bez_prihlaseni", text, kontext: ocistiKontext(telo.kontext),
  });
  return jsonOdpoved({ stav: "prijato", predano: Boolean(cislo) });
}
