"""HOD_21L with an era-appropriate long swap. Swap per night (bp of price) = (US 2y yield + markup) /
365, markup calibrated so that today's value equals the measured Exness swap ($0.5493/oz/night at
the current price); Wednesday counts 3 nights. 2015 (before the Treasury file) uses the 2016-01
yield. Gate re-applied on swap-adjusted R. Read-only."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path[:0] = [str(HERE), str(ROOT / "research" / "pilot")]
import engine as E  # noqa: E402
import families as F  # noqa: E402
import external_traces as X  # noqa: E402

SWAP_USD, PRICE_NOW = 0.5493, 4154.5


def main():
    nom = X.treasury("nominal")
    y2 = nom["BC_2YEAR"].dropna()
    y_now = float(y2.iloc[-1])
    swap_now_ann = SWAP_USD / PRICE_NOW * 365 * 100           # % per year
    markup = swap_now_ann - y_now
    print(f"current 2y {y_now:.2f} %, measured swap {swap_now_ann:.2f} %/yr -> markup {markup:.2f} %")
    H, D, cuts, cell = E.load()
    cb = np.where(H.week >= 0, cell[np.clip(H.week, 0, len(cell) - 1)], "")
    sp = [s for s in F.hod(H) if s.name == "HOD_21L"][0]
    g, ex = E.simulate(H, sp.ent, sp.dirs, sp.stop, sp.tgt, sp.last)
    vol = np.array([c.split("/")[0] if c else "" for c in cb[sp.ent]])
    mk = np.isin(vol, ["NORMAL", "HIGH"])
    d = pd.to_datetime(H.t[sp.ent], unit="s")
    yv = y2.reindex(pd.DatetimeIndex(d.normalize()), method="ffill").to_numpy()
    yv = np.where(np.isfinite(yv), yv, float(y2.iloc[0]))
    nights = np.where(H.dow[sp.ent] == 2, 3, 1)
    swap_bp = np.maximum(yv + markup, 0) / 100 / 365 * nights * 1e4
    sbp = sp.stop / H.o[sp.ent] * 1e4
    rows = []
    for per, (a, b, alpha) in {"DISC 2015-20": ("2015", "2021", None), "VAL 2021-23": ("2021", "2024", 0.05),
                               "HOLD 2024-26": ("2024", "2027", 0.003125)}.items():
        m = mk & (d >= a) & (d < b)
        net = g[m] - E.COST_BP - swap_bp[m]
        stress = g[m] - E.STRESS_BP - swap_bp[m]
        R = net / sbp[m]
        t = E.cluster_t(R, H.t[sp.ent][m] // E.WEEK)
        p = E.one_sided_p(t)
        rows.append(dict(period=per, n=int(m.sum()), swap_bp=swap_bp[m].mean(), net_bp=net.mean(), stress_bp=stress.mean(),
                         net_R=R.mean(), t_R=t, p=p, alpha=alpha, passes=None if alpha is None else bool(p < alpha and net.mean() > 0 and stress.mean() > 0)))
    pd.set_option("display.width", 200)
    print(pd.DataFrame(rows).round(4).to_string(index=False))


if __name__ == "__main__":
    main()
