"""User's point: don't test a setup against one arbitrary window - find ALL
historical periods whose regime characteristics MATCH the current one, pool
them, and measure against that pooled "similar regime" sample. This directly
fixes Part 20's small-n weakness (one 2-month window, n=82-88) by combining
every historically comparable stretch instead.

Current regime (from regime_stability_score.py, 2026-09-28 04:00 UTC, fresh
MT5 pull): ATR percentile ~64 (moderately elevated, not extreme), efficiency
ratio ~0.009-0.034 across 14-180d windows (choppy, not trending), regime
label TREND_DOWN but only 22% stable (unreliable label).

This script computes the SAME two numbers (ATR percentile via a 100-bar
lookback on M15, and efficiency ratio over a rolling 20-trading-day window)
across the ENTIRE canonical M5 history, then flags every week whose reading
falls within a band around today's: efficiency ratio <= 0.05 (choppy, not
trending) AND ATR percentile in [40, 85] (moderate-to-elevated vol, not
dead-quiet and not extreme-vol). Read-only, no MT5 connection needed (uses
the frozen canonical snapshot for full-history reproducibility).
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import core as C5
import historical_regime_walkforward as hist
import mtf_engine as E

ATR_LOOKBACK = 100          # bars, matches regime_stability_score.py's M15 lookback
EFF_WINDOW_DAYS = 20        # ~20 trading days, matches Amendment 28's regime window
EFF_MAX = 0.05              # choppy: today's readings were 0.009-0.034
ATR_PCTL_LO, ATR_PCTL_HI = 40.0, 85.0   # band around today's ATR percentile of ~64


def efficiency_ratio(c: np.ndarray) -> float:
    net = abs(c[-1] - c[0])
    path = np.abs(np.diff(c)).sum()
    return net / path if path > 0 else np.nan


def main() -> int:
    b5 = hist.load_history()
    t = pd.to_datetime(b5.t, unit="s", utc=True)

    b15, _ = E.resample(b5, 3)
    atr15 = C5.atr(b15, 14)
    t15 = pd.to_datetime(b15.t, unit="s", utc=True)

    n15 = len(b15)
    atr_pctl = np.full(n15, np.nan)
    for i in range(ATR_LOOKBACK, n15):
        window = atr15[i - ATR_LOOKBACK:i]
        atr_pctl[i] = 100.0 * np.sum(window < atr15[i]) / ATR_LOOKBACK

    # weekly cadence over M5 bars, using trailing EFF_WINDOW_DAYS for efficiency
    day_ns = 86400
    week_starts = pd.date_range(t[0].floor("D"), t[-1].floor("D"), freq="7D")
    rows = []
    for ws in week_starts:
        idx5 = int(np.searchsorted(t.values, ws.to_datetime64()))
        if idx5 <= 0 or idx5 >= len(b5):
            continue
        eff_start = int(np.searchsorted(t.values, ws.to_datetime64() - np.timedelta64(EFF_WINDOW_DAYS, "D")))
        if eff_start >= idx5:
            continue
        eff = efficiency_ratio(b5.c[eff_start:idx5])
        idx15 = int(np.searchsorted(t15.values, ws.to_datetime64())) - 1
        if idx15 < ATR_LOOKBACK or idx15 >= n15:
            continue
        pctl = atr_pctl[idx15]
        rows.append(dict(week_start=ws, m5_idx=idx5, efficiency=eff, atr_pctl=pctl))

    df = pd.DataFrame(rows)
    similar = df[(df.efficiency <= EFF_MAX) &
                (df.atr_pctl >= ATR_PCTL_LO) & (df.atr_pctl <= ATR_PCTL_HI)]

    print(f"total weeks scanned: {len(df)}")
    print(f"criteria: efficiency <= {EFF_MAX}, ATR percentile in [{ATR_PCTL_LO}, {ATR_PCTL_HI}]")
    print(f"matching 'similar regime' weeks: {len(similar)} "
          f"({100*len(similar)/len(df):.1f}% of history)\n")

    similar_years = similar.week_start.dt.year.value_counts().sort_index()
    print("matching weeks by year (checking these are NOT just 2024-2026 again):")
    for y, c in similar_years.items():
        print(f"  {y}: {c}")

    out_path = Path("data/similar_regime_weeks.csv")
    similar[["week_start", "m5_idx", "efficiency", "atr_pctl"]].to_csv(out_path, index=False)
    print(f"\nwrote {out_path} ({len(similar)} matching week-start indices)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
