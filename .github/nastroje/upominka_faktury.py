"""Upomínka faktury — a polite reminder to a customer whose invoice is past
due. Dispatched by SimteGen (faktura.upominky_zakaznikum), a few days after
the due date and once more later; the owner hears only after both.

Why here: the customer's e-mail lives in the product's database and the
Resend key in the organisation's secrets — SimteGen has neither, the same
reason the Faktura workflow runs here. Text only, no PDF: the invoice went
out already; the reminder repeats what pays it (amount, account, symbol).

Nothing is sent when the order is no longer `fakturovana` — paid in the
meantime (Platba marks it `zaplacena`) or cancelled: a reminder after the
money arrived is the worst mail a firm can send.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.request
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from faktura import cz_datum, d1, iban_cz, kc, variabilni_symbol  # noqa: E402


def text_upominky(poradi: int, cislo: str, castka: int, splatnost: str, ucet: str, iban: str, vs: str,
                  nazev: str) -> tuple[str, str]:
    """(subject, body). Formal, short, no threat — the second one only says
    it is the second. Pure."""
    predmet = (f"Připomínka: faktura č. {cislo}" if poradi <= 1
               else f"Druhá připomínka: faktura č. {cislo}")
    text = (
        "Dobrý den,\n\n"
        f"{'' if poradi <= 1 else 'znovu '}připomínáme fakturu č. {cislo} na {kc(Decimal(castka))}, "
        f"která byla splatná {cz_datum(splatnost)}. Platbu jsme zatím nepřijali.\n\n"
        f"Platbu prosím na účet {ucet} (IBAN {iban}), variabilní symbol {vs}. "
        "Fakturu s QR kódem najdete v e-mailu, se kterým přišla.\n\n"
        "Pokud jste už zaplatili, děkujeme a tuto zprávu prosím berte jako bezpředmětnou — "
        "platba se k vašemu účtu přiřadí sama.\n\n"
        + (nazev or "") + "\n"
    )
    return predmet, text


def posli(api_key: str, odesilatel: str, komu: str, kopie: str | None, predmet: str, text: str) -> None:
    payload = {"from": odesilatel, "to": [komu], "subject": predmet, "text": text}
    if kopie and kopie.lower() != komu.lower():
        payload["bcc"] = [kopie]
    req = urllib.request.Request(
        "https://api.resend.com/emails", data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}, method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        if r.status >= 300:
            raise SystemExit(f"Resend vrátil {r.status}")


def main() -> int:
    env = os.environ
    for key in ("CLOUDFLARE_API_TOKEN", "CLOUDFLARE_ACCOUNT_ID", "RESEND_API_KEY", "EMAIL_ODESILATEL"):
        if not env.get(key):
            print(f"Chybí {key} (org secret / variable) — upomínku nelze doručit.")
            return 1
    projekt, objednavka, cislo = env["PROJEKT"], int(env["OBJEDNAVKA"]), env["CISLO"]
    castka, poradi = int(env["CASTKA_CZK"]), int(env["PORADI"])
    dodavatel = json.loads(env["DODAVATEL"])
    rows = d1(f"{projekt}-db", "SELECT o.stav, u.email FROM objednavky o JOIN uzivatele u ON u.id = o.uzivatel_id "
                               f"WHERE o.id = {objednavka}")
    if not rows:
        print(f"Objednávka {objednavka} neexistuje.")
        return 1
    o = rows[0]
    # Public repo, public logs (see platba.py): mask the customer's address
    # before anything could print it.
    if (o.get("email") or "").strip():
        print(f"::add-mask::{o['email'].strip()}", flush=True)
    if o["stav"] != "fakturovana":
        print(f"Objednávka {objednavka} je ve stavu {o['stav']} — upomínka se neposílá.")
        return 0
    predmet, text = text_upominky(poradi, cislo, castka, env["SPLATNOST"], dodavatel["ucet"],
                                  iban_cz(dodavatel["ucet"]), variabilni_symbol(cislo), dodavatel.get("nazev") or "")
    posli(env["RESEND_API_KEY"], env["EMAIL_ODESILATEL"], o["email"], dodavatel.get("email"), predmet, text)
    print(f"Upomínka {poradi} k faktuře {cislo} odeslána.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
