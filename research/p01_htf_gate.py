#!/usr/bin/env python3
"""P01 gated by a higher-timeframe trend: M5 on M15/M30, M15 on H1/H4.

THE GATE, PER THE SPEC'S OWN C02 DEFINITION

  Buy allowed only if EMA20_HTF > EMA50_HTF AND EMA20_HTF is higher than it
  was 3 HTF bars ago (rising, not just above). Sell is the mirror. C02's own
  text: "ใช้ H1 ปิดแล้วและตรวจซ้ำก่อน fill" - use the HTF bar that has
  ALREADY CLOSED, not the one still forming.

  That closed-bar requirement is the part a naive implementation gets wrong.
  A signal on M15 at 14:37 cannot see the H1 bar covering 14:00-15:00,
  because that bar has not closed yet - it can only see the H1 bar that
  closed at 14:00. This is done with merge_asof against each HTF bar's own
  CLOSE time (open + its own period), direction="backward", so every LTF
  signal is matched to the last HTF bar genuinely known at that instant.

WHAT IS COMPARED

  Same fixed engine as p01_trade_log.py / p01_multi_tf_2026.py (real
  bid/ask, TP=1R, 24-bar time exit, tick-rounded SL, G09 gate), same 2026
  signals-only window, same 5,000 USC / 1% risk account. Baseline (no HTF
  filter) against gated, side by side, so the filter's effect is read
  against the SAME underlying signals rather than a different run.
"""
import pathlib, sys
import numpy as np, pandas as pd

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import fetch_dukascopy as D
import xauusd_1000_setups as X
from p01_trade_log import trade_log
from p01_multi_tf_2026 import h1_source, resample_bidask, m1_source

YEAR = 2026
TICK = 0.001
RISK = 0.01
START_EQUITY = 5000.0

HTF_FREQ = {"M15": pd.Timedelta(minutes=15), "M30": pd.Timedelta(minutes=30),
           "H1": pd.Timedelta(hours=1), "H4": pd.Timedelta(hours=4)}


def htf_trend_state(htf_bars, freq):
    """EMA20/EMA50 trend, C02's rule, indexed by the bar's own CLOSE time -
    the instant it becomes knowable to anything watching a finer clock."""
    c = htf_bars["close"].to_numpy(float)
    e20 = pd.Series(X.ema(c, 20), index=htf_bars.index)
    e50 = pd.Series(X.ema(c, 50), index=htf_bars.index)
    up = (e20 > e50) & (e20 > e20.shift(3))
    dn = (e20 < e50) & (e20 < e20.shift(3))
    state = pd.Series(0, index=htf_bars.index, dtype=np.int8)
    state[up.fillna(False)] = 1
    state[dn.fillna(False)] = -1
    close_time = pd.DatetimeIndex(htf_bars.index + freq).as_unit("us")
    return pd.DataFrame({"close_time": close_time, "state": state.to_numpy()})


def apply_htf_gate(ltf_idx, dvec, htf_state_df):
    """Keep a signal only if it agrees with the last CLOSED HTF bar's trend."""
    sig_times = pd.DataFrame({"t": pd.DatetimeIndex(ltf_idx[np.arange(len(dvec))])
                              .as_unit("us")})
    matched = pd.merge_asof(sig_times.sort_values("t"), htf_state_df,
                            left_on="t", right_on="close_time",
                            direction="backward")
    matched = matched.set_index(sig_times.index)  # merge_asof re-sorts; restore
    matched = matched.reindex(sig_times.sort_values("t").index).sort_index()
    htf_state = matched["state"].to_numpy()
    out = dvec.copy()
    out[(dvec != 0) & (dvec != htf_state)] = 0
    return out


def run_variant(label, ltf_bars, htf_bars, htf_freq):
    P = X.prep(ltf_bars, 0)
    dvec, Ivec = X.make_templates(P)["P01"]()
    n_yr = int((P["idx"] < pd.Timestamp(f"{YEAR}-01-01", tz="UTC")).sum())

    rows = {}
    T0 = trade_log(P, dvec, Ivec, n_yr, P["N"], TICK, RISK, START_EQUITY)
    rows["no filter"] = T0

    if htf_bars is not None:
        hstate = htf_trend_state(htf_bars, htf_freq)
        dvec_g = apply_htf_gate(P["idx"], dvec, hstate)
        kept = int((dvec_g != 0).sum())
        total = int((dvec != 0).sum())
        T1 = trade_log(P, dvec_g, Ivec, n_yr, P["N"], TICK, RISK, START_EQUITY)
        rows[f"HTF-gated ({kept}/{total} signals kept)"] = T1
    return rows


def summarize(name, T):
    if len(T) == 0:
        print(f"    {name:<40} no trades")
        return
    n = len(T)
    win = float((T.R > 0).mean()) * 100
    print(f"    {name:<40}{n:>6,}{win:>7.1f}%{T.R.sum():>+9.2f}"
          f"{T.pnl_USC.sum():>+11.2f}{T.equity_USC.iloc[-1]:>12.2f}"
          f"{T.drawdown_pct.max():>8.1f}%")


def main():
    print("P01 GATED BY HTF TREND - M5 on M15/M30, M15 on H1/H4 - 2026 ONLY")
    print("=" * 92)
    print(__doc__.split("THE GATE, PER THE SPEC'S OWN C02 DEFINITION")[1]
          .split("WHAT IS COMPARED")[0])
    print(f"5,000 USC start, 1% risk, real Dukascopy bid/ask\n")

    m1_m5 = m1_source("2025-09-01")
    m1_m5 = m1_m5[(m1_m5.index.dayofweek < 5) |
                  ((m1_m5.index.dayofweek == 5) & (m1_m5.index.hour == 0))]
    m5 = resample_bidask(m1_m5, "5min")
    m15_for_m5 = resample_bidask(m1_m5, "15min")
    m30_for_m5 = resample_bidask(m1_m5, "30min")

    m1_m15 = m1_source("2023-01-01")
    m1_m15 = m1_m15[(m1_m15.index.dayofweek < 5) |
                    ((m1_m15.index.dayofweek == 5) & (m1_m15.index.hour == 0))]
    m15 = resample_bidask(m1_m15, "15min")

    h1 = h1_source()
    h4 = resample_bidask(h1, "4h")

    print(f"  {'variant':<44}{'trades':>6}{'win%':>7}{'sum R':>9}"
          f"{'P&L USC':>11}{'equity':>12}{'max DD':>8}")

    print("\nM5, HTF = M15")
    r = run_variant("M5/M15", m5, m15_for_m5, HTF_FREQ["M15"])
    for k, T in r.items():
        summarize(k, T)

    print("\nM5, HTF = M30")
    r2 = run_variant("M5/M30", m5, m30_for_m5, HTF_FREQ["M30"])
    summarize(list(r2.keys())[1], r2[list(r2.keys())[1]])

    print("\nM15, HTF = H1")
    r3 = run_variant("M15/H1", m15, h1, HTF_FREQ["H1"])
    for k, T in r3.items():
        summarize(k, T)

    print("\nM15, HTF = H4")
    r4 = run_variant("M15/H4", m15, h4, HTF_FREQ["H4"])
    summarize(list(r4.keys())[1], r4[list(r4.keys())[1]])

    # save every book that has trades
    all_books = {"M5_nofilter": r["no filter"],
                 "M5_HTF_M15": r[list(r.keys())[1]],
                 "M5_HTF_M30": r2[list(r2.keys())[1]],
                 "M15_nofilter": r3["no filter"],
                 "M15_HTF_H1": r3[list(r3.keys())[1]],
                 "M15_HTF_H4": r4[list(r4.keys())[1]]}
    for name, T in all_books.items():
        out = pathlib.Path(__file__).parent / f"p01_htf_{name}.csv"
        T.to_csv(out, index=False)
    print(f"\n  saved: " + ", ".join(f"p01_htf_{n}.csv" for n in all_books))


if __name__ == "__main__":
    main()
