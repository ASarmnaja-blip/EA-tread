"""WPWB current-era backtest in money terms: weekly/monthly P&L, equity,
drawdown, and attribution of every week to what the market did.

Tools (all frozen, weekly rebuild every Friday 22:15 UTC, trade Sunday open ->
Friday close, Demo90 base costs incl. long swap):
  LONG    - hold 1 oz long all week (the baseline: gold's own trend)
  VOLMAN  - same, size s = min(2, median52(sigma)/sigma_now), hl=13
  TSM26   - long or short the week by the sign of the 26-week trend
$ are per 0.01 lot base (1 oz, $1 per $1 of gold price); VOLMAN scales it.
Account view: $1,000 start, fixed base size, no compounding.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
os.chdir(ROOT)
sys.path.insert(0, str(ROOT / "research" / "wpwb_search"))
sys.path.insert(0, str(ROOT / "research" / "wpwb_live"))
import common as C  # noqa: E402
from approaches import tsm_tool  # noqa: E402
from run_live_hod import combined_bars  # noqa: E402
from run_round3 import sigma_at, volman_size  # noqa: E402

TIER1 = {"Fed Interest Rate Decision": "FOMC", "CPI m/m": "CPI",
         "Nonfarm Payrolls": "NFP", "Core PCE Price Index m/m": "PCE",
         "GDP q/q": "GDP", "Fed Chair Powell Testimony": "Powell-testimony"}


def usd(bp, price):
    return bp / 1e4 * price


def load_events():
    df = pd.read_csv("data/calendar.csv", encoding="latin-1")
    df = df[(df.currency == "USD") & (df.event.isin(TIER1))].copy()
    dt = pd.to_datetime(df.time, format="%Y.%m.%d %H:%M", utc=True)
    df["ts"] = ((dt - pd.Timestamp("1970-01-01", tz="UTC")) // pd.Timedelta(seconds=1)).astype("int64")
    assert df.ts.between(1.5e9, 1.9e9).all(), "event timestamps not in seconds"
    return df


def main() -> int:
    m = C.Market(combined_bars())
    last = int(m.t[-1]) + C.HOUR
    cuts = np.array([c for c in m.cuts if c >= C.DEV_END and c + C.WEEK <= last])
    dxy = np.load("data/fresh/DXY_M5.npz")
    ev = load_events()
    sc: dict = {}
    rows = []
    for cut in cuts:
        cut = int(cut)
        lo, hi = m.week_bars(cut)
        if hi <= lo:
            continue
        p0, p1 = m.o[lo], m.c[hi - 1]
        long_bp = float(m.pnl_bp([lo], [hi - 1], [1], 1.0)[0])
        short_bp = float(m.pnl_bp([lo], [hi - 1], [-1], 1.0)[0])
        s = volman_size(m, cut, 13, sc)
        d = tsm_tool(m, cut, 26)
        sig = sigma_at(m, cut, 13)
        a = np.searchsorted(dxy["t"], cut); b = np.searchsorted(dxy["t"], cut + C.WEEK) - 1
        dxy_pct = (dxy["c"][b] / dxy["o"][a] - 1) * 100 if b > a else np.nan
        wk = ev[(ev.ts >= cut) & (ev.ts < cut + C.WEEK)]
        labels = []
        for _, e in wk.iterrows():
            lab = TIER1[e.event]
            try:
                act, fc = float(e.actual), float(e.forecast)
                if lab in ("CPI", "NFP", "PCE", "GDP") and np.isfinite(act) and np.isfinite(fc):
                    lab += "(hot)" if act > fc else "(cool)" if act < fc else "(inline)"
            except (TypeError, ValueError):
                pass
            if lab not in labels:
                labels.append(lab)
        j0 = np.searchsorted(m.b5.t, cut); j1 = np.searchsorted(m.b5.t, cut + C.WEEK)
        cw = m.b5.c[j0:j1]
        path = np.abs(np.diff(cw)).sum()
        eff = float(abs(cw[-1] - cw[0]) / path) if path > 0 else np.nan   # this week only
        rows.append(dict(
            week_start=pd.to_datetime(cut, unit="s").date(), cut=cut,
            gold_open=round(p0, 2), gold_close=round(p1, 2),
            gold_move_usd=round(p1 - p0, 2), gold_move_pct=round((p1 / p0 - 1) * 100, 2),
            week_range_usd=round(float(m.h[lo:hi].max() - m.l[lo:hi].min()), 2),
            sigma_daily_pct_at_rebuild=round(sig * 100, 2), volman_size=round(s, 2),
            tsm26_dir=d, dxy_pct=round(float(dxy_pct), 2), efficiency_week=round(eff, 3),
            events=" ".join(labels),
            LONG_usd=round(usd(long_bp, p0), 2),
            VOLMAN_usd=round(s * usd(long_bp, p0), 2),
            TSM26_usd=round(usd(long_bp if d > 0 else short_bp, p0), 2) if d != 0 else 0.0))
    df = pd.DataFrame(rows)
    for col in ("LONG_usd", "VOLMAN_usd", "TSM26_usd"):
        df[col.replace("_usd", "_equity")] = 1000 + df[col].cumsum()
    df["month"] = pd.to_datetime(df.week_start).dt.to_period("M").astype(str)
    df.to_csv("data/wpwb_backtest_weekly.csv", index=False)

    # ---------------- summary
    print(f"weeks {len(df)}: {df.week_start.iloc[0]} .. {df.week_start.iloc[-1]}; "
          f"gold {df.gold_open.iloc[0]:.0f} -> {df.gold_close.iloc[-1]:.0f} "
          f"({(df.gold_close.iloc[-1] / df.gold_open.iloc[0] - 1) * 100:+.0f}%)\n")
    print(f"{'tool':8s}{'net $':>10s}{'win wks':>9s}{'best wk':>10s}{'worst wk':>10s}"
          f"{'max DD $':>10s}{'DD % of $1k':>12s}{'PF':>7s}")
    for t in ("LONG", "VOLMAN", "TSM26"):
        x = df[f"{t}_usd"]; eq = df[f"{t}_equity"]
        dd = (eq - np.maximum.accumulate(np.r_[1000, eq])[1:]).min()
        pf = x[x > 0].sum() / -x[x < 0].sum()
        print(f"{t:8s}{x.sum():+10.0f}{(x > 0).mean():8.0%}{x.max():+10.0f}{x.min():+10.0f}"
              f"{dd:+10.0f}{dd / 10:+11.0f}%{pf:7.2f}")

    mon = df.groupby("month").agg(gold_move_pct=("gold_move_pct", "sum"),
                                  LONG=("LONG_usd", "sum"), VOLMAN=("VOLMAN_usd", "sum"),
                                  TSM26=("TSM26_usd", "sum"),
                                  sigma=("sigma_daily_pct_at_rebuild", "mean"),
                                  dxy_pct=("dxy_pct", "sum")).round(1)
    mon.to_csv("data/wpwb_backtest_monthly.csv")
    q = pd.to_datetime(df.week_start).dt.to_period("Q").astype(str)
    qt = df.groupby(q).agg(gold_pct=("gold_move_pct", "sum"), LONG=("LONG_usd", "sum"),
                           VOLMAN=("VOLMAN_usd", "sum"), TSM26=("TSM26_usd", "sum"),
                           sigma=("sigma_daily_pct_at_rebuild", "mean"),
                           dxy_pct=("dxy_pct", "sum"), pos_wks=("gold_move_usd",
                                                                lambda x: (x > 0).mean())).round(2)
    print("\nby quarter ($ per 0.01 lot; gold/dxy = summed weekly %, sigma = mean daily % at rebuild):")
    print(qt.to_string())

    # ---------------- attribution
    print("\nwhy - correlations over all weeks:")
    print(f"  LONG $ vs DXY weekly %:        corr {df.LONG_usd.corr(df.dxy_pct):+.2f}")
    print(f"  |gold move| vs rebuild sigma:  corr {df.gold_move_usd.abs().corr(df.sigma_daily_pct_at_rebuild):+.2f}"
          f"  (volatility is forecastable)")
    print(f"  gold move vs rebuild sigma:    corr {df.gold_move_usd.corr(df.sigma_daily_pct_at_rebuild):+.2f}"
          f"  (direction is not)")
    for tag in ("FOMC", "CPI", "NFP", "PCE"):
        k = df.events.str.contains(tag)
        print(f"  weeks with {tag:4s}: n={k.sum():3d} mean |move| ${df.gold_move_usd[k].abs().mean():5.0f} "
              f"vs ${df.gold_move_usd[~k].abs().mean():5.0f} without; mean move ${df.gold_move_usd[k].mean():+5.0f}")
    terc = pd.qcut(df.sigma_daily_pct_at_rebuild, 3, labels=["low vol", "mid vol", "high vol"])
    g = df.groupby(terc, observed=True)
    print("\nby volatility tercile at the rebuild (why VOLMAN beats LONG):")
    for name, x in g:
        print(f"  {name:8s} weeks {len(x):3d}  gold mean {x.gold_move_usd.mean():+6.1f}$/wk  "
              f"worst wk {x.gold_move_usd.min():+6.0f}$  VOLMAN size {x.volman_size.mean():.2f}  "
              f"LONG {x.LONG_usd.sum():+6.0f}$  VOLMAN {x.VOLMAN_usd.sum():+6.0f}$")

    cols = ["week_start", "gold_move_usd", "gold_move_pct", "dxy_pct", "sigma_daily_pct_at_rebuild",
            "volman_size", "events", "LONG_usd", "VOLMAN_usd"]
    print("\n10 best weeks (LONG):")
    print(df.nlargest(10, "LONG_usd")[cols].to_string(index=False))
    print("\n10 worst weeks (LONG):")
    print(df.nsmallest(10, "LONG_usd")[cols].to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
