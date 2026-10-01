"""Y8 of docs/BUNDLE2_2026-10-01_PREREG.md (corrected implementation: one position per market and system on a time basis, not every
signal stacked). Per clean market, each H1 / H4 / D1 signal is allowed only on the timeframe chosen by the D1 1-year ATR percentile at the
signal (< 0.33 -> D1, 0.33-0.67 -> H4, > 0.67 -> H1); a trade is taken when it enters at or after the exit of the market's last taken
trade of that system. Compared with the fixed-TF versions built the same way. 1 % per trade, 15 markets (USDINR excluded).
Usage: python research/bundle/y8_router.py"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import common as C  # noqa: E402
import y1_htf_system as Y  # noqa: E402


def take_time(g):
    g = g.sort_values(["t", "tf"]); keep = []; busy = -1
    for t, tx in zip(g.t.to_numpy(), g.t_exit.to_numpy()):
        ok = t >= busy; keep.append(ok)
        if ok:
            busy = tx
    return g[np.asarray(keep)]


def main():
    frames = []
    for mkt in [m for m in Y.CLEAN if m != "USDINR"]:
        for tf in ("H1", "H4", "D1"):
            _, T = Y.market_frame(mkt, tf)
            frames.append(T[["t", "t_exit", "R", "d", "s", "ep", "system", "reg_near", "chase", "d1_pct", "mkt", "tf"]])
    A = pd.concat(frames, ignore_index=True)
    A["allow"] = np.where(A.d1_pct < 0.33, "D1", np.where(A.d1_pct <= 0.67, "H4", "H1"))
    rows = []
    for v in ("BASE", "FULL"):
        m = np.ones(len(A), bool) if v == "BASE" else ((A.reg_near == A.d) & ~A.chase).to_numpy()
        for system in C.SYSTEMS:
            S = A[m & (A.system == system).to_numpy()]
            for lab, sub in (("router", S[S.allow == S.tf]), ("fixed D1", S[S.tf == "D1"]), ("fixed H4", S[S.tf == "H4"]), ("fixed H1", S[S.tf == "H1"])):
                tk = pd.concat([take_time(g) for _, g in sub.groupby("mkt")]) if len(sub) else sub
                rows.append(dict(variant=v, system=system, version=lab, R=tk.R.mean() if len(tk) else np.nan, **C.equity(tk, 0.01)))
    D = pd.DataFrame(rows)
    D.to_csv(Y.OUT / "y8_router.csv", index=False)
    pd.set_option("display.width", 200)
    print(D[["variant", "system", "version", "n", "R", "cagr", "dd", "pos_years"]].round(3).to_string(index=False))


if __name__ == "__main__":
    main()
