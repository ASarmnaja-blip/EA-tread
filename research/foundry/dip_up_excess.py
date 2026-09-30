"""Descriptive (seen data): BUY_DIP in UP-trend weeks vs random LONG entries in the same UP weeks
(same year, same hold rule and stop in ATR units, swap and cost on both), per era, with t."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import engine as E  # noqa: E402
import families as F  # noqa: E402

H, D, cuts, cell = E.load()
cbH = np.where(H.week >= 0, cell[np.clip(H.week, 0, len(cell) - 1)], "")
trendH = np.array([c.split("/")[1] if c else "" for c in cbH])
rng = np.random.default_rng(2026)
for k in (2.0, 2.5, 3.0):
    s = F.shock_fade_clock(H, k=k)
    m = (s.dirs > 0) & (trendH[s.ent] == "UP")
    ent, last, stop = s.ent[m], s.last[m], s.stop[m]
    g, ex = E.simulate(H, ent, np.ones(len(ent)), stop, np.full(len(ent), np.nan), last)
    g = g - E.swap_bp(H, ent, ex, np.ones(len(ent))) - E.COST_BP
    sb = stop / H.o[ent] * 1e4
    R = g / sb
    # control: random long entries in UP-trend bars of the same year, same clock hold (71 h) and 3 ATR stop
    pool = pd.Series(np.flatnonzero((trendH == "UP") & np.isfinite(H.atr))).groupby(H.year[(trendH == "UP") & np.isfinite(H.atr)]).apply(np.array)
    Rc = []
    for _ in range(20):
        ce = np.array([rng.choice(pool[y]) for y in H.year[ent]])
        lc = np.searchsorted(H.t, H.t[ce] + 71 * 3600, side="right") - 1
        gc, exc = E.simulate(H, ce, np.ones(len(ce)), 3 * H.atr[ce], np.full(len(ce), np.nan), lc)
        gc = gc - E.swap_bp(H, ce, exc, np.ones(len(ce))) - E.COST_BP
        Rc.append(gc / (3 * H.atr[ce] / H.o[ce] * 1e4))
    Rc = np.nanmean(np.vstack(Rc), axis=0)
    d = pd.to_datetime(H.t[ent], unit="s")
    wk = H.t[ent] // E.WEEK
    rows = []
    for nm, (a, b) in {"03-08": ("2003", "2009"), "09-14": ("2009", "2015"), "15-20": ("2015", "2021"), "21-26": ("2021", "2027"), "ALL": ("2003", "2027")}.items():
        mm = (d >= a) & (d < b)
        rows.append(dict(era=nm, n=int(mm.sum()), R=R[mm].mean(), t_R=E.cluster_t(R[mm], wk[mm]), random_long_R=Rc[mm].mean(),
                         excess=(R - Rc)[mm].mean(), t_excess=E.cluster_t((R - Rc)[mm], wk[mm])))
    print(f"k = {k}: BUY_DIP in UP weeks (hold 72 h, stop 3 ATR, after cost and swap)")
    print(pd.DataFrame(rows).round(3).to_string(index=False), "\n")
