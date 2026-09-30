"""Descriptive surface (no gate, no alpha): fade an H1 bar whose close-to-close move exceeds k ATR,
enter at the next open, hold h hours, stop s ATR, after 2 bp cost and swap, by era."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import engine as E  # noqa: E402
from families import nonoverlap  # noqa: E402

H, D, cuts, cell = E.load()
r1 = np.r_[np.nan, np.diff(H.c)]
eras = {"03-14": ("2003", "2015"), "15-20": ("2015", "2021"), "21-23": ("2021", "2024"), "24-26": ("2024", "2027")}
rows = []
for k in (1.5, 2.0, 2.5, 3.0):
    sig = np.abs(r1) > k * H.atr
    for h in (12, 24, 36, 48, 72):
        for s in (2.0, 3.0, 4.0):
            ent = np.flatnonzero(sig[:-1]) + 1
            last = np.searchsorted(H.t, H.t[ent] + (h - 1) * 3600, side="right") - 1
            keep = nonoverlap(ent, last); ent, last = ent[keep], last[keep]
            d = -np.sign(r1[ent - 1]); a = H.atr[ent]; ok = np.isfinite(a) & (d != 0)
            ent, last, d, a = ent[ok], last[ok], d[ok], a[ok]
            g, ex = E.simulate(H, ent, d, s * a, np.full(len(ent), np.nan), last)
            g = g - E.swap_bp(H, ent, ex, d) - E.COST_BP
            R = g / (s * a / H.o[ent] * 1e4)
            dt = pd.to_datetime(H.t[ent], unit="s")
            row = dict(k=k, h=h, s=s)
            for nm, (a0, a1) in eras.items():
                m = (dt >= a0) & (dt < a1)
                row[f"R_{nm}"] = R[m].mean(); row[f"n_{nm}"] = int(m.sum())
            rows.append(row)
S = pd.DataFrame(rows)
pd.set_option("display.width", 220)
cols = ["k", "h", "s"] + [f"R_{e}" for e in eras] + [f"n_{e}" for e in eras]
print(S[cols].round(3).to_string(index=False))
rec = S[["R_15-20", "R_21-23", "R_24-26"]]
print(f"\nshare of the {len(S)} grid points with net R > 0 in all of 2015-20, 2021-23, 2024-26: "
      f"{(rec > 0).all(1).mean():.0%}; in 2003-14: {(S['R_03-14'] > 0).mean():.0%}")
