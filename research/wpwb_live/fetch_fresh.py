"""Fetch fresh M5 bars from the live MT5 terminal (read-only, no orders) and
verify the timestamp convention against the frozen canonical snapshot on
their overlap before any analysis uses them. Writes data/fresh/<SYM>_M5.npz.
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
os.chdir(ROOT)
sys.path.insert(0, str(ROOT / "research" / "pilot"))
import historical_regime_walkforward as hist  # noqa: E402

SYMBOLS = ("XAUUSD", "DXY", "XAGUSD", "US500", "USDJPY", "EURUSD")


def fetch(mt5, sym, start, end):
    info = mt5.symbol_info(sym)
    if info is None or not mt5.symbol_select(sym, True):
        return None
    chunks, a = [], start
    while a < end:
        b = min(a + timedelta(days=120), end)
        r = mt5.copy_rates_range(sym, mt5.TIMEFRAME_M5, a, b)
        if r is not None and len(r):
            chunks.append(r)
        a = b
    if not chunks:
        return None
    r = np.concatenate(chunks)
    r = r[np.argsort(r["time"])]
    r = r[np.r_[True, r["time"][1:] != r["time"][:-1]]]
    return dict(t=r["time"].astype(np.int64), o=r["open"], h=r["high"], l=r["low"],
                c=r["close"], v=r["tick_volume"].astype(float),
                sp=r["spread"] * info.point, point=info.point)


def main() -> int:
    import MetaTrader5 as mt5
    if not mt5.initialize():
        print("MT5 initialize failed:", mt5.last_error())
        return 2
    try:
        acc = mt5.account_info()
        print(f"terminal: {acc.server} trade_mode={acc.trade_mode} (read-only fetch)")
        end = datetime.now(timezone.utc) + timedelta(hours=1)
        start = datetime(2023, 9, 1, tzinfo=timezone.utc)
        Path("data/fresh").mkdir(parents=True, exist_ok=True)
        for sym in SYMBOLS:
            d = fetch(mt5, sym, start, end)
            if d is None:
                print(f"{sym}: unavailable")
                continue
            np.savez(f"data/fresh/{sym}_M5.npz", **d)
            print(f"{sym}: {len(d['t']):,} bars "
                  f"{datetime.fromtimestamp(int(d['t'][0]), timezone.utc):%Y-%m-%d} .. "
                  f"{datetime.fromtimestamp(int(d['t'][-1]), timezone.utc):%Y-%m-%d %H:%M}")
    finally:
        mt5.shutdown()

    # timestamp-convention check on the overlap with the canonical snapshot
    b5 = hist.load_history()
    f = np.load("data/fresh/XAUUSD_M5.npz")
    common_t, ia, ib = np.intersect1d(b5.t, f["t"], return_indices=True)
    diff = np.abs(b5.c[ia] - f["c"][ib])
    print(f"overlap bars: {len(common_t):,}; close match within 0.01: "
          f"{(diff <= 0.01).mean():.4%}; median |diff| {np.median(diff):.4f}")
    best = None
    for off_h in range(-3, 4):
        _, ja, jb = np.intersect1d(b5.t, f["t"] + off_h * 3600, return_indices=True)
        if len(ja):
            m = float((np.abs(b5.c[ja] - f["c"][jb]) <= 0.01).mean())
            best = max(best or (0, 0), (m, off_h))
    print(f"best-matching offset: {best[1]:+d} h (match {best[0]:.4%})")
    return 0 if best[1] == 0 and best[0] > 0.99 else 3


if __name__ == "__main__":
    raise SystemExit(main())
