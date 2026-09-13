#!/usr/bin/env python3
"""Reproductions for the execution-engine defects raised in review.

Each case below is a MINIMAL, hand-built price path where the correct answer
is known before any code runs. A case that reproduces prints the wrong number
the engine currently returns alongside the right one. Nothing here is fixed by
this file - it exists so the fixes can be verified against a failing test
rather than against an argument.

Run:  python3 research/bug_reproductions.py
Exit code is non-zero while any defect still reproduces.
"""
import sys, pathlib
import numpy as np, pandas as pd

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import mega_search as M

found = []

def frame(rows, spread=0.0):
    o, h, l, c = map(np.array, zip(*rows))
    idx = pd.date_range("2020-01-01", periods=len(rows), freq="1h", tz="UTC")
    return pd.DataFrame({"open": o, "high": h, "low": l, "close": c,
                         "spread": np.full(len(rows), spread),
                         "volume": np.ones(len(rows))}, index=idx)

def report(tag, reproduced, detail):
    found.append((tag, reproduced))
    mark = "REPRODUCED" if reproduced else "not reproduced"
    print(f"  [{mark}] {tag}")
    for line in detail.splitlines():
        print(f"        {line}")

# ---------------------------------------------------------------- BUG 1 ---
def bug1_entry_gap_long():
    """A long signal whose ENTRY BAR opens far below the stop.

    Signal closes at 110 with the stop at 98 (the 20-bar low). The next bar -
    the entry bar - opens at 90, already 8 points BELOW the stop, and never
    trades above 92 afterwards. The only honest outcomes are to fill the exit
    at the opening price of 90 (a loss beyond 1R) or to skip the trade. The
    engine must not book an exit at 98, because 98 never occurs after entry."""
    print("\nBUG 1  entry bar gaps through the stop (long)")
    rows = [(100, 102, 98, 100)] * 30
    rows += [(100, 110, 98, 110)]        # bar 30: signal, close 110, 20-bar low 98
    rows += [(90, 92, 88, 89)]           # bar 31: ENTRY opens at 90, below stop 98
    rows += [(89, 91, 87, 88)] * 20
    m = frame(rows)
    P = M.prep(m)
    W = M.walk_rule(P, 20, 0.0, "range", np.zeros(P["N"]), 96)
    if W is None or len(W["i"]) == 0:
        report("bug1 long gap", False, "engine generated no trade (acceptable)"); return
    entry = float(W["entry"][0]); risk = float(W["risk"][0])
    R, _ = M.outcome(W, 2, 3)
    got = float(R[0])
    # correct: fill at the open, 90. R = (90 - 110_signal_ref...) - the engine
    # measures from the ENTRY, so (90 - 90)/12 = 0 at best, and any exit price
    # above the entry is impossible because the bar's high is 92.
    worst_possible_gain = (92.0 - entry) / risk
    bad = got > worst_possible_gain + 1e-9
    report("bug1 long gap", bad,
           f"entry={entry}  stop=98  risk={risk}\n"
           f"engine returned R={got:+.4f}\n"
           f"the entry bar's HIGH is 92, so the largest attainable R is "
           f"{worst_possible_gain:+.4f}\n"
           f"a larger number means the engine booked a price that never traded "
           f"after entry")

def bug1_entry_gap_short():
    """The mirror: a short whose entry bar opens far ABOVE its stop."""
    print("\nBUG 1b  entry bar gaps through the stop (short)")
    rows = [(100, 102, 98, 100)] * 30
    rows += [(100, 102, 90, 90)]         # bar 30: signal short, close 90 < low 98
    rows += [(110, 112, 108, 111)]       # bar 31: ENTRY opens 110, above stop 102
    rows += [(111, 113, 109, 112)] * 20
    m = frame(rows)
    P = M.prep(m)
    W = M.walk_rule(P, 20, 0.0, "range", np.zeros(P["N"]), 96)
    if W is None or len(W["i"]) == 0:
        report("bug1 short gap", False, "engine generated no trade (acceptable)"); return
    entry = float(W["entry"][0]); risk = float(W["risk"][0])
    R, _ = M.outcome(W, 2, 3)
    got = float(R[0])
    worst_possible_gain = (entry - 108.0) / risk    # short profits as price falls
    bad = got > worst_possible_gain + 1e-9
    report("bug1 short gap", bad,
           f"entry={entry}  stop=102  risk={risk}\n"
           f"engine returned R={got:+.4f}\n"
           f"the entry bar's LOW is 108, so the largest attainable R is "
           f"{worst_possible_gain:+.4f}")

# ---------------------------------------------------------------- BUG 2 ---
def bug2_control_expiry():
    """Strategy and control must expire on the SAME bar.

    The strategy records its hold-H exit as the close of bar e+H-1 (its `step`
    counter starts at 1 on the entry bar). The control prices its time exit at
    c[e+H]. That is one bar of free information, in whichever direction the
    extra bar happens to move."""
    print("\nBUG 2  matched control expires one bar later than the strategy")
    src = pathlib.Path(__file__).parent / "mega_search.py"
    txt = src.read_text()
    strat = "if step == hh: c_at[hi] = c[k]"
    ctrl = "px = c[min(e + hold, N - 1)]"
    both = strat in txt and ctrl in txt
    detail = (f"strategy horizon line : {strat!r}\n"
              f"  step = k - e + 1, so step == H means k = e + H - 1\n"
              f"control horizon line  : {ctrl!r}\n"
              f"  prices the same horizon at bar e + H\n"
              f"difference: exactly one bar, every control trade")
    report("bug2 control off-by-one expiry", both, detail)

# ---------------------------------------------------------------- BUG 3 ---
def bug3_holdout_leak():
    """Changing data AFTER the discovery/holdout boundary must not change any
    discovery-period result. It currently does, three separate ways."""
    print("\nBUG 3  holdout leaks into discovery scoring")
    n = 4000
    m = M.synth(n, 5, 0.0012)
    cut = 3000
    P = M.prep(m)
    cost = P["spread"] + M.COMMISSION
    W = M.walk_rule(P, 20, 0.1, "atr2", cost, 1000)
    keep = W["i"] < cut
    Wd = {k: (v[..., keep] if k in ("t_tp", "p_tp", "c_at") else v[keep])
          for k, v in W.items()}
    R1, _ = M.outcome(Wd, 2, 5)          # hold=1000 straddles the boundary

    m2 = m.copy()
    tail = m2.index[cut:]
    rng = np.random.default_rng(9)
    bump = np.abs(rng.normal(0, 80, len(tail))) + 50      # push the tail far up
    for col in ("open", "high", "low", "close"):
        m2.loc[tail, col] = m2.loc[tail, col].to_numpy() + bump
    m2.loc[tail, "high"] = m2.loc[tail, ["open", "high", "low", "close"]].max(axis=1)
    m2.loc[tail, "low"] = m2.loc[tail, ["open", "high", "low", "close"]].min(axis=1)
    P2 = M.prep(m2); cost2 = P2["spread"] + M.COMMISSION
    W2 = M.walk_rule(P2, 20, 0.1, "atr2", cost2, 1000)
    keep2 = W2["i"] < cut
    Wd2 = {k: (v[..., keep2] if k in ("t_tp", "p_tp", "c_at") else v[keep2])
           for k, v in W2.items()}
    R2, _ = M.outcome(Wd2, 2, 5)
    nn = min(len(R1), len(R2))
    changed = int((np.abs(R1[:nn] - R2[:nn]) > 1e-9).sum())
    report("bug3a discovery trades change when the holdout changes", changed > 0,
           f"{changed} of {nn} discovery trades changed R\n"
           f"mean R before {R1[:nn].mean():+.4f} -> after {R2[:nn].mean():+.4f}\n"
           f"cause: a trade signalled before the cut can hold past it")

    txt = (pathlib.Path(__file__).parent / "mega_search.py").read_text()
    leaks = []
    if "def med(x): return np.nanmedian(x[np.isfinite(x)])" in txt:
        leaks.append("build_filters medians (spread, volume, efficiency) are "
                     "computed over the WHOLE series, holdout included")
    if "pool = np.arange(ATR_N + 200, N - max(HOLDS) - 2)" in txt:
        leaks.append("matched_control draws its random bars from the WHOLE "
                     "series, so a discovery control trade can land in the holdout")
    report("bug3b thresholds and control sampling span the boundary",
           len(leaks) > 0, "\n".join(leaks) if leaks else "none found")

# ---------------------------------------------------------------- BUG 4 ---
def bug4_audit_centering():
    """metric_audit's fat-tail case subtracted each sample's OWN mean before
    measuring coverage, which removes exactly the tail-driven variation the
    test was meant to measure. Measured here both ways, against the production
    function."""
    print("\nBUG 4  the 0.5% false-positive figure was produced by a centred sample")
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
    diff = abs(out["not centred (correct)"] - out["centred (what the audit did)"])
    report("bug4 centring hid the true false-positive rate", diff > 0.02,
           "\n".join(f"{k:<32} {v:.2%}" for k, v in out.items()) +
           f"\nnominal is 5% - the centred figure understates it")

# ---------------------------------------------------------------- BUG 5 ---
def bug5_fwer():
    """sqrt(2 ln k) is the EXPECTED maximum of k noise draws, not a 5%
    family-wise threshold. Measured directly."""
    print("\nBUG 5  sqrt(2 ln k) is a heuristic, not a 5% family-wise bar")
    import math
    rng = np.random.default_rng(4)
    rows = []
    for k in (1000, 10000):
        bar = math.sqrt(2 * math.log(k))
        exceed = np.mean([np.abs(rng.normal(0, 1, k)).max() > bar for _ in range(400)])
        rows.append((k, bar, exceed))
    bad = any(e > 0.10 for _, _, e in rows)
    report("bug5 family-wise error at the noise bar is far above 5%", bad,
           "\n".join(f"k={k:>6}: bar {b:.2f}, at least one draw exceeds it "
                     f"{e:.1%} of the time" for k, b, e in rows))

def main():
    print("EXECUTION ENGINE - DEFECT REPRODUCTIONS")
    print("Every case is hand-built so the right answer is known in advance.")
    print("=" * 70)
    for fn in (bug1_entry_gap_long, bug1_entry_gap_short, bug2_control_expiry,
               bug3_holdout_leak, bug4_audit_centering, bug5_fwer):
        try:
            fn()
        except Exception as e:
            report(fn.__name__, True, f"raised {type(e).__name__}: {e}")
    print("\n" + "=" * 70)
    live = [t for t, r in found if r]
    print(f"{len(live)} of {len(found)} defects reproduce on the current engine")
    for t in live: print(f"  - {t}")
    sys.exit(1 if live else 0)

if __name__ == "__main__":
    main()
