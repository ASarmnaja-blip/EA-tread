"""Read-only contract audit for the proposed P2-A volatility router."""
from __future__ import annotations

import ast
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
POWER = ROOT / "research" / "wpwb_procedure" / "codex_checks" / "round3_power.py"
MATRIX = ROOT / "data" / "wpwb_procedure_matrix.npz"


def assignments(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    out = {}
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id in {"HIGH", "LOW"}:
                    out[target.id] = ast.literal_eval(node.value)
    return out


def main():
    maps = assignments(POWER)
    z = np.load(MATRIX, allow_pickle=False)
    names = [str(x) for x in z["names"]]
    family = np.array([x.split()[0] for x in names])
    print("FROZEN-IN-SIMULATION FAMILY MAP")
    for state in ("HIGH", "LOW"):
        hit = np.isin(family, sorted(maps[state]))
        print(f"{state}: {sorted(maps[state])}")
        print(f"  variants in matrix={hit.sum()}: {[names[i] for i in np.flatnonzero(hit)]}")
    text = POWER.read_text(encoding="utf-8")
    checks = {
        "state proxy is cross-tool abs(P&L), not XAU H1 RV":
            "proxy_cells = np.where((N > 0) & V, np.abs(A), np.nan)" in text,
        "binary threshold is prior proxy > trailing-52 median":
            "proxy[w - 1] > np.nanmedian(hist)" in text,
        "reported e-process threshold is hard-coded at alpha .025":
            ">= 40" in text,
        "empty routed basket is assigned zero rather than whole/flat by contract":
            "if basket.any() else 0.0" in text,
    }
    print("\nCONTRACT MISMATCH CHECKS")
    for label, found in checks.items():
        print(f"{found!s:5s} {label}")


if __name__ == "__main__":
    main()
