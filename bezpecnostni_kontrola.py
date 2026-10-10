"""Bezpečnostní kontrola kódu produktu — infrastruktura šablony.

NEUPRAVOVAT V PRODUKTU: stavitel tenhle soubor při každé stavbě obnoví ze
šablony; volá ho kontrola_manifestu.py, takže běží v CI každého produktu.

Why deterministic rules before any model looks: the holes that matter in a
small app with accounts are few and mechanical — an endpoint that forgets
to ask who is calling, SQL glued together from input, a query on customer
data that does not filter by the customer, HTML built from data, a key
pasted into the code. Each is a pattern a regex finds every time, and a
model reviewer finds only on a good day. The model review (recenzent's
security pass) is for what patterns cannot see.

The rules, in order:
- every API file outside the public list checks the signed-in user;
- SQL goes through prepare("literal").bind(...) — no variables, no ${};
- every statement on a table with uzivatel_id names uzivatel_id;
- no raw DB.exec(), no innerHTML/eval/document.write with data;
- no keys or tokens in the repository;
- web/_headers carries the Content-Security-Policy (memory template);
- reports leave only encrypted (through schranka_sifra.js).

Run alone:  python bezpecnostni_kontrola.py
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

# Endpoints of the template that are public by design: logging in cannot
# require being logged in. A product adds its own through the manifest
# (verejna_api: [{"soubor": "...", "proc": "..."}]) — visible, reasoned, and
# in front of the reviewer, never a silent exception.
VEREJNA_API_SABLONY = {"functions/api/prihlaseni.js", "functions/api/overeni.js",
                       "functions/api/odhlaseni.js", "functions/api/navsteva.js",
                       "functions/api/nahlasit.js"}

# Security plumbing of the template, queried by token or expiry, not by
# customer — the uzivatel_id rule is about customer data.
ZAKLADNI_TABULKY = {"uzivatele", "prihlasovaci_odkazy", "relace"}

# Template files that build SQL identifiers from the database's own catalogue
# (export and delete over every table with uzivatel_id). Only there, and only
# as a quoted identifier "${...}", is interpolation allowed.
IDENTIFIKATORY_SMI = {"spolecne.js", "functions/api/ucet/export.js",
                      "functions/api/ucet/smazat.js"}

_STRAZ = re.compile(r"!\s*(?:context\.)?(?:data\.)?uzivatel\b|vyzadujUzivatele\s*\(|vyzadujPredplatne\s*\(")

# A justified exception to the uzivatel_id rule, written next to the query:
#   // mimo-uzivatele: členství v cizí dílně se maže podle e-mailu
# Team membership keyed by e-mail is the first real case. The reason travels
# with the code, so the security review reads it instead of a silent pass.
_VYJIMKA = re.compile(r"mimo-uzivatele:\s*\S.{4,}")

# Built from pieces so this file does not trip its own scan.
_TAJEMSTVI = [
    ("Stripe klíč", re.compile("sk_" + r"(?:live|test)_[0-9A-Za-z]{16,}")),
    ("GitHub token", re.compile("gh" + r"[pousr]_[0-9A-Za-z]{30,}|github" + r"_pat_[0-9A-Za-z_]{30,}")),
    ("Resend klíč", re.compile(r"\bre" + r"_[0-9A-Za-z]{8,}_[0-9A-Za-z]{16,}")),
    ("AWS klíč", re.compile("AK" + r"IA[0-9A-Z]{16}")),
    ("Slack token", re.compile("xo" + r"x[abprs]-[0-9A-Za-z-]{10,}")),
    ("Google klíč", re.compile("AI" + r"za[0-9A-Za-z_-]{35}")),
    ("soukromý klíč", re.compile("-----BEGIN " + r"(?:RSA |EC |OPENSSH )?PRIVATE KEY-----")),
    ("Cloudflare/obecný token v přiřazení", re.compile(
        r"(?i)\b(?:api[_-]?key|secret|token|heslo|password)\b\s*[:=]\s*[\"'][0-9A-Za-z_\-]{24,}[\"']")),
]
_TEXTOVE = {".js", ".mjs", ".html", ".css", ".json", ".toml", ".sql", ".md", ".txt", ".py",
            ".yml", ".yaml", ".sablona", ".webmanifest"}
_PRESKOCIT_ADRESARE = {".git", "node_modules", "__pycache__", ".wrangler"}

_CSP_NUTNE = ("default-src 'self'", "connect-src 'self'", "object-src 'none'",
              "frame-ancestors 'none'", "base-uri 'self'")


def _rel(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def _radek(text: str, pozice: int) -> int:
    return text.count("\n", 0, pozice) + 1


def _soubory(root: Path, kde: Path, pripony: tuple[str, ...]):
    if not kde.exists():
        return
    for path in sorted(kde.rglob("*")):
        if path.is_file() and path.suffix.lower() in pripony and not (
                set(path.relative_to(root).parts) & _PRESKOCIT_ADRESARE):
            yield path


# --- SQL in prepare(...) -----------------------------------------------------

def _argument(text: str, start: int) -> tuple[str, int]:
    """The first argument of a call whose '(' is at text[start-1]: up to the
    first top-level ',' or the closing ')', with strings and ${} respected."""
    i, hloubka = start, 0
    while i < len(text):
        ch = text[i]
        if ch in "\"'":
            konec = i + 1
            while konec < len(text) and text[konec] != ch:
                konec += 2 if text[konec] == "\\" else 1
            i = konec + 1
            continue
        if ch == "`":
            i += 1
            while i < len(text) and text[i] != "`":
                if text[i] == "\\":
                    i += 2
                    continue
                if text.startswith("${", i):
                    vnoreni, i = 1, i + 2
                    while i < len(text) and vnoreni:
                        vnoreni += {"{": 1, "}": -1}.get(text[i], 0)
                        i += 1
                    continue
                i += 1
            i += 1
            continue
        if ch in "([{":
            hloubka += 1
        elif ch in ")]}":
            if hloubka == 0:
                return text[start:i], i
            hloubka -= 1
        elif ch == "," and hloubka == 0:
            return text[start:i], i
        i += 1
    return text[start:], len(text)


_LITERAL = re.compile(r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|`(?:\\.|\$\{[^}]*\}|[^`\\])*`', re.S)


_KONSTANTA = re.compile(r"^[A-Z][A-Z0-9_]*$")
# A helper called with literals only (sqlBezDiakritiky("z.jmeno")) produces
# the same SQL every time — code, not input.
_VOLANI_S_LITERALY = re.compile(
    r"""^\w+\(\s*(?:(?:"[^"]*"|'[^']*'|\d+)\s*(?:,\s*(?:"[^"]*"|'[^']*'|\d+)\s*)*)?\)$""")
_TOKEN = re.compile(r"\x00|[A-Za-z_$][\w$.]*(?:\([^()]*\))?|[^\s+()]")


def _konstanty(root: Path) -> dict[str, str]:
    """UPPER_CASE constants assigned pure SQL text anywhere outside web/ —
    the shared SELECT fragments the first real product keeps in one place.
    Resolved transitively; a constant that is not pure text stays out (and
    a query using it is then refused as a variable)."""
    surove: dict[str, str] = {}
    for path in _soubory(root, root, (".js", ".mjs")):
        if _rel(root, path).startswith("web/"):
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for m in re.finditer(r"(?:export\s+)?const\s+([A-Z][A-Z0-9_]*)\s*=\s*", text):
            konec = text.find(";", m.end())
            surove[m.group(1)] = text[m.end():konec if konec >= 0 else len(text)]
    hotove: dict[str, str] = {}
    for _ in range(5):
        for jmeno, vyraz in surove.items():
            if jmeno not in hotove:
                sql, problem = _sql_z_argumentu(vyraz, hotove, False)
                if problem is None:
                    hotove[jmeno] = sql
    return hotove


def _sql_z_argumentu(arg: str, konstanty: dict[str, str],
                     identifikatory: bool) -> tuple[str, str | None]:
    """(SQL text, problem or None). Literals, known constants and helpers
    called with literals make SQL; any other variable or ${...} is a value
    that belongs in .bind()."""
    casti: list[str] = []
    zbytek = _LITERAL.sub(lambda m: casti.append(m.group(0)) or "\x00", arg)
    literaly = iter(casti)
    sql = ""
    for token in _TOKEN.findall(zbytek):
        if token == "\x00":
            cast = next(literaly)
            obsah = cast[1:-1]
            if cast[0] == "`":
                spatne: list[str] = []

                def nahrad(m, spatne=spatne):
                    vyraz = m.group(2).strip()
                    if _KONSTANTA.match(vyraz) and vyraz in konstanty:
                        return m.group(1) + konstanty[vyraz] + m.group(3)
                    if _VOLANI_S_LITERALY.match(vyraz):
                        return m.group(1) + "_funkce_" + m.group(3)
                    if identifikatory and m.group(1) == '"' and m.group(3) == '"':
                        return '"_identifikator_"'
                    spatne.append(m.group(0))
                    return "_promenna_"

                obsah = re.sub(r"(\"?)\$\{([^}]*)\}(\"?)", nahrad, obsah)
                if spatne:
                    return sql, (f"${{…}} uvnitř SQL ({', '.join(spatne)[:80]}) — hodnoty patří "
                                 "do .bind(), jinak je to SQL injection.")
            sql += obsah
        elif _KONSTANTA.match(token) and token in konstanty:
            sql += konstanty[token]
        elif re.match(r"^\w+\((?:\s*(?:\x00|\d+)\s*,?)*\)$", token):
            # Helper with literal arguments; its literals were masked above.
            for _ in range(token.count("\x00")):
                next(literaly)
            sql += "_funkce_"
        else:
            return sql, (f"SQL není jen zapsaný text ({token[:40]}) — hodnoty patří do .bind(), "
                         "ne do dotazu.")
    return sql, None


_TABULKA = re.compile(r'(?i)\b(?:FROM|JOIN|UPDATE|INTO)\s+"?([A-Za-z_][A-Za-z0-9_]*)"?')


def _tabulky_s_uzivatelem(root: Path) -> set[str]:
    tabulky = set()
    for sql_soubor in _soubory(root, root / "db", (".sql",)):
        text = sql_soubor.read_text(encoding="utf-8", errors="replace")
        for m in re.finditer(r'(?is)CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?"?(\w+)"?\s*\((.*?)\);', text):
            if re.search(r"\buzivatel_id\b", m.group(2)):
                tabulky.add(m.group(1).lower())
        for m in re.finditer(r'(?is)ALTER\s+TABLE\s+"?(\w+)"?\s+ADD\s+(?:COLUMN\s+)?"?uzivatel_id\b', text):
            tabulky.add(m.group(1).lower())
    return tabulky - ZAKLADNI_TABULKY


def _zkontroluj_sql(root: Path) -> list[str]:
    chyby: list[str] = []
    s_uzivatelem = _tabulky_s_uzivatelem(root)
    konstanty = _konstanty(root)
    for path in _soubory(root, root, (".js", ".mjs")):
        rel = _rel(root, path)
        if rel.startswith("web/"):
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for m in re.finditer(r"\bDB\s*\.\s*exec\s*\(", text):
            chyby.append(f"{rel}:{_radek(text, m.start())}: DB.exec() spouští SQL bez parametrů — "
                         "použij prepare(\"…\").bind(…).")
        for m in re.finditer(r"\.prepare\s*\(", text):
            arg, _ = _argument(text, m.end())
            radek = _radek(text, m.start())
            kde = f"{rel}:{radek}"
            sql, problem = _sql_z_argumentu(arg, konstanty, rel in IDENTIFIKATORY_SMI)
            if problem:
                chyby.append(f"{kde}: {problem}")
                continue
            okoli = "\n".join(text.splitlines()[max(0, radek - 5):radek + 1])
            dotcene = {t.lower() for t in _TABULKA.findall(sql)} & s_uzivatelem
            if dotcene and not re.search(r"\buzivatel_id\b", sql) and not _VYJIMKA.search(okoli):
                chyby.append(f"{kde}: dotaz na {', '.join(sorted(dotcene))} nefiltruje podle uzivatel_id "
                             "— jeden zákazník by viděl nebo měnil data druhého. (Je-li to záměr, "
                             "napiš nad dotaz komentář „mimo-uzivatele: důvod“.)")
    return chyby


# --- who may call which endpoint ---------------------------------------------

def _zkontroluj_pristup(root: Path, manifest: dict) -> list[str]:
    api = root / "functions" / "api"
    if not api.exists():
        return []
    chyby: list[str] = []
    verejna = set(VEREJNA_API_SABLONY)
    for polozka in manifest.get("verejna_api") or []:
        soubor = (polozka or {}).get("soubor", "") if isinstance(polozka, dict) else ""
        if not soubor or not (polozka.get("proc") or "").strip():
            chyby.append("data-manifest.json: každá položka verejna_api potřebuje soubor a proc "
                         "(proč endpoint smí volat i nepřihlášený).")
            continue
        verejna.add(soubor.replace("\\", "/"))
    for path in _soubory(root, api, (".js", ".mjs")):
        rel = _rel(root, path)
        if rel in verejna:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if not re.search(r"export\s+(?:async\s+)?function\s+onRequest", text):
            continue
        if not _STRAZ.search(text):
            chyby.append(f"{rel}: endpoint neověřuje přihlášeného uživatele "
                         "(if (!data.uzivatel) return json(…, 401)) — nebo ho uveď ve verejna_api s důvodem.")
    return chyby


# --- the browser side ----------------------------------------------------------

_XSS = [
    (re.compile(r"\.outerHTML\s*\+?="), "outerHTML"),
    (re.compile(r"\binsertAdjacentHTML\s*\("), "insertAdjacentHTML"),
    (re.compile(r"\bdocument\s*\.\s*write(?:ln)?\s*\("), "document.write"),
    (re.compile(r"(?<![\w.])eval\s*\("), "eval"),
    (re.compile(r"\bnew\s+Function\s*\("), "new Function"),
    (re.compile(r"\bset(?:Timeout|Interval)\s*\(\s*[\"'`]"), "setTimeout s textem"),
    (re.compile(r"(?i)href\s*=\s*[\"']\s*javascript:"), "javascript: odkaz"),
]


def _zkontroluj_web(root: Path, preskocit: set[Path]) -> list[str]:
    chyby: list[str] = []
    for path in _soubory(root, root / "web", (".js", ".mjs", ".html", ".htm")):
        if path.resolve() in preskocit:
            continue
        rel = _rel(root, path)
        text = path.read_text(encoding="utf-8", errors="replace")
        # innerHTML with content is refused only where the file has no HTML
        # escaping at all. Whether every value goes through it is beyond a
        # regex — that is the security review's job, and it is told so.
        escapuje = "&lt;" in text and "&amp;" in text
        radky_html = []
        for m in re.finditer(r"\.innerHTML\s*(\+?=)(?!=)\s*", text):
            prava = text[m.end():m.end() + 3]
            if m.group(1) == "=" and prava[:2] in ('""', "''", "``"):
                continue  # clearing a container is fine
            radky_html.append(str(_radek(text, m.start())))
        if radky_html and not escapuje:
            chyby.append(f"{rel}:{','.join(radky_html[:6])}: innerHTML s obsahem a soubor nemá žádné "
                         "escapování (&lt; &amp;) — data vkládej přes textContent / createElement, "
                         "jinak je to XSS.")
        for vzor, nazev in _XSS:
            for m in vzor.finditer(text):
                chyby.append(f"{rel}:{_radek(text, m.start())}: {nazev} — zakázané (spouští nebo vkládá "
                             "kód z textu).")
    return chyby


def _zkontroluj_hlavicky(root: Path) -> list[str]:
    """Memory template only (it has a database, db/): the browser itself refuses
    to send data anywhere but the product's own /api/ — the second wall
    behind the network check, and the one that holds when a regex misses."""
    if not (root / "db").exists():
        return []
    soubor = root / "web" / "_headers"
    if not soubor.exists():
        return ["web/_headers chybí — nese Content-Security-Policy (stavitel ho obnovuje ze šablony)."]
    # Header lines only: the file's own comment explains connect-src, and a
    # deleted directive must not pass because the comment still names it.
    text = "\n".join(r for r in soubor.read_text(encoding="utf-8", errors="replace").splitlines()
                     if not r.lstrip().startswith("#"))
    chybi = [c for c in _CSP_NUTNE if c not in text]
    if "Content-Security-Policy" not in text or chybi:
        return [f"web/_headers: Content-Security-Policy nemá {', '.join(chybi) or 'hlavičku'} — "
                "soubor je ze šablony, neupravuje se."]
    return []


def _zkontroluj_hlaseni(root: Path) -> list[str]:
    """A report issue created anywhere but schranka_sifra.js would carry the
    customer's text in plain sight: product repos are public. The template's
    own mailbox did exactly that before the encryption existed."""
    chyby: list[str] = []
    for path in _soubory(root, root, (".js", ".mjs")):
        rel = _rel(root, path)
        if rel.startswith("web/") or rel == "schranka_sifra.js":
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        m = re.search(r"labels\s*:\s*\[[^\]]*[\"']hlaseni[\"']", text)
        if m:
            chyby.append(f"{rel}:{_radek(text, m.start())}: hlášení jde do issue mimo schranka_sifra.js — "
                         "repozitář je veřejný, text musí jít šifrovaně přes zrcadliHlaseni().")
    return chyby


def _zkontroluj_tajemstvi(root: Path) -> list[str]:
    chyby: list[str] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in _TEXTOVE:
            continue
        if set(path.relative_to(root).parts) & _PRESKOCIT_ADRESARE or path.name == Path(__file__).name:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for nazev, vzor in _TAJEMSTVI:
            m = vzor.search(text)
            if m:
                chyby.append(f"{_rel(root, path)}:{_radek(text, m.start())}: vypadá to na {nazev} v kódu — "
                             "tajemství patří do secrets hostingu, nikdy do repozitáře.")
    return chyby


def zkontroluj(root: Path | None = None, manifest: dict | None = None,
               preskocit: set[Path] | None = None) -> list[str]:
    root = Path(root or Path(__file__).resolve().parent)
    if manifest is None:
        cesta = root / "data-manifest.json"
        manifest = json.loads(cesta.read_text(encoding="utf-8")) if cesta.exists() else {}
    preskocit = {Path(p).resolve() for p in (preskocit or set())}
    return (_zkontroluj_pristup(root, manifest) + _zkontroluj_sql(root)
            + _zkontroluj_web(root, preskocit) + _zkontroluj_hlavicky(root)
            + _zkontroluj_hlaseni(root) + _zkontroluj_tajemstvi(root))


def main() -> int:
    chyby = zkontroluj()
    for chyba in chyby:
        print(" -", chyba)
    print("Bezpečnostní kontrola prošla." if not chyby else f"Bezpečnostní kontrola: {len(chyby)} nálezů.")
    return 1 if chyby else 0


if __name__ == "__main__":
    sys.exit(main())
