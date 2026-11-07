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

Ničivé = DROP TABLE / VIEW / TRIGGER / COLUMN, ALTER TABLE … RENAME,
DELETE FROM, UPDATE … SET, REPLACE / INSERT OR REPLACE. CREATE, ADD COLUMN,
INSERT a indexy jsou v pořádku bez schválení.

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

_NICIVE = (
    re.compile(r"\bDROP\s+(?:TABLE|VIEW|TRIGGER)\s+(?:IF\s+EXISTS\s+)?[\w\"`\[\]]+", re.IGNORECASE),
    re.compile(r"\bALTER\s+TABLE\s+[\w\"`\[\]]+\s+(?:DROP|RENAME)\b(?:\s+(?:COLUMN|TO))?(?:\s+[\w\"`\[\]]+)?", re.IGNORECASE),
    re.compile(r"\bDELETE\s+FROM\s+[\w\"`\[\]]+", re.IGNORECASE),
    re.compile(r"\bUPDATE\s+(?:OR\s+\w+\s+)?[\w\"`\[\]]+\s+SET\b", re.IGNORECASE),
    re.compile(r"\b(?:INSERT\s+OR\s+REPLACE|REPLACE)\s+INTO\s+[\w\"`\[\]]+", re.IGNORECASE),
)
_DIGEST_INFO = bytes.fromhex("3031300d060960864801650304020105000420")


def _bez_komentaru(sql: str) -> str:
    sql = re.sub(r"/\*.*?\*/", " ", sql, flags=re.DOTALL)
    sql = re.sub(r"--[^\n]*", " ", sql)
    # String literals cannot hide a statement, but they can contain words.
    return re.sub(r"'(?:[^']|'')*'", "''", sql)


def nicive_prikazy(sql: str) -> list[str]:
    """What in this SQL deletes or rewrites data — the statements, short."""
    text = _bez_komentaru(sql)
    nalezy = [(m.start(), " ".join(m.group(0).split())) for p in _NICIVE for m in p.finditer(text)]
    return [n for _, n in sorted(nalezy)]


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
                      "nikdy úpravou souborů.")
        (varovani if jen_varuj else chyby).append(zprava_txt)
    return chyby, varovani


def main() -> int:
    chyby, varovani = zkontroluj()
    for c in chyby + varovani:
        print(" -", c)
    print("Migrace v pořádku." if not chyby else f"Migrace: {len(chyby)} bez schválení.")
    return 1 if chyby else 0


if __name__ == "__main__":
    sys.exit(main())
