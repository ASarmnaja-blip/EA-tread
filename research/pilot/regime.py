"""
Market Regime Score — how much the market's own character has changed lately.

Amendment 01 section 5 keeps this strictly apart from Strategy Health. MRS cuts
the windows that a setup is then measured on, so if a setup's own performance
fed into it the score would be choosing its own test set. Nothing here takes a
trade, a return, or any performance input, and `test_regime.py` asserts that
from the signature rather than trusting the comment.

Stability is not trendiness. A market that has been ranging quietly for two
weeks is stable; one that was ranging and has started trending is not, and so
is one that was trending and has stopped. Every component therefore compares a
SHORT window against a LONG one and asks how far the recent character has
drifted from the established one.

A component with no data source is reported missing. It is never imputed, and
the score carries the count and the names of what was absent, because a score
built from three inputs and one built from six should not look alike.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

# Declared tolerances: the drift at which a component's stability reaches zero.
# Fixed here rather than fitted - Amendment 01 section 7 treats an adaptive
# policy as a candidate that must beat fixed baselines before it is adopted.
TOL_ATR = 0.60          # ATR short/long ratio
TOL_STRUCTURE = 0.35    # efficiency-ratio difference
TOL_LIQUIDITY = 0.70    # activity short/long ratio
TOL_SPREAD = 0.60       # spread short/long ratio
TOL_VOV = 0.80          # volatility of volatility, normalised
EVENTS_AT_ZERO = 4      # high-impact events in the window that take it to zero

MIN_COMPONENTS = 3      # below this the score is not reported at all

STABLE, SHIFTING, BREAKING, UNKNOWN = "STABLE", "SHIFTING", "BREAKING", "UNKNOWN"


@dataclass
class RegimeScore:
    score: float | None
    label: str
    n_components: int
    missing: list[str] = field(default_factory=list)
    components: dict[str, float] = field(default_factory=dict)
    reason: str = ""

    @property
    def usable(self) -> bool:
        return self.score is not None


def _stability(drift: float, tol: float) -> float:
    """Map a drift to 0-100. Linear, clamped, and declared in advance."""
    if not np.isfinite(drift) or tol <= 0:
        return float("nan")
    return float(np.clip(100.0 * (1.0 - abs(drift) / tol), 0.0, 100.0))


def _efficiency(close: np.ndarray) -> float:
    """Kaufman efficiency: net travel over gross travel. Near 1 is directional,
    near 0 is choppy. Used only as a character measure to compare windows."""
    if len(close) < 3:
        return float("nan")
    gross = float(np.abs(np.diff(close)).sum())
    if gross <= 0:
        return float("nan")
    return abs(float(close[-1] - close[0])) / gross


def score_at(i: int, close: np.ndarray, atr: np.ndarray,
             volume: np.ndarray | None = None,
             spread: np.ndarray | None = None,
             n_events_in_window: int | None = None,
             short: int = 192, long: int = 960) -> RegimeScore:
    """Regime score using bars up to and including `i` - never past it.

    `short` and `long` default to roughly 2 and 10 trading days of 15m bars.
    """
    comps: dict[str, float] = {}
    missing: list[str] = []

    if i < long:
        return RegimeScore(None, UNKNOWN, 0, ["warm-up"], {},
                           f"only {i + 1} bars available, {long} needed")

    s0, l0, e = i - short + 1, i - long + 1, i + 1
    cs, cl = close[s0:e], close[l0:e]
    as_, al = atr[s0:e], atr[l0:e]

    # --- volatility level -------------------------------------------
    ml, ms = float(np.nanmean(al)), float(np.nanmean(as_))
    if ml > 0 and np.isfinite(ms):
        comps["atr_level"] = _stability(ms / ml - 1.0, TOL_ATR)
    else:
        missing.append("atr_level")

    # --- volatility of volatility -----------------------------------
    if len(al) > 2 and ml > 0:
        vov_l = float(np.nanstd(np.diff(al))) / ml
        vov_s = float(np.nanstd(np.diff(as_))) / ml
        comps["vol_of_vol"] = _stability(vov_s - vov_l, TOL_VOV)
    else:
        missing.append("vol_of_vol")

    # --- price structure --------------------------------------------
    es, el = _efficiency(cs), _efficiency(cl)
    if np.isfinite(es) and np.isfinite(el):
        comps["structure"] = _stability(es - el, TOL_STRUCTURE)
    else:
        missing.append("structure")

    # --- activity ----------------------------------------------------
    if volume is not None and len(volume) > i:
        vl = float(np.nanmean(volume[l0:e]))
        vs = float(np.nanmean(volume[s0:e]))
        if vl > 0:
            comps["liquidity"] = _stability(vs / vl - 1.0, TOL_LIQUIDITY)
        else:
            missing.append("liquidity")
    else:
        missing.append("liquidity")

    # --- cost --------------------------------------------------------
    if spread is not None and len(spread) > i:
        sl = float(np.nanmean(spread[l0:e]))
        ss = float(np.nanmean(spread[s0:e]))
        if sl > 0:
            comps["spread"] = _stability(ss / sl - 1.0, TOL_SPREAD)
        else:
            missing.append("spread")
    else:
        missing.append("spread")

    # --- scheduled events --------------------------------------------
    if n_events_in_window is not None:
        comps["events"] = _stability(n_events_in_window / EVENTS_AT_ZERO, 1.0)
    else:
        missing.append("events")

    # Cross-asset correlation is in the mandate and has no feed in this
    # project: no DXY, no US yields. Reported missing rather than dropped
    # quietly, so the score never looks more complete than it is.
    missing.append("cross_asset_correlation")

    good = {k: v for k, v in comps.items() if np.isfinite(v)}
    if len(good) < MIN_COMPONENTS:
        return RegimeScore(None, UNKNOWN, len(good), missing, good,
                           f"only {len(good)} components available, "
                           f"{MIN_COMPONENTS} required")

    val = float(np.mean(list(good.values())))
    label = STABLE if val >= 70 else (SHIFTING if val >= 40 else BREAKING)
    return RegimeScore(val, label, len(good), missing, good,
                       f"{len(good)} components, missing {missing}")
