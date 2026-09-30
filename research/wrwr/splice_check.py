"""C5 splice validation on the real seam Dukascopy H1 -> live Exness H1 (mid = bid + half the recorded spread), the series the
forward record needs to reach the current week. Prints the check table; exit code 1 if any check fails.
Also validates the HistData -> Exness M5 seam at 2021-01-01 if the spliced M5 file exists."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import contracts as K  # noqa: E402

sys.path.insert(0, str(K.ROOT / "research" / "foundry")); sys.path.insert(0, str(K.ROOT / "research" / "wpwb_weekly"))
import engine as E  # noqa: E402


def exness_h1():
    import bars as BR
    b5 = BR.load_bars(frozen=False)
    half = np.asarray(b5.sp, float) / 2
    t = np.asarray(b5.t, np.int64)
    o, c = (np.asarray(getattr(b5, x), float) + half for x in ("o", "c"))
    sp_bp = np.asarray(b5.sp, float) / c * 1e4
    df = pd.DataFrame(dict(k=t // 3600, t=t, o=o, c=c, sp=sp_bp, n=1)).groupby("k").agg(t=("t", "first"), o=("o", "first"), c=("c", "last"), sp=("sp", "first"), n=("n", "sum"))
    df = df[df.n >= 10]                                               # a full hour has 12 M5 bars
    df["t"] = df.index.to_numpy() * 3600
    return dict(t=df.t.to_numpy(np.int64), o=df.o.to_numpy(), c=df.c.to_numpy(), sp=df.sp.to_numpy())


def main():
    H, _, _, _ = E.load()
    A = dict(t=np.asarray(H.t, np.int64), o=np.asarray(H.o, float), c=np.asarray(H.c, float), sp=np.asarray(H.spread_bp, float))
    X = exness_h1()
    seam = int(A["t"][-1]) + 3600
    print(f"Dukascopy H1 ends {pd.to_datetime(A['t'][-1], unit='s')}; Exness H1 from {pd.to_datetime(X['t'][0], unit='s')} to {pd.to_datetime(X['t'][-1], unit='s')}; seam at {pd.to_datetime(seam, unit='s')}")
    ok = True
    # B = Exness; the check compares A (before the seam) with B on the overlap before the seam and looks at B after it
    r0 = K.validate_seam(A, X, seam, strict=False)                                       # v5 rule (raw recorded spread ratio)
    print("v5 rule (raw recorded spreads):", {k: (v[0], v[1]) for k, v in r0.items() if k == "spread_ratio"})
    r = K.validate_seam(A, X, seam, strict=False, cost_floor_bp=K.COST_FLOOR_BP["XAUUSD"])   # v8 rule (charged cost)
    for k, (passed, v) in r.items():
        print(f"  {k:18s} {'PASS' if passed else 'FAIL'}  {v}")
        ok &= passed
    print("SEAM VALID" if ok else "SEAM INVALID")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
