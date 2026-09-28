"""Independent audit of the Round-3 P2-B feasibility inputs.

This script reads only the frozen local bar snapshots.  It does not call MT5,
run selector P, or calculate P/B'/d on the real procedure matrix.
"""
from __future__ import annotations

import math
import os
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
for p in ("research/wpwb_live", "research/wpwb_search"):
    sys.path.insert(0, str(ROOT / p))
import common as C  # noqa: E402
from run_live_hod import combined_bars  # noqa: E402


def returns(m: C.Market, lo: int, hold: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return start indices, valid-horizon mask and gross open-to-close bp."""
    idx = np.arange(lo, len(m.t) - hold + 1)
    end = idx + hold - 1
    contiguous = (m.t[end] - m.t[idx]) == (hold - 1) * C.HOUR
    r = np.full(len(m.t), np.nan)
    r[idx[contiguous]] = (m.c[end[contiguous]] - m.o[idx[contiguous]]) / m.o[idx[contiguous]] * 1e4
    return idx, contiguous, r


def previous_available_same_clock(m: C.Market, idx: np.ndarray, r: np.ndarray) -> np.ndarray:
    """Nearest earlier UTC date having a valid return at the same clock time."""
    by_clock: dict[int, list[int]] = {}
    out = np.full(len(idx), -1, int)
    for q, i in enumerate(idx):
        clock = int(m.t[i] % 86400)
        past = by_clock.setdefault(clock, [])
        if past:
            out[q] = past[-1]
        if np.isfinite(r[i]):
            past.append(int(i))
    return out


def ac1(x: np.ndarray) -> float:
    return float(np.corrcoef(x[:-1], x[1:])[0, 1]) if len(x) > 2 else np.nan


def main() -> int:
    os.chdir(ROOT)
    m = C.Market(combined_bars())
    rng = np.random.default_rng(1)
    end = int(m.t[-1])
    print("hold window control       n    mean_bp  sd_raw  sd_signed  ac1_raw")
    for weeks in (52, 26):
        lo = int(np.searchsorted(m.t, end - weeks * C.WEEK))
        for hold in (1, 4, 12):
            idx, ok, r = returns(m, lo, hold)
            exact = np.array([np.searchsorted(m.t, m.t[i] - 86400) for i in idx])
            exact_ok = ((exact < len(m.t)) & (m.t[np.minimum(exact, len(m.t) - 1)] == m.t[idx] - 86400))
            exact = np.where(exact_ok, exact, -1)
            prior = previous_available_same_clock(m, idx, r)
            for label, ctrl in (("minus24h", exact), ("prior_date", prior)):
                good = ok & (ctrl >= 0)
                good &= np.isfinite(r[idx]) & np.isfinite(r[np.maximum(ctrl, 0)])
                pair = r[idx[good]] - r[ctrl[good]]
                signed = pair * rng.choice((-1.0, 1.0), len(pair))
                print(f"{hold:4d} {weeks:4d}w {label:10s} {len(pair):5d} "
                      f"{pair.mean():9.2f} {pair.std(ddof=0):7.1f} "
                      f"{signed.std(ddof=0):9.1f} {ac1(pair):8.3f}")

    # matched_once labels event_sd as the event residual SD, then multiplies
    # by a mean-one lognormal volatility factor.  Its unconditional SD is
    # therefore larger than the supplied value by sqrt(E[v^2]).
    draws = []
    for _ in range(10000):
        x = np.zeros(372)
        innovation = 0.35 * math.sqrt(1 - 0.81**2)
        for t in range(1, len(x)):
            x[t] = 0.81 * x[t - 1] + rng.normal(0, innovation)
        v = np.exp(x)
        v /= v.mean()
        draws.append(float(np.mean(v * v)))
    inflation = math.sqrt(float(np.mean(draws)))
    print(f"\nmatched_once unconditional event-SD inflation from log-vol: {inflation:.3f}x")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
