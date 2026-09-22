"""Payment marked — run by the Platba workflow after the owner's word.

The bank is the one thing the firm cannot see, so "zaplaceno" stays the
owner's sentence (to ARGO); everything after it is this script:

  1. the order (by id) and its account from the product's D1,
  2. paid period: months added to max(now, current end) — and for a
     consumer who did NOT consent to an early start, no earlier than 14
     days after the order (§ 1837 l): the withdrawal window is honoured by
     construction, not by memory,
  3. the ledger row in `platby` (the monthly review counts first and
     second payments from it), order → `zaplacena`,
  4. an e-mail to the customer with the new end date.

Same SQL shape as the Predplatne workflow, which stays as the manual road.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import urllib.request


def d1(db: str, sql: str) -> list[dict]:
    run = subprocess.run(
        ["npx", "--yes", "wrangler@3", "d1", "execute", db, "--remote", "--json", "--command", sql],
        capture_output=True, text=True, encoding="utf-8",
    )
    if run.returncode != 0:
        raise SystemExit(f"D1 selhalo: {run.stderr[-800:]}")
    out = json.loads(run.stdout)
    return (out[0].get("results") or []) if out else []


def sql_text(value: str) -> str:
    return (value or "").replace("'", "''")


def predplatne_sql(uzivatel_id: int, mesice: int, poznamka: str, start_nejdrive: int) -> str:
    """Upsert of the paid period. start_nejdrive = unix time before which
    the paid period may not begin (0 = now)."""
    return (
        "INSERT INTO predplatne (uzivatel_id, plati_do, poznamka, zmeneno) "
        f"SELECT u.id, CAST(strftime('%s', datetime(MAX(unixepoch(), COALESCE(p.plati_do, 0), {start_nejdrive}), "
        f"'unixepoch', '+{mesice} months')) AS INTEGER), '{sql_text(poznamka)}', unixepoch() "
        f"FROM uzivatele u LEFT JOIN predplatne p ON p.uzivatel_id = u.id WHERE u.id = {uzivatel_id} "
        "ON CONFLICT(uzivatel_id) DO UPDATE SET plati_do = excluded.plati_do, "
        "poznamka = excluded.poznamka, zmeneno = excluded.zmeneno;"
    )


def posli(api_key: str, odesilatel: str, komu: str, predmet: str, text: str) -> None:
    payload = {"from": odesilatel, "to": [komu], "subject": predmet, "text": text}
    req = urllib.request.Request(
        "https://api.resend.com/emails", data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}, method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        if r.status >= 300:
            raise SystemExit(f"Resend vrátil {r.status}")


def main() -> int:
    env = os.environ
    for key in ("CLOUDFLARE_API_TOKEN", "CLOUDFLARE_ACCOUNT_ID"):
        if not env.get(key):
            print(f"Chybí {key} (org secret).")
            return 1
    projekt, objednavka = env["PROJEKT"], int(env["OBJEDNAVKA"])
    mesice, poznamka = int(env["MESICE"]), env.get("POZNAMKA") or ""
    if not 1 <= mesice <= 24:
        print("mesice musí být 1–24.")
        return 1
    db = f"{projekt}-db"

    rows = d1(db, "SELECT o.id, o.uzivatel_id, o.mesice, o.stav, o.spotrebitel, o.souhlas_zahajeni, "
                  "o.vytvoreno, u.email FROM objednavky o JOIN uzivatele u ON u.id = o.uzivatel_id "
                  f"WHERE o.id = {objednavka}")
    if not rows:
        print(f"Objednávka {objednavka} v {db} neexistuje.")
        return 1
    o = rows[0]
    if o["stav"] == "zaplacena":
        print(f"Objednávka {objednavka} už je zaplacená — nic nedělám.")
        return 0
    if int(o["mesice"]) != mesice:
        print(f"Nesouhlasí měsíce: objednávka {o['mesice']}, firma {mesice}.")
        return 1
    # Consumer without the § 1837 l consent: the paid service may start only
    # once the 14-day withdrawal window has closed.
    start = int(o["vytvoreno"]) + 14 * 86400 if (int(o["spotrebitel"] or 0) and not int(o["souhlas_zahajeni"] or 0)) else 0

    uid = int(o["uzivatel_id"])
    d1(db, predplatne_sql(uid, mesice, poznamka, start))
    d1(db, f"INSERT INTO platby (uzivatel_id, mesice, poznamka) VALUES ({uid}, {mesice}, '{sql_text(poznamka)}');")
    d1(db, f"UPDATE objednavky SET stav = 'zaplacena' WHERE id = {objednavka};")
    konec = d1(db, f"SELECT date(plati_do, 'unixepoch') AS den FROM predplatne WHERE uzivatel_id = {uid}")
    den = (konec[0]["den"] if konec else "") or ""
    print(f"Platba zapsána: {o['email']} má předplatné do {den}.")

    if env.get("RESEND_API_KEY") and env.get("EMAIL_ODESILATEL"):
        y, m, d = den.split("-") if den.count("-") == 2 else ("", "", "")
        hezky = f"{int(d)}. {int(m)}. {y}" if y else den
        posli(env["RESEND_API_KEY"], env["EMAIL_ODESILATEL"], o["email"], "Platba přijata — předplatné zapsáno",
              f"Dobrý den,\n\nděkujeme, platbu jsme přijali ({poznamka}). Vaše předplatné platí do {hezky}.\n"
              "Stav vidíte v aplikaci u svého účtu.\n")
    else:
        print("Bez RESEND_API_KEY / EMAIL_ODESILATEL e-mail zákazníkovi neodešel.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
