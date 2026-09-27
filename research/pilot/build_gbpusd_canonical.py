"""Fetch and validate a canonical GBPUSD M5 file, 2021-08-01 onward.

Amendment 29. Uses the same fetch/validate/save discipline already proven for
XAUUSD (canonical_history.py, historical_regime_walkforward.py's chunking).
GBPUSD's canonical file is separate; the XAUUSD one is untouched.
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import canonical_history as ch
from data import Bars

SYMBOL = "GBPUSD"
START = datetime(2021, 8, 1, tzinfo=timezone.utc)
OUT = Path("data/canonical_GBPUSD_M5.npz")


def main() -> int:
    import MetaTrader5 as mt5
    if not mt5.initialize():
        print("MT5 init failed:", mt5.last_error())
        return 1
    info = mt5.symbol_info(SYMBOL)
    if info is None:
        print("no symbol info"); mt5.shutdown(); return 1
    end = datetime.now(timezone.utc)
    chunks = []
    y0, y1 = START.year, end.year
    for year in range(y0, y1 + 1):
        a = max(START, datetime(year, 1, 1, tzinfo=timezone.utc))
        b = min(end, datetime(year + 1, 1, 1, tzinfo=timezone.utc))
        if a >= b:
            continue
        rates = mt5.copy_rates_range(SYMBOL, mt5.TIMEFRAME_M5, a, b)
        n = 0 if rates is None else len(rates)
        print(f"  {year}: {a:%Y-%m-%d}..{b:%Y-%m-%d} -> {n:,} bars")
        if rates is not None and len(rates):
            chunks.append(rates)
    mt5.shutdown()
    if not chunks:
        print("no data"); return 1
    r = np.concatenate(chunks)
    order = np.argsort(r["time"])
    r = r[order]
    uniq = np.r_[True, r["time"][1:] != r["time"][:-1]]
    r = r[uniq]
    print(f"total unique bars: {len(r):,}")

    step = 300
    gaps = np.diff(r["time"].astype(np.int64))
    print(f"gap histogram: ==step {np.sum(gaps==step):,}  "
          f"weekend/other {np.sum((gaps>step)&(gaps<=3*86400)):,}  "
          f">3d {np.sum(gaps>3*86400):,}")

    sp = np.maximum(r["spread"].astype(np.float64) * info.point, 1e-9)
    bars = Bars(r["time"].astype(np.int64), r["open"].astype(np.float64),
               r["high"].astype(np.float64), r["low"].astype(np.float64),
               r["close"].astype(np.float64), r["tick_volume"].astype(np.float64),
               300, SYMBOL, sp)

    if OUT.exists():
        OUT.unlink()
        OUT.with_suffix(OUT.suffix + ".json").unlink(missing_ok=True)
    meta = ch.save(OUT, bars, source=f"MT5 annual M5 {START:%Y-%m-%d}..now")
    print(f"\nsaved {OUT}")
    print(f"  bars {meta['bars']:,}  {datetime.fromtimestamp(meta['first_epoch'], timezone.utc)}"
          f" .. {datetime.fromtimestamp(meta['last_epoch'], timezone.utc)}")
    print(f"  sha256 {meta['sha256'][:16]}...")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
