"""Descriptive (seen data, no gate): SHOCK_FADE_k2.5_h72_s3 trades 2022-2026 split by whether the shock
bar contained a HIGH-importance USD release (MT5 calendar) and by the WPWB volatility class."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parents[1] / "research" / "pilot")]
import engine as E  # noqa: E402
import families as F  # noqa: E402
import calendar_feed  # noqa: E402

H, D, cuts, cell = E.load()
s = F.shock_fade_clock(H)
g, ex = E.simulate(H, s.ent, s.dirs, s.stop, s.tgt, s.last)
g = g - E.swap_bp(H, s.ent, ex, s.dirs) - E.COST_BP
R = g / (s.stop / H.o[s.ent] * 1e4)
cal = calendar_feed.load_calendar(str(E.ROOT / "data" / "calendar.csv"))
hi = cal[(cal.currency == "USD") & (cal.importance.astype(str).str.upper().str.contains("HIGH") | (cal.importance.astype(str) == "3"))]
ev = np.sort(hi.epoch.unique().astype(np.int64))
t_shock = H.t[s.ent - 1]
j = np.searchsorted(ev, t_shock, side="left")
news = (j < len(ev)) & (ev[np.minimum(j, len(ev) - 1)] < t_shock + 3600)
vol = np.array([c.split("/")[0] if c else "" for c in np.where(H.week[s.ent] >= 0, cell[np.clip(H.week[s.ent], 0, len(cell) - 1)], "")])
d = pd.to_datetime(H.t[s.ent], unit="s")
m = (d >= "2022-01-10") & (d < "2026-09-01")
df = pd.DataFrame(dict(R=R[m], news=news[m], vol=vol[m], year=d.year[m], dir=np.where(s.dirs[m] > 0, "fade-down(long)", "fade-up(short)")))
print(f"importance values in calendar: {sorted(cal.importance.astype(str).unique())[:6]}; HIGH USD events {len(ev)}")
for col in ("news", "vol", "dir", "year"):
    print(df.groupby(col).R.agg(["count", "mean"]).round(3).T.to_string(), "\n")
