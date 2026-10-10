"""Invoice for one order — run by the Faktura workflow, never by the app.

SimteGen (the firm) allocates the number and the amount and dispatches the
workflow; this script is the only place where the customer's billing
details (product database) meet the firm's bank account (input). It

  1. reads the order and the account e-mail from the product's D1,
  2. checks the order agrees with what the firm computed (months, price
     the customer saw) — a mismatch is a stop, not a guess,
  3. renders a PDF (reportlab) with a QR payment code (segno, SPAYD),
  4. mails it to the customer, copy to the firm's contact address (that
     copy is the accounting archive; the workflow artifact is a spare),
  5. marks the order `fakturovana`.

Python does the arithmetic with Decimal; no model is involved anywhere.
Stdlib + segno + reportlab; run on ubuntu-latest with DejaVu fonts.
"""

from __future__ import annotations

import base64
import json
import os
import subprocess
import sys
import urllib.request
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

VYSTUP = Path("vystup")
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
FONT_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


# ── Pure helpers (tested without a runner) ────────────────────────────

def iban_cz(account: str) -> str:
    """Czech account "prefix-number/bank" or "number/bank" → IBAN. An
    input that already is an IBAN passes through (spaces removed)."""
    raw = (account or "").replace(" ", "").upper()
    if raw.startswith("CZ") and len(raw) == 24:
        return raw
    if "/" not in raw:
        raise ValueError("účet musí být ve tvaru číslo/kód banky nebo IBAN")
    number, bank = raw.split("/", 1)
    prefix, base = (number.split("-", 1) + [""])[:2] if "-" in number else ("", number)
    if not (bank.isdigit() and len(bank) == 4 and base.isdigit() and (prefix == "" or prefix.isdigit())):
        raise ValueError("účet má nečíselné části")
    bban = f"{bank}{prefix.zfill(6)}{base.zfill(10)}"
    check_input = bban + "123500"  # C=12, Z=35, 00
    check = 98 - int(check_input) % 97
    return f"CZ{check:02d}{bban}"


def spayd(iban: str, amount: Decimal, vs: str, message: str) -> str:
    """Short Payment Descriptor (Czech QR platba). Message is ASCII-only
    without '*' — the spec's alphabet; diacritics are stripped."""
    import unicodedata

    dashes = message.replace("—", "-").replace("–", "-")
    plain = unicodedata.normalize("NFKD", dashes).encode("ascii", "ignore").decode()
    plain = plain.replace("*", "-")[:60]
    return f"SPD*1.0*ACC:{iban}*AM:{amount:.2f}*CC:CZK*X-VS:{vs}*MSG:{plain}"


def castky(celkem: int, sazba: int) -> dict[str, Decimal]:
    """VAT breakdown of a VAT-inclusive total (Decimal, half-up). Rate 0 =
    not a VAT payer: base equals total, tax is zero."""
    total = Decimal(celkem).quantize(Decimal("0.01"))
    if sazba <= 0:
        return {"zaklad": total, "dph": Decimal("0.00"), "celkem": total}
    base = (total / (1 + Decimal(sazba) / 100)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return {"zaklad": base, "dph": total - base, "celkem": total}


def variabilni_symbol(cislo: str) -> str:
    digits = "".join(ch for ch in cislo if ch.isdigit())
    return digits[-10:] or "0"


def kc(value: Decimal) -> str:
    whole, _, frac = f"{value:.2f}".partition(".")
    grouped = f"{int(whole):,}".replace(",", " ")
    return f"{grouped},{frac} Kč"


def mesice_slovem(n: int) -> str:
    return f"{n} " + ("měsíc" if n == 1 else "měsíce" if n < 5 else "měsíců")


def cz_datum(iso: str) -> str:
    y, m, d = iso.split("-")
    return f"{int(d)}. {int(m)}. {y}"


# ── D1 ────────────────────────────────────────────────────────────────

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


# ── PDF ───────────────────────────────────────────────────────────────

def render_pdf(path: Path, f: dict) -> None:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.pdfgen import canvas
    import segno

    pdfmetrics.registerFont(TTFont("DejaVu", FONT))
    pdfmetrics.registerFont(TTFont("DejaVu-Bold", FONT_BOLD))
    c = canvas.Canvas(str(path), pagesize=A4)
    w, h = A4
    y = h - 20 * mm

    def text(x, yy, s, size=10, bold=False):
        c.setFont("DejaVu-Bold" if bold else "DejaVu", size)
        c.drawString(x, yy, s)

    def block(x, yy, lines, size=10):
        for line in lines:
            if line:
                text(x, yy, line, size)
                yy -= size + 3
        return yy

    platce = f["dodavatel"].get("dph_sazba", 0) > 0
    text(20 * mm, y, f"FAKTURA č. {f['cislo']}", 16, True)
    text(20 * mm, y - 7 * mm, "Daňový doklad" if platce else "Faktura — nejsme plátci DPH", 10)
    y -= 20 * mm

    d = f["dodavatel"]
    text(20 * mm, y, "Dodavatel", 9, True)
    text(110 * mm, y, "Odběratel", 9, True)
    y -= 5 * mm
    left = [d.get("nazev"), d.get("sidlo"), f"IČO: {d.get('ico')}", f"DIČ: {d.get('dic')}" if d.get("dic") else "",
            d.get("zapis_or"), d.get("email")]
    right = f["odberatel"].splitlines()[:8] + [f["email"]]
    y_l = block(20 * mm, y, left)
    y_r = block(110 * mm, y, right)
    y = min(y_l, y_r) - 8 * mm

    dates = [f"Datum vystavení: {cz_datum(f['vystaveno'])}", f"Datum splatnosti: {cz_datum(f['splatnost'])}"]
    if platce:
        dates.append(f"Datum uskutečnění zdanitelného plnění: {cz_datum(f['vystaveno'])}")
    dates.append("Způsob úhrady: převodem")
    y = block(20 * mm, y, dates) - 6 * mm

    text(20 * mm, y, "Položka", 9, True)
    text(130 * mm, y, "Množství", 9, True)
    text(165 * mm, y, "Cena", 9, True)
    y -= 2 * mm
    c.line(20 * mm, y, w - 20 * mm, y)
    y -= 5 * mm
    text(20 * mm, y, f["popis"][:70], 10)
    text(130 * mm, y, "1", 10)
    text(165 * mm, y, kc(f["castky"]["celkem"]), 10)
    y -= 4 * mm
    c.line(20 * mm, y, w - 20 * mm, y)
    y -= 7 * mm
    if platce:
        text(110 * mm, y, f"Základ daně: {kc(f['castky']['zaklad'])}", 10); y -= 5 * mm
        text(110 * mm, y, f"DPH {d['dph_sazba']} %: {kc(f['castky']['dph'])}", 10); y -= 5 * mm
    text(110 * mm, y, f"Celkem k úhradě: {kc(f['castky']['celkem'])}", 12, True)
    y -= 14 * mm

    text(20 * mm, y, "Platební údaje", 9, True)
    qr_top = y + 2 * mm
    y -= 5 * mm
    y = block(20 * mm, y, [f"Číslo účtu: {d['ucet']}", f"IBAN: {f['iban']}", f"Variabilní symbol: {f['vs']}",
                           f"Částka: {kc(f['castky']['celkem'])}"])
    # The QR sits to the right of the payment block, hanging DOWN from its
    # top edge (drawImage anchors bottom-left), so it never climbs into the
    # totals above it.
    qr = segno.make(f["spayd"], error="m")
    qr_path = path.with_suffix(".png")
    qr.save(str(qr_path), scale=4, border=1)
    c.drawImage(str(qr_path), 130 * mm, qr_top - 40 * mm, width=40 * mm, height=40 * mm)
    text(130 * mm, qr_top - 44 * mm, "QR platba", 8)
    qr_path.unlink(missing_ok=True)
    y = min(y, qr_top - 46 * mm) - 6 * mm

    note = [f"Předplatné na {mesice_slovem(f['mesice'])}."]
    if not platce:
        note.append("Dodavatel není plátcem DPH.")
    note.append("Doklad vystaven automaticky; platný bez podpisu a razítka.")
    block(20 * mm, y, note, 9)
    c.showPage()
    c.save()


# ── Mail ──────────────────────────────────────────────────────────────

def posli(api_key: str, odesilatel: str, komu: str, kopie: str | None, predmet: str, text: str,
          priloha: Path) -> None:
    payload = {
        "from": odesilatel, "to": [komu], "subject": predmet, "text": text,
        "attachments": [{"filename": priloha.name,
                         "content": base64.b64encode(priloha.read_bytes()).decode()}],
    }
    if kopie and kopie.lower() != komu.lower():
        payload["bcc"] = [kopie]
    req = urllib.request.Request(
        "https://api.resend.com/emails", data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}, method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        if r.status >= 300:
            raise SystemExit(f"Resend vrátil {r.status}")


# ── Main ──────────────────────────────────────────────────────────────

def main() -> int:
    env = os.environ
    for key in ("CLOUDFLARE_API_TOKEN", "CLOUDFLARE_ACCOUNT_ID", "RESEND_API_KEY", "EMAIL_ODESILATEL"):
        if not env.get(key):
            print(f"Chybí {key} (org secret / variable) — fakturu nelze doručit.")
            return 1
    projekt, objednavka, cislo = env["PROJEKT"], int(env["OBJEDNAVKA"]), env["CISLO"]
    castka, mesice = int(env["CASTKA_CZK"]), int(env["MESICE"])
    dodavatel = json.loads(env["DODAVATEL"])
    db = f"{projekt}-db"

    rows = d1(db, "SELECT o.id, o.mesice, o.varianta, o.cena_czk, o.fakturace, o.stav, u.email "
                  f"FROM objednavky o JOIN uzivatele u ON u.id = o.uzivatel_id WHERE o.id = {objednavka}")
    if not rows:
        print(f"Objednávka {objednavka} v {db} neexistuje.")
        return 1
    o = rows[0]
    if o["stav"] == "fakturovana":
        print(f"Objednávka {objednavka} už má fakturu — nic nedělám.")
        return 0
    if o["stav"] != "nova":
        print(f"Objednávka {objednavka} je ve stavu {o['stav']} — nefakturuji.")
        return 1
    if int(o["mesice"]) != mesice:
        print(f"Nesouhlasí měsíce: objednávka {o['mesice']}, firma {mesice}.")
        return 1
    if o.get("cena_czk") is not None and int(o["cena_czk"]) != castka:
        print(f"Nesouhlasí cena: zákazník viděl {o['cena_czk']} Kč, schválená cena dává {castka} Kč. "
              "Zkontroluj ceník v aplikaci proti schválené ceně.")
        return 1

    iban = iban_cz(dodavatel["ucet"])
    vs = variabilni_symbol(cislo)
    amounts = castky(castka, int(dodavatel.get("dph_sazba") or 0))
    f = {
        "cislo": cislo, "dodavatel": dodavatel, "odberatel": o.get("fakturace") or "", "email": o["email"],
        "vystaveno": env["VYSTAVENO"], "splatnost": env["SPLATNOST"], "popis": env["POPIS"],
        "mesice": mesice, "castky": amounts, "iban": iban, "vs": vs,
        "spayd": spayd(iban, amounts["celkem"], vs, f"Faktura {cislo}"),
    }
    VYSTUP.mkdir(exist_ok=True)
    pdf = VYSTUP / f"faktura-{cislo}.pdf"
    render_pdf(pdf, f)

    text = (
        f"Dobrý den,\n\nv příloze posíláme fakturu č. {cislo} na {kc(amounts['celkem'])} "
        f"za předplatné ({mesice_slovem(mesice)}). Splatnost {cz_datum(env['SPLATNOST'])}.\n\n"
        f"Platbu prosím na účet {dodavatel['ucet']} (IBAN {iban}), variabilní symbol {vs}, "
        "nebo načtěte QR kód z faktury.\n\nPo připsání platby zapíšeme zaplacené období k vašemu účtu "
        "a dáme vědět e-mailem.\n\n" + str(dodavatel.get("nazev") or "") + "\n"
    )
    posli(env["RESEND_API_KEY"], env["EMAIL_ODESILATEL"], o["email"], dodavatel.get("email"),
          f"Faktura č. {cislo}", text, pdf)
    d1(db, f"UPDATE objednavky SET stav = 'fakturovana' WHERE id = {objednavka}")
    print(f"Faktura {cislo} na {kc(amounts['celkem'])} odeslána; objednávka {objednavka} fakturována.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
