"""Ověření pokynu — první krok workflow Faktura, Platba, Predplatne, Upominka
faktury, Domena, Play odpoved a Vydani (u Vydani v každém jobu).

Token bota smí spouštět workflow (firma fakturuje sama), takže kdo by ho
ukradl, mohl by spustit Platbu nebo Predplatne a dát komukoli zaplacené
měsíce. Proto běh projde, jen když:

- nese platný a čerstvý podpis SimteGenu (vstup `podpis`, klíč jen na
  mini PC; veřejná polovina v org proměnné SIMTEGEN_PODPIS), nebo
- ho ručně spustil člověk ze seznamu v org proměnné SIMTEGEN_SPRAVCI
  (loginy oddělené čárkou).

Bez org proměnné SIMTEGEN_PODPIS projde jen správce: podpis nejde ověřit,
a co nejde ověřit, neprojde. Proměnnou může změnit jen správce organizace.

Vstupy se čtou ze souboru události ($GITHUB_EVENT_PATH), ne z prostředí
kroku: prostředí kroku GitHub vypisuje do veřejného logu dřív, než by je
cokoli stihlo zamaskovat. Volný text a osobní údaje se tu hned maskují —
maska platí pro všechny další kroky jobu. Ostatní nástroje čtou citlivé
vstupy stejnou cestou (vstup()).

Podpis: RSASSA-PKCS1-v1_5 se SHA-256 nad textem
  <název workflow>\\n@repo=<vlastník/repo>\\n<klíč=hodnota pro každý neprázdný
  vstup kromě podpis, seřazeně>\\ncas=<unix>
— stejný text skládá podpis_pokynu.zprava() v SimteGenu. Repozitář je
v podpisu, aby podpis viditelný v jednom repu neplatil v jiném.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import sys
import time

PLATNOST_S = 3 * 3600
DIGEST_INFO = bytes.fromhex("3031300d060960864801650304020105000420")
# Until this moment (2026-12-10 00:00 UTC) a signature without the repository
# line still passes outside production, with a warning: the template and the
# signing service are updated separately, and invoices must not stop in
# between. After it, only signatures bound to the repository count.
PRECHOD_DO = 1796860800
# Free text and personal data among the inputs of the signed workflows.
CITLIVE = ("email", "poznamka", "dodavatel", "popis", "text", "predplatne", "podpis")


def _text(hodnota) -> str:
    if hodnota is None:
        return ""
    if isinstance(hodnota, bool):
        # The event file may keep a boolean input as JSON true/false; the
        # inputs context and every shell see "true"/"false".
        return "true" if hodnota else "false"
    return str(hodnota)


def maskuj(hodnota: str) -> None:
    """::add-mask:: works line by line; an empty line would mask nothing."""
    for radek in str(hodnota).splitlines():
        if radek.strip():
            print(f"::add-mask::{radek}", flush=True)


def vstupy_udalosti() -> dict[str, str] | None:
    """The dispatch inputs from the event file; None outside Actions (no
    file), {} for an event without inputs. Sensitive values are masked
    before they are returned."""
    cesta = os.environ.get("GITHUB_EVENT_PATH")
    if not cesta:
        return None
    try:
        with open(cesta, encoding="utf-8") as f:
            udalost = json.load(f)
    except (OSError, ValueError):
        return None
    surove = udalost.get("inputs") if isinstance(udalost, dict) else None
    vstupy = {str(k): _text(v) for k, v in surove.items()} if isinstance(surove, dict) else {}
    for jmeno in CITLIVE:
        if vstupy.get(jmeno):
            maskuj(vstupy[jmeno])
    return vstupy


def vstup(jmeno: str) -> str:
    """One input for a tool: from the event file in Actions, else from the
    environment variable of the same name in capitals (local runs, tests)."""
    vstupy = vstupy_udalosti()
    if vstupy is not None and jmeno in vstupy:
        return vstupy[jmeno]
    return os.environ.get(jmeno.upper(), "")


def zprava(workflow: str, vstupy: dict, cas: int, repo: str | None) -> bytes:
    """The signed text. repo=None builds the older text without the
    repository line (accepted only during the transition)."""
    # Empty inputs never count: SimteGen signs without them (podpis_pokynu.zprava).
    radky = ([workflow] + ([f"@repo={repo.strip().lower()}"] if repo is not None else [])
             + [f"{x}={vstupy[x]}" for x in sorted(vstupy) if x != "podpis" and vstupy[x] != ""]
             + [f"cas={cas}"])
    return "\n".join(radky).encode("utf-8")


def over(klic_json: str, workflow: str, vstupy: dict, podpis: str, ted: int, *, repo: str = "",
         prechod: bool = False) -> str | None:
    """None když podpis sedí, jinak důvod odmítnutí. prechod=True přijme
    i starší podpis bez repozitáře (jen do PRECHOD_DO)."""
    try:
        cas_text, _, sig_b64 = podpis.partition(".")
        cas = int(cas_text)
        sig = base64.b64decode(sig_b64, validate=True)
        klic = json.loads(klic_json)
        n, e = int(klic["n"], 16), int(klic["e"])
    except (ValueError, KeyError, TypeError):
        return "podpis nebo klíč nemá správný tvar"
    if abs(ted - cas) > PLATNOST_S:
        return "podpis je starší než 3 hodiny"
    if any("\n" in str(v) or "\r" in str(v) for v in vstupy.values()):
        # The signed text is one input per line: a value with a line break
        # could make one signature cover an input that was never signed.
        return "vstup obsahuje zalomení řádku"
    if not repo.strip():
        return "nevím, ve kterém repozitáři běh běží (GITHUB_REPOSITORY)"
    k = (n.bit_length() + 7) // 8
    if len(sig) != k:
        return "podpis nemá délku klíče"
    vyjde = pow(int.from_bytes(sig, "big"), e, n).to_bytes(k, "big")

    def sedi(data: bytes) -> bool:
        t = DIGEST_INFO + hashlib.sha256(data).digest()
        return vyjde == b"\x00\x01" + b"\xff" * (k - len(t) - 3) + b"\x00" + t

    if sedi(zprava(workflow, vstupy, cas, repo)):
        return None
    if prechod and ted < PRECHOD_DO and sedi(zprava(workflow, vstupy, cas, None)):
        return None
    return "podpis nesedí (jiný klíč, jiný repozitář, nebo se vstupy změnily)"


def main() -> int:
    env = os.environ
    vstupy = vstupy_udalosti()
    klic = (env.get("PODPIS_KLIC") or "").strip()
    akter = env.get("AKTER", "")
    spravci = {s.strip().lower() for s in (env.get("SPRAVCI") or "").split(",") if s.strip()}
    if vstupy is None:
        print("::error::Chybí soubor události (GITHUB_EVENT_PATH) — vstupy nejde ověřit. Odmítnuto.")
        return 1
    if akter.lower() in spravci:
        print(f"Běh spustil správce {akter} — bez podpisu je v pořádku.")
        return 0
    if not klic:
        print("::error::Podpis pokynů není zapnutý (org proměnná SIMTEGEN_PODPIS, python main.py "
              "--podpis-klic na mini PC) — bez něj projde jen správce. Odmítnuto.")
        return 1
    podpis = vstupy.get("podpis", "")
    if not podpis:
        print(f"::error::Běh spustil {akter or 'neznámý'} bez podpisu SimteGenu a není ve SIMTEGEN_SPRAVCI — odmítnuto.")
        return 1
    repo, workflow, ted = env.get("GITHUB_REPOSITORY", ""), env.get("WORKFLOW", ""), int(time.time())
    duvod = over(klic, workflow, vstupy, podpis, ted, repo=repo)
    if duvod and env.get("PRISNE") != "1" \
            and over(klic, workflow, vstupy, podpis, ted, repo=repo, prechod=True) is None:
        # The production job (PRISNE) never takes the older form.
        print("::warning::Podpis SimteGenu je ve starším tvaru bez repozitáře — platí jen do 10. 12. 2026. "
              "Aktualizuj SimteGen na mini PC.")
        return 0
    if duvod:
        print(f"::error::Pokyn odmítnut: {duvod}.")
        return 1
    print("Podpis SimteGenu sedí.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
