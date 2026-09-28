"""Direction-agnostic feasibility input for Codex's P2-B planning DGP.

P2-B assumes a paired-event residual SD of about 60 bp. For a fixed hold of
H hours, the paired difference is (return after the event bar) minus (the
return over the same clock hours one trading day earlier). Its SD is a scale
property of the market, measured here over EVERY H1 bar with a random sign,
so it contains no information about any direction rule. Gross (before cost).
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
for p in ("research/wpwb_live", "research/wpwb_search"):
    sys.path.insert(0, str(ROOT / p))
import common as C  # noqa: E402
from run_live_hod import combined_bars  # noqa: E402


def main() -> int:
    import os
    os.chdir(ROOT)
    m = C.Market(combined_bars())
    rng = np.random.default_rng(1)
    t_end = int(m.t[-1])
    print("hold_h  window     n_pairs  SD_pair_bp  SD_single_bp")
    for weeks in (52, 26):
        lo = int(np.searchsorted(m.t, t_end - weeks * C.WEEK))
        for H in (1, 4, 12):
            idx = np.arange(lo, len(m.t) - H)
            k = idx + H - 1
            ok = (m.t[k] - m.t[idx]) == (H - 1) * C.HOUR          # contiguous hold
            r = np.full(len(m.t), np.nan)
            r[idx[ok]] = (m.c[k[ok]] - m.o[idx[ok]]) / m.o[idx[ok]] * 1e4
            pos = {int(t): i for i, t in enumerate(m.t)}
            ctrl = np.array([pos.get(int(m.t[i]) - 86400, -1) for i in idx])
            good = ok & (ctrl >= 0)
            a = r[idx[good]]; b = r[ctrl[good]]
            f = np.isfinite(a) & np.isfinite(b)
            s = rng.choice((-1.0, 1.0), f.sum())
            pair = s * (a[f] - b[f])
            print(f"{H:6d}  last {weeks:3d}w  {f.sum():7d}  {pair.std():10.1f}  {a[f].std():12.1f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
