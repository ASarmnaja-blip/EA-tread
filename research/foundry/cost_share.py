"""Diagnostic (no gate, no alpha): over the last 104 weeks, which variants have positive GROSS R
(before cost and swap) and how much of it cost and swap take."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import engine as E  # noqa: E402
import forward_panel as FP  # noqa: E402

H, D, cuts, cell = E.load()
rows = []
cbH = np.where(H.week >= 0, cell[np.clip(H.week, 0, len(cell) - 1)], "")
lo = int(H.t[-1]) - 104 * E.WEEK
for s in FP.universe(H, D):
    B = H if s.tf == "H1" else D
    g, ex = E.simulate(B, s.ent, s.dirs, s.stop, s.tgt, s.last, s.eprice)
    sw = E.swap_bp(B, s.ent, ex, s.dirs)
    ep = s.eprice if s.eprice is not None else B.o[s.ent]
    sb = s.stop / ep * 1e4
    m = B.t[s.ent] > lo
    if m.sum() < 40:
        continue
    rows.append(dict(name=s.name, n=int(m.sum()), gross_R=(g[m] / sb[m]).mean(), cost_R=(E.COST_BP / sb[m]).mean(),
                     swap_R=(sw[m] / sb[m]).mean(), net_R=((g[m] - sw[m] - E.COST_BP) / sb[m]).mean(),
                     t_gross=E.cluster_t(g[m] / sb[m], B.t[s.ent][m] // E.WEEK), stop_bp=float(np.median(sb[m]))))
R = pd.DataFrame(rows)
pd.set_option("display.width", 200)
print(f"{len(R)} variants with >= 40 trades in the last 104 weeks; gross R > 0: {(R.gross_R > 0).mean():.0%}; net R > 0: {(R.net_R > 0).mean():.0%}")
print("top 20 by gross t (last 104 weeks):")
print(R.sort_values("t_gross", ascending=False).head(20).round(3).to_string(index=False))
print("\nmedian cost share of R:", round(float(R.cost_R.median()), 3), " median swap share:", round(float(R.swap_R.median()), 3))
