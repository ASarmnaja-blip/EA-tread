#!/usr/bin/env python3
"""
One command that does the whole XAUUSD export: find the symbol, measure the
server offset, pull M1 and M5, and write a single report you can paste back.

    pip install MetaTrader5 pandas
    python tools/mt5_export_all.py

Everything it prints also lands in data/mt5_export_report.txt.

Nothing here places an order. It only reads history from an open terminal.

The offset matters more than it looks: copy_rates_range returns BROKER SERVER
TIME, not UTC, and a wrong offset shifts every session bucket - invisible in a
summary, fatal in a session split. This script measures it and writes it into
each meta file so nothing downstream has to guess.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

LOG: list[str] = []


def say(msg: str = "") -> None:
    print(msg)
    LOG.append(msg)


def die(msg: str) -> None:
    say(f"ERROR: {msg}")
    _flush()
    sys.exit(1)


def _flush(outdir: str = "data") -> None:
    p = Path(outdir)
    p.mkdir(parents=True, exist_ok=True)
    (p / "mt5_export_report.txt").write_text("\n".join(LOG), encoding="utf-8")


def pick_symbol(mt5, wanted: str | None):
    if wanted:
        if mt5.symbol_info(wanted) is None:
            die(f"symbol {wanted!r} not found. Run with --list to see the real names.")
        return wanted
    cands = [s.name for s in mt5.symbols_get()
             if "XAU" in s.name.upper() or "GOLD" in s.name.upper()]
    if not cands:
        die("no XAU/GOLD symbol found on this account. Pass --symbol explicitly.")
    # prefer the plainest spelling, then the shortest
    for exact in ("XAUUSD", "GOLD"):
        if exact in cands:
            return exact
    return sorted(cands, key=len)[0]


def server_offset_hours(mt5, symbol: str) -> float:
    tick = mt5.symbol_info_tick(symbol)
    if tick is None or not tick.time:
        die(f"no tick for {symbol}. Is the market open and the symbol in Market Watch?")
    delta = tick.time - datetime.now(timezone.utc).timestamp()
    return round(delta / 3600.0 * 4) / 4.0      # nearest quarter hour


def export(mt5, pd, symbol: str, tf_name: str, years: float, offset: float,
           outdir: Path) -> dict | None:
    tf = getattr(mt5, f"TIMEFRAME_{tf_name}", None)
    if tf is None:
        die(f"unknown timeframe {tf_name}")
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=int(years * 365.25))
    rates = mt5.copy_rates_range(symbol, tf, start, end)
    if rates is None or len(rates) == 0:
        say(f"  {tf_name}: NO BARS RETURNED ({mt5.last_error()}). "
            f"Open a {symbol} {tf_name} chart, press Home, scroll back to force "
            f"a download, then re-run.")
        return None

    info = mt5.symbol_info(symbol)
    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s")     # broker server time

    outdir.mkdir(parents=True, exist_ok=True)
    csv_path = outdir / f"{symbol}_{tf_name}.csv"
    df.to_csv(csv_path, index=False)

    meta = dict(symbol=info.name, timeframe=tf_name, digits=info.digits,
                point=info.point, contract_size=info.trade_contract_size,
                volume_min=info.volume_min, volume_step=info.volume_step,
                server_offset_hours=offset,
                time_basis="broker server time (subtract server_offset_hours for UTC)",
                exported_utc=datetime.now(timezone.utc).isoformat())
    (outdir / f"{symbol}_{tf_name}.meta.json").write_text(json.dumps(meta, indent=2))

    span = (df["time"].iloc[-1] - df["time"].iloc[0]).days
    say(f"  {tf_name}: {len(df):,} bars  {df['time'].iloc[0]} .. "
        f"{df['time'].iloc[-1]}  ({span} days)  -> {csv_path.name}")

    tf_min = int(tf_name[1:]) if tf_name[0] == "M" else 60
    gaps = df["time"].diff().dt.total_seconds().div(60)
    intraday = int(((gaps > tf_min * 4) & (gaps < 60 * 24 * 2)).sum())
    weekend = int((gaps >= 60 * 24 * 2).sum())
    say(f"      intraday gaps > {tf_min * 4}min (excl. weekends): {intraday}"
        f"   weekend breaks: {weekend}")

    result = dict(timeframe=tf_name, bars=len(df), span_days=span,
                  first=str(df["time"].iloc[0]), last=str(df["time"].iloc[-1]),
                  intraday_gaps=intraday)

    if "spread" in df.columns:
        sp = df["spread"] * info.point
        result["spread"] = dict(mean=float(sp.mean()), median=float(sp.median()),
                                p90=float(sp.quantile(0.90)), max=float(sp.max()))
        say(f"      spread: mean {sp.mean():.4f}  median {sp.median():.4f}  "
            f"p90 {sp.quantile(0.90):.4f}  max {sp.max():.4f}")
    return result


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--symbol", default=None, help="default: auto-detect")
    ap.add_argument("--years", type=float, default=3.0)
    ap.add_argument("--outdir", default="data")
    ap.add_argument("--list", action="store_true", help="list gold symbols and exit")
    args = ap.parse_args()

    try:
        import MetaTrader5 as mt5
        import pandas as pd
    except ImportError as exc:
        die(f"missing dependency: {exc}.  pip install MetaTrader5 pandas")

    if not mt5.initialize():
        die(f"could not attach to the terminal: {mt5.last_error()}. "
            "Open MetaTrader 5 and log in first.")

    try:
        if args.list:
            for s in mt5.symbols_get():
                if "XAU" in s.name.upper() or "GOLD" in s.name.upper():
                    say(f"{s.name:20s} digits={s.digits} point={s.point} "
                        f"contract={s.trade_contract_size} min_lot={s.volume_min}")
            return 0

        symbol = pick_symbol(mt5, args.symbol)
        info = mt5.symbol_info(symbol)
        if not info.visible and not mt5.symbol_select(symbol, True):
            die(f"could not select {symbol} in Market Watch")
        info = mt5.symbol_info(symbol)

        say("=" * 72)
        say("MT5 EXPORT REPORT")
        say("=" * 72)
        say(f"terminal     : {mt5.terminal_info().name}  build {mt5.version()[1]}")
        say(f"account      : {mt5.account_info().server}  "
            f"({'DEMO' if mt5.account_info().trade_mode == 0 else 'LIVE'})")
        say("")
        say("SYMBOL SPEC")
        say(f"  name       : {info.name}")
        say(f"  digits     : {info.digits}    point: {info.point}")
        say(f"  contract   : {info.trade_contract_size}")
        say(f"  lot min    : {info.volume_min}   step: {info.volume_step}")
        say(f"  stops level: {info.trade_stops_level} points")
        say(f"  spread now : {info.spread} points = {info.spread * info.point:.4f}")

        off = server_offset_hours(mt5, symbol)
        say("")
        say(f"SERVER OFFSET: {off:+.2f} hours  (server time minus UTC)")
        say("  written into every meta.json; nothing downstream has to guess it")

        say("")
        say(f"EXPORTS  ({args.years} years requested)")
        outdir = Path(args.outdir)
        results = [r for r in (export(mt5, pd, symbol, tf, args.years, off, outdir)
                               for tf in ("M1", "M5")) if r]

        say("")
        say("SPREAD BY HOUR (broker server time, from the M5 file)")
        m5 = outdir / f"{symbol}_M5.csv"
        if m5.exists():
            df = pd.read_csv(m5, parse_dates=["time"])
            if "spread" in df.columns:
                sp = df["spread"] * info.point
                by = sp.groupby(df["time"].dt.hour).agg(["median", "mean", "max", "count"])
                say(f"  {'hour':>5}{'median':>10}{'mean':>10}{'max':>10}{'bars':>10}")
                for hh, row in by.iterrows():
                    say(f"  {hh:>5}{row['median']:>10.4f}{row['mean']:>10.4f}"
                        f"{row['max']:>10.4f}{int(row['count']):>10}")
                cheap = sorted(by['median'].nsmallest(6).index.tolist())
                say(f"  cheapest 6 hours (server time): {cheap}")
                say(f"  same hours in UTC             : "
                    f"{sorted((h - off) % 24 for h in cheap)}")
            else:
                say("  no spread column in this build's history")
        else:
            say("  M5 export did not produce a file")

        say("")
        say("=" * 72)
        say("Send the whole of this back. The CSVs stay on your machine.")
        say("=" * 72)
        return 0
    finally:
        _flush(args.outdir)
        mt5.shutdown()


if __name__ == "__main__":
    sys.exit(main())
