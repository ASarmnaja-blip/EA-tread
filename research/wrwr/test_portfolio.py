"""Synthetic tests of the C2 event-driven portfolio (research/wrwr/portfolio.py). Run directly; raises on failure."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import portfolio as PF  # noqa: E402

W = 7 * 86400
CUTS = np.arange(0, 6 * W, W, dtype=np.int64) + 1_000_000


def toy(sig):
    """sig[c] = list of (entry offset from cut 0, duration, R). stop 10 $, entry 4000 $, contract 100 oz."""
    n = len(sig)
    et = [np.array([CUTS[0] + a for a, _, _ in s], np.int64) for s in sig]
    xt = [np.array([CUTS[0] + a + d for a, d, _ in s], np.int64) for s in sig]
    R = [np.array([r for _, _, r in s], float) for s in sig]
    ptr = np.vstack([np.searchsorted(t, CUTS, side="right") for t in et]).astype(np.int32)
    return PF.Pool([dict(hash=str(i)) for i in range(n)], et, xt, R, [r - 0.1 for r in R],
                   [np.full(len(s), 10.0) for s in sig], [np.full(len(s), 4000.0) for s in sig], ptr, CUTS, 100.0,
                   np.arange(n), np.zeros(n, int))


def run(P, champs, equity0=10_000.0, f=0.01):
    log = []
    wr, eq, cnt = PF.simulate(P, champs, np.ones(len(CUTS)), f=f, equity0=equity0, log=log)
    return wr, eq, cnt, log


def test_busy_and_order():
    P = toy([[(100, 5000, 1.0), (200, 100, 1.0), (5100, 100, -1.0)]])     # 2nd overlaps 1st; 3rd starts after 1st exits
    wr, eq, cnt, log = run(P, [[0]] + [[]] * 5)
    assert cnt["skip_busy"] == 1 and cnt["entries"] == 2, cnt
    P = toy([[(100, 900, 1.0), (1000, 100, 1.0)]])                        # exit at t=1000 and entry at t=1000: exit first
    wr, eq, cnt, log = run(P, [[0]] + [[]] * 5)
    assert cnt["entries"] == 2 and cnt["skip_busy"] == 0, cnt
    print("PASS C2 busy rule and exit-before-entry at the same timestamp")


def test_week_stop():
    # U = $100; lots shrink with equity: -150, -135, -135 -> realised -420 <= -3U after the 3rd, so the 4th/5th skip
    sig = [[(100, 10, -1.5), (200, 10, -1.5), (300, 10, -1.5), (400, 10, -1.5), (500, 10, 1.0)]]
    wr, eq, cnt, log = run(toy(sig), [[0]] + [[]] * 5)
    assert cnt["entries"] == 3 and cnt["skip_weekstop"] == 2, (cnt, log)
    print("PASS C2 weekly -3U entry stop; later signals skipped, nothing force-closed")


def test_min_lot_skip_not_busy():
    wr, eq, cnt, log = run(toy([[(100, 50, 1.0), (200, 50, 1.0)]]), [[0]] + [[]] * 5, equity0=500.0)
    assert cnt["skip_minlot"] == 2 and cnt["entries"] == 0, cnt            # 1% of $500 = $5 < 0.01 lot x $10 x 100 oz
    wr, eq, cnt, log = run(toy([[(100, 50, 1.0), (200, 50, 1.0)]]), [[0]] + [[]] * 5, equity0=20_000.0)
    assert cnt["entries"] == 2, cnt
    print("PASS C2 below 0.01 lot the signal is skipped with zero return and the candidate stays flat")


def test_handover_and_risk_cap():
    # cand 0 champion in week 0 opens a 3-week trade; weeks 1.. champions 1 and 2; the old trade keeps counting risk
    sig = [[(100, 3 * W, 2.0), (W + 200, 50, 1.0)], [(W + 100, 10, 1.0)], [(W + 150, 10, 1.0)]]
    wr, eq, cnt, log = run(toy(sig), [[0], [1, 2], [], [], [], []])
    assert cnt["entries"] == 3, cnt                                          # cand 0's week-1 signal is ignored (not champion)
    assert len(log) == 3 and log[0][1] == 0 and log[0][3] == CUTS[0] + 100 + 3 * W
    wk = int(np.flatnonzero(np.abs(wr) > 0)[-1])
    assert wk == 3, wr                                                       # the handed-over trade exits in week 3
    print("PASS C2 handover: position kept to its own exit, former champion's new signals ignored")


def test_weekly_R_unit():
    wr, eq, cnt, log = run(toy([[(100, 10, 2.0)]]), [[0]] + [[]] * 5)
    assert abs(wr[0] - 2.0) < 1e-9, wr                                        # 1% risk, +2R trade -> weekly R = 2
    print("PASS C2 weekly R = realised $ / U_k")


if __name__ == "__main__":
    for t in (test_busy_and_order, test_week_stop, test_min_lot_skip_not_busy, test_handover_and_risk_cap, test_weekly_R_unit):
        t()
    print("ALL PORTFOLIO TESTS PASS")
