#!/usr/bin/env python3
"""Discovery/holdout separation that survives being tested.

THREE LEAKS THE REVIEW IDENTIFIED, AND WHAT EACH ONE IS

  1. STRADDLING TRADES. A trade whose SIGNAL falls in discovery but whose EXIT
     falls in the holdout reads holdout bars to decide its own outcome. The
     previous code filtered on the signal index alone, so at hold=1000 a trade
     signalled on the last discovery bar consumed a thousand holdout bars and
     still counted as a discovery result.

  2. THRESHOLDS FITTED ON EVERYTHING. `build_filters` took the median of
     spread, volume and efficiency over the WHOLE series. Every "below median
     spread" decision in discovery therefore knew where the holdout's spreads
     would land. The fix is not to recompute the median per period - that is
     still two different rules - but to FIT ONCE ON DISCOVERY and carry the
     frozen number into the holdout, which is what a live system would have.

  3. THE CONTROL SAMPLED EVERYWHERE. The matched control drew its random bars
     from the full history, so the baseline a discovery result was measured
     against was partly built from holdout data.

WHAT THIS MODULE GUARANTEES
  A `Split` fixes the boundary once. `purge()` drops straddling trades and
  reports how many. `Thresholds` are fitted on discovery only and then frozen.
  `window_pool()` returns sampling indices confined to one side of the line.

  The guarantee is testable, and `test_split_guard.py` tests it: change every
  bar after the boundary and every discovery-side number must be bit-identical.
"""
import numpy as np, pandas as pd

class Split:
    """One boundary, fixed before anything is computed."""

    def __init__(self, index, boundary):
        b = pd.Timestamp(boundary)
        self.boundary = b.tz_localize("UTC") if b.tzinfo is None else b.tz_convert("UTC")
        self.index = index
        self.is_disc = index < self.boundary
        self.n_disc = int(self.is_disc.sum())
        if self.n_disc == 0 or self.n_disc == len(index):
            raise ValueError(f"boundary {self.boundary} leaves one side empty")

    def __repr__(self):
        return (f"Split(boundary={self.boundary.date()}, "
                f"discovery={self.n_disc:,} bars, "
                f"holdout={len(self.index) - self.n_disc:,} bars)")

    def side_mask(self, side):
        return self.is_disc if side == "discovery" else ~self.is_disc

def purge(sig_bars, exit_bars, split, side):
    """Keep only trades that BEGIN AND END on the requested side.

    Returns (keep_mask, report). A trade that starts in discovery and finishes
    in the holdout is dropped from both - it belongs to neither, because its
    outcome was decided by bars the discovery side is not allowed to see."""
    sig_bars = np.asarray(sig_bars, int)
    exit_bars = np.asarray(exit_bars, int)
    n_disc = split.n_disc
    starts_disc = sig_bars < n_disc
    ends_disc = exit_bars < n_disc
    straddles = starts_disc & ~ends_disc
    if side == "discovery":
        keep = starts_disc & ends_disc
    else:
        keep = ~starts_disc & ~ends_disc
    report = dict(total=len(sig_bars), kept=int(keep.sum()),
                  straddling=int(straddles.sum()),
                  other_side=int((starts_disc != (side == "discovery")).sum()))
    return keep, report

class Thresholds:
    """Fitted on discovery, then frozen.

    Every quantile a filter needs is computed once from discovery bars and
    reused verbatim on the holdout. Refitting per period would make discovery
    and holdout two different strategies; fitting on everything is the leak."""

    def __init__(self):
        self.values = {}
        self.fitted_on = None

    def fit(self, series_map, split):
        """series_map: {name: full-length array}. Only discovery rows are read."""
        d = split.is_disc
        for name, arr in series_map.items():
            a = np.asarray(arr, float)[d]
            a = a[np.isfinite(a)]
            self.values[name] = float(np.median(a)) if len(a) else float("nan")
        self.fitted_on = (split.boundary, split.n_disc)
        return self

    def __getitem__(self, name):
        if self.fitted_on is None:
            raise RuntimeError("thresholds used before fit() - that is the leak "
                               "this class exists to prevent")
        return self.values[name]

    def __repr__(self):
        return f"Thresholds(fitted_on_discovery={self.fitted_on}, {self.values})"

def window_pool(split, side, lo_pad, hi_pad):
    """Bar indices a control trade may be drawn from, confined to one side.

    lo_pad leaves room for indicator warm-up, hi_pad for the holding period, so
    a control trade drawn at the last eligible bar still resolves inside its
    own side rather than borrowing bars from across the line."""
    n = len(split.index)
    if side == "discovery":
        lo, hi = lo_pad, split.n_disc - hi_pad
    else:
        lo, hi = split.n_disc + lo_pad, n - hi_pad
    if hi <= lo:
        return np.array([], int)
    return np.arange(lo, hi)
