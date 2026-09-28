"""Build and cache the 38-tool weekly outcome matrix (does NOT run selector P).

Output: data/wpwb_procedure_matrix.npz with cuts, R10, R15, NTR, VALID and
the menu names, plus input hashes. Run from the repo root.
"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
for p in ("research/wpwb_procedure", "research/wpwb_live", "research/wpwb_search"):
    sys.path.insert(0, str(ROOT / p))
import common as C  # noqa: E402
import menu as M  # noqa: E402
from run_live_hod import combined_bars  # noqa: E402

OUT = ROOT / "data" / "wpwb_procedure_matrix.npz"
LAST_CUT = int(np.datetime64("2026-09-18T22:15:00").astype("datetime64[s]").astype(np.int64))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main() -> int:
    import os
    os.chdir(ROOT)
    b5 = combined_bars()
    m = C.Market(b5)
    last = int(m.t[-1]) + C.HOUR
    cuts = np.array([c for c in m.cuts if c + C.WEEK <= last and c <= LAST_CUT], np.int64)
    assert cuts[-1] == LAST_CUT, "last outcome cut must be 2026-09-18 22:15 UTC"
    man = M.manifest()
    V = M.validity(m, cuts, man)
    R, NTR, INNER = M.build_matrix(m, cuts, (1.0, 1.5), man)
    np.savez_compressed(OUT, cuts=cuts, R10=R[1.0], R15=R[1.5], NTR=NTR, INNER=INNER, VALID=V,
                        names=np.array([x[2] for x in man]),
                        lookback=np.array([x[4] for x in man]),
                        sha_canonical=sha("data/canonical_XAUUSD_M5.npz"),
                        sha_fresh=sha("data/fresh/XAUUSD_M5.npz"))
    print(f"saved {OUT.name}: {R[1.0].shape}, cuts {len(cuts)}; "
          f"trade-weeks {int((NTR > 0).sum())}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
