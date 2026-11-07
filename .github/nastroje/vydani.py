"""Android release of one product — run by the Vydani workflow.

Two steps, both deterministic, no model anywhere:

  priprav   reads the product's LIVE web manifest (the production site is
            the single source of truth: name, colours, icons and the Play
            package in related_applications — all written by
            vykresli_aplikaci.py and deployed by the product's own CI) and
            writes twa-manifest.json for Bubblewrap, with a version code
            that only ever grows.
  nahraj    uploads the signed bundle to Google Play through the Android
            Publisher API, INTERNAL track only. Promotion to production is
            the owner's tap in Play Console — the one step of the release
            cycle that stays human, on purpose.

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


def priprav(projekt: str, domena: str = "") -> dict:
    host = domena.strip() or f"{projekt}.pages.dev"
    nakupy = nakupy_v_produktu(host)
    twa = twa_manifest(_stahni_manifest(host), host, nakupy=nakupy)
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


def _ok(odpoved, co):
    if odpoved.status_code >= 300:
        raise SystemExit(f"Google Play: {co} selhalo ({odpoved.status_code}): {odpoved.text[:500]}")
    return odpoved.json() if odpoved.text else {}


def nahraj_zaznam(session, balicek: str, edit: str, obchod: Path, host: str) -> list[str]:
    """The store listing into the same edit as the bundle: texts from the
    product's play/zaznam.json (generated from its manifest — the same claims
    as its privacy policy), contacts, and the images the release rendered
    from the product (vizualni_kontrola.py --obchod). Images are replaced
    wholesale, so a removed screen does not linger in the store. Returns
    what was uploaded, for the summary."""
    zaznam = json.loads((obchod / "zaznam.json").read_text(encoding="utf-8"))
    jazyk = zaznam.get("jazyk") or "cs-CZ"
    zaklad = f"{_API}/{balicek}/edits/{edit}"
    _ok(session.put(f"{zaklad}/listings/{jazyk}", json={
        "language": jazyk, "title": zaznam["nazev"], "shortDescription": zaznam["kratky_popis"],
        "fullDescription": zaznam["dlouhy_popis"]}), "záznam v obchodě")
    _ok(session.patch(f"{zaklad}/details", json={
        "defaultLanguage": jazyk, "contactEmail": zaznam["kontakt_email"],
        "contactWebsite": f"https://{host}"}), "kontakty v obchodě")
    nahrano = ["texty"]
    # One set of tablet pictures serves both of Google's tablet sizes; without
    # any, Play hardly offers the app on tablets.
    tablety = sorted(obchod.glob("tablet-*.jpg"))
    for typ, soubory in (("phoneScreenshots", sorted(obchod.glob("telefon-*.jpg"))),
                         ("sevenInchScreenshots", tablety),
                         ("tenInchScreenshots", tablety),
                         ("featureGraphic", [obchod / "grafika.jpg"]),
                         ("icon", [obchod / "ikona.png"])):
        soubory = [s for s in soubory if s.exists()]
        if not soubory:
            continue
        _ok(session.delete(f"{zaklad}/listings/{jazyk}/{typ}"), f"smazání starých obrázků {typ}")
        for soubor in soubory:
            _ok(session.post(f"{_UPLOAD}/{balicek}/edits/{edit}/listings/{jazyk}/{typ}?uploadType=media",
                             data=soubor.read_bytes(),
                             headers={"Content-Type": "image/png" if soubor.suffix == ".png" else "image/jpeg"}),
                f"nahrání {soubor.name}")
        nahrano.append(f"{typ} ×{len(soubory)}")
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
    odpovez("PSL_DATA_COLLECTION_COLLECTS_PERSONAL_DATA", hodnota="TRUE" if b["sbira"] else "FALSE")
    if b["sbira"]:
        odpovez("PSL_DATA_COLLECTION_ENCRYPTED_IN_TRANSIT",
                hodnota="TRUE" if b.get("sifrovano_pri_prenosu") else "FALSE")
    if zaznam.get("ucty"):
        # The e-mail is the user name, the one-time link from it the other
        # authentication — no password exists.
        odpovez("PSL_SUPPORTED_ACCOUNT_CREATION_METHODS", "PSL_ACM_USER_ID_OTHER_AUTH")
        odpovez("PSL_ACCOUNT_DELETION_URL", hodnota=adresa + (zaznam.get("smazani_uctu_cesta") or "/zasady.html"))
    else:
        odpovez("PSL_SUPPORTED_ACCOUNT_CREATION_METHODS", "PSL_ACM_NONE")
    if b["sbira"]:
        odpovez("PSL_SUPPORT_DATA_DELETION_BY_USER",
                "DATA_DELETION_YES" if b.get("lze_smazat") else "DATA_DELETION_NO")
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
    _ok(session.post(f"{_API}/{balicek}/dataSafety", json={"safetyLabels": csv_text}), "bezpečnost údajů")


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
# customer pays); other countries get Google's own conversion of it.
# Created and activated if missing, repriced if the approved price moved
# (Google keeps existing subscribers on their price), never deleted.

ZAKLADNI_PLAN = "zakladni"
_DPH = 1.21


def _penize(mena: str, castka: float) -> dict:
    cele = int(castka)
    return {"currencyCode": mena, "units": str(cele), "nanos": int(round((castka - cele) * 1e9))}


def _plan(polozka: dict, prevod: dict) -> dict:
    regiony = []
    for kod, p in (prevod.get("convertedRegionPrices") or {}).items():
        cena = p.get("price")
        if kod == "CZ":
            cena = _penize("CZK", float(polozka["cena_czk"]))
        regiony.append({"regionCode": kod, "newSubscriberAvailability": True, "price": cena})
    if not any(r["regionCode"] == "CZ" for r in regiony):
        regiony.append({"regionCode": "CZ", "newSubscriberAvailability": True,
                        "price": _penize("CZK", float(polozka["cena_czk"]))})
    plan = {"basePlanId": ZAKLADNI_PLAN, "regionalConfigs": sorted(regiony, key=lambda r: r["regionCode"]),
            "autoRenewingBasePlanType": {"billingPeriodDuration": polozka["obdobi"]}}
    jine = prevod.get("convertedOtherRegionsPrice") or {}
    if jine.get("usdPrice") and jine.get("eurPrice"):
        plan["otherRegionsConfig"] = {"usdPrice": jine["usdPrice"], "eurPrice": jine["eurPrice"],
                                      "newSubscriberAvailability": True}
    return plan


def _cz_cena(predplatne: dict) -> float | None:
    for plan in predplatne.get("basePlans") or []:
        for r in plan.get("regionalConfigs") or []:
            if r.get("regionCode") == "CZ" and r.get("price"):
                return int(r["price"].get("units") or 0) + int(r["price"].get("nanos") or 0) / 1e9
    return None


def nahraj_predplatne(session, balicek: str, polozky: list[dict], nazev: str) -> list[str]:
    """Create / reprice the app's subscription products. Returns one line
    per product for the summary; raises SystemExit with Google's words."""
    hotovo = []
    for polozka in polozky:
        pid = polozka["id"]
        rocni = polozka["obdobi"] == "P1Y"
        prevod = _ok(session.post(f"{_API}/{balicek}/pricing:convertRegionPrices", json={
            "price": _penize("CZK", round(float(polozka["cena_czk"]) / _DPH, 2))}), "převod ceny do zemí")
        verze = (prevod.get("regionVersion") or {}).get("version") or "2022/02"
        telo = {
            "packageName": balicek, "productId": pid,
            "listings": [{"languageCode": "cs-CZ",
                          "title": f"{nazev[:40]} — {'roční' if rocni else 'měsíční'} předplatné",
                          "benefits": ["Všechny funkce bez omezení", "Stejný účet v aplikaci i na webu"],
                          "description": "Předplatné se automaticky obnovuje, zrušit ho lze kdykoli v Google Play."}],
            "basePlans": [_plan(polozka, prevod)],
        }
        odpoved = session.get(f"{_API}/{balicek}/subscriptions/{pid}")
        if odpoved.status_code == 404:
            _ok(session.post(f"{_API}/{balicek}/subscriptions",
                             params={"productId": pid, "regionsVersion.version": verze}, json=telo),
                f"založení předplatného {pid}")
            _ok(session.post(f"{_API}/{balicek}/subscriptions/{pid}/basePlans/{ZAKLADNI_PLAN}:activate",
                             json={}), f"zapnutí předplatného {pid}")
            hotovo.append(f"{pid}: založeno za {polozka['cena_czk']} Kč")
            continue
        stavajici = _ok(odpoved, f"čtení předplatného {pid}")
        if _cz_cena(stavajici) == float(polozka["cena_czk"]):
            hotovo.append(f"{pid}: beze změny ({polozka['cena_czk']} Kč)")
            continue
        _ok(session.patch(f"{_API}/{balicek}/subscriptions/{pid}",
                          params={"updateMask": "basePlans", "regionsVersion.version": verze}, json=telo),
            f"změna ceny předplatného {pid}")
        hotovo.append(f"{pid}: nová cena {polozka['cena_czk']} Kč (stávající předplatitelé platí dál původní)")
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
            vysledek.append({"id": p["id"], "obdobi": p["obdobi"], "cena_czk": p["cena_czk"]})
    return vysledek


NEZNAMA = "neznama"


def nahraj_bundle(session, balicek: str, bundle: bytes, nazev_verze: str, poznamka: str,
                  pred_potvrzenim=None) -> dict:
    """One edit: insert → upload bundle → internal track → (listing) →
    commit. `session` is an authorised requests-like session (tests pass a
    fake); `pred_potvrzenim(edit)` adds to the same edit before the commit,
    so a release and its listing land together or not at all. Returns
    {"versionCode", "status"}; status "neznama" when Google does not know
    the package yet (the first upload is a human's, the API refuses it);
    raises SystemExit with Google's words on anything else."""
    ok = _ok

    odpoved = session.post(f"{_API}/{balicek}/edits", json={})
    if odpoved.status_code == 404:
        # Not a failure: the build is fine and the .aab in the artifact is
        # exactly what the owner uploads. As a failed job it read "sestavení
        # selhalo" after every deploy.
        return {"versionCode": None, "status": NEZNAMA, "zaznam": None}
    edit = ok(odpoved, "založení úpravy")["id"]
    nahrano = ok(session.post(f"{_UPLOAD}/{balicek}/edits/{edit}/bundles?uploadType=media", data=bundle,
                              headers={"Content-Type": "application/octet-stream"}, timeout=900),
                 "nahrání balíčku")
    kod = str(nahrano["versionCode"])
    vydani = {"name": nazev_verze, "versionCodes": [kod], "status": "completed",
              "releaseNotes": [{"language": "cs-CZ", "text": poznamka[:500] or "Průběžné vydání."}]}
    odpoved = session.put(f"{_API}/{balicek}/edits/{edit}/tracks/internal",
                          json={"track": "internal", "releases": [vydani]})
    if odpoved.status_code == 400 and "draft" in odpoved.text.lower():
        # Never-published app: Google takes only drafts until the first
        # release is sent from the console.
        vydani["status"] = "draft"
        odpoved = session.put(f"{_API}/{balicek}/edits/{edit}/tracks/internal",
                              json={"track": "internal", "releases": [vydani]})
    ok(odpoved, "zařazení do interního testování")
    zaznam = pred_potvrzenim(edit) if pred_potvrzenim else None
    ok(session.post(f"{_API}/{balicek}/edits/{edit}:commit"), "potvrzení úpravy")
    return {"versionCode": kod, "status": vydani["status"], "zaznam": zaznam}


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
    zaznam = ((lambda edit: nahraj_zaznam(session, twa["packageId"], edit, obchod, twa["host"]))
              if (obchod / "zaznam.json").exists() else None)
    vysledek = nahraj_bundle(session, twa["packageId"], Path(cesta_bundle).read_bytes(),
                             twa["appVersionName"], poznamka_k_vydani(), pred_potvrzenim=zaznam)
    vystup = os.environ.get("GITHUB_OUTPUT")
    if vysledek["status"] == NEZNAMA:
        print(f"Google Play aplikaci {twa['packageId']} zatím nezná. První verzi nahraj ručně v Play Console "
              "(Interní testování → Vytvořit vydání → soubor .aab z artefaktu tohoto běhu).")
        if vystup:
            with open(vystup, "a", encoding="utf-8") as f:
                f.write(f"stav={NEZNAMA}\n")
        return vysledek
    if vysledek.get("zaznam"):
        print("Záznam v obchodě:", ", ".join(vysledek["zaznam"]))
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
            print(f"::warning::Bezpečnost údajů se nepodařilo nahrát: {e}")
        if vystup:
            with open(vystup, "a", encoding="utf-8") as f:
                f.write(f"bezpecnost={'1' if vysledek['bezpecnost'] else '0'}\n")
    polozky = predplatne_ze_vstupu(os.environ.get("PREDPLATNE", ""))
    if polozky and twa.get("features", {}).get("playBilling"):
        # Like the form: the release is in; a refused price is reported,
        # and the next release tries again.
        try:
            vysledek["predplatne"] = nahraj_predplatne(session, twa["packageId"], polozky, twa.get("name") or "")
            print("Předplatné v Google Play:", "; ".join(vysledek["predplatne"]))
            stav_predplatneho = "1"
        except (Exception, SystemExit) as e:  # noqa: BLE001
            print(f"::warning::Předplatné v Google Play se nepodařilo nastavit: {e}")
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
        # None: not attempted (no listing, unknown app, no upload at all).
        "bezpecnost_dat": {"1": True, "0": False}.get(env.get("BEZPECNOST", "")),
        # Selling in the app: built with Play Billing; subscription products
        # in Play set (None = nothing to set: no approved price, no billing).
        "nakupy": env.get("NAKUPY") == "1",
        "predplatne_play": {"1": True, "0": False}.get(env.get("PREDPLATNE_PLAY", "")),
        "run_url": env.get("RUN_URL", ""),
        "cas": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    (VYSTUP / "vysledek.json").write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    return data


def navod(adresar: Path = VYSTUP) -> Path:
    """obchod/PRVNI_VYDANI.md: the owner's first upload, every value filled
    in. Play Console asks for the package when the app is created and never
    lets it change again — so the guide names it, not the owner's memory.
    Written into every artifact; it costs nothing and a later reader of an
    old run still gets the right values for that build."""
    twa = json.loads((adresar / "twa-manifest.json").read_text(encoding="utf-8"))
    zaznam_soubor = adresar / "obchod" / "zaznam.json"
    zaznam = json.loads(zaznam_soubor.read_text(encoding="utf-8")) if zaznam_soubor.exists() else {}
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
        radky += [
            "Ostatní prohlášení (reklamy, cílová skupina, hodnocení obsahu) podle `BEZPECNOST_DAT.md` ve stejné složce:",
            "",
            f"- Kategorie: `{zaznam.get('kategorie')}`, kontaktní e-mail: `{zaznam.get('kontakt_email')}`",
            f"- Web: `https://{host}`",
            f"- Zásady ochrany soukromí: `https://{host}{zaznam.get('zasady_cesta') or '/zasady.html'}`",
            "- Texty, ikona, grafika a snímky se nahrávají samy s každým vydáním.",
            "- Přístup k aplikaci (pro kontrolora Googlu): hotový text je v `BEZPECNOST_DAT.md` — "
            "kontrolor klepne na „Vyzkoušet ukázku“, žádné heslo.",
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
    print("Použití: vydani.py priprav | vydani.py nahraj <soubor.aab>")
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
