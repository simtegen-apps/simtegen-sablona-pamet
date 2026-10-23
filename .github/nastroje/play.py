"""Google Play data for SimteGen — run by the Play and Play odpoved workflows.

  stahni <vetev>   for every released app (vydani/*.json in the metriky
                   branch checkout): Android vitals (crash and ANR rates,
                   Play Developer Reporting API), new reviews (Android
                   Publisher API) and the fingerprint of the key Google signs
                   the app with (generatedApks) → play/<projekt>.json in the
                   same checkout. Without the service account it records only
                   "not connected", so SimteGen can say so instead of
                   guessing.
  odpovez          one reply to one review (env BALICEK, RECENZE, TEXT).
                   The workflow runs it only after over_pokyn.py accepted
                   SimteGen's signature: a public reply in the company's name
                   is not something a stolen bot token may do.

What leaves Google: numbers, and review texts with their stars — public on
the store page anyway. The author's name stays out: SimteGen does not need
to know who wrote it to fix what they wrote about.
"""

from __future__ import annotations

import base64
import json
import os
import re
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

_PUBLISHER = "https://androidpublisher.googleapis.com/androidpublisher/v3/applications"
_REPORTING = "https://playdeveloperreporting.googleapis.com/v1beta1/apps"
_SCOPES = ["https://www.googleapis.com/auth/androidpublisher",
           "https://www.googleapis.com/auth/playdeveloperreporting"]
MAX_ODPOVED = 350  # Play's limit for a developer reply


def _session():
    from google.auth.transport.requests import AuthorizedSession
    from google.oauth2 import service_account

    ucet = json.loads(os.environ["PLAY_SERVICE_ACCOUNT_JSON"])
    return AuthorizedSession(service_account.Credentials.from_service_account_info(ucet, scopes=_SCOPES))


def _ok(odpoved, co):
    if odpoved.status_code >= 300:
        raise RuntimeError(f"{co}: {odpoved.status_code} {odpoved.text[:300]}")
    return odpoved.json() if odpoved.text else {}


def _vitals(session, balicek: str, sada: str, metriky: list[str]) -> dict:
    """The newest complete day of one vitals metric set. Google publishes
    with a delay; the freshness info says which day is complete."""
    info = _ok(session.get(f"{_REPORTING}/{balicek}/{sada}"), sada)
    denni = next((f for f in (info.get("freshnessInfo") or {}).get("freshnesses") or []
                  if f.get("aggregationPeriod") == "DAILY"), None)
    if not denni:
        return {}
    konec = denni["latestEndTime"]
    den = date(konec["year"], konec["month"], konec["day"]) - timedelta(days=1)
    spec = {"aggregationPeriod": "DAILY",
            "startTime": {"year": den.year, "month": den.month, "day": den.day, "timeZone": konec.get("timeZone")},
            "endTime": konec}
    data = _ok(session.post(f"{_REPORTING}/{balicek}/{sada}:query",
                            json={"timelineSpec": spec, "metrics": metriky}), f"{sada}:query")
    radek = (data.get("rows") or [{}])[-1]
    vysledek = {"den": den.isoformat()}
    for m in radek.get("metrics") or []:
        hodnota = (m.get("decimalValue") or {}).get("value")
        if hodnota is not None:
            vysledek[m["metric"]] = float(hodnota)
    return vysledek


def otisk_z_hashe(hodnota: str) -> str | None:
    """Google's certificateSha256Hash → the AB:CD:… form assetlinks and Play
    Console use. The API sends exactly that form (seen 18. 10. 2026 on
    Kusovník); bare hex and base64 are accepted too, in case it changes."""
    hodnota = (hodnota or "").strip()
    if re.fullmatch(r"([0-9a-fA-F]{2}:){31}[0-9a-fA-F]{2}", hodnota):
        hodnota = hodnota.replace(":", "")
    if re.fullmatch(r"[0-9a-fA-F]{64}", hodnota):
        surove = bytes.fromhex(hodnota)
    else:
        try:
            surove = base64.b64decode(hodnota + "=" * (-len(hodnota) % 4), validate=False)
        except ValueError:
            return None
    if len(surove) != 32:
        return None
    return ":".join(f"{b:02X}" for b in surove)


def _v_play(session, balicek: str) -> dict | None:
    """What Google knows about a package: None when it does not know it
    (the first upload is a human's), else the newest version code on any
    track and the app signing key's fingerprint. Reads through an edit and
    throws the edit away — nothing is changed."""
    odpoved = session.post(f"{_PUBLISHER}/{balicek}/edits", json={})
    if odpoved.status_code == 404:
        return None
    edit = _ok(odpoved, "úprava (jen čtení)")["id"]
    try:
        stopy = _ok(session.get(f"{_PUBLISHER}/{balicek}/edits/{edit}/tracks"), "kanály").get("tracks") or []
    finally:
        session.delete(f"{_PUBLISHER}/{balicek}/edits/{edit}")
    kody = [int(k) for t in stopy for r in t.get("releases") or [] for k in r.get("versionCodes") or []]
    if not kody:
        return {"kod": None, "otisk": None}
    kod = max(kody)
    apk = _ok(session.get(f"{_PUBLISHER}/{balicek}/generatedApks/{kod}"), "vygenerované APK")
    otisky = [otisk_z_hashe(g.get("certificateSha256Hash")) for g in apk.get("generatedApks") or []]
    return {"kod": kod, "otisk": next((o for o in otisky if o), None)}


def _recenze(session, balicek: str) -> list[dict]:
    data = _ok(session.get(f"{_PUBLISHER}/{balicek}/reviews", params={"maxResults": 50}), "reviews")
    vystup = []
    for r in data.get("reviews") or []:
        uzivatel = next((c["userComment"] for c in r.get("comments") or [] if "userComment" in c), None)
        if not uzivatel:
            continue
        odpoved = any("developerComment" in c for c in r.get("comments") or [])
        cas = (uzivatel.get("lastModified") or {}).get("seconds")
        vystup.append({
            "id": r.get("reviewId"),
            "hvezdy": uzivatel.get("starRating"),
            "text": (uzivatel.get("text") or "").strip()[:2000],
            "jazyk": uzivatel.get("reviewerLanguage"),
            "cas": datetime.fromtimestamp(int(cas), timezone.utc).isoformat() if cas else None,
            "odpovezeno": odpoved,
        })
    return vystup


def stahni(vetev: Path) -> int:
    ted = datetime.now(timezone.utc).isoformat(timespec="seconds")
    (vetev / "play").mkdir(parents=True, exist_ok=True)
    pripojeno = bool(os.environ.get("PLAY_SERVICE_ACCOUNT_JSON"))
    (vetev / "play" / "_stav.json").write_text(json.dumps({"pripojeno": pripojeno, "cas": ted}), encoding="utf-8")
    if not pripojeno:
        print("Bez PLAY_SERVICE_ACCOUNT_JSON — zapsáno jen „nepřipojeno“.")
        return 0
    session = _session()
    hotovo = 0
    for soubor in sorted((vetev / "vydani").glob("*.json")):
        projekt = soubor.stem
        vydani = json.loads(soubor.read_text(encoding="utf-8"))
        predtim = vetev / "play" / f"{projekt}.json"
        znamy = (json.loads(predtim.read_text(encoding="utf-8")).get("balicek") if predtim.exists() else None)
        # The package Google knows wins: a build may still carry an older
        # manifest's package until the product's PR with the new one lands.
        kandidati = [b for b in dict.fromkeys([znamy, vydani.get("balicek")]) if b]
        if not kandidati:
            continue
        zaznam = {"cas": ted, "balicek": kandidati[-1], "v_play": False, "kod": None, "otisk": None,
                  "vitals": None, "recenze": [], "chyba": None}
        try:
            for balicek in kandidati:
                info = _v_play(session, balicek)
                if info is not None:
                    zaznam.update(balicek=balicek, v_play=True, kod=info["kod"], otisk=info["otisk"])
                    break
            balicek = zaznam["balicek"]
            if not zaznam["v_play"]:
                (vetev / "play" / f"{projekt}.json").write_text(
                    json.dumps(zaznam, ensure_ascii=False, indent=1), encoding="utf-8")
                print(f"{projekt}: Google Play aplikaci zatím nezná.")
                continue
            # A new app has no vitals yet and Google answers 404. That used
            # to fail the whole app, reviews included — vitals and reviews
            # are separate questions.
            try:
                pady = _vitals(session, balicek, "crashRateMetricSet",
                               ["crashRate", "userPerceivedCrashRate", "distinctUsers"])
                zamrznuti = _vitals(session, balicek, "anrRateMetricSet", ["anrRate", "userPerceivedAnrRate"])
            except RuntimeError as e:
                if " 404 " not in str(e):
                    raise
                pady, zamrznuti = {}, {}
            if pady or zamrznuti:
                zaznam["vitals"] = {
                    "den": pady.get("den") or zamrznuti.get("den"),
                    "pady": pady.get("crashRate"), "pady_uzivatele": pady.get("userPerceivedCrashRate"),
                    "zamrznuti": zamrznuti.get("anrRate"),
                    "zamrznuti_uzivatele": zamrznuti.get("userPerceivedAnrRate"),
                    "uzivatele": pady.get("distinctUsers"),
                }
            zaznam["recenze"] = _recenze(session, balicek)
        except Exception as e:  # noqa: BLE001 — one app's failure must not hide the others
            zaznam["chyba"] = str(e)[:300]
        (vetev / "play" / f"{projekt}.json").write_text(json.dumps(zaznam, ensure_ascii=False, indent=1),
                                                       encoding="utf-8")
        hotovo += 1
        print(f"{projekt}: {balicek}, otisk {'ano' if zaznam['otisk'] else 'ne'}, "
              f"{len(zaznam['recenze'])} recenzí, vitals {'ano' if zaznam['vitals'] else 'ne'}"
              + (f", chyba: {zaznam['chyba']}" if zaznam["chyba"] else ""))
    return hotovo


def odpovez() -> None:
    balicek, recenze = os.environ["BALICEK"], os.environ["RECENZE"]
    text = os.environ["TEXT"].strip()[:MAX_ODPOVED]
    if not text:
        raise SystemExit("Prázdná odpověď se neposílá.")
    _ok(_session().post(f"{_PUBLISHER}/{balicek}/reviews/{recenze}:reply", json={"replyText": text}),
        "odpověď na recenzi")
    print(f"Odpověď na recenzi {recenze} odeslána.")


def main(argv: list[str]) -> int:
    if len(argv) >= 3 and argv[1] == "stahni":
        stahni(Path(argv[2]))
        return 0
    if len(argv) >= 2 and argv[1] == "odpovez":
        odpovez()
        return 0
    print("Použití: play.py stahni <vetev> | play.py odpovez")
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
