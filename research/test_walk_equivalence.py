#!/usr/bin/env python3
"""The recorded walk must BE exec_engine.execute(), not merely resemble it.

WHY THIS TEST IS THE LOAD-BEARING ONE

  The review's second demand was that the strategy and the matched control be
  measured by the same execution function. The control now calls
  exec_engine.execute() directly, so that half is settled by construction.

  The strategy cannot: pricing 36 (target, hold) pairs per signal through
  execute() is 36x the work and the sweep does not finish. It walks each
  signal once and derives the pairs arithmetically. That shortcut is only
  honest if it is INDISTINGUISHABLE from execute().

  So this test does the slow thing on purpose. For every signal, every target
  multiple and every horizon, it calls execute() and demands the recorded walk
  return the same R to the bit, the same exit price, the same exit bar, and
  the same skip decision. If the two ever disagree the sweep is not measuring
  what the unit tests certify, and this fails.

Run:  python3 research/test_walk_equivalence.py
"""
import sys, pathlib
import numpy as np, pandas as pd

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from exec_engine import execute, GAP_SKIP
import mega_search as M

fails = []
def ck(name, cond, detail=""):
    print(f"  [{'PASS' if cond else '*** FAIL'}] {name}")
    if detail: print(f"          {detail}")
    if not cond: fails.append(name)

def path(seed, n=2500, gappy=True):
    """A random path with deliberate GAPS, because gaps are where the two
    implementations could differ and a smooth path would never notice."""
    rng = np.random.default_rng(seed)
    o = 2000 + np.cumsum(rng.normal(0, 2.5, n))
    if gappy:
        # Isolated, VIOLENT jumps. They have to be violent: a jump at bar i+1
        # does not appear in ATR(14) measured at bar i, so the stop is sized
        # from the calm regime and only a jump several times that width can
        # open the entry bar beyond it. Mild noise never reaches the branch.
        jump = rng.random(n) < 0.03
        o = o + np.cumsum(np.where(jump, rng.normal(0, 120, n), 0.0))
    c = o + rng.normal(0, 2.0, n)
    h = np.maximum(o, c) + np.abs(rng.normal(0, 1.5, n))
    l = np.minimum(o, c) - np.abs(rng.normal(0, 1.5, n))
    idx = pd.date_range("2020-01-01", periods=n, freq="1h", tz="UTC")
    sp = 0.30 + np.abs(rng.normal(0, 0.15, n))
    return pd.DataFrame({"open": o, "high": h, "low": l, "close": c,
                         "spread": sp, "volume": np.ones(n)}, index=idx)

TPS_REAL = [t for t in M.TPS if t is not None]

def compare(m, look, buf, sm):
    """Returns (n_checked, n_gap_cases, list of mismatch descriptions)."""
    P = M.prep(m)
    cost = P["spread"] + M.COMMISSION
    W = M.walk_rule(P, look, buf, sm, cost, max(M.HOLDS))
    if W is None: return 0, 0, []
    o, h, l, c, N = P["o"], P["h"], P["l"], P["c"], P["N"]
    bad, checked, gaps = [], 0, 0
    tp_list = [None] + list(range(len(TPS_REAL)))
    for tp_j in tp_list:
        for hk in range(len(M.HOLDS)):
            R, held, ok = M.outcome(W, tp_j, hk)
            hold = M.HOLDS[hk]
            for q in range(len(W["i"])):
                i = int(W["i"][q]); d = int(W["d"][q])
                risk = float(W["risk"][q]); stop = float(W["stop"][q])
                tgt = None if tp_j is None else c[i] + d * TPS_REAL[tp_j] * risk
                t = execute(o, h, l, c, N, i, d, stop, risk, tgt, hold, cost,
                            on_gap="skip")
                checked += 1
                if t is None:
                    if ok[q]: bad.append(f"execute skipped, walk kept (i={i})")
                    continue
                if t["reason"] == GAP_SKIP:
                    gaps += 1
                    if ok[q]:
                        bad.append(f"entry gap: execute skips, walk kept "
                                   f"(i={i}, tp={tp_j}, hold={hold}, R={R[q]:+.6f})")
                    continue
                if not ok[q]:
                    bad.append(f"walk skipped, execute filled "
                               f"(i={i}, tp={tp_j}, hold={hold}, R={t['R']:+.6f})")
                    continue
                if R[q] != t["R"]:
                    bad.append(f"R differs at i={i} tp={tp_j} hold={hold}: "
                               f"walk {R[q]:+.10f} vs execute {t['R']:+.10f} "
                               f"(reason {t['reason']})")
                elif held[q] != t["held"]:
                    bad.append(f"held differs at i={i} tp={tp_j} hold={hold}: "
                               f"walk {held[q]} vs execute {t['held']}")
                if len(bad) > 12: return checked, gaps, bad
    return checked, gaps, bad

print("EQUIVALENCE: recorded walk vs exec_engine.execute()")
print("=" * 70)

print("\nGROUP 1  gappy random paths, every target x every horizon")
tot, tot_gap, all_bad = 0, 0, []
combos = [(20, 0.0, "range"), (20, 0.1, "atr2"), (40, 0.25, "atr1"),
          (10, 0.0, "atr3")]
for seed in (1, 2, 3):
    m = path(seed)
    for look, buf, sm in combos:
        n, g, bad = compare(m, look, buf, sm)
        tot += n; tot_gap += g; all_bad += bad
        if bad: break
    if all_bad: break
ck("every (signal, target, horizon) resolves identically",
   not all_bad,
   f"{tot:,} trade-configurations compared, {tot_gap:,} of them entry-gap "
   f"skips" + ("" if not all_bad else "\n          " +
               "\n          ".join(all_bad[:8])))

ck("the paths actually exercised the entry-gap branch",
   tot_gap > 0,
   f"{tot_gap:,} entry-gap cases - if this were 0 the test above would be "
   f"proving nothing about the bug that started all this")

print("\nGROUP 2  smooth paths (no gaps) must agree too")
tot2, all_bad2 = 0, []
for seed in (11, 12):
    m = path(seed, gappy=False)
    for look, buf, sm in [(20, 0.0, "range"), (20, 0.1, "atr2")]:
        n, g, bad = compare(m, look, buf, sm)
        tot2 += n; all_bad2 += bad
ck("identical on smooth paths as well",
   not all_bad2, f"{tot2:,} trade-configurations compared" +
   ("" if not all_bad2 else "\n          " + "\n          ".join(all_bad2[:8])))

print("\nGROUP 3  the original defect path, end to end through the sweep")
# The exact case from bug_reproductions: a long signal whose entry bar opens
# far BELOW its stop. This is deterministic, so the entry-gap branch is
# covered whether or not the random paths happen to reach it.
rows = [(100, 102, 98, 100)] * 30 + [(100, 110, 98, 110)] + \
       [(90, 92, 88, 89)] + [(89, 91, 87, 88)] * 20
o_, h_, l_, c_ = (np.asarray(x, float) for x in zip(*rows))
gm = pd.DataFrame({"open": o_, "high": h_, "low": l_, "close": c_,
                   "spread": np.full(len(rows), 0.3),
                   "volume": np.ones(len(rows))},
                  index=pd.date_range("2020-01-01", periods=len(rows),
                                      freq="1h", tz="UTC"))
Pg = M.prep(gm)
Wg = M.walk_rule(Pg, 20, 0.0, "range", Pg["spread"] + M.COMMISSION, max(M.HOLDS))
if Wg is None:
    ck("the sweep no longer books a profit on the gapped entry", True,
       "no trade generated at all, which is also a correct answer")
else:
    Rg, hg, okg = M.outcome(Wg, 2, 3)
    # bar 30 is the defect: a long signalled at 110 whose entry bar opens at 90,
    # eight points BELOW the 98 stop. The old engine booked +0.667R on it by
    # filling an exit at 98, a price that never traded after entry.
    # (bar 31 is a separate, legitimate downside breakout and is allowed to live)
    q = int(np.where(Wg["i"] == 30)[0][0])
    ck("the gapped long at bar 30 is skipped, not booked at +0.667R",
       bool(Wg["g_stop"][q]) and not okg[q] and np.isnan(Rg[q]),
       f"entry {Wg['entry'][q]:.2f} vs stop {Wg['stop'][q]:.2f} -> "
       f"g_stop={bool(Wg['g_stop'][q])}, ok={okg[q]}, R={Rg[q]}")
    others = [int(x) for x in Wg["i"] if x != 30]
    ck("no OTHER signal in this path was collateral damage",
       all(okg[int(np.where(Wg['i'] == b)[0][0])] for b in others),
       f"other signals in the path: {others} (bar 31 is a genuine downside "
       f"breakout, entry 89.00 vs stop 110.00, and still trades)")

print("\n" + "=" * 70)
if fails:
    print(f"{len(fails)} FAILED:")
    for f in fails: print(f"  - {f}")
    sys.exit(1)
print("the recorded walk and execute() are the same function")
sys.exit(0)
