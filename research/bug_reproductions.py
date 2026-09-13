#!/usr/bin/env python3
"""Reproductions for the execution-engine defects raised in review.

WHAT THIS FILE IS FOR, IN TWO PARTS

  PART 1 - ENGINE DEFECTS. Three defects were raised, reproduced here on
  hand-built paths whose correct answer is known before any code runs, and
  then fixed. This part now asserts they are GONE. If any of them comes back -
  a refactor that re-widens the entry-gap hole, a control that stops calling
  execute(), a filter that reads across the split - this file fails and the
  sweep's numbers are not to be trusted until it passes again.

    1. ENTRY GAP. A long whose entry bar opened at 90 with the stop at 98 was
       booked at +0.667R, an exit filled at a price that never traded after
       entry. The short mirror returned the same fabricated number.
    2. CONTROL EXPIRY. The strategy's hold-H exit was the close of bar e+H-1;
       the control's was c[e+H]. One free bar of information on every control
       trade, in whichever direction that bar happened to move.
    3. HOLDOUT LEAK. Discovery results moved when holdout data changed, three
       ways: trades straddling the boundary, filter medians fitted on the
       whole series, and a control that sampled the whole history.

  PART 2 - STANDING FACTS. Two of the seven items were never engine bugs that
  could be "fixed" - they are measurements about the statistics themselves,
  and they stay true. They are re-measured on every run so the numbers in the
  write-ups can be checked rather than believed, and they do NOT gate the exit
  code.

Run:  python3 research/bug_reproductions.py
Exit code is non-zero if any ENGINE DEFECT has returned.
"""
import sys, pathlib
import numpy as np, pandas as pd

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import mega_search as M
from exec_engine import execute, GAP_SKIP
from split_guard import Split

regressions = []

def frame(rows, spread=0.0):
    o, h, l, c = map(np.array, zip(*rows))
    idx = pd.date_range("2020-01-01", periods=len(rows), freq="1h", tz="UTC")
    return pd.DataFrame({"open": o, "high": h, "low": l, "close": c,
                         "spread": np.full(len(rows), spread, float),
                         "volume": np.ones(len(rows))}, index=idx)

def check(tag, fixed, detail):
    if not fixed: regressions.append(tag)
    print(f"  [{'FIXED' if fixed else '*** REGRESSED'}] {tag}")
    for line in detail.splitlines():
        print(f"        {line}")

def note(tag, detail):
    print(f"  [MEASURED] {tag}")
    for line in detail.splitlines():
        print(f"        {line}")

# =========================================================== PART 1 ========
# ---------------------------------------------------------------- BUG 1 ---
def bug1_entry_gap_long():
    """A long signal whose ENTRY BAR opens far below the stop.

    Signal closes at 110 with the stop at 98 (the 20-bar low). The next bar -
    the entry bar - opens at 90, already 8 points BELOW the stop, and never
    trades above 92 afterwards. The only honest outcomes are to fill at the
    opening price of 90 (a loss beyond 1R) or to skip the trade. Booking an
    exit at 98 is fiction: 98 never occurs after entry."""
    print("\nBUG 1  entry bar gaps through the stop (long)")
    rows = [(100, 102, 98, 100)] * 30
    rows += [(100, 110, 98, 110)]        # bar 30: signal, close 110, 20-bar low 98
    rows += [(90, 92, 88, 89)]           # bar 31: ENTRY opens at 90, below stop 98
    rows += [(89, 91, 87, 88)] * 20
    P = M.prep(frame(rows))
    W = M.walk_rule(P, 20, 0.0, "range", np.zeros(P["N"]), 96)
    if W is None or 30 not in set(W["i"].tolist()):
        check("bug1 long gap", True, "no trade generated at bar 30 at all")
        return
    q = int(np.where(W["i"] == 30)[0][0])
    R, held, ok = M.outcome(W, 2, 3)
    entry, risk = float(W["entry"][q]), float(W["risk"][q])
    best = (92.0 - entry) / risk        # the entry bar's HIGH is 92
    skipped = bool(W["g_stop"][q]) and not ok[q]
    honest = skipped or (np.isfinite(R[q]) and R[q] <= best + 1e-9)
    check("bug1 long gap", honest,
          f"entry={entry}  stop={float(W['stop'][q])}  risk={risk}\n"
          f"the entry bar's HIGH is 92, so the largest attainable R is {best:+.4f}\n"
          f"engine now: g_stop={bool(W['g_stop'][q])}, trade kept={bool(ok[q])}, "
          f"R={R[q]}\n"
          f"(the old engine returned R=+0.6667 here by filling the exit at 98)")

def bug1_entry_gap_short():
    """The mirror: a short whose entry bar opens far ABOVE its stop."""
    print("\nBUG 1b  entry bar gaps through the stop (short)")
    rows = [(100, 102, 98, 100)] * 30
    rows += [(100, 102, 90, 90)]         # bar 30: signal short, close 90 below low
    rows += [(110, 112, 108, 111)]       # bar 31: ENTRY opens 110, above stop 102
    rows += [(111, 113, 109, 112)] * 20
    P = M.prep(frame(rows))
    W = M.walk_rule(P, 20, 0.0, "range", np.zeros(P["N"]), 96)
    if W is None or 30 not in set(W["i"].tolist()):
        check("bug1 short gap", True, "no trade generated at bar 30 at all")
        return
    q = int(np.where(W["i"] == 30)[0][0])
    R, held, ok = M.outcome(W, 2, 3)
    entry, risk = float(W["entry"][q]), float(W["risk"][q])
    best = (entry - 108.0) / risk       # a short profits as price falls; low is 108
    skipped = bool(W["g_stop"][q]) and not ok[q]
    honest = skipped or (np.isfinite(R[q]) and R[q] <= best + 1e-9)
    check("bug1 short gap", honest,
          f"entry={entry}  stop={float(W['stop'][q])}  risk={risk}\n"
          f"the entry bar's LOW is 108, so the largest attainable R is {best:+.4f}\n"
          f"engine now: g_stop={bool(W['g_stop'][q])}, trade kept={bool(ok[q])}, "
          f"R={R[q]}\n"
          f"(the old engine returned R=+0.6667 here by filling the exit at 102)")

# ---------------------------------------------------------------- BUG 2 ---
def bug2_control_expiry():
    """Strategy and control must expire on the SAME bar.

    Checked two ways: the old divergent code paths must be gone from the
    source, and - the check that actually matters - a control trade that
    reaches its horizon must be held for exactly the horizon, never one bar
    more, measured by running it."""
    print("\nBUG 2  matched control expires one bar later than the strategy")
    txt = (pathlib.Path(__file__).parent / "mega_search.py").read_text()
    old_ctrl = "px = c[min(e + hold, N - 1)]"
    gone = old_ctrl not in txt
    shares = "execute(" in txt.split("def matched_control")[1].split("\ndef ")[0]

    # a flat path: nothing ever reaches a stop or target, so every control
    # trade must exit on the clock, and the clock must be the strategy's
    rng = np.random.default_rng(5)
    n = 900
    px = 2000 + np.cumsum(rng.normal(0, 0.5, n))
    m = frame(list(zip(px, px + 0.4, px - 0.4, px + rng.normal(0, 0.2, n))),
              spread=0.3)
    P = M.prep(m)
    split = Split(P["idx"], P["idx"][600])
    W = dict(i=np.arange(40, 240), d=np.where(np.arange(200) % 2 == 0, 1, -1).astype(float),
             risk=np.full(200, 30.0))
    HOLD_K = 1                                   # HOLDS[1] = 24
    ctrl, st = M.matched_control(P, W, 2, HOLD_K, split, "discovery", reps=2)
    hold = M.HOLDS[HOLD_K]
    over = 0 if np.isnan(st["mean_held"]) else int(st["mean_held"] > hold)
    ok = gone and shares and not over
    check("bug2 control off-by-one expiry", ok,
          f"old divergent control line {old_ctrl!r} present in source: {not gone}\n"
          f"matched_control calls exec_engine.execute(): {shares}\n"
          f"measured: horizon {hold} bars, control mean held "
          f"{st['mean_held']:.2f} bars over {st['n']} trades - a control that "
          f"expired at e+H would average {hold + 1:.0f}\n"
          f"control long fraction {st['long_frac']:.2f} against a 0.50 strategy mix")

# ---------------------------------------------------------------- BUG 3 ---
def bug3_holdout_leak():
    """Changing data AFTER the boundary must not change any discovery result.

    Run through mega_search's own resolve(), so this tests the sweep as it
    actually runs rather than a stand-in for it."""
    print("\nBUG 3  holdout leaks into discovery scoring")
    n, cut = 4000, 3000
    m = M.synth(n, 5, 0.0012)

    def disc_scores(frame_in):
        P = M.prep(frame_in)
        split = Split(P["idx"], P["idx"][cut])
        th = M.fit_thresholds(P, split)
        cost = P["spread"] + M.COMMISSION
        W = M.walk_rule(P, 20, 0.1, "atr2", cost, max(M.HOLDS))
        # tp=None at hold=1000 ON PURPOSE. With a 2R target every trade on this
        # path resolves inside 68 bars, nothing straddles the boundary, and the
        # check passes while testing nothing - the same vacuity trap the
        # split-guard suite guards against with its unguarded control. Removing
        # the target is what produces trades that are still open at the line.
        R, held, keep, rep = M.resolve(W, None, 5, split, "discovery")
        F = M.build_filters(P, W, th)
        msk = keep & F["spread_tight"] & F["efficiency_high"]
        return W["i"][msk], R[msk], rep

    m2 = m.copy()
    tail = m2.index[cut:]
    rng = np.random.default_rng(9)
    bump = np.abs(rng.normal(0, 80, len(tail))) + 50      # push the tail far up
    for col in ("open", "high", "low", "close"):
        m2.loc[tail, col] = m2.loc[tail, col].to_numpy() + bump
    m2.loc[tail, "high"] = m2.loc[tail, ["open", "high", "low", "close"]].max(axis=1)
    m2.loc[tail, "low"] = m2.loc[tail, ["open", "high", "low", "close"]].min(axis=1)

    i1, R1, rep1 = disc_scores(m)
    i2, R2, rep2 = disc_scores(m2)
    same = len(R1) == len(R2) and np.array_equal(i1, i2) and \
           (len(R1) == 0 or np.abs(R1 - R2).max() == 0.0)
    md = 0.0 if len(R1) == len(R2) == 0 else (
        np.abs(R1 - R2).max() if len(R1) == len(R2) else float("inf"))
    check("bug3a discovery trades change when the holdout changes", same,
          f"hold=1000 no target, filters spread_tight+efficiency_high\n"
          f"n {len(R1)} vs {len(R2)}, max |dR| = {md:.3e}\n"
          f"purged: {rep1['straddling']} straddling, {rep1['gap_skipped']} "
          f"entry-gap skips")
    # the check above is worthless if nothing straddled: it would be asserting
    # that unaffected trades are unaffected
    check("bug3a is not vacuous - trades really did straddle the boundary",
          rep1["straddling"] > 0,
          f"{rep1['straddling']} trades were still open at the boundary and "
          f"were dropped from both sides. Had they been kept on the signal "
          f"index alone, as the old code did, each would have read up to 1000 "
          f"holdout bars to decide its own outcome.")

    leaks = []
    if "def med(x): return np.nanmedian(x[np.isfinite(x)])" in \
            (pathlib.Path(__file__).parent / "mega_search.py").read_text():
        leaks.append("build_filters still takes whole-series medians")
    if "pool = np.arange(ATR_N + 200, N - max(HOLDS) - 2)" in \
            (pathlib.Path(__file__).parent / "mega_search.py").read_text():
        leaks.append("matched_control still draws from the whole series")
    check("bug3b thresholds and control sampling span the boundary",
          not leaks,
          "\n".join(leaks) if leaks else
          "thresholds come from fit_thresholds(P, split) (discovery rows only)\n"
          "control draws from window_pool(split, side, ...) (one side only)")

# =========================================================== PART 2 ========
def fact_audit_centering():
    """metric_audit's fat-tail case subtracted each sample's OWN mean before
    measuring coverage, which removes exactly the tail-driven variation the
    test was meant to measure. The correct figure is the un-centred one."""
    print("\nFACT 1  the 0.5% false-positive figure came from a centred sample")
    rng = np.random.default_rng(3)
    n, trials, overlap = 600, 400, 20
    def draw(center):
        base = rng.normal(0, 1, n + overlap)
        smooth = np.array([base[k:k + overlap].mean() for k in range(n)])
        fat = np.where(rng.random(n) < 0.01, 99.0, -1.0)
        return smooth + fat - (fat.mean() if center else 0.0)
    out = {}
    for label, center in (("centred (what the audit did)", True),
                          ("not centred (correct)", False)):
        hits = 0
        for q in range(trials):
            R = draw(center)
            ci = M.block_bootstrap_ci(R, np.arange(n).astype(float),
                                      np.full(n, float(overlap)), reps=300, seed=q)
            if ci is not None and (ci[0] > 0 or ci[1] < 0): hits += 1
        out[label] = hits / trials
    note("centring hid the true false-positive rate",
         "\n".join(f"{k:<32} {v:.2%}" for k, v in out.items()) +
         "\nnominal is 5%; the centred figure understates it and is not usable")

def fact_fwer():
    """sqrt(2 ln k) is the EXPECTED maximum of k noise draws, not a 5%
    family-wise threshold. Measured directly, and reported as such by the
    sweep, which calls it a heuristic floor rather than a bar."""
    print("\nFACT 2  sqrt(2 ln k) is a heuristic, not a 5% family-wise bar")
    import math
    rng = np.random.default_rng(4)
    rows = []
    for k in (1000, 10000):
        bar = math.sqrt(2 * math.log(k))
        exceed = np.mean([np.abs(rng.normal(0, 1, k)).max() > bar for _ in range(400)])
        rows.append((k, bar, exceed))
    note("family-wise error at the noise floor is far above 5%",
         "\n".join(f"k={k:>6}: floor {b:.2f}, at least one draw exceeds it "
                   f"{e:.1%} of the time" for k, b, e in rows))

def main():
    print("EXECUTION ENGINE - DEFECT REPRODUCTIONS AND REGRESSION CHECKS")
    print("Every case is hand-built so the right answer is known in advance.")
    print("=" * 74)
    print("\nPART 1 - ENGINE DEFECTS (these must stay fixed)")
    for fn in (bug1_entry_gap_long, bug1_entry_gap_short, bug2_control_expiry,
               bug3_holdout_leak):
        try:
            fn()
        except Exception as e:
            import traceback; traceback.print_exc()
            check(fn.__name__, False, f"raised {type(e).__name__}: {e}")
    print("\n" + "-" * 74)
    print("PART 2 - STANDING FACTS (measured, not gating)")
    for fn in (fact_audit_centering, fact_fwer):
        fn()
    print("\n" + "=" * 74)
    if regressions:
        print(f"{len(regressions)} ENGINE DEFECT(S) HAVE RETURNED:")
        for t in regressions: print(f"  - {t}")
        sys.exit(1)
    print("all reproduced defects remain fixed")
    sys.exit(0)

if __name__ == "__main__":
    main()
