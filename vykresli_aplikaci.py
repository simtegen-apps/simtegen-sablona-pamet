"""The installable-app module: everything a product needs to become an
Android app (Trusted Web Activity) without a line of native code.

Switched on by an `aplikace` section in data-manifest.json:

    "aplikace": {
      "balicek": "cz.simtegen.evidence_pneu",   # never changes once released
      "nazev": "Evidence pneu",                  # store title, <= 30 chars
      "kratky_nazev": "Pneu",                    # under the icon, <= 12 chars
      "popis": "Kde leží čí pneumatiky.",        # <= 80 chars
      "otisky": ["AB:CD:..."],                   # SHA-256 of the signing key(s)
      "pismeno": "E"                             # optional icon letter
    }

From that section this script writes, deterministically:

  web/manifest.webmanifest     name, colours, icons, and the Play package in
                               related_applications (the release workflow
                               reads the package from the LIVE manifest, so
                               the site is the single source of truth)
  web/.well-known/assetlinks.json
                               Digital Asset Links: Android shows the app
                               without a browser bar only when the site
                               vouches for the signing key. Empty `otisky`
                               is valid — the app then runs with a URL bar
                               until the owner copies the fingerprint from
                               Play Console (App integrity).
  web/sw.js, web/offline.html  a network-first service worker: online the
                               app is exactly the deployed site; offline it
                               shows the shell instead of Chrome's dinosaur.
                               It never touches /api/ — account data must
                               not outlive a session in a cache. It caches
                               only the site's own public files, not
                               anything about the customer.
  web/ikona-*.png              icons drawn from the design system: the
                               product's symbol (play/piktogram.svg, paper
                               lines on a 24 grid) over a gradient of the
                               product colour, a faint drawing grid and a
                               soft shadow; the symbol's `detail` lines
                               (a dimension line, a tick) drawn finer. A
                               product without a symbol keeps one letter.
  web/index.html               the manifest link and the worker registration
                               are inserted if missing (idempotent).

`zkontroluj(manifest)` is what CI runs (via kontrola_manifestu.py): the
files must equal what this script generates — a hand-edited worker is
drift, exactly like a hand-edited privacy policy. Icons are compared by
pixels, not bytes, because zlib builds differ between Windows and the CI
runner.

Stdlib only; the same file lives in both templates and is refreshed into
every product by the builder, like the policy generator.
"""

from __future__ import annotations

import colorsys
import json
import math
import re
import struct
import sys
import unicodedata
import zlib
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass

WEB = Path("web")
MANIFEST = Path("data-manifest.json")
ZNACKA = "<!-- aplikace: vykresli_aplikaci.py -->"
ODKAZ_MANIFESTU = '<link rel="manifest" href="/manifest.webmanifest">'
REGISTRACE = ('<script>if ("serviceWorker" in navigator) '
              'navigator.serviceWorker.register("/sw.js");</script>')
IKONY = (("ikona-192.png", 192, False), ("ikona-512.png", 512, False),
         ("ikona-maskable-512.png", 512, True))

BALICEK_VZOR = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*){2,}$")
OTISK_VZOR = re.compile(r"^([0-9A-F]{2}:){31}[0-9A-F]{2}$")

# The store listing (vizualni_kontrola.py --obchod draws it): 3–6 phone
# shots, each one screen and one sentence; the feature graphic's sentence.
SNIMKY_POCET = (3, 6)
TITULEK_DELKA = (8, 40)
STITEK_DELKA = 24
HLAVNI_VETA_DELKA = (12, 60)
CO_JE_NOVEHO = Path("play") / "co_je_noveho.txt"
CO_JE_NOVEHO_DELKA = 500          # Google's limit for release notes
UKAZKA = Path("play") / "ukazka.json"
# Published for "Vyzkoušet ukázku" (functions/api/ukazka.js + web/play.js):
# the same invented data the screenshots show — public on purpose. Also for
# products without the app: the first-login empty state loads the same data
# into the customer's own account (functions/api/ukazka-uctu.js), so it is
# published whenever play/ukazka.json exists.
UKAZKA_WEB = Path("web") / "ukazka.json"
UKAZKA_KROKU = 60

# The symbol: paper lines on a 24 grid. Ordinary icon: the grid spans 62 %
# of the icon. Maskable: 56 %, and every line must stay within 14 grid
# units of the centre — Android crops adaptive icons to as little as the
# central 66 % circle (14 / 24 × 56 % ≈ 33 % radius).
PIKTOGRAM = Path("play") / "piktogram.svg"
PIKTOGRAM_MERITKO = 0.62
PIKTOGRAM_MERITKO_MASKA = 0.56
BEZPECNY_POLOMER = 14.0
PIKTOGRAM_TVARU = 40
_PIKTOGRAM_ATRIBUTY = {
    "svg": {"viewBox", "xmlns", "width", "height", "fill", "stroke"},
    "g": {"class"},
    "path": {"d", "class"},
    "line": {"x1", "y1", "x2", "y2", "class"},
    "polyline": {"points", "class"},
    "rect": {"x", "y", "width", "height", "class"},
    "circle": {"cx", "cy", "r", "class"},
}

SW = """// Offline shell of the installed app. GENERATED by vykresli_aplikaci.py —
// do not edit; CI compares this file with the generator.
// Network first, always: online the app is exactly the deployed site and the
// cache only answers when the network does not. /api/ is never touched —
// account data must not outlive a session in a cache.
const SKORAPKA = "skorapka-v1";
const PREDEM = ["/", "/styl.css", "/offline.html", "/manifest.webmanifest", "/ikona-192.png", "/ikona-512.png"];

self.addEventListener("install", (udalost) => {
  udalost.waitUntil(caches.open(SKORAPKA).then((c) => c.addAll(PREDEM)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (udalost) => {
  udalost.waitUntil(
    caches.keys()
      .then((klice) => Promise.all(klice.filter((k) => k !== SKORAPKA).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (udalost) => {
  const pozadavek = udalost.request;
  const adresa = new URL(pozadavek.url);
  if (pozadavek.method !== "GET" || adresa.origin !== self.location.origin || adresa.pathname.startsWith("/api/")) {
    return;
  }
  udalost.respondWith(
    fetch(pozadavek)
      .then((odpoved) => {
        if (odpoved.ok && PREDEM.includes(adresa.pathname)) {
          const kopie = odpoved.clone();
          caches.open(SKORAPKA).then((c) => c.put(pozadavek, kopie));
        }
        return odpoved;
      })
      .catch(() => caches.match(pozadavek).then((ulozena) =>
        ulozena || (pozadavek.mode === "navigate" ? caches.match("/offline.html") : Response.error())))
  );
});
"""

OFFLINE = """<!doctype html>
<html lang="cs">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
  <meta name="theme-color" content="{barva}">
  <title>{nazev} — bez připojení</title>
  <link rel="stylesheet" href="styl.css">
  <link rel="stylesheet" href="produkt.css">
</head>
<body class="appka">
  <main class="obrazovka aktivni">
    <div class="karta">
      <h1>Jste offline</h1>
      <p>{nazev} potřebuje připojení k internetu. Jakmile bude zpátky, stačí to zkusit znovu.</p>
      <button class="tlacitko" onclick="location.reload()">Zkusit znovu</button>
    </div>
  </main>
</body>
</html>
"""


# ── Google Play: store listing and Data safety ────────────────────────
#
# The listing and the Data safety form are claims to Google about the data
# — the same claims the privacy policy makes, so they come from the same
# manifest and CI holds them to it. Each `ukladame` entry says which Google
# data type it is (`play_typy`) and why it is collected (`play_ucely`); the
# keys below are the only allowed values. Labels: the Czech Play Console
# wording as best known, the English name in brackets is the exact one.

PLAY_TYPY = {
    "email": ("Osobní údaje", "E-mailová adresa", "Personal info", "Email address"),
    "jmeno": ("Osobní údaje", "Jméno", "Personal info", "Name"),
    "adresa": ("Osobní údaje", "Adresa", "Personal info", "Address"),
    "telefon": ("Osobní údaje", "Telefonní číslo", "Personal info", "Phone number"),
    "id_uzivatele": ("Osobní údaje", "ID uživatelů", "Personal info", "User IDs"),
    "osobni_jine": ("Osobní údaje", "Jiné informace", "Personal info", "Other info"),
    "platebni_udaje": ("Finanční údaje", "Platební údaje uživatele", "Financial info", "User payment info"),
    "historie_nakupu": ("Finanční údaje", "Historie nákupů", "Financial info", "Purchase history"),
    "financni_jine": ("Finanční údaje", "Jiné finanční údaje", "Financial info", "Other financial info"),
    "zpravy": ("Zprávy", "Jiné zprávy v aplikaci", "Messages", "Other in-app messages"),
    "obsah_uzivatele": ("Aktivita v aplikaci", "Jiný obsah vytvořený uživatelem", "App activity",
                        "Other user-generated content"),
    "akce_v_aplikaci": ("Aktivita v aplikaci", "Interakce s aplikací", "App activity", "App interactions"),
    "hledani": ("Aktivita v aplikaci", "Historie vyhledávání v aplikaci", "App activity", "In-app search history"),
    "fotky": ("Fotky a videa", "Fotky", "Photos and videos", "Photos"),
    "soubory": ("Soubory a dokumenty", "Soubory a dokumenty", "Files and docs", "Files and docs"),
    "kalendar": ("Kalendář", "Události v kalendáři", "Calendar", "Calendar events"),
    "kontakty": ("Kontakty", "Kontakty", "Contacts", "Contacts"),
    "poloha_priblizna": ("Poloha", "Přibližná poloha", "Location", "Approximate location"),
    "poloha_presna": ("Poloha", "Přesná poloha", "Location", "Precise location"),
    "diagnostika": ("Informace o aplikaci a výkonu", "Diagnostika", "App info and performance", "Diagnostics"),
    "pady": ("Informace o aplikaci a výkonu", "Protokoly o selhání", "App info and performance", "Crash logs"),
}
PLAY_UCELY = {
    "funkce": ("Funkce aplikace", "App functionality"),
    "ucet": ("Správa účtu", "Account management"),
    "komunikace": ("Komunikace vývojáře", "Developer communications"),
    "analytika": ("Analýza", "Analytics"),
    "bezpecnost": ("Prevence podvodů, zabezpečení a dodržování předpisů", "Fraud prevention, security, and compliance"),
    "personalizace": ("Personalizace", "Personalization"),
    "marketing": ("Reklama nebo marketing", "Advertising or marketing"),
}
PLAY_KATEGORIE = {
    "BUSINESS": "Firmy", "PRODUCTIVITY": "Produktivita", "TOOLS": "Nástroje", "FINANCE": "Finance",
    "EDUCATION": "Vzdělávání", "LIFESTYLE": "Životní styl", "HOUSE_AND_HOME": "Dům a domácnost",
    "FOOD_AND_DRINK": "Jídlo a pití", "HEALTH_AND_FITNESS": "Zdraví a fitness", "SHOPPING": "Nakupování",
    "AUTO_AND_VEHICLES": "Auta a vozidla", "TRAVEL_AND_LOCAL": "Cestování a místní informace",
    "SPORTS": "Sport", "PARENTING": "Rodičovství", "EVENTS": "Události", "COMMUNICATION": "Komunikace",
    "BOOKS_AND_REFERENCE": "Knihy a referenční materiály", "ENTERTAINMENT": "Zábava",
}
# Mandatory "Nahlásit chybu" is in every product: the text the customer
# writes and the technical facts the form attaches, both optional.
HLASENI_PLAY = {"entita": "hlášení chyb (tlačítko Nahlásit chybu)",
                "play_typy": ["zpravy", "diagnostika"], "play_ucely": ["funkce", "komunikace"],
                "play_volitelne": True}
PLAY = Path("play")


# The template's source attribution (migration 0910, _middleware.js): a
# campaign label on the account, used to measure which promotion works.
ZDROJE_PLAY = {"entita": "zdroj příchodu (odkaz z kampaně)",
               "play_typy": ["akce_v_aplikaci"], "play_ucely": ["analytika"], "play_volitelne": True}
ZDROJE_MIGRACE = Path("db") / "migrace" / "0910_zdroje.sql"


def _polozky_play(manifest: dict) -> list[dict]:
    return ([u for u in manifest.get("ukladame") or [] if isinstance(u, dict)] + [HLASENI_PLAY]
            + ([ZDROJE_PLAY] if ZDROJE_MIGRACE.exists() else []))


def _bezpecnost_dat(manifest: dict) -> dict:
    typy: dict[str, dict] = {}
    for polozka in _polozky_play(manifest):
        for klic in polozka.get("play_typy") or []:
            t = typy.setdefault(klic, {"ucely": [], "zdroje": [], "volitelne": True})
            for ucel in polozka.get("play_ucely") or []:
                if ucel not in t["ucely"]:
                    t["ucely"].append(ucel)
            t["zdroje"].append(str(polozka.get("entita")))
            # Required as soon as one place needs it (an account needs its e-mail).
            t["volitelne"] = t["volitelne"] and bool(polozka.get("play_volitelne"))
    poradi = list(PLAY_TYPY)
    return {
        "sbira": bool(typy),
        # Cloudflare, Resend, GitHub process data FOR us — service providers,
        # which Google's form explicitly does not count as sharing.
        "sdili": False,
        "sifrovano_pri_prenosu": True,
        "lze_smazat": True,
        "typy": [{"klic": k, "kategorie": PLAY_TYPY[k][2], "typ": PLAY_TYPY[k][3],
                  "ucely": [PLAY_UCELY[u][1] for u in typy[k]["ucely"]],
                  "volitelne": typy[k]["volitelne"], "zdroje": typy[k]["zdroje"]}
                 for k in sorted(typy, key=poradi.index)],
    }


def _zaznam(manifest: dict) -> dict:
    a = manifest["aplikace"]
    ucty = any(u.get("entita") == "uzivatele" for u in manifest.get("ukladame") or [] if isinstance(u, dict))
    return {
        "jazyk": "cs-CZ",
        "nazev": str(a.get("nazev") or ""),
        "kratky_popis": str(a.get("popis") or ""),
        "dlouhy_popis": str(a.get("dlouhy_popis") or ""),
        "kategorie": str(a.get("kategorie") or ""),
        "kontakt_email": str(a.get("kontakt_email") or manifest.get("kontakt_email") or ""),
        "hlavni_veta": str(a.get("hlavni_veta") or a.get("popis") or ""),
        "snimky": [s for s in a.get("snimky") or [] if isinstance(s, dict)],
        # Paths, not URLs: the product's address is known to the release
        # workflow (custom domain or <repo>.pages.dev), not to the repo.
        "zasady_cesta": "/zasady.html",
        "ucty": ucty,
        "smazani_uctu_cesta": "/zasady.html" if ucty else None,
        "bezpecnost_dat": _bezpecnost_dat(manifest),
    }


# Google's reviewer cannot finish a login by e-mail link; the demo button
# (functions/api/ukazka.js) gives anyone a throwaway account with the demo
# data and the paid features — no credentials to hand over or keep secret.
PRISTUP_KONTROLORA = (
    "No login credentials are needed. On the start screen tap \"Vyzkoušet ukázku\" "
    "(Try the demo): the app creates a temporary account with sample data and all paid "
    "features unlocked; it is deleted after 24 hours. Sign-in for real customers is by a "
    "one-time link sent to their e-mail (no password). Purchases are disabled in the demo "
    "account; the subscription offer and its terms are shown there."
)


def _tahak(manifest: dict, zaznam: dict) -> str:
    """The Data safety form and the rest of "App content", answered in the
    order Play Console asks. Data safety itself the Vydani workflow sends
    over the API (vydani.py bezpecnost_csv); the rest has no API and the
    owner clicks it through once per app."""
    b = zaznam["bezpecnost_dat"]
    kat = zaznam["kategorie"]
    r = [
        "# Google Play — co vyplnit v Play Console",
        "",
        "GENEROVANÝ SOUBOR z data-manifest.json (`python vykresli_aplikaci.py`) — needituj ručně.",
        "Kde je `<adresa>`, doplň adresu produktu (vlastní doména, nebo `<repo>.pages.dev`).",
        "",
        "## 1. Hlavní záznam v obchodě (Main store listing)",
        "",
        "Workflow Vydání ho nahrává sám, jakmile má servisní účet. Ručně jen poprvé, nebo bez něj:",
        "",
        f"- **Název aplikace:** {zaznam['nazev']}",
        f"- **Krátký popis:** {zaznam['kratky_popis']}",
        f"- **Kategorie:** {PLAY_KATEGORIE.get(kat, kat)} (`{kat}`) — v Play Console: Nastavení obchodu",
        f"- **Kontaktní e-mail:** {zaznam['kontakt_email']}",
        "- **Web:** `<adresa>`",
        "- **Úplný popis:**",
        "",
        "```",
        zaznam["dlouhy_popis"],
        "```",
        "",
        "## 2. Zásady ochrany soukromí (Privacy policy)",
        "",
        f"`<adresa>{zaznam['zasady_cesta']}`",
        "",
        "## 3. Bezpečnost údajů (Data safety)",
        "",
        "Vyplní se sama: workflow Vydání ji s každým vydáním posílá Googlu (`bezpecnost_dat.csv`). "
        "Níž je totéž ke kontrole.",
        "",
        f"1. *Shromažďuje nebo sdílí aplikace některý z požadovaných typů uživatelských údajů?* "
        f"**{'Ano' if b['sbira'] else 'Ne'}**",
        "2. *Jsou všechny shromážděné údaje šifrovány při přenosu?* **Ano** (jen HTTPS)",
        "3. *Poskytujete uživatelům způsob, jak požádat o smazání údajů?* **Ano** — "
        + ("v aplikaci Účet → Smazat účet a všechna data; popis na webu." if zaznam["ucty"]
           else f"e-mailem na {zaznam['kontakt_email']}."),
    ]
    if zaznam["ucty"]:
        r.append(f"4. *Metoda vytvoření účtu:* **Uživatelské jméno a další ověření** "
                 f"(e-mail + jednorázový odkaz, bez hesla). Odkaz na smazání účtu: "
                 f"`<adresa>{zaznam['smazani_uctu_cesta']}`")
    r += [
        "",
        "**Sdílení: u žádného typu Ne.** Cloudflare (hosting, databáze), Resend (e-maily) a GitHub "
        "(evidence hlášení, šifrovaně) zpracovávají údaje pro nás — Google je za sdílení nepočítá.",
        "**Zpracování dočasné (ephemeral): Ne** — údaje se ukládají.",
        "",
        "| Kategorie | Typ údajů | Shromažďováno | Povinné? | Účely | Odkud (manifest) |",
        "|---|---|---|---|---|---|",
    ]
    for t in b["typy"]:
        cz = PLAY_TYPY[t["klic"]]
        ucely = ", ".join(f"{PLAY_UCELY[k][0]} ({PLAY_UCELY[k][1]})" for k in PLAY_UCELY
                          if PLAY_UCELY[k][1] in t["ucely"])
        r.append(f"| {cz[0]} ({cz[2]}) | {cz[1]} ({cz[3]}) | Ano | "
                 f"{'volitelné' if t['volitelne'] else 'povinné'} | {ucely} | {', '.join(t['zdroje'])} |")
    r += [
        "",
        "## 4. Obsah aplikace — ostatní prohlášení (App content)",
        "",
        "- **Reklamy:** Ne, aplikace neobsahuje reklamy.",
        "- **Cílová skupina:** 18 let a více.",
        "- **Hodnocení obsahu (dotazník IARC):** kategorie Nástroje / Produktivita; na otázky o násilí, "
        "sexu, vulgaritách, drogách, hazardu a sdílení polohy odpověz Ne. Uživatelé spolu "
        "v aplikaci nekomunikují.",
        "- **Zpravodajská aplikace / vládní aplikace / finanční funkce / zdraví:** Ne.",
    ]
    if zaznam["ucty"]:
        r += [
            "- **Přístup k aplikaci (App access):** Všechny funkce nebo jejich část jsou omezené → "
            "Přidat pokyny. Název: `Ukázka`; uživatelské jméno a heslo nevyplňuj; do „Další informace“ vlož:",
            "",
            "```",
            PRISTUP_KONTROLORA,
            "```",
        ]
    return "\n".join(r) + "\n"

def _barvy(styl: str, produkt: str = "") -> dict[str, str]:
    """Light-theme colours for the app. Design v2: the product's colour
    lives in web/produkt.css (--barva-produktu) and the ground is the
    paper (--barva-papir in styl.css). v1 products had --barva-akcent and
    --barva-pozadi in styl.css — still read as the fallback, so an app
    built before v2 keeps its colours until its next build converts it."""
    def tokeny(text: str) -> dict[str, str]:
        blok = re.search(r":root\s*\{(.*?)\}", text, re.S)
        return dict(re.findall(r"--(barva-[a-z0-9-]+)\s*:\s*(#[0-9a-fA-F]{6})", blok.group(1) if blok else ""))
    s, pr = tokeny(styl), tokeny(produkt)
    akcent = pr.get("barva-produktu") or s.get("barva-produktu") or s.get("barva-akcent") or "#c2410c"
    pozadi = s.get("barva-papir") or s.get("barva-pozadi") or "#f6f4ef"
    return {"akcent": akcent.lower(), "akcent_text": "#ffffff", "pozadi": pozadi.lower()}


def _nacti_barvy() -> dict[str, str]:
    def cti(jmeno: str) -> str:
        cesta = WEB / jmeno
        return cesta.read_text(encoding="utf-8") if cesta.exists() else ""
    return _barvy(cti("styl.css"), cti("produkt.css"))


def _pismeno(aplikace: dict) -> str:
    zdroj = str(aplikace.get("pismeno") or aplikace.get("kratky_nazev") or aplikace.get("nazev") or "S")
    plain = unicodedata.normalize("NFKD", zdroj).encode("ascii", "ignore").decode().upper()
    for ch in plain:
        if ch in _GLYFY:
            return ch
    return "S"


# ── Icons: signed-distance rendering, stdlib only ─────────────────────

# Letters as strokes on a 4 x 6 grid (y down). Drawn as round-capped
# capsules, so they read as a clean monoline mark at any size.
_GLYFY: dict[str, list[list[tuple[float, float]]]] = {
    "A": [[(0, 6), (2, 0), (4, 6)], [(0.7, 4), (3.3, 4)]],
    "B": [[(0, 3), (0, 0), (2.8, 0), (3.8, 0.8), (3.8, 2.2), (2.8, 3), (0, 3)],
          [(0, 3), (0, 6), (3, 6), (4, 5.1), (4, 3.9), (3, 3)]],
    "C": [[(4, 1), (3, 0), (1, 0), (0, 1), (0, 5), (1, 6), (3, 6), (4, 5)]],
    "D": [[(0, 0), (0, 6), (2.4, 6), (4, 4.4), (4, 1.6), (2.4, 0), (0, 0)]],
    "E": [[(4, 0), (0, 0), (0, 6), (4, 6)], [(0, 3), (3, 3)]],
    "F": [[(4, 0), (0, 0), (0, 6)], [(0, 3), (3, 3)]],
    "G": [[(4, 1), (3, 0), (1, 0), (0, 1), (0, 5), (1, 6), (3, 6), (4, 5), (4, 3.4), (2.4, 3.4)]],
    "H": [[(0, 0), (0, 6)], [(4, 0), (4, 6)], [(0, 3), (4, 3)]],
    "I": [[(2, 0), (2, 6)], [(1, 0), (3, 0)], [(1, 6), (3, 6)]],
    "J": [[(4, 0), (4, 5), (3, 6), (1, 6), (0, 5)]],
    "K": [[(0, 0), (0, 6)], [(4, 0), (0, 3.6)], [(1.4, 2.4), (4, 6)]],
    "L": [[(0, 0), (0, 6), (4, 6)]],
    "M": [[(0, 6), (0, 0), (2, 3.2), (4, 0), (4, 6)]],
    "N": [[(0, 6), (0, 0), (4, 6), (4, 0)]],
    "O": [[(1, 0), (3, 0), (4, 1), (4, 5), (3, 6), (1, 6), (0, 5), (0, 1), (1, 0)]],
    "P": [[(0, 6), (0, 0), (3, 0), (4, 1), (4, 2), (3, 3), (0, 3)]],
    "Q": [[(1, 0), (3, 0), (4, 1), (4, 5), (3, 6), (1, 6), (0, 5), (0, 1), (1, 0)], [(2.6, 4.6), (4, 6)]],
    "R": [[(0, 6), (0, 0), (3, 0), (4, 1), (4, 2), (3, 3), (0, 3)], [(2, 3), (4, 6)]],
    "S": [[(4, 1), (3, 0), (1, 0), (0, 1), (0, 2), (1, 3), (3, 3), (4, 4), (4, 5), (3, 6), (1, 6), (0, 5)]],
    "T": [[(0, 0), (4, 0)], [(2, 0), (2, 6)]],
    "U": [[(0, 0), (0, 5), (1, 6), (3, 6), (4, 5), (4, 0)]],
    "V": [[(0, 0), (2, 6), (4, 0)]],
    "W": [[(0, 0), (1, 6), (2, 3), (3, 6), (4, 0)]],
    "X": [[(0, 0), (4, 6)], [(4, 0), (0, 6)]],
    "Y": [[(0, 0), (2, 3), (4, 0)], [(2, 3), (2, 6)]],
    "Z": [[(0, 0), (4, 0), (0, 6), (4, 6)]],
}


def _hex(barva: str) -> tuple[int, int, int]:
    return int(barva[1:3], 16), int(barva[3:5], 16), int(barva[5:7], 16)


def _vzdalenost_useck(px: float, py: float, useky: list[tuple[float, float, float, float]]) -> float:
    nejblize = 1e9
    for ax, ay, bx, by in useky:
        dx, dy = bx - ax, by - ay
        delka2 = dx * dx + dy * dy
        t = 0.0 if delka2 == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / delka2))
        ex, ey = px - (ax + t * dx), py - (ay + t * dy)
        d = ex * ex + ey * ey
        if d < nejblize:
            nejblize = d
    return math.sqrt(nejblize)


# A shape of the symbol, in grid units: ("usek", ax, ay, bx, by, detail)
# or ("kruh", cx, cy, r, 0, detail). Letters use round caps ("kulaty").
Tvar = tuple


def _cislo(text: str) -> float:
    return float(text)


def _body_cesty(d: str) -> tuple[list[list[tuple[float, float]]], str | None]:
    """Straight-line paths only: M L H V Z, absolute or relative. Curves
    are refused — a symbol is drawn with a ruler, and a pure-Python
    renderer stays exact and small that way."""
    tokeny = re.findall(r"[A-Za-z]|-?(?:\d+\.?\d*|\.\d+)(?:[eE]-?\d+)?", d)
    tahy: list[list[tuple[float, float]]] = []
    x = y = sx = sy = 0.0
    prikaz = None
    i = 0
    while i < len(tokeny):
        t = tokeny[i]
        if t.isalpha():
            if t not in "MmLlHhVvZz":
                return [], f"příkaz „{t}“ (oblouky a křivky nejsou dovolené, jen M L H V Z)"
            prikaz = t
            i += 1
            if t in "Zz":
                if tahy and tahy[-1]:
                    tahy[-1].append((sx, sy))
                x, y = sx, sy
            continue
        if prikaz is None:
            return [], "cesta musí začínat příkazem M"
        try:
            if prikaz in "Mm":
                nx, ny = _cislo(tokeny[i]), _cislo(tokeny[i + 1])
                i += 2
                x, y = (x + nx, y + ny) if prikaz == "m" else (nx, ny)
                sx, sy = x, y
                tahy.append([(x, y)])
                prikaz = "l" if prikaz == "m" else "L"   # implicit lineto after the first pair
                continue
            if prikaz in "Ll":
                nx, ny = _cislo(tokeny[i]), _cislo(tokeny[i + 1])
                i += 2
                x, y = (x + nx, y + ny) if prikaz == "l" else (nx, ny)
            elif prikaz in "Hh":
                n = _cislo(tokeny[i])
                i += 1
                x = x + n if prikaz == "h" else n
            elif prikaz in "Vv":
                n = _cislo(tokeny[i])
                i += 1
                y = y + n if prikaz == "v" else n
            else:
                return [], f"za „{prikaz}“ nečekám čísla"
        except (IndexError, ValueError):
            return [], "neúplná souřadnice"
        if not tahy:
            return [], "cesta musí začínat příkazem M"
        tahy[-1].append((x, y))
    return tahy, None


def nacti_piktogram(text: str) -> tuple[list[Tvar], list[str]]:
    """(shapes, problems). The file is the builder's drawing; the rules
    are strict so every product's symbol reads as one family."""
    import xml.etree.ElementTree as ET

    if "<!DOCTYPE" in text or "<!ENTITY" in text:
        return [], ["play/piktogram.svg: DOCTYPE ani ENTITY nejsou dovolené."]
    try:
        koren = ET.fromstring(text)
    except ET.ParseError as e:
        return [], [f"play/piktogram.svg není platné SVG: {e}"]
    jmeno = lambda el: el.tag.rsplit("}", 1)[-1]
    if jmeno(koren) != "svg" or re.sub(r"\s+", " ", koren.get("viewBox", "").strip()) != "0 0 24 24":
        return [], ["play/piktogram.svg: kořen musí být <svg viewBox=\"0 0 24 24\">."]
    chyby: list[str] = []
    tvary: list[Tvar] = []

    def projdi(el, detail: bool) -> None:
        for dite in el:
            tag = jmeno(dite)
            povolene = _PIKTOGRAM_ATRIBUTY.get(tag)
            if povolene is None or tag == "svg":
                chyby.append(f"play/piktogram.svg: prvek <{tag}> není dovolený (jen g, path, line, polyline, rect, circle).")
                continue
            navic = sorted(a.rsplit("}", 1)[-1] for a in dite.attrib if a.rsplit("}", 1)[-1] not in povolene)
            if navic:
                chyby.append(f"play/piktogram.svg: <{tag}> s atributy {navic} — barvu, tloušťku a styl dává generátor.")
                continue
            trida = dite.get("class")
            if trida not in (None, "detail"):
                chyby.append(f"play/piktogram.svg: class smí být jen „detail“ (je „{trida}“).")
                continue
            d2 = detail or trida == "detail"
            try:
                if tag == "g":
                    projdi(dite, d2)
                elif tag == "line":
                    tvary.append(("usek", _cislo(dite.get("x1", "0")), _cislo(dite.get("y1", "0")),
                                  _cislo(dite.get("x2", "0")), _cislo(dite.get("y2", "0")), d2))
                elif tag == "rect":
                    x, y = _cislo(dite.get("x", "0")), _cislo(dite.get("y", "0"))
                    w, h = _cislo(dite.get("width", "0")), _cislo(dite.get("height", "0"))
                    rohy = [(x, y), (x + w, y), (x + w, y + h), (x, y + h), (x, y)]
                    tvary.extend([("usek", *a, *b, d2) for a, b in zip(rohy, rohy[1:])])
                elif tag == "circle":
                    tvary.append(("kruh", _cislo(dite.get("cx", "0")), _cislo(dite.get("cy", "0")),
                                  _cislo(dite.get("r", "0")), 0.0, d2))
                elif tag == "polyline":
                    cisla = [_cislo(c) for c in re.findall(r"-?(?:\d+\.?\d*|\.\d+)", dite.get("points", ""))]
                    body = list(zip(cisla[0::2], cisla[1::2]))
                    tvary.extend([("usek", *a, *b, d2) for a, b in zip(body, body[1:])])
                elif tag == "path":
                    tahy, chyba = _body_cesty(dite.get("d", ""))
                    if chyba:
                        chyby.append(f"play/piktogram.svg: path — {chyba}.")
                    for tah in tahy:
                        tvary.extend([("usek", *a, *b, d2) for a, b in zip(tah, tah[1:])])
            except ValueError:
                chyby.append(f"play/piktogram.svg: <{tag}> má nečíselnou souřadnici.")

    projdi(koren, False)
    if not tvary and not chyby:
        chyby.append("play/piktogram.svg je prázdný — symbol produktu chybí.")
    if len(tvary) > PIKTOGRAM_TVARU:
        chyby.append(f"play/piktogram.svg: {len(tvary)} čar, nejvýš {PIKTOGRAM_TVARU} — symbol má být jednoduchý.")
    if not any(not t[5] for t in tvary):
        chyby.append("play/piktogram.svg: všechno je „detail“ — hlavní tvar musí být plnou čarou.")
    # Inside the grid, and inside the circle Android may crop to.
    for t in tvary:
        body = [(t[1], t[2]), (t[3], t[4])] if t[0] == "usek" else [(t[1], t[2])]
        presah = t[3] if t[0] == "kruh" else 0.0
        for bx, by in body:
            if not (0 <= bx <= 24 and 0 <= by <= 24):
                chyby.append(f"play/piktogram.svg: bod ({bx:g}, {by:g}) je mimo mřížku 24×24.")
                break
            if math.hypot(bx - 12, by - 12) + presah + 0.8 > BEZPECNY_POLOMER:
                chyby.append(f"play/piktogram.svg: bod ({bx:g}, {by:g}) je dál než {BEZPECNY_POLOMER:g} od středu "
                             "— Android by ho v kulaté ikoně uřízl.")
                break
    return tvary, chyby[:6]


def _tvary_pismena(pismeno: str) -> list[Tvar]:
    """The fallback: one letter, 13 grid units tall, centred, round caps."""
    k = 13.0 / 6.0
    x0, y0 = 12.0 - 2.0 * k, 12.0 - 3.0 * k
    tvary = []
    for tah in _GLYFY[pismeno]:
        for (ax, ay), (bx, by) in zip(tah, tah[1:]):
            tvary.append(("kulaty", x0 + ax * k, y0 + ay * k, x0 + bx * k, y0 + by * k, False))
    return tvary


def _odstiny(akcent: str) -> dict[str, tuple[int, int, int]]:
    """The gradient and shadow from the product colour alone — every app
    gets the same treatment without anyone picking more colours."""
    r, g, b = (c / 255.0 for c in _hex(akcent))
    h, l, s = colorsys.rgb_to_hls(r, g, b)

    def hls(lightness: float) -> tuple[int, int, int]:
        rr, gg, bb = colorsys.hls_to_rgb(h, max(0.0, min(1.0, lightness)), s)
        return round(rr * 255), round(gg * 255), round(bb * 255)

    return {"svetla": hls(l + 0.09), "zaklad": _hex(akcent), "tmava": hls(l - 0.095), "stin": hls(l * 0.3)}


def _sd(px: float, py: float, tvar: Tvar, polomer: float) -> float:
    """Signed distance from a pixel to one stroked shape (pixel units)."""
    if tvar[0] == "kruh":
        return abs(math.hypot(px - tvar[1], py - tvar[2]) - tvar[3]) - polomer
    ax, ay, bx, by = tvar[1], tvar[2], tvar[3], tvar[4]
    dx, dy = bx - ax, by - ay
    delka = math.hypot(dx, dy)
    if tvar[0] == "kulaty" or delka == 0:
        t = 0.0 if delka == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (delka * delka)))
        return math.hypot(px - (ax + t * dx), py - (ay + t * dy)) - polomer
    # Square caps: the stroke is a rectangle (length + 2r) × 2r along the
    # segment, so rectangles drawn from four lines meet in clean corners.
    ux, uy = dx / delka, dy / delka
    u = (px - ax) * ux + (py - ay) * uy - delka / 2.0
    v = -(px - ax) * uy + (py - ay) * ux
    qx, qy = abs(u) - (delka / 2.0 + polomer), abs(v) - polomer
    return math.hypot(max(qx, 0.0), max(qy, 0.0)) + min(max(qx, qy), 0.0)


def vykresli_ikonu(velikost: int, tvary: list[Tvar], barvy: dict[str, str], maskovatelna: bool) -> bytes:
    """Raw RGBA rows (with PNG filter byte 0) of one icon.

    Layers, bottom up: a diagonal gradient of the product colour with a
    soft light in the top-left corner; a faint drawing grid (every 2 grid
    units, white at 7 %); a soft shadow under the main lines; the main
    lines in paper colour; `detail` lines finer and at 62 %. Ordinary
    icon: rounded square. Maskable: full bleed, symbol smaller. Every edge
    is anti-aliased from signed distances — exact, deterministic (CI
    compares pixels) and fast enough in pure Python."""
    s = float(velikost)
    o = _odstiny(barvy["akcent"])
    papir = _hex(barvy["pozadi"])
    k = s * (PIKTOGRAM_MERITKO_MASKA if maskovatelna else PIKTOGRAM_MERITKO) / 24.0
    posun = (s - 24.0 * k) / 2.0
    hlavni = [(t[0], posun + t[1] * k, posun + t[2] * k,
               (t[3] * k) if t[0] == "kruh" else posun + t[3] * k,
               0.0 if t[0] == "kruh" else posun + t[4] * k, t[5]) for t in tvary]
    tah_hlavni, tah_detail = 0.7 * k, 0.3 * k
    stin_dy, stin_sigma = 0.6 * k, 0.6 * k
    plne = [t for t in hlavni if not t[5]]
    detaily = [t for t in hlavni if t[5]]
    okraj = tah_hlavni + stin_dy + 3 * stin_sigma + 2
    xs = [c for t in hlavni for c in ((t[1] - t[3], t[1] + t[3]) if t[0] == "kruh" else (t[1], t[3]))]
    ys = [c for t in hlavni for c in ((t[2] - t[3], t[2] + t[3]) if t[0] == "kruh" else (t[2], t[4]))]
    bx0, bx1 = min(xs) - okraj, max(xs) + okraj
    by0, by1 = min(ys) - okraj, max(ys) + okraj
    krok = s / 12.0
    mrizka_pul = s * 0.06 / 24.0 / 2.0
    zaobleni = s * 0.22
    polovina = s / 2.0

    def mix(a, b, t):
        return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t)

    radky = bytearray()
    for y in range(velikost):
        radky.append(0)
        py = y + 0.5
        for x in range(velikost):
            px = x + 0.5
            # Gradient: light top-left → base at 55 % → dark bottom-right.
            t = (px + py) / (2.0 * s)
            barva = mix(o["svetla"], o["zaklad"], t / 0.55) if t < 0.55 else mix(o["zaklad"], o["tmava"], (t - 0.55) / 0.45)
            svetlo = 0.16 * max(0.0, 1.0 - math.hypot(px / s - 0.22, py / s - 0.12) / 0.75)
            barva = mix(barva, (255, 255, 255), svetlo)
            # Drawing grid.
            gx = min(px % krok, krok - px % krok)
            gy = min(py % krok, krok - py % krok)
            mrizka = max(0.0, min(1.0, 0.5 - (min(gx, gy) - mrizka_pul)))
            if mrizka > 0:
                barva = mix(barva, (255, 255, 255), 0.07 * mrizka)
            if bx0 <= px <= bx1 and by0 <= py <= by1:
                if plne:
                    d_stin = min(_sd(px, py - stin_dy, t_, tah_hlavni) for t_ in plne)
                    stin = 0.45 * max(0.0, min(1.0, 1.0 - d_stin / (2.0 * stin_sigma)))
                    if stin > 0:
                        barva = mix(barva, o["stin"], stin)
                if detaily:
                    d = min(_sd(px, py, t_, tah_detail) for t_ in detaily)
                    pokryti = max(0.0, min(1.0, 0.5 - d))
                    if pokryti > 0:
                        barva = mix(barva, papir, 0.62 * pokryti)
                if plne:
                    d = min(_sd(px, py, t_, tah_hlavni) for t_ in plne)
                    pokryti = max(0.0, min(1.0, 0.5 - d))
                    if pokryti > 0:
                        barva = mix(barva, papir, pokryti)
            if maskovatelna:
                alfa = 1.0
            else:
                qx = abs(px - polovina) - (polovina - zaobleni)
                qy = abs(py - polovina) - (polovina - zaobleni)
                vne = math.hypot(max(qx, 0.0), max(qy, 0.0)) + min(max(qx, qy), 0.0) - zaobleni
                alfa = max(0.0, min(1.0, 0.5 - vne))
            radky += bytes((round(barva[0]), round(barva[1]), round(barva[2]), round(alfa * 255)))
    return bytes(radky)


def png(velikost: int, radky: bytes) -> bytes:
    def blok(typ: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + typ + data + struct.pack(">I", zlib.crc32(typ + data) & 0xFFFFFFFF)
    hlavicka = struct.pack(">IIBBBBB", velikost, velikost, 8, 6, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + blok(b"IHDR", hlavicka)
            + blok(b"IDAT", zlib.compress(radky, 9)) + blok(b"IEND", b""))


def pixely_png(data: bytes) -> tuple[int, int, bytes] | None:
    """(width, height, raw rows) of a PNG we wrote — for comparing by pixels."""
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        return None
    pos, sirka, vyska, idat = 8, 0, 0, b""
    while pos < len(data):
        delka = struct.unpack(">I", data[pos:pos + 4])[0]
        typ = data[pos + 4:pos + 8]
        obsah = data[pos + 8:pos + 8 + delka]
        if typ == b"IHDR":
            sirka, vyska = struct.unpack(">II", obsah[:8])
        elif typ == b"IDAT":
            idat += obsah
        pos += 12 + delka
    try:
        return sirka, vyska, zlib.decompress(idat)
    except zlib.error:
        return None


# ── Outputs ───────────────────────────────────────────────────────────

def _texty(manifest: dict, barvy: dict[str, str]) -> dict[Path, str]:
    a = manifest["aplikace"]
    nazev = str(a.get("nazev") or manifest.get("produkt") or "Aplikace")
    web_manifest = {
        "name": nazev,
        "short_name": str(a.get("kratky_nazev") or nazev)[:12],
        "description": str(a.get("popis") or ""),
        "lang": "cs",
        "dir": "ltr",
        "start_url": "/",
        "scope": "/",
        "display": "standalone",
        "orientation": "portrait",
        "background_color": barvy["pozadi"],
        "theme_color": barvy["akcent"],
        "icons": [
            {"src": "/ikona-192.png", "sizes": "192x192", "type": "image/png", "purpose": "any"},
            {"src": "/ikona-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any"},
            {"src": "/ikona-maskable-512.png", "sizes": "512x512", "type": "image/png", "purpose": "maskable"},
        ],
        "related_applications": [{
            "platform": "play", "id": a["balicek"],
            "url": f"https://play.google.com/store/apps/details?id={a['balicek']}",
        }],
        "prefer_related_applications": False,
    }
    odkazy = [{
        "relation": ["delegate_permission/common.handle_all_urls"],
        "target": {"namespace": "android_app", "package_name": a["balicek"],
                   "sha256_cert_fingerprints": [str(o).upper() for o in a.get("otisky") or []]},
    }]
    zaznam = _zaznam(manifest)
    return {
        WEB / "manifest.webmanifest": json.dumps(web_manifest, ensure_ascii=False, indent=2) + "\n",
        WEB / ".well-known" / "assetlinks.json": json.dumps(odkazy, indent=2) + "\n",
        WEB / "sw.js": SW,
        WEB / "offline.html": OFFLINE.format(nazev=nazev, barva=barvy["akcent"]),
        PLAY / "zaznam.json": json.dumps(zaznam, ensure_ascii=False, indent=2) + "\n",
        PLAY / "BEZPECNOST_DAT.md": _tahak(manifest, zaznam),
        **_ukazka_web(),
    }


def _ukazka_web() -> dict[Path, str]:
    if not UKAZKA.exists():
        return {}
    try:
        data = json.loads(UKAZKA.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}  # _chyby_ukazky reports it
    return {UKAZKA_WEB: json.dumps(data, ensure_ascii=False, indent=1) + "\n"}


def _tvary_ikony(manifest: dict) -> list[Tvar]:
    if PIKTOGRAM.exists():
        tvary, chyby = nacti_piktogram(PIKTOGRAM.read_text(encoding="utf-8"))
        if not chyby:
            return tvary
    return _tvary_pismena(_pismeno(manifest["aplikace"]))


def _ikony(manifest: dict, barvy: dict[str, str]) -> dict[Path, tuple[int, bytes]]:
    tvary = _tvary_ikony(manifest)
    return {WEB / jmeno: (velikost, vykresli_ikonu(velikost, tvary, barvy, maskovatelna))
            for jmeno, velikost, maskovatelna in IKONY}


def _obrazovky_webu() -> set[str]:
    """Ids of the app's screens (.obrazovka[id]) across web/*.html."""
    ids: set[str] = set()
    for stranka in WEB.glob("*.html") if WEB.is_dir() else []:
        for tag in re.findall(r"<[a-zA-Z][^>]*\bclass=\"[^\"]*\bobrazovka\b[^\"]*\"[^>]*>",
                              stranka.read_text(encoding="utf-8", errors="replace")):
            m = re.search(r"\bid=\"([^\"]+)\"", tag)
            if m:
                ids.add(m.group(1))
    return ids


def _chyby_obchodu(manifest: dict) -> list[str]:
    """The store listing's inputs: symbol, screenshots script, the feature
    graphic's sentence, demo data, release notes. Required with the app
    module — a listing of 'Nejste přihlášeni' screens and a letter for an
    icon is what this replaced."""
    a = manifest["aplikace"]
    chyby: list[str] = []
    if not PIKTOGRAM.exists():
        chyby.append("play/piktogram.svg chybí — symbol produktu pro ikonu (čáry na mřížce 24×24, viz DESIGN.md).")
    else:
        chyby += nacti_piktogram(PIKTOGRAM.read_text(encoding="utf-8"))[1]
    veta = str(a.get("hlavni_veta") or "").strip()
    if not HLAVNI_VETA_DELKA[0] <= len(veta) <= HLAVNI_VETA_DELKA[1]:
        chyby.append(f"aplikace.hlavni_veta musí mít {HLAVNI_VETA_DELKA[0]}–{HLAVNI_VETA_DELKA[1]} znaků "
                     "(věta produktu na grafice v obchodě).")
    snimky = a.get("snimky")
    if not isinstance(snimky, list) or not SNIMKY_POCET[0] <= len(snimky) <= SNIMKY_POCET[1]:
        chyby.append(f"aplikace.snimky musí být seznam {SNIMKY_POCET[0]}–{SNIMKY_POCET[1]} snímků "
                     "({obrazovka, stitek, titulek, kliky?, posun?, tablet?}).")
        snimky = []
    obrazovky = _obrazovky_webu()
    for i, s in enumerate(snimky, 1):
        if not isinstance(s, dict):
            chyby.append(f"aplikace.snimky[{i}] musí být objekt.")
            continue
        # A one-page site has no screens: its shots differ by `posun`.
        if obrazovky and s.get("obrazovka") not in obrazovky:
            chyby.append(f"aplikace.snimky[{i}].obrazovka „{s.get('obrazovka')}“ není id žádné .obrazovka ve web/ "
                         f"(jsou: {', '.join(sorted(obrazovky))}).")
        posun = s.get("posun", 0)
        if not isinstance(posun, int) or not 0 <= posun <= 20000:
            chyby.append(f"aplikace.snimky[{i}].posun je odsazení stránky v px (0–20000).")
        titulek = str(s.get("titulek") or "").strip()
        if not TITULEK_DELKA[0] <= len(titulek) <= TITULEK_DELKA[1]:
            chyby.append(f"aplikace.snimky[{i}].titulek musí mít {TITULEK_DELKA[0]}–{TITULEK_DELKA[1]} znaků.")
        if not str(s.get("stitek") or "").strip() or len(str(s.get("stitek"))) > STITEK_DELKA:
            chyby.append(f"aplikace.snimky[{i}].stitek musí mít 1–{STITEK_DELKA} znaků.")
        kliky = s.get("kliky", [])
        if not isinstance(kliky, list) or len(kliky) > 3 or not all(isinstance(k, str) and k for k in kliky):
            chyby.append(f"aplikace.snimky[{i}].kliky je seznam nejvýš 3 CSS selektorů.")
    if snimky and not any(isinstance(s, dict) and s.get("tablet") for s in snimky):
        chyby.append("aplikace.snimky: aspoň jeden snímek označ „tablet“: true — z něj vznikne snímek tabletu.")
    if CO_JE_NOVEHO.exists():
        text = CO_JE_NOVEHO.read_text(encoding="utf-8").strip()
        if not text or len(text) > CO_JE_NOVEHO_DELKA:
            chyby.append(f"play/co_je_noveho.txt musí mít 1–{CO_JE_NOVEHO_DELKA} znaků (limit Google Play).")
    if (Path("db")).exists():
        chyby += _chyby_ukazky()
    return chyby


def _chyby_ukazky() -> list[str]:
    """play/ukazka.json: the demo account's data, created through the real
    API before the store screenshots are taken. Invented, never a real
    person — e-mail addresses only at example.cz/example.com."""
    if not UKAZKA.exists():
        return ["play/ukazka.json chybí — ukázková data pro snímky do obchodu (kroky jako v uat/scenare.json)."]
    try:
        data = json.loads(UKAZKA.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        return [f"play/ukazka.json nejde přečíst: {e}"]
    kroky = data.get("kroky") if isinstance(data, dict) else None
    if not isinstance(kroky, list) or not 1 <= len(kroky) <= UKAZKA_KROKU:
        return [f"play/ukazka.json: „kroky“ musí být seznam 1–{UKAZKA_KROKU} požadavků."]
    chyby = []
    for j, k in enumerate(kroky, 1):
        if not isinstance(k, dict) or not re.match(r"^(GET|POST|PUT|PATCH|DELETE) /api/", str(k.get("pozadavek", ""))):
            chyby.append(f"play/ukazka.json krok {j}: „pozadavek“ musí být „POST /api/…“ (jen API produktu).")
    for email in re.findall(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+", json.dumps(data, ensure_ascii=False)):
        if not email.lower().endswith(("@example.cz", "@example.com")):
            chyby.append(f"play/ukazka.json: e-mail „{email}“ — ukázková data jen s adresami @example.cz.")
            break
    return chyby[:6]


# Google Play Payments policy: inside the app from Play, a digital
# subscription is sold only through Play Billing and nothing may lead to
# another way to pay. The invoice order stays on the web; the attribute on
# <html> lets styl.css hide [data-objednavka] until web/play.js has proved
# the page runs in a browser — a mistake hides it, never shows it.
HTML_APLIKACE = "data-aplikace"
_HTML_TAG = re.compile(r"<html\b(?![^>]*\bdata-aplikace\b)", re.IGNORECASE)
OBJEDNAVKA_API = Path("functions") / "api" / "objednavka.js"
PLAY_API = Path("functions") / "api" / "play.js"
PRIHLASENI_API = Path("functions") / "api" / "prihlaseni.js"
UKAZKA_API = Path("functions") / "api" / "ukazka.js"
PLAY_DOMENA = "androidpublisher.googleapis.com"


def _chyby_play(manifest: dict) -> list[str]:
    """What a product inside Google Play must have so that Google accepts
    it and the customer can pay: no invoice order inside the app, Play
    Billing where it sells a subscription, a way in for the reviewer.
    The module files themselves come from SimteGen (moduly/play) with the
    build; this proves the product wired them in."""
    index = WEB / "index.html"
    text = index.read_text(encoding="utf-8") if index.exists() else ""
    chyby: list[str] = []
    if OBJEDNAVKA_API.exists():
        if "data-objednavka" not in text:
            chyby.append("web/index.html: fakturační objednávku (kartu s tlačítkem „Objednávka zavazující "
                         "k platbě“) označ atributem data-objednavka — v aplikaci z Google Play musí "
                         "zmizet (Payments policy), jinak Google aplikaci stáhne.")
        if not PLAY_API.exists():
            chyby.append("functions/api/play.js chybí — produkt s předplatným a aplikací prodává v aplikaci "
                         "přes Google Play (soubory doplní stavba ze SimteGenu).")
    if PLAY_API.exists():
        if "data-predplatne-play" not in text:
            chyby.append("web/index.html: do karty předplatného patří prázdný <div data-predplatne-play></div> "
                         "— tam play.js v aplikaci ukáže nákup přes Google Play.")
        if "play_nakupy" not in {u.get("entita") for u in manifest.get("ukladame") or [] if isinstance(u, dict)}:
            chyby.append("data-manifest.json: chybí entita play_nakupy (nákupy předplatného v Google Play).")
        if not any(s.get("domena") == PLAY_DOMENA for s in manifest.get("sluzby_treti_strany") or []
                   if isinstance(s, dict)):
            chyby.append(f"data-manifest.json: chybí služba Google Play (domena {PLAY_DOMENA}) — ověřuje nákupy.")
        if not any(c.get("nazev") == "aplikace" for c in manifest.get("cookies") or [] if isinstance(c, dict)):
            chyby.append("data-manifest.json: chybí cookie „aplikace“ (technická — pozná aplikaci z Google Play).")
    if PRIHLASENI_API.exists() and UKAZKA.exists():
        if "data-ukazka" not in text:
            chyby.append("web/index.html: na přihlašovací obrazovku patří tlačítko s atributem data-ukazka "
                         "(„Vyzkoušet ukázku“) — kontrolor Googlu se e-mailovým odkazem nepřihlásí.")
        if not UKAZKA_API.exists():
            chyby.append("functions/api/ukazka.js chybí (soubory doplní stavba ze SimteGenu).")
    return chyby


def _index_s_odkazy(text: str) -> str:
    text = _HTML_TAG.sub(f"<html {HTML_APLIKACE}", text, count=1)
    if ODKAZ_MANIFESTU not in text and "</head>" in text:
        text = text.replace("</head>", f"  {ZNACKA}\n  {ODKAZ_MANIFESTU}\n</head>", 1)
    if REGISTRACE not in text and "</body>" in text:
        text = text.replace("</body>", f"  {REGISTRACE}\n</body>", 1)
    return text


def _chyby_konfigurace(manifest: dict) -> list[str]:
    a = manifest.get("aplikace")
    if not isinstance(a, dict):
        return ["data-manifest.json: `aplikace` musí být objekt."]
    chyby = []
    if not BALICEK_VZOR.match(str(a.get("balicek") or "")):
        chyby.append("aplikace.balicek chybí nebo není platné jméno balíčku (např. cz.simtegen.evidence_pneu).")
    if not str(a.get("nazev") or "").strip() or len(str(a.get("nazev"))) > 30:
        chyby.append("aplikace.nazev musí mít 1–30 znaků (limit Google Play).")
    if len(str(a.get("kratky_nazev") or "")) > 12:
        chyby.append("aplikace.kratky_nazev smí mít nejvýš 12 znaků (vejde se pod ikonu).")
    if len(str(a.get("popis") or "")) > 80:
        chyby.append("aplikace.popis smí mít nejvýš 80 znaků (krátký popis v Google Play).")
    for otisk in a.get("otisky") or []:
        if not OTISK_VZOR.match(str(otisk).upper()):
            chyby.append(f"aplikace.otisky: „{str(otisk)[:40]}“ není SHA-256 otisk (32 párů hex oddělených dvojtečkou).")
    dlouhy = str(a.get("dlouhy_popis") or "").strip()
    if not 80 <= len(dlouhy) <= 4000:
        chyby.append("aplikace.dlouhy_popis musí mít 80–4000 znaků (úplný popis v Google Play: co aplikace "
                     "dělá, pro koho, co stojí).")
    if a.get("kategorie") not in PLAY_KATEGORIE:
        chyby.append(f"aplikace.kategorie musí být jedna z: {', '.join(PLAY_KATEGORIE)}.")
    if not (a.get("kontakt_email") or manifest.get("kontakt_email")):
        chyby.append("aplikace.kontakt_email (nebo kontakt_email v manifestu) chybí — Google Play ho vyžaduje.")
    # Every stored entity says what it is for Google; an unannotated one would
    # silently vanish from the Data safety form — a false claim to Google.
    for u in manifest.get("ukladame") or []:
        if not isinstance(u, dict):
            continue
        jmeno = u.get("entita", "?")
        if not isinstance(u.get("play_typy"), list):
            chyby.append(f"ukladame „{jmeno}“: chybí play_typy (seznam z {', '.join(PLAY_TYPY)}; "
                         "[] jen když nejde o údaje uživatele, např. otisky tokenů).")
            continue
        spatne = [t for t in u["play_typy"] if t not in PLAY_TYPY]
        if spatne:
            chyby.append(f"ukladame „{jmeno}“: neznámé play_typy {spatne}.")
        ucely = u.get("play_ucely") or []
        if u["play_typy"] and (not ucely or [x for x in ucely if x not in PLAY_UCELY]):
            chyby.append(f"ukladame „{jmeno}“: play_ucely musí být neprázdný seznam z {', '.join(PLAY_UCELY)}.")
    return chyby


def _zapis_ukazku() -> list[str]:
    zapsano = []
    for cesta, text in _ukazka_web().items():
        cesta.parent.mkdir(parents=True, exist_ok=True)
        cesta.write_text(text, encoding="utf-8", newline="\n")
        zapsano.append(str(cesta))
    return zapsano


def vykresli(manifest: dict) -> list[str]:
    """Write every output. Returns the paths written (empty = nothing to do)."""
    if "aplikace" not in manifest:
        return _zapis_ukazku()
    chyby = _chyby_konfigurace(manifest)
    if chyby:
        raise SystemExit("Modul aplikace: " + " ".join(chyby))
    barvy = _nacti_barvy()
    zapsano = []
    for cesta, text in _texty(manifest, barvy).items():
        cesta.parent.mkdir(parents=True, exist_ok=True)
        cesta.write_text(text, encoding="utf-8", newline="\n")
        zapsano.append(str(cesta))
    for cesta, (velikost, radky) in _ikony(manifest, barvy).items():
        cesta.write_bytes(png(velikost, radky))
        zapsano.append(str(cesta))
    # The listing's inputs do not stop the app files — CI reports them.
    for chyba in _chyby_obchodu(manifest):
        print("Pozor (záznam v obchodě):", chyba)
    for chyba in _chyby_play(manifest):
        print("Pozor (Google Play):", chyba)
    index = WEB / "index.html"
    if index.exists():
        puvodni = index.read_text(encoding="utf-8")
        novy = _index_s_odkazy(puvodni)
        if novy != puvodni:
            index.write_text(novy, encoding="utf-8", newline="\n")
            zapsano.append(str(index))
    return zapsano


def generovane_soubory(manifest: dict) -> set[Path]:
    """Files this module owns — the checkers skip them in their network and
    storage scans (the worker must fetch and cache), because zkontroluj()
    already proves they are exactly the generated ones."""
    if "aplikace" not in manifest:
        return set()
    return {WEB / "sw.js", WEB / "offline.html"}


def _chyby_ukazky_webu() -> list[str]:
    chyby = []
    for cesta, text in _ukazka_web().items():
        if not cesta.exists() or cesta.read_text(encoding="utf-8").replace("\r\n", "\n") != text:
            chyby.append(f"{cesta} neodpovídá play/ukazka.json — spusť `python vykresli_aplikaci.py` (ručně se needituje).")
    return chyby


def zkontroluj(manifest: dict) -> list[str]:
    """CI: the configuration is valid and every output equals the generator."""
    if "aplikace" not in manifest:
        # Sample data without the app (empty state): valid and published.
        return (_chyby_ukazky() + _chyby_ukazky_webu()) if UKAZKA.exists() else []
    chyby = _chyby_konfigurace(manifest)
    if chyby:
        return chyby
    chyby = _chyby_obchodu(manifest) + _chyby_play(manifest)
    barvy = _nacti_barvy()
    for cesta, text in _texty(manifest, barvy).items():
        if not cesta.exists() or cesta.read_text(encoding="utf-8").replace("\r\n", "\n") != text:
            chyby.append(f"{cesta} neodpovídá manifestu — spusť `python vykresli_aplikaci.py` (ručně se needituje).")
    for cesta, (velikost, radky) in _ikony(manifest, barvy).items():
        pixely = pixely_png(cesta.read_bytes()) if cesta.exists() else None
        if pixely != (velikost, velikost, radky):
            chyby.append(f"{cesta} neodpovídá návrhovému systému — spusť `python vykresli_aplikaci.py`.")
    index = WEB / "index.html"
    if index.exists():
        text = index.read_text(encoding="utf-8")
        if ODKAZ_MANIFESTU not in text or REGISTRACE not in text or _HTML_TAG.search(text):
            chyby.append("web/index.html nemá odkaz na manifest aplikace nebo registraci service workeru — "
                         "spusť `python vykresli_aplikaci.py`.")
    return chyby


def main() -> int:
    if not MANIFEST.exists():
        print("CHYBA: chybí data-manifest.json.")
        return 1
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    zapsano = vykresli(manifest)
    if "aplikace" not in manifest:
        print("Modul aplikace není zapnutý (v manifestu chybí sekce `aplikace`)"
              + (" — zveřejněna jen ukázková data: " + ", ".join(zapsano) if zapsano else " — nic k vykreslení."))
        return 0
    print("Aplikace vykreslena:", ", ".join(zapsano))
    if not manifest["aplikace"].get("otisky"):
        print("Pozor: aplikace.otisky je prázdné — aplikace poběží s adresním řádkem, dokud tam "
              "nebude SHA-256 otisk podpisového klíče z Play Console (Integrita aplikace).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
