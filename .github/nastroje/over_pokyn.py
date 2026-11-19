"""Ověření pokynu — první krok workflow Faktura, Platba, Predplatne, Upominka
faktury, Domena, Play odpoved a Vydani (u Vydani v obou jobech).

Token bota smí spouštět workflow (firma fakturuje sama), takže kdo by ho
ukradl, mohl by spustit Platbu nebo Predplatne a dát komukoli zaplacené
měsíce. Proto běh projde, jen když:

- nese platný a čerstvý podpis SimteGenu (vstup `podpis`, klíč jen na
  mini PC; veřejná polovina v org proměnné SIMTEGEN_PODPIS), nebo
- ho ručně spustil člověk ze seznamu v org proměnné SIMTEGEN_SPRAVCI
  (loginy oddělené čárkou).

Dokud SIMTEGEN_PODPIS není nastavená, jen varuje (přechod). Proměnnou může
změnit jen správce organizace — token bota na ni nedosáhne.

Podpis: RSASSA-PKCS1-v1_5 se SHA-256 nad textem
  <název workflow>\\n<klíč=hodnota pro každý neprázdný vstup kromě podpis, seřazeně>\\ncas=<unix>
— stejný text skládá podpis_pokynu.zprava() v SimteGenu.
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


def over(klic_json: str, workflow: str, vstupy: dict, podpis: str, ted: int) -> str | None:
    """None když podpis sedí, jinak důvod odmítnutí."""
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
    k = (n.bit_length() + 7) // 8
    if len(sig) != k:
        return "podpis nemá délku klíče"
    # Empty inputs never count: GitHub leaves an input dispatched as "" out
    # of toJSON(inputs), and SimteGen signs without them (podpis_pokynu.zprava).
    radky = ([workflow] + [f"{x}={vstupy[x]}" for x in sorted(vstupy) if x != "podpis" and vstupy[x] != ""]
             + [f"cas={cas}"])
    t = DIGEST_INFO + hashlib.sha256("\n".join(radky).encode("utf-8")).digest()
    ocekavam = b"\x00\x01" + b"\xff" * (k - len(t) - 3) + b"\x00" + t
    if pow(int.from_bytes(sig, "big"), e, n).to_bytes(k, "big") != ocekavam:
        return "podpis nesedí (jiný klíč, nebo se vstupy změnily)"
    return None


def main() -> int:
    env = os.environ
    klic = (env.get("PODPIS_KLIC") or "").strip()
    akter = env.get("AKTER", "")
    spravci = {s.strip().lower() for s in (env.get("SPRAVCI") or "").split(",") if s.strip()}
    vstupy = {k: "" if v is None else str(v) for k, v in json.loads(env.get("VSTUPY") or "{}").items()}

    if not klic:
        if env.get("PRISNE") == "1":
            # The production job: the transition "no key yet → let it pass"
            # must never apply where the production key waits.
            print("::error::Podpis pokynů není zapnutý (org proměnná SIMTEGEN_PODPIS) — do produkce nic.")
            return 1
        print("::warning::Podpis pokynů není zapnutý — nastav org proměnnou SIMTEGEN_PODPIS "
              "(python main.py --podpis-klic na mini PC). Běh pouštím.")
        return 0
    if akter.lower() in spravci:
        print(f"Běh spustil správce {akter} — bez podpisu je v pořádku.")
        return 0
    podpis = vstupy.get("podpis", "")
    if not podpis:
        print(f"::error::Běh spustil {akter or 'neznámý'} bez podpisu SimteGenu a není ve SIMTEGEN_SPRAVCI — odmítnuto.")
        return 1
    duvod = over(klic, env.get("WORKFLOW", ""), vstupy, podpis, int(time.time()))
    if duvod:
        print(f"::error::Pokyn odmítnut: {duvod}.")
        return 1
    print("Podpis SimteGenu sedí.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
