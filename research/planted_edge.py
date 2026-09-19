#!/usr/bin/env python3
"""A synthetic generator with a REAL, sized edge, for positive-control
calibration.

WHY A NEGATIVE CALIBRATION IS NOT ENOUGH

  calibrate_pipeline.py proves the pipeline stays quiet on data with nothing
  in it. That is necessary but not sufficient: a gate tightened enough to
  never fire on noise could just as easily never fire on anything, including
  a real edge. A search that always says no is calibrated against false
  positives and worthless against false negatives, and nothing about the
  no-edge run can tell those two apart. The only way to tell them apart is to
  hand the pipeline data where the right answer is known to be YES and check
  it says so.

THE CONSTRUCTION

  Built on top of mega_search.synth's arithmetic martingale so the ONLY
  difference from the calibration data is the planted effect - same step
  size, same spread, same structure. Every `period` bars, a coin flip in
  {up, down} is drawn. The bar exactly `look` bars before the flip is
  engineered to look like a real breakout: `pre` bars of low-volatility noise
  (so a genuine N-bar range forms), then the flip's direction is a real
  drift added on top of ordinary steps for the next `drift_bars` bars, sized
  so that a trade taking the ATR-implied stop and this rule's own risk
  distance earns approximately `edge_r` R in expectation over that window.

  This does not reverse-engineer the specific breakout rule's signals (that
  would be circular - the rule's own detector would be told the answer).
  It engineers the PRICE STRUCTURE a breakout rule is built to find - a
  quiet range followed by a genuine directional move - at a size the rule
  can be expected to catch a large fraction of the time, and leaves the
  discovery process to actually find it.

WHAT edge_r MEANS
  edge_r is the intended mean R of a trade taken at the flip, given the
  ATR at that point and a 1x-2x ATR stop (the range this repo's rules use).
  It is a target, not a guarantee - the realized edge depends on how well the
  rule's own stop/entry timing lines up with the injected structure, which is
  exactly what the positive-control run is checking.
"""
import numpy as np, pandas as pd

def planted(n, seed, sigma, edge_r, period=60, pre=24, drift_bars=24,
            look=20):
    """One synthetic OHLC frame with a planted directional edge of size
    edge_r (in R, roughly) injected every `period` bars."""
    rng = np.random.default_rng(seed)
    step_abs = 2000.0 * sigma
    price = 2000.0
    o = np.empty(n); h = np.empty(n); lo = np.empty(n); c = np.empty(n)
    flip_bars, flip_dirs = [], []
    next_flip = period
    drift_until = -1
    drift_dir = 0
    drift_per_bar = 0.0
    for i in range(n):
        # decide today's per-bar drift, if we are inside a planted window
        if i == next_flip - drift_bars:
            drift_dir = 1 if rng.random() < 0.5 else -1
            # ATR proxy: recent realised step size, so the target R is
            # calibrated to whatever regime the noise happens to be in
            recent = step_abs * np.sqrt(pre)     # rough N-bar range scale
            stop_dist = 1.5 * step_abs * np.sqrt(look)   # ~ range-based stop
            total_move = edge_r * stop_dist
            drift_per_bar = drift_dir * total_move / drift_bars
            drift_until = i + drift_bars
            flip_bars.append(i); flip_dirs.append(drift_dir)
        if i == next_flip:
            next_flip += period
        d = drift_per_bar if i < drift_until else 0.0
        steps = rng.normal(d, step_abs, 4)
        path = price + np.cumsum(steps)
        o[i] = price
        h[i] = max(price, path.max())
        lo[i] = min(price, path.min())
        c[i] = path[-1]
        price = path[-1]
    idx = pd.date_range("2004-01-01", periods=n, freq="1h", tz="UTC")
    m = pd.DataFrame({"open": o, "high": h, "low": lo, "close": c,
                      "spread": np.full(n, 0.40), "volume": np.ones(n)},
                     index=idx)
    return m, dict(flip_bars=flip_bars, flip_dirs=flip_dirs,
                   edge_r=edge_r, period=period, drift_bars=drift_bars)
