"""Migrace, které mažou nebo přepisují data, jen se schválením majitele.

Infrastruktura šablony (NEUPRAVOVAT V PRODUKTU): stavitel ji při každé
stavbě obnoví ze šablony; volá ji kontrola_manifestu.py, takže běží v CI
každého produktu — a v CI PŘED krokem „Migrace databaze“, takže migrace,
kterou nikdo neschválil, se na produkční databázi nikdy nespustí a PR
s ní nejde mergnout (kontrola je povinná podle rulesetu).

Why a signature and not a marker comment: the migration is written by the
builder — a model — and a model can write any comment, any flag, any
file. What it cannot write is a signature by the key on the mini PC.
SimteGen signs (db/migrace/schvalene.json) only migrations that are
already on main (they ran in production long ago) and the ones the owner
approved; the verifying public key (simtegen_podpis.json) is written by
SimteGen after the builder's run, so a key the model planted is gone
before any check sees it.

The verifying key is pinned: when the organisation variable SIMTEGEN_PODPIS
is in the environment (the CI step gets it; only an org admin can change
it), the key file must be exactly that key — a model that rewrites both the
key file and the signatures in one PR still fails here.

Ničivé = DROP TABLE / VIEW / TRIGGER / INDEX / COLUMN, ALTER TABLE … RENAME,
DELETE FROM, UPDATE … SET (i main.t, AS alias, INDEXED BY, OR …), REPLACE /
INSERT OR REPLACE, ON CONFLICT … DO UPDATE. CREATE, ADD COLUMN, INSERT
a indexy jsou v pořádku bez schválení.

Run alone:  python kontrola_migraci.py
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import sys
from pathlib import Path

MIGRACE = Path("db") / "migrace"
SCHVALENE = MIGRACE / "schvalene.json"
KLIC = Path("simtegen_podpis.json")

# A table name as the stripper leaves it: bare, or "quoted" (brackets and
# backticks are normalised to quotes), optionally schema-qualified.
_JMENO = r'(?:"\w*"|\w+)(?:\s*\.\s*(?:"\w*"|\w+))?'
# Readable names for the owner's list. They only describe; what counts as
# destructive is decided by the token scan below, so a syntax variant no
# pattern foresaw is still caught — it is just shown as a raw snippet.
_NICIVE = (
    re.compile(rf"\bDROP\s+(?:TABLE|VIEW|TRIGGER|INDEX)\s+(?:IF\s+EXISTS\s+)?{_JMENO}", re.IGNORECASE),
    re.compile(rf"\bALTER\s+TABLE\s+{_JMENO}\s+(?:DROP|RENAME)\b(?:\s+(?:COLUMN|TO))?(?:\s+{_JMENO})?",
               re.IGNORECASE),
    re.compile(rf"\bDELETE\s+FROM\s+{_JMENO}", re.IGNORECASE),
    re.compile(rf"\bUPDATE\s+(?:OR\s+\w+\s+)?{_JMENO}(?:\s+(?:AS\s+)?(?!SET\b|INDEXED\b|NOT\b)\w+)?"
               r"(?:\s+INDEXED\s+BY\s+\w+|\s+NOT\s+INDEXED)?\s+SET\b", re.IGNORECASE),
    re.compile(rf"\b(?:INSERT\s+OR\s+REPLACE|REPLACE)\s+INTO\s+{_JMENO}", re.IGNORECASE),
    re.compile(r"\bON\s+CONFLICT\b[^;]*?\bDO\s+UPDATE\b", re.IGNORECASE),
)
# Words that change or remove existing rows wherever they stand as a
# statement — UPDATE and DELETE except as a trigger event or a foreign-key
# action (AFTER UPDATE ON, ON DELETE CASCADE), REPLACE except the string
# function replace(…).
_SLOVO = re.compile(r'"\w*"|[A-Za-z_]\w*|\S')
_UDALOST = {"ON", "AFTER", "BEFORE", "OF"}
_DIGEST_INFO = bytes.fromhex("3031300d060960864801650304020105000420")
_E = 65537


def _bez_komentaru(sql: str) -> str:
    """Comments out, string literals emptied, quoted identifiers normalised —
    in ONE left-to-right pass. Two passes cannot be right: stripping
    comments first lets a '--' inside a string swallow the real code after
    it; stripping strings first lets a quote inside a comment swallow the
    code after the comment. Whatever a migration hides must not survive
    as something the checker skips but SQLite runs."""
    out: list[str] = []
    i, n = 0, len(sql)
    while i < n:
        if sql.startswith("--", i):
            j = sql.find("\n", i)
            i = n if j < 0 else j
            out.append(" ")
        elif sql.startswith("/*", i):
            # SQLite ends an unterminated block comment at the end of input.
            j = sql.find("*/", i + 2)
            i = n if j < 0 else j + 2
            out.append(" ")
        elif sql[i] in "'\"`[":
            konec = "]" if sql[i] == "[" else sql[i]
            j = i + 1
            while j < n:
                if sql[j] == konec:
                    if konec != "]" and sql.startswith(konec * 2, j):
                        j += 2  # doubled quote = the quote itself
                        continue
                    break
                j += 1
            obsah = sql[i + 1:j]
            i = j + 1
            # A string's words are data; an identifier is kept as one
            # neutral word so a column called "drop" stays a name.
            out.append("''" if konec == "'" else '"' + re.sub(r"\W", "_", obsah) + '"')
        else:
            out.append(sql[i])
            i += 1
    return "".join(out)


def _nicive_slova(text: str):
    """Positions of every token that changes or removes existing data."""
    slova = [(m.start(), m.group(0)) for m in _SLOVO.finditer(text)]
    for k, (pozice, slovo) in enumerate(slova):
        horni = slovo.upper()
        pred = slova[k - 1][1].upper() if k else ""
        dalsi = slova[k + 1][1] if k + 1 < len(slova) else ""
        if horni in ("DROP", "RENAME"):
            yield pozice
        elif horni in ("UPDATE", "DELETE") and pred not in _UDALOST:
            yield pozice
        elif horni == "REPLACE" and dalsi != "(":
            yield pozice


def nicive_prikazy(sql: str) -> list[str]:
    """What in this SQL deletes or rewrites data — the statements, short."""
    text = _bez_komentaru(sql)
    nalezy = [(m.start(), m.end(), " ".join(m.group(0).split())) for p in _NICIVE for m in p.finditer(text)]
    for pozice in _nicive_slova(text):
        if not any(od <= pozice < do for od, do, _ in nalezy):
            konec = text.find(";", pozice)
            usek = " ".join(text[pozice:konec if konec >= 0 else len(text)].split())
            nalezy.append((pozice, pozice + 1, usek[:60] + ("…" if len(usek) > 60 else "")))
    return [n for _, _, n in sorted(nalezy)]


def obsah(soubor: Path) -> bytes:
    """The migration as signed: line endings normalised, so a checkout on
    Windows (CRLF) and on the CI runner (LF) hash the same."""
    return soubor.read_bytes().replace(b"\r\n", b"\n")


def otisk(soubor: Path) -> str:
    return hashlib.sha256(obsah(soubor)).hexdigest()


def zprava(rel: str, sha: str) -> bytes:
    """The exact bytes SimteGen signs (migrace.py builds the same)."""
    return f"simtegen-migrace\nsoubor={rel}\nsha256={sha}".encode("utf-8")


def _podpis_sedi(klic: dict, data: bytes, podpis_b64: str) -> bool:
    try:
        n, e = int(klic["n"], 16), int(klic["e"])
        sig = base64.b64decode(podpis_b64, validate=True)
    except (KeyError, TypeError, ValueError):
        return False
    k = (n.bit_length() + 7) // 8
    if len(sig) != k:
        return False
    t = _DIGEST_INFO + hashlib.sha256(data).digest()
    ocekavam = b"\x00\x01" + b"\xff" * (k - len(t) - 3) + b"\x00" + t
    return pow(int.from_bytes(sig, "big"), e, n).to_bytes(k, "big") == ocekavam


def _vada_klice(klic) -> str | None:
    """Why this key file must not verify anything, or None. The file lies in
    the product repo next to the signatures, so on its own it proves only
    that whoever wrote the signatures also wrote the key. The pin is the
    org variable SIMTEGEN_PODPIS, which the bot token cannot change."""
    try:
        n, e = int(klic["n"], 16), int(klic["e"])
    except (KeyError, TypeError, ValueError):
        return f"{KLIC.as_posix()} chybí nebo nemá tvar {{n, e}}"
    if e != _E:
        return f"{KLIC.as_posix()} nemá exponent {_E}"
    pin = (os.environ.get("SIMTEGEN_PODPIS") or "").strip()
    if not pin:
        return None
    try:
        p = json.loads(pin)
        pn, pe = int(p["n"], 16), int(p["e"])
    except (KeyError, TypeError, ValueError):
        return "org proměnná SIMTEGEN_PODPIS nemá tvar {\"n\", \"e\"} (py main.py --podpis-klic)"
    if (pn, pe) != (n, e):
        return f"{KLIC.as_posix()} není klíč z org proměnné SIMTEGEN_PODPIS"
    return None


def zkontroluj(root: Path | None = None) -> tuple[list[str], list[str]]:
    """(chyby, varování). On SimteGen's own pre-check (SIMTEGEN_PRED_CI=1) a
    missing approval only warns: the owner has not decided yet, and that is
    not the builder's to fix. In CI it is an error."""
    root = Path(root or Path(__file__).resolve().parent)
    slozka = root / MIGRACE
    if not slozka.exists():
        return [], []
    try:
        klic = json.loads((root / KLIC).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        klic = None
    vada = _vada_klice(klic)
    if vada:
        klic = None
    try:
        schvalene = {z.get("soubor"): z for z in json.loads((root / SCHVALENE).read_text(encoding="utf-8"))
                     .get("schvaleno") or [] if isinstance(z, dict)}
    except (OSError, ValueError, AttributeError):
        schvalene = {}
    jen_varuj = os.environ.get("SIMTEGEN_PRED_CI") == "1"
    chyby: list[str] = []
    varovani: list[str] = []
    for soubor in sorted(slozka.glob("*.sql")):
        prikazy = nicive_prikazy(obsah(soubor).decode("utf-8", "replace"))
        if not prikazy:
            continue
        rel = (MIGRACE / soubor.name).as_posix()
        sha = otisk(soubor)
        zaznam = schvalene.get(rel) or {}
        if klic and zaznam.get("sha256") == sha and _podpis_sedi(klic, zprava(rel, sha), str(zaznam.get("podpis") or "")):
            continue
        zprava_txt = (f"{rel}: migrace maže nebo přepisuje data ({'; '.join(prikazy[:3])}) a nemá schválení "
                      "majitele — schvaluje se přes SimteGen (py main.py --schval-migraci N nebo ARGO), "
                      "nikdy úpravou souborů." + (f" ({vada}.)" if vada and zaznam else ""))
        (varovani if jen_varuj else chyby).append(zprava_txt)
    if schvalene and not vada and not jen_varuj and not (os.environ.get("SIMTEGEN_PODPIS") or "").strip():
        # Not an error: until the CI step carries the variable, products must
        # keep deploying. But the signatures then rest on a key from the repo.
        varovani.append("klíč ke schválení migrací není připnutý — CI nemá org proměnnou SIMTEGEN_PODPIS.")
    return chyby, varovani


def main() -> int:
    chyby, varovani = zkontroluj()
    for c in chyby + varovani:
        print(" -", c)
    print("Migrace v pořádku." if not chyby else f"Migrace: {len(chyby)} bez schválení.")
    return 1 if chyby else 0


if __name__ == "__main__":
    sys.exit(main())
