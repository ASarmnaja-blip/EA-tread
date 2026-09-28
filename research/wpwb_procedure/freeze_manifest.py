"""Print the freeze manifest: sha256 of every code file P depends on, of the
input snapshots and outcome matrix, the frozen constants, and dependency
versions. Paste the output into the prereg at freeze. Does not run P."""
from __future__ import annotations

import hashlib
import platform
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import procedure as P  # noqa: E402

CODE = [
    "research/wpwb_procedure/procedure.py", "research/wpwb_procedure/menu.py",
    "research/wpwb_procedure/build_matrix.py", "research/wpwb_procedure/harness.py",
    "research/wpwb_procedure/test_procedure.py", "research/wpwb_procedure/audit_builder.py",
    "research/wpwb_search/common.py", "research/wpwb_search/approaches.py",
    "research/wpwb_search/approaches2.py", "research/wpwb_search/run_round3.py",
    "research/wpwb_live/run_live_hod.py", "research/pilot/data.py",
    "research/pilot/historical_regime_walkforward.py",
]
DATA = ["data/canonical_XAUUSD_M5.npz", "data/fresh/XAUUSD_M5.npz",
        "data/wpwb_procedure_matrix.npz"]
CONSTS = ["SCALE_W", "SCORE_W", "HALF_LIFE", "MIN_ACTIVE", "SD_FLOOR", "TARGET", "CAP",
          "BLOCK", "BLOCK_SHARE", "EXCESS_FLOOR", "MARGIN_BP", "C_FLOOR", "LAMBDAS",
          "MIN_LOOKBACK_VALID"]


def sha(p):
    return hashlib.sha256((ROOT / p).read_bytes()).hexdigest()


def main() -> int:
    print("| file | sha256 |\n|---|---|")
    for p in CODE + DATA:
        print(f"| `{p}` | `{sha(p)}` |")
    print("\nconstants: " + ", ".join(f"{k}={getattr(P, k)}" for k in CONSTS))
    print(f"python {platform.python_version()}, numpy {np.__version__}, pandas {pd.__version__}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
