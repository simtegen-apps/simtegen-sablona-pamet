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
ZAZNAM = Path("ZAZNAM_O_ZPRACOVANI.md")
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
}


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
    return manifest.get("provozovatel") or "SimteGen s.r.o."


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


def _hlava(title: str) -> str:
    return f"""<!doctype html>
<!-- {_HLAVICKA} -->
<html lang="cs">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{_esc(title)}</title>
  <style>
{_STYL}
  </style>
</head>
<body>"""


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

  <h2>Vaše práva</h2>
  <ul>
    <li><strong>Přístup k údajům a jejich výpis</strong> si kdykoli stáhnete přímo v aplikaci
    (Účet → Stáhnout moje data).</li>
    <li><strong>Smazání účtu a všech údajů</strong> provedete přímo v aplikaci
    (Účet → Smazat účet). Z provozní databáze se údaje smažou okamžitě, ze zabezpečených
    záloh nejpozději do 30 dnů, kdy se zálohy přepíší. Déle uchováváme jen účetní
    a daňové doklady, kde nám to ukládá zákon.</li>
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

def vykresli_podminky(manifest: dict) -> str:
    produkt = _produkt(manifest)
    zkusebni = manifest.get("zkusebni_dni") or 30
    return f"""{_hlava(f"Obchodní podmínky — {produkt}")}
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
  zkušebního období se nic automaticky neúčtuje a předplatné se samo neobnovuje —
  další užívání je podmíněno tím, že si zákazník předplatné aktivně objedná.</p>
  <p>Aktuální ceník je dostupný v aplikaci před objednáním. Uvedené ceny
  jsou {_s(manifest, 'cena_dph', 'doplnit: „včetně DPH“ / „bez DPH, poskytovatel není plátcem DPH“')}
  a jsou konečné — žádné další poplatky se neúčtují. Objednávkové tlačítko je označeno
  slovy „Objednávka zavazující k platbě“ a před jeho stisknutím zákazník vidí rozsah,
  délku a celkovou cenu předplatného.</p>
  <p>Předplatné se hradí na základě faktury (daňového dokladu) vystavené poskytovatelem,
  se splatností uvedenou na faktuře. Zaplacené období se v aplikaci zobrazuje u účtu.</p>
  <p>Změnu ceny oznámíme v aplikaci nebo e-mailem nejméně 30 dní předem; nová cena platí
  až od dalšího předplaceného období. Zákazník, který se změnou nesouhlasí, může smlouvu
  do účinnosti změny ukončit bez jakékoli sankce.</p>
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
  </div>

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


VYSTUPY = (
    (ZASADY, vykresli_zasady),
    (PODMINKY, vykresli_podminky),
    (DPA, vykresli_dpa),
    (ODSTOUPENI, vykresli_odstoupeni),
    (ZAZNAM, vykresli_zaznam),
    (POSTUP, vykresli_postup),
)


def main() -> int:
    if not MANIFEST.exists():
        print("CHYBA: chybí data-manifest.json.")
        return 1
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    WEB.mkdir(parents=True, exist_ok=True)
    for path, render in VYSTUPY:
        path.write_text(render(manifest), encoding="utf-8", newline="\n")
    print("Vygenerováno: " + ", ".join(str(p) for p, _ in VYSTUPY) + ".")
    return 0


if __name__ == "__main__":
    sys.exit(main())
