"""Bezpečnostní brány CI spouštěné z repa šablony — infrastruktura šablony.

NEUPRAVOVAT V PRODUKTU. Job `kontrola` v deploy.yml produktu stáhne repo
ŠABLONY (main), ověří otisky tohoto souboru a kontrol, které volá, proti
seznamu `# OTISK-KONTROLY` v deploy.yml šablony a teprve pak je spustí proti
checkoutu produktu:

    python3 -I kontroly_ze_sablony.py --koren <checkout produktu>

Why from the template and not from the checkout: the product's own copies
of these checks live on the branch they judge, so a branch could swap them
for one that always passes. The copies here come from the template's main,
and they run only when they match the hashes in the template's deploy.yml —
a workflow file, which only a person can change. `-I` keeps the product's
directory, the working directory and PYTHON* variables out of the import
path: every module below comes from this directory.

What runs: bezpecnostni_kontrola (who may call what, SQL with bound values,
customer data filtered by account…) and, in the memory template,
kontrola_migraci (destructive migrations only with the owner's signature).
The product's own kontrola_manifestu.py runs after this, as before.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# -I leaves even the script's own directory off the path (it implies -P):
# the checks are put there by hand, and nothing else is.
sys.path.insert(0, str(Path(__file__).resolve().parent))

import bezpecnostni_kontrola  # noqa: E402

try:
    import kontrola_migraci  # noqa: E402
except ImportError:  # the basic template has no database
    kontrola_migraci = None

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass


def _generovane(koren: Path, manifest: dict) -> set[Path]:
    """The service worker and offline page the app generator owns — the same
    set as vykresli_aplikaci.generovane_soubory, which the product's
    kontrola_manifestu passes; kept here so this runner imports nothing else."""
    if "aplikace" not in manifest:
        return set()
    return {koren / "web" / "sw.js", koren / "web" / "offline.html"}


def zkontroluj(koren: Path) -> tuple[list[str], list[str]]:
    """(chyby, upozornění) for the product checked out at `koren`."""
    koren = Path(koren).resolve()
    cesta = koren / "data-manifest.json"
    try:
        manifest = json.loads(cesta.read_text(encoding="utf-8")) if cesta.exists() else {}
    except ValueError:
        return ["data-manifest.json není platný JSON"], []
    if not isinstance(manifest, dict):
        return ["data-manifest.json nemá tvar objektu"], []
    chyby, upozorneni = bezpecnostni_kontrola.zkontroluj_vse(koren, manifest, _generovane(koren, manifest))
    chyby = [f"bezpečnost: {c}" for c in chyby]
    upozorneni = [f"bezpečnost: {u}" for u in upozorneni]
    if kontrola_migraci is not None:
        m_chyby, m_varovani = kontrola_migraci.zkontroluj(koren)
        chyby += [f"migrace: {c}" for c in m_chyby]
        upozorneni += [f"migrace: {v}" for v in m_varovani]
    return chyby, upozorneni


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Bezpečnostní brány CI ze šablony.")
    parser.add_argument("--koren", required=True, help="checkout produktu")
    args = parser.parse_args(argv)
    chyby, upozorneni = zkontroluj(Path(args.koren))
    for u in upozorneni:
        print("Upozornění:", u)
    for c in chyby:
        print(" -", c)
    print("Kontroly ze šablony prošly." if not chyby else f"Kontroly ze šablony: {len(chyby)} nálezů.")
    return 1 if chyby else 0


if __name__ == "__main__":
    sys.exit(main())
