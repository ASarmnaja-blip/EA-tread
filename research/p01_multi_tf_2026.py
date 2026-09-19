#!/usr/bin/env python3
"""P01's real 2026 trades, across H4/H1/M15/M1, in money.

WHAT THIS IS

  The same fixed engine as p01_trade_log.py (see the retraction in
  test_spec_engine_calibration.py and change_ledger.json for why "fixed"
  matters here), run on real Dukascopy bid/ask, restricted to signals whose
  SIGNAL BAR falls in 2026. Each timeframe gets enough history BEFORE 2026 to
  warm up its own ATR and confirmed-pivot state - that data is never traded,
  only used so the indicators are not cold on January 1st.

WHY FOUR TIMEFRAMES SIDE BY SIDE

  Nothing in this project has tested P01 below H1. Cost as a share of ATR
  rises as the bar shrinks - this repo's own measurements put H1 at 8.7% and
  M15 at 13.5% - so if the H1 result is a coin flip on cost grounds, M1 is
  the harshest environment this rule could be asked to survive.
"""
import pathlib, sys
import numpy as np, pandas as pd

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import fetch_dukascopy as D
import xauusd_1000_setups as X
from p01_trade_log import trade_log

YEAR = 2026
TICK = 0.001
RISK = 0.01
START_EQUITY = 5000.0


def h1_source():
    df = pd.read_parquet(".cache_duka/XAUUSD_H1_2003_2026.parquet")
    df = df[df.index.year >= 2004]
    spr = df["ask_close"] - df["bid_close"]
    df = df[(spr > 0)]
    for k in ("open", "high", "low", "close"):
        df[k] = (df[f"bid_{k}"] + df[f"ask_{k}"]) / 2
    return df[df.high >= df.low]


def resample_bidask(src, rule):
    agg = {"open": "first", "high": "max", "low": "min", "close": "last",
           "bid_open": "first", "bid_high": "max", "bid_low": "min",
           "bid_close": "last", "ask_open": "first", "ask_high": "max",
           "ask_low": "min", "ask_close": "last"}
    out = src.resample(rule).agg(agg).dropna(subset=["close"])
    return out[(out.index.dayofweek < 5) |
               ((out.index.dayofweek == 5) & (out.index.hour == 0))]


def m1_source(start):
    m1 = D.load(start, None)
    m1["open"] = (m1["bid_open"] + m1["ask_open"]) / 2
    m1["high"] = (m1["bid_high"] + m1["ask_high"]) / 2
    m1["low"] = (m1["bid_low"] + m1["ask_low"]) / 2
    m1["close"] = (m1["bid_close"] + m1["ask_close"]) / 2
    return m1


def run_tf(name, bars):
    P = X.prep(bars, 0)
    dvec, Ivec = X.make_templates(P)["P01"]()
    n_yr = int((P["idx"] < pd.Timestamp(f"{YEAR}-01-01", tz="UTC")).sum())
    T = trade_log(P, dvec, Ivec, n_yr, P["N"], TICK, RISK, START_EQUITY)
    T["timeframe"] = name
    return P, T


def summarize(name, T):
    print(f"\n{'='*80}\n{name}\n{'='*80}")
    if len(T) == 0:
        print("  no trades")
        return
    n = len(T)
    wins = T[T.R > 0]
    print(f"  trades              {n:,}")
    print(f"  win rate            {len(wins)/n*100:.1f}%")
    if len(wins) and len(T[T.R <= 0]):
        print(f"  avg win / avg loss  {wins.R.mean():+.3f}R / "
              f"{T[T.R<=0].R.mean():+.3f}R")
    print(f"  exit reasons        " + ", ".join(
        f"{k} {v} ({v/n*100:.0f}%)" for k, v in
        T.exit_reason.value_counts().items()))
    print(f"  total P&L           {T.pnl_USC.sum():+,.2f} USC "
          f"(from {START_EQUITY:,.0f} start)")
    print(f"  ending equity       {T.equity_USC.iloc[-1]:,.2f} USC")
    print(f"  max drawdown        {T.drawdown_pct.max():.1f}%")
    zeroed = int((T.pnl_USC == 0).sum())
    if zeroed:
        print(f"  ({zeroed} trades sized below Exness's 0.01 min lot -> "
              f"pnl 0, not tradeable at this risk)")


def main():
    print("P01 - 2026 TRADES ONLY - H4 / H1 / M15 / M1 - FIXED ENGINE")
    print(f"risk {RISK*100:.0f}% of equity/trade, start {START_EQUITY:,.0f} USC, "
          f"real Dukascopy bid/ask\n")

    results = {}

    h1 = h1_source()
    h4 = resample_bidask(h1, "4h")
    P, T = run_tf("H4", h4)
    summarize("H4  (warm-up from 2004, signals only in 2026)", T)
    results["H4"] = T

    P, T = run_tf("H1", h1)
    summarize("H1  (warm-up from 2004, signals only in 2026)", T)
    results["H1"] = T

    m1_15 = m1_source("2023-01-01")
    m15 = resample_bidask(m1_15, "15min")
    P, T = run_tf("M15", m15)
    summarize("M15  (warm-up from 2023, signals only in 2026)", T)
    results["M15"] = T

    m1_src = m1_source("2025-06-01")
    m1_src = m1_src[(m1_src.index.dayofweek < 5) |
                    ((m1_src.index.dayofweek == 5) & (m1_src.index.hour == 0))]
    P, T = run_tf("M1", m1_src)
    summarize("M1  (warm-up from 2025-06, signals only in 2026)", T)
    results["M1"] = T

    print(f"\n{'='*80}\nSIDE BY SIDE\n{'='*80}")
    print(f"  {'tf':<6}{'trades':>8}{'win%':>7}{'sum R':>9}{'P&L USC':>11}"
          f"{'end equity':>12}{'max DD':>8}")
    for name, T in results.items():
        if len(T) == 0:
            print(f"  {name:<6}    no trades")
            continue
        print(f"  {name:<6}{len(T):>8,}{float((T.R>0).mean())*100:>6.1f}%"
              f"{T.R.sum():>+9.2f}{T.pnl_USC.sum():>+11.2f}"
              f"{T.equity_USC.iloc[-1]:>12.2f}{T.drawdown_pct.max():>7.1f}%")

    # H4 and H1 came back with EVERY trade below Exness's 0.01 min lot at 1%
    # risk on 500 USC - gold's 2026 stop distances average $29 on H1, and
    # 1% of 500 USC only affords 0.0022 lots. That is not a defect in the
    # engine, it is the account: report what risk fraction this account
    # would actually need to open a single H1 trade, since "0 P&L" alone
    # reads like a bug rather than a sizing wall.
    print(f"\n{'='*80}\nWHAT RISK THIS {START_EQUITY:,.0f} USC ACCOUNT WOULD NEED, "
          f"JUST TO OPEN")
    print(f"{'='*80}")
    any_wall = False
    for name, T in results.items():
        if len(T) == 0:
            continue
        dist = (T.entry_px - T.stop_px).abs()
        need = dist * 100 * 0.01  # USC needed for 0.01 lot
        pct = need / START_EQUITY * 100
        flag = "  <- exceeds the 1% risk budget" if pct.median() > 1.0 else ""
        if pct.median() > 1.0:
            any_wall = True
        print(f"  {name:<6}median stop ${dist.median():>7.2f}   needs "
              f"{need.median():>6.2f} USC for 0.01 lot   = "
              f"{pct.median():>5.2f}% of equity per trade{flag}")
    if any_wall:
        print(f"\n  At {RISK*100:.0f}% risk this account still cannot open every")
        print(f"  timeframe at minimum lot - see the flagged rows above.")
    else:
        print(f"\n  At {RISK*100:.0f}% risk on {START_EQUITY:,.0f} USC, the minimum")
        print(f"  lot no longer binds on any timeframe - unlike the 500 USC")
        print(f"  case, where H4 and H1 could not open a single trade.")

    for name, T in results.items():
        out = pathlib.Path(__file__).parent / f"p01_2026_{name}.csv"
        T.to_csv(out, index=False)
        print(f"\n  {name} full log -> {out.name}")


if __name__ == "__main__":
    main()
