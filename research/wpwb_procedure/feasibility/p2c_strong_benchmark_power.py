"""P2-C power against stronger, free benchmarks (last-week RV, EWMA 0.75),
reusing Codex's round-4 functions unchanged. Data through the P1 cut only.
Development evidence; nothing here is confirmation."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "codex_checks"))
import p2c_forecast_power as F  # noqa: E402


def main() -> int:
    os.chdir(F.ROOT)
    with np.load(F.ROOT / "data/wpwb_procedure_matrix.npz") as z:
        cuts = z["cuts"].copy()
    m = F.C.Market(F.combined_bars())
    rv, _, _ = F.weekly_rv(m, cuts, int(cuts[-1]))
    cand, bench26, _, ix = F.expanding_har(rv)
    ewma = np.full(len(rv), np.nan); ewma[0] = rv[0]
    for t in range(1, len(rv)):
        ewma[t] = 0.75 * ewma[t - 1] + 0.25 * rv[t - 1]
    lc = F.qlike(rv[ix], cand[ix])
    rng = np.random.default_rng(F.SEED)
    print("benchmark      cap   mean_x   power100%_26w/52w   power50%_26w/52w")
    for label, b in (("26w-mean", bench26[ix]), ("last-week", rv[ix - 1]), ("EWMA-.75", ewma[ix])):
        diff = F.qlike(rv[ix], b) - lc
        for cap in F.DIFF_CAPS:
            x = np.clip(diff, -cap, cap) / cap
            p1 = [F.power(x, 1.0, h, rng) for h in (26, 52)]
            p5 = [F.power(x, 0.5, h, rng) for h in (26, 52)]
            print(f"{label:12s} {cap:5.2f}  {x.mean():+.4f}   {p1[0]:.3f}/{p1[1]:.3f}          {p5[0]:.3f}/{p5[1]:.3f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
