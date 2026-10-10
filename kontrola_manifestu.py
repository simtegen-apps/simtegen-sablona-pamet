"""CI gate: code, migrations and generated policy must match data-manifest.json.

The memory template stores customer data, so this check is stricter than the
storage-free template's version. Still a deterministic heuristic — it cannot
prove compliance, it exists so the manifest cannot drift from reality
*silently*:

1. Network: the frontend (web/) may only call its own /api/; server code
   (functions/) may additionally call domains declared in sluzby_treti_strany.
2. Policy: web/zasady.html and ZAZNAM_O_ZPRACOVANI.md must equal what
   vykresli_zasady.py generates from the manifest — a hand-edited policy is
   drift, not an improvement.
3. Data model: every table created in db/migrace/ beyond the template's base
   must carry a uzivatel_id column (so export and account deletion reach it)
   and be declared in manifest.ukladame; every declared entity must have a
   table. Deletion by the customer must, by construction, cover everything.

Stdlib only, so the CI step needs nothing but python3.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass

WEB = Path("web")
FUNKCE = Path("functions")
MIGRACE = Path("db") / "migrace"
MANIFEST = Path("data-manifest.json")
ZAZNAM = Path("ZAZNAM_O_ZPRACOVANI.md")

# Tables the template itself ships; account deletion handles them explicitly,
# so they are the only ones allowed to live without a uzivatel_id column.
ZAKLADNI_TABULKY = {"uzivatele", "prihlasovaci_odkazy", "relace"}

# Column names that make a table personal data. An aggregate table (manifest
# `agregaty`) may live without uzivatel_id only if none of these appear —
# a "counter" with an e-mail column is a customer table in disguise.
OSOBNI_SLOUPCE = ("email", "e_mail", "ip", "adresa", "jmeno", "prijmeni", "telefon",
                  "uzivatel", "token", "agent", "cookie", "poznamka", "text")

# Outbound-request markers beyond fetch(), which gets domain-aware handling.
SITOVE_VZORY = (
    "XMLHttpRequest",
    "sendBeacon",
    "new WebSocket",
    '<script src="http',
    "<script src='http",
    "@import url(http",
    '<img src="http',
    "<img src='http",
)

ULOZISTE_VZORY = (
    "localStorage",
    "sessionStorage",
    "indexedDB",
    "document.cookie",
)

_CREATE_TABLE = re.compile(
    r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?[\"'`]?(\w+)", re.IGNORECASE
)


_PRESKOCIT: set[Path] = set()


def _soubory(root: Path, pripony: tuple[str, ...]):
    if not root.exists():
        return
    for path in sorted(root.rglob("*")):
        if path.is_file() and path.suffix.lower() in pripony and path not in _PRESKOCIT:
            yield path


def _zkontroluj_sit(manifest: dict) -> list[str]:
    povolene = [s["domena"] for s in manifest.get("sluzby_treti_strany") or []
                if s.get("domena")]
    chyby: list[str] = []

    def fetch_povoleny(line: str, server: bool) -> bool:
        if "http" not in line:
            return True  # relative call to own /api/
        return server and any(d in line for d in povolene)

    for root, server in ((WEB, False), (FUNKCE, True)):
        for path in _soubory(root, (".html", ".htm", ".js", ".mjs", ".css")):
            for number, line in enumerate(
                path.read_text(encoding="utf-8", errors="replace").splitlines(), 1
            ):
                if "fetch(" in line and not fetch_povoleny(line, server):
                    chyby.append(f"{path}:{number}: fetch mimo deklarované domény "
                                 f"({line.strip()[:80]})")
                for vzor in SITOVE_VZORY:
                    if vzor in line:
                        chyby.append(f"{path}:{number}: {vzor} ({line.strip()[:80]})")
                if "<link" in line and 'href="http' in line:
                    chyby.append(f"{path}:{number}: externí <link> ({line.strip()[:80]})")
    return chyby


def _zkontroluj_uloziste(manifest: dict) -> list[str]:
    if manifest.get("uloziste_v_prohlizeci"):
        return []
    chyby: list[str] = []
    for path in _soubory(WEB, (".html", ".htm", ".js", ".mjs")):
        for number, line in enumerate(
            path.read_text(encoding="utf-8", errors="replace").splitlines(), 1
        ):
            for vzor in ULOZISTE_VZORY:
                if vzor in line:
                    chyby.append(f"{path}:{number}: {vzor} ({line.strip()[:80]})")
    return chyby


def _zkontroluj_zasady(manifest: dict) -> list[str]:
    """The whole legal pack is generated from the manifest and drifts the
    same way: policy, terms, DPA, withdrawal form, record of processing,
    incident procedure. A hand-edited file fails here on purpose — the
    19. 9. 2026 review landed in the generator, not in the files."""
    import vykresli_zasady as generator

    chyby: list[str] = []
    for path, render in generator.VYSTUPY:
        if not path.exists() or path.read_text(encoding="utf-8") != render(manifest):
            chyby.append(f"{path.as_posix()} neodpovídá manifestu — spusť "
                         "`python3 vykresli_zasady.py` (needituj ho ručně).")
    return chyby


def _sloupce(create_stmt: str) -> list[str]:
    """Column names of one CREATE TABLE: comment lines dropped, the body
    between the outer parentheses split on commas, first token of each part
    (constraint lines start with PRIMARY/UNIQUE/FOREIGN and fall out)."""
    text = "\n".join(line for line in create_stmt.splitlines()
                     if not line.strip().startswith("--"))
    if "(" not in text:
        return []
    body = text[text.index("(") + 1:text.rfind(")")]
    names = []
    for part in body.split(","):
        words = part.strip().split()
        if not words:
            continue
        token = words[0].strip('"`').lower()
        if token not in ("primary", "unique", "foreign", "check", "constraint"):
            names.append(token)
    return names


def _zkontroluj_tabulky(manifest: dict) -> list[str]:
    deklarovane = {u.get("entita") for u in manifest.get("ukladame") or []}
    chyby: list[str] = []
    tabulky: set[str] = set()
    for path in _soubory(MIGRACE, (".sql",)):
        text = path.read_text(encoding="utf-8", errors="replace")
        for zapis in re.split(r";", text):
            match = _CREATE_TABLE.search(zapis)
            if not match:
                continue
            nazev = match.group(1)
            tabulky.add(nazev)
            if nazev in ZAKLADNI_TABULKY:
                continue
            if nazev in (manifest.get("agregaty") or []):
                # Aggregates: allowed without uzivatel_id, forbidden to carry
                # anything that looks like a person.
                osobni = [s for s in OSOBNI_SLOUPCE
                          if any(name.startswith(s) or f"_{s}" in name for name in _sloupce(zapis))]
                if osobni:
                    chyby.append(f"{path}: agregační tabulka {nazev} má osobní sloupce "
                                 f"({', '.join(osobni)}) — agregát smí nést jen čísla.")
                continue
            if "uzivatel_id" not in _sloupce(zapis):
                chyby.append(f"{path}: tabulka {nazev} nemá sloupec uzivatel_id "
                             "— export a smazání účtu by ji minuly.")
            if nazev not in deklarovane:
                chyby.append(f"{path}: tabulka {nazev} není deklarovaná "
                             "v manifestu (ukladame).")
    for agregat in manifest.get("agregaty") or []:
        if agregat not in tabulky:
            chyby.append(f"manifest deklaruje agregát {agregat}, ale žádná migrace "
                         "takovou tabulku nezakládá.")
    for entita in sorted(deklarovane - tabulky):
        chyby.append(f"manifest deklaruje entitu {entita}, ale žádná migrace "
                     "takovou tabulku nezakládá.")
    return chyby


LEGAL_PAGES = ("zasady.html", "podminky.html", "zpracovatelska-smlouva.html", "odstoupeni-formular.html")

# Design system v2 („Mřížka a papír“). The files are template
# infrastructure (the builder refreshes them on every build); produkt.css
# is the product's only design input.
NAVRH_SOUBORY = (
    "web/styl.css", "web/produkt.css", "web/simtegen.js",
    "web/pismo/schibsted-grotesk.woff2", "web/pismo/plex-mono-400.woff2", "web/pismo/plex-mono-500.woff2",
)
PRAVNI_STRANKY = LEGAL_PAGES
_BARVA = re.compile(r"#[0-9a-fA-F]{3,8}\b|\b(?:rgba?|hsla?)\s*\(")
_STYL_ATRIBUT = re.compile(r"""\sstyle\s*=\s*("[^"]*"|'[^']*')""", re.IGNORECASE)
_STYL_BLOK = re.compile(r"<style\b[^>]*>(.*?)</style>", re.IGNORECASE | re.DOTALL)
_SVG_BARVA = re.compile(r"""\s(?:fill|stroke|stop-color)\s*=\s*("[^"]*"|'[^']*')""", re.IGNORECASE)
PAPIR_SVETLY, PAPIR_TMAVY = "#f6f4ef", "#161513"


def _jas(hex_barva: str) -> float:
    h = hex_barva.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    kanaly = []
    for i in (0, 2, 4):
        c = int(h[i:i + 2], 16) / 255
        kanaly.append(c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4)
    return 0.2126 * kanaly[0] + 0.7152 * kanaly[1] + 0.0722 * kanaly[2]


def kontrast(a: str, b: str) -> float:
    la, lb = sorted((_jas(a), _jas(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def _zkontroluj_produkt_css() -> list[str]:
    """produkt.css: only --barva-produktu (light, optionally dark) and
    readable on the paper — the product's colour is a pointer and a word
    like „Dnes“, so it must pass as text."""
    cesta = WEB / "produkt.css"
    if not cesta.exists():
        return []
    text = re.sub(r"/\*.*?\*/", "", cesta.read_text(encoding="utf-8"), flags=re.DOTALL)
    chyby: list[str] = []
    deklarace = re.findall(r"([-\w]+)\s*:\s*([^;{}]+);", text)
    for nazev, _ in deklarace:
        if nazev != "--barva-produktu":
            chyby.append(f"web/produkt.css smí nastavit jen --barva-produktu, ne {nazev}.")
    zbytek = re.sub(r"[-\w]+\s*:\s*[^;{}]+;", "", text)
    zbytek = re.sub(r"@media\s*\(\s*prefers-color-scheme\s*:\s*dark\s*\)", "", zbytek)
    if re.sub(r"[\s{}]|:root", "", zbytek):
        chyby.append("web/produkt.css obsahuje něco jiného než :root s --barva-produktu "
                     "(a volitelně totéž v @media (prefers-color-scheme: dark)).")
    tmavy = re.search(r"@media[^{]*dark[^{]*\{(.*)\}", text, re.DOTALL)
    svetla_cast = text[:tmavy.start()] if tmavy else text
    for cast, papir, rezim in ((svetla_cast, PAPIR_SVETLY, "světlém"),
                               (tmavy.group(1) if tmavy else "", PAPIR_TMAVY, "tmavém")):
        m = re.search(r"--barva-produktu\s*:\s*(#[0-9a-fA-F]{6}|#[0-9a-fA-F]{3})\s*;", cast)
        if not m:
            if rezim == "světlém":
                chyby.append("web/produkt.css nemá --barva-produktu jako #hex.")
            continue
        k = kontrast(m.group(1), papir)
        if k < 4.5:
            chyby.append(f"Barva produktu {m.group(1)} má v {rezim} režimu na papíře kontrast {k:.1f}:1 "
                         "— potřeba aspoň 4.5:1 (tmavší ve světlém, světlejší v tmavém).")
    return chyby


def _barvy_v_html(text: str) -> list[str]:
    nalezy: list[str] = []
    for m in list(_STYL_ATRIBUT.finditer(text)) + list(_SVG_BARVA.finditer(text)):
        hodnota = m.group(1)[1:-1]
        if _BARVA.search(hodnota):
            nalezy.append(m.group(0).strip()[:60])
    for m in _STYL_BLOK.finditer(text):
        if _BARVA.search(m.group(1)):
            nalezy.append("<style> s barvou")
    return nalezy


def _zkontroluj_design() -> list[str]:
    """The deterministic part of the design bar (v2). The taste part — one
    main action, the four states, detail that carries information — is the
    reviewer's, from screenshots."""
    chyby: list[str] = []
    for rel in NAVRH_SOUBORY:
        if not Path(rel).exists():
            chyby.append(f"{rel} chybí — návrhový systém v2 je součást každého produktu "
                         "(stavitel ho obnovuje ze šablony).")
    styl = WEB / "styl.css"
    if styl.exists() and "simtegen-navrh v2" not in styl.read_text(encoding="utf-8")[:200]:
        chyby.append("web/styl.css není návrhový systém v2 — v produktu se neupravuje, obnoví ho stavba.")
    chyby += _zkontroluj_produkt_css()
    for path in sorted(WEB.glob("*.html")):
        if path.name in PRAVNI_STRANKY or path.name == "offline.html":
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for odkaz, co in (('href="styl.css"', "styl.css"), ('href="produkt.css"', "produkt.css"),
                          ('src="simtegen.js"', "simtegen.js (úvodní obrazovka s logem)")):
            if odkaz not in text:
                chyby.append(f"{path}: nenačítá {co} (viz Kostra v DESIGN.md).")
        if 'name="viewport"' not in text:
            chyby.append(f"{path}: chybí <meta name=\"viewport\"> — není to mobilní stránka.")
        if 'name="application-name"' not in text:
            chyby.append(f"{path}: chybí <meta name=\"application-name\"> — název produktu pro úvodní obrazovku.")
        # Mandatory reporting: simtegen.js opens the form for any element with
        # this class; a page without one leaves the customer no way to tell us.
        if "nahlasit-chybu" not in text:
            chyby.append(f"{path}: chybí tlačítko „Nahlásit chybu“ (class=\"nahlasit-chybu\") — "
                         "hlášení chyb je povinné na každé stránce aplikace.")
        if '<link rel="stylesheet" href="http' in text or "@import" in text:
            chyby.append(f"{path}: externí styl/písmo — produkty jsou bez závislostí.")
        for nalez in _barvy_v_html(text):
            chyby.append(f"{path}: barva zapsaná přímo v HTML ({nalez}) — barvy jsou jen ve styl.css "
                         "a produkt.css, použij třídu nebo proměnnou.")
    return chyby

def _zkontroluj_bezpecnost(manifest: dict, preskocit: set[Path]) -> list[str]:
    """bezpecnostni_kontrola.py: who may call which endpoint, SQL only with
    bound values, customer data filtered by uzivatel_id, no HTML or code
    built from text, no keys in the repository, the CSP header. Infra like
    this checker — the build refreshes it, so every product gets the rules."""
    if not Path("bezpecnostni_kontrola.py").exists():
        return ["chybí bezpecnostni_kontrola.py — je součást šablony (stavitel ho obnovuje při stavbě)."]
    import bezpecnostni_kontrola

    return [f"bezpečnost: {c}" for c in bezpecnostni_kontrola.zkontroluj(Path.cwd(), manifest, preskocit)]


def _zkontroluj_uat() -> list[str]:
    """uat_kontrola.py: the product's real API (wrangler pages dev, local D1
    from its migrations) — endpoints refuse strangers, the acceptance
    scenarios from the approved spec pass, account B never gets account A's
    data. Mandatory on GitHub Actions; elsewhere without Node it skips, and
    UAT_KONTROLA=vypnuto skips it outside CI (the template's own tests)."""
    import os

    v_ci = os.environ.get("GITHUB_ACTIONS") == "true"
    if not v_ci and os.environ.get("UAT_KONTROLA") == "vypnuto":
        return []
    if not Path("uat_kontrola.py").exists():
        return ["chybí uat_kontrola.py — je součást šablony (stavitel ho obnovuje při stavbě)."]
    import uat_kontrola

    problemy, poznamka = uat_kontrola.zkontroluj(Path.cwd(), povinne=v_ci)
    if poznamka and not problemy:
        print("Akceptační testy:", poznamka)
    return [f"uat: {p}" for p in problemy]


def _zkontroluj_vzhled() -> list[str]:
    """The rendered page (vizualni_kontrola.py): no sideways scroll at 360–1440
    px, labels, thumb-sized targets, contrast in light and dark. Mandatory on
    GitHub Actions, where Chrome always exists — a check that silently skips
    in CI would be a rule that looks enforced and is not. Elsewhere a missing
    browser skips it; VIZUALNI_KONTROLA=vypnuto skips it too, outside CI only
    (the template's own tests run this checker dozens of times)."""
    import os

    v_ci = os.environ.get("GITHUB_ACTIONS") == "true"
    if not v_ci and os.environ.get("VIZUALNI_KONTROLA") == "vypnuto":
        return []
    if not Path("vizualni_kontrola.py").exists():
        return ["chybí vizualni_kontrola.py — je součást šablony (stavitel ho obnovuje při stavbě)."]
    import vizualni_kontrola

    problemy, _, poznamka = vizualni_kontrola.zkontroluj(Path.cwd(), povinne=v_ci)
    if poznamka and not problemy:
        print("Vizuální kontrola:", poznamka)
    return [f"vzhled: {p}" for p in problemy]


def _zkontroluj_aplikaci(manifest: dict) -> list[str]:
    """The installable-app module (vykresli_aplikaci.py): off without an
    `aplikace` section; on, every generated file must equal the generator."""
    if "aplikace" not in manifest:
        return []
    try:
        import vykresli_aplikaci
    except ImportError:
        return ["data-manifest.json zapíná modul aplikace, ale chybí vykresli_aplikaci.py "
                "(obnoví ho příští stavba ze šablony)."]
    return vykresli_aplikaci.zkontroluj(manifest)


def _generovane(manifest: dict) -> set[Path]:
    """Files owned by a generator that proves them separately — the service
    worker has to fetch and cache, which the scans below would flag."""
    try:
        import vykresli_aplikaci
    except ImportError:
        return set()
    return vykresli_aplikaci.generovane_soubory(manifest)


def main() -> int:
    if not MANIFEST.exists():
        print("CHYBA: chybí data-manifest.json.")
        return 1
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    _PRESKOCIT.update(_generovane(manifest))

    chyby = (_zkontroluj_sit(manifest) + _zkontroluj_uloziste(manifest)
             + _zkontroluj_zasady(manifest) + _zkontroluj_tabulky(manifest)
             + _zkontroluj_design() + _zkontroluj_aplikaci(manifest)
             + _zkontroluj_bezpecnost(manifest, _PRESKOCIT) + _zkontroluj_vzhled()
             + _zkontroluj_uat())
    if chyby:
        print("Kód se rozešel s data-manifest.json:")
        for chyba in chyby:
            print(" -", chyba)
        print("Buď to uveď do souladu s manifestem, nebo uprav manifest "
              "a přegeneruj zásady.")
        return 1
    print("Manifest souhlasí s kódem, zásadami i datovým modelem.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
