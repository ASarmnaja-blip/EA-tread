"""Shared engine for the WPWB edge search (docs/WPWB_EDGE_SEARCH_PREREG.md).

H1 bars resampled from the canonical M5 snapshot; Bid prices; Demo90 costs;
P&L in basis points of entry price. Every approach consumes this module so
strategy and controls share one cost model.
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

PILOT = Path(__file__).resolve().parents[1] / "pilot"
sys.path.insert(0, str(PILOT))
import core  # noqa: E402
import mtf_engine as E  # noqa: E402
from weekly_evolution_grid import _week_boundary  # noqa: E402


def ep(y: int, m: int, d: int) -> int:
    return int(datetime(y, m, d, tzinfo=timezone.utc).timestamp())


DEV_START = ep(2021, 3, 5)
DEV_END = ep(2024, 1, 1)
HO_END = ep(2026, 9, 21)
WEEK = 7 * 86400
HOUR = 3600
SPREAD_FLOOR = E.SPREAD_FALLBACK
FEES = E.COMMISSION_RT + 2.0 * E.SLIP_PER_FILL
SWAP_LONG = E.SWAP_LONG
ROLL_S = E.ROLLOVER_H * HOUR


def rollover_nights_vec(t0: np.ndarray, t1: np.ndarray) -> np.ndarray:
    """Vectorised mtf_engine.rollover_nights: 21:00 UTC instants in [t0, t1]."""
    t0 = np.asarray(t0, np.int64)
    t1 = np.asarray(t1, np.int64)
    first = (t0 // 86400) * 86400 + ROLL_S
    first = np.where(first < t0, first + 86400, first)
    return np.where(first <= t1, (t1 - first) // 86400 + 1, 0)


class Market:
    """H1 view of a Bars object plus per-bar costs and calendar fields."""

    def __init__(self, b5):
        self.b5 = b5
        h1, _ = E.resample(b5, 12)
        self.t = h1.t.astype(np.int64)
        self.o, self.h, self.l, self.c = h1.o, h1.h, h1.l, h1.c
        n5 = len(b5)
        sp5 = (np.full(n5, SPREAD_FLOOR) if b5.sp is None
               else np.maximum(np.nan_to_num(b5.sp, nan=SPREAD_FLOOR), SPREAD_FLOOR))
        m5_first = np.searchsorted(b5.t, self.t)
        self.sp_in = sp5[m5_first]
        self.sp_out = sp5[np.minimum(m5_first + 11, n5 - 1)]
        self.atr = core.atr(h1, 14)
        self.day = self.t // 86400
        self.hour = (self.t % 86400) // HOUR
        self.wday = (self.day + 3) % 7          # 1970-01-01 was a Thursday; Mon=0
        cut = _week_boundary(int(self.t[0]))
        cuts = []
        while cut <= int(self.t[-1]) + WEEK:
            cuts.append(cut)
            cut += WEEK
        self.cuts = np.array(cuts, np.int64)

    # ---------------------------------------------------------------- weeks
    def week_bars(self, cut: int) -> tuple[int, int]:
        """[lo, hi) H1 indices of bars that start at/after cut and end by cut+WEEK."""
        lo = int(np.searchsorted(self.t, cut))
        hi = int(np.searchsorted(self.t, cut + WEEK - HOUR, side="right"))
        return lo, hi

    def last_bar_before(self, cut: int) -> int:
        """Index of the last H1 bar that ends at or before cut (-1 if none)."""
        return int(np.searchsorted(self.t, cut - HOUR, side="right")) - 1

    def exit_index(self, i: int, hold: int, hi: int) -> int:
        """Hold `hold` contiguous H1 bars from i, truncated at a gap or at hi."""
        k = i
        for _ in range(hold - 1):
            if k + 1 < hi and self.t[k + 1] - self.t[k] == HOUR:
                k += 1
            else:
                break
        return k

    # ---------------------------------------------------------------- P&L
    def pnl_bp(self, i_in, k_out, d, stress: float = 1.0) -> np.ndarray:
        """Net P&L in bp of entry price. Enter at open of bar i_in, exit at
        close of bar k_out. d=+1 long (buy Ask, sell Bid), d=-1 short (sell
        Bid, buy Ask). stress scales spread+commission+slippage, not swap."""
        i_in = np.asarray(i_in, np.int64)
        k_out = np.asarray(k_out, np.int64)
        d = np.asarray(d, np.int64)
        entry = self.o[i_in]
        exit_ = self.c[k_out]
        fees = FEES * stress
        long_p = exit_ - (entry + self.sp_in[i_in] * stress) - fees
        nights = rollover_nights_vec(self.t[i_in], self.t[k_out] + HOUR - 1)
        long_p = long_p - SWAP_LONG * nights
        short_p = entry - (exit_ + self.sp_out[k_out] * stress) - fees
        p = np.where(d > 0, long_p, short_p)
        return p / entry * 1e4

    # ---------------------------------------------------------------- regime
    def efficiency_at(self, cut: int, trading_days: int = 20) -> float:
        """Efficiency ratio of M5 closes over the last `trading_days` distinct
        UTC dates strictly before cut."""
        b5 = self.b5
        j = int(np.searchsorted(b5.t, cut))
        if j <= 1:
            return np.nan
        days = b5.t[:j] // 86400
        uniq = np.unique(days)
        if len(uniq) < trading_days:
            return np.nan
        start_day = uniq[-trading_days]
        s = int(np.searchsorted(b5.t, start_day * 86400))
        c = b5.c[s:j]
        path = np.abs(np.diff(c)).sum()
        return float(abs(c[-1] - c[0]) / path) if path > 0 else np.nan


def weighted_t(x: np.ndarray, w: np.ndarray) -> tuple[float, float]:
    """Decay-weighted mean and t-stat (effective-n standard error)."""
    if len(x) < 3 or w.sum() <= 0:
        return 0.0, 0.0
    sw = w.sum()
    m = float((w * x).sum() / sw)
    var = float((w * (x - m) ** 2).sum() / sw)
    n_eff = sw * sw / float((w * w).sum())
    if var <= 0 or n_eff <= 1:
        return m, 0.0
    return m, m / np.sqrt(var / n_eff)


def _cbb_p(x: np.ndarray, block: int, draws: int, seed: int) -> float:
    """One-sided p for mean > 0: centered circular block bootstrap."""
    n = len(x)
    rng = np.random.default_rng(seed)
    nb = int(np.ceil(n / block))
    starts = rng.integers(0, n, size=(draws, nb))
    idx = ((starts[:, :, None] + np.arange(block)) % n).reshape(draws, -1)[:, :n]
    dev = (x[idx].mean(axis=1) - x.mean()) * np.sqrt(n / (n - 1))
    return float((dev >= x.mean()).mean())


def _hac_p(x: np.ndarray, lags: int) -> float:
    """One-sided p for mean > 0: Newey-West (Bartlett) t, Student-t tail."""
    from scipy import stats
    n = len(x)
    d = x - x.mean()
    s = float((d * d).mean())
    for lag in range(1, lags + 1):
        s += 2 * (1 - lag / (lags + 1)) * float((d[lag:] * d[:-lag]).mean())
    t = x.mean() / np.sqrt(max(s, 1e-18) / n)
    return float(stats.t.sf(t, n - 1))


def block_boot(x: np.ndarray, block: int = 8, draws: int = 5000,
               seed: int = 12345) -> dict:
    """Conservative one-sided test that a weekly series has mean > 0.

    p = max(circular-block-bootstrap p, Newey-West p). Measured under
    AR(1) nulls (phi 0-0.5, n=140) both components alone are anti-
    conservative (~7-9% false-pass at nominal 5%); the max compared to a
    HALVED threshold restores true size to <=5%. See the prereg amendment.
    """
    x = np.asarray(x, float)
    n = len(x)
    if n < block * 2 or x.std() == 0:
        return dict(n=n, mean=float(x.mean()) if n else np.nan, p=np.nan,
                    t=np.nan, ac1=np.nan)
    p = max(_cbb_p(x, block, draws, seed), _hac_p(x, block))
    sd = x.std(ddof=1)
    ac1 = float(np.corrcoef(x[1:], x[:-1])[0, 1]) if n > 3 else np.nan
    return dict(n=n, mean=float(x.mean()), p=p,
                t=float(x.mean() / (sd / np.sqrt(n))), ac1=ac1)


DEV_P_MAX = 0.025          # halved from nominal 0.05 (calibration, amendment 1)


def holdout_p_max(k_finalists: int) -> float:
    return 0.025 / max(k_finalists, 1)
