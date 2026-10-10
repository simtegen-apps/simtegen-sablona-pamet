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
5. B's data export contains nothing of A's.

Run alone:  python uat_kontrola.py [--povinne]
"""

from __future__ import annotations

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
                       "functions/api/ja.js", "functions/api/nahlasit.js"}
UCTY = {"A": "uat-a@example.cz", "B": "uat-b@example.cz"}
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

    def pozadavek(self, metoda: str, cesta: str, telo=None) -> tuple[int, str, dict]:
        data = None if telo is None else json.dumps(telo, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(self.zaklad + cesta, data=data, method=metoda)
        if data is not None:
            req.add_header("Content-Type", "application/json")
        if self.cookie:
            req.add_header("Cookie", self.cookie)
        try:
            with _OTEVIRAC.open(req, timeout=30) as r:
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
    sablona = root / "wrangler.toml.sablona"
    if not sablona.exists():
        return ["wrangler.toml.sablona chybí — bez něj nejde API spustit."], ""
    npx = shutil.which("npx")
    try:
        if npx is None:
            raise Prostredi("na stroji není Node.js (npx)")
        return _zkontroluj_naostro(root, scenare, npx, sablona), "API: wrangler pages dev"
    except Prostredi as e:
        if povinne:
            return [f"akceptační testy se nepovedlo spustit: {e}"], ""
        return [], f"akceptační testy přeskočeny: {e}"


def _zkontroluj_naostro(root: Path, scenare: list[dict], npx: str, sablona: Path) -> list[str]:
    manifest_cesta = root / "data-manifest.json"
    manifest = json.loads(manifest_cesta.read_text(encoding="utf-8")) if manifest_cesta.exists() else {}
    verejna = set(VEREJNA_API_SABLONY) | {
        (p or {}).get("soubor", "").replace("\\", "/") for p in manifest.get("verejna_api") or []
        if isinstance(p, dict)}

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
        kod, vystup = _wrangler(npx, ["d1", "migrations", "apply", "uat-db", "--local"], kopie, env, 180)
        if kod != 0:
            return [f"migrace databáze neprojdou ani lokálně: {vystup.strip()[-400:]}"]

        port = _volny_port()
        log = open(prac / "server.log", "wb")
        server = _spust([npx, "--yes", WRANGLER, "pages", "dev", "web", "--ip", "127.0.0.1",
                         "--port", str(port), "--show-interactive-dev-session=false"], kopie, env, log)
        zaklad = f"http://127.0.0.1:{port}"
        konec = time.monotonic() + 90
        while True:
            if server.poll() is not None or time.monotonic() > konec:
                log.flush()
                vystup = (prac / "server.log").read_text(encoding="utf-8", errors="replace")
                return [f"API produktu nenastartovalo (wrangler pages dev): {vystup.strip()[-400:]}"]
            try:
                with urllib.request.urlopen(zaklad + "/", timeout=2):
                    break
            except urllib.error.HTTPError:
                break
            except OSError:
                time.sleep(0.5)

        chyby: list[str] = []
        nikdo = Klient(zaklad, "nikdo")
        for soubor, metoda, cesta in _endpointy(kopie, verejna):
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
        return chyby
    finally:
        if server is not None:
            _pohrbi(server)
        if log is not None:
            log.close()
        for _ in range(10):
            shutil.rmtree(prac, ignore_errors=True)
            if not prac.exists():
                break
            time.sleep(0.5)


def main() -> int:
    povinne = "--povinne" in sys.argv or os.environ.get("GITHUB_ACTIONS") == "true"
    chyby, poznamka = zkontroluj(povinne=povinne)
    for c in chyby:
        print(" -", c)
    print(poznamka or ("Akceptační testy prošly." if not chyby else f"Akceptační testy: {len(chyby)} nálezů."))
    return 1 if chyby else 0


if __name__ == "__main__":
    sys.exit(main())
