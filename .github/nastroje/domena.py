"""Workflow Domena: a product's subdomain on the company domain.

    python3 .github/nastroje/domena.py nastav

Env: CLOUDFLARE_API_TOKEN, CLOUDFLARE_ACCOUNT_ID (org secrets), PROJEKT
(= Pages project = repo), SUBDOMENA, ZONA, OZNACENI, RUN_URL. Writes
domeny/vysledek.json for SimteGen, whatever happens — a silent failure would
leave SimteGen waiting for an address that never comes.

Order matters: DNS record → custom domain on the Pages project → wait for
it to go active (certificate) → only then redirect <projekt>.pages.dev to
it. Redirecting first would send customers to an address without a
certificate.

The redirect is one account-wide Bulk Redirect list (simtegen_pages_dev)
with one item per product and one rule that applies it. Subdomains of the
source are NOT included: build previews live at <větev>.<projekt>.pages.dev
and must stay where they are.

Stdlib only (urllib): nothing to install, nothing to pin.
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

API = "https://api.cloudflare.com/client/v4"
SEZNAM = "simtegen_pages_dev"
PRAVIDLO = f"http.request.full_uri in ${SEZNAM}"
VYSTUP = Path("domeny")
CEKANI_S = 15 * 60


class Chyba(Exception):
    def __init__(self, duvod: str, text: str):
        super().__init__(text)
        self.duvod = duvod


def _cf(metoda: str, cesta: str, telo=None) -> tuple[int, dict]:
    data = None if telo is None else json.dumps(telo).encode("utf-8")
    pozadavek = urllib.request.Request(API + cesta, data=data, method=metoda, headers={
        "Authorization": f"Bearer {os.environ['CLOUDFLARE_API_TOKEN']}",
        "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(pozadavek, timeout=60) as odpoved:
            return odpoved.status, json.loads(odpoved.read() or b"{}")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read() or b"{}")
        except json.JSONDecodeError:
            return e.code, {}


def _zprava(odpoved: dict) -> str:
    chyby = odpoved.get("errors") or []
    return "; ".join(f"{c.get('code')}: {c.get('message')}" for c in chyby)[:240] or "bez popisu"


def _nutne(kod: int, odpoved: dict, co: str, opravneni: str) -> dict:
    if kod in (401, 403):
        raise Chyba("opravneni", f"{co}: token nemá oprávnění {opravneni} ({_zprava(odpoved)})")
    if not odpoved.get("success"):
        raise Chyba("jine", f"{co}: HTTP {kod} — {_zprava(odpoved)}")
    return odpoved


def zona_id(zona: str) -> str:
    odpoved = _nutne(*_cf("GET", f"/zones?name={zona}"), "zóna", "Zone:Read")
    if not odpoved.get("result"):
        raise Chyba("opravneni", f"zóna {zona}: token ji nevidí (Zone:Read pro {zona}), nebo není v tomhle účtu")
    return odpoved["result"][0]["id"]


def dns(zona: str, fqdn: str, cil: str, projekt: str) -> None:
    z = zona_id(zona)
    zaznamy = _nutne(*_cf("GET", f"/zones/{z}/dns_records?name={fqdn}"), "DNS", "DNS:Read")["result"]
    for r in zaznamy:
        if r.get("type") == "CNAME" and r.get("content", "").rstrip(".") == cil:
            return
        raise Chyba("obsazeno", f"{fqdn} už v DNS je ({r.get('type')} → {r.get('content')}) — nepřepisuju")
    _nutne(*_cf("POST", f"/zones/{z}/dns_records", {
        "type": "CNAME", "name": fqdn, "content": cil, "proxied": True, "ttl": 1,
        "comment": f"SimteGen: {projekt}"}), "DNS záznam", "DNS:Edit")


def pages_domena(ucet: str, projekt: str, fqdn: str) -> None:
    zaklad = f"/accounts/{ucet}/pages/projects/{projekt}/domains"
    kod, odpoved = _cf("GET", f"{zaklad}/{fqdn}")
    if kod in (401, 403):
        _nutne(kod, odpoved, "Pages", "Cloudflare Pages:Edit")
    if not odpoved.get("success"):
        _nutne(*_cf("POST", zaklad, {"name": fqdn}), "doména v Pages", "Cloudflare Pages:Edit")
    konec = time.monotonic() + CEKANI_S
    while True:
        stav = (_cf("GET", f"{zaklad}/{fqdn}")[1].get("result") or {}).get("status")
        if stav == "active":
            return
        if stav in ("error", "blocked", "deactivated"):
            raise Chyba("certifikat", f"Cloudflare vrátil stav domény {stav}")
        if time.monotonic() > konec:
            raise Chyba("certifikat", f"doména se do {CEKANI_S // 60} minut neaktivovala (stav {stav}) — zkusí se znovu")
        time.sleep(15)


def presmerovani(ucet: str, zdroj: str, cil: str) -> str | None:
    """None when <projekt>.pages.dev now redirects, else why not. Never
    raises: the address works without it, so it must not fail the run."""
    try:
        kod, odpoved = _cf("GET", f"/accounts/{ucet}/rules/lists")
        _nutne(kod, odpoved, "seznam přesměrování", "Account Filter Lists:Edit")
        seznam = next((s for s in odpoved["result"] if s.get("name") == SEZNAM), None)
        if seznam is None:
            seznam = _nutne(*_cf("POST", f"/accounts/{ucet}/rules/lists", {
                "name": SEZNAM, "kind": "redirect",
                "description": "SimteGen: <projekt>.pages.dev na podadresy firemní domény"}),
                "seznam přesměrování", "Account Filter Lists:Edit")["result"]
        polozky = _nutne(*_cf("GET", f"/accounts/{ucet}/rules/lists/{seznam['id']}/items"),
                         "položky přesměrování", "Account Filter Lists:Edit")["result"]
        moje = [p for p in polozky if (p.get("redirect") or {}).get("source_url") == zdroj]
        if not any(p["redirect"].get("target_url") == cil for p in moje):
            if moje:
                _cekej(ucet, _nutne(*_cf("DELETE", f"/accounts/{ucet}/rules/lists/{seznam['id']}/items",
                                         {"items": [{"id": p["id"]} for p in moje]}),
                                    "smazání staré položky", "Account Filter Lists:Edit"))
            _cekej(ucet, _nutne(*_cf("POST", f"/accounts/{ucet}/rules/lists/{seznam['id']}/items", [{
                "redirect": {"source_url": zdroj, "target_url": cil, "status_code": 301,
                             "preserve_query_string": True, "subpath_matching": True,
                             "preserve_path_suffix": True, "include_subdomains": False}}]),
                "položka přesměrování", "Account Filter Lists:Edit"))
        pravidlo(ucet)
        return None
    except Chyba as e:
        return str(e)


def _cekej(ucet: str, odpoved: dict) -> None:
    """List edits are asynchronous; the next edit fails while one pends."""
    operace = (odpoved.get("result") or {}).get("operation_id")
    if not operace:
        return
    for _ in range(40):
        stav = (_cf("GET", f"/accounts/{ucet}/rules/lists/bulk_operations/{operace}")[1].get("result") or {})
        if stav.get("status") == "completed":
            return
        if stav.get("status") == "failed":
            raise Chyba("jine", f"úprava seznamu přesměrování selhala: {stav.get('error')}")
        time.sleep(3)
    raise Chyba("jine", "úprava seznamu přesměrování se nedokončila")


def pravidlo(ucet: str) -> None:
    """The one rule that applies the list. Appended, never PUT over the
    entrypoint once it exists — that would wipe redirects the owner made
    by hand."""
    zaklad = f"/accounts/{ucet}/rulesets/phases/http_request_redirect/entrypoint"
    telo = {"action": "redirect", "expression": PRAVIDLO, "enabled": True,
            "description": "SimteGen: pages.dev na podadresy",
            "action_parameters": {"from_list": {"name": SEZNAM, "key": "http.request.full_uri"}}}
    kod, odpoved = _cf("GET", zaklad)
    if kod == 404:
        _nutne(*_cf("PUT", zaklad, {"rules": [telo]}), "pravidlo přesměrování", "Account Rulesets:Edit")
        return
    sada = _nutne(kod, odpoved, "pravidla přesměrování", "Account Rulesets:Edit")["result"]
    if any(r.get("expression") == PRAVIDLO for r in sada.get("rules") or []):
        return
    _nutne(*_cf("POST", f"/accounts/{ucet}/rulesets/{sada['id']}/rules", telo),
           "pravidlo přesměrování", "Account Rulesets:Edit")


def nastav(env=None) -> dict:
    env = env if env is not None else os.environ
    projekt, sub, zona = env["PROJEKT"], env["SUBDOMENA"], env["ZONA"]
    fqdn, cil = f"{sub}.{zona}", f"{projekt}.pages.dev"
    data = {"oznaceni": env.get("OZNACENI", ""), "subdomena": sub, "zona": zona, "stav": "chyba",
            "duvod": None, "chyba": None, "presmerovani": False, "presmerovani_chyba": None,
            "run_url": env.get("RUN_URL", "")}
    try:
        if not env.get("CLOUDFLARE_API_TOKEN") or not env.get("CLOUDFLARE_ACCOUNT_ID"):
            raise Chyba("opravneni", "org secrets CLOUDFLARE_API_TOKEN / CLOUDFLARE_ACCOUNT_ID tu nejsou")
        dns(zona, fqdn, cil, projekt)
        print(f"DNS: {fqdn} → {cil}")
        pages_domena(env["CLOUDFLARE_ACCOUNT_ID"], projekt, fqdn)
        print(f"Pages: {fqdn} aktivní")
        data["stav"] = "aktivni"
        proc = presmerovani(env["CLOUDFLARE_ACCOUNT_ID"], f"{cil}/", f"https://{fqdn}/")
        data["presmerovani"] = proc is None
        data["presmerovani_chyba"] = proc
        print("Přesměrování z pages.dev:", "ano" if proc is None else f"ne — {proc}")
    except Chyba as e:
        data["duvod"], data["chyba"] = e.duvod, str(e)
        print(f"Doména {fqdn}: {e}")
    data["cas"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    VYSTUP.mkdir(exist_ok=True)
    (VYSTUP / "vysledek.json").write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    return data


def main(argv: list[str]) -> int:
    if argv[1:2] == ["nastav"]:
        return 0 if nastav()["stav"] == "aktivni" else 1
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
