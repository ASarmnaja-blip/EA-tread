"""The ten entry tools retail traders actually use, with deliberately bad
parameter settings, implementing Amendment 09 section 3.

Nothing here is chosen because it is known to work or known to fail. The library
is the one people actually reach for, and each tool gets three parameter
settings - deliberately too fast, the textbook default, and deliberately too
slow - because "tune it to be as bad as possible" means searching a stated grid
for the worst rather than asserting which setting is bad.

Every tool exposes the same three things, all computed from the CLOSE of bar i
so that an entry at the next bar's open cannot see its own outcome:

    fire_long[i]   the tool would enter long here
    fire_short[i]  the tool would enter short here
    state[i]       +1 the tool is currently bullish, -1 bearish, 0 neutral

`state` exists for the contradiction stacks in Amendment 09 section 4: a pair
fires when tool A signals a direction while tool B's state points the other way.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import data as D


class Tool:
    __slots__ = ("name", "fire_long", "fire_short", "state")

    def __init__(self, name, fl, fs, st):
        self.name = name
        self.fire_long = fl
        self.fire_short = fs
        self.state = st


def _cross_up(x: np.ndarray, level) -> np.ndarray:
    p = pd.Series(x).shift(1).to_numpy()
    return (p <= level) & (x > level)


def _cross_dn(x: np.ndarray, level) -> np.ndarray:
    p = pd.Series(x).shift(1).to_numpy()
    return (p >= level) & (x < level)


def _rsi(c: np.ndarray, n: int) -> np.ndarray:
    d = np.diff(c, prepend=c[0])
    up = pd.Series(np.where(d > 0, d, 0.0)).ewm(alpha=1 / n, adjust=False).mean()
    dn = pd.Series(np.where(d < 0, -d, 0.0)).ewm(alpha=1 / n, adjust=False).mean()
    rs = up / dn.replace(0, np.nan)
    return (100 - 100 / (1 + rs)).to_numpy()


def _ema(x: np.ndarray, n: int) -> np.ndarray:
    return pd.Series(x).ewm(span=n, adjust=False).mean().to_numpy()


def build(b15: D.Bars) -> dict:
    """Every tool at every one of its three settings, keyed `tool:param`."""
    c, h, l, o = b15.c, b15.h, b15.l, b15.o
    out: dict[str, Tool] = {}

    # 1. RSI - crossing back out of oversold / overbought
    for n in (4, 14, 40):
        r = _rsi(c, n)
        out[f"rsi:{n}"] = Tool(f"rsi:{n}", _cross_up(r, 30), _cross_dn(r, 70),
                               np.where(r > 50, 1, np.where(r < 50, -1, 0)))

    # 2. Stochastic - %K crossing %D inside the extreme zone
    for n in (5, 14, 40):
        ll = pd.Series(l).rolling(n).min().to_numpy()
        hh = pd.Series(h).rolling(n).max().to_numpy()
        with np.errstate(invalid="ignore", divide="ignore"):
            k_ = 100 * (c - ll) / np.where(hh > ll, hh - ll, np.nan)
        d_ = pd.Series(k_).rolling(3).mean().to_numpy()
        up = _cross_up(k_ - d_, 0.0)
        dn = _cross_dn(k_ - d_, 0.0)
        out[f"stoch:{n}"] = Tool(f"stoch:{n}", up & (k_ < 20), dn & (k_ > 80),
                                 np.where(k_ > 50, 1, np.where(k_ < 50, -1, 0)))

    # 3. MACD - line crossing its signal
    for (f, s, g) in ((5, 10, 4), (12, 26, 9), (30, 60, 20)):
        line = _ema(c, f) - _ema(c, s)
        sig = _ema(line, g)
        out[f"macd:{f}-{s}"] = Tool(
            f"macd:{f}-{s}", _cross_up(line - sig, 0.0), _cross_dn(line - sig, 0.0),
            np.where(line > sig, 1, np.where(line < sig, -1, 0)))

    # 4. Bollinger - close outside the band, taken as mean reversion
    for n in (10, 20, 50):
        m = pd.Series(c).rolling(n).mean().to_numpy()
        sd = pd.Series(c).rolling(n).std().to_numpy()
        lo_b, hi_b = m - 2 * sd, m + 2 * sd
        out[f"boll:{n}"] = Tool(f"boll:{n}", c < lo_b, c > hi_b,
                                np.where(c > m, 1, np.where(c < m, -1, 0)))

    # 5. EMA cross
    for (f, s) in ((5, 10), (20, 50), (50, 200)):
        ef, es = _ema(c, f), _ema(c, s)
        out[f"emax:{f}-{s}"] = Tool(
            f"emax:{f}-{s}", _cross_up(ef - es, 0.0), _cross_dn(ef - es, 0.0),
            np.where(ef > es, 1, np.where(ef < es, -1, 0)))

    # 6. CCI - leaving an extreme reading
    for n in (7, 20, 60):
        tp = (h + l + c) / 3.0
        ma = pd.Series(tp).rolling(n).mean().to_numpy()
        md = pd.Series(tp).rolling(n).apply(
            lambda v: np.abs(v - v.mean()).mean(), raw=True).to_numpy()
        with np.errstate(invalid="ignore", divide="ignore"):
            cci = (tp - ma) / (0.015 * np.where(md > 0, md, np.nan))
        out[f"cci:{n}"] = Tool(f"cci:{n}", _cross_up(cci, -100), _cross_dn(cci, 100),
                               np.where(cci > 0, 1, np.where(cci < 0, -1, 0)))

    # 7. Williams %R - leaving an extreme reading
    for n in (7, 14, 50):
        hh = pd.Series(h).rolling(n).max().to_numpy()
        ll = pd.Series(l).rolling(n).min().to_numpy()
        with np.errstate(invalid="ignore", divide="ignore"):
            wr = -100 * (hh - c) / np.where(hh > ll, hh - ll, np.nan)
        out[f"wpr:{n}"] = Tool(f"wpr:{n}", _cross_up(wr, -80), _cross_dn(wr, -20),
                               np.where(wr > -50, 1, np.where(wr < -50, -1, 0)))

    # 8. Donchian breakout
    for n in (10, 20, 55):
        hh = pd.Series(h).rolling(n).max().shift(1).to_numpy()
        ll = pd.Series(l).rolling(n).min().shift(1).to_numpy()
        mid = (hh + ll) / 2.0
        out[f"donch:{n}"] = Tool(f"donch:{n}", c > hh, c < ll,
                                 np.where(c > mid, 1, np.where(c < mid, -1, 0)))

    # 9. Round numbers - a touch that is rejected, which is how they are traded
    for step in (5.0, 10.0, 50.0):
        lvl = np.round(c / step) * step
        touched = (l <= lvl) & (h >= lvl)
        out[f"round:{step:g}"] = Tool(
            f"round:{step:g}", touched & (c > lvl), touched & (c < lvl),
            np.where(c > lvl, 1, np.where(c < lvl, -1, 0)))

    # 10. Candle patterns - engulfing, plus a pin bar at three wick ratios
    body = np.abs(c - o)
    rng = np.maximum(h - l, 1e-12)
    up_w = h - np.maximum(c, o)
    dn_w = np.minimum(c, o) - l
    pb = pd.Series(body).shift(1).to_numpy()
    po = pd.Series(o).shift(1).to_numpy()
    pc = pd.Series(c).shift(1).to_numpy()
    engulf_up = (c > o) & (pc < po) & (c >= po) & (o <= pc)
    engulf_dn = (c < o) & (pc > po) & (c <= po) & (o >= pc)
    for ratio in (1.5, 2.0, 3.0):
        pin_up = (dn_w >= ratio * body) & (body < 0.4 * rng)
        pin_dn = (up_w >= ratio * body) & (body < 0.4 * rng)
        out[f"candle:{ratio:g}"] = Tool(
            f"candle:{ratio:g}", engulf_up | pin_up, engulf_dn | pin_dn,
            np.where(c > o, 1, np.where(c < o, -1, 0)))

    for t in out.values():
        t.fire_long = np.nan_to_num(t.fire_long, nan=0).astype(bool)
        t.fire_short = np.nan_to_num(t.fire_short, nan=0).astype(bool)
        t.state = np.nan_to_num(t.state, nan=0).astype(int)
    return out


# The textbook setting of each tool, used for the contradiction pairs so that
# the pair grid measures the DISAGREEMENT rather than a second parameter sweep.
DEFAULTS = ("rsi:14", "stoch:14", "macd:12-26", "boll:20", "emax:20-50",
            "cci:20", "wpr:14", "donch:20", "round:10", "candle:2")
