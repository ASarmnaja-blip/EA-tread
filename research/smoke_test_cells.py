"""Offline smoke test for the QuantConnect research cells.

Stubs the QuantBook surface with synthetic data so a cell can be run end to end
locally - catching crashes, shape errors and NaN handling before anyone spends
a QuantConnect run on them.

It doubles as a NEGATIVE CONTROL. The synthetic series is a driftless random
walk, so a cell free of look-ahead should report gross expectancy near zero on
it. Baseline currently returns +0.05R at t = +0.34, which is the answer a
martingale should give.

Point it at whichever cell you are changing by editing the path at the bottom.
"""
import numpy as np, pandas as pd
from datetime import datetime, timedelta

# ---- stub the QuantConnect surface the cell touches ----------------------
class Resolution:  MINUTE = "min"
class Market:      OANDA = "oanda"
class Futures:
    class Metals:  GOLD = "GC"
class DataNormalizationMode: BACKWARDS_RATIO = 0
class DataMappingMode:       OPEN_INTEREST = 0

RNG = np.random.default_rng(7)
# only serve these ranges, so both IS and OOS are populated but the test is small
SERVE = [(datetime(2025,1,1), datetime(2025,5,1)),
         (datetime(2026,1,1), datetime(2026,3,1))]

SUB = 12   # sub-steps per minute

def _synth(start, end, seed_price):
    """A driftless random walk whose bar extremes are the TRUE extremes of the
    path inside each minute.

    Drawing high/low independently of the path, as an earlier version did, is
    not a valid negative control here: a fake spike that reverts still trips
    TP1 and moves the other legs to break-even, so the ladder harvests noise
    that never happened and gross expectancy comes out positive on a
    martingale."""
    idx = pd.date_range(start, end, freq="min", inclusive="left")
    idx = idx[(idx.dayofweek < 5)]
    n = len(idx)
    if n == 0: return None
    path = (RNG.normal(0, 0.35 / np.sqrt(SUB), n * SUB).cumsum()
            + seed_price).reshape(n, SUB)
    df = pd.DataFrame({"open": path[:, 0], "high": path.max(1),
                       "low": path.min(1), "close": path[:, -1],
                       "volume": np.zeros(n)}, index=idx)
    return df

class _Sec:
    def __init__(self, s): self.symbol = s
class QuantBook:
    def add_cfd(self, t, r, m):   return _Sec("XAUUSD")
    def add_future(self, *a, **k): raise RuntimeError("no futures in smoke test")
    def history(self, sym, start, end, res=None):
        out = []
        for a, b in SERVE:
            lo, hi = max(a, start), min(b, end)
            if lo < hi:
                d = _synth(lo, hi, 2600.0 if a.year == 2025 else 4200.0)
                if d is not None: out.append(d)
        return pd.concat(out) if out else None

import builtins
for k, v in dict(Resolution=Resolution, Market=Market, Futures=Futures,
                 QuantBook=QuantBook, DataNormalizationMode=DataNormalizationMode,
                 DataMappingMode=DataMappingMode).items():
    setattr(builtins, k, v)

src = open("research/qc_4part_filter_test.py").read()
exec(compile(src, "census", "exec"), {"__name__": "__main__"})
