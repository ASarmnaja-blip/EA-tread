"""Descriptive: do trades of the frozen panel candidates that START within 2 h after a scheduled HIGH
USD release (or in the hour before one) do worse than the rest? 2022-2026, after cost and swap."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parents[1] / "research" / "pilot")]
import engine as E  # noqa: E402
import forward_panel as FP  # noqa: E402
import calendar_feed as C  # noqa: E402

H, D, cuts, cell = E.load()
names = [c["name"] for f in ("forward_panel1.json", "forward_panel2.json", "forward_panel3.json")
         for c in json.loads((FP.SHADOW / f).read_text())["candidates"]]
T = FP.trades(H, D, cell, [s for s in FP.universe(H, D) if s.name in names])
cal = C.load_calendar(str(E.ROOT / "data" / "calendar.csv"))
ev = np.sort(cal[(cal.currency == "USD") & (cal.importance == "HIGH")].epoch.unique().astype(np.int64))
T = T[T.et >= ev.min()]
j = np.searchsorted(ev, T.et.to_numpy(), side="right") - 1
since = np.where(j >= 0, T.et.to_numpy() - ev[np.maximum(j, 0)], 10 ** 9)
k = np.searchsorted(ev, T.et.to_numpy(), side="left")
until = np.where(k < len(ev), ev[np.minimum(k, len(ev) - 1)] - T.et.to_numpy(), 10 ** 9)
T["zone"] = np.where(since <= 2 * 3600, "0-2h after release", np.where(until <= 3600, "<=1h before release", "away from releases"))
pd.set_option("display.width", 200)
g = T.groupby(["name", "zone"]).R.agg(["count", "mean"]).round(3).unstack("zone")
print(g.to_string())
print("\nall panel candidates pooled:")
print(T.groupby("zone").R.agg(["count", "mean"]).round(3).to_string())
