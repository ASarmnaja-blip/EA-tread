"""Is silver's gap the way MT5 triggers stops, or the price data?

Replays the matched M30 trades on the broker's own M1 bars twice, with the same entry bar, the same risk and the same 30-bar
time exit, changing one thing only:
  mid  stop and target walked on the mid price, entry at mid  - the research's method (Dukascopy mid)
  mt5  long enters at the ask, its stop and target trigger on the bid (short: the reverse)  - what MT5 does
Same data on both runs, so any difference is the trigger method alone. The mt5 run should also reproduce the EA's own trades,
which checks this replay before trusting the mid run.

MT5 bar prices are bids; ask = bid + spread x point, using each M1 bar's recorded spread. Within a minute the stop is checked
before the target, as the research engine does. All MT5 range requests use UTC-aware datetimes (a naive datetime is read as
local time and shifts the window by the UTC offset).

Usage: python silver_trigger_test.py [--markets XAGUSD,XAUUSD]
"""
from __future__ import annotations

import argparse
import sys
from datetime import timezone

import MetaTrader5 as mt5
import numpy as np
import pandas as pd

sys.path.insert(0, ".")
import compare_m30 as C

HOLD = 30
utc = lambda ts: ts.to_pydatetime().replace(tzinfo=timezone.utc)


def replay(m1, entry_px, d, risk, t_exit_open, mode, pt):
    """Walk M1 bars from the entry minute to the time-exit bar; returns (exit price in the trade's own terms, reason, gross R)."""
    bid_o, bid_h, bid_l = m1["open"], m1["high"], m1["low"]
    spr = m1["spread"] * pt
    if mode == "mid":
        o, h, l = bid_o + spr / 2, bid_h + spr / 2, bid_l + spr / 2
        trig_o, trig_h, trig_l = o, h, l
        ep = entry_px
    else:
        # long closes on the bid, short closes on the ask
        ep = entry_px
        if d > 0:
            trig_o, trig_h, trig_l = bid_o, bid_h, bid_l
        else:
            trig_o, trig_h, trig_l = bid_o + spr, bid_h + spr, bid_l + spr
    stop = ep - d * risk
    tp = ep + d * 2.0 * risk
    for k in range(len(m1)):
        if m1["time"][k] >= t_exit_open:
            # time exit at the open of bar e+30, priced on the side the position closes on
            px = trig_o[k]
            return px, "time", d * (px - ep) / risk
        if (d > 0 and trig_l[k] <= stop) or (d < 0 and trig_h[k] >= stop):
            px = stop if d * (trig_o[k] - stop) > 0 else trig_o[k]
            return px, "stop", d * (px - ep) / risk
        if (d > 0 and trig_h[k] >= tp) or (d < 0 and trig_l[k] <= tp):
            px = tp if d * (tp - trig_o[k]) > 0 else trig_o[k]
            return px, "tp", d * (px - ep) / risk
    return np.nan, "open", np.nan


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--markets", default="XAGUSD,XAUUSD")
    a = ap.parse_args()
    X, _, _ = C.load_ea(str(C.COMMON / "tester_g27k_m30_log.csv"))
    E = pd.read_csv(C.HANDOFF / "trades_M30.csv.gz")
    for c in ("entry_time_utc", "exit_time_utc"):
        E[c] = pd.to_datetime(E[c])
    E = E[(E.entry_time_utc >= "2023-01-01") & (E.entry_time_utc <= "2026-10-01")].copy()
    E["signal_bar"] = (E.entry_time_utc - C.M30).dt.floor("30min")
    d_ = E.direction; tol = E.stop_distance * 0.02
    E["reason"] = np.where((E.exit_price - (E.entry_price - d_ * E.stop_distance)).abs() <= tol, "stop",
                  np.where((E.exit_price - (E.entry_price + d_ * 2 * E.stop_distance)).abs() <= tol, "tp", "time"))
    J = E.merge(X, on=["market", "signal_bar"], suffixes=("_exp", "_ea"))
    J = J[J.net_R_ea.notna()]
    mt5.initialize(path=r"C:\Program Files\MetaTrader 5\terminal64.exe") or mt5.initialize()
    for m in [s.strip() for s in a.markets.split(",")]:
        g = J[J.market == m]
        pt = mt5.symbol_info(m).point
        rows = []
        for r in g.itertuples():
            e_bar = r.entry_time.floor("30min")
            bars = mt5.copy_rates_range(m, mt5.TIMEFRAME_M30, utc(e_bar), utc(e_bar + pd.Timedelta(days=10)))
            if bars is None or len(bars) <= HOLD:
                continue
            t_exit_open = int(bars[HOLD]["time"])                       # open of bar e+30, counting real bars
            m1 = mt5.copy_rates_range(m, mt5.TIMEFRAME_M1, utc(r.entry_time.floor("1min")), utc(pd.Timestamp(t_exit_open, unit="s")))
            if m1 is None or len(m1) == 0:
                continue
            d = int(r.direction_ea)
            risk = 2.0 * r.atr20
            spr0 = float(m1["spread"][0]) * pt
            mid0 = m1["open"][0] + spr0 / 2
            res_mid = replay(m1, mid0, d, risk, t_exit_open, "mid", pt)
            res_mt5 = replay(m1, r.fill, d, risk, t_exit_open, "mt5", pt)
            rows.append(dict(R_research=r.R_gross, R_ea=r.r_gross_ea, R_mid=res_mid[2], R_mt5=res_mt5[2],
                             why_research=r.reason, why_ea=r.exit_reason, why_mid=res_mid[1], why_mt5=res_mt5[1]))
        T = pd.DataFrame(rows)
        print(f"== {m}: {len(T)} matched trades replayed on the broker's M1 bars")
        print(f"   check - the mt5 replay reproduces the EA: exit reason agrees on {(T.why_mt5 == T.why_ea).mean():.0%},"
              f" gross R {T.R_mt5.mean():+.3f} vs EA {T.R_ea.mean():+.3f}")
        print(f"   gross R per trade:  research {T.R_research.mean():+.3f} | mid trigger {T.R_mid.mean():+.3f}"
              f" | mt5 trigger {T.R_mt5.mean():+.3f} | EA {T.R_ea.mean():+.3f}")
        gap = T.R_research.mean() - T.R_ea.mean()
        trig = T.R_mid.mean() - T.R_mt5.mean()
        print(f"   total gap research - EA {gap:+.3f}R, of which the trigger method alone {trig:+.3f}R ({trig / gap:.0%})"
              f" and the remaining data difference {gap - trig:+.3f}R")
        print(f"   exit reason, mid vs mt5 trigger on the SAME data:")
        print("   " + pd.crosstab(T.why_mid, T.why_mt5).to_string().replace("\n", "\n   "))
        print()
    mt5.shutdown()


if __name__ == "__main__":
    main()
