"""Descriptive (seen data, no gate): long-only fade of sharp H1 DROPS (> k ATR), hold 72 h, stop 3 ATR,
by the WPWB 13-week trend state of the week (UP / FLAT / DOWN) and era; also the up-spike fade (short)."""
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
eras = {"03-08": ("2003", "2009"), "09-14": ("2009", "2015"), "15-20": ("2015", "2021"), "21-26": ("2021", "2027")}
for k in (2.0, 2.5, 3.0):
    s = F.shock_fade_clock(H, k=k)
    g, ex = E.simulate(H, s.ent, s.dirs, s.stop, s.tgt, s.last)
    g = g - E.swap_bp(H, s.ent, ex, s.dirs) - E.COST_BP
    R = g / (s.stop / H.o[s.ent] * 1e4)
    cb = np.where(H.week[s.ent] >= 0, cell[np.clip(H.week[s.ent], 0, len(cell) - 1)], "")
    trend = np.array([c.split("/")[1] if c else "" for c in cb])
    d = pd.to_datetime(H.t[s.ent], unit="s")
    era = pd.cut(d.year, [2002, 2008, 2014, 2020, 2027], labels=list(eras))
    df = pd.DataFrame(dict(R=R, side=np.where(s.dirs > 0, "BUY_DIP", "SELL_SPIKE"), trend=trend, era=era))
    df = df[df.trend != ""]
    t = df.pivot_table(index=["side", "trend"], columns="era", values="R", aggfunc="mean", observed=False).round(3)
    n = df.pivot_table(index=["side", "trend"], columns="era", values="R", aggfunc="size", observed=False)
    print(f"k = {k}: mean net R (hold 72 h, stop 3 ATR)"); print(t.to_string()); print("counts"); print(n.to_string(), "\n")
