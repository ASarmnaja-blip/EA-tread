"""Synthetic tests of the C2 event-driven portfolio (research/wrwr/portfolio.py, contract v5). Run directly; raises on
failure. Toy world: stop $10, entry price $4,000 (stop = 25 bp), contract 100 oz, flat mark price unless a test sets one."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import portfolio as PF  # noqa: E402

W = 7 * 86400
CUTS = np.arange(0, 6 * W, W, dtype=np.int64) + 1_000_000


def toy(sig, mark=None):
    """sig[c] = list of (entry offset from cut 0, duration, net R [, cost_bp [, dir]]). mark = (times, prices)."""
    n = len(sig)
    rows = []
    for s_ in sig:
        rr = []
        for r in s_:
            a_, d_, R_ = r[:3]
            rr.append((a_, d_, R_, r[3] if len(r) > 3 else 0.0, r[4] if len(r) > 4 else 1))
        rows.append(rr)
    et = [np.array([CUTS[0] + a_ for a_, *_ in s_], np.int64) for s_ in rows]
    xt = [np.array([CUTS[0] + a_ + d_ for a_, d_, *_ in s_], np.int64) for s_ in rows]
    R = [np.array([r[2] for r in s_], np.float32) for s_ in rows]
    cb = [np.array([r[3] for r in s_], np.float32) for s_ in rows]
    dr = [np.array([r[4] for r in s_], np.int8) for s_ in rows]
    gross = [(r.astype(float) * 25.0 + c).astype(np.float32) for r, c in zip(R, cb)]      # net R = (gross - cost) / 25 bp
    ptr = np.vstack([np.searchsorted(t, CUTS, side="right") for t in et]).astype(np.int32)
    mt, mc = (np.array([CUTS[0] - 10**6], np.int64), np.array([4000.0])) if mark is None else (np.asarray(mark[0], np.int64), np.asarray(mark[1], float))
    return PF.Pool([dict(hash=str(i)) for i in range(n)], et, xt, dr, gross, cb, [np.zeros(len(s), np.float32) for s in rows],
                   [np.full(len(s), 10.0, np.float32) for s in rows], [np.full(len(s), 4000.0, np.float32) for s in rows], R,
                   [np.full(len(s), 25.0, np.float32) for s in rows], ptr, CUTS, 100.0, np.arange(n), np.zeros(n, int),
                   np.array(["H1"] * n), mt, mc, {}, 0)


def run(P, champs, equity0=10_000.0, f=0.01):
    log, sk = [], []
    wr, eq, cnt = PF.simulate(P, champs, np.ones(len(CUTS)), f=f, equity0=equity0, log=log, skiplog=sk)
    return wr, eq, cnt, log, sk


def test_busy_and_order():
    P = toy([[(100, 5000, 1.0), (200, 100, 1.0), (5100, 100, -1.0)]])     # 2nd overlaps 1st; 3rd starts after 1st exits
    wr, eq, cnt, log, sk = run(P, [[0]] + [[]] * 5)
    assert cnt["skip_busy"] == 1 and cnt["entries"] == 2, cnt
    assert [s[3] for s in sk] == ["BUSY"], sk
    P = toy([[(100, 900, 1.0), (1000, 100, 1.0)]])                        # exit at t=1000 and entry at t=1000: exit first
    wr, eq, cnt, log, sk = run(P, [[0]] + [[]] * 5)
    assert cnt["entries"] == 2 and cnt["skip_busy"] == 0, cnt
    print("PASS C2 busy rule, exit-before-entry at the same timestamp, skip log rule ID")


def test_week_stop():
    # U = $100; lots shrink with equity: -150, -135, -135 -> realised -420 <= -3U after the 3rd, so the 4th/5th skip
    sig = [[(100, 10, -1.5), (200, 10, -1.5), (300, 10, -1.5), (400, 10, -1.5), (500, 10, 1.0)]]
    wr, eq, cnt, log, sk = run(toy(sig), [[0]] + [[]] * 5)
    assert cnt["entries"] == 3 and cnt["skip_weekstop"] == 2, (cnt, log)
    assert all(s[3] == "WEEKSTOP" and s[5] <= -300 for s in sk), sk          # state: realised week P&L at the skip
    print("PASS C2 weekly -3U entry stop; later signals skipped and logged with the causing state")


def test_min_lot_skip_not_busy():
    wr, eq, cnt, log, sk = run(toy([[(100, 50, 1.0), (200, 50, 1.0)]]), [[0]] + [[]] * 5, equity0=500.0)
    assert cnt["skip_minlot"] == 2 and cnt["entries"] == 0, cnt            # 1% of $500 = $5 < 0.01 lot x $10 x 100 oz
    wr, eq, cnt, log, sk = run(toy([[(100, 50, 1.0), (200, 50, 1.0)]]), [[0]] + [[]] * 5, equity0=20_000.0)
    assert cnt["entries"] == 2, cnt
    print("PASS C2 below 0.01 lot the signal is skipped with zero return and the candidate stays flat")


def test_handover_and_risk_cap():
    sig = [[(100, 3 * W, 2.0), (W + 200, 50, 1.0)], [(W + 100, 10, 1.0)], [(W + 150, 10, 1.0)]]
    wr, eq, cnt, log, sk = run(toy(sig), [[0], [1, 2], [], [], [], []])
    assert cnt["entries"] == 3, cnt                                          # cand 0's week-1 signal is ignored (not champion)
    assert len(log) == 3 and log[0][1] == 0 and log[0][3] == CUTS[0] + 100 + 3 * W
    wk = int(np.flatnonzero(np.abs(wr) > 0)[-1])
    assert wk == 3, wr                                                       # the handed-over trade exits in week 3
    print("PASS C2 handover: position kept to its own exit, former champion's new signals ignored")


def test_weekly_R_unit():
    wr, eq, cnt, log, sk = run(toy([[(100, 10, 2.0)]]), [[0]] + [[]] * 5)
    assert abs(wr[0] - 2.0) < 1e-9, wr                                        # 1% risk, +2R trade -> weekly R = 2
    print("PASS C2 weekly R = realised $ / U_k")


def test_mtm_equity_sizing():
    # cand 0: long $40,000 notional opened at cut 0 + 100 s (0.10 lot), held 3 weeks; price rises 4000 -> 4400 by cut 1.
    # cand 1 enters in week 1 while cand 0 is open: equity = 10,000 + 40,000 x 10% = 14,000 -> 0.14 lot (balance would give 0.10)
    mark = ([CUTS[0] + 10, CUTS[1] - 10], [4000.0, 4400.0])
    sig = [[(100, 3 * W, 2.0)], [(W + 100, 50, 1.0)]]
    wr, eq, cnt, log, sk = run(toy(sig, mark), [[0], [1], [], [], [], []])
    assert abs(log[0][4] - 0.10) < 1e-9 and abs(log[1][4] - 0.14) < 1e-9, [(l[1], l[4]) for l in log]
    assert abs(log[1][7] - 14_000.0) < 1e-6, log[1]                          # equity logged at the entry
    assert abs(eq[1] - 14_000.0) < 1e-6, eq                                   # equity at cut 1 = balance + unrealised
    print("PASS C2 equity = balance + mark-to-market: sizing and U_k use the open position's unrealised P&L")


def test_mtm_cost_and_short():
    # a long with 10 bp round-trip cost: its cost ($40) is charged to equity from entry on; a short loses when price rises
    mark = ([CUTS[0] + 10], [4000.0])
    wr, eq, cnt, log, sk = run(toy([[(100, 3 * W, 1.0, 10.0)], [(W + 100, 50, 1.0)]], mark), [[0], [1], [], [], [], []])
    assert abs(log[1][7] - 9_960.0) < 1e-6 and abs(log[1][4] - 0.09) < 1e-9, log
    mark = ([CUTS[0] + 10, CUTS[1] - 10], [4000.0, 4200.0])
    wr, eq, cnt, log, sk = run(toy([[(100, 3 * W, -1.0, 0.0, -1)], [(W + 100, 50, 1.0)]], mark), [[0], [1], [], [], [], []])
    assert abs(log[1][7] - (10_000.0 - 40_000.0 * 0.05)) < 1e-6, log         # short, price +5% -> -$2,000
    print("PASS C2 mark-to-market: entry cost charged immediately, shorts lose when the mark rises")


def test_risk_cap_and_margin():
    # f = 1%: every trade risks $100 (0.10 lot); the cap is 3 x f x equity = $300 of stop dollars across ALL open positions
    sig = [[(100, 3 * W, 1.0)], [(200, 3 * W, 1.0)], [(W + 100, 3 * W, 1.0)], [(W + 200, 3 * W, 1.0)]]
    wr, eq, cnt, log, sk = run(toy(sig), [[0, 1], [2, 3], [], [], [], []])
    assert cnt["entries"] == 3 and cnt["skip_riskcap"] == 1, cnt            # the 4th open position would hold $400 > $300
    assert sk[0][3] == "RISKCAP" and abs(sk[0][6] - 300.0) < 1e-6, sk        # logged state: $300 of open stop dollars
    # f = 20%: 2 lots = $8,000 of margin at 1:100 -> free margin test (>= 50% of equity) fails
    wr, eq, cnt, log, sk = run(toy([[(100, 50, 1.0)]]), [[0]] + [[]] * 5, f=0.20)
    assert cnt["entries"] == 0 and cnt["skip_margin"] == 1, cnt
    print("PASS C2 stop-dollar cap across open positions, free-margin test, both logged with state")


if __name__ == "__main__":
    for t in (test_busy_and_order, test_week_stop, test_min_lot_skip_not_busy, test_handover_and_risk_cap, test_weekly_R_unit,
              test_mtm_equity_sizing, test_mtm_cost_and_short, test_risk_cap_and_margin):
        t()
    print("ALL PORTFOLIO TESTS PASS")
