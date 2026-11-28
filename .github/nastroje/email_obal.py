"""The products' mails in the product's own dress — for the mails the template
repo's workflows send (trial and renewal reminders, the answer to a report,
invoices, invoice reminders, the payment confirmation).

Every mail goes out as multipart: the text part is what it always was (the
record, the words the tests pin), and `html_emailu` builds the HTML part from
THAT text, line for line — no new sentences, the legal ones byte-identical. A
customer knows the product, not the firm, so the head is the product's name
with its colour square; SimteGen signs small at the foot.

The same markup as email_obal.js in the template root (the mails the
product's own Functions send: the login link, the order confirmation) — keep
the two in step; tests/test_email_obal.py renders both and compares them.

Mail clients are not browsers: tables, inline styles, one system font, no CSS
variables, web fonts, scripts, SVG or data: URIs. Everything that comes from
data — the product's name, the firm's answer to a report, the supplier's
name — is escaped; only links the caller hands over as links become anchors.

Not `email.py`: this directory goes first on sys.path, and urllib.request
imports the standard library's `email` package — a module of that name here
would break every mail. Stdlib only; Python 3.11.
"""

from __future__ import annotations

import json
import re
import urllib.request

# The logo travels inside the mail as an inline attachment (cid:), not as an
# address on the web: a remote image tells whoever hosts it who opened the
# mail and when — the owner's call (24. 11. 2026). The same bytes as
# PRILOHA_LOGA in email_obal.js (tests/test_email_obal.py compares them);
# white behind the ink so a client that inverts colours keeps it legible.
LOGO_CID = "simtegen-logo"
LOGO_SIMTEGEN = f"cid:{LOGO_CID}"
PRILOHA_LOGA = {
    "filename": "simtegen-logo.png",
    "content_id": LOGO_CID,
    "content": "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",
}


def s_logem(payload: dict) -> dict:
    """The Resend payload with the logo attached once — every mail that has
    an HTML part needs it, or its cid: reference shows as a broken image."""
    prilohy = list(payload.get("attachments") or [])
    if not any(p.get("content_id") == LOGO_CID for p in prilohy):
        prilohy.append(dict(PRILOHA_LOGA))
    payload["attachments"] = prilohy
    return payload

PISMO = "Arial, Helvetica, sans-serif"
PAPIR = "#f6f4ef"
LIST = "#ffffff"
LINKA = "#dcd8cf"
INKOUST = "#141414"
DRUHOTNY = "#5e5c57"

PODPIS = {"cs": "aplikace od SimteGen", "en": "an app by SimteGen"}

_HEX6 = re.compile(r"^#[0-9a-fA-F]{6}$")
_HEX3 = re.compile(r"^#[0-9a-fA-F]{3}$")
_ODKAZ = re.compile(r"^https://[^\s\"'<>\\]+$")


def escapuj(hodnota: object) -> str:
    # The same five as email_obal.js (html.escape would agree, but spelling
    # the apostrophe the same way keeps the two outputs byte-comparable).
    s = "" if hodnota is None else str(hodnota)
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;").replace("'", "&#39;"))


def hex_barva(barva: object) -> str:
    """"#abc" / "#aabbcc" → "#aabbcc"; anything else → the ink. The value
    lands in an attribute and a style, so a pattern, not a trust."""
    s = str(barva or "").strip()
    if _HEX6.match(s):
        return s.lower()
    if _HEX3.match(s):
        return ("#" + "".join(c * 2 for c in s[1:])).lower()
    return INKOUST


def barva_z_css(css: str) -> str | None:
    """The light-theme --barva-produktu from web/produkt.css (the first
    :root — the dark one sits in @media below it). None = ink."""
    blok = re.search(r":root\s*\{([^}]*)\}", css or "")
    m = blok and re.search(r"--barva-produktu\s*:\s*(#[0-9a-fA-F]{6}|#[0-9a-fA-F]{3})\s*;", blok.group(1))
    return hex_barva(m.group(1)) if m else None


def _odkaz_ok(url: object) -> bool:
    return bool(_ODKAZ.match(str(url or "")))


def _odstavec(radky: list[str]) -> str:
    return (f'<p style="margin:0 0 16px 0;font-family:{PISMO};font-size:15px;line-height:22px;color:{INKOUST};">'
            + "<br>".join(radky) + "</p>")


def _tlacitko(url: str, popisek: str) -> str:
    h = escapuj(url)
    return ('<table role="presentation" cellpadding="0" cellspacing="0" border="0" style="margin:0 0 12px 0;">'
            f'<tr><td bgcolor="{INKOUST}" style="background-color:{INKOUST};">'
            f'<a href="{h}" style="display:inline-block;padding:14px 28px;font-family:{PISMO};font-size:15px;'
            f'font-weight:bold;line-height:20px;color:{PAPIR};text-decoration:none;">{escapuj(popisek)}</a>'
            "</td></tr></table>"
            f'<p style="margin:0 0 16px 0;font-family:{PISMO};font-size:13px;line-height:20px;color:{DRUHOTNY};'
            f'word-break:break-all;"><a href="{h}" style="color:{DRUHOTNY};text-decoration:underline;">{h}</a></p>')


def _odkaz(url: str) -> str:
    h = escapuj(url)
    return f'<a href="{h}" style="color:{INKOUST};text-decoration:underline;word-break:break-all;">{h}</a>'


def _telo(text: str, tlacitko: dict | None, odkazy: list[str] | tuple[str, ...]) -> str:
    """The text part, paragraph by paragraph (blank line = paragraph,
    newline = <br>). A line that is exactly the button's link becomes the
    button; a line that is exactly one of `odkazy` an anchor showing itself."""
    tlacitko_url = tlacitko.get("odkaz") if tlacitko and _odkaz_ok(tlacitko.get("odkaz")) else None
    jine = {o for o in odkazy or () if _odkaz_ok(o)}
    vystup: list[str] = []
    for kus in re.split(r"\n{2,}", (text or "").replace("\r\n", "\n").replace("\r", "\n").strip()):
        radky: list[str] = []
        for radek in kus.split("\n"):
            cisty = radek.strip()
            if tlacitko_url and cisty == tlacitko_url:
                if radky:
                    vystup.append(_odstavec(radky))
                radky = []
                vystup.append(_tlacitko(tlacitko_url, tlacitko.get("popisek") or ""))
            elif cisty in jine:
                radky.append(_odkaz(cisty))
            else:
                radky.append(escapuj(radek))
        if radky:
            vystup.append(_odstavec(radky))
    return "\n".join(vystup)


def _hlavicka(produkt: str, barva: str) -> str:
    if not produkt:
        return ""
    return ('<tr><td style="padding:24px 32px 4px 32px;">'
            '<table role="presentation" cellpadding="0" cellspacing="0" border="0"><tr>'
            '<td valign="middle" style="padding:0 10px 0 0;">'
            '<table role="presentation" cellpadding="0" cellspacing="0" border="0"><tr>'
            f'<td width="12" height="12" bgcolor="{barva}" style="width:12px;height:12px;background-color:{barva};'
            'font-size:0;line-height:0;">&nbsp;</td></tr></table></td>'
            f'<td valign="middle" style="font-family:{PISMO};font-size:18px;line-height:24px;font-weight:bold;'
            f'color:{INKOUST};">{escapuj(produkt)}</td>'
            "</tr></table></td></tr>")


def _paticka(jazyk: str) -> str:
    return ('<tr><td style="padding:8px 32px 24px 32px;">'
            '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"><tr>'
            f'<td style="border-top:1px solid {LINKA};padding:16px 0 0 0;">'
            f'<img src="{LOGO_SIMTEGEN}" width="90" alt="SimteGen" style="display:block;width:90px;max-width:90px;'
            f'height:auto;border:0;outline:none;text-decoration:none;font-family:{PISMO};font-size:13px;'
            f'font-weight:bold;color:{INKOUST};">'
            f'<p style="margin:8px 0 0 0;font-family:{PISMO};font-size:12px;line-height:18px;color:{DRUHOTNY};">'
            f"{PODPIS[jazyk]}</p>"
            "</td></tr></table></td></tr>")


def html_emailu(predmet: str, text: str, produkt: str | None = None, barva: str | None = None,
                jazyk: str = "cs", tlacitko: dict | None = None,
                odkazy: list[str] | tuple[str, ...] = ()) -> str:
    """The whole HTML document for a mail whose text part is `text`."""
    j = "en" if jazyk == "en" else "cs"
    nazev = str(produkt or "").strip()
    return ("<!doctype html>\n" f'<html lang="{j}">\n<head>\n<meta charset="utf-8">\n'
            '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
            '<meta name="color-scheme" content="light">\n<meta name="supported-color-schemes" content="light">\n'
            f"<title>{escapuj(predmet)}</title>\n</head>\n"
            f'<body style="margin:0;padding:0;background-color:{PAPIR};">\n'
            f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" bgcolor="{PAPIR}" '
            f'style="background-color:{PAPIR};"><tr><td align="center" style="padding:24px 12px;">\n'
            f'<table role="presentation" width="600" cellpadding="0" cellspacing="0" border="0" bgcolor="{LIST}" '
            f'style="width:100%;max-width:600px;background-color:{LIST};border:1px solid {LINKA};">\n'
            + _hlavicka(nazev, hex_barva(barva)) + "\n"
            + f'<tr><td style="padding:20px 32px 8px 32px;">\n{_telo(text, tlacitko, odkazy)}\n</td></tr>\n'
            + _paticka(j) + "\n"
            + "</table>\n</td></tr></table>\n</body>\n</html>\n")


# ── Where the product's name and colour come from ─────────────────────
# The workflows run in the template repo with only the product's repo name;
# the name is in its data-manifest.json, the colour in its web/produkt.css,
# both public (as upominky.nacti_manifest already reads). Never a reason not
# to send: anything that fails is the repo name and ink.

def vlastnik(env: dict) -> str:
    """The org the products live in: the workflow's VLASTNIK, else the
    runner's own owner (every Actions job has GITHUB_REPOSITORY_OWNER)."""
    return env.get("VLASTNIK") or env.get("GITHUB_REPOSITORY_OWNER") or "simtegen-apps"


def _stahni(vlastnik_: str, repo: str, cesta: str) -> str:
    url = f"https://raw.githubusercontent.com/{vlastnik_}/{repo}/HEAD/{cesta}"
    with urllib.request.urlopen(url, timeout=20) as r:
        return r.read().decode("utf-8")


def nacti_barvu(vlastnik_: str, repo: str) -> str | None:
    try:
        return barva_z_css(_stahni(vlastnik_, repo, "web/produkt.css"))
    except Exception:  # noqa: BLE001 — a missing colour is ink, never a mail not sent
        return None


def nacti_znacku(vlastnik_: str, repo: str) -> tuple[str, str | None]:
    """(product name, colour) for a mail sent from a workflow."""
    produkt = ""
    try:
        manifest = json.loads(_stahni(vlastnik_, repo, "data-manifest.json"))
        produkt = str(manifest.get("produkt") or "").strip() if isinstance(manifest, dict) else ""
    except Exception:  # noqa: BLE001 — the repo name, as upominky does without a name
        produkt = ""
    return produkt or repo, nacti_barvu(vlastnik_, repo)
