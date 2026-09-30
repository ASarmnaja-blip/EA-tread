"""One-time: the historical weekly-R expectation of every frozen forward candidate (mean and sd of weekly
R over 2021-01..2026-08, weeks without trades = 0), written to data/foundry/shadow/expectations.json
for the Auditor drift check in the weekly summary. Descriptive only."""
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
C = []
for f in sorted(FP.SHADOW.glob("forward_panel*.json")):
    C += json.loads(f.read_text())["candidates"]
T = FP.trades(H, D, cell, [s for s in FP.universe(H, D) if s.name in {c["name"] for c in C}])
start = int(np.datetime64("2021-01-01T22:15:00", "s").astype(np.int64))
weeks = np.arange(start - (start - E.FIRST_CUT) % E.WEEK, int(H.t[-1]) - E.WEEK, E.WEEK)
out = {}
for c in C:
    g = T[(T.name == c["name"]) & E.cell_mask(T.cell.to_numpy(), c["cell"])]
    k = np.searchsorted(weeks, g.et.to_numpy(), side="left") - 1
    ok = k >= 0
    w = pd.Series(g.R.to_numpy()[ok]).groupby(k[ok]).mean().reindex(range(len(weeks))).fillna(0).clip(lower=-2)
    out[c["name"]] = dict(mean=float(w.mean()), sd=float(w.std()), weeks=len(w), trade_weeks=int((w != 0).sum()))
(FP.SHADOW / "expectations.json").write_text(json.dumps(out, indent=1))
print(json.dumps(out, indent=1))
