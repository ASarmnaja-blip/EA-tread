#!/usr/bin/env python3
"""
Export XAU/USD M15 history from a running MetaTrader 5 terminal to CSV.

Requires no MQL5 script: it talks to the terminal through the official
`MetaTrader5` Python package, so the terminal just needs to be open and
logged in on the account whose history you want.

    pip install MetaTrader5 pandas
    python tools/export_mt5_data.py --symbol XAUUSD --years 6

Output: data/XAUUSD_M15.csv  (and optionally the tick file for
"Every tick based on real ticks" modelling).

The symbol name differs between brokers (XAUUSD, XAUUSD.m, XAUUSDm,
GOLD, XAUUSD#). Run with --list to print what your broker actually
offers before exporting.
"""
import argparse
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path


def die(msg: str) -> None:
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(1)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--symbol", default="XAUUSD")
    ap.add_argument("--years", type=float, default=6.0,
                    help="how far back to pull (default 6)")
    ap.add_argument("--outdir", default="data")
    ap.add_argument("--ticks", action="store_true",
                    help="also export raw ticks (large; needed for real-tick modelling)")
    ap.add_argument("--list", action="store_true",
                    help="list matching broker symbols and exit")
    args = ap.parse_args()

    try:
        import MetaTrader5 as mt5
        import pandas as pd
    except ImportError as exc:
        die(f"missing dependency: {exc}. Run: pip install MetaTrader5 pandas")

    if not mt5.initialize():
        die(f"could not attach to the MT5 terminal: {mt5.last_error()}. "
            "Open MetaTrader 5 and log in first.")

    try:
        if args.list:
            for s in mt5.symbols_get():
                if "XAU" in s.name.upper() or "GOLD" in s.name.upper():
                    print(f"{s.name:20s} digits={s.digits} contract={s.trade_contract_size} "
                          f"min_lot={s.volume_min} step={s.volume_step}")
            return

        info = mt5.symbol_info(args.symbol)
        if info is None:
            die(f"symbol {args.symbol!r} not found. Re-run with --list to see the real name.")
        if not info.visible and not mt5.symbol_select(args.symbol, True):
            die(f"could not select {args.symbol} in Market Watch")

        print(f"symbol      : {info.name}")
        print(f"digits      : {info.digits}   point: {info.point}")
        print(f"contract    : {info.trade_contract_size}")
        print(f"lot min/step: {info.volume_min} / {info.volume_step}")
        print(f"stops level : {info.trade_stops_level} points")

        end = datetime.now(timezone.utc)
        start = end - timedelta(days=int(args.years * 365.25))

        rates = mt5.copy_rates_range(args.symbol, mt5.TIMEFRAME_M15, start, end)
        if rates is None or len(rates) == 0:
            die(f"no M15 bars returned: {mt5.last_error()}. In the terminal open a "
                f"{args.symbol} M15 chart and scroll back to force a history download.")

        outdir = Path(args.outdir)
        outdir.mkdir(parents=True, exist_ok=True)

        df = pd.DataFrame(rates)
        df["time"] = pd.to_datetime(df["time"], unit="s")
        bars_csv = outdir / f"{args.symbol}_M15.csv"
        df.to_csv(bars_csv, index=False)

        span_days = (df["time"].iloc[-1] - df["time"].iloc[0]).days
        print(f"\nwrote {len(df):,} M15 bars -> {bars_csv}")
        print(f"range {df['time'].iloc[0]} .. {df['time'].iloc[-1]}  ({span_days} days)")

        # A gap report matters: the tester silently interpolates missing history,
        # which flatters any session-based strategy.
        gaps = df["time"].diff().dt.total_seconds().div(60)
        big = (gaps > 15 * 4) & (gaps < 60 * 24 * 2)   # ignore weekends
        print(f"intraday gaps > 1h (excluding weekends): {int(big.sum())}")

        if args.ticks:
            ticks = mt5.copy_ticks_range(args.symbol, start, end, mt5.COPY_TICKS_ALL)
            if ticks is None or len(ticks) == 0:
                print(f"warning: no ticks returned ({mt5.last_error()})")
            else:
                tdf = pd.DataFrame(ticks)
                tdf["time"] = pd.to_datetime(tdf["time_msc"], unit="ms")
                tick_csv = outdir / f"{args.symbol}_ticks.csv"
                tdf.to_csv(tick_csv, index=False)
                print(f"wrote {len(tdf):,} ticks -> {tick_csv}")
    finally:
        mt5.shutdown()


if __name__ == "__main__":
    main()
