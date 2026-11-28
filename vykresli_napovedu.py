"""The product's help page: web/napoveda.html from napoveda.json.

Why it exists (P7): a customer who does not know where something is asks
the firm, and the support agent answered from the build specifications —
text written for the builder, not for the customer, and of whichever three
builds came last. A help page written for the customer is both: the place
the customer finds the answer alone, and the ground the agent answers
from (schranka._produkt reads napoveda.json from the product's main).

napoveda.json is written by the builder (every build keeps it current)
and, for "Časté otázky", by SimteGen's bot PR from repeated questions
(prirucka.py) — the owner's merge is the gate. Plain text only:

    {
      "uvod":    "1–2 sentences: what the tool does and for whom",
      "temata":  [{"nadpis": "Jak přidat zakázku", "text": "…"}],      1–12
      "otazky":  [{"otazka": "Jak smažu účet?", "odpoved": "…"}],      0–30
      "en":      {"uvod": "…", "temata": […], "otazky": […]}          optional
    }

"en" (batch B2, 14. 11. 2026) is the same help in English, for a product
that speaks English (simtegen-jazyky). One page carries both: each language
in its own block with lang="cs"/"en", simtegen.js picks by the app's
language and the chrome (back link, headings, footer) switches with data-t.
Without "en" the page is exactly what it always was — a Czech-only product
does not turn red in CI because the generator learned English. CI checks
"en" when it is there; that a bilingual product HAS it is SimteGen's
build gate (stavitel._napoveda_chybi), not CI's, for the same reason.

In "text" and "odpoved" an empty line starts a new paragraph and lines
starting with "- " become a list. No HTML, no links: the page is the
firm's word to the customer, and a link in it is where a planted one would
hide (the same rule as the agent's answers, podpora._ODPOVED_NESMI).

The page uses the app's skeleton (DESIGN.md "Kostra"), so the design and
visual checks hold for it like for any screen. The generator also puts a
"Nápověda" link into the footer of web/index.html (before the privacy
link) when it is missing — the one line of index.html it ever touches.

`zkontroluj()` is what CI runs (via kontrola_manifestu.py): without
napoveda.json nothing is checked (a product from before P7 gets its help
with its next build — SimteGen's own pre-check requires it there); with
it the file must be valid and the page and the link exactly what this
script writes.

Stdlib only; the same file lives in both templates.
"""

from __future__ import annotations

import html
import json
import re
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass

ZDROJ = Path("napoveda.json")
MANIFEST = Path("data-manifest.json")
STRANKA = Path("web") / "napoveda.html"
INDEX = Path("web") / "index.html"
ODKAZ = '<a href="napoveda.html">Nápověda</a>'
_ZASADY = '<a href="zasady.html"'

_LIMITY = {"uvod": 400, "nadpis": 80, "text": 1500, "otazka": 200, "odpoved": 800}
_ZAKAZANE = re.compile(r"<|>|https?://|www\.|\S@\S|javascript:", re.IGNORECASE)


def nacti(root: Path) -> dict | None:
    try:
        data = json.loads((root / ZDROJ).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as e:
        return {"_chyba": f"napoveda.json není čitelný JSON ({e})"}
    return data if isinstance(data, dict) else {"_chyba": "napoveda.json musí být objekt"}


def chyby(data: dict) -> list[str]:
    """What is wrong with napoveda.json, as sentences for the builder."""
    if "_chyba" in data:
        return [data["_chyba"]]
    out = _chyby_casti(data, "")
    if "en" in data:
        en = data["en"]
        if not isinstance(en, dict):
            out.append("napoveda.json: „en“ musí být objekt (uvod, temata, otazky — anglicky).")
        else:
            out += _chyby_casti(en, "en: ")
    return out


def _chyby_casti(data: dict, predpona: str) -> list[str]:
    out = []

    def pole(kde: str, klic: str, hodnota) -> None:
        if not isinstance(hodnota, str) or not hodnota.strip():
            out.append(f"napoveda.json: {predpona}{kde} — chybí text „{klic}“.")
        elif len(hodnota) > _LIMITY[klic]:
            out.append(f"napoveda.json: {predpona}{kde} — „{klic}“ má víc než {_LIMITY[klic]} znaků.")
        elif _ZAKAZANE.search(hodnota):
            out.append(f"napoveda.json: {predpona}{kde} — jen obyčejný text: bez HTML, odkazů a e-mailů.")

    pole("úvod", "uvod", data.get("uvod"))
    temata, otazky = data.get("temata"), data.get("otazky", [])
    if not isinstance(temata, list) or not 1 <= len(temata) <= 12:
        out.append(f"napoveda.json: {predpona}„temata“ musí být seznam 1–12 témat (nadpis + text).")
        temata = []
    if not isinstance(otazky, list) or len(otazky) > 30:
        out.append(f"napoveda.json: {predpona}„otazky“ musí být seznam nejvýš 30 otázek (otazka + odpoved).")
        otazky = []
    for n, t in enumerate(temata, 1):
        t = t if isinstance(t, dict) else {}
        pole(f"téma {n}", "nadpis", t.get("nadpis"))
        pole(f"téma {n}", "text", t.get("text"))
    for n, q in enumerate(otazky, 1):
        q = q if isinstance(q, dict) else {}
        pole(f"otázka {n}", "otazka", q.get("otazka"))
        pole(f"otázka {n}", "odpoved", q.get("odpoved"))
    return out


def _odstavce(text: str, odsazeni: str) -> str:
    """Empty line = paragraph, "- " lines = a list. Escaped: plain text."""
    bloky = []
    for blok in re.split(r"\n\s*\n", text.strip().replace("\r\n", "\n")):
        radky = [r.strip() for r in blok.split("\n") if r.strip()]
        if radky and all(r.startswith("- ") for r in radky):
            polozky = "".join(f"\n{odsazeni}  <li>{html.escape(r[2:].strip())}</li>" for r in radky)
            bloky.append(f"{odsazeni}<ul>{polozky}\n{odsazeni}</ul>")
        elif radky:
            bloky.append(f"{odsazeni}<p>{html.escape(' '.join(radky))}</p>")
    return "\n".join(bloky)


def _nazev(root: Path) -> str:
    try:
        manifest = json.loads((root / MANIFEST).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        manifest = {}
    aplikace = manifest.get("aplikace") if isinstance(manifest.get("aplikace"), dict) else {}
    return " ".join(str(manifest.get("produkt") or aplikace.get("nazev") or "Aplikace").split())


def _faq(otazky: list, jazyk: str) -> str:
    faq = {"@context": "https://schema.org", "@type": "FAQPage", "inLanguage": jazyk,
           "mainEntity": [{"@type": "Question", "name": " ".join(q["otazka"].split()),
                           "acceptedAnswer": {"@type": "Answer", "text": " ".join(q["odpoved"].split())}}
                          for q in otazky]}
    ld = json.dumps(faq, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    return f'  <script type="application/ld+json">{ld}</script>'


def _hlava(data: dict, nazev: str) -> str:
    """For search engines and the AI chats behind them: a description, and
    the questions as schema.org FAQPage — the page's own words, so nothing
    the customer cannot read. Texts are plain by chyby() (no "<"); "</" is
    escaped anyway, the script element must not close early. With "en":
    the language list for simtegen.js and the English questions too."""
    uvod = " ".join(str(data.get("uvod") or "").split())
    popis = f"Nápověda k aplikaci {nazev}: {uvod}"
    if len(popis) > 160:
        popis = popis[:159].rsplit(" ", 1)[0] + "…"
    radky = [f'  <meta name="description" content="{html.escape(popis, quote=True)}">']
    en = data.get("en") if isinstance(data.get("en"), dict) else None
    if en:
        radky.insert(0, '  <meta name="simtegen-jazyky" content="cs en">')
    if data.get("otazky"):
        radky.append(_faq(data["otazky"], "cs"))
    if en and en.get("otazky"):
        radky.append(_faq(en["otazky"], "en"))
    return "\n".join(radky) + "\n"


def _obsah(data: dict, nadpis_otazek: str) -> str:
    sekce = [f'      <section class="karta">\n{_odstavce(data["uvod"], "        ")}\n      </section>']
    for t in data.get("temata") or []:
        sekce.append(f'      <section>\n        <h2 class="sekce-titulek">{html.escape(t["nadpis"].strip())}</h2>\n'
                     f'        <div class="karta">\n{_odstavce(t["text"], "          ")}\n        </div>\n'
                     "      </section>")
    if data.get("otazky"):
        otazky = "\n".join(
            f'        <details class="karta">\n          <summary>{html.escape(q["otazka"].strip())}</summary>\n'
            f'{_odstavce(q["odpoved"], "          ")}\n        </details>' for q in data["otazky"])
        sekce.append(f'      <section>\n        <h2 class="sekce-titulek">{nadpis_otazek}</h2>\n{otazky}\n'
                     "      </section>")
    return "\n".join(sekce)


def _odsad(text: str, kolik: str) -> str:
    return "\n".join(kolik + r if r else r for r in text.split("\n"))


def stranka(data: dict, nazev: str) -> str:
    n = html.escape(nazev, quote=True)
    en = data.get("en") if isinstance(data.get("en"), dict) else None
    if en:
        # Two blocks; the one not in the app's language is hidden by styl.css
        # (html[lang]) — and its lang tells the English-page check which
        # text is not meant to be English.
        obsah = (f'      <div lang="cs" data-jazyk-napovedy="cs">\n{_odsad(_obsah(data, "Časté otázky"), "  ")}\n'
                 f'      </div>\n      <div lang="en" data-jazyk-napovedy="en">\n'
                 f'{_odsad(_obsah(en, "Frequently asked questions"), "  ")}\n      </div>')
        t = {k: f' data-t="sg.napoveda{k}"' for k in ("", ".zpet", ".zasady")}
        t["nahlasit"] = ' data-t="sg.napoveda.nahlasit"'
        t["nahlasit_aria"] = ' data-t-aria-label="sg.napoveda.nahlasit"'
        # Every page that declares two languages loads the product's
        # dictionary right after simtegen.js (kontrola_jazyku.py). Without it
        # the generated page failed that check, which no builder can fix by
        # hand — build 18 went round six times between "napoveda.json has
        # no English" and "napoveda.html does not load texty.js" (17. 11. 2026).
        texty = '\n  <script src="texty.js"></script>'
    else:
        obsah = _obsah(data, "Časté otázky")
        t = {"": "", ".zpet": "", ".zasady": "", "nahlasit": "", "nahlasit_aria": ""}
        texty = ""
    return f"""<!doctype html>
<!-- GENEROVANÝ SOUBOR — neupravuj ručně. Zdroj: napoveda.json, generátor: vykresli_napovedu.py. -->
<html lang="cs">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
  <meta name="application-name" content="{n}">
  <title>Nápověda — {n}</title>
{_hlava(data, nazev)}  <link rel="stylesheet" href="styl.css">
  <link rel="stylesheet" href="produkt.css">
</head>
<body>
  <script src="simtegen.js"></script>{texty}
  <div class="appka">
    <nav class="navigace" aria-label="Hlavní menu">
      <a class="znacka" href="/" aria-label="SimteGen"><span class="znacka-ctverec"></span><span class="znacka-slovo">SimteGen</span></a>
      <a href="/"{t[".zpet"]}>Zpět do aplikace</a>
      <a href="napoveda.html" aria-current="page"{t[""]}>Nápověda</a>
      <span class="mezera"></span>
      <button class="nahlasit-chybu" type="button"{t["nahlasit"]}>Nahlásit chybu</button>
    </nav>
    <header class="hlavicka">
      <h1{t[""]}>Nápověda</h1>
      <button type="button" class="nahlasit-chybu jen-telefon" aria-label="Nahlásit chybu"{t["nahlasit_aria"]}>
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" aria-hidden="true"><path d="M5 21V4M5 4h11l-2 4 2 4H5"/></svg>
      </button>
    </header>
    <main class="obsah">
{obsah}
    </main>
    <footer class="paticka">
      <a href="/"{t[".zpet"]}>Zpět do aplikace</a>
      <a href="zasady.html"{t[".zasady"]}>Zásady zpracování údajů</a>
    </footer>
  </div>
</body>
</html>
"""


def index_s_odkazem(text: str) -> str:
    """The footer link, before the privacy link — or the text unchanged
    when it is there already or the footer has no privacy link to go by."""
    if ODKAZ in text or _ZASADY not in text:
        return text
    i = text.index(_ZASADY)
    zacatek = text.rfind("\n", 0, i) + 1
    odsazeni = text[zacatek:i] if not text[zacatek:i].strip() else ""
    return text[:i] + ODKAZ + "\n" + odsazeni + text[i:]


def vykresli(root: Path | None = None) -> list[str]:
    root = Path(root or Path.cwd())
    data = nacti(root)
    if data is None or chyby(data):
        return []
    zapsano = []
    obsah = stranka(data, _nazev(root))
    cil = root / STRANKA
    if not cil.exists() or cil.read_text(encoding="utf-8").replace("\r\n", "\n") != obsah:
        cil.write_text(obsah, encoding="utf-8", newline="\n")
        zapsano.append(STRANKA.as_posix())
    index = root / INDEX
    if index.exists():
        text = index.read_text(encoding="utf-8").replace("\r\n", "\n")
        novy = index_s_odkazem(text)
        if novy != text:
            index.write_text(novy, encoding="utf-8", newline="\n")
            zapsano.append(INDEX.as_posix())
    return zapsano


def zkontroluj(root: Path | None = None) -> list[str]:
    root = Path(root or Path.cwd())
    data = nacti(root)
    if data is None:
        return []
    out = chyby(data)
    if out:
        return out
    oprava = "spusť python3 vykresli_napovedu.py"
    cil = root / STRANKA
    if not cil.exists() or cil.read_text(encoding="utf-8").replace("\r\n", "\n") != stranka(data, _nazev(root)):
        out.append(f"web/napoveda.html neodpovídá napoveda.json — {oprava} (stránka se needituje ručně).")
    index = root / INDEX
    if index.exists():
        text = index.read_text(encoding="utf-8").replace("\r\n", "\n")
        if ODKAZ not in text:
            out.append(f"web/index.html: v patičce chybí odkaz {ODKAZ} — {oprava}.")
    return out


def main() -> int:
    data = nacti(Path.cwd())
    if data is None:
        print("Nápověda: napoveda.json není — nic se negeneruje.")
        return 0
    problemy = chyby(data)
    if problemy:
        for p in problemy:
            print("CHYBA:", p)
        return 1
    zapsano = vykresli()
    print("Nápověda vykreslena:", ", ".join(zapsano) if zapsano else "beze změny")
    return 0


if __name__ == "__main__":
    sys.exit(main())
