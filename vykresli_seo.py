"""Search and link-preview basics for every product: the meta description,
Open Graph, the Twitter card and the canonical link in web/index.html, plus
web/robots.txt and web/sitemap.xml — all from data-manifest.json.

Why it exists: the first funnel diagnosis was "nobody comes", and the
marketer posts links where the preview IS the ad. A page with a bare
<title> previews as a grey box with the domain in it.

The tags live in a delimited block inside <head>:

    <!-- SEO: GENEROVÁNO z data-manifest.json (vykresli_seo.py) — needituj ručně -->
    ...
    <!-- /SEO -->

Only the block is ever rewritten; everything else in index.html belongs to
the product. An index without the markers (every product born before this
module) gets the block inserted before </head> — refusing instead would
keep its CI red until someone hand-placed two comments.

Manifest inputs:

  produkt     og:title
  popis       the meta and og description, <= 160 characters (search
              engines cut the rest); falls back to aplikace.popis
  adresa      the public URL, https://host without a path. SimteGen writes
              it (domeny.adresa: the subdomain once active, <repo>.pages.dev
              until then) — the repo cannot know its own address, it moves
              without a commit. Without it every URL-dependent piece is left
              out (canonical, og:url, og:image, sitemap.xml, the Sitemap
              line): a guessed canonical tells search engines to index some
              other site, which is worse than no canonical at all.

og:image is the app icon (web/ikona-512.png) and only with the app module:
that module is what draws the icon, so deciding by the manifest instead of
by the file keeps the output independent of the order generators run in.

`zkontroluj(manifest)` is what CI runs (via kontrola_manifestu.py): the
block and both files must equal what this script writes — a hand-edited
block is drift, exactly like a hand-edited privacy policy.

Stdlib only; the same file lives in both templates and is refreshed into
every product like the other generators.
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

WEB = Path("web")
MANIFEST = Path("data-manifest.json")
INDEX = WEB / "index.html"
ROBOTS = WEB / "robots.txt"
SITEMAP = WEB / "sitemap.xml"

ZACATEK = "<!-- SEO: GENEROVÁNO z data-manifest.json (vykresli_seo.py) — needituj ručně -->"
KONEC = "<!-- /SEO -->"
HLAVICKA = "GENEROVANÝ SOUBOR z data-manifest.json (vykresli_seo.py) — needituj ručně."
POPIS_DELKA = 160
# Legal pages of both templates, in sitemap order; only those the product has.
PRAVNI = ("zasady.html", "podminky.html", "zpracovatelska-smlouva.html", "odstoupeni-formular.html")
OBRAZEK = "ikona-512.png"

_ADRESA = re.compile(r"^https://[a-z0-9](?:[a-z0-9-]*[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]*[a-z0-9])?)+$")
# The first block only. A second one is not ours, and it must stay visible
# to the checker's scans (they skip exactly what this module proves).
_BLOK = re.compile(re.escape("<!-- SEO:") + r".*?" + re.escape(KONEC), re.DOTALL)
# Tags the block owns. A copy outside it leaves two descriptions or two
# canonicals, and which one a crawler believes is undefined.
_VLASTNI = re.compile(r"""<meta\s[^>]*(?:name\s*=\s*["'](?:description|twitter:[\w:]+)["']"""
                      r"""|property\s*=\s*["']og:[\w:]+["'])[^>]*>|<link\s[^>]*rel\s*=\s*["']canonical["'][^>]*>""",
                      re.IGNORECASE)


def _atr(text: str) -> str:
    return html.escape(text, quote=True)


def _jednoradkove(text) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def adresa(manifest: dict) -> str:
    """The product's public URL without a trailing slash, or "" when the
    manifest has none or an unusable one (_chyby_konfigurace says which)."""
    url = str(manifest.get("adresa") or "").strip().rstrip("/").lower()
    return url if _ADRESA.match(url) else ""


def _nazev(manifest: dict) -> str:
    aplikace = manifest.get("aplikace") if isinstance(manifest.get("aplikace"), dict) else {}
    return _jednoradkove(manifest.get("produkt") or aplikace.get("nazev"))


def _popis(manifest: dict) -> str:
    aplikace = manifest.get("aplikace") if isinstance(manifest.get("aplikace"), dict) else {}
    return _jednoradkove(manifest.get("popis") or aplikace.get("popis"))


def _chyby_konfigurace(manifest: dict) -> list[str]:
    chyby = []
    surova = str(manifest.get("adresa") or "").strip()
    if surova and not adresa(manifest):
        chyby.append(f"data-manifest.json: adresa „{surova[:80]}“ není https://domena bez cesty "
                     "(doplňuje ji SimteGen — needituj ji ručně).")
    if len(_popis(manifest)) > POPIS_DELKA:
        chyby.append(f"data-manifest.json: popis má {len(_popis(manifest))} znaků, nejvýš {POPIS_DELKA} "
                     "— vyhledávač delší popis usekne uprostřed věty.")
    return chyby


def blok(manifest: dict) -> str:
    """The block itself, its first line without indentation (that belongs
    to the surrounding file)."""
    url, nazev, popis = adresa(manifest), _nazev(manifest), _popis(manifest)
    radky = [ZACATEK]
    if popis:
        radky.append(f'<meta name="description" content="{_atr(popis)}">')
    if url:
        radky.append(f'<link rel="canonical" href="{url}/">')
    radky += ['<meta property="og:type" content="website">',
              '<meta property="og:locale" content="cs_CZ">']
    if nazev:
        radky.append(f'<meta property="og:title" content="{_atr(nazev)}">')
    if popis:
        radky.append(f'<meta property="og:description" content="{_atr(popis)}">')
    if url:
        radky.append(f'<meta property="og:url" content="{url}/">')
        if "aplikace" in manifest:
            radky.append(f'<meta property="og:image" content="{url}/{OBRAZEK}">')
    # "summary", not "summary_large_image": the only picture is a square
    # icon, which the large card would crop into a strip.
    radky.append('<meta name="twitter:card" content="summary">')
    radky.append(KONEC)
    return "\n  ".join(radky)


def index_s_blokem(text: str, manifest: dict) -> str | None:
    """index.html with the current block. None when it cannot be placed: no
    </head>, or half a block (a start without an end, or the reverse) — a
    hand edit whose end nobody can guess without eating product content."""
    novy = blok(manifest)
    m = _BLOK.search(text)
    if m:
        return text[:m.start()] + novy + text[m.end():]
    if "<!-- SEO:" in text or KONEC in text or "</head>" not in text:
        return None
    return text.replace("</head>", f"  {novy}\n</head>", 1)


def bez_bloku(text: str) -> str:
    """index.html with the block's lines blanked (line numbers kept). For
    the checkers' network scans: the canonical <link href="https://…"> is
    not a request, and the block is proven equal to the generator here."""
    return _BLOK.sub(lambda m: "\n" * m.group(0).count("\n"), text, count=1)


def robots(manifest: dict) -> str:
    url = adresa(manifest)
    radky = [f"# {HLAVICKA}", "User-agent: *", "Allow: /",
             # The API answers people with accounts, not crawlers.
             "Disallow: /api/"]
    if url:
        radky += ["", f"Sitemap: {url}/sitemap.xml"]
    return "\n".join(radky) + "\n"


def sitemap(manifest: dict) -> str | None:
    """None without an address: the sitemap protocol wants absolute URLs.
    No lastmod — the output must not depend on when it was generated."""
    url = adresa(manifest)
    if not url:
        return None
    stranky = [""] + [jmeno for jmeno in PRAVNI if (WEB / jmeno).exists()]
    radky = ['<?xml version="1.0" encoding="UTF-8"?>', f"<!-- {HLAVICKA} -->",
             '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    radky += [f"  <url><loc>{url}/{jmeno}</loc></url>" for jmeno in stranky]
    radky.append("</urlset>")
    return "\n".join(radky) + "\n"


def vystupy(manifest: dict) -> dict[Path, str | None]:
    """Whole generated files; None = must not exist."""
    return {ROBOTS: robots(manifest), SITEMAP: sitemap(manifest)}


def vykresli(manifest: dict) -> list[str]:
    """Write every output. Returns the paths written or removed."""
    zapsano = []
    for cesta, obsah in vystupy(manifest).items():
        if obsah is None:
            if cesta.exists():
                cesta.unlink()
                zapsano.append(str(cesta))
            continue
        cesta.parent.mkdir(parents=True, exist_ok=True)
        if not cesta.exists() or cesta.read_text(encoding="utf-8") != obsah:
            cesta.write_text(obsah, encoding="utf-8", newline="\n")
            zapsano.append(str(cesta))
    if INDEX.exists():
        puvodni = INDEX.read_text(encoding="utf-8")
        novy = index_s_blokem(puvodni, manifest)
        if novy is None:
            raise SystemExit("web/index.html: blok SEO nejde umístit — chybí </head>, nebo je blok rozbitý "
                             f"(„{ZACATEK[:12]}…“ bez „{KONEC}“ nebo naopak). Oprav značky ručně a spusť znovu.")
        if novy != puvodni:
            INDEX.write_text(novy, encoding="utf-8", newline="\n")
            zapsano.append(str(INDEX))
    return zapsano


def zkontroluj(manifest: dict) -> list[str]:
    """CI: the block and both files equal the generator, nothing outside
    the block duplicates its tags."""
    chyby = _chyby_konfigurace(manifest)
    oprava = "spusť `python vykresli_seo.py` (generuje se z manifestu, ručně se needituje)"
    if INDEX.exists():
        text = INDEX.read_text(encoding="utf-8").replace("\r\n", "\n")
        ocekavany = index_s_blokem(text, manifest)
        if ocekavany is None:
            chyby.append("web/index.html: blok SEO nejde umístit — chybí </head>, nebo je blok rozbitý "
                         f"(začátek bez „{KONEC}“ nebo naopak).")
        elif ocekavany != text:
            chyby.append(f"web/index.html: blok SEO chybí nebo neodpovídá manifestu — {oprava}.")
        cizi = _VLASTNI.search(_BLOK.sub("", text, count=1))
        if cizi:
            chyby.append(f"web/index.html: {cizi.group(0)[:70]} mimo blok SEO — smaž ho; popis patří "
                         "do manifestu (popis), zbytek dělá generátor.")
    for cesta, obsah in vystupy(manifest).items():
        if obsah is None:
            if cesta.exists():
                chyby.append(f"{cesta.as_posix()} bez adresy produktu v manifestu nemá být — {oprava}.")
        elif not cesta.exists() or cesta.read_text(encoding="utf-8").replace("\r\n", "\n") != obsah:
            chyby.append(f"{cesta.as_posix()} neodpovídá manifestu — {oprava}.")
    return chyby


def main() -> int:
    if not MANIFEST.exists():
        print("CHYBA: chybí data-manifest.json.")
        return 1
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    for chyba in _chyby_konfigurace(manifest):
        print("Pozor (SEO):", chyba)
    zapsano = vykresli(manifest)
    print("SEO vykresleno:", ", ".join(zapsano) if zapsano else "beze změny")
    if not adresa(manifest):
        print("Pozor: v manifestu chybí adresa produktu — kanonický odkaz, og:url, obrázek náhledu "
              "a sitemap.xml se vynechaly (adresu doplní SimteGen).")
    if not _popis(manifest):
        print("Pozor: v manifestu chybí popis — vyhledávač i náhled odkazu si vezmou cokoli ze stránky.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
