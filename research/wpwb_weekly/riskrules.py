"""Frozen rules that close the holes in docs/WPWB_HOLES.md (spec v3 draft).

Every rule here can only REFUSE or REDUCE. None of them opens a position,
chooses a direction, or increases size. They are stated before measurement
where possible, and the few numeric constants are descriptive risk quantities
read once from the data by `measure_tails.py` (how large is a weekend gap, how
far price moves in the news minute, what the broker requires as margin) — not
parameters tuned to make anything profitable.

H2 intraweek breaker · H3 weekend gap · H4 news minute · H6 broker stop-out.
"""
from __future__ import annotations

import math

import numpy as np

# ---------------------------------------------------------------- H2 breaker
# Reuses the volatility class edge already frozen in spec v2 (NORMAL -> HIGH is
# a variance ratio of 1.5): the breaker trips when the week is PACING into a
# higher class than was forecast. No new constant is introduced.
BREAKER_K = 1.5
# No breaker before this many H1 bars have closed inside the week: two or three
# noisy bars must not trip it. 20 bars ~ Monday's close in a normal week.
BREAKER_MIN_BARS = 20
BARS_PER_WEEK = 115          # typical complete week (median of the frozen history)

# ---------------------------------------------------------- H3 / H4 / H6
# Filled by measure_tails.py on 2026-09-29 and then FROZEN. A later
# re-measurement is a new spec version, never a silent edit.
GAP_P99_BP: float | None = 175.1        # |weekend gap| p99, n=273 weekends 2021-07..2026-09
GAP_P95_BP: float | None = 91.5         # p95 (max seen 306.4 on 2026-01-30)
NEWS_JUMP_P95_BP: float | None = 158.3  # tier-1 1-minute |move| p95 -- n=14 ONLY, see below
LEVERAGE: int | None = 2000             # Exness-MT5Trial7, read from MT5 2026-09-29
STOP_OUT_PCT: float | None = 0.0        # margin_so_so = 0%: the broker liquidates only
MARGIN_CALL_PCT: float = 30.0           # when equity reaches zero. margin_so_call = 30%
                                        # is a warning, not a liquidation level.

# NEWS_JUMP_P95_BP rests on 14 tier-1 releases of tick history (Jun-Sep 2026):
# median 89.2, p95 158.3, max 177.5 bp. A p95 from n=14 is barely more than the
# maximum, so treat it as "wider than almost anything observed", re-measure as
# tick history accumulates, and note that the operational consequence is the
# same either way: an ordinary stop cannot survive a tier-1 minute.
CONTRACT = 100.0                       # oz per lot
LOT_STEP = 0.01

TIER1 = ("Nonfarm Payrolls", "CPI m/m", "Fed Interest Rate Decision",
         "Core PCE Price Index m/m")


def floor_lot(x):
    return math.floor(max(x, 0.0) / LOT_STEP + 1e-9) * LOT_STEP


# ---------------------------------------------------------------------- H2
def breaker_tripped(rv_so_far_bp2, bars_so_far, forecast_rv_bp2,
                    bars_per_week=BARS_PER_WEEK, k=BREAKER_K,
                    min_bars=BREAKER_MIN_BARS):
    """True when realised variance since the week's reopen is running at more
    than k times the forecast pace. Uses only bars already closed."""
    if bars_so_far < min_bars or not np.isfinite(forecast_rv_bp2) or forecast_rv_bp2 <= 0:
        return False
    expected = forecast_rv_bp2 * bars_so_far / bars_per_week
    return bool(rv_so_far_bp2 > k * expected)


def breaker_state(m_t, m_c, cut, now, forecast_rv_bp2):
    """Evaluate the breaker at wall-clock `now` inside the week starting at
    `cut`, from H1 closes only. Returns (tripped, rv_so_far, bars, pace)."""
    close_t = np.asarray(m_t) + 3600
    use = (close_t > cut) & (close_t <= min(now, cut + 7 * 86400))
    idx = np.flatnonzero(use)
    if len(idx) < 2:
        return False, 0.0, len(idx), np.nan
    lr = np.diff(np.log(np.asarray(m_c)[idx]))
    rv = float(np.nansum(lr * lr) * 1e8)
    n = len(idx)
    exp = forecast_rv_bp2 * n / BARS_PER_WEEK if np.isfinite(forecast_rv_bp2) else np.nan
    return (breaker_tripped(rv, n, forecast_rv_bp2), rv, n,
            rv / exp if np.isfinite(exp) and exp > 0 else np.nan)


# ---------------------------------------------------------------------- H3
def weekend_max_lots(risk_budget_usd, price, gap_bp=None):
    """Largest position that may be carried across a Friday cut: a p99 adverse
    weekend gap must cost no more than the per-trade risk budget."""
    g = GAP_P99_BP if gap_bp is None else gap_bp
    if g is None or price <= 0 or risk_budget_usd <= 0:
        return 0.0
    usd_per_lot = g / 1e4 * price * CONTRACT
    return floor_lot(risk_budget_usd / usd_per_lot)


def weekend_hold_allowed(forecast_class):
    """No position is carried over the weekend into a week forecast HIGH or
    EXTREME; the gap distribution there is the fat one."""
    return forecast_class not in ("HIGH", "EXTREME")


# ---------------------------------------------------------------------- H4
def news_hold_allowed(stop_distance_bp, jump_bp=None):
    """A position may be held through a tier-1 release only if its stop is
    farther than the p95 one-minute move; otherwise flatten before it."""
    j = NEWS_JUMP_P95_BP if jump_bp is None else jump_bp
    if j is None or not np.isfinite(stop_distance_bp):
        return False
    return bool(stop_distance_bp >= j)


def tier1_in_window(cal_events, t0, t1):
    """Names of tier-1 releases scheduled in [t0, t1)."""
    return [e for ep, e in cal_events if t0 <= ep < t1 and any(k in e for k in TIER1)]


# ---------------------------------------------------------------------- H6
def margin_required(lots, price, leverage=None):
    lev = LEVERAGE if leverage is None else leverage
    if lev is None or lev <= 0:
        return np.nan
    return lots * CONTRACT * price / lev


def margin_level_pct(equity, lots, price, leverage=None):
    m = margin_required(lots, price, leverage)
    if not np.isfinite(m) or m <= 0:
        return np.inf
    return equity / m * 100.0


def stopped_out(equity_at_worst, lots, price, leverage=None, so_pct=None):
    """True when the broker would have liquidated: margin level at the worst
    price inside the period falls to or below the stop-out level."""
    so = STOP_OUT_PCT if so_pct is None else so_pct
    if so is None:
        return equity_at_worst <= 0            # fall back to the old zero-equity rule
    return margin_level_pct(equity_at_worst, lots, price, leverage) <= so


def frozen() -> bool:
    """All measured constants present?"""
    return all(v is not None for v in (GAP_P99_BP, GAP_P95_BP, NEWS_JUMP_P95_BP,
                                       LEVERAGE, STOP_OUT_PCT))
