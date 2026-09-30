"""Diagnostic (no gate, no alpha): variants whose GROSS R (before cost and swap) and whose excess over
a time-free random-entry control are positive in all three eras 2015-20, 2021-23, 2024-26."""
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
cbH = np.where(H.week >= 0, cell[np.clip(H.week, 0, len(cell) - 1)], "")
cbD = np.where(D.week >= 0, cell[np.clip(D.week, 0, len(cell) - 1)], "")
eras = {"15-20": ("2015", "2021"), "21-23": ("2021", "2024"), "24-26": ("2024", "2027")}
rng = np.random.default_rng(11)
rows = []
for s in FP.universe(H, D):
    B, cb = (H, cbH) if s.tf == "H1" else (D, cbD)
    g, ex = E.simulate(B, s.ent, s.dirs, s.stop, s.tgt, s.last, s.eprice)
    a = B.atr[s.ent]
    ctrl = E.matched_control(B, cb, s.ent, s.dirs, s.stop / a, s.tgt / a, s.last - s.ent, rng, key="none")
    sw = E.swap_bp(B, s.ent, ex, s.dirs)
    ep = s.eprice if s.eprice is not None else B.o[s.ent]
    sb = s.stop / ep * 1e4
    d = pd.to_datetime(B.t[s.ent], unit="s")
    r = dict(name=s.name)
    ok = True
    for k, (a0, a1) in eras.items():
        m = (d >= a0) & (d < a1)
        if m.sum() < 30:
            ok = False; break
        r[f"gross_{k}"] = (g[m] / sb[m]).mean()
        r[f"exc_{k}"] = np.nanmean((g[m] - sw[m] - ctrl[m]) / sb[m])
        r[f"net_{k}"] = ((g[m] - sw[m] - E.COST_BP) / sb[m]).mean()
    if ok:
        rows.append(r)
R = pd.DataFrame(rows)
g_all = (R[[c for c in R if c.startswith("gross_")]] > 0).all(1)
e_all = (R[[c for c in R if c.startswith("exc_")]] > 0).all(1)
n_all = (R[[c for c in R if c.startswith("net_")]] > 0).all(1)
print(f"{len(R)} variants; gross > 0 in all 3 eras: {g_all.sum()}; excess > 0 in all 3: {e_all.sum()}; "
      f"net > 0 in all 3: {n_all.sum()}; gross AND excess all 3: {(g_all & e_all).sum()}")
print(f"(if each era were a coin flip: expected ~{len(R) / 8:.0f})")
pd.set_option("display.width", 220)
print(R[g_all & e_all].round(3).to_string(index=False))
