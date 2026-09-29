"""Calibrate the block length of Plan B on NULL data only (circular-shifted
features) before any real Plan B result is read. Amendment 1 of
docs/PLAN_B_DAILY_PREREG.md. Read-only."""
from __future__ import annotations
import os, sys
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parent))
import plan_b_daily as PB

CASES = (("ret5", 5), ("ret20", 20), ("dow", 1), ("vol_ratio", 5))
LENGTHS = (10, 20, 40, 60, 90, 120, 180)
SHIFTS = 60


def main():
    os.chdir(PB.ROOT)
    d = PB.daily_from_h1()
    feats, fwd, ok, days, years = PB.make(d)
    n = len(days)
    print(f"{'block days':>10s} " + " ".join(f"{nm}/h{h:<3d}" for nm, h in CASES) + "   worst")
    for L in LENGTHS:
        PB.BLOCK_DAYS = L
        rates = []
        for nm, h in CASES:
            rej = 0
            for _ in range(SHIFTS):
                s = int(PB.RNG.integers(260, n - 260))
                r = PB.run_test(np.roll(feats[nm], s), nm, fwd, ok, years, days, h, reps=300)
                rej += bool(r and r["p"] < 0.05)
            rates.append(rej / SHIFTS)
        print(f"{L:>10d} " + " ".join(f"{x:7.0%}" for x in rates) + f"   {max(rates):.0%}", flush=True)


if __name__ == "__main__":
    main()
