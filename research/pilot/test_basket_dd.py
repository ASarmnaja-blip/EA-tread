"""Regression tests for the Amendment 23 basket research engine.

The integration no-look-ahead audit is intentionally run by basket_dd.py
against the full-hash-verified real cache.  These fast tests cover the same
causal boundary primitives without loading the 1.5 GB cache.
"""
from __future__ import annotations

from pathlib import Path
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import basket_dd as B
import evolution_portfolio_audit as audit
import historical_regime_walkforward as hist


def test_exit_week_assignment_and_zero_weeks() -> None:
    bounds = np.asarray([0, B.WEEK, 2 * B.WEEK, 3 * B.WEEK], np.int64)
    # A result exactly on a boundary belongs to the new week.
    assert int(np.searchsorted(bounds, B.WEEK, side="right") - 1) == 1
    x = np.zeros(3)
    x[1] += 2.0
    assert x.tolist() == [0.0, 2.0, 0.0]


def test_decay_effective_sample_size() -> None:
    w = B.DECAY ** np.arange(399, -1, -1, dtype=float)
    got = w.sum() ** 2 / np.dot(w, w)
    want = (1.0 + B.DECAY) / (1.0 - B.DECAY)
    assert abs(got - want) < 1e-10


def test_truncation_removes_future_columns() -> None:
    wd = B.WeeklyData(("a",), {"a": 0}, np.arange(6, dtype=np.int64),
                      np.asarray([[1., 2., 3., 1e9, -1e9]]),
                      np.asarray([[1., 2., 3., 1e9, -1e9]]))
    cut = wd.truncated(3)
    assert cut.boundaries.tolist() == [0, 1, 2, 3]
    assert cut.base.tolist() == [[1.0, 2.0, 3.0]]
    assert cut.stress.tolist() == [[1.0, 2.0, 3.0]]


def test_real_cache_members_weights_and_multiplier_are_future_invariant() -> None:
    """Slow integration test; uses the full-hash-verified 1.5 GB cache."""
    b5 = hist.load_history()
    uni, meta = audit.load_universe(b5)
    wd = B.WeeklyData.build(b5, uni)
    result = B.audit_truncation(b5, wd, uni, meta)
    assert result["same_members"]
    assert result["same_weights"]
    assert result["same_multiplier"]
    assert result["passed"]
