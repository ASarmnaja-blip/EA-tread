"""M1-only extension of the weekly diverse evolutionary selector.

Signals close on M1 and can first execute at the following M1 open.  The 24h
time stop is therefore 1,440 M1 bars.  This is a separate, shorter-history
extension and is never merged silently with the M5-based result.
"""
from __future__ import annotations

from pathlib import Path
import pickle
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import data as D
import evolution_portfolio_audit as audit
import mtf_engine as E
import walk_forward as wf


CACHE = Path("data/weekly_evolution_m1_v3.pkl")


def load_m1_universe():
    raw = D.load_csv("data/XAUUSD_M1.csv")
    # E.resample validates a 300-second execution base.  For the M1-only
    # mult=1 path it does not resample or synthesize timestamps, so a proxy
    # step lets us reuse the audited entry/resolve machinery while the actual
    # 60-second timestamps remain untouched everywhere that affects results.
    spread = (np.maximum(raw.sp, E.SPREAD_FALLBACK) if raw.sp is not None
              else np.full(len(raw), E.SPREAD_FALLBACK))
    base = D.Bars(raw.t, raw.o, raw.h, raw.l, raw.c, raw.v, 300,
                  raw.symbol, spread)
    stamp = audit.canonical.bars_digest(base)
    if CACHE.exists():
        with CACHE.open("rb") as fh:
            old_stamp, uni, meta = pickle.load(fh)
        if old_stamp == stamp:
            print(f"m1_cache=HIT cells={len(uni):,}")
            return base, uni, meta
    print("m1_cache=MISS building 1,650 declared M1 cells...")
    old_tf, old_stop = E.TIMEFRAMES, E.TIME_STOP_M5
    try:
        E.TIMEFRAMES = (("M1", 1),)
        E.TIME_STOP_M5 = 1440
        uni, meta = wf.build_universe(base, int(base.t[-1] + 60))
    finally:
        E.TIMEFRAMES, E.TIME_STOP_M5 = old_tf, old_stop
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    with CACHE.open("wb") as fh:
        pickle.dump((stamp, uni, meta), fh, protocol=pickle.HIGHEST_PROTOCOL)
    return base, uni, meta


def main() -> int:
    b1, uni, meta = load_m1_universe()
    first, last = int(b1.t[0]), int(b1.t[-1] + 60)
    rankings, purged = audit.weekly_rankings(uni, first, last)
    rows, info = audit.weekly_portfolio(
        b1, uni, meta, rankings, purged, 5, True)
    print("M1", info)
    print("FULL", audit.metrics(rows))
    print("365D", audit.metrics(rows, last - 365 * audit.DAY))
    print("90D", audit.metrics(rows, last - 90 * audit.DAY))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
