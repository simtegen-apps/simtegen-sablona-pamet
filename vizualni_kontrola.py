"""Vizuální kontrola produktu ve skutečném prohlížeči — infrastruktura šablony.

NEUPRAVOVAT V PRODUKTU: stavitel tenhle soubor při každé stavbě obnoví ze
šablony, stejně jako kontrola_manifestu.py, která ho volá.

Why a browser and not more regexes: the failures the owner kept seeing —
a page that scrolls sideways on a phone, a tablet that is just a stretched
phone, grey-on-paper text nobody can read, a button too small for a thumb —
exist only after layout. The static design check can prove the page loads
the right files; only rendering proves the result fits.

How, without dependencies (CI runs plain python3, the mini PC has no pip
packages): the Chromium the machine already has (Chrome on the GitHub
runner, Edge on Windows) started headless, driven over the DevTools
protocol through a minimal WebSocket client below. web/ is served from
127.0.0.1 with every /api/ answering 401, so the app shows its signed-out
state; each .obrazovka is then shown in turn (the template's ukaz(), or
plain toggling) and measured at five widths, light and dark. Resizing
re-runs the media queries live, so one page load covers every width.

All other network is mapped to nowhere (--host-resolver-rules): product
JavaScript is model-written, and a check that runs it must not be the
thing that lets it phone home.

Run alone:  python vizualni_kontrola.py [--snimky DIR] [--json] [--povinne]
"""

from __future__ import annotations

import base64
import http.server
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

# Pages that are not app screens: generated legal texts (both templates'
# lists) and the offline shell from vykresli_aplikaci.py.
PRESKOCIT = {"zasady.html", "podminky.html", "zpracovatelska-smlouva.html",
             "odstoupeni-formular.html", "offline.html"}

# (name, width, height, screenshot?) — 360 is the small Android the owner's
# customers actually carry; 820 is the narrow end of the tablet layout, where
# a 12-column grid overflows first; 1180 the wide end; 1440 a notebook.
SIRKY = (
    ("telefon-maly", 360, 740, False),
    ("telefon", 390, 844, True),
    ("tablet", 820, 1180, True),
    ("tablet-sirsi", 1180, 820, False),
    ("notebook", 1440, 900, True),
)
TELEFON_DO = 768          # below this the thumb rules apply
MAX_SNIMKU = 14           # what the reviewer can usefully look at in one turn
SIROCE_OBRAZOVEK = 2      # screens shown at all three widths; the rest phone only
MAX_PROBLEMU_NA_DRUH = 6  # per screen and kind — the first few say enough


def najdi_prohlizec() -> str | None:
    """Chrome/Chromium/Edge, whichever the machine has. PROHLIZEC overrides."""
    if os.environ.get("PROHLIZEC"):
        return os.environ["PROHLIZEC"]
    for jmeno in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser",
                  "chrome", "msedge", "microsoft-edge"):
        cesta = shutil.which(jmeno)
        if cesta:
            return cesta
    for promenna, rel in (("ProgramFiles(x86)", r"Microsoft\Edge\Application\msedge.exe"),
                          ("ProgramFiles", r"Microsoft\Edge\Application\msedge.exe"),
                          ("ProgramFiles", r"Google\Chrome\Application\chrome.exe"),
                          ("LOCALAPPDATA", r"Google\Chrome\Application\chrome.exe")):
        zaklad = os.environ.get(promenna)
        if zaklad and (Path(zaklad) / rel).exists():
            return str(Path(zaklad) / rel)
    return None


# --- minimal WebSocket client (RFC 6455, text frames only) -----------------

class _WebSocket:
    def __init__(self, url: str, timeout: float = 30.0):
        assert url.startswith("ws://")
        hostport, _, path = url[5:].partition("/")
        host, _, port = hostport.partition(":")
        self.sock = socket.create_connection((host, int(port or 80)), timeout=timeout)
        klic = base64.b64encode(os.urandom(16)).decode()
        self.sock.sendall((f"GET /{path} HTTP/1.1\r\nHost: {hostport}\r\nUpgrade: websocket\r\n"
                           f"Connection: Upgrade\r\nSec-WebSocket-Key: {klic}\r\n"
                           "Sec-WebSocket-Version: 13\r\n\r\n").encode())
        hlavicka = b""
        while b"\r\n\r\n" not in hlavicka:
            kus = self.sock.recv(4096)
            if not kus:
                raise ConnectionError("prohlížeč zavřel spojení při navazování")
            hlavicka += kus
        if b" 101 " not in hlavicka.split(b"\r\n", 1)[0]:
            raise ConnectionError(f"DevTools odmítl WebSocket: {hlavicka[:120]!r}")
        self._zbytek = hlavicka.split(b"\r\n\r\n", 1)[1]

    def _presne(self, n: int) -> bytes:
        while len(self._zbytek) < n:
            kus = self.sock.recv(max(65536, n - len(self._zbytek)))
            if not kus:
                raise ConnectionError("prohlížeč zavřel spojení")
            self._zbytek += kus
        data, self._zbytek = self._zbytek[:n], self._zbytek[n:]
        return data

    def _posli_ramec(self, opcode: int, data: bytes) -> None:
        maska = os.urandom(4)
        delka = len(data)
        if delka < 126:
            hlava = bytes([0x80 | opcode, 0x80 | delka])
        elif delka < 65536:
            hlava = bytes([0x80 | opcode, 0x80 | 126]) + delka.to_bytes(2, "big")
        else:
            hlava = bytes([0x80 | opcode, 0x80 | 127]) + delka.to_bytes(8, "big")
        self.sock.sendall(hlava + maska + bytes(b ^ maska[i % 4] for i, b in enumerate(data)))

    def posli(self, text: str) -> None:
        self._posli_ramec(0x1, text.encode("utf-8"))

    def prijmi(self) -> str:
        zprava = b""
        while True:
            b1, b2 = self._presne(2)
            opcode, delka = b1 & 0x0F, b2 & 0x7F
            if delka == 126:
                delka = int.from_bytes(self._presne(2), "big")
            elif delka == 127:
                delka = int.from_bytes(self._presne(8), "big")
            maska = self._presne(4) if b2 & 0x80 else b""
            data = self._presne(delka)
            if maska:
                data = bytes(b ^ maska[i % 4] for i, b in enumerate(data))
            if opcode == 0x8:
                raise ConnectionError("prohlížeč ukončil spojení")
            if opcode == 0x9:
                self._posli_ramec(0xA, data)
                continue
            if opcode in (0x0, 0x1, 0x2):
                zprava += data
                if b1 & 0x80:
                    return zprava.decode("utf-8", "replace")

    def zavri(self) -> None:
        try:
            self.sock.close()
        except OSError:
            pass


class _DevTools:
    def __init__(self, ws: _WebSocket):
        self.ws = ws
        self._id = 0
        self._udalosti: list[dict] = []
        # Page commands travel in the session of the tab we opened ourselves;
        # browser-level ones (createTarget, close) without it.
        self.session: str | None = None

    def volej(self, metoda: str, **parametry):
        self._id += 1
        moje = self._id
        zprava_ven = {"id": moje, "method": metoda, "params": parametry}
        if self.session and not metoda.startswith(("Target.", "Browser.")):
            zprava_ven["sessionId"] = self.session
        self.ws.posli(json.dumps(zprava_ven))
        while True:
            zprava = json.loads(self.ws.prijmi())
            if zprava.get("id") == moje:
                if "error" in zprava:
                    raise RuntimeError(f"{metoda}: {zprava['error'].get('message')}")
                return zprava.get("result", {})
            if "method" in zprava:
                self._udalosti.append(zprava)

    def cekej_na(self, udalost: str, limit: float = 15.0) -> bool:
        konec = time.monotonic() + limit
        while time.monotonic() < konec:
            for i, z in enumerate(self._udalosti):
                if z.get("method") == udalost:
                    del self._udalosti[: i + 1]
                    return True
            self.ws.sock.settimeout(max(0.1, konec - time.monotonic()))
            try:
                zprava = json.loads(self.ws.prijmi())
            except socket.timeout:
                break
            finally:
                self.ws.sock.settimeout(30.0)
            if "method" in zprava:
                self._udalosti.append(zprava)
        return False

    def js(self, vyraz: str):
        vysledek = self.volej("Runtime.evaluate", expression=vyraz, returnByValue=True,
                              awaitPromise=True)
        if "exceptionDetails" in vysledek:
            raise RuntimeError("chyba skriptu kontroly: "
                               + str(vysledek["exceptionDetails"].get("text"))[:200])
        return vysledek.get("result", {}).get("value")


# --- local server: web/ as files, /api/ as "signed out" --------------------

def _hlavicky_pages(web: Path) -> list[tuple[str, str]]:
    """The `/*` block of web/_headers, as Cloudflare Pages would send it.
    The check renders under the product's real CSP: a page that works here
    and breaks in production behind its own header is what this prevents."""
    soubor = web / "_headers"
    if not soubor.exists():
        return []
    hlavicky, v_bloku = [], False
    for radek in soubor.read_text(encoding="utf-8", errors="replace").splitlines():
        if not radek.strip() or radek.lstrip().startswith("#"):
            continue
        if not radek[0].isspace():
            v_bloku = radek.strip() == "/*"
        elif v_bloku and ":" in radek:
            jmeno, _, hodnota = radek.strip().partition(":")
            hlavicky.append((jmeno.strip(), hodnota.strip()))
    return hlavicky


def _server(web: Path) -> http.server.ThreadingHTTPServer:
    hlavicky = _hlavicky_pages(web)

    class Obsluha(http.server.SimpleHTTPRequestHandler):
        def end_headers(self):
            if not self.path.startswith("/api/"):
                for jmeno, hodnota in hlavicky:
                    self.send_header(jmeno, hodnota)
            super().end_headers()

        # Windows takes MIME types from the registry, where .js can be
        # text/plain; the page must load the same way it does on Pages.
        extensions_map = {**http.server.SimpleHTTPRequestHandler.extensions_map,
                          ".js": "text/javascript", ".mjs": "text/javascript",
                          ".css": "text/css", ".woff2": "font/woff2",
                          ".webmanifest": "application/manifest+json", ".svg": "image/svg+xml"}

        def __init__(self, *a, **kw):
            super().__init__(*a, directory=str(web), **kw)

        def _api(self) -> bool:
            if not self.path.startswith("/api/"):
                return False
            telo = json.dumps({"chyba": "Nejsi přihlášený."}).encode("utf-8")
            self.send_response(401)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(telo)))
            self.end_headers()
            self.wfile.write(telo)
            return True

        def do_GET(self):
            if not self._api():
                super().do_GET()

        def do_POST(self):
            if not self._api():
                self.send_error(405)

        do_PUT = do_DELETE = do_PATCH = do_POST

        def log_message(self, *a):
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Obsluha)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


# --- what is measured on each screen at each width -------------------------

_MERENI = r"""
(() => {
  const W = document.documentElement.clientWidth;
  // The report form is measured on its own: the page behind it already was.
  const koren = window.__sgKoren || document.body;
  const telefon = W < %(telefon)d;
  const out = {preteka: [], popisky: [], tlacitka: [], obrazky: [], kontrast: [], male: []};
  const vid = (el) => {
    const r = el.getBoundingClientRect();
    if (r.width < 2 || r.height < 2) return false;
    for (let e = el; e; e = e.parentElement) {
      const cs = getComputedStyle(e);
      if (cs.display === 'none' || cs.visibility === 'hidden') return false;
    }
    return true;
  };
  const popis = (el) => {
    let s = el.tagName.toLowerCase();
    if (el.id) s += '#' + el.id;
    else { const c = [...el.classList].slice(0, 2).join('.'); if (c) s += '.' + c; }
    const t = (el.innerText || el.value || el.getAttribute('aria-label') || '').trim().replace(/\s+/g, ' ').slice(0, 30);
    return t ? s + ' „' + t + '“' : s;
  };
  const pridej = (pole, x) => { if (pole.length < %(max)d) pole.push(x); };

  // 1. Sideways scroll: name the element that sticks out of a parent that fits.
  if (document.documentElement.scrollWidth > W + 1) {
    for (const el of koren.querySelectorAll('*')) {
      if (!vid(el)) continue;
      const r = el.getBoundingClientRect();
      const p = el.parentElement && el.parentElement.getBoundingClientRect();
      if (r.right > W + 1 && (!p || p.right <= W + 1)) {
        let posuvne = false;
        for (let e = el.parentElement; e; e = e.parentElement) {
          if (['auto', 'scroll', 'hidden', 'clip'].includes(getComputedStyle(e).overflowX)) { posuvne = true; break; }
        }
        if (!posuvne) pridej(out.preteka, popis(el) + ' (' + Math.round(r.right) + ' px)');
      }
    }
    if (!out.preteka.length) out.preteka.push('stránka je široká ' + document.documentElement.scrollWidth + ' px');
  }

  // 2. Every field has a label, every button and link says what it does.
  for (const el of koren.querySelectorAll('input, select, textarea')) {
    if (['hidden', 'submit', 'button', 'reset', 'image'].includes(el.type) || !vid(el)) continue;
    if (!((el.labels && el.labels.length) || el.getAttribute('aria-label') || el.getAttribute('aria-labelledby') || el.title))
      pridej(out.popisky, popis(el));
  }
  for (const el of koren.querySelectorAll('button, [role=button], a[href]')) {
    if (!vid(el)) continue;
    const jmeno = (el.innerText || '').trim() || el.getAttribute('aria-label') || el.title
      || [...el.querySelectorAll('img[alt], svg title')].map((x) => x.alt || x.textContent).join('').trim();
    if (!jmeno) pridej(out.tlacitka, popis(el));
  }
  for (const el of koren.querySelectorAll('img')) {
    if (vid(el) && !el.hasAttribute('alt')) pridej(out.obrazky, popis(el));
  }

  // 3. Thumb-sized targets on a phone (DESIGN.md: 44 px; 40 leaves room for borders).
  if (telefon) {
    for (const el of koren.querySelectorAll('button, [role=button], select, textarea, input, a.tlacitko, .volba, nav a')) {
      if (['hidden', 'checkbox', 'radio'].includes(el.type) || !vid(el)) continue;
      if (getComputedStyle(el).display === 'inline') continue;
      const r = el.getBoundingClientRect();
      if (r.height < 40 || r.width < 40) pridej(out.male, popis(el) + ' ' + Math.round(r.width) + '×' + Math.round(r.height) + ' px');
    }
  }

  // 4. Text contrast against what is actually behind it (WCAG AA).
  const barva = (s) => {
    let m = s.match(/^rgba?\(([^)]+)\)/);
    if (m) { const p = m[1].split(/[\s,\/]+/).filter(Boolean).map(Number); return [p[0], p[1], p[2], p.length > 3 ? p[3] : 1]; }
    m = s.match(/^color\(srgb ([^)]+)\)/);
    if (m) { const p = m[1].split(/[\s\/]+/).filter(Boolean).map(Number); return [p[0] * 255, p[1] * 255, p[2] * 255, p.length > 3 ? p[3] : 1]; }
    return null;
  };
  const smichej = (horni, spodni, a) => [0, 1, 2].map((i) => horni[i] * a + spodni[i] * (1 - a));
  const jas = (c) => {
    const k = c.map((v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); });
    return 0.2126 * k[0] + 0.7152 * k[1] + 0.0722 * k[2];
  };
  const pozadi = (el) => {
    const vrstvy = [];
    for (let e = el; e; e = e.parentElement) {
      const cs = getComputedStyle(e);
      // A gradient or picture under the text: its colour there is unknown,
      // and guessing from the page behind it called white-on-green 1.1:1.
      // The page's own dot grid (html/body) is decoration on a known paper.
      if (cs.backgroundImage !== 'none' && e !== document.body && e !== document.documentElement) return null;
      const c = barva(cs.backgroundColor);
      if (c && c[3] > 0) { vrstvy.push(c); if (c[3] >= 1) break; }
    }
    let vysledek = [255, 255, 255];
    for (const v of vrstvy.reverse()) vysledek = smichej(v, vysledek, v[3]);
    return vysledek;
  };
  for (const el of koren.querySelectorAll('*')) {
    const text = [...el.childNodes].filter((n) => n.nodeType === 3).map((n) => n.textContent).join('').trim();
    if (!text || !vid(el) || el.closest('.sg-start') || el.disabled) continue;
    const cs = getComputedStyle(el);
    let fg = barva(cs.color), bg = pozadi(el);
    if (!fg || !bg) continue;
    let pruhlednost = fg[3];
    for (let e = el; e; e = e.parentElement) pruhlednost *= parseFloat(getComputedStyle(e).opacity);
    const c = smichej(fg, bg, pruhlednost);
    const a = jas(c), b = jas(bg);
    const pomer = (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05);
    const velikost = parseFloat(cs.fontSize), tucne = parseInt(cs.fontWeight, 10) >= 700;
    const limit = (velikost >= 24 || (velikost >= 18.66 && tucne)) ? 3 : 4.5;
    if (pomer < limit - 0.05) pridej(out.kontrast, popis(el) + ' ' + pomer.toFixed(2) + ':1');
  }
  return out;
})()
""" % {"telefon": TELEFON_DO, "max": MAX_PROBLEMU_NA_DRUH}

_DRUHY = {
    "preteka": "obsah přetéká do strany (vodorovné posouvání)",
    "popisky": "pole bez popisku (label, aria-label)",
    "tlacitka": "tlačítko nebo odkaz bez textu",
    "obrazky": "obrázek bez alt",
    "male": "dotykový cíl menší než 44 px",
    "kontrast": "text s nedostatečným kontrastem",
}

_UVODNI = r"""
(() => {
  const s = document.querySelector('.sg-start');
  if (!s || !s.isConnected) return 'pryc';
  const cs = getComputedStyle(s);
  return (s.hidden || cs.display === 'none' || cs.visibility === 'hidden' || parseFloat(cs.opacity) === 0) ? 'pryc' : 'videt';
})()
"""

# Injected before any page script: notes that the splash appeared at all.
# Sampling after the load event raced with simtegen.js's own 2.5 s fallback
# on a slow runner — the logo had come and gone before anyone looked.
_HLIDAC_UVODNI = r"""
window.__sgStart = { videna: false };
new MutationObserver((zmeny, o) => {
  if (document.querySelector('.sg-start')) { window.__sgStart.videna = true; o.disconnect(); }
}).observe(document, { childList: true, subtree: true });
// What the Content-Security-Policy refused: in production that piece of the
// page silently does nothing — or the page tried to reach a foreign server.
window.__sgCsp = [];
document.addEventListener('securitypolicyviolation', (e) => {
  const zaznam = (e.effectiveDirective || e.violatedDirective) + ' ← ' + (e.blockedURI || 'inline');
  if (!window.__sgCsp.includes(zaznam)) window.__sgCsp.push(zaznam);
});
"""

_OBRAZOVKY = "[...document.querySelectorAll('.obrazovka[id]')].map((e) => e.id)"

# Reporting is mandatory: some .nahlasit-chybu must be on screen (scrolling
# allowed — the footer counts), and clicking it must open the form that
# simtegen.js builds.
_HLASENI_VIDET = r"""
(() => [...document.querySelectorAll('.nahlasit-chybu')].some((el) => {
  const r = el.getBoundingClientRect();
  if (r.width < 2 || r.height < 2) return false;
  for (let e = el; e; e = e.parentElement) {
    const cs = getComputedStyle(e);
    if (cs.display === 'none' || cs.visibility === 'hidden') return false;
  }
  return true;
}))()
"""

_HLASENI_OTEVRI = r"""
(() => {
  const vid = (el) => { const r = el.getBoundingClientRect(); return r.width > 1 && r.height > 1; };
  const tl = [...document.querySelectorAll('.nahlasit-chybu')].find(vid);
  if (!tl) return 'bez-tlacitka';
  tl.click();
  const panel = document.querySelector('.sg-hlaseni');
  if (!panel || panel.hidden) return 'neotevrel';
  const pole = panel.querySelector('textarea');
  if (!pole || !vid(pole) || !(pole.labels && pole.labels.length)) return 'bez-pole';
  return 'ok';
})()
"""

_HLASENI_ZAVRI = r"""
(() => { const p = document.querySelector('.sg-hlaseni'); const z = p && p.querySelector('.tlacitko.tiche');
  if (z) z.click(); return !p || p.hidden; })()
"""


def _zkus_hlaseni(dt: "_DevTools", jmeno: str, obrazovky: list, nalezy: dict) -> list[str]:
    """Click the report button on the first screen that shows one, check the
    form opened, measure the form itself (it is part of every app), close."""
    _velikost(dt, SIRKY[1][1], SIRKY[1][2])
    for obrazovka in obrazovky:
        if obrazovka:
            dt.js(_UKAZ % json.dumps(obrazovka))
        if not dt.js(_HLASENI_VIDET):
            continue
        stav = dt.js(_HLASENI_OTEVRI)
        if stav != "ok":
            return [f"web/{jmeno}: klepnutí na „Nahlásit chybu“ neotevřelo formulář s popsaným polem "
                    f"({stav}) — formulář staví simtegen.js, stránka ho musí načítat."]
        time.sleep(0.2)
        dt.js("window.__sgKoren = document.querySelector('.sg-hlaseni')")
        nalez = dt.js(_MERENI) or {}
        dt.js("window.__sgKoren = null")
        for druh, popis in _DRUHY.items():
            for polozka in nalez.get(druh) or ():
                kde_nalez = nalezy.setdefault((jmeno, "light", popis, polozka), {"obrazovky": [], "sirky": []})
                if "formulář hlášení" not in kde_nalez["obrazovky"]:
                    kde_nalez["obrazovky"].append("formulář hlášení")
                if str(SIRKY[1][1]) not in kde_nalez["sirky"]:
                    kde_nalez["sirky"].append(str(SIRKY[1][1]))
        dt.js(_HLASENI_ZAVRI)
        return []
    return []

_UKAZ = r"""
((id) => {
  if (typeof window.ukaz === 'function') { try { window.ukaz(id); return true; } catch (e) {} }
  document.querySelectorAll('.obrazovka').forEach((o) => {
    o.hidden = o.id !== id; o.classList.toggle('aktivni', o.id === id);
  });
  return true;
})(%s)
"""


def _spust_prohlizec(exe: str, profil: Path, log) -> tuple[subprocess.Popen, _DevTools]:
    """Start the browser and open our own tab over the browser-level socket.

    Not /json/list + the default tab: on a GitHub runner Chrome came up,
    wrote its port, and still listed no page within 30 s — the first CI run
    of this check failed exactly so. Target.createTarget does not wait for
    anything Chrome decides on its own."""
    argv = [exe, "--headless=new", "--remote-debugging-port=0", f"--user-data-dir={profil}",
            "--no-first-run", "--no-default-browser-check", "--disable-extensions",
            "--disable-gpu", "--hide-scrollbars", "--mute-audio", "--disable-sync",
            "--disable-background-networking", "--disable-component-update",
            "--force-color-profile=srgb", "--font-render-hinting=none",
            "--host-resolver-rules=MAP * ~NOTFOUND , EXCLUDE 127.0.0.1",
            "about:blank"]
    if sys.platform.startswith("linux"):
        # GitHub runners and containers lack the user namespaces Chrome's
        # sandbox wants; the page is our own, served from 127.0.0.1.
        argv.insert(1, "--no-sandbox")
    # __COMPAT_LAYER is a Windows compatibility shim some launchers pass down
    # (seen: DetectorsAppHealth). Under it Edge 155 hands the window to the
    # user's running Edge and exits 0 — no DevToolsActivePort, no check.
    prostredi = {k: v for k, v in os.environ.items() if k.upper() != "__COMPAT_LAYER"}
    proces = subprocess.Popen(argv, stdout=subprocess.DEVNULL, stderr=log, env=prostredi)
    soubor = profil / "DevToolsActivePort"
    konec = time.monotonic() + 60
    while True:
        radky = (soubor.read_text(encoding="utf-8", errors="replace").split()
                 if soubor.exists() else [])
        if len(radky) >= 2:
            break
        if proces.poll() is not None or time.monotonic() > konec:
            raise RuntimeError("prohlížeč se nespustil (DevToolsActivePort nevznikl)")
        time.sleep(0.1)
    dt = _DevTools(_WebSocket(f"ws://127.0.0.1:{int(radky[0])}{radky[1]}", timeout=60))
    cil = dt.volej("Target.createTarget", url="about:blank")["targetId"]
    dt.session = dt.volej("Target.attachToTarget", targetId=cil, flatten=True)["sessionId"]
    return proces, dt


def _velikost(dt: _DevTools, sirka: int, vyska: int) -> None:
    dt.volej("Emulation.setDeviceMetricsOverride", width=sirka, height=vyska,
             deviceScaleFactor=1, mobile=False)
    time.sleep(0.15)


def zkontroluj(root: Path | None = None, *, snimky: Path | None = None,
               povinne: bool = False) -> tuple[list[str], list[dict], str]:
    """Returns (problems, screenshots, note). Problems are Czech sentences for
    the builder; screenshots are {soubor, popis} for the reviewer; the note
    says which browser ran, or why nothing did."""
    root = Path(root or Path(__file__).resolve().parent)
    web = root / "web"
    stranky = sorted(p for p in web.glob("*.html") if p.name not in PRESKOCIT) if web.is_dir() else []
    if not stranky:
        return [], [], "žádná obrazovka ke kontrole"
    exe = najdi_prohlizec()
    if exe is None:
        if povinne:
            return ["vizuální kontrola: na stroji není Chrome, Chromium ani Edge"], [], ""
        return [], [], "prohlížeč nenalezen — vizuální kontrola přeskočena"

    problemy: list[str] = []
    # (page, scheme, kind, item) -> where it was seen. A shared footer is
    # one problem, not fourteen — the first real product printed it per screen.
    nalezy: dict[tuple, dict[str, list[str]]] = {}
    obrazovek_na_strance: dict[str, int] = {}
    snimky_out: list[dict] = []
    if snimky is not None:
        snimky.mkdir(parents=True, exist_ok=True)
    server = _server(web)
    profil = Path(tempfile.mkdtemp(prefix="simtegen-prohlizec-"))
    proces = None
    dt = None
    fd, log_jmeno = tempfile.mkstemp(prefix="simtegen-prohlizec-", suffix=".log")
    log_cesta = Path(log_jmeno)
    log = os.fdopen(fd, "wb")  # the one handle — a second open() leaked mkstemp's
    try:
        proces, dt = _spust_prohlizec(exe, profil, log)
        dt.volej("Page.enable")
        dt.volej("Page.addScriptToEvaluateOnNewDocument", source=_HLIDAC_UVODNI)
        port = server.server_address[1]
        for stranka in stranky:
            for schema in ("light", "dark"):
                # Reduced motion: the screen fade-in must not be photographed
                # half-way (it once made a finished screen look washed out).
                dt.volej("Emulation.setEmulatedMedia", features=[
                    {"name": "prefers-color-scheme", "value": schema},
                    {"name": "prefers-reduced-motion", "value": "reduce"}])
                _velikost(dt, SIRKY[1][1], SIRKY[1][2])
                dt.volej("Page.navigate", url=f"http://127.0.0.1:{port}/{stranka.name}")
                if not dt.cekej_na("Page.loadEventFired", 20):
                    problemy.append(f"web/{stranka.name}: stránka se nenačetla do 20 s")
                    break
                if schema == "light":
                    videla = bool(dt.js("window.__sgStart && window.__sgStart.videna"))
                    konec = time.monotonic() + 4
                    while dt.js(_UVODNI) == "videt" and time.monotonic() < konec:
                        time.sleep(0.1)
                    if not videla:
                        problemy.append(f"web/{stranka.name}: úvodní obrazovka se značkou SimteGen se "
                                        "neukázala (načítá se simtegen.js jako první v <body>?)")
                    elif dt.js(_UVODNI) == "videt":
                        problemy.append(f"web/{stranka.name}: úvodní obrazovka nezmizela ani po 4 s")
                else:
                    time.sleep(1.0)
                time.sleep(0.4)  # the app's first /api/ answer (401) settles
                obrazovky = dt.js(_OBRAZOVKY) or [None]
                obrazovek_na_strance[stranka.name] = len(obrazovky)
                bez_hlaseni: list[str] = []
                fotografovano = 0
                for obrazovka in obrazovky:
                    if obrazovka:
                        dt.js(_UKAZ % json.dumps(obrazovka))
                    kde = f"web/{stranka.name}" + (f" #{obrazovka}" if obrazovka else "")
                    # The loading skeleton is a state worth checking, not worth
                    # a reviewer's picture; the first screens get all widths.
                    fotit_obrazovku = schema == "light" and "nacitani" not in (obrazovka or "")
                    siroce = fotografovano < SIROCE_OBRAZOVEK
                    if fotit_obrazovku:
                        fotografovano += 1
                    # Dark mode changes colours, not layout: contrast only.
                    sirky = SIRKY if schema == "light" else (SIRKY[1],)
                    for nazev, sirka, vyska, fotit in sirky:
                        _velikost(dt, sirka, vyska)
                        nalez = dt.js(_MERENI) or {}
                        if schema == "light" and nazev == "telefon" and not dt.js(_HLASENI_VIDET):
                            bez_hlaseni.append(obrazovka or stranka.name)
                        for druh, popis in _DRUHY.items():
                            if schema == "dark" and druh != "kontrast":
                                continue
                            for polozka in nalez.get(druh) or ():
                                kde_nalez = nalezy.setdefault((stranka.name, schema, popis, polozka),
                                                              {"obrazovky": [], "sirky": []})
                                for pole, hodnota in (("obrazovky", obrazovka), ("sirky", str(sirka))):
                                    if hodnota not in kde_nalez[pole]:
                                        kde_nalez[pole].append(hodnota)
                        if (snimky is not None and fotit and fotit_obrazovku and len(snimky_out) < MAX_SNIMKU
                                and (siroce or nazev == "telefon")):
                            vyska_stranky = dt.js("document.documentElement.scrollHeight") or vyska
                            data = dt.volej("Page.captureScreenshot", format="jpeg", quality=72,
                                            captureBeyondViewport=True,
                                            clip={"x": 0, "y": 0, "width": sirka,
                                                  "height": min(int(vyska_stranky), vyska * 2),
                                                  "scale": 1})["data"]
                            jmeno = f"{stranka.stem}-{obrazovka or 'stranka'}-{nazev}.jpg"
                            (snimky / jmeno).write_bytes(base64.b64decode(data))
                            snimky_out.append({"soubor": str(snimky / jmeno),
                                               "popis": f"{kde}, {nazev} {sirka}×{vyska} px"})
                if schema == "light":
                    if bez_hlaseni:
                        problemy.append(f"web/{stranka.name}: na obrazovce {', '.join('#' + o for o in bez_hlaseni)} "
                                        "není na telefonu vidět „Nahlásit chybu“ — hlášení musí jít z každé obrazovky.")
                    problemy.extend(_zkus_hlaseni(dt, stranka.name, obrazovky, nalezy))
                    zablokovano = dt.js("window.__sgCsp || []") or []
                    if zablokovano:
                        problemy.append(f"web/{stranka.name}: Content-Security-Policy zablokovala "
                                        + "; ".join(zablokovano[:5]) + " — v produkci by to nefungovalo "
                                        "(nebo stránka volá cizí server).")
        radky: dict[tuple, list[str]] = {}
        for (jmeno, schema, popis, polozka), kde_nalez in nalezy.items():
            klic = (jmeno, schema, popis, tuple(kde_nalez["obrazovky"]), tuple(kde_nalez["sirky"]))
            radky.setdefault(klic, []).append(polozka)
        for (jmeno, schema, popis, obrazovky_nalezu, sirky_nalezu), polozky in radky.items():
            rezim = ", tmavý režim" if schema == "dark" else ""
            if obrazovky_nalezu == (None,):
                kde = f"web/{jmeno}"
            elif len(obrazovky_nalezu) > 1 and len(obrazovky_nalezu) == obrazovek_na_strance.get(jmeno):
                kde = f"web/{jmeno} (všechny obrazovky)"
            else:
                kde = f"web/{jmeno} " + ", ".join(o if o.startswith("formulář") else f"#{o}"
                                                  for o in obrazovky_nalezu)
            problemy.append(f"{kde} ({'/'.join(sirky_nalezu)} px{rezim}): {popis} — "
                            + "; ".join(polozky))
        poznamka = f"prohlížeč: {Path(exe).name}"
    except (OSError, RuntimeError, ConnectionError, ValueError) as e:
        # A browser that will not start is the machine's problem, not the
        # product's — unless the caller (CI) said the check is mandatory.
        # Chrome's own last words go with it: without them the first CI
        # failure said only "neotevřel stránku".
        log.flush()
        try:
            vystup = log_cesta.read_text(encoding="utf-8", errors="replace").strip()[-400:]
        except OSError:
            vystup = ""
        duvod = f"{e}" + (f" (prohlížeč: {vystup})" if vystup else "")
        if povinne:
            problemy.append(f"vizuální kontrola se nepovedla: {duvod}")
        poznamka = f"vizuální kontrola se nepovedla: {duvod}"
    finally:
        if dt is not None:
            try:
                dt.volej("Browser.close")
            except Exception:
                pass
            dt.ws.zavri()
        if proces is not None:
            try:
                proces.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proces.kill()
                proces.wait()
        server.shutdown()
        server.server_close()
        log.close()
        # Edge's helper processes inherit the stderr handle and may outlive
        # the browser by a moment; Windows will not delete an open file.
        for _ in range(10):
            try:
                log_cesta.unlink()
                break
            except FileNotFoundError:
                break
            except OSError:
                time.sleep(0.3)
        for _ in range(5):
            shutil.rmtree(profil, ignore_errors=True)
            if not profil.exists():
                break
            time.sleep(0.3)
    return problemy, snimky_out, poznamka


# ── Google Play assets (the release workflow runs this) ───────────────
#
# Play wants phone screenshots and a 1024×500 feature graphic for every
# listing. Drawing them by hand per product is exactly the repeated manual
# step the firm exists to remove, and the product can render itself: the
# same server and browser as the check, a phone at 1080×1920, each screen,
# and a graphic composed from the design system (paper, product colour,
# name, the SimteGen mark). JPEG, because Play refuses PNG with alpha.

MAX_SNIMKU_OBCHODU = 8

_GRAFIKA = """<!doctype html><html lang="cs"><head><meta charset="utf-8">
<link rel="stylesheet" href="/styl.css"><link rel="stylesheet" href="/produkt.css">
<style>
  body {{ margin: 0; width: 1024px; height: 500px; overflow: hidden; }}
  .g {{ box-sizing: border-box; height: 500px; padding: 64px 72px; display: flex; flex-direction: column;
        justify-content: space-between; }}
  .g h1 {{ font-size: 76px; line-height: 1; margin: 0; display: flex; align-items: center; gap: 28px; }}
  .g h1::before {{ content: ""; width: 44px; height: 44px; background: var(--barva-produktu); flex: none; }}
  .g p {{ font-size: 30px; max-width: 760px; margin: 22px 0 0; }}
  .g .pata {{ display: flex; align-items: center; gap: 14px; border-top: 1px solid var(--barva-linka); padding-top: 22px; }}
</style></head><body><div class="g">
  <div><h1></h1><p></p></div>
  <div class="pata"><span class="znacka-ctverec"></span><span class="znacka-slovo">simtegen</span></div>
</div></body></html>"""


def obchod(root: Path, vystup: Path) -> list[str]:
    """Phone screenshots and the feature graphic into `vystup`; returns the
    file names. Raises on a browser that will not start — the release
    workflow then fails loudly instead of uploading an empty listing."""
    root = Path(root)
    zaznam = {}
    if (root / "play" / "zaznam.json").exists():
        zaznam = json.loads((root / "play" / "zaznam.json").read_text(encoding="utf-8"))
    vystup.mkdir(parents=True, exist_ok=True)
    exe = najdi_prohlizec()
    if exe is None:
        raise RuntimeError("na stroji není Chrome, Chromium ani Edge")
    server = _server(root / "web")
    profil = Path(tempfile.mkdtemp(prefix="simtegen-prohlizec-"))
    fd, log_jmeno = tempfile.mkstemp(prefix="simtegen-prohlizec-", suffix=".log")
    log = os.fdopen(fd, "wb")
    proces, dt = None, None
    soubory: list[str] = []
    try:
        proces, dt = _spust_prohlizec(exe, profil, log)
        dt.volej("Page.enable")
        dt.volej("Emulation.setEmulatedMedia", features=[
            {"name": "prefers-color-scheme", "value": "light"},
            {"name": "prefers-reduced-motion", "value": "reduce"}])
        dt.volej("Emulation.setDeviceMetricsOverride", width=360, height=640, deviceScaleFactor=3, mobile=True)
        port = server.server_address[1]
        dt.volej("Page.navigate", url=f"http://127.0.0.1:{port}/index.html")
        dt.cekej_na("Page.loadEventFired", 20)
        konec = time.monotonic() + 5
        while dt.js(_UVODNI) == "videt" and time.monotonic() < konec:
            time.sleep(0.1)
        time.sleep(0.5)
        obrazovky = [o for o in (dt.js(_OBRAZOVKY) or [None]) if "nacitani" not in (o or "")]
        for poradi, obrazovka in enumerate(obrazovky[:MAX_SNIMKU_OBCHODU], 1):
            if obrazovka:
                dt.js(_UKAZ % json.dumps(obrazovka))
            dt.js("window.scrollTo(0, 0)")
            time.sleep(0.3)
            data = dt.volej("Page.captureScreenshot", format="jpeg", quality=90)["data"]
            jmeno = f"telefon-{poradi}.jpg"
            (vystup / jmeno).write_bytes(base64.b64decode(data))
            soubory.append(jmeno)
        dt.volej("Emulation.setDeviceMetricsOverride", width=1024, height=500, deviceScaleFactor=1, mobile=False)
        dt.js("document.open(); document.write(%s); document.close();" % json.dumps(_GRAFIKA.format()))
        dt.js("document.querySelector('.g h1').textContent = %s; document.querySelector('.g p').textContent = %s;"
              % (json.dumps(zaznam.get("nazev") or ""), json.dumps(zaznam.get("kratky_popis") or "")))
        dt.js("document.fonts.ready.then(() => true)")
        time.sleep(0.5)
        data = dt.volej("Page.captureScreenshot", format="jpeg", quality=92,
                        clip={"x": 0, "y": 0, "width": 1024, "height": 500, "scale": 1})["data"]
        (vystup / "grafika.jpg").write_bytes(base64.b64decode(data))
        soubory.append("grafika.jpg")
        ikona = root / "web" / "ikona-512.png"
        if ikona.exists():
            shutil.copy(ikona, vystup / "ikona.png")
            soubory.append("ikona.png")
    finally:
        if dt is not None:
            try:
                dt.session = None
                dt.volej("Browser.close")
            except Exception:
                pass
            dt.ws.zavri()
        if proces is not None:
            try:
                proces.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proces.kill()
                proces.wait()
        server.shutdown()
        server.server_close()
        log.close()
        # Edge lets go of its profile a moment after it exits (same as in
        # zkontroluj): one rmtree left folders behind in the temp dir.
        for _ in range(10):
            shutil.rmtree(profil, ignore_errors=True)
            try:
                os.unlink(log_jmeno)
            except FileNotFoundError:
                pass
            except OSError:
                pass
            if not profil.exists() and not Path(log_jmeno).exists():
                break
            time.sleep(0.3)
    return soubory


def main() -> int:
    args = sys.argv[1:]
    snimky = Path(args[args.index("--snimky") + 1]) if "--snimky" in args else None
    root = Path(args[args.index("--koren") + 1]) if "--koren" in args else None
    if "--obchod" in args:
        soubory = obchod(root or Path(__file__).resolve().parent, Path(args[args.index("--obchod") + 1]))
        print("Podklady pro Google Play:", ", ".join(soubory))
        return 0
    povinne = "--povinne" in args or os.environ.get("GITHUB_ACTIONS") == "true"
    problemy, fotky, poznamka = zkontroluj(root, snimky=snimky, povinne=povinne)
    if "--json" in args:
        print(json.dumps({"problemy": problemy, "snimky": fotky, "poznamka": poznamka},
                         ensure_ascii=False))
    else:
        for p in problemy:
            print(" -", p)
        print(poznamka or "Vizuální kontrola prošla.")
    return 1 if problemy else 0


if __name__ == "__main__":
    sys.exit(main())
