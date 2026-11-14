"""Languages of a product (DESIGN.md, Jazyky) — ze šablony, NEUPRAVOVAT V PRODUKTU.

A product that says it speaks more than Czech
(<meta name="simtegen-jazyky" content="cs en">) brings its words in
web/texty.js as one call, SimteGen.slovnik({...}), whose argument is plain
JSON — so this check reads exactly what the browser runs. It refuses:

  - a language the template cannot speak (its own bars would stay Czech),
  - a key in one language and not in the other, a placeholder ({n},
    {nazev}) that one side lost, a plural that is a sentence on one side,
  - a data-t / data-t-* / SimteGen.t("…") key missing from the Czech words
    (the page would show the bare key),
  - a declaring page that does not load texty.js, or a product with no
    switch outside a footer (data-prepinac-jazyka) — a customer whose browser guessed wrong
    must be able to change it.

What it cannot see — Czech written straight into an English screen — the
visual check finds by rendering ?jazyk=en (vizualni_kontrola.py).
Shared by both templates' kontrola_manifestu.py, which import it.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

PODPOROVANE = ("cs", "en")
# Not app screens: generated legal pages and the offline shell (the same
# list as the visual check) — they get their language from their generator.
PRESKOCIT = {"zasady.html", "podminky.html", "zpracovatelska-smlouva.html",
             "odstoupeni-formular.html", "offline.html"}

_META = re.compile(r'<meta\s+name=["\']simtegen-jazyky["\']\s+content=["\']([^"\']*)["\']', re.I)
_DATA_T = re.compile(r'data-t(?:-[a-z-]+)?=["\']([\w.-]+)["\']')
_VOLANI_T = re.compile(r'SimteGen\.t\(\s*["\']([\w.-]+)["\']')
_ZAVORKY = re.compile(r"\{(\w+)\}")
_OBAL = re.compile(r"^\s*(?:/\*.*?\*/\s*)?SimteGen\.slovnik\(\s*(\{.*\})\s*\);?\s*$", re.S)


def jazyky(html: str) -> list[str]:
    m = _META.search(html)
    return [j for j in re.split(r"[\s,]+", m.group(1)) if j] if m else ["cs"]


def nacti_slovnik(cesta: Path) -> dict:
    """texty.js → {"cs": {...}, "en": {...}}; ValueError with a reason."""
    m = _OBAL.match(cesta.read_text(encoding="utf-8"))
    if not m:
        raise ValueError("texty.js musí být jediné volání SimteGen.slovnik({...}); (smí mu předcházet komentář /* */)")
    data = json.loads(m.group(1))
    if not isinstance(data, dict):
        raise ValueError("argument SimteGen.slovnik není objekt")
    return data


def _promenne(hodnota) -> set[str]:
    if isinstance(hodnota, dict):
        return set().union(*(_promenne(v) for v in hodnota.values())) if hodnota else set()
    return set(_ZAVORKY.findall(str(hodnota)))


def zkontroluj(web: Path) -> list[str]:
    if not web.is_dir():
        return []
    stranky = {p: p.read_text(encoding="utf-8", errors="replace")
               for p in sorted(web.glob("*.html")) if p.name not in PRESKOCIT}
    hlasi = {p: jazyky(t) for p, t in stranky.items() if len(jazyky(t)) > 1}
    if not hlasi:
        return []
    chyby: list[str] = []
    vsechny = sorted({j for js in hlasi.values() for j in js})
    for j in vsechny:
        if j not in PODPOROVANE:
            chyby.append(f"simtegen-jazyky: jazyk „{j}“ šablona neumí (umí {', '.join(PODPOROVANE)})")
    if "cs" not in vsechny:
        chyby.append("simtegen-jazyky: čeština je povinná — je zdrojem textů v HTML")
    for p, js in hlasi.items():
        if not re.search(r'<script\s+src=["\']texty\.js["\']', stranky[p]):
            chyby.append(f"web/{p.name}: hlásí jazyky {' '.join(js)}, ale nenačítá texty.js "
                         "(hned za simtegen.js)")
    # The switch is a settings row in the account (12. 11. 2026), never a
    # footer bar: one in a footer draws nothing, so it does not count.
    bez_paticek = [re.sub(r"<footer\b.*?</footer>", "", t, flags=re.S | re.I) for t in stranky.values()]
    if not any("data-prepinac-jazyka" in t for t in bez_paticek):
        chyby.append("web/: produkt mluví víc jazyky, ale v účtu (nastavení) není přepínač — "
                     "<div data-prepinac-jazyka></div> do obrazovky Účet, ne do patičky")

    cesta = web / "texty.js"
    if not cesta.exists():
        return chyby + ["web/texty.js chybí — slovník textů pro jazyky ze simtegen-jazyky"]
    try:
        slovnik = nacti_slovnik(cesta)
    except (ValueError, json.JSONDecodeError) as e:
        return chyby + [f"web/texty.js: {e}"]
    for j in vsechny:
        if not isinstance(slovnik.get(j), dict):
            chyby.append(f"web/texty.js: chybí jazyk „{j}“")
    cs = slovnik.get("cs") if isinstance(slovnik.get("cs"), dict) else {}
    for j in vsechny:
        druhy = slovnik.get(j)
        if j == "cs" or not isinstance(druhy, dict):
            continue
        for k in sorted(set(cs) - set(druhy))[:20]:
            chyby.append(f"web/texty.js: „{k}“ chybí v {j}")
        for k in sorted(set(druhy) - set(cs))[:20]:
            chyby.append(f"web/texty.js: „{k}“ je v {j}, ale ne v cs")
        for k in sorted(set(cs) & set(druhy)):
            a, b = cs[k], druhy[k]
            if isinstance(a, dict) != isinstance(b, dict):
                chyby.append(f"web/texty.js: „{k}“ má tvary množného čísla jen v jednom jazyce")
            elif isinstance(a, dict) and "other" not in b:
                chyby.append(f"web/texty.js: „{k}“ v {j} nemá tvar other")
            elif _promenne(a) != _promenne(b):
                chyby.append(f"web/texty.js: „{k}“ má v cs proměnné {sorted(_promenne(a))}, "
                             f"v {j} {sorted(_promenne(b))}")
            elif isinstance(b, str) and not b.strip():
                chyby.append(f"web/texty.js: „{k}“ je v {j} prázdné")

    pouzite: dict[str, str] = {}
    for p in [*sorted(web.glob("*.html")), *sorted(web.glob("*.js"))]:
        if p.name in ("simtegen.js", "texty.js", "play.js") or p.name in PRESKOCIT:
            continue
        text = p.read_text(encoding="utf-8", errors="replace")
        for k in _DATA_T.findall(text) + _VOLANI_T.findall(text):
            pouzite.setdefault(k, p.name)
    for k, kde in sorted(pouzite.items()):
        if k not in cs and not k.startswith("sg."):
            chyby.append(f"web/{kde}: klíč „{k}“ není v texty.js (cs)")
    return chyby
