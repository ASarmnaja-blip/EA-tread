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
    ap.add_argument("--timeframe", default="M15",
                    choices=["M1", "M5", "M15", "M30", "H1"],
                    help="M1 is what the research cells want: exits are resolved "
                         "on minute bars and every higher timeframe is resampled "
                         "from them (default M15)")
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

        tf = getattr(mt5, f"TIMEFRAME_{args.timeframe}")
        rates = mt5.copy_rates_range(args.symbol, tf, start, end)
        if rates is None or len(rates) == 0:
            die(f"no {args.timeframe} bars returned: {mt5.last_error()}. In the terminal "
                f"open a {args.symbol} {args.timeframe} chart and scroll back to force a "
                "history download.")

        outdir = Path(args.outdir)
        outdir.mkdir(parents=True, exist_ok=True)

        df = pd.DataFrame(rates)
        df["time"] = pd.to_datetime(df["time"], unit="s")
        bars_csv = outdir / f"{args.symbol}_{args.timeframe}.csv"
        df.to_csv(bars_csv, index=False)

        # The point size is needed to turn the spread column from points into
        # price, and it is not recoverable from the bars alone. Written beside
        # them so the research notebooks do not have to guess it.
        import json
        meta = dict(symbol=info.name, timeframe=args.timeframe, digits=info.digits,
                    point=info.point, contract_size=info.trade_contract_size,
                    volume_min=info.volume_min, volume_step=info.volume_step,
                    exported_utc=datetime.now(timezone.utc).isoformat())
        (outdir / f"{args.symbol}_{args.timeframe}.meta.json").write_text(
            json.dumps(meta, indent=2))

        span_days = (df["time"].iloc[-1] - df["time"].iloc[0]).days
        print(f"\nwrote {len(df):,} {args.timeframe} bars -> {bars_csv}")
        print(f"range {df['time'].iloc[0]} .. {df['time'].iloc[-1]}  ({span_days} days)")

        # A gap report matters: the tester silently interpolates missing history,
        # which flatters any session-based strategy.
        tf_min = int(args.timeframe[1:]) if args.timeframe[0] == "M" else 60
        gaps = df["time"].diff().dt.total_seconds().div(60)
        big = (gaps > tf_min * 4) & (gaps < 60 * 24 * 2)   # ignore weekends
        print(f"intraday gaps > 1h (excluding weekends): {int(big.sum())}")

        # THE SPREAD COLUMN IS THE POINT OF THIS EXPORT.
        # Every backtest so far has assumed one flat number for the spread. MT5
        # records what this broker actually charged on each bar, so the cost
        # side stops being an assumption. Hours matter enormously: the research
        # cells charge a single average, which overcharges liquid hours and
        # undercharges the rollover.
        if "spread" in df.columns:
            sp = df["spread"] * info.point
            print(f"\nSPREAD, as your broker actually charged it ({info.name}):")
            print(f"  mean {sp.mean():.4f}   median {sp.median():.4f}   "
                  f"p90 {sp.quantile(0.90):.4f}   max {sp.max():.4f}")
            by_hour = sp.groupby(df["time"].dt.hour).agg(["median", "mean", "count"])
            print(f"  {'hour':>5}{'median':>10}{'mean':>10}{'bars':>9}")
            for hh, row in by_hour.iterrows():
                print(f"  {hh:>5}{row['median']:>10.4f}{row['mean']:>10.4f}"
                      f"{int(row['count']):>9}")
            cheap = by_hour["median"].nsmallest(6).index.tolist()
            print(f"  cheapest 6 hours (broker time): {sorted(cheap)}")
            print("  Feed this file to research/colab_backtest.py, which charges")
            print("  the real per-bar spread instead of one flat guess.")

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
