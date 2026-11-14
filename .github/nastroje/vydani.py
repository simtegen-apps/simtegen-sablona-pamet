"""Android release of one product — run by the Vydani workflow.

Two steps, both deterministic, no model anywhere:

  priprav   reads the product's LIVE web manifest (the production site is
            the single source of truth: name, colours, icons and the Play
            package in related_applications — all written by
            vykresli_aplikaci.py and deployed by the product's own CI) and
            writes twa-manifest.json for Bubblewrap, with a version code
            that only ever grows.
  nahraj    uploads the signed bundle to Google Play through the Android
            Publisher API, INTERNAL track only.
  povys     promotes that same version code to PRODUCTION — in a job of its
            own, with a service account of its own that holds nothing but
            the production permission, and without the upload key: it can
            only move a bundle this pipeline built, never bring a new one.
            Only when the app is already in production (the first
            production release stays the owner's tap in Play Console), the
            domain is the one the product's repo declares, and the app's
            shell changed (otisk_obalu) — a change of the website alone is
            in the app the moment it deploys, no store release needed.

Why the live site and not the product repo: the template repo's token
cannot read product repos, and the thing Android verifies at run time
(manifest + assetlinks.json) is the deployed site anyway. If the site does
not declare the app, there is nothing to release.

Google specifics worth knowing before touching this:
  - The very first bundle of a new app must be uploaded by hand in Play
    Console (the API answers 404 for a package it has never seen). The
    workflow keeps the bundle as an artifact exactly for that.
  - An app that has never been published accepts only DRAFT releases over
    the API; `nahraj` retries as a draft and says so.

Selling in the app (etapa 5, bod 5): a product with /api/play gets Play
Billing in its build (Digital Goods API inside the TWA), its subscription
products in Play created from the price the owner approved (`PREDPLATNE`
from SimteGen), and the order-only service account as a Pages secret, so
the product can verify and acknowledge purchases itself.
"""

from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

VYSTUP = Path("vydani")
_EPOCHA = datetime(2024, 1, 1, tzinfo=timezone.utc)
# The English listing's language as Google Play names it (vykresli_aplikaci.JAZYK_EN).
JAZYK_EN_PLAY = "en-US"
# "What's new" for English customers. Fixed, never from the inputs: the note
# SimteGen sends is Czech, a translation would need a model, and the
# production job accepts exactly this text besides the hashed Czech one — so
# the internal key cannot smuggle words into production through it.
POZNAMKA_EN = "A new version of the app."


def verze(ted: datetime | None = None) -> tuple[int, str]:
    """(versionCode, versionName). Minutes since 2024 — monotonic across
    re-runs and workflow renames, far below Play's 2 100 000 000 ceiling
    for the next four thousand years."""
    ted = ted or datetime.now(timezone.utc)
    kod = int((ted - _EPOCHA).total_seconds() // 60)
    return kod, ted.strftime("%Y.%m.%d.%H%M")


def balicek_z_manifestu(manifest: dict) -> str:
    for aplikace in manifest.get("related_applications") or []:
        if aplikace.get("platform") == "play" and aplikace.get("id"):
            return str(aplikace["id"])
    raise SystemExit("Web manifest nedeklaruje aplikaci v Google Play (related_applications). "
                     "Produkt nemá zapnutý modul aplikace, nebo ještě není nasazený.")


def start_aplikace(start_url: str | None) -> str:
    """The app's launch address carries ?aplikace=play: inside the app
    from Google Play the invoice order must never show (Payments policy),
    and the page recognises the app reliably only at launch — web/play.js
    remembers it from this mark (and from android-app:// as referrer)."""
    zaklad = start_url or "/"
    return zaklad + ("&" if "?" in zaklad else "?") + "aplikace=play"


def twa_manifest(manifest: dict, host: str, ted: datetime | None = None, nakupy: bool = False) -> dict:
    """Bubblewrap's project description, from the live web manifest.
    `nakupy`: the product sells its subscription in the app — Play Billing
    (Bubblewrap keeps it behind alphaDependencies)."""
    kod, nazev_verze = verze(ted)
    ikony = {i.get("purpose", "any"): i["src"] for i in manifest.get("icons") or []
             if i.get("sizes") == "512x512"}
    if "any" not in ikony:
        raise SystemExit("Web manifest nemá ikonu 512×512 — spusť v produktu vykresli_aplikaci.py.")
    zaklad = f"https://{host}"
    barva = manifest.get("theme_color") or "#10504b"
    twa = {
        "packageId": balicek_z_manifestu(manifest),
        "host": host,
        "name": manifest.get("name") or host,
        "launcherName": manifest.get("short_name") or manifest.get("name") or host,
        "display": "standalone",
        "orientation": manifest.get("orientation") or "portrait",
        "themeColor": barva,
        "themeColorDark": barva,
        "navigationColor": barva,
        "navigationColorDark": barva,
        "navigationDividerColor": barva,
        "navigationDividerColorDark": barva,
        "backgroundColor": manifest.get("background_color") or "#ffffff",
        # Bubblewrap refuses Play Billing without notification delegation
        # ("Play Billing requires enableNotifications to be true") — five
        # release runs failed on exactly this (19.–21. 10. 2026). The app
        # itself still sends no notification; this only lets Chrome do it.
        "enableNotifications": nakupy,
        "startUrl": start_aplikace(manifest.get("start_url")),
        "iconUrl": zaklad + ikony["any"],
        "maskableIconUrl": zaklad + ikony["maskable"] if "maskable" in ikony else None,
        "splashScreenFadeOutDuration": 300,
        "signingKey": {"path": "./upload.keystore", "alias": "upload"},
        "appVersionName": nazev_verze,
        "appVersionCode": kod,
        "appVersion": nazev_verze,
        "shortcuts": [],
        "generatorApp": "bubblewrap-cli",
        "webManifestUrl": f"{zaklad}/manifest.webmanifest",
        "fallbackType": "customtabs",
        "features": {"playBilling": {"enabled": True}} if nakupy else {},
        "alphaDependencies": {"enabled": nakupy},
        "enableSiteSettingsShortcut": True,
        "isChromeOSOnly": False,
        "isMetaQuest": False,
        "fullScopeUrl": f"{zaklad}/",
        # android-browser-helper 2.7.4 (Bubblewrap pulls the newest) declares
        # minSdk 24; Bubblewrap still writes 21 and the manifest merger fails
        # the build. Android 7 and older are well under 1 % of devices.
        "minSdkVersion": 24,
        "fingerprints": [],
        "additionalTrustedOrigins": [],
        "retainedBundles": [],
    }
    # Bubblewrap reads a missing key as "not set"; a null is a value it trips on.
    return {k: v for k, v in twa.items() if v is not None}


def _stahni_manifest(host: str) -> dict:
    pozadavek = urllib.request.Request(f"https://{host}/manifest.webmanifest",
                                       headers={"User-Agent": "simtegen-vydani"})
    try:
        with urllib.request.urlopen(pozadavek, timeout=30) as odpoved:
            return json.loads(odpoved.read().decode("utf-8"))
    except Exception as e:  # noqa: BLE001 — any failure means the same thing here
        raise SystemExit(f"Web manifest z https://{host}/manifest.webmanifest nejde načíst ({e}). "
                         "Je produkt nasazený a má zapnutý modul aplikace?")


def nakupy_v_produktu(host: str) -> bool:
    """Does the deployed product sell in the app? /api/play answers a
    stranger 401 (or 200) when it exists, 404 when it does not."""
    pozadavek = urllib.request.Request(f"https://{host}/api/play", headers={"User-Agent": "simtegen-vydani"})
    try:
        with urllib.request.urlopen(pozadavek, timeout=30) as odpoved:
            return odpoved.status == 200
    except urllib.error.HTTPError as e:
        return e.code == 401
    except Exception:  # noqa: BLE001 — unreachable means "not known to sell"
        return False


def balicek_z_repa(projekt: str, vlastnik: str) -> str | None:
    """The package the product's own repo declares (data-manifest.json on
    main; product repos are public). None when it cannot be read — a
    network hiccup must not stop a release the check exists only to guard."""
    adresa = f"https://raw.githubusercontent.com/{vlastnik}/{projekt}/main/data-manifest.json"
    try:
        with urllib.request.urlopen(urllib.request.Request(adresa, headers={"User-Agent": "simtegen-vydani"}),
                                    timeout=30) as odpoved:
            manifest = json.loads(odpoved.read().decode("utf-8"))
    except Exception:  # noqa: BLE001
        return None
    balicek = (manifest.get("aplikace") or {}).get("balicek") if isinstance(manifest, dict) else None
    return str(balicek) if balicek else None


def priprav(projekt: str, domena: str = "") -> dict:
    host = domena.strip() or f"{projekt}.pages.dev"
    nakupy = nakupy_v_produktu(host)
    twa = twa_manifest(_stahni_manifest(host), host, nakupy=nakupy)
    # The app is built from the domain, its listing, release note and Data
    # safety form from the repo. A hand run with one product's repo and
    # another's domain (11. 11. 2026: Pneusklad's repo, kusovnik.simtegen.com)
    # sent Pneusklad's declarations to Kusovník's store entry.
    if not _BALICEK.fullmatch(twa["packageId"] or ""):
        # It goes to GITHUB_OUTPUT and from there to the production job.
        raise SystemExit(f"Web manifest na {host} uvádí neplatný balíček aplikace.")
    z_repa = balicek_z_repa(projekt, os.environ.get("GITHUB_REPOSITORY_OWNER") or "simtegen-apps")
    if z_repa and z_repa != twa["packageId"]:
        raise SystemExit(f"Repo {projekt} patří k aplikaci {z_repa}, ale doména {host} k {twa['packageId']}. "
                         "Zkontroluj pole „Název repa produktu“ a „Vlastní doména“ — musí být téhož produktu.")
    VYSTUP.mkdir(exist_ok=True)
    (VYSTUP / "twa-manifest.json").write_text(json.dumps(twa, ensure_ascii=False, indent=2), encoding="utf-8")
    vystup = os.environ.get("GITHUB_OUTPUT")
    if vystup:
        with open(vystup, "a", encoding="utf-8") as f:
            f.write(f"balicek={twa['packageId']}\nverze={twa['appVersionName']}\nkod={twa['appVersionCode']}\n"
                    f"nakupy={'1' if nakupy else '0'}\n")
    print(f"Připraveno: {twa['packageId']} {twa['appVersionName']} (kód {twa['appVersionCode']}) z https://{host}")
    return twa


# ── Upload ────────────────────────────────────────────────────────────

_API = "https://androidpublisher.googleapis.com/androidpublisher/v3/applications"
_UPLOAD = "https://androidpublisher.googleapis.com/upload/androidpublisher/v3/applications"


# Play Console permission each part of a release needs, as the owner sees it
# there. Google answers a missing one with a bare "The caller does not have
# permission" — often only at the commit — so the hint names it. Kusovník and
# Pneusklad both stopped on that for a day (9. 11. 2026) and nobody could tell
# which permission it was.
PRAVO_VYDANI = "Uvolňovat aplikace do testovacích kanálů (Release apps to testing tracks)"
PRAVO_ZAZNAM = "Spravovat prezentaci v obchodě (Manage store presence)"
PRAVO_PREDPLATNE = "Spravovat produkty a předplatná v obchodě (Manage store products and subscriptions)"
# An app never released to production is a draft ("Koncept aplikace") — an
# internal track does not change that — and on a draft Google refuses the
# listing's contacts and images and the subscription's price conversion
# without this one, while texts and releases pass. Pneusklad, 12. 11. 2026:
# every other permission was there; ticking this made all of it go through.
PRAVO_KONCEPTY = "Vytváření, úpravy a mazání konceptů aplikací (Edit and delete draft apps)"


def duvod_googlu(text: str) -> str:
    """Google's refusal on one line: status, message and the reasons from the
    details. Raw, its JSON starts with a lone "{" — and a ::warning:: shows
    only the first line, which GitHub also masks as *** (a line of the
    service-account secret is a lone "{" too). Every refusal of 12. 11. 2026
    read "selhalo (403): ***" and said nothing."""
    try:
        chyba = json.loads(text).get("error") or {}
    except (ValueError, AttributeError):
        chyba = {}
    if isinstance(chyba, dict) and chyba:
        casti = [str(chyba.get("status") or ""), str(chyba.get("message") or "")]
        for d in (chyba.get("errors") or []) + (chyba.get("details") or []):
            if isinstance(d, dict):
                casti.append(str(d.get("reason") or d.get("@type", "").rsplit(".", 1)[-1] or ""))
                casti.append(str(d.get("message") or d.get("detail") or ""))
        vysledek = []
        for c in casti:
            if c and c not in vysledek:
                vysledek.append(c)
        return " | ".join(vysledek)[:500]
    return " ".join(text.split())[:500]


def jeden_radek(chyba) -> str:
    """A message for ::warning::, which keeps only its first line."""
    return " — ".join(r.strip() for r in str(chyba).splitlines() if r.strip())


def _ok(odpoved, co, pravo: str | None = None, ucet: str = "PLAY_SERVICE_ACCOUNT_JSON"):
    """`ucet`: the secret whose account was refused — the hint must never
    send the owner to give production rights to the internal account."""
    if odpoved.status_code >= 300:
        zprava = f"Google Play: {co} selhalo ({odpoved.status_code}): {duvod_googlu(odpoved.text)}"
        if pravo and odpoved.status_code in (401, 403):
            zprava += (f"\nServisnímu účtu ({ucet}) nejspíš chybí oprávnění „{pravo}“: "
                       "Play Console → Uživatelé a oprávnění → servisní účet → Oprávnění k účtu "
                       "(nebo Oprávnění aplikace u této aplikace). Změna se může projevit až za několik hodin.")
            if pravo in (PRAVO_ZAZNAM, PRAVO_PREDPLATNE):
                zprava += (f"\nJe aplikace ještě koncept (nikdy v produkci)? Pak k tomu potřebuje i „{PRAVO_KONCEPTY}“ "
                           "— bez něj Google odmítne kontakty, obrázky i předplatné, i když texty projdou.")
        raise SystemExit(zprava)
    return odpoved.json() if odpoved.text else {}


def _obrazky_zaznamu(obchod: Path, ikona: Path | None = None) -> list[tuple[str, list[Path]]]:
    # One set of tablet pictures serves both of Google's tablet sizes; without
    # any, Play hardly offers the app on tablets. `ikona`: a translation's
    # folder has no icon of its own — the app's icon speaks no language.
    tablety = sorted(obchod.glob("tablet-*.jpg"))
    obrazky = (("phoneScreenshots", sorted(obchod.glob("telefon-*.jpg"))),
               ("sevenInchScreenshots", tablety),
               ("tenInchScreenshots", tablety),
               ("featureGraphic", [obchod / "grafika.jpg"]),
               ("icon", [ikona or obchod / "ikona.png"]))
    return [(typ, [s for s in soubory if s.exists()]) for typ, soubory in obrazky
            if any(s.exists() for s in soubory)]


def casti_zaznamu(obchod: Path) -> list[str]:
    """The parts of a listing that can go in an edit on their own."""
    return ["texty", "kontakty", *(typ for typ, _ in _obrazky_zaznamu(obchod))]


def jazyky_zaznamu(obchod: Path, zaznam: dict) -> list[tuple[str, dict, Path]]:
    """(language, texts, folder of its pictures) for every listing: Czech
    from the top of zaznam.json and obchod/, each translation from
    `preklady` and obchod/<language>/ (vizualni_kontrola.py --obchod)."""
    jazyky = [(zaznam.get("jazyk") or "cs-CZ", zaznam, obchod)]
    for jazyk, texty in (zaznam.get("preklady") or {}).items():
        if isinstance(texty, dict) and str(texty.get("nazev") or "").strip() and re.fullmatch(r"[a-z]{2}-[A-Z]{2}", jazyk):
            jazyky.append((jazyk, texty, obchod / jazyk))
    return jazyky


def _cti(session, url: str) -> dict | None:
    """What Play holds now, or None when it holds nothing (or will not say):
    unknown means "upload", never "skip"."""
    odpoved = session.get(url)
    if odpoved.status_code != 200:
        return None
    try:
        data = odpoved.json()
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def nahraj_zaznam(session, balicek: str, edit: str, obchod: Path, host: str,
                  casti: set[str] | None = None, obrazky: bool = True) -> list[str]:
    """The store listing into an edit: texts from the product's
    play/zaznam.json (generated from its manifest — the same claims as its
    privacy policy), contacts, and the images the release rendered from the
    product (vizualni_kontrola.py --obchod) — in Czech and in every
    translation, the store's default language as zaznam.json says (English
    for a product that speaks it). `casti` limits it to those parts
    (casti_zaznamu). Returns what was uploaded, for the summary.

    Only what changed goes up: every listing change of a live app goes to
    Google review, and a release follows every deploy. Texts and contacts
    are compared with what Play holds. Pictures are replaced wholesale (a
    removed screen must not linger) when `obrazky` — the product's screens
    changed since the last upload (otisk_zdroju) — and otherwise only where
    Play has none (a new language, a failed earlier upload)."""
    zaznam = json.loads((obchod / "zaznam.json").read_text(encoding="utf-8"))
    zaklad = f"{_API}/{balicek}/edits/{edit}"
    jazyky = jazyky_zaznamu(obchod, zaznam)
    nahrano = []
    if casti is None or "texty" in casti:
        for jazyk, texty, _ in jazyky:
            chci = {"title": texty["nazev"], "shortDescription": texty["kratky_popis"],
                    "fullDescription": texty["dlouhy_popis"]}
            ted = _cti(session, f"{zaklad}/listings/{jazyk}") or {}
            if all(ted.get(k) == v for k, v in chci.items()):
                continue
            _ok(session.put(f"{zaklad}/listings/{jazyk}", json={"language": jazyk, **chci}),
                f"záznam v obchodě ({jazyk})", PRAVO_ZAZNAM)
            nahrano.append(f"texty {jazyk}")
    if casti is None or "kontakty" in casti:
        chci = {"defaultLanguage": zaznam.get("vychozi") or jazyky[0][0],
                "contactEmail": zaznam["kontakt_email"], "contactWebsite": f"https://{host}"}
        ted = _cti(session, f"{zaklad}/details") or {}
        if not all(ted.get(k) == v for k, v in chci.items()):
            _ok(session.patch(f"{zaklad}/details", json=chci), "kontakty v obchodě", PRAVO_ZAZNAM)
            nahrano.append("kontakty")
    for jazyk, _, slozka in jazyky:
        for typ, soubory in _obrazky_zaznamu(slozka, obchod / "ikona.png"):
            if casti is not None and typ not in casti:
                continue
            if not obrazky and (_cti(session, f"{zaklad}/listings/{jazyk}/{typ}") or {}).get("images"):
                continue
            _ok(session.delete(f"{zaklad}/listings/{jazyk}/{typ}"), f"smazání starých obrázků {typ}",
                PRAVO_ZAZNAM)
            for soubor in soubory:
                _ok(session.post(f"{_UPLOAD}/{balicek}/edits/{edit}/listings/{jazyk}/{typ}?uploadType=media",
                                 data=soubor.read_bytes(),
                                 headers={"Content-Type": "image/png" if soubor.suffix == ".png" else "image/jpeg"}),
                    f"nahrání {soubor.name}", PRAVO_ZAZNAM)
            nahrano.append(f"{typ} ×{len(soubory)}" if jazyk == jazyky[0][0] else f"{jazyk} {typ} ×{len(soubory)}")
    return nahrano


def nahraj_zaznam_zvlast(session, balicek: str, obchod: Path, host: str, obrazky: bool = True) -> list[str]:
    """The listing in its own edit, after the release is committed. Until
    9. 11. 2026 it rode in the release's edit, and Google refused the whole
    commit with one bare 403 — the owner could not tell whether the release
    or the listing lacked a permission, and the build that was fine had to be
    uploaded by hand. Now a listing Google refuses costs only the listing
    (reported, retried with the next release), and the hint names its
    permission. A refused edit is deleted, so nothing half-done waits in it.

    A 403 at the commit is then split: every part (texts, contacts, each
    kind of image) in an edit of its own. With the permission granted, Google
    still refused the whole listing for two days (10.–11. 11. 2026) with the
    same bare 403, and every call before the commit had passed — the commit
    is the only place Google says no, and it does not say to what. Parts it
    takes land in the store; the message names the ones it refused."""
    try:
        return _zaznam_v_uprave(session, balicek, obchod, host, None, obrazky)
    except SystemExit as e:
        if "potvrzení záznamu v obchodě selhalo (403)" not in str(e):
            raise
        prvni = str(e)
    prijato, odmitnuto = [], []
    for cast in casti_zaznamu(obchod):
        try:
            prijato += _zaznam_v_uprave(session, balicek, obchod, host, {cast}, obrazky)
        except SystemExit as e:
            kde = re.search(r"Google Play: (.+?) selhalo \((\d+)\): ?([^\n]*)", str(e))
            # Google's own words for the first refusal only: the parts are
            # usually refused for the same reason, and the line stays short.
            duvod = kde.group(3).strip() if kde and not odmitnuto else ""
            odmitnuto.append((f"{cast} ({kde.group(1)}, {kde.group(2)}" + (f": {duvod})" if duvod else ")"))
                             if kde else cast)
    if not prijato:
        # 11. 11. 2026: the cause behind two days of this was no default
        # listing at all — the API edits one, it never creates it.
        raise SystemExit(prvni + "\nGoogle odmítl i každou část záznamu zvlášť: " + "; ".join(odmitnuto)
                         + "\nMá aplikace výchozí záznam? Přes API ho Google nezaloží: Play Console → "
                         "Zvýšení počtu uživatelů → Prezentace v Obchodě → Záznamy v obchodě → "
                         "Vytvořit výchozí záznam (texty a obrázky z artefaktu podklady, složka obchod).")
    raise SystemExit("Záznam v obchodě jen zčásti — Google přijal: " + ", ".join(prijato)
                     + "; odmítl: " + "; ".join(odmitnuto))


def _zaznam_v_uprave(session, balicek: str, obchod: Path, host: str, casti: set[str] | None,
                     obrazky: bool = True) -> list[str]:
    edit = _ok(session.post(f"{_API}/{balicek}/edits", json={}), "založení úpravy záznamu", PRAVO_ZAZNAM)["id"]
    try:
        nahrano = nahraj_zaznam(session, balicek, edit, obchod, host, casti, obrazky)
        if not nahrano:
            # Nothing differs from Play: no commit, no review for nothing.
            session.delete(f"{_API}/{balicek}/edits/{edit}")
            return ["beze změny"]
        _ok(session.post(f"{_API}/{balicek}/edits/{edit}:commit"), "potvrzení záznamu v obchodě", PRAVO_ZAZNAM)
    except SystemExit:
        try:
            session.delete(f"{_API}/{balicek}/edits/{edit}")
        except Exception:  # noqa: BLE001 — the edit expires on its own anyway
            pass
        raise
    return nahrano


# ── Data safety ───────────────────────────────────────────────────────
#
# Google takes the whole Data safety form as one CSV in the shape of its own
# export (Play Console → Bezpečnost údajů → Exportovat do CSV), posted to
# applications/{pkg}/dataSafety — outside any edit, overwriting every earlier
# answer. data_safety_sablona.csv next to this file IS that export, empty: the
# question and response IDs come from Google, never from memory, and an ID
# the mapping below names but the template lacks stops the generator instead
# of sending a form Google would half-ignore. When Google changes the form,
# replace the template with a fresh export.
#
# Answers come from zaznam.json (bezpecnost_dat), the same claims the privacy
# policy makes. The CSV rules: TRUE/FALSE; in a choice, TRUE on each chosen
# row and the others left blank; a conditional question blank unless its
# condition holds.

SABLONA_BEZPECNOSTI = Path(__file__).with_name("data_safety_sablona.csv")
PSL_TYPY = {
    "email": "PSL_EMAIL", "jmeno": "PSL_NAME", "adresa": "PSL_ADDRESS", "telefon": "PSL_PHONE",
    "id_uzivatele": "PSL_USER_ACCOUNT", "osobni_jine": "PSL_OTHER_PERSONAL",
    "platebni_udaje": "PSL_CREDIT_DEBIT_BANK_ACCOUNT_NUMBER", "historie_nakupu": "PSL_PURCHASE_HISTORY",
    "financni_jine": "PSL_OTHER", "zpravy": "PSL_OTHER_MESSAGES",
    "obsah_uzivatele": "PSL_USER_GENERATED_CONTENT", "akce_v_aplikaci": "PSL_USER_INTERACTION",
    "hledani": "PSL_IN_APP_SEARCH_HISTORY", "fotky": "PSL_PHOTOS", "soubory": "PSL_FILES_AND_DOCS",
    "kalendar": "PSL_CALENDAR", "kontakty": "PSL_CONTACTS", "poloha_priblizna": "PSL_APPROX_LOCATION",
    "poloha_presna": "PSL_PRECISE_LOCATION", "diagnostika": "PSL_PERFORMANCE_DIAGNOSTICS",
    "pady": "PSL_CRASH_LOGS",
}
# zaznam.json names purposes in Google's English wording (vykresli_aplikaci.PLAY_UCELY).
PSL_UCELY = {
    "App functionality": "PSL_APP_FUNCTIONALITY", "Account management": "PSL_ACCOUNT_MANAGEMENT",
    "Developer communications": "PSL_DEVELOPER_COMMUNICATIONS", "Analytics": "PSL_ANALYTICS",
    "Fraud prevention, security, and compliance": "PSL_FRAUD_PREVENTION_SECURITY",
    "Personalization": "PSL_PERSONALIZATION", "Advertising or marketing": "PSL_ADVERTISING",
}


def bezpecnost_csv(zaznam: dict, host: str, sablona: str | None = None) -> str:
    """The filled-in Data safety CSV for one product. Raises SystemExit
    when the claims don't fit the template (unknown type, purpose, or an ID
    Google dropped) — a wrong declaration is worse than none."""
    import csv
    import io

    b = zaznam["bezpecnost_dat"]
    if b.get("sdili"):
        # Sharing would need the sharing purposes too; SimteGen products
        # only hand data to processors, which Google does not count.
        raise SystemExit("Bezpečnost údajů: sdílení s třetími stranami generátor neumí vyplnit.")
    sablona = sablona if sablona is not None else SABLONA_BEZPECNOSTI.read_text(encoding="utf-8")
    radky = list(csv.reader(io.StringIO(sablona)))
    hlavicka, telo = radky[0], radky[1:]
    znamy = {(r[0], r[1]) for r in telo}
    kategorie = {r[1]: r[0] for r in telo if r[0].startswith("PSL_DATA_TYPES_")}
    odpovedi: dict[tuple[str, str], str] = {}

    def odpovez(otazka: str, moznost: str = "", hodnota: str = "TRUE") -> None:
        if (otazka, moznost) not in znamy:
            raise SystemExit(f"Bezpečnost údajů: šablona od Googlu nezná {otazka} / {moznost or '—'}. "
                             "Exportuj čerstvou šablonu z Play Console.")
        odpovedi[(otazka, moznost)] = hodnota

    adresa = f"https://{host}"
    smazani = adresa + (zaznam.get("smazani_uctu_cesta") or "/zasady.html")
    odpovez("PSL_DATA_COLLECTION_COLLECTS_PERSONAL_DATA", hodnota="TRUE" if b["sbira"] else "FALSE")
    if b["sbira"]:
        odpovez("PSL_DATA_COLLECTION_ENCRYPTED_IN_TRANSIT",
                hodnota="TRUE" if b.get("sifrovano_pri_prenosu") else "FALSE")
    if zaznam.get("ucty"):
        # The e-mail is the user name, the one-time link from it the other
        # authentication — no password exists.
        odpovez("PSL_SUPPORTED_ACCOUNT_CREATION_METHODS", "PSL_ACM_USER_ID_OTHER_AUTH")
        odpovez("PSL_ACCOUNT_DELETION_URL", hodnota=smazani)
    else:
        odpovez("PSL_SUPPORTED_ACCOUNT_CREATION_METHODS", "PSL_ACM_NONE")
    if b["sbira"]:
        odpovez("PSL_SUPPORT_DATA_DELETION_BY_USER",
                "DATA_DELETION_YES" if b.get("lze_smazat") else "DATA_DELETION_NO")
        if b.get("lze_smazat"):
            # The template marks it MAYBE_REQUIRED, but Google refuses the
            # whole form ("Response missing for PSL_DATA_DELETION_URL") once
            # deletion is claimed without it. Same page as the account
            # deletion: it is where the privacy policy's erasure request lives.
            odpovez("PSL_DATA_DELETION_URL", hodnota=smazani)
    for t in b["typy"]:
        psl = PSL_TYPY.get(t["klic"])
        if psl is None or psl not in kategorie:
            raise SystemExit(f"Bezpečnost údajů: typ údajů „{t['klic']}“ nemá v šabloně Googlu protějšek.")
        odpovez(kategorie[psl], psl)
        zaklad = f"PSL_DATA_USAGE_RESPONSES:{psl}"
        odpovez(f"{zaklad}:PSL_DATA_USAGE_COLLECTION_AND_SHARING", "PSL_DATA_USAGE_ONLY_COLLECTED")
        odpovez(f"{zaklad}:PSL_DATA_USAGE_EPHEMERAL", hodnota="FALSE")
        odpovez(f"{zaklad}:DATA_USAGE_USER_CONTROL",
                "PSL_DATA_USAGE_USER_CONTROL_OPTIONAL" if t["volitelne"] else "PSL_DATA_USAGE_USER_CONTROL_REQUIRED")
        if not t["ucely"]:
            raise SystemExit(f"Bezpečnost údajů: typ „{t['klic']}“ nemá účel.")
        for ucel in t["ucely"]:
            if ucel not in PSL_UCELY:
                raise SystemExit(f"Bezpečnost údajů: účel „{ucel}“ nemá v šabloně Googlu protějšek.")
            odpovez(f"{zaklad}:DATA_USAGE_COLLECTION_PURPOSE", PSL_UCELY[ucel])

    vystup = io.StringIO()
    zapis = csv.writer(vystup, lineterminator="\n")
    zapis.writerow(hlavicka)
    for r in telo:
        zapis.writerow([r[0], r[1], odpovedi.get((r[0], r[1]), ""), *r[3:]])
    return vystup.getvalue()


def nahraj_bezpecnost(session, balicek: str, csv_text: str) -> None:
    _ok(session.post(f"{_API}/{balicek}/dataSafety", json={"safetyLabels": csv_text}), "bezpečnost údajů",
        PRAVO_ZAZNAM)


def bezpecnost(adresar: Path = VYSTUP) -> Path | None:
    """obchod/bezpecnost_dat.csv into the artifact: the same file the upload
    sends, so the owner can import it by hand before the app exists in Play
    (Bezpečnost údajů → Importovat z CSV)."""
    zaznam_soubor = adresar / "obchod" / "zaznam.json"
    if not zaznam_soubor.exists():
        return None
    twa = json.loads((adresar / "twa-manifest.json").read_text(encoding="utf-8"))
    zaznam = json.loads(zaznam_soubor.read_text(encoding="utf-8"))
    cil = adresar / "obchod" / "bezpecnost_dat.csv"
    cil.write_text(bezpecnost_csv(zaznam, twa["host"]), encoding="utf-8")
    return cil


# ── Subscription products in Play ─────────────────────────────────────
#
# What the app sells is what the owner approved (cenotvorba): SimteGen
# passes it as PREDPLATNE = [{"id": "predplatne_mesic" | "predplatne_rok",
# "obdobi": "P1M" | "P1Y", "cena_czk": 490}], one base plan each, the same
# price as on the web. The Czech price is exact (tax inclusive, what the
# customer pays); other countries get Google's own conversion of it —
# except where the owner approved a price in their currency too (Jazyky a
# měny): an item may carry "ceny": {"EUR": "4.90", "USD": "5.90"}, and every
# region Google prices in euros or dollars, and "other regions", then sell
# exactly that (tax inclusive, like the Czech one).
# Created and activated if missing, repriced if an approved price moved
# (Google keeps existing subscribers on their price), never deleted.

ZAKLADNI_PLAN = "zakladni"
_DPH = 1.21


def _penize(mena: str, castka: float) -> dict:
    cele = int(castka)
    return {"currencyCode": mena, "units": str(cele), "nanos": int(round((castka - cele) * 1e9))}


def _penize_text(mena: str, castka: str) -> dict:
    """An approved amount ("4.90") as Google's Money, without a float."""
    cele, _, zlomek = castka.partition(".")
    return {"currencyCode": mena, "units": str(int(cele)), "nanos": int((zlomek + "000000000")[:9])}


def _plan(polozka: dict, prevod: dict) -> dict:
    regiony = []
    ceny = polozka.get("ceny") or {}
    for kod, p in (prevod.get("convertedRegionPrices") or {}).items():
        cena = p.get("price")
        if kod == "CZ":
            cena = _penize("CZK", float(polozka["cena_czk"]))
        elif cena and cena.get("currencyCode") in ceny:
            cena = _penize_text(cena["currencyCode"], ceny[cena["currencyCode"]])
        regiony.append({"regionCode": kod, "newSubscriberAvailability": True, "price": cena})
    if not any(r["regionCode"] == "CZ" for r in regiony):
        regiony.append({"regionCode": "CZ", "newSubscriberAvailability": True,
                        "price": _penize("CZK", float(polozka["cena_czk"]))})
    plan = {"basePlanId": ZAKLADNI_PLAN, "regionalConfigs": sorted(regiony, key=lambda r: r["regionCode"]),
            "autoRenewingBasePlanType": {"billingPeriodDuration": polozka["obdobi"]}}
    jine = dict(prevod.get("convertedOtherRegionsPrice") or {})
    if "USD" in ceny and "EUR" in ceny:
        jine = {"usdPrice": _penize_text("USD", ceny["USD"]), "eurPrice": _penize_text("EUR", ceny["EUR"])}
    if jine.get("usdPrice") and jine.get("eurPrice"):
        plan["otherRegionsConfig"] = {"usdPrice": jine["usdPrice"], "eurPrice": jine["eurPrice"],
                                      "newSubscriberAvailability": True}
    return plan


def _sedi(predplatne: dict, plan: dict) -> bool:
    """The store already sells what we would send: the Czech price, and —
    for approved foreign prices — every euro and dollar region and the
    other-regions prices. Google's own conversions are not compared (they
    move with its rates; repricing for that would churn the plan)."""
    def castka(m: dict | None) -> tuple:
        m = m or {}
        return (m.get("currencyCode"), int(m.get("units") or 0), int(m.get("nanos") or 0))

    stavajici = (predplatne.get("basePlans") or [{}])[0]
    ted = {r.get("regionCode"): castka(r.get("price")) for r in stavajici.get("regionalConfigs") or []}
    for r in plan["regionalConfigs"]:
        nove = castka(r["price"])
        if (r["regionCode"] == "CZ" or nove[0] in ("EUR", "USD")) and ted.get(r["regionCode"]) != nove:
            return False
    jine, chci = stavajici.get("otherRegionsConfig") or {}, plan.get("otherRegionsConfig") or {}
    return all(castka(jine.get(k)) == castka(chci.get(k)) for k in ("usdPrice", "eurPrice")) if chci else True


def _cz_cena(predplatne: dict) -> float | None:
    for plan in predplatne.get("basePlans") or []:
        for r in plan.get("regionalConfigs") or []:
            if r.get("regionCode") == "CZ" and r.get("price"):
                return int(r["price"].get("units") or 0) + int(r["price"].get("nanos") or 0) / 1e9
    return None


def _listingy_predplatneho(nazev: str, nazev_en: str | None, rocni: bool) -> list[dict]:
    """Czech always; English too when the app has an English store listing.
    Google wants a subscription listing in the app's DEFAULT language, and a
    product that speaks English has en-US as its store default since
    13. 11. 2026 (#232) — a Czech-only listing would then be refused."""
    listingy = [{"languageCode": "cs-CZ",
                 "title": f"{nazev[:40]} — {'roční' if rocni else 'měsíční'} předplatné",
                 "benefits": ["Všechny funkce bez omezení", "Stejný účet v aplikaci i na webu"],
                 "description": "Předplatné se automaticky obnovuje, zrušit ho lze kdykoli v Google Play."}]
    if nazev_en:
        listingy.append({"languageCode": JAZYK_EN_PLAY,
                         "title": f"{nazev_en[:40]} — {'yearly' if rocni else 'monthly'} subscription",
                         "benefits": ["All features, no limits", "The same account in the app and on the web"],
                         "description": "The subscription renews automatically; cancel any time in Google Play."})
    return listingy


def nahraj_predplatne(session, balicek: str, polozky: list[dict], nazev: str,
                      nazev_en: str | None = None) -> list[str]:
    """Create / reprice the app's subscription products. Returns one line
    per product for the summary; raises SystemExit with Google's words.
    `nazev_en`: the app's English store name — then the subscription gets
    an English listing too, and an existing one missing it gets it added."""
    hotovo = []
    for polozka in polozky:
        pid = polozka["id"]
        rocni = polozka["obdobi"] == "P1Y"
        prevod = _ok(session.post(f"{_API}/{balicek}/pricing:convertRegionPrices", json={
            "price": _penize("CZK", round(float(polozka["cena_czk"]) / _DPH, 2))}), "převod ceny do zemí",
            PRAVO_PREDPLATNE)
        verze = (prevod.get("regionVersion") or {}).get("version") or "2022/02"
        telo = {
            "packageName": balicek, "productId": pid,
            "listings": _listingy_predplatneho(nazev, nazev_en, rocni),
            "basePlans": [_plan(polozka, prevod)],
        }
        odpoved = session.get(f"{_API}/{balicek}/subscriptions/{pid}")
        if odpoved.status_code == 404:
            _ok(session.post(f"{_API}/{balicek}/subscriptions",
                             params={"productId": pid, "regionsVersion.version": verze}, json=telo),
                f"založení předplatného {pid}", PRAVO_PREDPLATNE)
            _ok(session.post(f"{_API}/{balicek}/subscriptions/{pid}/basePlans/{ZAKLADNI_PLAN}:activate",
                             json={}), f"zapnutí předplatného {pid}", PRAVO_PREDPLATNE)
            hotovo.append(f"{pid}: založeno za {polozka['cena_czk']} Kč")
            continue
        stavajici = _ok(odpoved, f"čtení předplatného {pid}", PRAVO_PREDPLATNE)
        cena_sedi = _cz_cena(stavajici) == float(polozka["cena_czk"]) and (
            not polozka.get("ceny") or _sedi(stavajici, telo["basePlans"][0]))
        ma_jazyky = {x.get("languageCode") for x in stavajici.get("listings") or []}
        chybi_jazyk = not {x["languageCode"] for x in telo["listings"]} <= ma_jazyky
        if cena_sedi and not chybi_jazyk:
            hotovo.append(f"{pid}: beze změny ({polozka['cena_czk']} Kč)")
            continue
        maska = ",".join(m for m, ano in (("listings", chybi_jazyk), ("basePlans", not cena_sedi)) if ano)
        _ok(session.patch(f"{_API}/{balicek}/subscriptions/{pid}",
                          params={"updateMask": maska, "regionsVersion.version": verze}, json=telo),
            f"změna předplatného {pid}", PRAVO_PREDPLATNE)
        hotovo.append(f"{pid}: " + "; ".join(
            ([f"nová cena {polozka['cena_czk']} Kč (stávající předplatitelé platí dál původní)"] if not cena_sedi
             else []) + (["doplněn anglický popis"] if chybi_jazyk else [])))
    return hotovo


def predplatne_ze_vstupu(text: str) -> list[dict]:
    """PREDPLATNE as SimteGen sends it; anything malformed means nothing to
    sell — a wrong price in the store is worse than none."""
    try:
        data = json.loads(text or "[]")
    except json.JSONDecodeError:
        return []
    vysledek = []
    for p in data if isinstance(data, list) else []:
        if (isinstance(p, dict) and p.get("id") in ("predplatne_mesic", "predplatne_rok")
                and p.get("obdobi") in ("P1M", "P1Y") and isinstance(p.get("cena_czk"), (int, float))
                and 0 < p["cena_czk"] < 100000):
            polozka = {"id": p["id"], "obdobi": p["obdobi"], "cena_czk": p["cena_czk"]}
            ceny = p.get("ceny")
            # Foreign prices only whole and well-formed: half a price list
            # would sell euros in one region and Google's guess in the next.
            if (isinstance(ceny, dict) and set(ceny) == {"EUR", "USD"}
                    and all(isinstance(v, str) and re.fullmatch(r"\d{1,5}(?:\.\d{1,2})?", v)
                            and float(v) > 0 for v in ceny.values())):
                polozka["ceny"] = {"EUR": ceny["EUR"], "USD": ceny["USD"]}
            vysledek.append(polozka)
    return vysledek


NEZNAMA = "neznama"


def nahraj_bundle(session, balicek: str, bundle: bytes, nazev_verze: str, poznamka: str,
                  anglicky: bool = False) -> dict:
    """One edit with the release only: insert → upload bundle → internal
    track → commit. `session` is an authorised requests-like session (tests
    pass a fake). The listing goes in its own edit afterwards
    (nahraj_zaznam_zvlast): a permission the listing lacks must not hold the
    build back. Returns {"versionCode", "status"}; status "neznama" when
    Google does not know the package yet (the first upload is a human's, the
    API refuses it); raises SystemExit with Google's words — and, on a 403,
    the permission to add — on anything else. `anglicky`: the app has an
    English listing, so the release note gets the fixed English line too."""

    def ok(odpoved, co):
        return _ok(odpoved, co, PRAVO_VYDANI)

    odpoved = session.post(f"{_API}/{balicek}/edits", json={})
    if odpoved.status_code == 404:
        # Not a failure: the build is fine and the .aab in the artifact is
        # exactly what the owner uploads. As a failed job it read "sestavení
        # selhalo" after every deploy.
        return {"versionCode": None, "status": NEZNAMA}
    edit = ok(odpoved, "založení úpravy")["id"]
    nahrano = ok(session.post(f"{_UPLOAD}/{balicek}/edits/{edit}/bundles?uploadType=media", data=bundle,
                              headers={"Content-Type": "application/octet-stream"}, timeout=900),
                 "nahrání balíčku")
    kod = str(nahrano["versionCode"])
    vydani = {"name": nazev_verze, "versionCodes": [kod], "status": "completed",
              "releaseNotes": [{"language": "cs-CZ", "text": poznamka[:500] or "Průběžné vydání."}]
              + ([{"language": JAZYK_EN_PLAY, "text": POZNAMKA_EN}] if anglicky else [])}
    odpoved = session.put(f"{_API}/{balicek}/edits/{edit}/tracks/internal",
                          json={"track": "internal", "releases": [vydani]})
    if odpoved.status_code == 400 and "draft" in odpoved.text.lower():
        # Never-published app: Google takes only drafts until the first
        # release is sent from the console.
        vydani["status"] = "draft"
        odpoved = session.put(f"{_API}/{balicek}/edits/{edit}/tracks/internal",
                              json={"track": "internal", "releases": [vydani]})
    ok(odpoved, "zařazení do interního testování")
    ok(session.post(f"{_API}/{balicek}/edits/{edit}:commit"), "potvrzení vydání")
    return {"versionCode": kod, "status": vydani["status"]}


def poznamka_k_vydani(produkt: Path = Path("produkt")) -> str:
    """What the customer reads under "Co je nového": the builder's note from
    the product's last build (play/co_je_noveho.txt), else what SimteGen
    passed in. Google's limit is 500 characters."""
    soubor = produkt / "play" / "co_je_noveho.txt"
    if soubor.exists():
        text = soubor.read_text(encoding="utf-8").strip()
        if text:
            return text[:500]
    return os.environ.get("POZNAMKA", "")


def nahraj(cesta_bundle: str) -> dict:
    from google.auth.transport.requests import AuthorizedSession
    from google.oauth2 import service_account

    ucet = json.loads(os.environ["PLAY_SERVICE_ACCOUNT_JSON"])
    pristup = service_account.Credentials.from_service_account_info(
        ucet, scopes=["https://www.googleapis.com/auth/androidpublisher"])
    twa = json.loads((VYSTUP / "twa-manifest.json").read_text(encoding="utf-8"))
    session = AuthorizedSession(pristup)
    obchod = VYSTUP / "obchod"
    try:
        # A broken listing file must not stop the release itself.
        preklady = json.loads((obchod / "zaznam.json").read_text(encoding="utf-8")).get("preklady") or {}
    except (OSError, ValueError, AttributeError):
        preklady = {}
    poznamka = poznamka_k_vydani()[:500] or "Průběžné vydání."
    vysledek = nahraj_bundle(session, twa["packageId"], Path(cesta_bundle).read_bytes(),
                             twa["appVersionName"], poznamka, anglicky=JAZYK_EN_PLAY in preklady)
    vystup = os.environ.get("GITHUB_OUTPUT")
    if vystup:
        # Production publishes the internal release's note; this hash lets it
        # check the note is still the one this run wrote (the internal key
        # could rewrite it in between).
        with open(vystup, "a", encoding="utf-8") as f:
            f.write(f"poznamka_sha={_sha(poznamka)}\n")
    if vysledek["status"] == NEZNAMA:
        print(f"Google Play aplikaci {twa['packageId']} zatím nezná. První verzi nahraj ručně v Play Console "
              "(Interní testování → Vytvořit vydání → soubor .aab z artefaktu tohoto běhu).")
        if vystup:
            with open(vystup, "a", encoding="utf-8") as f:
                f.write(f"stav={NEZNAMA}\n")
        return vysledek
    vysledek["zaznam"] = None
    if (obchod / "zaznam.json").exists():
        # Like the form below: the release is in; a refused listing is
        # reported with its permission, and the next release tries again.
        otisk_soubor = obchod / "otisk.txt"
        otisk = otisk_soubor.read_text(encoding="utf-8").strip() if otisk_soubor.exists() else ""
        otisk = otisk if re.fullmatch(r"[0-9a-f]{64}", otisk) else ""
        obrazky = not otisk or otisk != os.environ.get("PREDCHOZI_OTISK_OBCHODU", "").strip()
        try:
            vysledek["zaznam"] = nahraj_zaznam_zvlast(session, twa["packageId"], obchod, twa["host"], obrazky)
            print("Záznam v obchodě:", ", ".join(vysledek["zaznam"]),
                  "" if obrazky else "(obrazovky produktu beze změny — snímky jen tam, kde v Play chybí)")
            if otisk and vystup:
                # Only after every picture went up: a refused one is retried
                # next time instead of being taken for current.
                with open(vystup, "a", encoding="utf-8") as f:
                    f.write(f"obchod_otisk={otisk}\n")
        except (Exception, SystemExit) as e:  # noqa: BLE001
            print(f"::warning::Záznam v obchodě se nepodařilo nahrát: {jeden_radek(e)}")
        if vystup:
            with open(vystup, "a", encoding="utf-8") as f:
                f.write(f"zaznam_play={'1' if vysledek['zaznam'] else '0'}\n")
    vysledek["bezpecnost"] = False
    formular = obchod / "bezpecnost_dat.csv"
    if formular.exists():
        # The release is already committed; a refused form must not turn it
        # into a failed job. It is reported instead, and the next release
        # tries again. SystemExit is how _ok carries Google's answer.
        try:
            nahraj_bezpecnost(session, twa["packageId"], formular.read_text(encoding="utf-8"))
            vysledek["bezpecnost"] = True
            print("Bezpečnost údajů: formulář vyplněn.")
        except (Exception, SystemExit) as e:  # noqa: BLE001
            print(f"::warning::Bezpečnost údajů se nepodařilo nahrát: {jeden_radek(e)}")
        if vystup:
            with open(vystup, "a", encoding="utf-8") as f:
                f.write(f"bezpecnost={'1' if vysledek['bezpecnost'] else '0'}\n")
    polozky = predplatne_ze_vstupu(os.environ.get("PREDPLATNE", ""))
    if polozky and twa.get("features", {}).get("playBilling"):
        # Like the form: the release is in; a refused price is reported,
        # and the next release tries again.
        try:
            nazev_en = str((preklady.get(JAZYK_EN_PLAY) or {}).get("nazev") or "") or None
            vysledek["predplatne"] = nahraj_predplatne(session, twa["packageId"], polozky, twa.get("name") or "",
                                                       nazev_en)
            print("Předplatné v Google Play:", "; ".join(vysledek["predplatne"]))
            stav_predplatneho = "1"
        except (Exception, SystemExit) as e:  # noqa: BLE001
            print(f"::warning::Předplatné v Google Play se nepodařilo nastavit: {jeden_radek(e)}")
            stav_predplatneho = "0"
        if vystup:
            with open(vystup, "a", encoding="utf-8") as f:
                f.write(f"predplatne={stav_predplatneho}\n")
    stav = ("připraveno jako koncept — aplikace ještě nebyla vydána, první vydání pošli v Play Console"
            if vysledek["status"] == "draft" else "v interním testování")
    print(f"Nahráno: {twa['packageId']} kód {vysledek['versionCode']}, {stav}.")
    if vystup:
        with open(vystup, "a", encoding="utf-8") as f:
            f.write(f"stav={vysledek['status']}\n")
    return vysledek


# ── Production ────────────────────────────────────────────────────────
#
# Threat model, the one that decided the shape (CLAUDE.md, "Publikace"):
#   - The release key (PLAY_SERVICE_ACCOUNT_JSON) and the upload key live in
#     `vydej`; a thief with both can put any bundle on the INTERNAL track —
#     testers only. The production key (PLAY_PRODUKCE_SERVICE_ACCOUNT_JSON)
#     lives only in the `produkce` job, behind a GitHub environment that
#     admits runs from main alone, next to no upload key and no product
#     code. A thief with it alone can promote what we built, nothing else:
#     Google takes only bundles signed with the registered upload key.
#   - What goes up is checked against Play itself, not against anything the
#     run was told: the version must already be on the internal track, newer
#     than production, and production must already exist.
#   - The domain must be the one the product's repo declares on main
#     (data-manifest.json → adresa), fail closed: the app is a window onto a
#     domain, and a manifest copied to a stranger's site would otherwise
#     carry our package to production.
#   - The shell's fingerprint is kept in the production release's own name
#     in Play (where only the owner and the production key write), never in
#     a branch the bot token could touch.

PRAVO_PRODUKCE = ("Vydávání v produkční verzi, vyloučení zařízení a používání Play App Signing "
                  "(Release to production, exclude devices, and use Play App Signing)")
_BALICEK = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$")
_PROJEKT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$")
_ADRESA = re.compile(r"^https://([a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)+)/?$")
# A production release the owner is steering by hand: halted, rolled out in
# stages, or prepared as a draft. Automation never replaces those.
_RUCNI_STAVY = ("halted", "inProgress", "draft")
_OTISK = re.compile(r"\bobal ([0-9a-f]{12})\b")
# What makes two bundles the same app for a user: everything in the TWA
# description but the version, and the generator (its version decides the
# target API level).
_BEZ_VERZE = ("appVersionName", "appVersionCode", "appVersion", "signingKey")


def _stahni_bajty(url: str) -> bytes:
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "simtegen-vydani"}),
                                timeout=30) as odpoved:
        return odpoved.read()


def otisk_obalu(twa: dict, generator: str, stahni=_stahni_bajty) -> str:
    """SHA-256 of the app's shell: the TWA description without its version,
    the Bubblewrap release, and the icons' bytes (an icon may change under
    the same address). Equal fingerprint = nothing for a user to update."""
    import hashlib

    h = hashlib.sha256()
    popis = {k: v for k, v in twa.items() if k not in _BEZ_VERZE}
    h.update(json.dumps(popis, sort_keys=True, ensure_ascii=False).encode("utf-8"))
    h.update(b"\0" + generator.encode("utf-8"))
    for klic in ("iconUrl", "maskableIconUrl", "monochromeIconUrl"):
        if twa.get(klic):
            h.update(b"\0" + klic.encode("ascii") + b"\0" + stahni(twa[klic]))
    return h.hexdigest()


def _sha(text: str) -> str:
    import hashlib

    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _cisty(text: str) -> str:
    """One line, no control characters — for GITHUB_OUTPUT and summaries."""
    return "".join(c if c.isprintable() else " " for c in text)[:300]


def adresa_z_repa(projekt: str, vlastnik: str) -> tuple[str | None, str | None]:
    """(host, package) the product's repo declares on main — or (None, None)
    when it cannot be read. Unlike balicek_z_repa this one fails closed: a
    production release without the check does not happen. Only an explicit
    https `adresa` counts: a bare <projekt>.pages.dev belongs to whoever
    created that Cloudflare project first, which need not be us."""
    adresa = f"https://raw.githubusercontent.com/{vlastnik}/{projekt}/main/data-manifest.json"
    try:
        manifest = json.loads(_stahni_bajty(adresa).decode("utf-8"))
    except Exception:  # noqa: BLE001
        return None, None
    if not isinstance(manifest, dict):
        return None, None
    shoda = _ADRESA.fullmatch(str(manifest.get("adresa") or "").strip())
    balicek = (manifest.get("aplikace") or {}).get("balicek")
    return (shoda.group(1) if shoda else None), (str(balicek) if balicek else None)


def brana_produkce(projekt: str, domena: str, balicek: str, kod: str, otisk: str,
                   vlastnik: str, cti_repo=adresa_z_repa) -> str | None:
    """None when the run may go on to Play; otherwise why not (Czech)."""
    if not _PROJEKT.fullmatch(projekt or ""):
        return "neplatný název repa produktu"
    if not _BALICEK.fullmatch(balicek or ""):
        return "neplatný název balíčku"
    if not re.fullmatch(r"\d{1,10}", kod or ""):
        return "neplatný kód verze"
    if not re.fullmatch(r"[0-9a-f]{64}", otisk or ""):
        return "chybí otisk obalu aplikace"
    host = (domena or "").strip()
    z_repa, balicek_repa = cti_repo(projekt, vlastnik)
    if z_repa is None:
        return ("repo produktu nejde přečíst, nebo v data-manifest.json nemá adresu https:// — "
                "bez ověřené domény se do produkce nevydává")
    if host != z_repa:
        return f"doména {host} není adresa produktu z jeho repa ({z_repa})"
    if balicek_repa != balicek:
        return f"balíček {balicek} není balíček produktu z jeho repa ({balicek_repa})"
    return None


def _verze_v_kanalu(kanal: dict) -> list[tuple[dict, int]]:
    return [(r, int(k)) for r in kanal.get("releases") or [] for k in r.get("versionCodes") or []]


def povys(session, balicek: str, kod: str, verze: str, otisk: str, poznamka_sha: str = "") -> dict:
    """Production release of a version already on the internal track.
    Returns {"stav": "povyseno" | "preskoceno", "duvod": …}; raises
    SystemExit with Google's words (and the permission) on a refusal."""

    def ok(odpoved, co):
        return _ok(odpoved, co, PRAVO_PRODUKCE, "PLAY_PRODUKCE_SERVICE_ACCOUNT_JSON")

    edit = ok(session.post(f"{_API}/{balicek}/edits", json={}), "založení úpravy pro produkci")["id"]

    def konec(duvod: str) -> dict:
        session.delete(f"{_API}/{balicek}/edits/{edit}")
        return {"stav": "preskoceno", "duvod": duvod}

    produkce = ok(session.get(f"{_API}/{balicek}/edits/{edit}/tracks/production"), "čtení produkce")
    vydani_produkce = produkce.get("releases") or []
    rucne = sorted({r.get("status") for r in vydani_produkce if r.get("status") in _RUCNI_STAVY})
    if rucne:
        return konec(f"v produkci je vydání, které řídíš ručně ({', '.join(rucne)}) — automat ho nepřepíše")
    zive = [r for r in vydani_produkce if r.get("status") == "completed"]
    if not zive:
        return konec("aplikace ještě není v produkci — první vydání do produkce je ruční (Play Console)")
    if any(otisk[:12] in _OTISK.findall(r.get("name") or "") for r in zive):
        return konec("obal aplikace se nezměnil — nový web je v aplikaci sám, vydání netřeba")
    nejvyssi = max((k for _, k in _verze_v_kanalu({"releases": zive})), default=0)
    if int(kod) <= nejvyssi:
        return konec(f"verze {kod} není novější než produkční {nejvyssi}")
    interni = ok(session.get(f"{_API}/{balicek}/edits/{edit}/tracks/internal"), "čtení interního testování")
    vydani = next((r for r, k in _verze_v_kanalu(interni) if k == int(kod) and r.get("status") == "completed"), None)
    if vydani is None:
        return konec(f"verze {kod} není dokončená v interním testování — do produkce jde jen to, co tam je")
    poznamky = vydani.get("releaseNotes") or []
    cesky = next((n.get("text") or "" for n in poznamky if n.get("language") == "cs-CZ"), None)
    # The Czech note this run hashed, plus at most the fixed English line —
    # anything else was written by someone else and is not published.
    cizi = [n for n in poznamky if n.get("language") != "cs-CZ"
            and not (n.get("language") == JAZYK_EN_PLAY and n.get("text") == POZNAMKA_EN)]
    cs_pocet = sum(1 for n in poznamky if n.get("language") == "cs-CZ")
    if cs_pocet != 1 or cizi or len(poznamky) > 2 or cesky is None or _sha(cesky) != poznamka_sha:
        return konec("poznámka k vydání v interním testování není ta, kterou napsal tento běh — nepublikuje se")
    nove = {"name": f"{verze} · obal {otisk[:12]}"[:50], "versionCodes": [str(kod)], "status": "completed",
            "releaseNotes": [{"language": "cs-CZ", "text": cesky}]
            + ([{"language": JAZYK_EN_PLAY, "text": POZNAMKA_EN}] if len(poznamky) == 2 else [])}
    ok(session.put(f"{_API}/{balicek}/edits/{edit}/tracks/production",
                   json={"track": "production", "releases": [nove]}), "zařazení do produkce")
    ok(session.post(f"{_API}/{balicek}/edits/{edit}:commit"), "potvrzení produkce")
    return {"stav": "povyseno", "duvod": f"verze {verze} (kód {kod}) odeslána ke kontrole Googlu do produkce"}


def povys_z_prostredi(env: dict | None = None) -> dict:
    """The `produkce` job: gate, then Play. A skip is a normal outcome;
    a refusal by Google fails the job (main returns 1: a red run is what
    the owner looks at)."""
    env = env if env is not None else os.environ
    ucet_text = env.get("PLAY_PRODUKCE_SERVICE_ACCOUNT_JSON", "")
    if not ucet_text:
        vysledek = {"stav": "preskoceno", "duvod": "chybí secret PLAY_PRODUKCE_SERVICE_ACCOUNT_JSON "
                                                   "v prostředí play-produkce"}
    else:
        duvod = brana_produkce(env.get("PROJEKT", ""), env.get("DOMENA", ""), env.get("BALICEK", ""),
                               env.get("KOD", ""), env.get("OTISK", ""),
                               env.get("GITHUB_REPOSITORY_OWNER") or "simtegen-apps")
        if duvod:
            vysledek = {"stav": "preskoceno", "duvod": duvod}
        else:
            from google.auth.transport.requests import AuthorizedSession
            from google.oauth2 import service_account

            pristup = service_account.Credentials.from_service_account_info(
                json.loads(ucet_text), scopes=["https://www.googleapis.com/auth/androidpublisher"])
            try:
                vysledek = povys(AuthorizedSession(pristup), env["BALICEK"], env["KOD"], env.get("VERZE", ""),
                                 env["OTISK"], env.get("POZNAMKA_SHA", ""))
            except SystemExit as e:
                # Google's words go to this job's log only; the result file
                # sits on a public branch and travels on as data.
                print(f"::warning::Produkce: {jeden_radek(e)}")
                vysledek = {"stav": "chyba", "duvod": "Google povýšení odmítl — důvod je v logu kroku Povyseni"}
    vystup = env.get("GITHUB_OUTPUT")
    if vystup:
        with open(vystup, "a", encoding="utf-8") as f:
            f.write(f"stav={vysledek['stav']}\nduvod={_cisty(vysledek['duvod'])}\n")
    print(f"Produkce: {_cisty(vysledek['duvod'])}")
    return vysledek


def zapis(env: dict | None = None) -> dict:
    """The `zapis` job: `vydej`'s result plus what production did. Without
    `vydej`'s file (it failed before writing) a bare result, so SimteGen
    still hears the run ended."""
    env = env if env is not None else os.environ
    cesta = VYSTUP / "vysledek.json"
    if cesta.exists() and _sha(cesta.read_text(encoding="utf-8")) != env.get("VYSLEDEK_SHA"):
        # The artifact store is reachable from the job that runs the
        # product's code; only the file `vydej` vouched for counts.
        print("::warning::Výsledek z vydej nesedí s jeho otiskem — zapisuje se jen holý výsledek.")
        cesta.unlink()
    if cesta.exists():
        data = json.loads(cesta.read_text(encoding="utf-8"))
    else:
        data = vysledek({**env, "STAV": env.get("STAV_VYDEJ") or "failure"})
    stav = env.get("PRODUKCE") or None
    duvod = env.get("PRODUKCE_DUVOD") or None
    if stav is None and env.get("PRODUKCE_JOB") == "failure":
        stav, duvod = "chyba", "job produkce selhal — důvod je v jeho logu"
    elif stav is None and env.get("PRODUKCE_JOB") == "skipped" and env.get("PRODUKCE_ZAPNUTO") != "ano":
        stav, duvod = "vypnuto", "automatické vydání do produkce je vypnuté (org proměnná PLAY_PRODUKCE)"
    data["produkce"], data["produkce_duvod"] = stav, _cisty(duvod or "") or None
    otisk = env.get("OBCHOD_OTISK", "")
    if re.fullmatch(r"[0-9a-f]{64}", otisk):
        (VYSTUP / "obchod.json").write_text(json.dumps({"otisk": otisk}) + "\n", encoding="utf-8")
    cesta.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    return data


# Bubblewrap's project names its Gradle distribution without a checksum;
# Gradle then runs whatever that URL serves. Pinned here — a different
# Gradle (a Bubblewrap bump) stops the build until its checksum is added
# (from https://services.gradle.org/distributions/<file>.sha256).
GRADLE_OTISKY = {
    "https\\://services.gradle.org/distributions/gradle-8.11.1-bin.zip":
        "f397b287023acdba1e9f6fc5ea72d22dd63669d59ed4a289a29b1a76eee151c6",
}


def pripni_gradle(projekt: Path = VYSTUP) -> str:
    cesta = projekt / "gradle" / "wrapper" / "gradle-wrapper.properties"
    radky = cesta.read_text(encoding="utf-8").splitlines()
    url = next((r.split("=", 1)[1].strip() for r in radky if r.startswith("distributionUrl=")), "")
    if url not in GRADLE_OTISKY:
        raise SystemExit(f"Bubblewrap chce Gradle {url or '(neuvedený)'}, který nemá ověřený otisk — "
                         "doplň ho do GRADLE_OTISKY ve vydani.py.")
    radky = [r for r in radky if not r.startswith("distributionSha256Sum=")]
    radky.append(f"distributionSha256Sum={GRADLE_OTISKY[url]}")
    cesta.write_text("\n".join(radky) + "\n", encoding="utf-8")
    return GRADLE_OTISKY[url]


def cilove_api(projekt_slozka: Path) -> int | None:
    """targetSdk of the generated Android project. Google raises the bar
    every year; SimteGen compares this with the coming deadline and
    rebuilds in time (a newer Bubblewrap targets a newer API)."""
    for gradle in sorted(projekt_slozka.rglob("build.gradle*")):
        m = re.search(r"targetSdk(?:Version)?\s*=?\s*(\d+)", gradle.read_text(encoding="utf-8", errors="replace"))
        if m:
            return int(m.group(1))
    return None


def vysledek(env: dict | None = None) -> dict:
    """What SimteGen reads back (template repo, branch metriky,
    vydani/<projekt>.json): which run, which version, which API level,
    whether it went to Play. Written even when the run failed — a silent
    failure would leave SimteGen waiting for a release that never comes."""
    env = env if env is not None else os.environ
    twa = {}
    if (VYSTUP / "twa-manifest.json").exists():
        twa = json.loads((VYSTUP / "twa-manifest.json").read_text(encoding="utf-8"))
    data = {
        "oznaceni": env.get("OZNACENI", ""),
        "stav": env.get("STAV", ""),
        "balicek": twa.get("packageId"),
        "verze": twa.get("appVersionName"),
        "kod": twa.get("appVersionCode"),
        "cilove_api": cilove_api(VYSTUP),
        "docasny_klic": env.get("DOCASNY") == "1",
        "nahrano": env.get("NAHRANO") == "success" and env.get("STAV_PLAY") != NEZNAMA,
        "stav_play": env.get("STAV_PLAY") or None,
        "zaznam": env.get("ZAZNAM") == "1",
        # The listing reached Play (None: not attempted — no listing, unknown
        # app, or the release itself did not go in).
        "zaznam_play": {"1": True, "0": False}.get(env.get("ZAZNAM_PLAY", "")),
        # None: not attempted (no listing, unknown app, no upload at all).
        "bezpecnost_dat": {"1": True, "0": False}.get(env.get("BEZPECNOST", "")),
        # Selling in the app: built with Play Billing; subscription products
        # in Play set (None = nothing to set: no approved price, no billing).
        "nakupy": env.get("NAKUPY") == "1",
        "predplatne_play": {"1": True, "0": False}.get(env.get("PREDPLATNE_PLAY", "")),
        # Production (job `produkce`): "povyseno" | "preskoceno" | "chyba",
        # None when the job did not run (switched off, upload failed…).
        "produkce": env.get("PRODUKCE") or None,
        "produkce_duvod": (env.get("PRODUKCE_DUVOD") or "")[:300] or None,
        "run_url": env.get("RUN_URL", ""),
        "cas": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    text = json.dumps(data, ensure_ascii=False, indent=1)
    (VYSTUP / "vysledek.json").write_text(text, encoding="utf-8")
    vystup = env.get("GITHUB_OUTPUT")
    if vystup:
        with open(vystup, "a", encoding="utf-8") as f:
            f.write(f"sha={_sha(text)}\n")
    return data


# ── Play Console: what has no API ─────────────────────────────────────
#
# Creating the app, its first bundle, the default store listing, the store
# category and the App content declarations exist only in Play Console
# (11. 11. 2026: the API edits a listing but never creates it). Nothing on
# the mini PC may hold the owner's Google session, so a human — or Claude in
# the owner's own Chrome, the owner confirming each save (skill
# play-nova-aplikace in SimteGen) — clicks it through, once per app. Every
# answer is generated here, from the same claims as the privacy policy, so
# neither of them invents one.

# Same text as vykresli_aplikaci.PRISTUP_KONTROLORA (a test keeps them equal):
# the template's release tool cannot import the product's generator.
PRISTUP_KONTROLORA = (
    "No login credentials are needed. On the start screen tap \"Vyzkoušet ukázku\" "
    "(Try the demo): the app creates a temporary account with sample data and all paid "
    "features unlocked; it is deleted after 24 hours. Sign-in for real customers is by a "
    "one-time link sent to their e-mail (no password). Purchases are disabled in the demo "
    "account; the subscription offer and its terms are shown there."
)
# Play Console's own Czech labels, as its category list shows them (Byznys,
# Auto moto, Cestování a místa read off it 11. 11. 2026) — the skill picks the
# option by this text, so a translation of our own would find nothing.
KATEGORIE_CZ = {
    "BUSINESS": "Byznys", "PRODUCTIVITY": "Produktivita", "TOOLS": "Nástroje", "FINANCE": "Finance",
    "EDUCATION": "Vzdělávání", "LIFESTYLE": "Životní styl", "HOUSE_AND_HOME": "Dům a domácnost",
    "FOOD_AND_DRINK": "Jídlo a pití", "HEALTH_AND_FITNESS": "Zdraví a fitness", "SHOPPING": "Nakupování",
    "AUTO_AND_VEHICLES": "Auto moto", "TRAVEL_AND_LOCAL": "Cestování a místa",
    "SPORTS": "Sport", "PARENTING": "Rodičovství", "EVENTS": "Události", "COMMUNICATION": "Komunikace",
    "BOOKS_AND_REFERENCE": "Knihy a referenční materiály", "ENTERTAINMENT": "Zábava",
}


def inzertni_id(adresar: Path) -> bool | None:
    """Does the built app ask for the advertising ID? Read from the bundle's
    own manifest (protobuf, but permission names stay plain strings), not
    assumed: a library that adds AD_ID would make "Ne" a false declaration.
    None when there is no bundle to read."""
    import zipfile

    aab = adresar / "app-release-bundle.aab"
    if not aab.exists():
        return None
    try:
        with zipfile.ZipFile(aab) as z:
            return b"permission.AD_ID" in z.read("base/manifest/AndroidManifest.xml")
    except (zipfile.BadZipFile, KeyError):
        return None


def konzole(twa: dict, zaznam: dict, obchod: Path) -> dict:
    """Every Play Console form that has no API, answered, in the order the
    console asks. Machine-readable (obchod/play_console.json, read by the
    Chrome skill) and the source of PRVNI_VYDANI.md, so the two never
    differ. Files are named relative to the artifact's obchod/ folder."""
    host = twa.get("host", "")
    adresa = f"https://{host}"
    nazev = zaznam.get("nazev") or twa.get("name") or twa["packageId"]
    kat = zaznam.get("kategorie") or ""
    ucty = bool(zaznam.get("ucty"))
    nakupy = bool((twa.get("features") or {}).get("playBilling"))
    obrazky = {typ: [s.name for s in soubory] for typ, soubory in _obrazky_zaznamu(obchod)}
    return {
        "balicek": twa["packageId"],
        "nazev": nazev[:30],
        "adresa": adresa,
        "vytvoreni": {
            "nazev": nazev[:30], "balicek": twa["packageId"], "jazyk": "čeština – cs-CZ",
            "typ": "Aplikace", "cena": "Zdarma",
            "deklarace": ["Zásady pro vývojáře", "Play App Signing", "Vývozní zákony USA"],
        },
        "prvni_vydani": {
            "kanal": "Interní testování", "soubor": "app-release-bundle.aab",
            "klic": "Použít klíč vygenerovaný Googlem", "poznamka": "První verze.",
            "verze": twa.get("appVersionName"), "kod": twa.get("appVersionCode"),
        },
        "vychozi_zaznam": {
            "nazev": nazev[:30], "kratky_popis": (zaznam.get("kratky_popis") or "")[:80],
            "dlouhy_popis": (zaznam.get("dlouhy_popis") or "")[:4000],
            "ikona": (obrazky.get("icon") or [None])[0],
            "grafika": (obrazky.get("featureGraphic") or [None])[0],
            "telefon": obrazky.get("phoneScreenshots") or [],
            "tablet_7": obrazky.get("sevenInchScreenshots") or [],
            "tablet_10": obrazky.get("tenInchScreenshots") or [],
        },
        "nastaveni_obchodu": {
            "typ": "Aplikace", "kategorie": KATEGORIE_CZ.get(kat, kat), "kategorie_kod": kat,
            "email": zaznam.get("kontakt_email") or "", "web": adresa,
        },
        # Obsah aplikace (App content), one form each, in the order Play
        # Console lets them be filled (Cílové publikum waits for Přihlašovací
        # údaje). Pages strips .html with a 308, so the policy URL is the
        # address it lands on.
        "zasady_url": f"{adresa}{(zaznam.get('zasady_cesta') or '/zasady.html').removesuffix('.html')}",
        "pristup": ({"omezeny": True, "nazev_pokynu": "Ukázka", "jmeno": "", "heslo": "",
                     "pokyny": PRISTUP_KONTROLORA,
                     # "Plný přístup ke všem funkcím" — a required declaration;
                     # the owner ticks it, never the skill.
                     "plny_pristup_zaskrtava_majitel": True} if ucty else {"omezeny": False}),
        "reklamy": False,
        "cilova_skupina": {"vek": ["18 a více"], "laka_deti": False},
        "vladni": False,
        "financni_funkce": "Aplikace neposkytuje žádné finanční funkce",
        "zdravi": "Aplikace nemá žádné zdravotní funkce",
        "inzertni_id": inzertni_id(obchod.parent),
        # Questions as the IARC questionnaire asks them for "all other apps"
        # (11. 11. 2026); the terms checkbox on its first page is the owner's.
        "hodnoceni_obsahu": {
            "email": zaznam.get("kontakt_email") or "",
            "kategorie": "Všechny ostatní typy aplikací",
            "podminky_iarc_zaskrtava_majitel": True,
            "stazeny_obsah_k_hodnoceni": False, "sdileni_uzivatelskeho_obsahu": False,
            "online_obsah": False, "vekove_omezene_produkty": False, "sdileni_polohy": False,
            "digitalni_nakupy": nakupy, "nahodne_polozky": False if nakupy else None,
            "penezni_odmeny_nft": False, "prohlizec_vyhledavac": False, "zpravy_vzdelavani": False,
        },
        "bezpecnost_udaju": "bezpecnost_dat.csv" if (obchod / "bezpecnost_dat.csv").exists() else None,
        # Owner's own declarations, never answered here: whether the assets
        # are AI-made (asked when the listing is saved), and the app-level
        # trader status.
        "majitel": ["Deklarace podkladů vytvořených pomocí AI (při uložení záznamu)",
                    "Status obchodníka na úrovni aplikace a smluvní podmínky"],
    }


def _ano(hodnota: bool) -> str:
    return "**Ano**" if hodnota else "**Ne**"


def navod(adresar: Path = VYSTUP) -> Path:
    """obchod/PRVNI_VYDANI.md and obchod/play_console.json: everything Play
    Console wants from a person for a new app, every value filled in. Play
    Console asks for the package when the app is created and never lets it
    change again — so the guide names it, not the owner's memory. Written
    into every artifact; it costs nothing and a later reader of an old run
    still gets the right values for that build."""
    twa = json.loads((adresar / "twa-manifest.json").read_text(encoding="utf-8"))
    obchod = adresar / "obchod"
    obchod.mkdir(parents=True, exist_ok=True)
    zaznam_soubor = obchod / "zaznam.json"
    zaznam = json.loads(zaznam_soubor.read_text(encoding="utf-8")) if zaznam_soubor.exists() else {}
    k = konzole(twa, zaznam, obchod)
    (obchod / "play_console.json").write_text(json.dumps(k, ensure_ascii=False, indent=2) + "\n",
                                              encoding="utf-8")
    nazev = zaznam.get("nazev") or twa.get("name") or twa["packageId"]
    host = twa.get("host", "")
    radky = [
        f"# První vydání: {nazev}",
        "",
        "Vygenerováno workflow Vydani pro tohle sestavení. Ručně se dělá jen úplně první",
        "vydání nové aplikace; každé další nahraje SimteGen sám.",
        "",
        "## 1. Play Console → Vytvořit aplikaci",
        "",
        "| Pole | Hodnota |",
        "|---|---|",
        f"| Název aplikace | `{nazev[:30]}` |",
        f"| **Název balíčku** | `{twa['packageId']}` (navždy, musí přesně sedět) |",
        "| Výchozí jazyk | čeština – cs-CZ |",
        "| Aplikace/hra | Aplikace |",
        "| Zdarma/placená | Za 0 Kč |",
        "| Deklarace | zaškrtnout všechny tři (zásady, Play App Signing, vývozní zákony USA) |",
        "",
        "## 2. Testování a vydání → Interní testování → Vytvořit nové vydání",
        "",
        "1. Podpisový klíč aplikace: **Použít klíč vygenerovaný Googlem** (výchozí).",
        f"2. Nahraj `app-release-bundle.aab` z tohoto artefaktu (verze {twa.get('appVersionName')}, "
        f"kód {twa.get('appVersionCode')}).",
        "3. Poznámky k vydání:",
        "   ```",
        "   <cs-CZ>",
        "   První verze.",
        "   </cs-CZ>",
        "   ```",
        "4. Další → varování o deobfuskaci a testerech ignoruj → Uložit → Spustit zavádění do interního testování.",
        "",
        "## 3. Testeři",
        "",
        "Záložka Testeři → Vytvořit seznam e-mailů (svůj Google účet) → uložit → odkaz pro připojení",
        "otevři v telefonu → Stát se testerem → nainstaluj z Google Play.",
        "",
        "## 4. Otisk klíče — nic nekopíruj",
        "",
        "SimteGen si otisk podpisového klíče stáhne z Google Play sám (denní workflow Play) a zapíše ho",
        "do produktu pull requestem od bota. Ty ho jen schválíš. Do té doby se aplikace otevírá",
        "s adresním řádkem prohlížeče.",
        "",
        "## 5. Před produkcí (ne pro interní testování)",
        "",
    ]
    if (adresar / "obchod" / "bezpecnost_dat.csv").exists():
        radky += [
            "**Bezpečnost údajů vyplní SimteGen sám** při prvním automatickém vydání (po tomhle ručním).",
            "Chceš-li ji mít hned: Obsah aplikace → Bezpečnost údajů → Importovat z CSV →",
            "`bezpecnost_dat.csv` z této složky → Uložit.",
            "",
        ]
    if zaznam:
        z, n, h = k["vychozi_zaznam"], k["nastaveni_obchodu"], k["hodnoceni_obsahu"]
        radky += [
            "### Výchozí záznam v obchodě — jednou ručně",
            "",
            "Zvýšení počtu uživatelů → Prezentace v Obchodě → Záznamy v obchodě → **Vytvořit výchozí",
            "záznam**. API záznam jen upravuje, nezaloží ho; přesné hodnoty pak přepisuje každé vydání.",
            "",
            f"- **Název aplikace:** {z['nazev']}",
            f"- **Krátký popis:** {z['kratky_popis']}",
            f"- **Ikona:** `{z['ikona']}` · **Grafika:** `{z['grafika']}`",
            f"- **Snímky z telefonu:** {', '.join(f'`{s}`' for s in z['telefon']) or '—'}",
            f"- **Tablet 7\" i 10\":** {', '.join(f'`{s}`' for s in z['tablet_7']) or '—'}",
            "- **Úplný popis:**",
            "",
            "```",
            z["dlouhy_popis"],
            "```",
            "",
            "Při uložení se Google zeptá na **podklady vytvořené pomocí AI** — to je tvoje prohlášení.",
            "",
            "### Nastavení obchodu",
            "",
            f"- **Aplikace/hra:** {n['typ']} (zkontroluj — u Pneuskladu tam bylo „Hra“)",
            f"- **Kategorie:** {n['kategorie']} (`{n['kategorie_kod']}`)",
            f"- **E-mail:** `{n['email']}` · **Web:** `{n['web']}` · telefon nevyplňuj",
            "",
            "### Obsah aplikace (Panel → Nastavení aplikace, nebo Sledování a vylepšování → Zásady a programy → Obsah aplikace)",
            "",
            f"- **Zásady ochrany soukromí:** `{k['zasady_url']}`",
            f"- **Reklamy:** obsahuje aplikace reklamy? {_ano(k['reklamy'])}",
        ]
        if k["pristup"]["omezeny"]:
            radky += [
                "- **Přihlašovací údaje (dřív Přístup k aplikaci):** Ano, část je omezená → Zadejte",
                "  podrobnosti → název `Ukázka`, jméno a heslo nevyplňuj, do „Další informace“ níž;",
                "  povinné prohlášení o plném přístupu zaškrtáváš ty:",
                "",
                "  ```",
                f"  {k['pristup']['pokyny']}",
                "  ```",
            ]
        else:
            radky.append("- **Přihlašovací údaje:** Ne, žádná část aplikace není omezená.")
        ad_id = k["inzertni_id"]
        radky += [
            f"- **Cílové publikum:** {', '.join(k['cilova_skupina']['vek'])} (až po přihlašovacích údajích)",
            f"- **Státní aplikace:** {_ano(k['vladni'])} · **Finanční funkce:** {k['financni_funkce']} · "
            f"**Zdraví:** {k['zdravi']}",
            "- **Inzertní ID:** " + ("**Ne** (balíček oprávnění AD_ID nemá)" if ad_id is False else
                                     "**Ano** — balíček žádá AD_ID, zjisti proč" if ad_id else
                                     "zkontroluj v balíčku, jestli žádá AD_ID"),
            f"- **Hodnocení obsahu:** e-mail `{h['email']}`, „{h['kategorie']}“, souhlas s podmínkami IARC "
            "zaškrtáváš ty; obsah k hodnocení, sdílení obsahu, online obsah, věkově omezené produkty, "
            f"poloha **Ne**; nákup digitálního zboží {_ano(h['digitalni_nakupy'])}"
            + ("; náhodné položky **Ne**" if h["digitalni_nakupy"] else "")
            + "; peněžní odměny/NFT, prohlížeč, zpravodajství/vzdělávání **Ne**.",
            f"- **Na tobě:** {'; '.join(k['majitel'])}.",
            "",
            "Totéž strojově v `play_console.json` — podle něj to umí vyplnit Claude v tvém Chromu",
            "(skill `play-nova-aplikace` v repu SimteGenu; každé uložení potvrzuješ ty).",
        ]
    else:
        radky += ["Produkt zatím nemá záznam v obchodě (vznikne s jeho příští stavbou)."]
    cil = adresar / "obchod" / "PRVNI_VYDANI.md"
    cil.parent.mkdir(parents=True, exist_ok=True)
    cil.write_text("\n".join(radky) + "\n", encoding="utf-8")
    return cil


def main(argv: list[str]) -> int:
    if len(argv) >= 2 and argv[1] == "priprav":
        priprav(os.environ["PROJEKT"], os.environ.get("DOMENA", ""))
        return 0
    if len(argv) >= 2 and argv[1] == "vysledek":
        VYSTUP.mkdir(exist_ok=True)
        print(json.dumps(vysledek(), ensure_ascii=False))
        return 0
    if len(argv) >= 2 and argv[1] == "navod":
        # The form first, so the guide can point at it. A form that does not
        # fit the template costs the form, not the release.
        try:
            formular = bezpecnost()
            if formular:
                print(f"Bezpečnost údajů: {formular}")
        except (Exception, SystemExit) as e:  # noqa: BLE001
            print(f"::warning::Bezpečnost údajů nejde vygenerovat: {e}")
        print(f"Návod pro první vydání: {navod()}")
        return 0
    if len(argv) >= 3 and argv[1] == "nahraj":
        nahraj(argv[2])
        return 0
    if len(argv) >= 2 and argv[1] == "otisk":
        twa = json.loads((VYSTUP / "twa-manifest.json").read_text(encoding="utf-8"))
        zamek = Path(__file__).with_name("bubblewrap.lock.json")
        generator = os.environ.get("BUBBLEWRAP", "") + (f" {_sha(zamek.read_text(encoding='utf-8'))}"
                                                       if zamek.exists() else "")
        otisk = otisk_obalu(twa, generator)
        vystup = os.environ.get("GITHUB_OUTPUT")
        if vystup:
            with open(vystup, "a", encoding="utf-8") as f:
                f.write(f"otisk={otisk}\n")
        print(f"Otisk obalu aplikace: {otisk[:12]}")
        return 0
    if len(argv) >= 2 and argv[1] == "zapis":
        VYSTUP.mkdir(exist_ok=True)
        print(json.dumps(zapis(), ensure_ascii=False))
        return 0
    if len(argv) >= 2 and argv[1] == "gradle":
        print(f"Gradle připnutý na otisk {pripni_gradle()[:12]}…")
        return 0
    if len(argv) >= 2 and argv[1] == "povys":
        return 1 if povys_z_prostredi()["stav"] == "chyba" else 0
    print("Použití: vydani.py priprav | nahraj <soubor.aab> | otisk | povys | vysledek | navod")
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
