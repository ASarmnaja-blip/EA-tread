"""Descriptive (seen data): weekly R of the six frozen panel candidates 2021-2026, their correlation, and
an equal-risk portfolio (mean of the six weekly R; weeks without a trade count 0)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import engine as E  # noqa: E402
import forward_panel as FP  # noqa: E402

H, D, cuts, cell = E.load()
C = json.loads((FP.SHADOW / "forward_panel.json").read_text())["candidates"] + json.loads((FP.SHADOW / "forward_panel2.json").read_text())["candidates"]
T = FP.trades(H, D, cell, [s for s in FP.universe(H, D) if s.name in {c["name"] for c in C}])
start = int(np.datetime64("2021-01-01T22:15:00", "s").astype(np.int64))
weeks = np.arange(start - (start - E.FIRST_CUT) % E.WEEK, int(H.t[-1]) - E.WEEK, E.WEEK)
W = pd.DataFrame(index=pd.to_datetime(weeks, unit="s"))
for c in C:
    g = T[(T.name == c["name"]) & E.cell_mask(T.cell.to_numpy(), c["cell"])]
    k = np.searchsorted(weeks, g.et.to_numpy(), side="left") - 1
    ok = k >= 0
    W[c["name"]] = pd.Series(g.R.to_numpy()[ok]).groupby(k[ok]).mean().reindex(range(len(weeks))).fillna(0).to_numpy()
pd.set_option("display.width", 220)
print("weekly R correlation 2021-26:"); print(W.corr().round(2).to_string())
P = W.mean(axis=1)
for nm, x in list(W.items()) + [("PORTFOLIO", P)]:
    sr = x.mean() / x.std() * np.sqrt(52) if x.std() > 0 else np.nan
    print(f"{nm:24s} mean week R {x.mean():+.4f}  sd {x.std():.3f}  annual Sharpe {sr:+.2f}  weeks {len(x)}")
sr = P.mean() / P.std()
print(f"\nportfolio: weeks to t = 2.9 at this weekly Sharpe ~ {(2.9 / sr) ** 2:.0f}")
