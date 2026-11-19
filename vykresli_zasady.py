"""Render the legal pack from the manifest: privacy policy, terms of service,
data processing agreement, withdrawal form, record of processing, incident
procedure.

The clauses live HERE, as frozen templates, and the manifest only fills the
slots. That is the whole legal design of the template: the builder edits
data-manifest.json, never the legal text, so a product can only ever say
what its manifest declares. kontrola_manifestu.py regenerates every file and
fails CI on any difference — a hand-edited document is treated as drift,
not as an improvement.

Text status: version 2.0 = the 19. 9. 2026 legal review (see the SimteGen
plan memory): consumer withdrawal (§ 1829, § 1837 l), B2B/B2C liability
split, Data Act portability, art. 21 objection, transfers outside the EU,
art. 28 (4) sub-processors, art. 30 (2) processor record, controller /
processor roles in the incident procedure. Empty identity slots render as
red "(doplnit …)" — a document with them is not publishable, and the
reviewer should see that at a glance.

Deterministic on purpose (no timestamps, stable ordering): the CI
comparison is a plain string equality. Stdlib only.
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

MANIFEST = Path("data-manifest.json")
WEB = Path("web")
ZASADY = WEB / "zasady.html"
PODMINKY = WEB / "podminky.html"
DPA = WEB / "zpracovatelska-smlouva.html"
ODSTOUPENI = WEB / "odstoupeni-formular.html"
SMAZANI = WEB / "smazani-uctu.html"
PRIVACY = WEB / "privacy.html"
TERMS = WEB / "terms.html"
INDEX = WEB / "index.html"
ZAZNAM = Path("ZAZNAM_O_ZPRACOVANI.md")
# The template's own source attribution (functions/api/_middleware.js). The
# policy says so whenever the product carries the migration — written by the
# template, so no product forgets to.
ZDROJE_MIGRACE = Path("db") / "migrace" / "0910_zdroje.sql"
# Script errors counted anonymously (P9, functions/api/chyba-stranky.js).
CHYBY_MIGRACE = Path("db") / "migrace" / "0930_chyby_stranek.sql"
# Why customers leave, counted (batch D2, functions/api/odchod.js).
ODCHODY_MIGRACE = Path("db") / "migrace" / "0960_odchody.sql"
POSTUP = Path("POSTUP_PRI_INCIDENTU.md")

_HLAVICKA = "GENEROVANÝ SOUBOR — neupravuj ručně. Zdroj: data-manifest.json, generátor: vykresli_zasady.py."

_STYL = """    body { font-family: system-ui, sans-serif; max-width: 40rem; margin: 2rem auto; padding: 0 1rem; line-height: 1.6; }
    table { border-collapse: collapse; width: 100%; }
    th, td { text-align: left; padding: 0.4rem 0.6rem; border-bottom: 1px solid #ccc; vertical-align: top; }
    h2 { margin-top: 1.6rem; }
    .doplnit { background: #ffe8e8; border-bottom: 2px solid #c00; padding: 0 0.2rem; font-weight: 600; }
    .meta { font-size: 0.9rem; color: #555; }
    .spotrebitel { border-left: 3px solid #2b6cb0; background: #eef5fb; padding: 0.6rem 0.9rem; }
    .formular { border: 1px solid #999; padding: 1rem 1.2rem; }"""

# Processors the template itself brings. A product adds its own via
# manifest.sluzby_treti_strany; these two are always there because the
# template's login and hosting need them.
_ZPRACOVATELE_SIDLO = {
    "Cloudflare": ("Cloudflare, Inc.", "USA", "primární instance databáze v EU"),
    "Resend": ("Resend (Plus Five Five, Inc.)", "USA", "USA / EU"),
    "GitHub": ("GitHub, Inc. (Microsoft)", "USA", "USA / EU"),
    # Payment in the Play app: Google sells and collects as the store; we
    # only learn that a purchase exists and until when it is paid.
    "Google Play": ("Google Ireland Limited / Google Commerce Limited", "Irsko", "EU"),
}


def _play(manifest: dict) -> bool:
    """Does the product sell in the Google Play app (module play)? The
    entity is what the product stores about such purchases, so the
    manifest says it once and terms, policy and record follow."""
    return any(isinstance(u, dict) and u.get("entita") == "play_nakupy"
               for u in manifest.get("ukladame") or [])


def _esc(text) -> str:
    return (str(text).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def _slot(manifest: dict, key: str, label: str, *, html: bool = True) -> str:
    """A manifest value, or a loud placeholder when it is empty."""
    value = (manifest.get(key) or "").strip() if isinstance(manifest.get(key), str) else manifest.get(key)
    if value in ("", None):
        return f'<span class="doplnit">({_esc(label)})</span>' if html else f"({label})"
    return _esc(value) if html else str(value)


def _s(manifest: dict, key: str, label: str) -> str:
    return _slot(manifest, key, label, html=True)


def _m(manifest: dict, key: str, label: str) -> str:
    return _slot(manifest, key, label, html=False)


def _produkt(manifest: dict) -> str:
    return manifest.get("produkt") or "Produkt SimteGen"


def _provozovatel(manifest: dict) -> str:
    return manifest.get("provozovatel") or "SimteGen, s.r.o."


def _kontakt_html(manifest: dict) -> str:
    kontakt = (manifest.get("kontakt_email") or "").strip()
    if not kontakt:
        return '<a href="mailto:(doplnit)"><span class="doplnit">(doplnit kontaktní e-mail)</span></a>'
    return f'<a href="mailto:{_esc(kontakt)}">{_esc(kontakt)}</a>'


def _identita_html(manifest: dict, *, plna: bool) -> str:
    """Operator identity line. plna = with DIČ and the commercial register."""
    parts = [f"<strong>{_esc(_provozovatel(manifest))}</strong>, IČO {_s(manifest, 'ico', 'doplnit IČO')}"]
    if plna:
        parts.append(f"DIČ {_s(manifest, 'dic', 'doplnit DIČ / „nejsme plátci DPH“')}")
    parts.append(f"se sídlem {_s(manifest, 'sidlo', 'doplnit sídlo')}")
    if plna:
        parts.append(f"zapsaná v obchodním rejstříku vedeném {_s(manifest, 'zapis_or', 'doplnit soud a spisovou značku')}")
    parts.append(f"e-mail {_kontakt_html(manifest)}")
    return ", ".join(parts)


def _meta(manifest: dict, *, cinna: bool = False) -> str:
    verze = manifest.get("verze_dokumentu") or "2.0"
    slovo = "účinná od" if cinna else "účinné od"
    return (f'  <p class="meta">Verze {_esc(verze)} · {slovo} '
            f"{_s(manifest, 'ucinnost_od', 'doplnit datum účinnosti')} · "
            "předchozí verze poskytneme na vyžádání.</p>")


def _hlava(title: str, *, aplikace: bool = False) -> str:
    """aplikace: the terms of a product sold in the Google Play app — the
    page hides the invoice-order paragraph there (_APLIKACE_STYL)."""
    atribut = f" {_APLIKACE_ATRIBUT}" if aplikace else ""
    styl = f"{_STYL}\n{_APLIKACE_STYL}" if aplikace else _STYL
    navic = (f'\n  <noscript><style>{_APLIKACE_BEZ_JS}</style></noscript>'
             f'\n  <script src="{PODMINKY_JS.name}" defer></script>') if aplikace else ""
    return f"""<!doctype html>
<!-- {_HLAVICKA} -->
<html lang="cs"{atribut}>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{_esc(title)}</title>
  <style>
{styl}
  </style>{navic}
</head>
<body>"""


# Google Play Payments policy (audit 19. 11. 2026): the app's footer links
# the terms, and inside the app from Google Play nothing may describe
# another way to pay — yet the terms explained the invoice order on the web.
# That paragraph is hidden in the app the way index.html hides the invoice
# order (styl.css + web/play.js): in a product with the app it stays hidden
# until a script proves the page runs in a browser (class sg-web), so a
# mistake hides it on the web (harmless) and never shows it in the app.
# The legal pages load neither styl.css nor play.js (play.js would ask for
# a rating and renew purchases on a legal page), so the rule is inline and
# the proof is a small generated script — not inline code, which would keep
# 'unsafe-inline' in the CSP (bezpecnostni_kontrola.inline_skripty). With
# JavaScript off — never the app, which runs in Chrome — <noscript> shows
# the paragraph, so the web terms stay whole for every reader.
_APLIKACE_ATRIBUT = "data-aplikace"
_APLIKACE_PRAVIDLO = "html[data-aplikace]:not(.sg-web) [data-objednavka]"
_APLIKACE_STYL = f"    {_APLIKACE_PRAVIDLO} {{ display: none; }}"
_APLIKACE_BEZ_JS = f"{_APLIKACE_PRAVIDLO} {{ display: block; }}"
PODMINKY_JS = WEB / "podminky-aplikace.js"


def vykresli_podminky_js(manifest: dict) -> str | None:
    """The browser proof for the terms (see _APLIKACE_STYL). The signs are
    web/play.js's own (signalAplikace): the app is recognisable only at
    launch, so the server's cookie (/api/play → v_aplikaci, answered to a
    stranger too) carries it to this page. Only an explicit "not the app"
    shows the paragraph; no answer keeps it hidden."""
    if not _play(manifest):
        return None
    return f"""/* {_HLAVICKA} */
// Is this page inside the Google Play app? Only an explicit "no" shows the
// invoice-order paragraph ([data-objednavka]) — why: vykresli_zasady.py.
(function () {{
  "use strict";
  var koren = document.documentElement;
  function signalAplikace() {{
    if ((document.referrer || "").indexOf("android-app://") === 0) return true;
    if (/[?&]aplikace=play\\b/.test(location.search)) return true;
    return ["standalone", "fullscreen", "minimal-ui"].some(function (rezim) {{
      return window.matchMedia && window.matchMedia("(display-mode: " + rezim + ")").matches;
    }});
  }}
  if (signalAplikace()) {{
    koren.classList.add("sg-v-aplikaci");
    return;
  }}
  fetch("/api/play", {{ credentials: "same-origin" }})
    .then(function (r) {{ return r.json(); }})
    .then(function (d) {{ koren.classList.add(d && d.v_aplikaci === false ? "sg-web" : "sg-v-aplikaci"); }})
    .catch(function () {{ /* no answer: the paragraph stays hidden */ }});
}})();
"""


def _zpracovatel_radek(s: dict) -> tuple[str, str, str, str]:
    """(full legal name, country, location text, DPA url) for a declared service."""
    nazev = s.get("nazev") or ""
    plny, zeme, kde = _ZPRACOVATELE_SIDLO.get(nazev, (nazev, "", ""))
    return plny, zeme, kde, s.get("dpa") or ""


def _radky_sluzby(manifest: dict) -> str:
    rows = []
    for s in manifest.get("sluzby_treti_strany") or []:
        plny, _, kde, dpa = _zpracovatel_radek(s)
        odkaz = f' (<a href="{_esc(dpa)}">zpracovatelská smlouva</a>)' if dpa else ""
        kde_txt = f" ({_esc(kde)})" if kde else ""
        rows.append(f"    <li><strong>{_esc(plny)}</strong> — {_esc(s.get('ucel', ''))}{kde_txt}{odkaz}</li>")
    return "\n".join(rows)


def _radky_cookies(manifest: dict) -> str:
    rows = []
    for c in manifest.get("cookies") or []:
        rows.append(f"    <li><code>{_esc(c.get('nazev', ''))}</code> — "
                    f"{_esc(c.get('ucel', ''))}; platnost {_esc(c.get('trvani', ''))}.</li>")
    return "\n".join(rows)


def _ukladame(manifest: dict) -> list[dict]:
    """Declared entities plus the three the template's operation implies
    (logs, support, accounting) — the review found the policy claiming
    "nothing else" while all three existed."""
    rows = []
    for u in manifest.get("ukladame") or []:
        rows.append({
            "entita": u.get("entita", ""), "ucel": u.get("ucel", ""), "pole": u.get("pole", ""),
            "zaklad": u.get("zaklad") or "plnění smlouvy",
            "zaklad_cl": u.get("zaklad_cl") or "čl. 6/1/b — plnění smlouvy",
            "subjekty": u.get("subjekty") or "zákazníci služby",
            "retence": u.get("retence", ""),
        })
    if ZDROJE_MIGRACE.exists():
        rows.append({
            "entita": "zdroj příchodu",
            "ucel": "zjistit, která naše propagace (reklama, katalog) přivádí zákazníky",
            "pole": "název zdroje a kampaně z odkazu, kterým jste přišli (např. „sklik“, "
                    "„jarni-akce“), u účtu; souhrnné počty návštěv podle zdroje bez vazby na osobu. "
                    "Nic se neukládá do vašeho prohlížeče.",
            "zaklad": "oprávněný zájem — vyhodnocení účinnosti propagace",
            "zaklad_cl": "čl. 6/1/f — oprávněný zájem",
            "subjekty": "zákazníci a návštěvníci",
            "retence": "u účtu do jeho smazání; souhrnné počty bez osobních údajů",
        })
    if CHYBY_MIGRACE.exists():
        rows.append({
            "entita": "chyby aplikace",
            "ucel": "najít a opravit chyby, na které v aplikaci narazíte, i když nám je nenahlásíte",
            "pole": "souhrnné počty chyb skriptu podle dne, obrazovky a místa v našem kódu — bez textu "
                    "chyby, bez vazby na osobu nebo zařízení. Nic se neukládá do vašeho prohlížeče.",
            "zaklad": "oprávněný zájem — funkční a bezpečná služba",
            "zaklad_cl": "čl. 6/1/f — oprávněný zájem",
            "subjekty": "zákazníci a návštěvníci",
            "retence": "souhrnné počty bez osobních údajů",
        })
    if ODCHODY_MIGRACE.exists():
        rows.append({
            "entita": "proč zákazníci nepokračují",
            "ucel": "zjistit, proč zákazníci po zkušební době nebo předplatném nepokračují, a podle toho "
                    "produkt zlepšit",
            "pole": "souhrnné počty důvodů podle dne a cesty — vaše odpověď na nepovinnou otázku po konci "
                    "zkušebního nebo předplaceného období a důvod zrušení předplatného, který zaznamená "
                    "Google Play — bez vazby na osobu. U účtu si pamatujeme jen to, že jste na otázku za dané "
                    "období odpověděli (aby se neopakovala), ne co jste odpověděli.",
            "zaklad": "oprávněný zájem — zlepšování služby",
            "zaklad_cl": "čl. 6/1/f — oprávněný zájem",
            "subjekty": "zákazníci",
            "retence": "souhrnné počty bez osobních údajů",
        })
    rows.append({
        "entita": "provozní a bezpečnostní logy",
        "ucel": "provozní a bezpečnostní záznamy (logy)",
        "pole": "IP adresa, čas a typ požadavku, identifikace prohlížeče",
        "zaklad": "oprávněný zájem — provoz a zabezpečení služby",
        "zaklad_cl": "čl. 6/1/f — oprávněný zájem",
        "subjekty": "zákazníci a návštěvníci",
        "retence": manifest.get("retence_logy") or "",
        "retence_label": "doplnit skutečnou dobu, typicky 30 dnů",
    })
    rows.append({
        "entita": "podpora a komunikace",
        "ucel": "vyřízení dotazu nebo požadavku podpory",
        "pole": "e-mailová adresa a obsah komunikace",
        "zaklad": "plnění smlouvy, u nezákazníků oprávněný zájem",
        "zaklad_cl": "čl. 6/1/b, u nezákazníků čl. 6/1/f",
        "subjekty": "zákazníci, zájemci",
        "retence": manifest.get("retence_podpora") or "",
        "retence_label": "doplnit, typicky 1 rok",
    })
    rows.append({
        "entita": "účetní a daňové doklady",
        "ucel": "účetní a daňové doklady",
        "pole": "fakturační údaje, částka, datum",
        "zaklad": "plnění právní povinnosti (zákon o účetnictví, zákon o DPH)",
        "zaklad_cl": "čl. 6/1/c — právní povinnost",
        "subjekty": "zákazníci",
        "retence": (manifest.get("retence_doklady") or "10 let") + "; vedeno mimo aplikaci",
    })
    return rows


def _retence_html(row: dict) -> str:
    if row.get("retence"):
        return _esc(row["retence"])
    return f'<span class="doplnit">({_esc(row.get("retence_label") or "doplnit")})</span>'


def _retence_md(row: dict) -> str:
    return row["retence"] if row.get("retence") else f"({row.get('retence_label') or 'doplnit'})"


# ── Zásady zpracování ───────────────────────────────────────────────

def vykresli_zasady(manifest: dict) -> str:
    produkt = _produkt(manifest)
    rows = "\n".join(
        f"      <tr><td>{_esc(r['ucel'])}</td><td>{_esc(r['pole'])}</td>"
        f"<td>{_esc(r['zaklad'])}</td><td>{_retence_html(r)}</td></tr>"
        for r in _ukladame(manifest)
    )
    return f"""{_hlava(f"Zásady zpracování údajů — {produkt}")}
  <h1>Zásady zpracování údajů</h1>
{_meta(manifest)}

  <p>Služba <strong>{_esc(produkt)}</strong>, provozovatel a správce údajů
  {_identita_html(manifest, plna=False)}. S dotazy k údajům nás kontaktujte na uvedeném e-mailu.</p>
  <p>Pověřence pro ochranu osobních údajů jsme nejmenovali — nesplňujeme žádnou z podmínek
  čl. 37 GDPR, které by nám to ukládaly. Dotazy k údajům vyřizuje kontaktní e-mail výše.</p>

  <h2>V jaké roli údaje zpracováváme</h2>
  <p>U údajů popsaných v těchto zásadách jsme <strong>správcem</strong> — rozhodujeme,
  proč a jak se zpracovávají.</p>
  <p>Vedle toho ukládáme obsah, který do služby vložíte vy. Jsou-li v něm osobní údaje
  třetích osob (např. vašich zákazníků), jste jejich správcem vy a my jsme pouze
  <strong>zpracovatelem</strong>, který je pro vás ukládá podle vašich pokynů.
  Pravidla pro tuto roli jsou ve <a href="zpracovatelska-smlouva.html">zpracovatelské
  smlouvě</a>; tyto zásady na takový obsah nedopadají.</p>

  <h2>Jaké údaje ukládáme a proč</h2>
  <p>Právním základem je plnění smlouvy (poskytnutí služby, kterou jste si vyžádali,
  čl. 6 odst. 1 písm. b) GDPR) a u provozních a bezpečnostních záznamů náš oprávněný zájem
  (čl. 6 odst. 1 písm. f) GDPR) na tom, aby služba fungovala, nebyla zneužita a aby bylo
  možné dohledat příčinu poruchy nebo útoku.</p>
  <table>
    <thead>
      <tr><th>Účel</th><th>Údaje</th><th>Právní základ</th><th>Jak dlouho</th></tr>
    </thead>
    <tbody>
{rows}
    </tbody>
  </table>
  <p>Poskytnutí e-mailové adresy je smluvním požadavkem — bez ní nelze účet založit
  ani službu poskytovat. Ostatní údaje vznikají provozem služby. Nedochází
  k automatizovanému rozhodování ani profilování s právními účinky pro vás.</p>

  <h2>Kde údaje jsou a kdo je zpracovává</h2>
  <p>Data běží na infrastruktuře níže uvedených zpracovatelů; primární instance databáze
  je umístěna v Evropské unii. Údaje nikomu neprodáváme a nepředáváme je k reklamním účelům.
  Kategoriemi příjemců jsou dále náš účetní a v nezbytném rozsahu orgány veřejné moci,
  ukládá-li nám to zákon.</p>
  <ul>
{_radky_sluzby(manifest)}
  </ul>

  <h2>Předávání mimo Evropskou unii</h2>
  <p>Uvedení zpracovatelé jsou společnosti se sídlem ve Spojených státech. Přestože primární
  instance databáze je v EU, může při provozu (zejména při podpoře, ochraně provozu
  a doručování e-mailů) dojít k přístupu k údajům ze Spojených států. Takové předání
  je zajištěno <strong>standardními smluvními doložkami</strong> Evropské komise
  podle čl. 46 odst. 2 písm. c) GDPR, které jsou součástí zpracovatelských smluv odkazovaných
  výše, případně rozhodnutím Evropské komise o odpovídající ochraně
  (rámec EU–USA pro ochranu údajů), je-li zpracovatel v tomto rámci certifikován.
  Kopii záruk vám na požádání poskytneme na kontaktním e-mailu.</p>

  <h2>Cookies</h2>
  <p>Používáme pouze technické cookies nezbytné pro chod služby — žádné sledovací
  ani reklamní. Pro takové cookies zákon souhlas nevyžaduje
  (§ 89 odst. 3 zákona č. 127/2005 Sb., o elektronických komunikacích):</p>
  <ul>
{_radky_cookies(manifest)}
  </ul>
  <p>Když si v aplikaci sami přepnete jazyk nebo měnu, prohlížeč si tuto volbu zapamatuje
  (úložiště prohlížeče, položka <code>sg-volba</code>), aby se příště nemusela opakovat. Nic
  jiného v ní není a nikam se neodesílá; smažete ji vymazáním dat stránky v prohlížeči.
  Výchozí měnu volíme podle země, ze které se připojujete — tu zná náš poskytovatel
  hostingu z připojení a nikde ji neukládáme.</p>

  <h2>Vaše práva</h2>
  <ul>
    <li><strong>Přístup k údajům a jejich výpis</strong> si kdykoli stáhnete přímo v aplikaci
    (Účet → Stáhnout moje data).</li>
    <li><strong>Smazání účtu a všech údajů</strong> provedete přímo v aplikaci
    (Účet → Smazat účet), postup i bez aplikace je na stránce
    <a href="smazani-uctu.html">Smazání účtu</a>. Z provozní databáze se údaje smažou okamžitě, ze zabezpečených
    záloh nejpozději do 30 dnů, kdy se zálohy přepíší. {_HLASENI_GITHUB_CS} Déle uchováváme
    jen účetní a daňové doklady, kde nám to ukládá zákon.</li>
    <li>Máte také právo na <strong>opravu</strong>, <strong>omezení zpracování</strong>
    a <strong>přenositelnost</strong> údajů — napište nám na kontaktní e-mail výše.</li>
    <li><strong>Právo vznést námitku</strong> (čl. 21 GDPR): proti zpracování založenému
    na našem oprávněném zájmu — tedy proti provozním a bezpečnostním záznamům — můžete
    kdykoli vznést námitku na kontaktním e-mailu. Zpracování pak ukončíme, pokud neprokážeme
    závažné oprávněné důvody pro jeho pokračování.</li>
    <li>Se <strong>stížností</strong> se můžete obrátit na Úřad pro ochranu osobních údajů,
    Pplk. Sochora 27, 170 00 Praha 7 (<a href="https://uoou.gov.cz">uoou.gov.cz</a>).</li>
  </ul>
  <p>Na žádost odpovíme nejpozději do jednoho měsíce; ve složitých případech lze lhůtu
  prodloužit o další dva měsíce, o čemž vás vyrozumíme.</p>

  <h2>Bezpečnostní incidenty</h2>
  <p>Pokud by došlo k porušení zabezpečení údajů, ohlásíme je Úřadu pro ochranu osobních
  údajů do 72 hodin od zjištění, pokud je pravděpodobné, že pro vás představuje riziko.
  Bude-li pro vás představovat vysoké riziko, budeme o něm bez zbytečného odkladu
  informovat i vás. Postup máme písemně zpracován.</p>

  <h2>Změny těchto zásad</h2>
  <p>Zásady můžeme aktualizovat; podstatnou změnu oznámíme v aplikaci nebo e-mailem
  nejméně 30 dní předem. Historické verze poskytneme na vyžádání.</p>

  <h2>Související dokumenty</h2>
  <p><a href="podminky.html">Obchodní podmínky</a> ·
  <a href="zpracovatelska-smlouva.html">Zpracovatelská smlouva</a></p>

  <p><a href="index.html">Zpět do aplikace</a></p>
</body>
</html>
"""


# ── Obchodní podmínky ───────────────────────────────────────────────

def _play_predplatne(manifest: dict) -> str:
    """Terms for the subscription bought in the Google Play app. The app
    sells only this way (Google Play Payments policy); the paid period is
    one and the same on the web and in the app."""
    if not _play(manifest):
        return ""
    return """  <p><strong>Předplatné v aplikaci z Google Play.</strong> V aplikaci nainstalované
  z Google Play se předplatné kupuje výhradně přes Google Play: platbu přijímá a zpracovává
  Google podle podmínek Google Play, cena v měně a s daněmi podle země zákazníka, délka
  období a automatické obnovení jsou vidět v nabídce před nákupem. Předplatné se
  <strong>obnovuje automaticky</strong> na další období, dokud ho zákazník nezruší; zrušit
  ho lze kdykoli v Google Play (Platby a předplatná → Předplatná) a zaplacené období doběhne.
  Zaplacené období platí stejně v aplikaci i na webu. Při změně ceny se u předplatného
  z Google Play postupuje podle pravidel Google Play, která zákazníka o změně předem
  informují. <strong>Smazáním účtu se předplatné v Google Play nezruší</strong> — aplikace
  proto smazání účtu nedovolí, dokud se předplatné obnovuje; zrušte ho nejdřív v Google Play.</p>
"""


def _play_odstoupeni(manifest: dict) -> str:
    """Withdrawal for a Play purchase. The Play purchase sheet does not ask
    for the § 1837 l consent our web order asks for, so the right is kept
    in full: we refund everything rather than argue a consent we never got."""
    if not _play(manifest):
        return ""
    return """  <p><strong>Předplatné koupené přes Google Play:</strong> souhlas se zahájením plnění
  podle § 1837 písm. l) se při nákupu přes Google Play nevyžaduje, právo odstoupit do 14 dnů
  proto trvá v plném rozsahu. Stačí nám napsat na kontaktní adresu; vrátíme celou zaplacenou
  částku, a to přes Google Play. Pomůže, když připojíte číslo objednávky z potvrzení
  od Google Play (začíná „GPA.“) — podle něj nákup v Google Play dohledáme.</p>
"""


def _web_predplatne(manifest: dict) -> str:
    """The subscription ordered on the web: by invoice, for one period, and
    it does NOT renew — the opposite of the app's (audit before Play
    production, 18. 11. 2026: the terms said "never renews" for everything
    and "renews automatically" two lines below). "Faktura", not "daňový
    doklad": a firm that is not a VAT payer issues no tax document.
    In a product sold in the Google Play app the paragraph carries
    data-objednavka and the app hides it (_APLIKACE_STYL)."""
    return f"""  <p{_objednavka(manifest)}><strong>Předplatné objednané na webu.</strong> Objednávkové tlačítko je označeno
  slovy „Objednávka zavazující k platbě“ a před jeho stisknutím zákazník vidí rozsah,
  délku a celkovou cenu předplatného. Předplatné se hradí na základě faktury vystavené
  poskytovatelem, se splatností uvedenou na faktuře, a platí na objednané období.
  <strong>Samo se neobnovuje</strong> — další období si zákazník objedná znovu. Objedná-li ho
  ještě před koncem zaplaceného (nebo zkušebního) období, služba mu běží dál až do splatnosti
  faktury; zaplacením se předplatné prodlouží. Zaplacené období se v aplikaci zobrazuje u účtu.</p>
"""


def _objednavka(manifest: dict) -> str:
    """The attribute that hides a web-order paragraph in the Play app."""
    return " data-objednavka" if _play(manifest) else ""


def vykresli_podminky(manifest: dict) -> str:
    produkt = _produkt(manifest)
    zkusebni = manifest.get("zkusebni_dni") or 30
    return f"""{_hlava(f"Obchodní podmínky — {produkt}", aplikace=_play(manifest))}
  <h1>Obchodní podmínky služby {_esc(produkt)}</h1>
{_meta(manifest)}

  <p>Poskytovatel: {_identita_html(manifest, plna=True)}.</p>

  <h2>1. Co je služba a pro koho je</h2>
  <p>Služba <strong>{_esc(produkt)}</strong> je webová aplikace poskytovaná na dálku
  (software jako služba). Zákazník ji používá ve svém prohlížeči, nic neinstaluje
  a data vedená ve službě zůstávají jeho.</p>
  <p>K provozu stačí běžný aktuální prohlížeč (Chrome, Firefox, Safari, Edge) s povoleným
  JavaScriptem a cookies a připojení k internetu; jiný hardware ani software není potřeba.
  Náklady na připojení nese zákazník podle sazeb svého operátora — poskytovatel si
  za použití prostředků komunikace na dálku nic neúčtuje.</p>
  <p>Službu mohou užívat podnikatelé i spotřebitelé. <strong>Spotřebitelem</strong> se rozumí
  člověk, který smlouvu uzavírá mimo rámec své podnikatelské činnosti. Ustanovení
  označená jako „pro spotřebitele“ platí jen pro ně; podnikatelů se netýkají.</p>

  <h2>2. Uzavření smlouvy a účet</h2>
  <p>Smlouva vzniká založením účtu (přihlášením jednorázovým e-mailovým odkazem)
  a trvá, dokud zákazník účet nesmaže nebo ji některá strana neukončí podle článku 9.
  Smlouva se uzavírá na dobu neurčitou; je v češtině a poskytovatel ji archivuje
  v elektronické podobě.</p>
  <p>Přihlašovací odkaz doručený na e-mail je klíčem k účtu. Zákazník proto dbá na to,
  aby k jeho e-mailové schránce neměl přístup nikdo nepovolaný, a neprodleně nám oznámí
  podezření na zneužití. Neodpovídá však za následky, které nezpůsobil a kterým nemohl
  rozumně zabránit.</p>

  <h2>3. Zkušební období, cena a předplatné</h2>
  <p>Po založení účtu je služba bezplatná po dobu <strong>{_esc(zkusebni)} dní</strong>. Po skončení
  zkušebního období se nic automaticky neúčtuje — další užívání je podmíněno tím,
  že si zákazník předplatné aktivně objedná nebo koupí.</p>
  <p>Aktuální ceník je dostupný v aplikaci před objednáním. Ceny objednávané na webu
  jsou {_s(manifest, 'cena_dph', 'doplnit: „včetně DPH“ / „bez DPH, poskytovatel není plátcem DPH“')}
  a jsou konečné — žádné další poplatky se neúčtují.</p>
{_web_predplatne(manifest)}{_play_predplatne(manifest)}  <p>Změna ceny se nedotkne již zaplaceného období; nová cena platí pro období objednaná
  nebo obnovená po její účinnosti. Zvýšení ceny oznámíme v aplikaci nebo e-mailem nejméně
  30 dní předem a zákazník, který se změnou nesouhlasí, může smlouvu do účinnosti změny
  ukončit bez jakékoli sankce.</p>
  <p>Není-li předplatné uhrazeno, přejde účet po uplynutí zaplaceného období do omezeného
  režimu: zákazník se přihlásí, vidí svá data, může si je stáhnout a účet smazat, ale nové
  záznamy nevkládá. Data se v omezeném režimu nemažou.</p>

  <h2>4. Odstoupení od smlouvy do 14 dnů (pro spotřebitele)</h2>
  <div class="spotrebitel">
  <p>Spotřebitel má právo odstoupit od smlouvy <strong>do 14 dnů ode dne jejího uzavření</strong>,
  a to bez udání důvodu a bez jakékoli sankce (§ 1829 občanského zákoníku).</p>
  <p>Odstoupit lze jakýmkoli jednoznačným prohlášením — e-mailem na kontaktní adresu uvedenou
  výše, nebo pomocí <a href="odstoupeni-formular.html">vzorového formuláře pro odstoupení</a>.
  Přijetí odstoupení potvrdíme bez zbytečného odkladu v textové podobě.</p>
  <p>Odstoupí-li spotřebitel, vrátíme mu všechny přijaté peněžní prostředky do 14 dnů
  stejným způsobem, jakým je zaplatil, není-li dohodnuto jinak.</p>
  <p><strong>Kdy právo na odstoupení zaniká:</strong> jde-li o digitální službu poskytovanou
  za úplatu, právo odstoupit zanikne, pokud plnění začalo s předchozím výslovným souhlasem
  spotřebitele uděleným před uplynutím 14denní lhůty a spotřebitel byl poučen, že tím
  právo na odstoupení ztrácí (§ 1837 písm. l) občanského zákoníku). Tento souhlas
  a poučení vyžadujeme samostatným zaškrtnutím při objednání předplatného a jeho udělení
  spotřebiteli potvrdíme v textové podobě. Bez zaškrtnutí souhlasu začneme poskytovat
  placenou službu až po uplynutí 14denní lhůty.</p>
  <p>Bezplatné zkušební období není smlouvou za úplatu a spotřebitel z něj nemá žádný
  platební závazek; účet lze kdykoli smazat.</p>
{_play_odstoupeni(manifest)}  </div>

  <h2>5. Dostupnost, podpora a vady služby</h2>
  <p>Poskytovatel provozuje službu s odbornou péčí a po celou dobu trvání smlouvy zajišťuje,
  aby byla způsobilá k obvyklému účelu, měla obvyklé vlastnosti a odpovídala popisu v těchto
  podmínkách. Po dobu trvání smlouvy poskytuje aktualizace nutné pro zachování funkčnosti
  a zabezpečení služby.</p>
  <p>Plánovanou odstávku oznamuje předem, je-li to možné. Podpora probíhá e-mailem
  na adrese uvedené výše, v pracovní dny.</p>
  <div class="spotrebitel">
  <p><strong>Pro spotřebitele:</strong> má-li digitální služba vadu, má spotřebitel práva
  podle § 2389a a následujících občanského zákoníku — zejména právo na odstranění vady
  v přiměřené době, na přiměřenou slevu z ceny a při podstatné vadě na odstoupení od smlouvy.
  Tato práva nelze předem omezit ani vyloučit a nedotýká se jich nic, co je v těchto
  podmínkách uvedeno o dostupnosti nebo o omezení odpovědnosti. Vadu stačí oznámit
  e-mailem na kontaktní adresu.</p>
  </div>
  <p>Pro zákazníky-podnikatele platí, že poskytovatel negarantuje nepřetržitou dostupnost
  služby, není-li dohodnuto jinak.</p>

  <h2>6. Data zákazníka, export a přenositelnost</h2>
  <p>Data, která zákazník do služby vloží, jsou jeho. Poskytovatel je zpracovává výhradně
  pro provoz služby, podle <a href="zasady.html">zásad zpracování údajů</a>,
  a je-li zákazník správcem osobních údajů třetích osob (např. svých vlastních zákazníků),
  podle <a href="zpracovatelska-smlouva.html">zpracovatelské smlouvy</a>, která je součástí
  těchto podmínek.</p>
  <p>Zákazník si může kdykoli a zdarma přímo v aplikaci stáhnout kompletní výpis svých dat
  ve strukturovaném, běžně používaném a strojově čitelném formátu (JSON)
  a účet včetně dat smazat. Export zahrnuje všechny záznamy, které zákazník do služby vložil,
  a údaje o jeho účtu; nezahrnuje interní technické údaje poskytovatele (např. provozní logy)
  a údaje chráněné obchodním tajemstvím poskytovatele.</p>
  <p><strong>Přechod k jinému poskytovateli.</strong> Rozhodne-li se zákazník přejít
  k jiné službě, poskytovatel mu poskytne přiměřenou součinnost: umožní export podle
  předchozího odstavce a po dobu <strong>nejméně 30 dní</strong> od podání výpovědi
  (přechodné období) ponechá data dostupná ke stažení. Za samotný export a součinnost
  poskytovatel neúčtuje žádné poplatky. Po uplynutí přechodného období a dokončení přechodu
  poskytovatel data smaže. Tato pravidla odpovídají požadavkům nařízení (EU) 2023/2854
  (Data Act) na změnu poskytovatele služby zpracování dat.</p>

  <h2>7. Povinnosti zákazníka</h2>
  <p>Zákazník službu užívá v souladu s právními předpisy, nevkládá do ní obsah, k němuž nemá
  oprávnění, a nepokouší se obcházet její zabezpečení ani ji zatěžovat nad běžnou míru.
  Za obsah, který do služby vloží, odpovídá zákazník; vkládá-li do ní osobní údaje třetích
  osob, odpovídá za to, že k tomu má právní titul.</p>

  <h2>8. Odpovědnost</h2>
  <p>Poskytovatel odpovídá za škodu způsobenou porušením těchto podmínek. Neodpovídá
  za škodu způsobenou nesprávným užitím služby zákazníkem ani za okolnosti vylučující
  odpovědnost podle § 2913 odst. 2 občanského zákoníku.</p>
  <p><strong>Pro zákazníky-podnikatele</strong> je náhrada škody omezena částkou, kterou
  zákazník za službu zaplatil za posledních 12 měsíců, a nehradí se ušlý zisk. Omezení
  neplatí pro škodu způsobenou úmyslně nebo z hrubé nedbalosti.</p>
  <div class="spotrebitel">
  <p><strong>Pro spotřebitele</strong> se omezení náhrady škody podle předchozího odstavce
  <strong>neuplatní</strong>. Spotřebiteli se nahrazuje újma v plném rozsahu podle zákona;
  práva spotřebitele z vadného plnění ani na náhradu újmy nejsou nijak omezena
  (§ 1814 občanského zákoníku).</p>
  </div>

  <h2>9. Ukončení smlouvy</h2>
  <p>Zákazník může smlouvu ukončit kdykoli a bez sankce smazáním účtu v aplikaci. Smazání
  je nevratné: před jeho dokončením aplikace nabídne stažení dat a vyžádá si potvrzení.
  Po smazání se data z provozní databáze odstraní okamžitě; ze zabezpečených záloh nejpozději
  do 30 dnů, kdy se zálohy přepíší.</p>
  <p>Poskytovatel může smlouvu vypovědět s výpovědní dobou 30 dní oznámenou e-mailem;
  výpovědní doba nikdy nepřesáhne 2 měsíce a po ní následuje přechodné období podle článku 6.
  Zaplacené předplatné za nevyužité období se v takovém případě vrací poměrně.</p>
  <p>Poskytovatel může smlouvu ukončit s okamžitou účinností jen při podstatném porušení
  podmínek zákazníkem, kterým se rozumí zejména vkládání protiprávního obsahu, útok
  na zabezpečení služby, její zneužití k rozesílání nevyžádaných sdělení nebo zatížení
  provozu nad běžnou míru. Není-li to vzhledem k povaze porušení vyloučeno, poskytovatel
  zákazníka nejprve vyzve k nápravě v přiměřené lhůtě. I při okamžitém ukončení umožní
  zákazníkovi po dobu 30 dní stažení dat.</p>
  <p>Ukončuje-li poskytovatel službu jako celek, oznámí to nejméně 60 dní předem, umožní
  stažení dat a vrátí poměrnou část předplatného.</p>

  <h2>10. Změny podmínek</h2>
  <p>Vzhledem k tomu, že jde o službu poskytovanou v běžném obchodním styku většímu počtu
  zákazníků, si poskytovatel podle § 1752 občanského zákoníku vyhrazuje právo tyto podmínky
  v přiměřeném rozsahu změnit — zejména při změně právní úpravy, rozsahu služby nebo
  technických podmínek provozu.</p>
  <p>Změnu oznámí v aplikaci a e-mailem nejméně 30 dní před její účinností, spolu s informací
  o tom, co se mění a o právu změnu odmítnout. Nesouhlasí-li zákazník, může smlouvu do
  účinnosti změny ukončit bez sankce; poskytovatel mu vrátí poměrnou část zaplaceného
  předplatného. Změna, která by zhoršila postavení zákazníka a s níž zákazník nesouhlasí,
  se na něj do konce zaplaceného období nepoužije.</p>

  <h2>11. Mimosoudní řešení sporů a dozor (pro spotřebitele)</h2>
  <div class="spotrebitel">
  <p>Spotřebitel má právo na mimosoudní řešení spotřebitelského sporu. Věcně příslušným
  subjektem je <strong>Česká obchodní inspekce</strong>, Ústřední inspektorát — oddělení ADR,
  Gorazdova 1969/24, 120 00 Praha 2, internetová adresa
  <a href="https://adr.coi.gov.cz">adr.coi.gov.cz</a>, e-mail adr@coi.gov.cz
  (§ 14 a § 20d a násl. zákona č. 634/1992 Sb., o ochraně spotřebitele).</p>
  <p>Návrh lze podat nejpozději do 1 roku ode dne, kdy spotřebitel poprvé uplatnil své právo
  u poskytovatele. Řízení je pro spotřebitele bezplatné.</p>
  <p>Dozor nad dodržováním povinností podle zákona o ochraně spotřebitele vykonává
  Česká obchodní inspekce (<a href="https://coi.gov.cz">coi.gov.cz</a>), dozor nad ochranou
  osobních údajů Úřad pro ochranu osobních údajů
  (<a href="https://uoou.gov.cz">uoou.gov.cz</a>).</p>
  </div>

  <h2>12. Závěrečná ustanovení</h2>
  <p>Smlouva se řídí právem České republiky. Je-li zákazník podnikatel, jsou k řešení sporů
  příslušné soudy podle sídla poskytovatele. Je-li zákazník spotřebitel, řídí se příslušnost
  soudu obecnou právní úpravou a spotřebitel může být žalován jen u soudu podle svého bydliště;
  volba práva nezbavuje spotřebitele ochrany, kterou mu poskytují kogentní předpisy státu
  jeho obvyklého pobytu.</p>
  <p>Je-li některé ustanovení těchto podmínek neplatné nebo nepoužitelné, zůstávají ostatní
  ustanovení v platnosti.</p>

  <p><a href="index.html">Zpět do aplikace</a> ·
  <a href="zasady.html">Zásady zpracování údajů</a> ·
  <a href="zpracovatelska-smlouva.html">Zpracovatelská smlouva</a> ·
  <a href="odstoupeni-formular.html">Formulář pro odstoupení</a></p>
</body>
</html>
"""


# ── Formulář pro odstoupení ─────────────────────────────────────────

def vykresli_odstoupeni(manifest: dict) -> str:
    produkt = _produkt(manifest)
    return f"""{_hlava(f"Vzorový formulář pro odstoupení od smlouvy — {produkt}")}
  <h1>Vzorový formulář pro odstoupení od smlouvy</h1>
  <p class="meta">Tento formulář vyplňte a odešlete jen v případě, že chcete odstoupit
  od smlouvy. Není povinné ho použít — odstoupit můžete jakýmkoli jednoznačným prohlášením.
  (§ 1820 odst. 1 písm. f) občanského zákoníku, příloha č. 1 nařízení vlády č. 363/2013 Sb.)</p>

  <div class="formular">
  <p><strong>Adresát:</strong><br>
  {_esc(_provozovatel(manifest))}, IČO {_s(manifest, 'ico', 'doplnit IČO')},
  se sídlem {_s(manifest, 'sidlo', 'doplnit sídlo')},<br>
  e-mail {_kontakt_html(manifest)}</p>

  <p>Oznamuji, že tímto odstupuji od smlouvy o poskytování služby
  <strong>{_esc(produkt)}</strong>.</p>

  <p>Datum uzavření smlouvy (založení účtu): ______________________</p>
  <p>E-mail účtu: ______________________</p>
  <p>Číslo faktury / dokladu (máte-li): ______________________</p>
  <p>Jméno a příjmení spotřebitele: ______________________</p>
  <p>Adresa spotřebitele: ______________________</p>
  <p>Bankovní účet pro vrácení peněz (nebylo-li placeno převodem): ______________________</p>
  <p>Datum: ______________________</p>
  <p>Podpis spotřebitele (pouze pokud je formulář zasílán v listinné podobě): ______________________</p>
  </div>

  <h2>Co bude následovat</h2>
  <p>Přijetí odstoupení vám bez zbytečného odkladu potvrdíme v textové podobě
  (e-mailem). Zaplacené peníze vám vrátíme do 14 dnů ode dne odstoupení stejným způsobem,
  jakým jste platili, nedohodneme-li se jinak.</p>
  <p>Právo odstoupit do 14 dnů zaniká, pokud placená služba začala být poskytována
  s vaším předchozím výslovným souhlasem uděleným před uplynutím 14denní lhůty
  a byli jste poučeni, že tím právo na odstoupení ztrácíte
  (§ 1837 písm. l) občanského zákoníku). Podrobnosti jsou v čl. 4
  <a href="podminky.html">obchodních podmínek</a>.</p>

  <p><a href="index.html">Zpět do aplikace</a></p>
</body>
</html>
"""


# ── Zpracovatelská smlouva ──────────────────────────────────────────

def _obsah_zakaznika(manifest: dict) -> str:
    return manifest.get("obsah_zakaznika_popis") or (
        "identifikační a kontaktní údaje (jméno, adresa, telefon, e-mail), údaje o zakázce "
        "nebo objednávce (popis, termíny, cena, místo plnění), fakturační údaje a obsah poznámek "
        "a volných textových polí, které správce vyplní")


def _subjekty_obsahu(manifest: dict) -> str:
    return manifest.get("subjekty_obsahu") or (
        "osoby, jejichž údaje správce do služby vloží — typicky jeho zákazníci a kontaktní "
        "osoby jeho obchodních partnerů, případně jeho pracovníci")


def vykresli_dpa(manifest: dict) -> str:
    produkt = _produkt(manifest)
    return f"""{_hlava(f"Zpracovatelská smlouva — {produkt}")}
  <h1>Smlouva o zpracování osobních údajů</h1>
{_meta(manifest, cinna=True)}

  <p>Uzavřená podle čl. 28 nařízení (EU) 2016/679 (GDPR) mezi <strong>zákazníkem</strong>
  služby {_esc(produkt)} jako <strong>správcem</strong> a {_identita_html(manifest, plna=False)}
  jako <strong>zpracovatelem</strong>. Je součástí
  <a href="podminky.html">obchodních podmínek</a>.</p>

  <h2>1. Předmět, povaha, účel a doba zpracování</h2>
  <p><strong>Předmět a povaha:</strong> zpracovatel pro správce ukládá a zpřístupňuje osobní
  údaje, které správce vloží do služby. Zpracování je automatizované a zahrnuje uložení
  v databázi, zobrazení v aplikaci, zálohování, export a výmaz.</p>
  <p><strong>Účel:</strong> výhradně provoz služby pro správce. Zpracovatel údaje nevyužívá
  k vlastním účelům, neprodává je a nepředává k reklamním účelům.</p>
  <p><strong>Doba:</strong> zpracování trvá po dobu trvání smlouvy o poskytování služby
  a končí výmazem nebo vrácením údajů podle článku 10.</p>
  <p>Tato smlouva se týká <strong>obsahu, který do služby vloží správce</strong>. Netýká se
  údajů o účtu správce (e-mailová adresa, přihlašovací tokeny, relace, evidence předplatného,
  provozní logy) — u těch je zpracovatel v postavení samostatného správce a jejich zpracování
  popisují <a href="zasady.html">zásady zpracování údajů</a>.</p>

  <h2>2. Kategorie subjektů údajů a kategorie osobních údajů</h2>
  <p><strong>Subjekty údajů:</strong> {_esc(_subjekty_obsahu(manifest))}.</p>
  <p><strong>Kategorie osobních údajů:</strong> {_esc(_obsah_zakaznika(manifest))}.</p>
  <p>Přesný rozsah určuje správce tím, jaké údaje do služby vloží. Správce odpovídá za to,
  že k jejich zpracování má právní titul a že subjekty údajů řádně informoval.</p>
  <p>Služba <strong>není určena</strong> ke zpracování zvláštních kategorií údajů podle
  čl. 9 GDPR (údaje o zdravotním stavu, biometrické údaje apod.) ani údajů o rozsudcích
  v trestních věcech podle čl. 10 GDPR. Vloží-li je správce přesto, činí tak na vlastní
  odpovědnost a je povinen o tom zpracovatele předem informovat, aby bylo možné posoudit
  přiměřenost zabezpečení.</p>

  <h2>3. Pokyny správce</h2>
  <p>Zpracovatel zpracovává údaje jen na doložené pokyny správce; pokynem je užívání služby
  podle obchodních podmínek a této smlouvy. Další pokyny zasílá správce na kontaktní e-mail;
  jde-li o pokyn nad rámec běžného provozu služby, mohou se strany dohodnout na úhradě
  nezbytných nákladů.</p>
  <p>Považuje-li zpracovatel pokyn za rozporný s GDPR nebo jiným předpisem o ochraně údajů,
  neprodleně na to správce upozorní a do vyjasnění není povinen pokyn vykonat.</p>
  <p>Údaje se zpracovávají v Evropské unii. Mimo EU je zpracovatel předá jen na pokyn správce
  nebo na základě právního předpisu EU či členského státu; v takovém případě o tom správce
  předem informuje, ledaže to daný předpis ze závažných důvodů veřejného zájmu zakazuje.
  Předání spojená se zapojením dalších zpracovatelů upravuje článek 6.</p>

  <h2>4. Důvěrnost</h2>
  <p>K údajům mají přístup jen osoby, které se k mlčenlivosti zavázaly smluvně nebo jsou
  vázány zákonnou povinností mlčenlivosti. Povinnost trvá i po skončení jejich zapojení
  do zpracování a po skončení této smlouvy.</p>

  <h2>5. Zabezpečení</h2>
  <p>Zpracovatel s ohledem na stav techniky, povahu zpracování a rizika uplatňuje zejména
  tato technická a organizační opatření (čl. 32 GDPR):</p>
  <ul>
    <li>šifrovaný přenos (HTTPS) a šifrování dat v klidu na straně poskytovatele infrastruktury;</li>
    <li>přihlášení bez hesel jednorázovými odkazy — v databázi jsou uloženy pouze otisky tokenů;</li>
    <li>oddělená databáze pro každý produkt s primární instancí v EU a oddělená testovací databáze
    (do testovací databáze se nekopírují produkční data);</li>
    <li>omezený a evidovaný přístup k produkčnímu prostředí, přístup jen pro nezbytné osoby;</li>
    <li>pravidelné zálohování s přepisem záloh nejpozději do 30 dnů;</li>
    <li>smazání účtu správcem přímo v aplikaci, které maže všechna jeho data;</li>
    <li>písemný postup při bezpečnostním incidentu a pravidelné ověřování účinnosti opatření.</li>
  </ul>
  <p>Zpracovatel může opatření měnit, nesmí však snížit dosaženou úroveň zabezpečení.</p>

  <h2>6. Další zpracovatelé</h2>
  <p>Správce uděluje obecné povolení k zapojení dalších zpracovatelů. Aktuálně jsou zapojeni:</p>
  <ul>
{_radky_sluzby(manifest)}
  </ul>
  <p>Zpracovatel uloží každému dalšímu zpracovateli smlouvou stejné povinnosti ochrany údajů,
  jaké má podle této smlouvy, zejména povinnost zavést dostatečné technické a organizační
  zabezpečení. Neplní-li další zpracovatel své povinnosti, <strong>odpovídá za jeho plnění
  správci v plném rozsahu zpracovatel</strong> (čl. 28 odst. 4 GDPR).</p>
  <p>Zamýšlenou změnu nebo doplnění dalších zpracovatelů oznámí zpracovatel v aplikaci nebo
  e-mailem nejméně 30 dní předem. Správce může proti změně v této lhůtě vznést námitku;
  nedojde-li k dohodě, může smlouvu o službě ukončit ke dni účinnosti změny bez sankce
  a s vrácením poměrné části předplatného.</p>
  <p>Předání mimo EU v rámci uvedených dalších zpracovatelů je zajištěno standardními
  smluvními doložkami Evropské komise podle čl. 46 odst. 2 písm. c) GDPR, které jsou součástí
  odkazovaných zpracovatelských smluv, případně rozhodnutím o odpovídající ochraně.
  Kopii záruk zpracovatel na žádost poskytne.</p>

  <h2>7. Součinnost</h2>
  <p>Zpracovatel je správci nápomocen:</p>
  <ul>
    <li><strong>při žádostech subjektů údajů</strong> (čl. 28 odst. 3 písm. e) GDPR) — výpis,
    oprava a výmaz údajů jsou správci dostupné přímo v aplikaci; u ostatních žádostí poskytne
    součinnost e-mailem bez zbytečného odkladu, nejpozději do 5 pracovních dnů. Obrátí-li se
    subjekt údajů se žádostí přímo na zpracovatele, zpracovatel ji nevyřizuje a bez zbytečného
    odkladu ji předá správci;</li>
    <li><strong>při plnění povinností podle čl. 32 až 36 GDPR</strong> — zabezpečení,
    ohlašování porušení, posouzení vlivu a předchozí konzultace, a to s ohledem na povahu
    zpracování a informace, které má k dispozici.</li>
  </ul>

  <h2>8. Doložení souladu a audit</h2>
  <p>Zpracovatel poskytne správci všechny informace potřebné k doložení splnění povinností
  podle čl. 28 GDPR a <strong>umožní audit</strong>, včetně inspekce, prováděný správcem nebo
  jím pověřeným auditorem, a k auditu poskytne součinnost (čl. 28 odst. 3 písm. h) GDPR).</p>
  <p>Praktické podmínky: audit se ohlašuje alespoň 14 dní předem, koná se v pracovní době,
  nesmí nepřiměřeně narušit provoz a auditor je vázán mlčenlivostí. Nejvýše jeden audit ročně
  je bezplatný; to neplatí, koná-li se audit po bezpečnostním incidentu nebo na základě
  pokynu dozorového úřadu. Tyto podmínky právo správce na audit neomezují, jen upravují
  jeho provedení.</p>

  <h2>9. Porušení zabezpečení</h2>
  <p>Zjistí-li zpracovatel porušení zabezpečení osobních údajů správce, ohlásí mu je
  bez zbytečného odkladu, <strong>nejpozději do 24 hodin od zjištění</strong>, aby správce
  stihl svou 72hodinovou lhůtu podle čl. 33 GDPR. Ohlášení obsahuje popis povahy porušení,
  dotčené kategorie a přibližný počet subjektů údajů a záznamů, pravděpodobné důsledky
  a přijatá či navržená opatření. Nejsou-li všechny informace dostupné najednou, poskytne
  je zpracovatel postupně bez dalšího zbytečného odkladu.</p>
  <p>Zpracovatel neohlašuje porušení týkající se údajů správce dozorovému úřadu ani subjektům
  údajů — to je povinností správce, ledaže ho správce ohlášením výslovně pověří.</p>

  <h2>10. Ukončení, výmaz a vrácení údajů</h2>
  <p>Po ukončení poskytování služby zpracovatel podle <strong>rozhodnutí správce</strong>
  osobní údaje buď vymaže, nebo mu je vrátí, a vymaže existující kopie
  (čl. 28 odst. 3 písm. g) GDPR). Správce své rozhodnutí sdělí nejpozději do konce
  přechodného období podle čl. 6 obchodních podmínek; nesdělí-li je, zpracovatel údaje
  po uplynutí tohoto období vymaže.</p>
  <p>Vrácením se rozumí export ve strukturovaném, běžně používaném a strojově čitelném formátu,
  který je správci dostupný přímo v aplikaci. Smazáním účtu v aplikaci správce volí výmaz.</p>
  <p>Z provozní databáze se údaje mažou okamžitě, ze záloh nejpozději do 30 dnů jejich přepisem.
  Déle se údaje uchovávají jen tam, kde to ukládá právo EU nebo členského státu;
  o takovém případu zpracovatel správce informuje.</p>

  <h2>11. Odpovědnost a závěrečná ustanovení</h2>
  <p>Odpovědnost stran se řídí čl. 82 GDPR a obchodními podmínkami; omezení náhrady škody
  sjednané v obchodních podmínkách se nevztahuje na povinnosti podle této smlouvy porušené
  úmyslně nebo z hrubé nedbalosti.</p>
  <p>Tato smlouva se řídí právem České republiky. Je-li některé její ustanovení v rozporu
  s GDPR, použije se GDPR a ostatní ustanovení zůstávají v platnosti.</p>

  <p><a href="index.html">Zpět do aplikace</a> ·
  <a href="podminky.html">Obchodní podmínky</a> ·
  <a href="zasady.html">Zásady zpracování údajů</a></p>
</body>
</html>
"""


# ── Záznam o činnostech zpracování ──────────────────────────────────

def vykresli_zaznam(manifest: dict) -> str:
    produkt = _produkt(manifest)
    provozovatel = _provozovatel(manifest)
    verze = manifest.get("verze_dokumentu") or "2.0"
    radky = "\n".join(
        f"| {r['entita']} | {r['ucel']} | {r['subjekty']} | {r['pole']} | {r['zaklad_cl']} | {_retence_md(r)} |"
        for r in _ukladame(manifest)
    )
    zprac = []
    for s in manifest.get("sluzby_treti_strany") or []:
        plny, zeme, kde, _ = _zpracovatel_radek(s)
        zaruky = "standardní smluvní doložky EK (čl. 46/2/c), případně rámec EU–USA pro ochranu údajů"
        zprac.append(f"| {plny}{f' ({zeme})' if zeme else ''} | {s.get('ucel', '')} | {kde or '—'} | {zaruky} |")
    zpracovatele_jmena = "; ".join(_zpracovatel_radek(s)[0] for s in manifest.get("sluzby_treti_strany") or [])
    return f"""<!-- {_HLAVICKA} -->
# Záznam o činnostech zpracování — {produkt}

**Verze:** {verze} · **poslední aktualizace:** {_m(manifest, 'ucinnost_od', 'doplnit datum')} · **zpracoval:** {_m(manifest, 'odpovedna_osoba', 'doplnit jméno')}
**Přezkoumat:** nejméně 1× ročně a při každé změně zpracování, zpracovatelů nebo účelů.

**Správce:** {provozovatel}, IČO {_m(manifest, 'ico', 'doplnit')}, se sídlem {_m(manifest, 'sidlo', 'doplnit')},
e-mail {_m(manifest, 'kontakt_email', 'doplnit')}, datová schránka {_m(manifest, 'datova_schranka', 'doplnit')}.
**Zástupce podle čl. 27 GDPR:** nejmenován (správce je usazen v EU).
**Pověřenec pro ochranu osobních údajů:** nejmenován — nesplněna žádná z podmínek čl. 37 GDPR.

Vedeno podle čl. 30 GDPR. Záznam má dvě části: **A** pro zpracování, kde je {provozovatel}
správcem, a **B** pro zpracování prováděná pro zákazníky, kde je {provozovatel} zpracovatelem.

---

## A. Záznam správce (čl. 30 odst. 1 GDPR)

### A.1 Účely a rozsah

| Entita / oblast | Účel | Kategorie subjektů | Kategorie údajů | Právní základ | Doba uložení |
|---|---|---|---|---|---|
{radky}

**Oprávněný zájem (čl. 6/1/f)** je u logů vymezen jako zajištění provozu, dostupnosti
a bezpečnosti služby a možnost dohledat příčinu poruchy nebo útoku. Test proporcionality:
{_m(manifest, 'balancni_test', 'doplnit odkaz na provedený balanční test nebo datum jeho provedení')}.

### A.2 Kategorie příjemců

Zpracovatelé uvedení v části A.3; účetní ({_m(manifest, 'ucetni', 'doplnit obchodní firmu')}); orgány veřejné moci
v rozsahu, v jakém to ukládá zákon. Údaje se neprodávají ani nepředávají k reklamním účelům.

### A.3 Zpracovatelé a předávání mimo EU

| Zpracovatel | Co dělá | Umístění | Záruky pro předání mimo EU |
|---|---|---|---|
{chr(10).join(zprac)}

Kopie záruk: uloženy u správce, na žádost poskytovány subjektům údajů.

### A.4 Technická a organizační opatření (obecný popis, čl. 30 odst. 1 písm. g)

Šifrovaný přenos (HTTPS) a šifrování dat v klidu; přihlášení bez hesel (jednorázové e-mailové
odkazy, v databázi jen otisky tokenů); oddělená databáze na produkt s primární instancí v EU;
oddělená testovací databáze bez produkčních dat; omezený a evidovaný přístup k produkci;
zálohování s přepisem do 30 dnů; smazání účtu zákazníkem přímo v aplikaci maže všechna jeho
data; písemný postup při incidentu v `POSTUP_PRI_INCIDENTU.md`; roční přezkum opatření.

---

## B. Záznam zpracovatele (čl. 30 odst. 2 GDPR)

{provozovatel} zpracovává osobní údaje jako **zpracovatel** pro zákazníky služby, kteří
do aplikace vkládají údaje třetích osob. Právním rámcem je
`web/zpracovatelska-smlouva.html` (čl. 28 GDPR), uzavíraná jako součást obchodních podmínek.

| Položka | Obsah |
|---|---|
| **Správci, pro které se zpracovává** | zákazníci služby {produkt}; jmenný seznam vede správce v evidenci účtů (viz entita `uzivatele`) |
| **Kategorie zpracování** | uložení v databázi, zpřístupnění a zobrazení v aplikaci, zálohování, export na pokyn správce, výmaz |
| **Kategorie subjektů údajů** | {_subjekty_obsahu(manifest)} |
| **Kategorie údajů** | {_obsah_zakaznika(manifest)} |
| **Zvláštní kategorie (čl. 9/10)** | služba k nim není určena; jejich vkládání je smluvně vyloučeno |
| **Další zpracovatelé** | {zpracovatele_jmena} (viz A.3) |
| **Předání mimo EU** | jen na pokyn správce nebo v rámci dalších zpracovatelů, se zárukami podle A.3 |
| **Doba zpracování** | po dobu trvání smlouvy o službě; poté výmaz nebo vrácení dle volby správce |
| **Technická a organizační opatření** | shodná s A.4 |

---

## Poznámky k vedení záznamu

- Výjimka z vedení záznamu pro subjekty pod 250 zaměstnanců (čl. 30 odst. 5 GDPR)
  se **nepoužije**, protože zpracování probíhá pravidelně a není příležitostné.
- Záznam se na vyžádání předkládá Úřadu pro ochranu osobních údajů.
- Zdrojem je `data-manifest.json` tohoto repozitáře; generuje `vykresli_zasady.py`.
"""


# ── Postup při incidentu ────────────────────────────────────────────

def vykresli_postup(manifest: dict) -> str:
    return f"""<!-- {_HLAVICKA} -->
# Postup při bezpečnostním incidentu

Platí pro každý produkt z této šablony. „Incidentem" se myslí důvodné podezření, že se
k uloženým údajům dostal někdo nepovolaný, že byly změněny nebo zničeny nebo se staly
nedostupnými (únik databáze, kompromitovaný token, chyba zpřístupňující cizí data,
ransomware, ztráta záloh).

**Odpovědná osoba:** {_m(manifest, 'odpovedna_osoba', 'doplnit jméno')}, zástup: {_m(manifest, 'zastup', 'doplnit jméno')}.
Kdo incident zjistí, uvědomí ji neprodleně — lhůty níže běží od okamžiku, kdy se
o incidentu dozvěděl kdokoli z firmy, ne od okamžiku, kdy se to dozvěděla odpovědná osoba.

---

## 1. Zastav škodu (hned)

Otoč Cloudflare API token a klíč k odesílání e-mailů, smaž všechny relace
(`DELETE FROM relace`), v krajním případě pozastav Pages projekt.
Nic z toho nepotřebuje ničí souhlas. Kompromitované přístupové údaje se nikdy
nepoužívají znovu ani v jiném prostředí.

## 2. Zapiš, co se stalo

Do evidence incidentů (`incidenty/RRRR-MM-DD-nazev.md`) zapiš:

- čas incidentu a čas zjištění (obojí),
- co uniklo — které entity a kategorie údajů,
- kolika účtů a přibližně kolika subjektů údajů se to týká,
- jak k tomu došlo a jak to bylo zjištěno,
- pravděpodobné důsledky pro dotčené osoby,
- přijatá a navržená opatření.

**Zapisuje se každý incident, i ten, který se nikam nehlásí.** Evidenci vyžaduje
čl. 33 odst. 5 GDPR a slouží jako doklad, že posouzení proběhlo.

## 3. Urči roli — tohle rozhoduje, komu se hlásí

| Čích údajů se incident týká | Naše role | Komu hlásíme |
|---|---|---|
| účty zákazníků, přihlašovací tokeny, relace, předplatné, logy | **správce** | ÚOOÚ do 72 h + dotčeným osobám při vysokém riziku |
| obsah, který do aplikace vložil zákazník (údaje jeho klientů) | **zpracovatel** | **dotčenému zákazníkovi do 24 h** — on pak hlásí ÚOOÚ sám |
| obojí zároveň | obě role | obě větve současně |

V roli zpracovatele **nehlásíme ÚOOÚ ani subjektům údajů** — to je povinnost zákazníka
jako správce (čl. 33 odst. 2 GDPR). Naší povinností je dát mu včas úplné podklady.

## 4. V roli správce: ohlášení ÚOOÚ do 72 hodin

Ohlas na https://uoou.gov.cz (formulář pro ohlášení porušení zabezpečení)
**do 72 hodin od zjištění**, pokud je pravděpodobné, že incident představuje riziko
pro práva a svobody dotčených osob (čl. 33 odst. 1 GDPR).

Riziko posuzuj podle typu a citlivosti údajů, snadnosti identifikace osob, závažnosti
důsledků, počtu dotčených osob a toho, zda byly údaje čitelné (šifrované × nešifrované).
U této šablony uniká nejvýš e-mail a data deklarovaná v manifestu — u úniku e-mailů
spolu s otisky tokenů riziko zpravidla dosaženo je; samostatný únik nečitelných otisků
tokenů bez e-mailů zpravidla ne. Závěr vždy odůvodni v evidenci.

Nestihne-li se 72 h, ohlas i tak a připoj **důvody prodlení** — pozdní ohlášení s odůvodněním
je přípustné, neohlášení ne. Nejsou-li všechny informace k dispozici, ohlas, co víš,
a zbytek doplň postupně.

## 5. Informuj dotčené osoby

- **V roli správce:** informuj dotčené osoby bez zbytečného odkladu, pokud incident
  představuje **vysoké riziko** pro jejich práva a svobody (čl. 34 GDPR). Sděl jim
  srozumitelně, co se stalo, co s tím děláme, co mají udělat oni a kontakt na nás.
  Informovat nemusíš, pokud byly údaje nečitelné (šifrované), pokud jsi přijal opatření,
  která vysoké riziko odvrátila, nebo pokud by to vyžadovalo nepřiměřené úsilí —
  tehdy stačí veřejné oznámení. Důvod zapiš do evidence.
- **V roli zpracovatele:** dotčené osoby neinformuješ ty, ale zákazník. Nabídni mu
  součinnost a podklady.
- **Vždy:** ať už je povinnost jakákoli, zvaž informování zákazníků z hlediska důvěry.
  Dobrovolné oznámení je v pořádku — jen ho neprezentuj jako zákonnou povinnost.

## 6. Oprav příčinu

Normální cestou (build větev → recenze → merge). Po vyřešení doplň poučení
do tohoto souboru v šabloně, ať ho zdědí další produkty, a zkontroluj, zda
zjištění nemění technická a organizační opatření popsaná v záznamu o činnostech
zpracování a ve zpracovatelské smlouvě — pokud ano, aktualizuj i je.

---

## Lhůty na jednom místě

| Kdy | Co |
|---|---|
| ihned | zastavit škodu, uvědomit odpovědnou osobu |
| do 24 h | v roli zpracovatele ohlásit dotčenému zákazníkovi |
| do 72 h od zjištění | v roli správce ohlásit ÚOOÚ (je-li riziko) |
| bez zbytečného odkladu | informovat dotčené osoby (je-li vysoké riziko) |
| průběžně | vést evidenci incidentů |

## Kontakty

- Odpovědná osoba a kontakt na správce: viz výše a `data-manifest.json` (`kontakt_email`)
- Úřad pro ochranu osobních údajů: https://uoou.gov.cz, Pplk. Sochora 27, 170 00 Praha 7
- **K ověření:** spadá-li firma pod zákon o kybernetické bezpečnosti (NIS2), hlásí se
  incidenty také NÚKIB. U poskytovatele cloudových služeb pod 50 zaměstnanci a s obratem
  do 10 mil. EUR to zpravidla neplatí — potvrdit a zapsat závěr sem.
"""


# ── Smazání účtu (Google Play: Account / Data deletion URL) ─────────

# Reports mirrored to GitHub (schranka_sifra.js) on deletion of the account
# (functions/api/ucet/smazat.js + schranka.vymaz_hlaseni). The page said the
# text "is replaced with a deletion notice" — true for the issue, but GitHub
# keeps the edit history (on a public repo anyone can open it), so the
# encrypted block stays there. Said as it is: encrypted, readable only by
# us, our decrypted copy erased, the encrypted form may remain in GitHub's
# history (audit 19. 11. 2026). One wording for the deletion page and the
# policy, so a lawyer reads one claim.
_HLASENI_GITHUB_CS = ("Kopie vašich hlášení u našeho poskytovatele GitHub jsou zašifrované — přečíst je "
                      "můžeme jen my. Při smazání účtu jejich text nahradíme větou o smazání a svou "
                      "rozšifrovanou kopii smažeme. Zašifrovaná podoba hlášení však může zůstat v historii "
                      "úprav, kterou GitHub uchovává; bez našeho klíče ji přečíst nelze.")
_HLASENI_GITHUB_EN = ("The copies of your reports at our provider GitHub are encrypted — only we can read "
                      "them. When the account is deleted we replace their text with a deletion notice and "
                      "delete our decrypted copy. The encrypted form of a report may, however, remain in "
                      "the edit history GitHub keeps; it cannot be read without our key.")


def vykresli_smazani(manifest: dict) -> str:
    """The page Google Play's "delete account" and "delete data" links point
    to (vykresli_aplikaci.smazani_uctu_cesta). Google wants the steps
    prominent and about this app; they pointed at the privacy policy, where
    erasure is one bullet, in Czech only — and an app from Google Play is
    sold in English too (audit before Play production, 18. 11. 2026). Both
    languages on one static page: it is read by Google's reviewer and by
    someone who may no longer be able to open the app."""
    produkt = _esc(_produkt(manifest))
    kontakt = _kontakt_html(manifest)
    provozovatel = _esc(_provozovatel(manifest))
    play_cs = play_en = ""
    if _play(manifest):
        play_cs = """  <p><strong>Předplatné z Google Play smazáním účtu nekončí.</strong> Nejdřív ho zrušte
  v Google Play (Platby a předplatná → Předplatná); zaplacené období doběhne. Aplikace
  smazání účtu nedovolí, dokud se předplatné obnovuje.</p>
"""
        play_en = """  <p><strong>Deleting the account does not end a Google Play subscription.</strong> Cancel it in
  Google Play first (Payments &amp; subscriptions → Subscriptions); the paid period runs to its
  end. The app does not let you delete the account while the subscription still renews.</p>
"""
    return f"""{_hlava(f"Smazání účtu a údajů — {_produkt(manifest)}")}
  <h1>Smazání účtu a údajů — {produkt}</h1>
  <p>Službu {produkt} provozuje {provozovatel}, kontakt {kontakt}.</p>

  <h2>V aplikaci</h2>
  <ol>
    <li>Přihlaste se do aplikace {produkt}.</li>
    <li>Otevřete <strong>Účet</strong>.</li>
    <li>Klepněte na <strong>Smazat účet</strong> a smazání potvrďte. Předtím si můžete
    stáhnout svá data (<strong>Stáhnout moje data</strong>).</li>
  </ol>
{play_cs}
  <h2>Bez aplikace</h2>
  <p>Napište nám na {kontakt} z e-mailu, kterým se přihlašujete, s předmětem
  „Smazání účtu“. Účet smažeme a potvrdíme to nejpozději do jednoho měsíce.</p>

  <h2>Co se smaže a co zůstává</h2>
  <ul>
    <li>Účet, všechna data, která jste do služby vložili, přihlašovací údaje a hlášení
    chyb se z provozní databáze smažou <strong>okamžitě</strong>, ze zabezpečených záloh
    nejpozději do 30 dnů.</li>
    <li>{_HLASENI_GITHUB_CS}</li>
    <li>Déle uchováváme jen účetní a daňové doklady (faktury), kde nám to ukládá zákon.</li>
    <li>Souhrnné počty bez vazby na účet (např. kolik lidí službu navštívilo) nejsou
    osobní údaje a zůstávají.</li>
  </ul>
  <p>Podrobnosti jsou v <a href="zasady.html">zásadách zpracování údajů</a>.</p>

  <section lang="en">
  <h2>Deleting your account and data — {produkt}</h2>
  <p>{produkt} is run by {provozovatel}, contact {kontakt}.</p>
  <h3>In the app</h3>
  <ol>
    <li>Sign in to {produkt}.</li>
    <li>Open <strong>Account</strong>.</li>
    <li>Tap <strong>Delete account</strong> and confirm. You can download your data first
    (<strong>Download my data</strong>).</li>
  </ol>
{play_en}  <h3>Without the app</h3>
  <p>Write to {kontakt} from the e-mail address you sign in with, subject “Account deletion”.
  We delete the account and confirm it within one month at the latest.</p>
  <h3>What is deleted and what stays</h3>
  <ul>
    <li>The account, all data you entered, sign-in records and bug reports are deleted from
    the live database <strong>immediately</strong> and from secured backups within 30 days.</li>
    <li>{_HLASENI_GITHUB_EN}</li>
    <li>We keep only accounting and tax documents (invoices) for as long as the law requires.</li>
    <li>Aggregate counts not linked to any account (such as how many people visited) are not
    personal data and stay.</li>
  </ul>
  <p>{'Details are in the <a href="privacy.html">privacy policy</a>.' if _anglicky() else
     'Details are in the privacy policy (<a href="zasady.html">zasady.html</a>, in Czech).'}</p>
  </section>

  <p><a href="index.html">Zpět do aplikace / Back to the app</a></p>
</body>
</html>
"""


# ── English: privacy.html, terms.html ──────────────────────────────
# A product for the world speaks English from its first version (batch B)
# and Google Play shows its English listing by default — yet the privacy
# policy and the terms were Czech only (audit before Play production,
# 18. 11. 2026). Generated only for a product whose app declares English
# (simtegen-jazyky in web/index.html); a Czech product gets nothing new.
# The template's own entities, services and cookies are translated here;
# a product's own entity carries its English in the manifest
# (ukladame[].en = {ucel, pole, retence}) — the builder's gate asks for it
# (stavitel._pravni_en_chybi). Anything still only in Czech is shown in
# Czech and marked, never silently dropped: the Czech version is the one a
# lawyer approved.

def _anglicky() -> bool:
    """The app declares English (the same meta simtegen.js reads)."""
    try:
        text = INDEX.read_text(encoding="utf-8")
    except OSError:
        return False
    m = re.search(r'<meta\s+name="simtegen-jazyky"\s+content="([^"]*)"', text)
    return bool(m) and "en" in m.group(1).split()


_V_CESTINE = " (in Czech)"
_CESKA_PISMENA = re.compile(r"[ěščřžýáíéůúňťďĚŠČŘŽÝÁÍÉŮÚŇŤĎ]")

# The template's entities (sablona_pamet/data-manifest.json, stavitel's
# _INFRA_ENTITY and the Play module): {entita: (purpose, data, retention)}.
_EN_ENTITY = {
    "uzivatele": ("customer account and sign-in", "e-mail address, account creation time, app language",
                  "until the customer deletes the account"),
    "prihlasovaci_odkazy": ("one-time sign-in by an e-mailed link",
                            "token digest, e-mail address, expiry, app language", "24 hours"),
    "relace": ("keeping you signed in", "token digest, link to the account, expiry",
               "30 days from the last use of the app, at most 90 days from signing in"),
    "predplatne": ("record of the paid subscription period; an e-mail a week before a prepaid period ends "
                   "(only when paying by invoice, at most once per period; no advertising)",
                   "link to the account, end date of the subscription, payment note (e.g. document number)",
                   "until the customer deletes the account; the operator keeps accounting documents outside "
                   "the app for the period required by law"),
    "hlaseni": ("your reports and questions about the app and our answers; we let you know about an answer "
                "by e-mail (with its text, at most once per answer)",
                "report text, status, answer, record number in the support system, time",
                "until the customer deletes the account"),
    "platby": ("record of paid subscription periods (payment history)",
               "link to the account, number of months paid, payment note, time of the entry",
               "until the customer deletes the account; the operator keeps accounting documents outside "
               "the app for the period required by law"),
    "objednavky": ("subscription order and record of the consent to start the service",
                   "link to the account, length and option of the subscription, price, billing details, "
                   "whether you are a consumer, the consent to start and its time, status",
                   "until the customer deletes the account; the operator keeps accounting documents outside "
                   "the app for the period required by law"),
    "zkusebni_doba": ("notices that the free trial is about to end and has ended (in the app and in at most "
                      "three service e-mails — 2–3 days and 1 day before the end and after it; no advertising)",
                      "link to the account, end date of the trial as the app derives it from your account",
                      "until the customer deletes the account"),
    "ukazkova_data": ("filling an empty account with made-up sample records on your request, and removing "
                      "them with one tap",
                      "link to the account, numbers of the sample records, time loaded (the sample data "
                      "itself is made up)",
                      "until the sample data is removed or the customer deletes the account"),
    "play_nakupy": ("subscription bought in the Google Play app: verifying the purchase with Google and "
                    "the period it pays for",
                    "link to the account, Google Play purchase token, product, end of the paid period, "
                    "subscription state, time of the last check",
                    "until the customer deletes the account"),
}
_EN_UPOMINKY_ZAKLAD = ("so that each notice about the end of the trial or of a prepaid period and each "
                       "e-mail with an answer to a report goes out at most once")
_EN_UPOMINKY_ODCHOD = ("and so that the question why you do not continue can be answered only once per ended "
                       "period (we remember that you answered, not what)")
_EN_UPOMINKY_RECENZE = ("and so that the request to rate the app in Google Play appears at most twice (only "
                        "after a repeated payment, never by e-mail)")

# Standard legal bases as the template writes them.
_EN_ZAKLAD = {
    "plnění smlouvy": "performance of the contract",
    "plnění smlouvy, u nezákazníků oprávněný zájem": "performance of the contract; legitimate interest for "
                                                      "non-customers",
    "oprávněný zájem — vyhodnocení účinnosti propagace": "legitimate interest — measuring how well our "
                                                         "promotion works",
    "oprávněný zájem — funkční a bezpečná služba": "legitimate interest — a working and secure service",
    "oprávněný zájem — zlepšování služby": "legitimate interest — improving the service",
    "oprávněný zájem — provoz a zabezpečení služby": "legitimate interest — running and securing the service",
    "plnění právní povinnosti (zákon o účetnictví, zákon o DPH)": "compliance with a legal obligation "
                                                                  "(Accounting Act, VAT Act)",
}

# Retention as the template and products usually write it: the fixed
# phrases, then "N <unit>". Whatever stays Czech is marked.
_EN_CAS_FRAZE = (
    ("do smazání účtu zákazníkem", "until the customer deletes the account"),
    ("vedeno mimo aplikaci", "kept outside the app"),
    ("souhrnné počty bez osobních údajů", "aggregate counts without personal data"),
    ("od posledního použití", "from the last use"),
    ("nejdéle", "at most"),
)
_EN_JEDNOTKY = (
    (r"(\d+)\s*(?:let|roků|roky|rok)\b", r"\1 years"),
    (r"(\d+)\s*(?:měsíců|měsíce|měsíc)\b", r"\1 months"),
    (r"(\d+)\s*(?:dnů|dní|dny|den)\b", r"\1 days"),
    (r"(\d+)\s*(?:hodin|hodiny|hodina)\b", r"\1 hours"),
)


def _en_cas(text: str) -> str:
    if not text:
        return ""
    out = text
    for cs, en in _EN_CAS_FRAZE:
        out = out.replace(cs, en)
    for vzor, nahrada in _EN_JEDNOTKY:
        out = re.sub(vzor, nahrada, out)
    out = out.replace(" a ", " and ").replace("; ", "; ")
    return out if not _CESKA_PISMENA.search(out) else text + _V_CESTINE


def _en_text(text: str) -> str:
    """A product's own Czech words, kept but marked."""
    return text + _V_CESTINE if text and _CESKA_PISMENA.search(text) else text


_EN_SLUZBY = {
    "Cloudflare": ("Cloudflare, Inc.", "hosting of the app and the database (primary instance in the EU)",
                   "primary database instance in the EU"),
    "Resend": ("Resend (Plus Five Five, Inc.)", "sending account e-mails: the sign-in link, order "
               "confirmations, notices about the end of the trial and of prepaid periods, and answers to "
               "reports", "USA / EU"),
    "GitHub": ("GitHub, Inc. (Microsoft)", "keeping customers' reports for support (report text, technical "
               "details of the page and an anonymous account fingerprint with whether the subscription is "
               "paid and the account's age — encrypted, GitHub sees only an unreadable block; no e-mail, no "
               "name)", "USA / EU"),
    "Google Play": ("Google Ireland Limited / Google Commerce Limited", "selling the subscription in the "
                    "Google Play app: Google takes and processes the payment; we learn only that a purchase "
                    "exists and until when it is paid", "EU"),
}
_EN_COOKIES = {
    "__Host-relace": ("keeping you signed in (technical, HttpOnly)",
                      "30 days from the last use, at most 90 days"),
    "aplikace": ("remembering that the page runs inside the Google Play app, so that it never offers "
                 "another way of paying there (technical)", "1 year"),
}


def _ukladame_en(manifest: dict) -> list[dict]:
    """English rows in the same order as _ukladame (so the two policies
    describe the same table)."""
    rows = []
    for u, cz in zip(manifest.get("ukladame") or [], _ukladame(manifest)):
        entita = u.get("entita", "")
        vlastni = u.get("en") if isinstance(u.get("en"), dict) else {}
        if entita == "upominky":
            ucel = _EN_UPOMINKY_ZAKLAD
            if _ODCHODY_ZNACKA in (u.get("ucel") or ""):
                ucel += "; " + _EN_UPOMINKY_ODCHOD
            if _RECENZE_ZNACKA in (u.get("ucel") or ""):
                ucel += "; " + _EN_UPOMINKY_RECENZE
            sablona = (ucel, "link to the account, kind of notice, time sent", "until the customer deletes the account")
        else:
            sablona = _EN_ENTITY.get(entita)
        if vlastni.get("ucel"):
            ucel, pole, retence = (vlastni.get("ucel"), vlastni.get("pole") or _en_text(cz["pole"]),
                                   vlastni.get("retence") or _en_cas(cz["retence"]))
        elif sablona:
            ucel, pole, retence = sablona
        else:
            ucel, pole, retence = _en_text(cz["ucel"]), _en_text(cz["pole"]), _en_cas(cz["retence"])
        rows.append({"ucel": ucel, "pole": pole,
                     "zaklad": vlastni.get("zaklad") or _EN_ZAKLAD.get(cz["zaklad"]) or _en_text(cz["zaklad"]),
                     "retence": retence, "retence_label": cz.get("retence_label")})
    vlastnich = len(manifest.get("ukladame") or [])
    for cz in _ukladame(manifest)[vlastnich:]:
        rows.append({"ucel": _EN_RADKY_SABLONY.get(cz["entita"], (_en_text(cz["ucel"]),))[0],
                     "pole": _EN_RADKY_SABLONY.get(cz["entita"], (None, _en_text(cz["pole"])))[1],
                     "zaklad": _EN_ZAKLAD.get(cz["zaklad"]) or _en_text(cz["zaklad"]),
                     "retence": _en_cas(cz["retence"]), "retence_label": cz.get("retence_label")})
    return rows


# The rows the template adds by itself (_ukladame after the declared ones).
_EN_RADKY_SABLONY = {
    "zdroj příchodu": ("finding out which of our promotion (an ad, a catalogue) brings customers",
                       "the source and campaign name from the link you arrived by (e.g. “sklik”, “spring-offer”), "
                       "with the account; aggregate visit counts by source not linked to anyone. Nothing is "
                       "stored in your browser."),
    "chyby aplikace": ("finding and fixing errors you run into in the app, even if you do not report them",
                       "aggregate counts of script errors by day, screen and place in our code — no error text, "
                       "not linked to a person or device. Nothing is stored in your browser."),
    "proč zákazníci nepokračují": ("finding out why customers do not continue after the trial or the "
                                   "subscription, and improving the product accordingly",
                                   "aggregate counts of reasons by day and channel — your answer to an optional "
                                   "question after the trial or a prepaid period ends, and the cancellation "
                                   "reason Google Play records — not linked to a person. With the account we "
                                   "only remember that you answered for that period (so it is not asked "
                                   "again), not what you answered."),
    "provozní a bezpečnostní logy": ("operational and security records (logs)",
                                     "IP address, time and type of the request, browser identification"),
    "podpora a komunikace": ("handling a question or a support request", "e-mail address and the "
                             "content of the communication"),
    "účetní a daňové doklady": ("accounting and tax documents", "billing details, amount, date"),
}
_ODCHODY_ZNACKA = "proč nepokračujete"
_RECENZE_ZNACKA = "hodnocení v Google Play"


def _retence_en_html(row: dict) -> str:
    if row.get("retence"):
        return _esc(row["retence"])
    return f'<span class="doplnit">({_esc(row.get("retence_label") or "doplnit")})</span>'


def _hlava_en(title: str, *, aplikace: bool = False) -> str:
    return _hlava(title, aplikace=aplikace).replace('<html lang="cs"', '<html lang="en"', 1)


def _identita_en(manifest: dict, *, plna: bool) -> str:
    parts = [f"<strong>{_esc(_provozovatel(manifest))}</strong>, company ID (IČO) {_s(manifest, 'ico', 'doplnit IČO')}"]
    if plna:
        parts.append(f"VAT ID (DIČ) {_s(manifest, 'dic', 'doplnit DIČ / „nejsme plátci DPH“')}")
    parts.append(f"registered office {_s(manifest, 'sidlo', 'doplnit sídlo')}, Czech Republic")
    if plna:
        parts.append(f"registered in the Commercial Register kept by "
                     f"{_s(manifest, 'zapis_or', 'doplnit soud a spisovou značku')}")
    parts.append(f"e-mail {_kontakt_html(manifest)}")
    return ", ".join(parts)


def _meta_en(manifest: dict, ceska: str) -> str:
    verze = manifest.get("verze_dokumentu") or "2.0"
    return (f'  <p class="meta">Version {_esc(verze)} · effective from '
            f"{_s(manifest, 'ucinnost_od', 'doplnit datum účinnosti')} · earlier versions on request. "
            f'This is a translation of the <a href="{ceska}">Czech version</a>, which prevails in case of '
            "doubt.</p>")


def _cena_dph_en(manifest: dict) -> str:
    text = (manifest.get("cena_dph") or "").strip()
    if not text:
        return _s(manifest, "cena_dph", 'doplnit: „včetně DPH“ / „bez DPH, poskytovatel není plátcem DPH“')
    nizko = text.lower()
    if "není plátcem" in nizko or "neni platcem" in nizko:
        return "without VAT — the provider is not a VAT payer"
    if "včetně dph" in nizko:
        return "including VAT"
    return _esc(text) + _V_CESTINE


def vykresli_privacy(manifest: dict) -> str | None:
    if not _anglicky():
        return None
    produkt = _produkt(manifest)
    rows = "\n".join(
        f"      <tr><td>{_esc(r['ucel'])}</td><td>{_esc(r['pole'])}</td>"
        f"<td>{_esc(r['zaklad'])}</td><td>{_retence_en_html(r)}</td></tr>"
        for r in _ukladame_en(manifest))
    sluzby = []
    for s in manifest.get("sluzby_treti_strany") or []:
        plny, ucel, kde = _EN_SLUZBY.get(s.get("nazev") or "", (s.get("nazev") or "", _en_text(s.get("ucel") or ""), ""))
        odkaz = f' (<a href="{_esc(s["dpa"])}">data processing agreement</a>)' if s.get("dpa") else ""
        sluzby.append(f"    <li><strong>{_esc(plny)}</strong> — {_esc(ucel)}{f' ({_esc(kde)})' if kde else ''}{odkaz}</li>")
    cookies = []
    for c in manifest.get("cookies") or []:
        ucel, trvani = _EN_COOKIES.get(c.get("nazev") or "", (_en_text(c.get("ucel") or ""), _en_cas(c.get("trvani") or "")))
        cookies.append(f"    <li><code>{_esc(c.get('nazev', ''))}</code> — {_esc(ucel)}; valid for {_esc(trvani)}.</li>")
    return f"""{_hlava_en(f"Privacy policy — {produkt}")}
  <h1>Privacy policy</h1>
{_meta_en(manifest, "zasady.html")}

  <p>The service <strong>{_esc(produkt)}</strong> is operated by, and your data is controlled by,
  {_identita_en(manifest, plna=False)}. Contact us at that e-mail with any question about your data.</p>
  <p>We have not appointed a data protection officer — none of the conditions of Article 37 GDPR that
  would require it applies to us. Questions about data are handled at the contact e-mail above.</p>

  <h2>Our role</h2>
  <p>For the data described in this policy we are the <strong>controller</strong> — we decide why and
  how it is processed.</p>
  <p>Besides that we store the content you put into the service. If it contains personal data of other
  people (for example your own customers), you are their controller and we are only a
  <strong>processor</strong> storing it for you on your instructions. That role is governed by the
  <a href="zpracovatelska-smlouva.html">data processing agreement</a> (in Czech); this policy does not
  cover such content.</p>

  <h2>What we store and why</h2>
  <p>The legal basis is the performance of a contract (providing the service you asked for, Article 6(1)(b)
  GDPR) and, for operational and security records, our legitimate interest (Article 6(1)(f) GDPR) in the
  service working, not being misused, and the cause of a fault or an attack being traceable.</p>
  <table>
    <thead>
      <tr><th>Purpose</th><th>Data</th><th>Legal basis</th><th>How long</th></tr>
    </thead>
    <tbody>
{rows}
    </tbody>
  </table>
  <p>Giving an e-mail address is a contractual requirement — without it no account can be created and the
  service cannot be provided. Other data arises from using the service. There is no automated
  decision-making or profiling with legal effects for you.</p>

  <h2>Where the data is and who processes it</h2>
  <p>The data runs on the infrastructure of the processors below; the primary database instance is located
  in the European Union. We do not sell data or pass it on for advertising. Further recipients are our
  accountant and, to the extent necessary, public authorities where the law requires it.</p>
  <ul>
{chr(10).join(sluzby)}
  </ul>

  <h2>Transfers outside the European Union</h2>
  <p>The processors listed are companies based in the United States. Although the primary database instance
  is in the EU, the data may be accessed from the United States during operation (in particular for support,
  protecting the service and delivering e-mail). Such a transfer is covered by the European Commission's
  <strong>standard contractual clauses</strong> under Article 46(2)(c) GDPR, which form part of the
  processing agreements linked above, or by the Commission's adequacy decision (EU–US Data Privacy
  Framework) where the processor is certified under it. We will provide a copy of the safeguards on request
  at the contact e-mail.</p>

  <h2>Cookies</h2>
  <p>We use only technical cookies necessary for the service — no tracking or advertising cookies. The law
  does not require consent for such cookies (Section 89(3) of Czech Act No. 127/2005 Coll.,
  on Electronic Communications):</p>
  <ul>
{chr(10).join(cookies)}
  </ul>
  <p>When you switch the language or the currency in the app yourself, your browser remembers that choice
  (browser storage, item <code>sg-volba</code>) so you need not repeat it. Nothing else is in it and it is
  never sent anywhere; you remove it by clearing the site's data in your browser. The default currency
  follows the country you connect from — our hosting provider knows it from the connection and we do not
  store it anywhere.</p>

  <h2>Your rights</h2>
  <ul>
    <li><strong>Access to your data and a copy of it</strong>: download it in the app at any time
    (Account → Download my data).</li>
    <li><strong>Deleting the account and all data</strong>: in the app (Account → Delete account); the
    steps, also without the app, are on the page <a href="smazani-uctu.html">Deleting your account</a>.
    Data is deleted from the live database immediately and from secured backups within 30 days, when the
    backups are overwritten. {_HLASENI_GITHUB_EN} We keep longer only accounting and tax documents where
    the law requires it.</li>
    <li>You also have the right to <strong>rectification</strong>, <strong>restriction of
    processing</strong> and <strong>data portability</strong> — write to the contact e-mail above.</li>
    <li><strong>Right to object</strong> (Article 21 GDPR): you may object at any time, at the contact
    e-mail, to processing based on our legitimate interest — that is, to the operational and security
    records. We then stop unless we demonstrate compelling legitimate grounds to continue.</li>
    <li>You may lodge a <strong>complaint</strong> with the Czech Office for Personal Data Protection
    (Úřad pro ochranu osobních údajů), Pplk. Sochora 27, 170 00 Prague 7
    (<a href="https://uoou.gov.cz">uoou.gov.cz</a>), or with the supervisory authority of your country.</li>
  </ul>
  <p>We answer a request within one month at the latest; in complex cases this may be extended by two
  further months, and we will tell you so.</p>

  <h2>Security incidents</h2>
  <p>If a personal data breach occurred, we would notify the Office for Personal Data Protection within
  72 hours of finding out, where it is likely to result in a risk to you. Where it is likely to result in a
  high risk to you, we would also inform you without undue delay. We have a written procedure for this.</p>

  <h2>Changes to this policy</h2>
  <p>We may update this policy; we announce a substantial change in the app or by e-mail at least 30 days
  in advance. Earlier versions are available on request.</p>

  <h2>Related documents</h2>
  <p><a href="terms.html">Terms of service</a> · <a href="zasady.html">Zásady zpracování údajů (Czech)</a>
  · <a href="zpracovatelska-smlouva.html">Data processing agreement (Czech)</a></p>

  <p><a href="index.html">Back to the app</a></p>
</body>
</html>
"""


def _play_predplatne_en(manifest: dict) -> str:
    if not _play(manifest):
        return ""
    return """  <p><strong>Subscription in the app from Google Play.</strong> In the app installed from Google Play the
  subscription is bought only through Google Play: Google takes and processes the payment under the Google
  Play terms; the price in the customer's currency and with the taxes of their country, the length of the
  period and the automatic renewal are shown in the offer before buying. The subscription
  <strong>renews automatically</strong> for another period until the customer cancels it; it can be
  cancelled at any time in Google Play (Payments &amp; subscriptions → Subscriptions) and the paid period
  runs to its end. The paid period applies equally in the app and on the web. A price change of a Google Play
  subscription follows the Google Play rules, which tell the customer in advance. <strong>Deleting the
  account does not cancel the Google Play subscription</strong> — the app therefore does not allow deleting
  the account while the subscription still renews; cancel it in Google Play first.</p>
"""


def _play_odstoupeni_en(manifest: dict) -> str:
    if not _play(manifest):
        return ""
    return """  <p><strong>Subscription bought through Google Play:</strong> a purchase through Google Play does not ask
  for the consent under Section 1837(l), so the right of withdrawal applies in full. Just write to us at
  the contact address; we refund the whole amount paid, through Google Play. It helps if you include the
  order number from Google Play's receipt (it starts with “GPA.”) — we find the purchase by it.</p>
"""


def vykresli_terms(manifest: dict) -> str | None:
    if not _anglicky():
        return None
    produkt = _produkt(manifest)
    zkusebni = manifest.get("zkusebni_dni") or 30
    return f"""{_hlava_en(f"Terms of service — {produkt}", aplikace=_play(manifest))}
  <h1>Terms of service of {_esc(produkt)}</h1>
{_meta_en(manifest, "podminky.html")}

  <p>Provider: {_identita_en(manifest, plna=True)}.</p>

  <h2>1. What the service is and who it is for</h2>
  <p><strong>{_esc(produkt)}</strong> is a web application provided remotely (software as a service). The
  customer uses it in their browser, installs nothing, and the data kept in the service remain theirs.</p>
  <p>An ordinary up-to-date browser (Chrome, Firefox, Safari, Edge) with JavaScript and cookies enabled and
  an internet connection are all that is needed. The customer bears the cost of the connection at their
  operator's rates — the provider charges nothing for the use of means of distance communication.</p>
  <p>The service may be used by businesses and consumers. A <strong>consumer</strong> is a person who
  concludes the contract outside their business. Provisions marked “for consumers” apply only to them.</p>

  <h2>2. Conclusion of the contract and the account</h2>
  <p>The contract is concluded by creating an account (signing in with a one-time e-mailed link) and lasts
  until the customer deletes the account or either party ends it under article 9. It is concluded for an
  indefinite period; the contract is in Czech and this English text is its translation; the provider
  archives it electronically.</p>
  <p>The sign-in link delivered by e-mail is the key to the account. The customer therefore takes care that
  no unauthorised person has access to their mailbox and tells us without delay of any suspected misuse. They
  are not liable for consequences they did not cause and could not reasonably prevent.</p>

  <h2>3. Free trial, price and subscription</h2>
  <p>After the account is created the service is free for <strong>{_esc(zkusebni)} days</strong>. Nothing
  is charged automatically when the trial ends — further use requires the customer to actively order or buy
  a subscription.</p>
  <p>The current price list is shown in the app before ordering. Prices ordered on the web are
  {_cena_dph_en(manifest)} and are final — no further fees are charged.</p>
  <p{_objednavka(manifest)}><strong>Subscription ordered on the web.</strong> The order button is labelled with words meaning
  “order with an obligation to pay” and before pressing it the customer sees the scope, length and total
  price of the subscription. The subscription is paid on the basis of an invoice issued by the provider,
  due as stated on the invoice, and covers the period ordered. <strong>It does not renew by
  itself</strong> — the customer orders the next period again. If they order it before the paid period (or the
  free trial) ends, the service keeps running until the invoice is due; paying extends the subscription. The
  paid period is shown in the app with the account.</p>
{_play_predplatne_en(manifest)}  <p>A price change does not affect a period already paid; the new price applies to periods ordered or
  renewed after it takes effect. We announce a price increase in the app or by e-mail at least 30 days in
  advance, and a customer who disagrees may end the contract before it takes effect without any penalty.</p>
  <p>If the subscription is not paid, the account switches to a limited mode when the paid period ends: the
  customer can sign in, see their data, download it and delete the account, but cannot add new records. Data
  is not deleted in limited mode.</p>

  <h2>4. Withdrawal within 14 days (for consumers)</h2>
  <div class="spotrebitel">
  <p>A consumer may withdraw from the contract <strong>within 14 days of its conclusion</strong>, without
  giving a reason and without any penalty (Section 1829 of the Czech Civil Code).</p>
  <p>Withdrawal can be made by any unequivocal statement — by e-mail to the contact address above, or using
  the model withdrawal form below. We confirm receipt of the withdrawal in text form without undue delay.</p>
  <p>If a consumer withdraws, we refund all payments received within 14 days, by the same means of payment
  unless agreed otherwise.</p>
  <p><strong>When the right of withdrawal ends:</strong> for a digital service provided for payment, the
  right ends if performance began with the consumer's prior express consent given before the 14-day period
  ended and the consumer was informed that they thereby lose the right of withdrawal (Section 1837(l) of the
  Civil Code). We ask for this consent and information with a separate tick box when the subscription is
  ordered and confirm it to the consumer in text form. Without that consent we start providing the paid
  service only after the 14-day period.</p>
  <p>The free trial is not a contract for payment and the consumer has no payment obligation from it; the
  account can be deleted at any time.</p>
{_play_odstoupeni_en(manifest)}  <p><strong>Model withdrawal form</strong> (complete and return it only if you wish to withdraw):<br>
  To: {_esc(_provozovatel(manifest))}, {_s(manifest, 'sidlo', 'doplnit sídlo')}, e-mail {_kontakt_html(manifest)}<br>
  I hereby give notice that I withdraw from my contract for the provision of the digital service
  {_esc(produkt)}. Ordered on / received on: … · Name of consumer: … · Address of consumer: … ·
  E-mail of the account: … · Date: …</p>
  </div>

  <h2>5. Availability, support and defects</h2>
  <p>The provider runs the service with professional care and throughout the contract ensures that it is fit
  for its usual purpose, has the usual characteristics and matches the description in these terms. It
  provides the updates needed to keep the service working and secure.</p>
  <p>Planned downtime is announced in advance where possible. Support is by e-mail at the address above, on
  working days.</p>
  <div class="spotrebitel">
  <p><strong>For consumers:</strong> if the digital service has a defect, the consumer has the rights under
  Section 2389a et seq. of the Civil Code — in particular to have the defect remedied within a reasonable
  time, to a reasonable price reduction and, for a material defect, to withdraw from the contract. These
  rights cannot be limited or excluded in advance and nothing in these terms about availability or limitation
  of liability affects them. It is enough to report the defect by e-mail.</p>
  </div>
  <p>For business customers the provider does not guarantee uninterrupted availability unless agreed
  otherwise.</p>

  <h2>6. Customer data, export and portability</h2>
  <p>Data the customer puts into the service is theirs. The provider processes it only to run the service,
  under the <a href="privacy.html">privacy policy</a> and, where the customer is the controller of other
  people's personal data, under the <a href="zpracovatelska-smlouva.html">data processing agreement</a>
  (in Czech), which forms part of these terms.</p>
  <p>The customer can download a complete export of their data in a structured, commonly used,
  machine-readable format (JSON) in the app at any time and free of charge, and delete the account with its
  data. The export covers all records the customer entered and their account details; it does not include
  the provider's internal technical data (such as operational logs) or data protected as the provider's
  trade secret.</p>
  <p><strong>Switching to another provider.</strong> If the customer decides to move to another service,
  the provider gives reasonable assistance: the export described above, and the data stays available for
  download for <strong>at least 30 days</strong> after notice is given (transition period). The provider
  charges nothing for the export and the assistance. After the transition period and the completed switch
  the provider deletes the data. These rules follow Regulation (EU) 2023/2854 (Data Act) on switching
  between data processing services.</p>

  <h2>7. Customer's obligations</h2>
  <p>The customer uses the service lawfully, does not put into it content they have no right to, and does
  not try to circumvent its security or load it beyond normal use. The customer is responsible for the
  content they put into the service; where it includes other people's personal data, they are responsible
  for having a legal basis for it.</p>

  <h2>8. Liability</h2>
  <p>The provider is liable for damage caused by breaching these terms. It is not liable for damage caused
  by the customer's incorrect use of the service or for circumstances excluding liability under Section
  2913(2) of the Civil Code.</p>
  <p><strong>For business customers</strong> compensation is limited to the amount the customer paid for
  the service in the last 12 months and lost profit is not compensated. The limit does not apply to damage
  caused intentionally or by gross negligence.</p>
  <div class="spotrebitel">
  <p><strong>For consumers</strong> the limitation in the previous paragraph <strong>does not
  apply</strong>. A consumer is compensated in full under the law; the consumer's rights for defective
  performance and to compensation are not limited in any way (Section 1814 of the Civil Code).</p>
  </div>

  <h2>9. Ending the contract</h2>
  <p>The customer may end the contract at any time without penalty by deleting the account in the app.
  Deletion is irreversible: before it completes, the app offers to download the data and asks for
  confirmation. After deletion the data is removed from the live database immediately and from secured
  backups within 30 days, when the backups are overwritten.</p>
  <p>The provider may terminate the contract with 30 days' notice given by e-mail; the notice period never
  exceeds 2 months and is followed by the transition period under article 6. Prepaid subscription for the
  unused period is then refunded pro rata.</p>
  <p>The provider may end the contract with immediate effect only for a material breach of these terms by
  the customer, in particular putting unlawful content into the service, attacking its security, misusing it
  to send unsolicited messages or loading it beyond normal use. Unless the nature of the breach rules it out,
  the provider first asks the customer to remedy it within a reasonable time. Even on immediate termination
  the customer can download their data for 30 days.</p>
  <p>If the provider discontinues the service as a whole, it announces this at least 60 days in advance,
  allows the data to be downloaded and refunds the pro-rata part of the subscription.</p>

  <h2>10. Changes to the terms</h2>
  <p>As this service is provided in the ordinary course of business to a larger number of customers, the
  provider reserves the right under Section 1752 of the Civil Code to change these terms to a reasonable
  extent — in particular when the law, the scope of the service or the technical conditions of operation
  change.</p>
  <p>The provider announces a change in the app and by e-mail at least 30 days before it takes effect,
  together with what changes and the right to reject it. A customer who disagrees may end the contract before
  the change takes effect without penalty; the provider refunds the pro-rata part of the prepaid
  subscription. A change that would worsen the customer's position and that the customer rejects does not
  apply to them until the end of the paid period.</p>

  <h2>11. Out-of-court dispute resolution and supervision (for consumers)</h2>
  <div class="spotrebitel">
  <p>A consumer has the right to out-of-court resolution of a consumer dispute. The competent body is the
  <strong>Czech Trade Inspection Authority</strong> (Česká obchodní inspekce), Central Inspectorate — ADR
  Department, Gorazdova 1969/24, 120 00 Prague 2, <a href="https://adr.coi.gov.cz">adr.coi.gov.cz</a>,
  e-mail adr@coi.gov.cz (Sections 14 and 20d et seq. of Act No. 634/1992 Coll., on Consumer Protection).</p>
  <p>The proposal can be filed within 1 year of the day the consumer first raised the claim with the
  provider. The procedure is free of charge for the consumer.</p>
  <p>Compliance with consumer protection law is supervised by the Czech Trade Inspection Authority
  (<a href="https://coi.gov.cz">coi.gov.cz</a>), data protection by the Office for Personal Data Protection
  (<a href="https://uoou.gov.cz">uoou.gov.cz</a>).</p>
  </div>

  <h2>12. Final provisions</h2>
  <p>The contract is governed by Czech law. If the customer is a business, disputes belong to the courts of
  the provider's registered office. If the customer is a consumer, jurisdiction follows the general rules and
  the consumer may be sued only in the courts of their residence; the choice of law does not deprive the
  consumer of the protection given by the mandatory rules of the country of their habitual residence.</p>
  <p>If any provision of these terms is invalid or unenforceable, the other provisions remain in force.</p>

  <p><a href="index.html">Back to the app</a> ·
  <a href="privacy.html">Privacy policy</a> ·
  <a href="podminky.html">Obchodní podmínky (Czech)</a> ·
  <a href="smazani-uctu.html">Deleting your account</a></p>
</body>
</html>
"""


VYSTUPY = (
    (ZASADY, vykresli_zasady),
    (PODMINKY, vykresli_podminky),
    (DPA, vykresli_dpa),
    (ODSTOUPENI, vykresli_odstoupeni),
    (SMAZANI, vykresli_smazani),
    # None for a product that does not speak English: nothing is written
    # and the checker expects nothing (kontrola_manifestu._zkontroluj_zasady).
    (PRIVACY, vykresli_privacy),
    (TERMS, vykresli_terms),
    # None without the Play module (no paragraph to hide, nothing to load).
    (PODMINKY_JS, vykresli_podminky_js),
    (ZAZNAM, vykresli_zaznam),
    (POSTUP, vykresli_postup),
)


def main() -> int:
    if not MANIFEST.exists():
        print("CHYBA: chybí data-manifest.json.")
        return 1
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    WEB.mkdir(parents=True, exist_ok=True)
    hotovo = []
    for path, render in VYSTUPY:
        text = render(manifest)
        if text is None:
            continue
        path.write_text(text, encoding="utf-8", newline="\n")
        hotovo.append(str(path))
    print("Vygenerováno: " + ", ".join(hotovo) + ".")
    return 0


if __name__ == "__main__":
    sys.exit(main())
