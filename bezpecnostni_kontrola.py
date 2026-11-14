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
- every exported handler outside the public list that reaches data checks
  the signed-in user itself (or through a helper that does) — a guard in
  one handler of a file does not cover its neighbour;
- a public endpoint of the product only reads (writes are the template's);
- SQL goes through prepare("literal").bind(...) — no variables, no ${};
- every statement on a table with uzivatel_id names uzivatel_id, and the
  value bound for it does not come from the request;
- accounts, sessions, login links, subscriptions and payments are written
  only by the template's own files (a product endpoint that extends its
  caller's subscription passes every other rule);
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
                       # Script errors, counted (P9): a tally like navsteva —
                       # the login screen breaks too, no session to ask for.
                       "functions/api/chyba-stranky.js",
                       "functions/api/nahlasit.js",
                       # The visitor's country for the default currency
                       # (Jazyky a měny): Cloudflare's own two letters back to
                       # the same page, nothing read, nothing stored.
                       "functions/api/prostredi.js",
                       # The firm's answer to a report (SimteGen, odpovedi.py): no
                       # session — a signature of the answer key, verified inside.
                       "functions/api/schranka-odpoved.js",
                       # The firm's check account after a deploy (SimteGen,
                       # overeni.py): no session — a signature of the answer
                       # key, and it can only ever open the one fixed account.
                       "functions/api/kontrolni-prihlaseni.js", "functions/api/provoz.js",  # same signature, counts only
                       # Vyzkoušet ukázku (module play, SimteGen): a throwaway
                       # demo account — the reviewer and the visitor have none.
                       "functions/api/ukazka.js",
                       # Where customers come from: wraps /api/* after the
                       # product's own handler, never answers by itself.
                       "functions/api/_middleware.js"}

# Public endpoints that may accept a write from a stranger: the template's
# own, and the firm web's "Co vás trápí?" form (web_firmy/, written by
# SimteGen, never by the builder; still declared in that repo's
# verejna_api with its reason). Any other public endpoint only reads.
VEREJNE_ZAPISY = VEREJNA_API_SABLONY | {"functions/api/podnet.js"}

# Security plumbing of the template, queried by token or expiry, not by
# customer — the uzivatel_id rule is about customer data.
ZAKLADNI_TABULKY = {"uzivatele", "prihlasovaci_odkazy", "relace"}

# Template files that build SQL identifiers from the database's own catalogue
# (export and delete over every table with uzivatel_id). Only there, and only
# as a quoted identifier "${...}", is interpolation allowed.
IDENTIFIKATORY_SMI = {"spolecne.js", "functions/api/ucet/export.js",
                      "functions/api/ucet/smazat.js", "functions/api/ukazka.js",
                      # Sample data: snapshot and removal over the same catalogue.
                      "functions/api/ukazka-uctu.js"}

_STRAZ = re.compile(r"!\s*(?:context\.)?(?:data\.)?uzivatel\b|vyzadujUzivatele\s*\(|vyzadujPredplatne\s*\(")

# Tables a product endpoint never writes: who is logged in (relace,
# prihlasovaci_odkazy), who an account is (uzivatele — the e-mail is the
# identity) and what was paid for (predplatne, platby; the order's stav in
# the subscription-orders table is set only by the payment workflow). The
# other rules cannot tell a write here from any customer data: it is
# filtered by the caller's own uzivatel_id, and yet it is not his to set.
CHRANENE_TABULKY = {"predplatne", "platby", "relace", "prihlasovaci_odkazy", "uzivatele"}

# The template's files that do write them — and only these tables there.
# The login and logout endpoints are seeded once and stay product files,
# so a change to them is in the diff the reviewer reads.
CHRANENE_SMI = {
    "functions/api/overeni.js": {"prihlasovaci_odkazy", "uzivatele", "relace"},
    "functions/api/prihlaseni.js": {"prihlasovaci_odkazy"},
    "functions/api/odhlaseni.js": {"relace"},
    "functions/api/kontrolni-prihlaseni.js": {"uzivatele", "relace"},
    "functions/api/ucet/smazat.js": {"prihlasovaci_odkazy", "uzivatele", "relace"},
    "functions/api/_middleware.js": {"prihlasovaci_odkazy", "uzivatele", "relace"},
    # Module play (SimteGen): the demo account and the Play purchases.
    "functions/api/ukazka.js": {"uzivatele", "relace", "predplatne"},
    "play_nakupy.js": {"predplatne", "platby"},
}

# A justified exception to the uzivatel_id rule, written right at the query
# (on the prepare line or in the comment block directly above it):
#   // mimo-uzivatele: členství v cizí dílně se maže podle e-mailu
# Team membership keyed by e-mail is the first real case. The reason travels
# with the code, so the security review reads it instead of a silent pass.
# Only the one statement under it — a comment once covered every query in
# the five lines below, so one reason could carry a second, unrelated query.
# Every exception is counted in the report.
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
              "frame-ancestors 'none'", "base-uri 'self'", "form-action 'self'")
# The rest of the set (header, what its value must contain). Both templates
# and the firm's web carry them; a product without a database has no
# accounts, but its pages still run scripts and send the report form.
_HLAVICKY_NUTNE = (("Strict-Transport-Security", "max-age=31536000"), ("X-Content-Type-Options", "nosniff"),
                   ("Referrer-Policy", ""), ("Permissions-Policy", ""))


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


# --- JavaScript structure ------------------------------------------------------
# Rules about "this handler" need to know where a function ends. A brace
# counter over raw text is fooled by a quote or brace inside a string, a
# comment or a regex literal, so code is first masked: comments, string and
# regex contents and the static parts of template literals become spaces
# (offsets and newlines kept), ${…} inside templates stays code.

_REGEX_PO = set("(,=:[!&|?{};+-*%<>~^")
_REGEX_PO_SLOVE = {"return", "typeof", "case", "do", "else", "in", "of", "new", "delete", "void",
                   "throw", "yield", "await"}


def _maska(text: str) -> str:
    out = list(text)
    n = len(text)

    def prazdne(a: int, b: int) -> None:
        for k in range(a, min(b, n)):
            if out[k] != "\n":
                out[k] = " "

    sablony: list[int] = []  # open ${ … } depth per template literal level
    pred = ""
    i = 0
    while i < n:
        ch = text[i]
        if text.startswith("//", i):
            j = text.find("\n", i)
            j = n if j < 0 else j
            prazdne(i, j)
            i = j
            continue
        if text.startswith("/*", i):
            j = text.find("*/", i + 2)
            j = n if j < 0 else j + 2
            prazdne(i, j)
            i = j
            continue
        if ch in "\"'":
            j = i + 1
            while j < n and text[j] != ch and text[j] != "\n":
                j += 2 if text[j] == "\\" else 1
            prazdne(i + 1, j)
            i, pred = j + 1, "a"
            continue
        if ch == "`" or (ch == "}" and sablony and sablony[-1] == 0):
            if ch == "}":
                sablony.pop()
            j = i + 1
            while j < n and text[j] != "`" and not text.startswith("${", j):
                j += 2 if text[j] == "\\" else 1
            prazdne(i + 1, j)
            if j < n and text[j] == "`":
                i, pred = j + 1, "a"
            else:
                sablony.append(0)
                i, pred = j + 2, "("
            continue
        if ch == "/" and (pred == "" or pred in _REGEX_PO or pred in _REGEX_PO_SLOVE):
            j, trida = i + 1, False
            while j < n and text[j] != "\n":
                if text[j] == "\\":
                    j += 2
                    continue
                if text[j] == "[":
                    trida = True
                elif text[j] == "]":
                    trida = False
                elif text[j] == "/" and not trida:
                    break
                j += 1
            prazdne(i + 1, j)
            i, pred = j + 1, "a"
            continue
        if ch.isalnum() or ch in "_$":
            j = i
            while j < n and (text[j].isalnum() or text[j] in "_$"):
                j += 1
            i, pred = j, text[i:j]
            continue
        if sablony and ch == "{":
            sablony[-1] += 1
        elif sablony and ch == "}":
            sablony[-1] -= 1
        if not ch.isspace():
            pred = ch
        i += 1
    return "".join(out)


def _par(maska: str, start: int) -> int:
    """Index just past the bracket closing the one at maska[start]."""
    otevri = maska[start]
    zavri = {"{": "}", "(": ")", "[": "]"}[otevri]
    hloubka = 0
    for i in range(start, len(maska)):
        if maska[i] == otevri:
            hloubka += 1
        elif maska[i] == zavri:
            hloubka -= 1
            if hloubka == 0:
                return i + 1
    return len(maska)


_FUNKCE = re.compile(r"\b(?:async\s+)?function\s*\*?\s*([A-Za-z_$][\w$]*)\s*\("
                     r"|\b(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s+)?"
                     r"(?:function\b[^(]*\(|\(|[A-Za-z_$][\w$]*\s*=>)")


def _funkce(maska: str) -> dict[str, tuple[int, int]]:
    """Named functions of a file -> (start, end) of their body in the mask.
    An arrow function with an expression body ends at the first ';' or
    newline at depth zero — enough for "does it call X"."""
    vysledek: dict[str, tuple[int, int]] = {}
    for m in _FUNKCE.finditer(maska):
        jmeno = m.group(1) or m.group(2)
        i = m.end() - 1
        if maska[i] == "(":
            i = _par(maska, i)
        else:
            i = m.end()
        sipka = re.match(r"\s*(?:=>\s*)?", maska[i:])
        i += sipka.end()
        if i < len(maska) and maska[i] == "{":
            vysledek.setdefault(jmeno, (i, _par(maska, i)))
            continue
        konec = i
        hloubka = 0
        while konec < len(maska):
            c = maska[konec]
            if c in "([{":
                hloubka += 1
            elif c in ")]}":
                if hloubka == 0:
                    break
                hloubka -= 1
            elif c in ";\n" and hloubka == 0:
                break
            konec += 1
        vysledek.setdefault(jmeno, (i, konec))
    return vysledek


_HANDLER = re.compile(r"\bexport\s+(?:async\s+)?function\s+(onRequest\w*)\s*\("
                      r"|\bexport\s+(?:const|let|var)\s+(onRequest\w*)\s*=")
_ZAPISOVE = re.compile(r"^onRequest(?:Post|Put|Patch|Delete)?$")


def _handlery(maska: str) -> tuple[dict[str, tuple[int, int]], bool]:
    """Exported Pages handlers -> body span, and whether every export was
    understood. One that is not (export { … }, a middleware array) makes the
    caller fall back to the whole file — never a pass for want of parsing."""
    funkce = _funkce(maska)
    handlery: dict[str, tuple[int, int]] = {}
    vse = not re.search(r"\bexport\s*\{[^}]*\bonRequest", maska)
    for m in _HANDLER.finditer(maska):
        jmeno = m.group(1) or m.group(2)
        if jmeno in funkce:
            handlery[jmeno] = funkce[jmeno]
        else:
            vse = False
            handlery[jmeno] = (m.start(), len(maska))
    return handlery, vse


_IMPORT = re.compile(r"\bimport\s*\{([^}]*)\}\s*from\s*[\"'](\.{1,2}/[^\"']+)[\"']")


def _strazci(root: Path, path: Path, text: str, maska: str, funkce: dict[str, tuple[int, int]],
             _hloubka: int = 0) -> set[str]:
    """Names (as used in this file) of functions that check the signed-in
    user: local ones whose body has the guard or calls one that has, and
    ones imported from the product's own files that do the same there."""
    strazci: set[str] = set()
    if _hloubka < 2:
        for m in _IMPORT.finditer(text):
            if maska[m.start():m.start() + 6] != "import":
                continue  # an import inside a comment or string
            cil = (path.parent / m.group(2)).resolve()
            try:
                cil.relative_to(root.resolve())
                cizi = cil.read_text(encoding="utf-8", errors="replace")
            except (ValueError, OSError):
                continue
            cizi_maska = _maska(cizi)
            jejich = _strazci(root, cil, cizi, cizi_maska, _funkce(cizi_maska), _hloubka + 1)
            for polozka in m.group(1).split(","):
                casti = polozka.split()
                if casti and casti[0] in jejich:
                    strazci.add(casti[-1])
    zmena = True
    while zmena:
        zmena = False
        for jmeno, (od, do) in funkce.items():
            if jmeno in strazci:
                continue
            telo = maska[od:do]
            if _STRAZ.search(telo) or any(re.search(rf"\b{re.escape(s)}\s*\(", telo) for s in strazci):
                strazci.add(jmeno)
                zmena = True
    return strazci


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


def _tabulky(root: Path) -> dict[str, str]:
    """Table name -> its column text, from every CREATE / ALTER … ADD in db/."""
    tabulky: dict[str, str] = {}
    for sql_soubor in _soubory(root, root / "db", (".sql",)):
        text = sql_soubor.read_text(encoding="utf-8", errors="replace")
        for m in re.finditer(r'(?is)CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?"?(\w+)"?\s*\((.*?)\);', text):
            tabulky[m.group(1).lower()] = tabulky.get(m.group(1).lower(), "") + "\n" + m.group(2)
        for m in re.finditer(r'(?is)ALTER\s+TABLE\s+"?(\w+)"?\s+ADD\s+(?:COLUMN\s+)?([^;]*);', text):
            tabulky[m.group(1).lower()] = tabulky.get(m.group(1).lower(), "") + "\n" + m.group(2)
    return tabulky


def _tabulky_s_uzivatelem(root: Path) -> set[str]:
    return {t for t, sloupce in _tabulky(root).items() if re.search(r"\buzivatel_id\b", sloupce)} - ZAKLADNI_TABULKY


def _objednavky_predplatneho(root: Path) -> set[str]:
    """Tables of subscription orders: months bought and a state. The name
    differs (a tyre shop's "objednavky" are bookings, its subscription
    orders live elsewhere), the shape does not."""
    return {t for t, sloupce in _tabulky(root).items()
            if re.search(r"\bmesice\b", sloupce) and re.search(r"\bstav\b", sloupce)}


_ZAPIS = re.compile(r'(?is)\b(?:(?P<vloz>INSERT|REPLACE)\s+(?:OR\s+\w+\s+)?INTO\s+"?(?P<t1>\w+)"?(?P<sloupce>\s*\([^)]*\))?'
                    r'|UPDATE\s+(?:OR\s+\w+\s+)?"?(?P<t2>\w+)"?\s+(?:AS\s+\w+\s+)?SET\b(?P<set>.*?)(?=\bWHERE\b|\bRETURNING\b|$)'
                    r'|DELETE\s+FROM\s+"?(?P<t3>\w+)"?)')


def _chranene_zapisy(rel: str, sql: str, objednavky: set[str]) -> list[str]:
    """What this statement writes that only the template may write."""
    smi = CHRANENE_SMI.get(rel, set())
    nalezy = []
    for m in _ZAPIS.finditer(sql):
        tabulka = (m.group("t1") or m.group("t2") or m.group("t3")).lower()
        if tabulka in smi:
            continue
        druh = "INSERT" if m.group("vloz") else "UPDATE" if m.group("t2") else "DELETE"
        nastavuje = (m.group("set") or "") + (m.group("sloupce") or "")
        if druh == "INSERT":
            # An upsert's DO UPDATE SET belongs to the INSERT it rides on.
            nastavuje += sql[m.end():]
        if tabulka in CHRANENE_TABULKY - {"uzivatele"}:
            nalezy.append(f"{druh} {tabulka}")
        elif tabulka == "uzivatele" and (druh != "UPDATE" or re.search(r"\bemail\b", nastavuje)):
            nalezy.append(f"{druh} uzivatele" + (" (email)" if druh == "UPDATE" else ""))
        elif tabulka in objednavky and druh != "DELETE" and _stav_mimo_zruseni(druh, nastavuje):
            nalezy.append(f"{druh} {tabulka} (stav)")
    return nalezy


def _stav_mimo_zruseni(druh: str, nastavuje: str) -> bool:
    """Does this write set an order's stav to anything but a fixed, unpaid
    state? A customer cancelling his own unpaid order (stav = 'zrusena') is
    product logic; a stav bound from a variable, or written as invoiced or
    paid, belongs to the payment workflow alone."""
    if druh == "INSERT":
        return bool(re.search(r"\bstav\b", nastavuje))
    for m in re.finditer(r"\bstav\s*=\s*(?:'([^']*)'|[^,\s]+)", nastavuje):
        if m.group(1) is None or re.match(r"(?i)zaplac|faktur|uhraz", m.group(1)):
            return True
    return False


# Who a row belongs to, named in the request. Bound as the owner, it lets
# the caller pick the account: the uzivatel_id rule is satisfied, the data
# is someone else's (IDOR).
_JMENO_UZIVATELE = re.compile(r"(?i)^(?:\w*uzivatel\w*|\w*user_?id|uid|vlastnik(?:_id)?|owner_?id)$")


def _z_pozadavku(maska: str, text: str) -> tuple[set[str], set[str]]:
    """(objects read from the request — body, URL parameters, query;
    plain names that already hold a user id taken from them)."""
    objekty = {"params", "searchParams"}
    for m in re.finditer(r"\b([A-Za-z_$][\w$]*)\s*=\s*(?:await\s+)?(?:context\s*\.\s*)?request\s*\.\s*"
                         r"(?:json|formData|text)\b", maska):
        objekty.add(m.group(1))
    for m in re.finditer(r"\b([A-Za-z_$][\w$]*)\s*=\s*new\s+URL\s*\([^;\n]*?\)(?:\s*\.\s*searchParams)?(?=\s*[;\n])",
                         maska):
        objekty.add(m.group(1))
    jmena: set[str] = set()
    for m in re.finditer(r"\b(?:const|let|var)\s*\{([^}]*)\}\s*=\s*(?:await\s+)?"
                         r"(?:context\s*\.\s*)?(?:request\s*\.\s*(?:json|formData)\b|params\b|([A-Za-z_$][\w$]*))", maska):
        if m.group(2) and m.group(2) not in objekty:
            continue
        for polozka in m.group(1).split(","):
            jmeno = (polozka.split(":")[-1] if ":" in polozka else polozka).split("=")[0].strip()
            if _JMENO_UZIVATELE.match(jmeno):
                jmena.add(jmeno)
    for m in re.finditer(r"\b(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*([^;\n]+)", maska):
        if _id_z_pozadavku(text[m.start(2):m.end(2)], objekty, jmena):
            jmena.add(m.group(1))
    return objekty, jmena


def _id_z_pozadavku(vyraz: str, objekty: set[str], jmena: set[str]) -> str | None:
    """The part of an expression that is a user id taken from the request."""
    for m in re.finditer(r"\b([A-Za-z_$][\w$]*)\s*(?:\?\.|\.)\s*(?:get\s*\(\s*[\"'`](\w+)[\"'`]|(\w+))"
                         r"|\b([A-Za-z_$][\w$]*)\s*\[\s*[\"'`](\w+)[\"'`]\s*\]", vyraz):
        objekt = m.group(1) or m.group(4)
        klic = m.group(2) or m.group(3) or m.group(5)
        if objekt in objekty and _JMENO_UZIVATELE.match(klic or ""):
            return m.group(0)
    for m in re.finditer(r"[\w$.]*searchParams\s*\.\s*get\s*\(\s*[\"'`](\w+)[\"'`]", vyraz):
        if _JMENO_UZIVATELE.match(m.group(1)):
            return m.group(0)
    for m in re.finditer(r"(?<![\w$.])([A-Za-z_$][\w$]*)\b", vyraz):
        if m.group(1) in jmena:
            return m.group(1)
    return None


def _vyjimka_u(radky: list[str], radek: int) -> bool:
    """mimo-uzivatele on the prepare line itself or in the comment block
    right above it (one code line up when the call is chained)."""
    i = radek - 1  # 0-based index of the prepare line
    if _VYJIMKA.search(radky[i]):
        return True
    if radky[i].lstrip().startswith(".") and i > 0:
        i -= 1
    j = i - 1
    while j >= 0 and radky[j].lstrip().startswith(("//", "*", "/*")):
        if _VYJIMKA.search(radky[j]):
            return True
        j -= 1
    return False


def _zkontroluj_sql(root: Path) -> tuple[list[str], list[str]]:
    """(chyby, výjimky mimo-uzivatele that were honoured)."""
    chyby: list[str] = []
    vyjimky: list[str] = []
    s_uzivatelem = _tabulky_s_uzivatelem(root)
    objednavky = _objednavky_predplatneho(root)
    konstanty = _konstanty(root)
    for path in _soubory(root, root, (".js", ".mjs")):
        rel = _rel(root, path)
        if rel.startswith("web/"):
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        maska = _maska(text)
        radky = text.splitlines()
        objekty, jmena = _z_pozadavku(maska, text)
        for m in re.finditer(r"\bDB\s*\.\s*exec\s*\(", maska):
            chyby.append(f"{rel}:{_radek(text, m.start())}: DB.exec() spouští SQL bez parametrů — "
                         "použij prepare(\"…\").bind(…).")
        for m in re.finditer(r"\.\s*bind\s*\(", maska):
            argumenty = text[m.end():_par(maska, m.end() - 1) - 1]
            zdroj = _id_z_pozadavku(argumenty, objekty, jmena)
            if zdroj:
                chyby.append(f"{rel}:{_radek(text, m.start())}: .bind() dostává uživatele z požadavku "
                             f"({zdroj[:60]}) — kdo volá, si tím vybere cizí účet. Vlastníka ber jen "
                             "z přihlášení (data.uzivatel.id).")
        for m in re.finditer(r"\.prepare\s*\(", maska):
            arg, _ = _argument(text, m.end())
            radek = _radek(text, m.start())
            kde = f"{rel}:{radek}"
            sql, problem = _sql_z_argumentu(arg, konstanty, rel in IDENTIFIKATORY_SMI)
            if problem:
                chyby.append(f"{kde}: {problem}")
                continue
            for zapis in _chranene_zapisy(rel, sql, objednavky):
                chyby.append(f"{kde}: {zapis} — účty, přihlášení, předplatné a platby zapisuje jen šablona "
                             "(přihlášení, platební workflow); kód produktu je jen čte.")
            dotcene = {t.lower() for t in _TABULKA.findall(sql)} & s_uzivatelem
            if dotcene and not re.search(r"\buzivatel_id\b", sql):
                if _vyjimka_u(radky, radek):
                    vyjimky.append(f"{kde}: mimo-uzivatele ({', '.join(sorted(dotcene))})")
                    continue
                chyby.append(f"{kde}: dotaz na {', '.join(sorted(dotcene))} nefiltruje podle uzivatel_id "
                             "— jeden zákazník by viděl nebo měnil data druhého. (Je-li to záměr, "
                             "napiš přímo nad dotaz komentář „mimo-uzivatele: důvod“.)")
    return chyby, vyjimky


# --- who may call which endpoint ---------------------------------------------

# A handler reaches data when it uses anything of the request context — the
# database, the signed-in user, the bindings, the request — itself or
# through a helper it hands them to. Only a handler that ignores all of it
# (a CORS preflight) needs no guard.
_SAHA_NA_DATA = re.compile(r"\b(?:context|ctx|env|request|data|params|DB)\b|\.prepare\s*\(|uzivatel")


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
        text = path.read_text(encoding="utf-8", errors="replace")
        maska = _maska(text)
        handlery, rozumim = _handlery(maska)
        if not handlery:
            continue
        if rel in verejna:
            # The template's public endpoints write by design (logging in,
            # the report form, counters); a product's own public endpoint
            # only reads — a write without an account is open to anyone.
            zapisove = sorted(h for h in handlery if _ZAPISOVE.match(h))
            if rel not in VEREJNE_ZAPISY and zapisove:
                chyby.append(f"{rel}: veřejný endpoint (verejna_api) přijímá zápis ({', '.join(zapisove)}) — "
                             "bez přihlášení smí produkt jen číst.")
            continue
        if not rozumim:
            # An export this checker cannot take apart: the old rule, the
            # guard somewhere in the file, rather than a silent pass.
            if not _STRAZ.search(maska):
                chyby.append(f"{rel}: endpoint neověřuje přihlášeného uživatele "
                             "(if (!data.uzivatel) return json(…, 401)) — nebo ho uveď ve verejna_api s důvodem.")
            continue
        funkce = _funkce(maska)
        strazci = _strazci(root, path, text, maska, funkce)
        for jmeno, (od, do) in sorted(handlery.items()):
            telo = maska[od:do]
            if _STRAZ.search(telo) or any(re.search(rf"\b{re.escape(s)}\s*\(", telo) for s in strazci):
                continue
            # What the handler reaches through local helpers counts as its own.
            dosah, fronta, videno = telo, [telo], {jmeno}
            while fronta:
                kus = fronta.pop()
                for f, (fod, fdo) in funkce.items():
                    if f not in videno and re.search(rf"\b{re.escape(f)}\s*\(", kus):
                        videno.add(f)
                        dosah += maska[fod:fdo]
                        fronta.append(maska[fod:fdo])
            if not _SAHA_NA_DATA.search(dosah):
                continue
            chyby.append(f"{rel}:{_radek(text, od)}: {jmeno} — endpoint neověřuje přihlášeného uživatele "
                         "(if (!data.uzivatel) return json(…, 401) v každém handleru, ne jen v jednom "
                         "v souboru) — nebo soubor uveď ve verejna_api s důvodem.")
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
    """Both templates (once only the one with a database): the browser itself
    refuses to send data anywhere but the product's own /api/ — the second
    wall behind the network check, and the one that holds when a regex
    misses. The static template's pages run scripts and send the report
    form too, and the firm's web is built on it."""
    if not (root / "web").exists():
        return []
    soubor = root / "web" / "_headers"
    if not soubor.exists():
        return ["web/_headers chybí — nese Content-Security-Policy (stavitel ho obnovuje ze šablony)."]
    # Header lines only: the file's own comment explains connect-src, and a
    # deleted directive must not pass because the comment still names it.
    text = "\n".join(r for r in soubor.read_text(encoding="utf-8", errors="replace").splitlines()
                     if not r.lstrip().startswith("#"))
    chyby = []
    chybi = [c for c in _CSP_NUTNE if c not in text]
    if "Content-Security-Policy" not in text or chybi:
        chyby.append(f"web/_headers: Content-Security-Policy nemá {', '.join(chybi) or 'hlavičku'} — "
                     "soubor je ze šablony, neupravuje se.")
    for jmeno, hodnota in _HLAVICKY_NUTNE:
        m = re.search(rf"^\s*{jmeno}\s*:(.*)$", text, re.MULTILINE | re.IGNORECASE)
        if not m or hodnota not in m.group(1):
            chyby.append(f"web/_headers: chybí {jmeno}{': ' + hodnota if hodnota else ''} — "
                         "soubor je ze šablony, neupravuje se.")
    return chyby


# Inline code on a page: a <script> without src (JSON data blocks aside) and
# on…= handler attributes. Every one of them keeps 'unsafe-inline' in the
# CSP, and with it the CSP stops nothing that got into the page as markup.
_INLINE_SKRIPT = re.compile(r"<script\b(?![^>]*\bsrc\s*=)([^>]*)>", re.IGNORECASE)
_DATOVY_SKRIPT = re.compile(r"\btype\s*=\s*[\"']?application/(?:ld\+)?json", re.IGNORECASE)
_OBSLUHA = re.compile(r"\son[a-z]+\s*=\s*[\"'{]", re.IGNORECASE)


def inline_skripty(root: Path | None = None) -> list[str]:
    """Pages with inline scripts or handlers — a warning, never an error:
    builder-made pages have them (Pneusklad's app lives in one), and on the
    live domains Cloudflare inserts an inline script of its own, so the CSP
    keeps 'unsafe-inline' for now. The list is what has to go into .js files
    (handlers into addEventListener) before it can be dropped."""
    root = Path(root or Path(__file__).resolve().parent)
    vysledek = []
    for path in _soubory(root, root / "web", (".html", ".htm")):
        text = path.read_text(encoding="utf-8", errors="replace")
        skripty = sum(1 for m in _INLINE_SKRIPT.finditer(text) if not _DATOVY_SKRIPT.search(m.group(1)))
        obsluhy = sum(len(_OBSLUHA.findall(tag)) for tag in re.findall(r"<[A-Za-z][^>]*>", text))
        if skripty or obsluhy:
            vysledek.append(f"{_rel(root, path)}: inline skripty {skripty}, obsluhy on…= {obsluhy} — "
                            "dokud tu jsou, CSP musí povolit 'unsafe-inline' (patří do .js a addEventListener).")
    return vysledek


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


def zkontroluj_vse(root: Path | None = None, manifest: dict | None = None,
                  preskocit: set[Path] | None = None) -> tuple[list[str], list[str]]:
    """(chyby, upozornění). Upozornění = every honoured mimo-uzivatele
    exception, so their number is in front of the owner and the reviewer
    on every run, not only in the diff that added one."""
    root = Path(root or Path(__file__).resolve().parent)
    if manifest is None:
        cesta = root / "data-manifest.json"
        manifest = json.loads(cesta.read_text(encoding="utf-8")) if cesta.exists() else {}
    preskocit = {Path(p).resolve() for p in (preskocit or set())}
    sql_chyby, vyjimky = _zkontroluj_sql(root)
    chyby = (_zkontroluj_pristup(root, manifest) + sql_chyby
             + _zkontroluj_web(root, preskocit) + _zkontroluj_hlavicky(root)
             + _zkontroluj_hlaseni(root) + _zkontroluj_tajemstvi(root))
    upozorneni = ([f"výjimky z filtru uzivatel_id (mimo-uzivatele): {len(vyjimky)}"] + vyjimky) if vyjimky else []
    return chyby, upozorneni


def zkontroluj(root: Path | None = None, manifest: dict | None = None,
               preskocit: set[Path] | None = None) -> list[str]:
    return zkontroluj_vse(root, manifest, preskocit)[0]


def main() -> int:
    chyby, upozorneni = zkontroluj_vse()
    for chyba in chyby:
        print(" -", chyba)
    for u in upozorneni:
        print(" Upozornění:", u)
    print("Bezpečnostní kontrola prošla." if not chyby else f"Bezpečnostní kontrola: {len(chyby)} nálezů.")
    return 1 if chyby else 0


if __name__ == "__main__":
    sys.exit(main())
