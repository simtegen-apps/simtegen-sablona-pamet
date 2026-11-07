"""Akceptační testy proti skutečnému API produktu — infrastruktura šablony.

NEUPRAVOVAT V PRODUKTU: stavitel tenhle soubor při každé stavbě obnoví ze
šablony; volá ho kontrola_manifestu.py, takže běží v CI každého produktu.
Scénáře produktu jsou v uat/scenare.json — ty píše stavitel podle
akceptačních scénářů ze schválené specifikace.

Why the real API and not a mock: the failures that matter here — one
customer seeing another's data, an endpoint answering without a login, a
handler that crashes on the first real request — live in the Functions and
the SQL, not in the page. So the product runs exactly as Cloudflare runs
it: `wrangler pages dev` (workerd) with a local D1 built from the product's
own migrations, login in development mode (the link comes back in the
response), two fresh accounts A and B.

What runs, in order:
1. every non-public endpoint without a login must answer 4xx — never 2xx,
   never a crash;
2. A and B log in, /api/ja knows them;
3. the product's scenarios (uat/scenare.json), step by step;
4. isolation, automatically: every GET that answered A is repeated as B,
   and B must not get back anything A wrote (the strings from A's bodies);
5. B's data export contains nothing of A's;
6. the demo data (play/ukazka.json) builds, step by step, as its own
   account — the store screenshots are taken on exactly that data.

Run alone:  python uat_kontrola.py [--povinne]
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

WRANGLER = "wrangler@3"
SCENARE = Path("uat") / "scenare.json"
# bezpecnostni_kontrola's public list, plus /api/ja: it answers a stranger
# 200 {"prihlasen": false} on purpose — that is how the page picks the
# login screen — and carries nothing else.
VEREJNA_API_SABLONY = {"functions/api/prihlaseni.js", "functions/api/overeni.js",
                       "functions/api/odhlaseni.js", "functions/api/navsteva.js",
                       # Script errors, counted (P9): a tally like navsteva —
                       # the login screen breaks too, no session to ask for.
                       "functions/api/chyba-stranky.js",
                       "functions/api/ja.js", "functions/api/nahlasit.js",
                       "functions/api/ukazka.js",
                       # The check account (signed request, see the file);
                       # unsigned it answers 400/403/404 like any refusal.
                       "functions/api/kontrolni-prihlaseni.js",
                       # Where customers come from: wraps /api/* after the
                       # product's own handler, never answers by itself.
                       "functions/api/_middleware.js"}
UCTY = {"A": "uat-a@example.cz", "B": "uat-b@example.cz"}
# The accounts that fill the OLD version with data before a new migration
# runs over it (migrace_na_datech) — other addresses than A and B, so the
# new version's scenarios start on fresh accounts beside the old rows.
STARE_UCTY = {"A": "stary-a@example.cz", "B": "stary-b@example.cz"}
SMAZANI_UCTU = "POST /api/ucet/smazat"
UKAZKA = Path("play") / "ukazka.json"
UKAZKOVY_UCET = "ukazka@example.cz"
_METODY = {"onRequestGet": "GET", "onRequestPost": "POST", "onRequestPut": "PUT",
           "onRequestPatch": "PATCH", "onRequestDelete": "DELETE", "onRequest": "GET"}


class Prostredi(Exception):
    """The machine cannot run the check (no Node, no network for the first
    download) — not the product's fault. Mandatory only in CI."""


# --- processes: wrangler spawns node and workerd; kill the whole tree ------

def _spust(argv: list[str], cwd: Path, env: dict, log) -> subprocess.Popen:
    if os.name == "nt":
        return subprocess.Popen(argv, cwd=cwd, env=env, stdout=log, stderr=subprocess.STDOUT,
                                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
    return subprocess.Popen(argv, cwd=cwd, env=env, stdout=log, stderr=subprocess.STDOUT,
                            start_new_session=True)


def _pohrbi(proces: subprocess.Popen) -> None:
    """The tree, while its root still lives: killing only npx left node and
    workerd running and holding the port (seen on the first local trial)."""
    if proces.poll() is None:
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(proces.pid), "/T", "/F"],
                           capture_output=True, timeout=30)
        else:
            try:
                os.killpg(proces.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
    try:
        proces.wait(timeout=10)
    except subprocess.TimeoutExpired:
        if os.name != "nt":
            try:
                os.killpg(proces.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        proces.kill()
        proces.wait()


def _wrangler(npx: str, args: list[str], cwd: Path, env: dict, limit: int) -> tuple[int, str]:
    with tempfile.TemporaryFile() as log:
        proces = _spust([npx, "--yes", WRANGLER, *args], cwd, env, log)
        try:
            proces.wait(timeout=limit)
        except subprocess.TimeoutExpired:
            pass
        finally:
            kod = proces.poll()
            _pohrbi(proces)
        log.seek(0)
        vystup = log.read().decode("utf-8", "replace")
    return (kod if kod is not None else -1), vystup


def _volny_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


# --- HTTP without redirects (the login link answers 303 + Set-Cookie) ------

class _BezPresmerovani(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **kw):
        return None


_OTEVIRAC = urllib.request.build_opener(_BezPresmerovani)


class Klient:
    def __init__(self, zaklad: str, kdo: str):
        self.zaklad, self.kdo, self.cookie = zaklad, kdo, ""
        # Every GET that answered 2xx: after a migration the same account
        # asks again, and what it could read it must still read.
        self.cteni: list[str] = []

    def pozadavek(self, metoda: str, cesta: str, telo=None) -> tuple[int, str, dict]:
        data = None if telo is None else json.dumps(telo, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(self.zaklad + cesta, data=data, method=metoda)
        if data is not None:
            req.add_header("Content-Type", "application/json")
        if self.cookie:
            req.add_header("Cookie", self.cookie)
        try:
            with _OTEVIRAC.open(req, timeout=30) as r:
                if metoda == "GET" and 200 <= r.status < 300:
                    self.cteni.append(cesta)
                return r.status, r.read().decode("utf-8", "replace"), dict(r.headers)
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode("utf-8", "replace"), dict(e.headers or {})

    def prihlas(self, email: str) -> str | None:
        """None when logged in, else what went wrong."""
        kod, text, _ = self.pozadavek("POST", "/api/prihlaseni", {"email": email})
        try:
            odkaz = json.loads(text).get("odkaz")
        except (json.JSONDecodeError, AttributeError):
            odkaz = None
        if kod != 200 or not odkaz:
            return f"/api/prihlaseni vrátil {kod} bez odkazu ve vývojovém režimu: {text[:150]}"
        cesta = odkaz[odkaz.index("/api/"):]
        kod, text, hlavicky = self.pozadavek("GET", cesta)
        m = re.search(r"(relace=[^;]+)", hlavicky.get("Set-Cookie", "") or "")
        if not m:
            return f"přihlašovací odkaz vrátil {kod} bez cookie relace"
        self.cookie = m.group(1)
        kod, text, _ = self.pozadavek("GET", "/api/ja")
        if kod != 200 or email not in text:
            return f"/api/ja po přihlášení nevrátil {email} ({kod}: {text[:120]})"
        return None


# --- endpoints from the file tree -------------------------------------------

def _endpointy(root: Path, verejna: set[str]) -> list[tuple[str, str, str]]:
    """(file, method, path) for every non-public handler; [param] → 1."""
    vysledek = []
    api = root / "functions" / "api"
    for soubor in sorted(api.rglob("*.js")) if api.exists() else []:
        rel = soubor.relative_to(root).as_posix()
        if rel in verejna:
            continue
        casti = list(soubor.relative_to(root / "functions").with_suffix("").parts)
        if casti[-1] == "index":
            casti = casti[:-1]
        cesta = "/" + "/".join("1" if c.startswith("[") else c for c in casti)
        text = soubor.read_text(encoding="utf-8", errors="replace")
        for funkce in re.findall(r"export\s+(?:async\s+)?function\s+(onRequest\w*)", text):
            if funkce in _METODY:
                vysledek.append((rel, _METODY[funkce], cesta))
    return vysledek


def _vyber(data, cesta: str):
    for klic in cesta.split("."):
        if isinstance(data, list) and klic.isdigit() and int(klic) < len(data):
            data = data[int(klic)]
        elif isinstance(data, dict) and klic in data:
            data = data[klic]
        else:
            return None
    return data


def _dosad(hodnota, ulozene: dict):
    if isinstance(hodnota, str):
        return re.sub(r"\{(\w+)\}", lambda m: str(ulozene.get(m.group(1), m.group(0))), hodnota)
    if isinstance(hodnota, list):
        return [_dosad(h, ulozene) for h in hodnota]
    if isinstance(hodnota, dict):
        return {k: _dosad(v, ulozene) for k, v in hodnota.items()}
    return hodnota


def _stopy(telo) -> set[str]:
    """Strings A wrote that B must never get back: letters in them (dates
    and numbers repeat across accounts innocently), five characters or more."""
    if isinstance(telo, str):
        return {telo} if len(telo) >= 5 and re.search(r"[^\W\d_]", telo) else set()
    if isinstance(telo, list):
        return set().union(*(_stopy(t) for t in telo)) if telo else set()
    if isinstance(telo, dict):
        return set().union(*(_stopy(t) for t in telo.values())) if telo else set()
    return set()


def _zkontroluj_scenare(root: Path) -> tuple[list[dict], list[str]]:
    soubor = root / SCENARE
    if not soubor.exists():
        return [], [f"{SCENARE.as_posix()} chybí — akceptační scénáře ze specifikace, které CI spouští "
                    "proti skutečnému API (formát v DESIGN.md / README)."]
    try:
        scenare = json.loads(soubor.read_text(encoding="utf-8")).get("scenare")
    except (json.JSONDecodeError, AttributeError) as e:
        return [], [f"{SCENARE.as_posix()} nejde přečíst: {e}"]
    if not isinstance(scenare, list) or not scenare:
        return [], [f"{SCENARE.as_posix()}: pole „scenare“ je prázdné — aspoň jeden scénář na hlavní hodnotu."]
    chyby = []
    for i, s in enumerate(scenare, 1):
        if not isinstance(s, dict) or not s.get("nazev") or not isinstance(s.get("kroky"), list) or not s["kroky"]:
            chyby.append(f"{SCENARE.as_posix()}: scénář {i} potřebuje „nazev“ a neprázdné „kroky“.")
            continue
        for j, k in enumerate(s["kroky"], 1):
            if (not isinstance(k, dict) or k.get("jako") not in ("A", "B", "nikdo")
                    or not re.match(r"^(GET|POST|PUT|PATCH|DELETE) /", str(k.get("pozadavek", "")))
                    or "ocekavam" not in k):
                chyby.append(f"{SCENARE.as_posix()}: „{s['nazev']}“ krok {j}: potřebuje „jako“ (A/B/nikdo), "
                             "„pozadavek“ („GET /api/…“) a „ocekavam“ (kód nebo seznam kódů).")
        # A regression test of a reported bug names its report (SimteGen's
        # support agent, "H" + the incident number): the firm checks it
        # fails on the version before the fix.
        if "oprava" in s and not re.fullmatch(r"H\d+", str(s.get("oprava"))):
            chyby.append(f"{SCENARE.as_posix()}: „{s['nazev']}“: „oprava“ je číslo hlášení ve tvaru „H123“.")
    return scenare, chyby


def _spust_scenare(scenare: list[dict], klienti: dict[str, Klient]) -> list[str]:
    chyby: list[str] = []
    for s in scenare:
        ulozene: dict = {}
        stopy: set[str] = set()
        cteni_a: list[str] = []
        for j, krok in enumerate(s["kroky"], 1):
            metoda, cesta = krok["pozadavek"].split(" ", 1)
            cesta = _dosad(cesta, ulozene)
            telo = _dosad(krok.get("telo"), ulozene)
            klient = klienti[krok["jako"]]
            kod, text, _ = klient.pozadavek(metoda, cesta, telo)
            kde = f"„{s['nazev']}“ krok {j} ({krok['jako']}: {metoda} {cesta})"
            ocekavam = krok["ocekavam"] if isinstance(krok["ocekavam"], list) else [krok["ocekavam"]]
            if kod not in ocekavam:
                chyby.append(f"{kde}: čekal jsem {'/'.join(map(str, ocekavam))}, přišlo {kod}: {text[:160]}")
                break
            for hledane in krok.get("obsahuje") or []:
                if _dosad(hledane, ulozene) not in text:
                    chyby.append(f"{kde}: odpověď neobsahuje „{hledane}“: {text[:160]}")
            for hledane in krok.get("neobsahuje") or []:
                if _dosad(hledane, ulozene) in text:
                    chyby.append(f"{kde}: odpověď obsahuje „{hledane}“, a nemá.")
            if krok.get("uloz"):
                try:
                    data = json.loads(text)
                except json.JSONDecodeError:
                    data = None
                for jmeno, kde_v in krok["uloz"].items():
                    hodnota = _vyber(data, kde_v)
                    if hodnota is None:
                        chyby.append(f"{kde}: v odpovědi chybí „{kde_v}“ pro uložení {{{jmeno}}}: {text[:120]}")
                    ulozene[jmeno] = hodnota
            if krok["jako"] == "A":
                stopy |= _stopy(telo)
                if metoda == "GET" and 200 <= kod < 300:
                    cteni_a.append(cesta)
        # Isolation: everything A could read, B asks for too.
        for cesta in dict.fromkeys(cteni_a):
            kod, text, _ = klienti["B"].pozadavek("GET", cesta)
            uniklo = sorted(st for st in stopy if st in text) if 200 <= kod < 300 else []
            if uniklo:
                chyby.append(f"„{s['nazev']}“: účet B dostal na GET {cesta} data účtu A "
                             f"({', '.join(u[:30] for u in uniklo[:3])}) — chybí filtr uzivatel_id.")
            if kod >= 500:
                chyby.append(f"„{s['nazev']}“: GET {cesta} jako B spadl ({kod}): {text[:120]}")
    return chyby


def zkontroluj(root: Path | None = None, *, povinne: bool = False) -> tuple[list[str], str]:
    """(problems, note). Only products with accounts and a database (db/)
    are tested — a static page's one endpoint (nahlasit.js) has no data to
    leak and is covered by the template's own scenarios."""
    root = Path(root or Path(__file__).resolve().parent)
    if not (root / "db").exists():
        return [], "bez databáze — akceptační testy se nespouštějí"
    scenare, chyby = _zkontroluj_scenare(root)
    if chyby:
        return chyby, ""
    npx = shutil.which("npx")
    try:
        if npx is None:
            raise Prostredi("na stroji není Node.js (npx)")
        return _zkontroluj_naostro(root, scenare, npx), "API: wrangler pages dev"
    except Prostredi as e:
        if povinne:
            return [f"akceptační testy se nepovedlo spustit: {e}"], ""
        return [], f"akceptační testy přeskočeny: {e}"


class ApiNenabehlo(Exception):
    """The product's own fault: migrations fail, the server dies on start."""


@contextlib.contextmanager
def api_produktu(root: Path, npx: str, stav: Path | None = None):
    """The product running as Cloudflare runs it, on a free local port, with
    a fresh local D1 — yields the base URL. Shared by the acceptance tests
    and the store screenshots (vizualni_kontrola --obchod), so the pictures
    show exactly what the tests exercised. Raises Prostredi (the machine)
    or ApiNenabehlo (the product). `stav` keeps the local D1 outside the
    throwaway copy, so a second run (another version) opens the same
    database — wrangler then applies only the migrations it has not yet."""
    sablona = root / "wrangler.toml.sablona"
    if not sablona.exists():
        raise ApiNenabehlo("wrangler.toml.sablona chybí — bez něj nejde API spustit.")
    prac = Path(tempfile.mkdtemp(prefix="simtegen-uat-"))
    # The product as the repo has it, minus history and local state; mail keys
    # stay out of the environment so login runs in development mode.
    shutil.copytree(root, prac / "p", ignore=shutil.ignore_patterns(
        ".git", "node_modules", ".wrangler", "__pycache__", ".dev.vars", "wrangler.toml"))
    kopie = prac / "p"
    (kopie / "wrangler.toml").write_text(
        sablona.read_text(encoding="utf-8").replace("__PROJEKT__", "uat")
        .replace("__DB_ID__", "00000000-0000-4000-8000-000000000001")
        .replace("__DB_NAHLED_ID__", "00000000-0000-4000-8000-000000000002"), encoding="utf-8")
    env = {k: v for k, v in os.environ.items()
           if k not in ("RESEND_API_KEY", "EMAIL_ODESILATEL", "CLOUDFLARE_API_TOKEN")}
    env.update({"CI": "true", "WRANGLER_SEND_METRICS": "false", "NO_COLOR": "1"})
    server = None
    log = None
    try:
        kod, vystup = _wrangler(npx, ["--version"], kopie, env, 300)
        if kod != 0:
            raise Prostredi(f"wrangler se nepodařilo stáhnout nebo spustit: {vystup.strip()[-200:]}")
        trvale = ["--persist-to", str(stav)] if stav is not None else []
        kod, vystup = _wrangler(npx, ["d1", "migrations", "apply", "uat-db", "--local", *trvale], kopie, env, 180)
        if kod != 0:
            raise ApiNenabehlo(f"migrace databáze neprojdou ani lokálně: {vystup.strip()[-400:]}")

        port = _volny_port()
        log = open(prac / "server.log", "wb")
        server = _spust([npx, "--yes", WRANGLER, "pages", "dev", "web", "--ip", "127.0.0.1",
                         "--port", str(port), "--show-interactive-dev-session=false", *trvale], kopie, env, log)
        zaklad = f"http://127.0.0.1:{port}"
        konec = time.monotonic() + 90
        while True:
            if server.poll() is not None or time.monotonic() > konec:
                log.flush()
                vystup = (prac / "server.log").read_text(encoding="utf-8", errors="replace")
                raise ApiNenabehlo(f"API produktu nenastartovalo (wrangler pages dev): {vystup.strip()[-400:]}")
            try:
                with urllib.request.urlopen(zaklad + "/", timeout=2):
                    break
            except urllib.error.HTTPError:
                break
            except OSError:
                time.sleep(0.5)
        yield zaklad
    finally:
        if server is not None:
            _pohrbi(server)
        if log is not None:
            log.close()
        # workerd on Windows lets go of the local D1 files seconds after the
        # tree is killed; 5 s left a copy of the product behind per run, and
        # the reviewer now starts this for every build.
        for _ in range(30):
            shutil.rmtree(prac, ignore_errors=True)
            if not prac.exists():
                break
            time.sleep(0.5)


def jen_scenare(root: Path, scenare: list[dict], npx: str) -> dict[str, list[str]]:
    """Run only these scenarios against the product at `root` (accounts A
    and B logged in) — scenario name → what failed ([] = passed). SimteGen
    runs a fix's regression scenarios against the version BEFORE the fix:
    a test that passes there does not catch the bug. Raises Prostredi /
    ApiNenabehlo like api_produktu."""
    with api_produktu(root, npx) as zaklad:
        klienti = {"nikdo": Klient(zaklad, "nikdo")}
        for kdo, email in UCTY.items():
            klienti[kdo] = Klient(zaklad, kdo)
            chyba = klienti[kdo].prihlas(email)
            if chyba:
                raise ApiNenabehlo(f"přihlášení účtu {kdo} nefunguje: {chyba}")
        return {s["nazev"]: _spust_scenare([s], klienti) for s in scenare}


def migrace_na_datech(stara: Path, nova: Path, npx: str) -> tuple[list[str], str]:
    """(problems, note) — the new version's migrations over a database the
    OLD version filled with data, as production will be.

    Every other run starts on an empty database, where a migration that
    breaks on existing rows (a unique index over duplicates, a rebuilt table
    whose NOT NULL column the old rows leave empty, a backfill that trips on
    real values) passes — and fails first in production, at the deploy's
    migration step, or worse, succeeds and leaves the app unable to read
    what customers stored. So:
      1. the old version (`stara`, main) runs, its scenarios and demo data
         fill the database as the old accounts — scenarios that delete the
         account are left out, they would take their rows with them;
      2. the new version (`nova`) starts over THE SAME database: its new
         migrations apply on rows; failing = the build's problem;
      3. the old accounts still logged in ask again for everything they
         could read: never 5xx, never logged out (a migration must not
         sign every customer out), the export still works;
      4. the new version's scenarios run on fresh accounts beside the old
         rows.
    A note (no problems) when the old version cannot even fill anything —
    then this run proves nothing and says so. Raises Prostredi (the machine)."""
    prac = Path(tempfile.mkdtemp(prefix="simtegen-migrace-"))
    stav = prac / "d1"
    try:
        stare_scenare, chyby = _zkontroluj_scenare(stara)
        stare_scenare = [] if chyby else [
            sc for sc in stare_scenare
            if not any(str(k.get("pozadavek", "")).startswith(SMAZANI_UCTU) for k in sc["kroky"])]
        stari: list[Klient] = []
        try:
            with api_produktu(stara, npx, stav=stav) as zaklad:
                klienti = {"nikdo": Klient(zaklad, "nikdo")}
                for kdo, email in STARE_UCTY.items():
                    klienti[kdo] = Klient(zaklad, kdo)
                    if klienti[kdo].prihlas(email):
                        return [], "stará verze nejde přihlásit — migrace na datech neověřena"
                # The old version's own failures are not this build's.
                _spust_scenare(stare_scenare, klienti)
                ucastnici = [klienti["A"], klienti["B"]]
                if (stara / UKAZKA).exists():
                    ukazka = Klient(zaklad, "ukazka")
                    if not ukazka.prihlas(UKAZKOVY_UCET):
                        spust_ukazku(stara, ukazka)
                        ucastnici.append(ukazka)
                stari = [k for k in ucastnici if k.pozadavek("GET", "/api/ja")[0] == 200]
        except ApiNenabehlo as e:
            return [], f"stará verze nenaběhla ({str(e)[:120]}) — migrace na datech neověřena"
        if not any(k.cteni for k in stari):
            return [], "stará verze nic neuložila (žádné scénáře ani ukázka) — migrace na datech neověřena"
        try:
            with api_produktu(nova, npx, stav=stav) as zaklad:
                chyby = []
                for k in stari:
                    k.zaklad = zaklad
                    cteni, k.cteni = list(dict.fromkeys(k.cteni)), []
                    for cesta in cteni + ["/api/ucet/export"]:
                        kod, text, _ = k.pozadavek("GET", cesta)
                        if kod >= 500:
                            chyby.append(f"po migraci spadl GET {cesta} účtu ze staré verze ({kod}): {text[:160]}")
                        elif kod in (401, 403):
                            chyby.append(f"po migraci účet ze staré verze na GET {cesta} vrací {kod} — "
                                         "migrace odhlásila zákazníky nebo jim vzala přístup k jejich datům")
                            break
                klienti = {"nikdo": Klient(zaklad, "nikdo")}
                for kdo, email in UCTY.items():
                    klienti[kdo] = Klient(zaklad, kdo)
                    chyba = klienti[kdo].prihlas(email)
                    if chyba:
                        return chyby + [f"na databázi staré verze nefunguje přihlášení: {chyba}"], ""
                nove_scenare, chyby_sc = _zkontroluj_scenare(nova)
                if not chyby_sc:
                    chyby += [f"s daty staré verze: {c}" for c in _spust_scenare(nove_scenare, klienti)]
                return chyby, ""
        except ApiNenabehlo as e:
            return [f"nová verze nad databází staré verze s daty nenaběhla — migrace neprojde na existujících "
                    f"řádcích (v produkci by spadla při nasazení): {e}"], ""
    finally:
        for _ in range(30):
            shutil.rmtree(prac, ignore_errors=True)
            if not prac.exists():
                break
            time.sleep(0.5)


def spust_ukazku(root: Path, klient: Klient) -> list[str]:
    """play/ukazka.json as the demo account: the data the store screenshots
    show. Every step must succeed (2xx unless it says otherwise) — a demo
    that breaks would photograph an error."""
    soubor = root / UKAZKA
    if not soubor.exists():
        return []
    try:
        kroky = json.loads(soubor.read_text(encoding="utf-8")).get("kroky") or []
    except (json.JSONDecodeError, AttributeError) as e:
        return [f"{UKAZKA.as_posix()} nejde přečíst: {e}"]
    ulozene: dict = {}
    for j, krok in enumerate(kroky, 1):
        metoda, cesta = str(krok.get("pozadavek", "")).split(" ", 1)
        cesta = _dosad(cesta, ulozene)
        kod, text, _ = klient.pozadavek(metoda, cesta, _dosad(krok.get("telo"), ulozene))
        ocekavam = krok.get("ocekavam")
        dobre = (kod in (ocekavam if isinstance(ocekavam, list) else [ocekavam])) if ocekavam else 200 <= kod < 300
        if not dobre:
            return [f"{UKAZKA.as_posix()} krok {j} ({metoda} {cesta}): přišlo {kod}: {text[:160]}"]
        for jmeno, kde_v in (krok.get("uloz") or {}).items():
            try:
                hodnota = _vyber(json.loads(text), kde_v)
            except json.JSONDecodeError:
                hodnota = None
            if hodnota is None:
                return [f"{UKAZKA.as_posix()} krok {j}: v odpovědi chybí „{kde_v}“ pro {{{jmeno}}}: {text[:120]}"]
            ulozene[jmeno] = hodnota
    return []


def _zkontroluj_naostro(root: Path, scenare: list[dict], npx: str) -> list[str]:
    manifest_cesta = root / "data-manifest.json"
    manifest = json.loads(manifest_cesta.read_text(encoding="utf-8")) if manifest_cesta.exists() else {}
    verejna = set(VEREJNA_API_SABLONY) | {
        (p or {}).get("soubor", "").replace("\\", "/") for p in manifest.get("verejna_api") or []
        if isinstance(p, dict)}
    try:
        with api_produktu(root, npx) as zaklad:
            return _proti_api(root, zaklad, scenare, verejna)
    except ApiNenabehlo as e:
        return [str(e)]


def _proti_api(root: Path, zaklad: str, scenare: list[dict], verejna: set[str]) -> list[str]:
    chyby: list[str] = []
    nikdo = Klient(zaklad, "nikdo")
    for soubor, metoda, cesta in _endpointy(root, verejna):
        kod, text, _ = nikdo.pozadavek(metoda, cesta, {} if metoda != "GET" else None)
        if 200 <= kod < 300:
            chyby.append(f"{soubor}: {metoda} {cesta} bez přihlášení vrátil {kod} — data či akce "
                         "dostupné komukoli.")
        elif kod >= 500:
            chyby.append(f"{soubor}: {metoda} {cesta} bez přihlášení spadl ({kod}): {text[:120]}")

    klienti = {"nikdo": nikdo}
    for kdo, email in UCTY.items():
        klienti[kdo] = Klient(zaklad, kdo)
        chyba = klienti[kdo].prihlas(email)
        if chyba:
            return chyby + [f"přihlášení účtu {kdo} nefunguje: {chyba}"]

    chyby += _spust_scenare(scenare, klienti)

    kod, export_b, _ = klienti["B"].pozadavek("GET", "/api/ucet/export")
    if kod == 200 and UCTY["A"] in export_b:
        chyby.append("export dat účtu B obsahuje e-mail účtu A.")

    # The demo data must work on every build, not first in the release run
    # — a broken step would otherwise surface as a store listing of errors.
    if (root / UKAZKA).exists():
        ukazka = Klient(zaklad, "ukazka")
        chyba = ukazka.prihlas(UKAZKOVY_UCET)
        chyby += [f"přihlášení ukázkového účtu nefunguje: {chyba}"] if chyba else spust_ukazku(root, ukazka)
    return chyby


def main() -> int:
    povinne = "--povinne" in sys.argv or os.environ.get("GITHUB_ACTIONS") == "true"
    chyby, poznamka = zkontroluj(povinne=povinne)
    for c in chyby:
        print(" -", c)
    print(poznamka or ("Akceptační testy prošly." if not chyby else f"Akceptační testy: {len(chyby)} nálezů."))
    return 1 if chyby else 0


if __name__ == "__main__":
    sys.exit(main())
