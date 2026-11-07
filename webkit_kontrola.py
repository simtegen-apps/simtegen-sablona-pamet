"""Safari na iPhonu (WebKit) — infrastruktura šablony.

NEUPRAVOVAT V PRODUKTU: stavitel tenhle soubor při každé stavbě obnoví ze
šablony, stejně jako kontrola_manifestu.py, která ho volá.

Why: every other check renders the app in Chromium (Edge on the mini PC,
Chrome on the GitHub runner), while a good share of the customers carry an
iPhone, where every browser is WebKit. A script that uses what WebKit does
not have yet, or a layout that only Safari pushes sideways, passed every
check and broke on the phone of the customer who pays. So in CI the pages
are also opened in WebKit as an iPhone: an uncaught script error or
sideways scroll there is a finding like any other.

How, without touching the workflow (SimteGen's token may not, and the
products' deploy.yml would never get the change): Playwright is installed
into a throwaway folder (npm, pinned version) and its WebKit with the
system libraries it needs; web/ is served from 127.0.0.1 with every /api/
answering 401 (vizualni_kontrola._server — the signed-out app, as the
visual check sees it) and every request to another host is aborted:
product JavaScript is model-written and must not phone home from CI.

Only on GitHub Actions (or WEBKIT_KONTROLA=ano for a local try): the mini
PC has no reason to download a browser per build. When the install fails
(npm or the browser download is down) the check says so and passes — a CDN
hiccup must not block every deploy; findings in WebKit block like others.

Run alone:  WEBKIT_KONTROLA=ano python webkit_kontrola.py
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

PLAYWRIGHT = "1.48.2"
ZARIZENI = "iPhone 13"
LIMIT_INSTALACE_S = 600
LIMIT_BEHU_S = 300

_SKRIPT = r"""
const { webkit, devices } = require('playwright');
const cfg = JSON.parse(require('fs').readFileSync(process.argv[2], 'utf8'));
(async () => {
  const browser = await webkit.launch();
  const out = {};
  for (const stranka of cfg.stranky) {
    const ctx = await browser.newContext({ ...devices[cfg.zarizeni] });
    // Our own server only: nothing the product's script asks for elsewhere.
    await ctx.route('**/*', (r) => (r.request().url().startsWith(cfg.zaklad) ? r.continue() : r.abort()));
    const page = await ctx.newPage();
    const chyby = [];
    page.on('pageerror', (e) => chyby.push(String((e && e.message) || e).slice(0, 200)));
    try {
      await page.goto(cfg.zaklad + '/' + stranka, { waitUntil: 'load', timeout: 20000 });
      await page.waitForTimeout(1500);
      const [plna, okno] = await page.evaluate(() => [document.documentElement.scrollWidth,
                                                      document.documentElement.clientWidth]);
      out[stranka] = { chyby, plna, okno };
    } catch (e) {
      out[stranka] = { chyby, nenacteno: String((e && e.message) || e).slice(0, 160) };
    }
    await ctx.close();
  }
  await browser.close();
  process.stdout.write(JSON.stringify(out));
})().catch((e) => { process.stdout.write(JSON.stringify({ __chyba: String((e && e.message) || e).slice(0, 300) })); });
"""


def zapnuto() -> bool:
    return os.environ.get("GITHUB_ACTIONS") == "true" or os.environ.get("WEBKIT_KONTROLA") == "ano"


def stranky(root: Path) -> list[str]:
    import vizualni_kontrola as vk

    return [p.name for p in sorted((root / "web").glob("*.html")) if p.name not in vk.PRESKOCIT]


def vyhodnot(vysledek: dict) -> list[str]:
    """Pure: findings from the WebKit run's JSON."""
    problemy = []
    for stranka, v in sorted(vysledek.items()):
        if stranka.startswith("__") or not isinstance(v, dict):
            continue
        kde = f"web/{stranka} v Safari na iPhonu (WebKit)"
        if v.get("nenacteno"):
            problemy.append(f"{kde}: stránka se nenačetla — {v['nenacteno']}")
        for chyba in dict.fromkeys(v.get("chyby") or []):
            problemy.append(f"{kde}: chyba skriptu — {chyba}")
        if isinstance(v.get("plna"), int) and isinstance(v.get("okno"), int) and v["plna"] > v["okno"] + 1:
            problemy.append(f"{kde}: obsah přetéká do strany (stránka {v['plna']} px, okno {v['okno']} px)")
    return problemy


def _priprav(prac: Path) -> str | None:
    """Playwright and its WebKit in `prac`; None when ready, else why not."""
    npm = shutil.which("npm")
    if npm is None:
        return "na stroji není npm"
    kroky = [[npm, "install", "--prefix", str(prac), f"playwright@{PLAYWRIGHT}", "--no-audit", "--no-fund",
              "--loglevel=error"],
             ["node", str(prac / "node_modules" / "playwright" / "cli.js"), "install",
              *(["--with-deps"] if sys.platform.startswith("linux") else []), "webkit"]]
    for krok in kroky:
        try:
            beh = subprocess.run(krok, cwd=prac, capture_output=True, text=True, encoding="utf-8",
                                 errors="replace", timeout=LIMIT_INSTALACE_S)
        except (OSError, subprocess.TimeoutExpired) as e:
            return f"{Path(krok[0]).name} {krok[1]}: {e}"
        if beh.returncode != 0:
            return f"{Path(krok[0]).name} {krok[1]} skončil {beh.returncode}: {(beh.stderr or beh.stdout).strip()[-200:]}"
    return None


def spust(root: Path, prac: Path) -> dict:
    """The pages of root/web in WebKit as an iPhone: {page: {chyby, plna,
    okno} | {chyby, nenacteno}} or {"__chyba": why} when WebKit did not run."""
    import vizualni_kontrola as vk

    server = vk._server(root / "web")   # serves on its own thread already
    try:
        cfg = prac / "cfg.json"
        cfg.write_text(json.dumps({"zaklad": f"http://127.0.0.1:{server.server_address[1]}",
                                   "stranky": stranky(root), "zarizeni": ZARIZENI}), encoding="utf-8")
        (prac / "safari.js").write_text(_SKRIPT, encoding="utf-8")
        beh = subprocess.run(["node", str(prac / "safari.js"), str(cfg)], cwd=prac, capture_output=True,
                             text=True, encoding="utf-8", errors="replace", timeout=LIMIT_BEHU_S)
        try:
            return json.loads(beh.stdout or "{}")
        except ValueError:
            return {"__chyba": (beh.stderr or beh.stdout).strip()[-300:] or "WebKit nic nevrátil"}
    except subprocess.TimeoutExpired:
        return {"__chyba": f"WebKit nedoběhl do {LIMIT_BEHU_S} s"}
    finally:
        server.shutdown()
        server.server_close()


def zkontroluj(root: Path | None = None) -> tuple[list[str], str]:
    """(problems, note)."""
    root = Path(root or Path(__file__).resolve().parent)
    if not zapnuto():
        return [], "WebKit (Safari) se kontroluje jen v CI"
    if not (root / "web").is_dir() or not stranky(root):
        return [], "žádné stránky k otevření"
    prac = Path(tempfile.mkdtemp(prefix="simtegen-webkit-"))
    try:
        proc = _priprav(prac)
        if proc:
            return [], f"WebKit se nepodařilo připravit ({proc}) — Safari tentokrát neověřeno"
        vysledek = spust(root, prac)
        if "__chyba" in vysledek:
            return [], f"WebKit neběžel ({vysledek['__chyba']}) — Safari tentokrát neověřeno"
        return vyhodnot(vysledek), f"WebKit {PLAYWRIGHT}, {ZARIZENI}, {len(vysledek)} stránek"
    finally:
        shutil.rmtree(prac, ignore_errors=True)


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass
    problemy, poznamka = zkontroluj(Path.cwd())
    for p in problemy:
        print(" -", p)
    print(poznamka)
    return 1 if problemy else 0


if __name__ == "__main__":
    sys.exit(main())
