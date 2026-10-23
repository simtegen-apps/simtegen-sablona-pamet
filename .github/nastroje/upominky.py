"""Trial reminders — run once a day by the Upominky workflow in the template repo.

Pages Functions have no scheduler, so the reminders live where the other
scheduled work over the products' databases lives (Metriky): GitHub Actions
in the template repo, org secrets, one pass over every product with a D1
database `<repo>-db`. Nothing to add to a product but the template refresh.

Who gets one: an account the PRODUCT says is in its trial — the end date
comes from `zkusebni_doba`, which the template middleware copies from the
product's own predplatne.js on every /api/ja (the products disagree on the
trial: 14 days, a shop-owned trial with its own date). Never one that paid
(a row in `platby`, Play or invoice alike) or holds a paid period past the
trial end, never a demo account.

Which ones, and why these three:

  pred_3  2–3 calendar days before the end — an invoice paid by bank
          transfer takes a working day or two to arrive and be marked,
          so this is the last moment to pay without a gap
  pred_1  the day before (or the last day, if the run missed it)
  konec   after the end, at most three days late: says what still works
          and how to continue; the last one — nothing follows it

Each at most once per account: the row in `upominky` is claimed first
(INSERT OR IGNORE … RETURNING) and only a claimed row is sent; a failed send
gives the claim back, so tomorrow's run tries again. The bias is at most
once — a customer must never get the same mail twice.

Transactional, not marketing (contract performance, GDPR art. 6/1/b): the
end of the customer's own trial, the product's name, the way to pay — no
offers, no other products. The privacy policy says so (manifest entities
zkusebni_doba and upominky). The logs are public (public repo): they carry
counts only, never an address.

Without RESEND_API_KEY / EMAIL_ODESILATEL nothing is claimed or sent and
the run succeeds — the same development mode as the login. NANECISTO=true
only counts who would get what.

Stdlib only; the arithmetic is integers; no model anywhere.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.request
from datetime import date, datetime, timedelta, timezone

DEN = 86400
UKAZKOVY_UCET = "@ukazka.invalid"
DRUHY = ("pred_3", "pred_1", "konec")


# ── Pure helpers (tested without a runner) ────────────────────────────

def _posledni_nedele(rok: int, mesic: int) -> date:
    konec = date(rok, mesic + 1, 1) - timedelta(days=1) if mesic < 12 else date(rok, 12, 31)
    return konec - timedelta(days=(konec.weekday() + 1) % 7)


def den_v_cesku(unix: int) -> date:
    """The calendar day in Prague. EU summer time by its rule (last Sunday
    of March to last Sunday of October, 01:00 UTC) — no tz database needed,
    and "zítra" must mean tomorrow where the customer lives."""
    utc = datetime.fromtimestamp(unix, tz=timezone.utc)
    rok = utc.year
    od = datetime.combine(_posledni_nedele(rok, 3), datetime.min.time(), timezone.utc) + timedelta(hours=1)
    do = datetime.combine(_posledni_nedele(rok, 10), datetime.min.time(), timezone.utc) + timedelta(hours=1)
    posun = 2 if od <= utc < do else 1
    return (utc + timedelta(hours=posun)).date()


def druh_upominky(konec: int, nyni: int) -> str | None:
    """Which reminder is due for a trial ending at `konec`, or None."""
    if konec <= nyni:
        return "konec" if nyni - konec < 3 * DEN else None
    dni = (den_v_cesku(konec) - den_v_cesku(nyni)).days
    if 2 <= dni <= 3:
        return "pred_3"
    if dni <= 1:
        return "pred_1"
    return None


def cz_datum(unix: int) -> str:
    d = den_v_cesku(unix)
    return f"{d.day}. {d.month}. {d.year}"


def _dny(n: int) -> str:
    return "den" if n == 1 else ("dny" if 2 <= n <= 4 else "dní")


def zprava(druh: str, manifest: dict, repo: str, konec: int, nyni: int) -> tuple[str, str]:
    """(subject, text) — short, Czech, the product's name and the way to pay."""
    produkt = str(manifest.get("produkt") or repo).strip()
    adresa = str(manifest.get("adresa") or f"https://{repo}.pages.dev").rstrip("/")
    odkaz = f"{adresa}/?platba"
    datum = cz_datum(konec)
    paticka = (
        "\n\nTento e-mail posíláme, protože vám v naší službě končí zkušební období — je to provozní "
        "zpráva k vašemu účtu, ne reklama.\n"
        + str(manifest.get("provozovatel") or "SimteGen s.r.o.")
        + (f" · {manifest['kontakt_email']}" if manifest.get("kontakt_email") else "") + "\n"
    )
    if druh == "konec":
        return (
            f"{produkt}: zkušební období skončilo",
            f"Dobrý den,\n\nzkušební období služby {produkt} skončilo {datum}. Vaše data zůstávají "
            "uložená: přihlásíte se dál, stáhnete si je nebo účet smažete. Pokračovat v práci půjde po "
            f"objednání předplatného v aplikaci v části Účet:\n{odkaz}\n\n"
            "Tohle je naše poslední upozornění ke zkušebnímu období." + paticka,
        )
    dni = (den_v_cesku(konec) - den_v_cesku(nyni)).days
    kdy = "dnes" if dni <= 0 else "zítra" if dni == 1 else f"za {dni} {_dny(dni)}"
    return (
        f"{produkt}: zkušební období končí {kdy}",
        f"Dobrý den,\n\nzkušební období služby {produkt} končí {kdy} ({datum}). Aby vaše práce "
        "pokračovala bez přerušení, objednejte si předplatné v aplikaci v části Účet:\n"
        f"{odkaz}\n\nVaše data zůstanou uložená i po skončení zkušebního období." + paticka,
    )


def kandidati_sql(nyni: int, s_platbami: bool, s_predplatnym: bool) -> str:
    """Accounts whose trial ends within the reminder windows and who have
    not paid. Integers only go into the text — wrangler has no binds."""
    nyni = int(nyni)
    sql = (
        "SELECT z.uzivatel_id AS id, u.email AS email, z.konec AS konec "
        "FROM zkusebni_doba z JOIN uzivatele u ON u.id = z.uzivatel_id "
        f"WHERE z.konec > {nyni - 3 * DEN} AND z.konec <= {nyni + 4 * DEN} "
        f"AND u.email NOT LIKE '%{UKAZKOVY_UCET}'"
    )
    if s_platbami:
        sql += " AND NOT EXISTS (SELECT 1 FROM platby p WHERE p.uzivatel_id = z.uzivatel_id)"
    if s_predplatnym:
        sql += (" AND NOT EXISTS (SELECT 1 FROM predplatne p WHERE p.uzivatel_id = z.uzivatel_id "
                "AND p.plati_do > z.konec)")
    return sql


# ── D1, GitHub, Resend ────────────────────────────────────────────────

def d1(db: str, sql: str) -> list[dict]:
    run = subprocess.run(
        ["npx", "--yes", "wrangler@3", "d1", "execute", db, "--remote", "--json", "--command", sql],
        capture_output=True, text=True, encoding="utf-8",
    )
    if run.returncode != 0:
        raise RuntimeError(f"D1 selhalo: {run.stderr[-400:]}")
    out = json.loads(run.stdout)
    return (out[0].get("results") or []) if out else []


def produkty(env: dict) -> list[str]:
    """Same discovery as Metriky: an input, this repo, the org variable, or
    every `<repo>-db` on Cloudflare (preview databases end -db-nahled)."""
    if env.get("PROJEKT_VSTUP"):
        seznam = env["PROJEKT_VSTUP"]
    elif env.get("REPO_NAME") and env["REPO_NAME"] != "simtegen-sablona-pamet":
        seznam = env["REPO_NAME"]
    elif env.get("PRODUKTY"):
        seznam = env["PRODUKTY"]
    else:
        run = subprocess.run(["npx", "--yes", "wrangler@3", "d1", "list", "--json"],
                             capture_output=True, text=True, encoding="utf-8")
        if run.returncode != 0:
            raise RuntimeError(f"seznam databází selhal: {run.stderr[-400:]}")
        seznam = ",".join(d["name"][:-3] for d in json.loads(run.stdout) if str(d.get("name", "")).endswith("-db"))
    return [r.strip() for r in seznam.split(",") if r.strip()]


def nacti_manifest(vlastnik: str, repo: str) -> dict:
    """The product's name, address and contact, from its public repo."""
    url = f"https://raw.githubusercontent.com/{vlastnik}/{repo}/HEAD/data-manifest.json"
    with urllib.request.urlopen(url, timeout=30) as r:
        data = json.loads(r.read().decode("utf-8"))
    return data if isinstance(data, dict) else {}


def posli(api_key: str, odesilatel: str, komu: str, odpovedi: str | None, predmet: str, text: str) -> None:
    payload = {"from": odesilatel, "to": [komu], "subject": predmet, "text": text}
    if odpovedi:
        payload["reply_to"] = odpovedi
    req = urllib.request.Request(
        "https://api.resend.com/emails", data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}, method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        if r.status >= 300:
            raise RuntimeError(f"Resend vrátil {r.status}")


# ── One product ───────────────────────────────────────────────────────

def zpracuj(repo: str, env: dict, nyni: int, *, d1=d1, nacti_manifest=nacti_manifest, posli=posli) -> dict:
    """Counts per kind for one product: {"pred_3": n, …, "chyby": n} or
    {"preskoceno": reason}. The callables are parameters for the tests."""
    db = f"{repo}-db"
    tabulky = {r["name"] for r in d1(db, "SELECT name FROM sqlite_master WHERE type = 'table' AND name IN "
                                         "('zkusebni_doba', 'upominky', 'platby', 'predplatne')")}
    if not {"zkusebni_doba", "upominky"} <= tabulky:
        return {"preskoceno": "bez migrace 0920 (přijde s obnovou šablony)"}
    kandidati = d1(db, kandidati_sql(nyni, "platby" in tabulky, "predplatne" in tabulky))
    # Public repo, public logs (as in platba.py): every address is masked the
    # moment it is known, so no later error text can carry one out.
    for k in kandidati:
        if k.get("email"):
            print(f"::add-mask::{k['email']}", flush=True)
    souhrn = {d: 0 for d in DRUHY}
    souhrn["chyby"] = 0
    if not kandidati:
        return souhrn
    ids = ", ".join(str(int(k["id"])) for k in kandidati)
    odeslane = {(int(r["uzivatel_id"]), r["druh"])
                for r in d1(db, f"SELECT uzivatel_id, druh FROM upominky WHERE uzivatel_id IN ({ids})")}
    nanecisto = env.get("NANECISTO") == "true"
    manifest = None
    for k in kandidati:
        uid, konec = int(k["id"]), int(k["konec"])
        druh = druh_upominky(konec, nyni)
        if druh is None or (uid, druh) in odeslane or str(k.get("email") or "").endswith(UKAZKOVY_UCET):
            continue
        if nanecisto:
            souhrn[druh] += 1
            continue
        if manifest is None:
            # Only when something is due: no name, no mail (skipped whole).
            manifest = nacti_manifest(env.get("VLASTNIK") or "simtegen-apps", repo)
        if not d1(db, f"INSERT OR IGNORE INTO upominky (uzivatel_id, druh, odeslano) "
                      f"VALUES ({uid}, '{druh}', {int(nyni)}) RETURNING uzivatel_id"):
            continue  # claimed by a run in parallel
        predmet, text = zprava(druh, manifest, repo, konec, nyni)
        try:
            posli(env["RESEND_API_KEY"], env["EMAIL_ODESILATEL"], k["email"],
                  manifest.get("kontakt_email") or None, predmet, text)
            souhrn[druh] += 1
        except Exception:  # noqa: BLE001 — any failure: give the claim back, try tomorrow
            souhrn["chyby"] += 1
            d1(db, f"DELETE FROM upominky WHERE uzivatel_id = {uid} AND druh = '{druh}' "
                   f"AND odeslano = {int(nyni)}")
    return souhrn


def main() -> int:
    env = dict(os.environ)
    for key in ("CLOUDFLARE_API_TOKEN", "CLOUDFLARE_ACCOUNT_ID"):
        if not env.get(key):
            print(f"Chybí {key} (org secret) — databáze produktů nejsou dostupné.")
            return 1
    nanecisto = env.get("NANECISTO") == "true"
    if not nanecisto and not (env.get("RESEND_API_KEY") and env.get("EMAIL_ODESILATEL")):
        print("RESEND_API_KEY / EMAIL_ODESILATEL nejsou nastavené — upomínky se neposílají a nic se "
              "nezapisuje (vývojový režim jako u přihlášení).")
        return 0
    nyni = int(time.time())
    selhalo = 0
    for repo in produkty(env):
        try:
            souhrn = zpracuj(repo, env, nyni)
        except Exception as e:  # noqa: BLE001 — one product's trouble must not stop the others
            selhalo += 1
            print(f"{repo}: selhalo — {str(e)[:300]}")
            continue
        selhalo += int(souhrn.get("chyby") or 0)
        print(f"{repo}: {'nanečisto ' if nanecisto else ''}{json.dumps(souhrn, ensure_ascii=False)}")
    return 1 if selhalo else 0


if __name__ == "__main__":
    sys.exit(main())
