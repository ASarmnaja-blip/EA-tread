"""Pull the deepest XAUUSD history the MT5 server provides on every timeframe
(READ-ONLY: copy_rates only, no order function), save to data/history/, and
audit what each timeframe really contains: first/last bar, bar count, bars
per trading day, share of days that are truly intraday, and large gaps.
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "history"
SYMBOLS = ("XAUUSD",)


def main() -> int:
    import MetaTrader5 as mt5
    if not mt5.initialize():
        print("MT5 initialize failed:", mt5.last_error()); return 2
    acc = mt5.account_info(); ti = mt5.terminal_info()
    print(f"server {acc.server} trade_mode {acc.trade_mode} (read-only); maxbars {ti.maxbars}")
    tfs = [("M1", mt5.TIMEFRAME_M1, 60), ("M5", mt5.TIMEFRAME_M5, 300), ("M15", mt5.TIMEFRAME_M15, 900),
           ("M30", mt5.TIMEFRAME_M30, 1800), ("H1", mt5.TIMEFRAME_H1, 3600), ("H4", mt5.TIMEFRAME_H4, 14400),
           ("D1", mt5.TIMEFRAME_D1, 86400), ("W1", mt5.TIMEFRAME_W1, 604800), ("MN1", mt5.TIMEFRAME_MN1, 2592000)]
    OUT.mkdir(parents=True, exist_ok=True)
    rows = []
    end = datetime.now(timezone.utc)
    for sym in SYMBOLS:
        info = mt5.symbol_info(sym); mt5.symbol_select(sym, True)
        for name, tf, sec in tfs:
            chunks, a = [], datetime(1970, 1, 1, tzinfo=timezone.utc)
            # step in windows so the server returns everything it has
            span = {60: 30, 300: 120, 900: 365, 1800: 730}.get(sec, 20000)
            while a < end:
                b = min(datetime.fromtimestamp(a.timestamp() + span * 86400, timezone.utc), end)
                r = mt5.copy_rates_range(sym, tf, a, b)
                if r is not None and len(r):
                    chunks.append(r)
                a = b
            if not chunks:
                rows.append(dict(symbol=sym, tf=name, bars=0)); continue
            r = np.concatenate(chunks)
            r = r[np.argsort(r["time"])]
            r = r[np.r_[True, r["time"][1:] != r["time"][:-1]]]
            t = r["time"].astype(np.int64)
            np.savez(OUT / f"{sym}_{name}.npz", t=t, o=r["open"], h=r["high"], l=r["low"], c=r["close"],
                     v=r["tick_volume"].astype(float), sp=r["spread"] * info.point)
            day = t // 86400
            per_day = pd.Series(1, index=day).groupby(level=0).size()
            gaps = np.diff(t)
            big = gaps > max(4 * 86400, 3 * sec)
            intraday_start = None
            if sec < 86400:
                full = per_day[per_day >= max(2, 0.5 * 86400 / sec * 0.9)]
                intraday_start = pd.to_datetime(full.index.min() * 86400, unit="s").date() if len(full) else None
            rows.append(dict(
                symbol=sym, tf=name, bars=len(t),
                first=pd.to_datetime(t[0], unit="s"), last=pd.to_datetime(t[-1], unit="s"),
                median_bars_per_day=float(per_day.median()),
                full_intraday_from=intraday_start,
                gaps_over_4d=int(big.sum()),
                largest_gap_days=round(float(gaps.max() / 86400), 1)))
            print(f"{sym} {name}: {len(t):,} bars {rows[-1]['first']} .. {rows[-1]['last']}", flush=True)
    mt5.shutdown()
    df = pd.DataFrame(rows)
    df.to_csv(OUT / "inventory_mt5.csv", index=False)
    pd.set_option("display.width", 250)
    print(df.to_string(index=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
