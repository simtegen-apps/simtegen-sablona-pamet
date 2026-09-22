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
"""

from __future__ import annotations

import json
import os
import sys
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


def twa_manifest(manifest: dict, host: str, ted: datetime | None = None) -> dict:
    """Bubblewrap's project description, from the live web manifest."""
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
        "enableNotifications": False,
        "startUrl": manifest.get("start_url") or "/",
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
        "features": {},
        "alphaDependencies": {"enabled": False},
        "enableSiteSettingsShortcut": True,
        "isChromeOSOnly": False,
        "isMetaQuest": False,
        "fullScopeUrl": f"{zaklad}/",
        "minSdkVersion": 21,
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


def priprav(projekt: str, domena: str = "") -> dict:
    host = domena.strip() or f"{projekt}.pages.dev"
    twa = twa_manifest(_stahni_manifest(host), host)
    VYSTUP.mkdir(exist_ok=True)
    (VYSTUP / "twa-manifest.json").write_text(json.dumps(twa, ensure_ascii=False, indent=2), encoding="utf-8")
    vystup = os.environ.get("GITHUB_OUTPUT")
    if vystup:
        with open(vystup, "a", encoding="utf-8") as f:
            f.write(f"balicek={twa['packageId']}\nverze={twa['appVersionName']}\nkod={twa['appVersionCode']}\n")
    print(f"Připraveno: {twa['packageId']} {twa['appVersionName']} (kód {twa['appVersionCode']}) z https://{host}")
    return twa


# ── Upload ────────────────────────────────────────────────────────────

_API = "https://androidpublisher.googleapis.com/androidpublisher/v3/applications"
_UPLOAD = "https://androidpublisher.googleapis.com/upload/androidpublisher/v3/applications"


def nahraj_bundle(session, balicek: str, bundle: bytes, nazev_verze: str, poznamka: str) -> dict:
    """One edit: insert → upload bundle → internal track → commit. `session`
    is an authorised requests-like session (tests pass a fake). Returns
    {"versionCode", "status"}; raises SystemExit with Google's words."""
    def ok(odpoved, co):
        if odpoved.status_code >= 300:
            raise SystemExit(f"Google Play: {co} selhalo ({odpoved.status_code}): {odpoved.text[:500]}")
        return odpoved.json() if odpoved.text else {}

    odpoved = session.post(f"{_API}/{balicek}/edits", json={})
    if odpoved.status_code == 404:
        raise SystemExit(f"Google Play aplikaci {balicek} nezná. První verzi nahraj ručně v Play Console "
                         "(Interní testování → Vytvořit vydání → soubor .aab z artefaktu tohoto běhu).")
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
    ok(session.post(f"{_API}/{balicek}/edits/{edit}:commit"), "potvrzení úpravy")
    return {"versionCode": kod, "status": vydani["status"]}


def nahraj(cesta_bundle: str) -> dict:
    from google.auth.transport.requests import AuthorizedSession
    from google.oauth2 import service_account

    ucet = json.loads(os.environ["PLAY_SERVICE_ACCOUNT_JSON"])
    pristup = service_account.Credentials.from_service_account_info(
        ucet, scopes=["https://www.googleapis.com/auth/androidpublisher"])
    twa = json.loads((VYSTUP / "twa-manifest.json").read_text(encoding="utf-8"))
    vysledek = nahraj_bundle(AuthorizedSession(pristup), twa["packageId"], Path(cesta_bundle).read_bytes(),
                             twa["appVersionName"], os.environ.get("POZNAMKA", ""))
    stav = ("připraveno jako koncept — aplikace ještě nebyla vydána, první vydání pošli v Play Console"
            if vysledek["status"] == "draft" else "v interním testování")
    print(f"Nahráno: {twa['packageId']} kód {vysledek['versionCode']}, {stav}.")
    vystup = os.environ.get("GITHUB_OUTPUT")
    if vystup:
        with open(vystup, "a", encoding="utf-8") as f:
            f.write(f"stav={vysledek['status']}\n")
    return vysledek


def main(argv: list[str]) -> int:
    if len(argv) >= 2 and argv[1] == "priprav":
        priprav(os.environ["PROJEKT"], os.environ.get("DOMENA", ""))
        return 0
    if len(argv) >= 3 and argv[1] == "nahraj":
        nahraj(argv[2])
        return 0
    print("Použití: vydani.py priprav | vydani.py nahraj <soubor.aab>")
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
