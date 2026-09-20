"""
Synthetic price generators for Amendment 01 calibration.

All are driftless, so the true skill of any rule run on them is exactly zero.
They borrow the real bar calendar - timestamps, weekend holes, the CME break -
and one scalar, the 5m return standard deviation. No real price is scored.
"""
from __future__ import annotations

import numpy as np

from data import Bars

SUBSTEPS = 20


def _ohlc(t, v, sig_per_bar, rng, first_px):
    """Build 5m OHLC from SUBSTEPS sub-moves per bar, so no printed high or low
    is unreachable by the path that produced it."""
    n = len(t)
    inc = rng.normal(0.0, 1.0, size=(n, SUBSTEPS)) * (sig_per_bar[:, None] / np.sqrt(SUBSTEPS))
    path = np.cumsum(inc, axis=1)
    base = first_px + np.concatenate(([0.0], np.cumsum(path[:, -1])[:-1]))
    px = base[:, None] + path
    o = np.concatenate(([first_px], px[:-1, -1]))
    return Bars(t, o, np.maximum(px.max(1), o), np.minimum(px.min(1), o),
                px[:, -1], v, 300, "SYNTH")


def c1_random_walk(b5: Bars, sigma: float, rng) -> Bars:
    """Constant volatility."""
    return _ohlc(b5.t, b5.v, np.full(len(b5), sigma), rng, float(b5.c[0]))


def c2_vol_clustering(b5: Bars, sigma: float, rng,
                      alpha: float = 0.08, beta: float = 0.90) -> Bars:
    """GARCH(1,1) volatility, same unconditional level, still driftless.

    Persistence 0.98 - real intraday volatility clusters hard, and a control
    calibrated only at constant volatility is not calibrated.
    """
    n = len(b5)
    omega = sigma ** 2 * (1.0 - alpha - beta)
    s2 = np.empty(n)
    s2[0] = sigma ** 2
    e = rng.normal(0.0, 1.0, size=n)
    for i in range(1, n):
        s2[i] = omega + alpha * (e[i - 1] ** 2) * s2[i - 1] + beta * s2[i - 1]
    return _ohlc(b5.t, b5.v, np.sqrt(s2), rng, float(b5.c[0]))


def c3_extra_holes(b5: Bars, sigma: float, rng, drop_frac: float = 0.05) -> Bars:
    """C2 with additional bars deleted at random, on top of the calendar's own
    weekend and maintenance holes. The shift drops signals when a bar is
    absent, and that must not create a bias of its own."""
    b = c2_vol_clustering(b5, sigma, rng)
    keep = rng.random(len(b)) >= drop_frac
    keep[0] = keep[-1] = True
    return Bars(b.t[keep], b.o[keep], b.h[keep], b.l[keep], b.c[keep],
                b.v[keep], 300, "SYNTH")
