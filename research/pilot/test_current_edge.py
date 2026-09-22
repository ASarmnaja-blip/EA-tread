"""Focused checks for Amendment 19's tactical scanner."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import current_edge as CE
import data as D


def bars(highs, lows, opens=None, closes=None):
    n = len(highs)
    opens = np.asarray(opens if opens is not None else np.ones(n) * 100.0)
    closes = np.asarray(closes if closes is not None else opens)
    return D.Bars(np.arange(n) * 300 + 1_700_000_000, opens,
                  np.asarray(highs), np.asarray(lows), closes,
                  np.ones(n), 300, "TEST", np.ones(n) * 0.09)


def test_ambiguous_bar_loses_both_directions():
    # Entry 100, risk 1.5.  The next bar spans 98..102, so both the FOLLOW
    # and independently resolved FLIP must hit their stop first.
    b5 = bars([100, 102] + [100] * 72, [100, 98] + [100] * 72)
    b15 = D.Bars([b5.t[0] - 900], [100], [100], [100], [100], [1],
                 900, "TEST")
    nxt = np.array([0])
    atr = np.array([1.0])
    profile = np.ones(24)
    follow = CE.evaluate_arm([(0, 1)], False, b15, b5, nxt, atr, profile, 73)
    flipped = CE.evaluate_arm([(0, 1)], True, b15, b5, nxt, atr, profile, 73)
    assert follow[0].gross == -1.0
    assert flipped[0].gross == -1.0


def test_ready_requires_recent_positive_windows_and_stress():
    now = 2_000_000_000
    rows = []
    for j in range(24):
        t = now - (29 - j) * 86400
        rows.append(CE.Outcome(t, 0.20, 0.12, 0.25, 1))
    h = CE.arm_health(rows, now)
    assert h["ready"]
    rows[-1] = CE.Outcome(rows[-1].t, -5.0, -5.1, -4.9, 1)
    h2 = CE.arm_health(rows, now)
    assert not h2["ready"]


def test_rollover_count_is_inclusive_of_crossing():
    day = 1_700_000_000 - (1_700_000_000 % 86400)
    before = day + 20 * 3600 + 59 * 60
    after = day + 21 * 3600 + 1
    assert CE._nights(before, after) == 1
    assert CE._nights(before, day + 20 * 3600 + 59 * 60 + 30) == 0


def main():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in tests:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"{len(tests)}/{len(tests)} checks passed")


if __name__ == "__main__":
    main()
