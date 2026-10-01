"""Evidence for the W1 switch (K1 in docs/plans/BACKUP_SWITCH_PREREG.md): every setup-1 trade 2009-2026 tagged with the W1 (and D1) state at
its signal bar; results by state, market and period, and how often the W1 state flips."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent / "grid768")]
import complement as CP  # noqa: E402
import g27k as K  # noqa: E402
import g768 as G  # noqa: E402
import stress_top3 as S  # noqa: E402


def main():
    K.START = CP.FIRST
    ext = K.externals(); rows = []; flips = {}
    for m in K.MKTS:
        h1 = S.spliced_h1(m); M = K.prepare(m, h1, ext); F = G.frames(h1); X = G.features(F, m, "H4"); X["sec"] = 14400; CP.extras(m, h1, X, M)
        w1 = K.anchor(X, F["W1"], 14400, 7 * 86400); d1 = M["d1"]
        d = K.directions(M, "C8", "D3", "E1", "J1"); s = np.flatnonzero(d)
        for tr in CP.sim(X, m, s, d[s], 2.0, "ch20"):
            sb = tr["e"] - 1
            rows.append(dict(mkt=m, t=pd.Timestamp(tr["t"], unit="s"), R=tr["R"], w1="up" if w1[sb] > 0 else "down", d1="up" if d1[sb] > 0 else "down"))
        wk = pd.Series(w1, index=pd.to_datetime(X["t"], unit="s"))[pd.Timestamp(CP.FIRST, unit="s"):]
        flips[m] = (int((np.diff(np.sign(wk.to_numpy())) != 0).sum()), (wk.index[-1] - wk.index[0]).days / 365.25, float((wk > 0).mean()))
    D = pd.DataFrame(rows); D["period"] = np.where(D.t < "2021-10-01", "2009-2021 (not used to choose setup 1)", "2021-10..2026-09")
    pf = lambda x: x[x > 0].sum() / -x[x <= 0].sum() if (x <= 0).any() else np.inf
    agg = lambda g: pd.Series(dict(n=len(g), avgR=g.R.mean(), totR=g.R.sum(), win=(g.R > 0).mean(), pf=pf(g.R)))
    print("by W1 state at entry:\n", D.groupby("w1").apply(agg).round(3).to_string())
    print("\nby period and W1:\n", D.groupby(["period", "w1"]).apply(agg).round(3).to_string())
    print("\nby market and W1:\n", D.groupby(["mkt", "w1"]).apply(agg).round(3).to_string())
    print("\nby W1 and D1:\n", D.groupby(["w1", "d1"]).apply(agg).round(3).to_string())
    yr = D.assign(y=D.t.dt.year).groupby(["y", "w1"]).R.sum().unstack().fillna(0).round(1)
    print("\nR per year by W1 state:\n", yr.to_string())
    print("\nyears where W1-down trades lost:", int((yr.get("down", 0) < 0).sum()), "of", int((yr.get("down", 0) != 0).sum()), "years with W1-down trades")
    for m, (n, yrs, up) in flips.items():
        print(f"{m}: W1 state flips {n} times in {yrs:.1f} years ({n / yrs:.1f} per year), W1 up {up:.0%} of the time")
    D.to_csv(K.OUT / "w1_evidence.csv", index=False)


if __name__ == "__main__":
    main()
