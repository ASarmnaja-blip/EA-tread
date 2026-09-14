#!/usr/bin/env python3
"""Tests for discovery/holdout separation, including the invariance test the
review asked for.

THE INVARIANCE THAT MATTERS
  Replace every bar after the boundary with different data. Every
  discovery-side number - signals, eligibility, filter decisions, R, and the
  aggregate score - must be BIT-IDENTICAL. Anything that moves was reading
  across the line.

  This is run twice: once against the guarded path (must pass) and once
  against the unguarded path (must FAIL, which is what proves the test can
  detect the leak rather than passing vacuously).

Run:  python3 research/test_split_guard.py
"""
import sys, pathlib
import numpy as np, pandas as pd

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from split_guard import Split, purge, Thresholds, window_pool
from exec_engine import execute, plan_from_signal, GAP_SKIP
import mega_search as M

fails = []
def ck(name, cond, detail=""):
    print(f"  [{'PASS' if cond else '*** FAIL'}] {name}")
    if detail: print(f"          {detail}")
    if not cond: fails.append(name)

# ---------------------------------------------------------------------------
print("\nGROUP 1  straddling trades are purged")

idx = pd.date_range("2020-01-01", periods=1000, freq="1h", tz="UTC")
split = Split(idx, idx[600])
ck("split places the boundary where asked",
   split.n_disc == 600, f"{split!r}")

# three trades: wholly inside, straddling, wholly outside
sig = np.array([100, 590, 700])
exi = np.array([200, 650, 800])       # trade 2 starts at 590, ends at 650 > 600
keep_d, rep_d = purge(sig, exi, split, "discovery")
ck("a trade signalled in discovery but exiting in the holdout is dropped",
   list(keep_d) == [True, False, False] and rep_d["straddling"] == 1,
   f"keep={list(keep_d)}, report={rep_d}")
keep_h, rep_h = purge(sig, exi, split, "holdout")
ck("the holdout keeps only trades that begin and end inside it",
   list(keep_h) == [False, False, True], f"keep={list(keep_h)}")

# ---------------------------------------------------------------------------
print("\nGROUP 2  thresholds are fitted on discovery only and then frozen")

full = np.concatenate([np.full(600, 1.0), np.full(400, 99.0)])
th = Thresholds().fit({"spread": full}, split)
ck("a threshold fitted on discovery ignores holdout values entirely",
   abs(th["spread"] - 1.0) < 1e-12,
   f"median={th['spread']} (discovery is all 1.0, holdout all 99.0; "
   f"a whole-series median would be ~1.0 here only because of the count, so "
   f"the sharper check is below)")

# sharper: make the holdout dominate any whole-series statistic
full2 = np.concatenate([np.full(100, 1.0), np.full(900, 99.0)])
sp2 = Split(pd.date_range("2020-01-01", periods=1000, freq="1h", tz="UTC"),
            pd.Timestamp("2020-01-05 04:00", tz="UTC"))
th2 = Thresholds().fit({"spread": full2}, sp2)
whole = float(np.median(full2))
ck("the frozen threshold is the discovery median, not the whole-series one",
   abs(th2["spread"] - 1.0) < 1e-12 and abs(whole - 99.0) < 1e-12,
   f"discovery-only={th2['spread']}, whole-series={whole}")

try:
    Thresholds()["spread"]; raised = False
except RuntimeError:
    raised = True
ck("using a threshold before fitting raises rather than silently leaking",
   raised)

# ---------------------------------------------------------------------------
print("\nGROUP 3  control sampling stays on its own side")
pool_d = window_pool(split, "discovery", lo_pad=50, hi_pad=100)
pool_h = window_pool(split, "holdout", lo_pad=50, hi_pad=100)
ck("a discovery control can never draw a holdout bar",
   pool_d.max() < split.n_disc,
   f"discovery pool spans [{pool_d.min()}, {pool_d.max()}], boundary at "
   f"{split.n_disc}")
ck("a holdout control can never draw a discovery bar",
   pool_h.min() >= split.n_disc,
   f"holdout pool spans [{pool_h.min()}, {pool_h.max()}]")
ck("hi_pad leaves room for the holding period inside the same side",
   pool_d.max() + 100 <= split.n_disc,
   f"last drawable bar {pool_d.max()} + hold 100 = {pool_d.max()+100} "
   f"<= {split.n_disc}")

# ---------------------------------------------------------------------------
print("\nGROUP 4  INVARIANCE - change the future, the past must not move")

def build(seed, tail_shift=0.0, n=1400, cut=1000):
    """A deterministic path. tail_shift rewrites every bar after `cut`.

    Every random array is drawn in a FIXED order and at full length before the
    shift is applied, and every bar is built from its own draws only - no bar
    reads its neighbour. So bars 0..cut-1 are byte-for-byte the same in both
    versions, which is what makes the invariance test meaningful."""
    rng = np.random.default_rng(seed)
    step = rng.normal(0, 2.0, n)
    body = rng.normal(0, 1.5, n)
    wu = np.abs(rng.normal(0, 1.0, n))
    wd = np.abs(rng.normal(0, 1.0, n))
    bump = np.abs(rng.normal(0, 40.0, n))      # drawn always, used only past cut
    o = 2000 + np.cumsum(step)
    if tail_shift:
        o[cut:] = o[cut:] + tail_shift + bump[cut:]
    c = o + body
    h = np.maximum(o, c) + wu
    l = np.minimum(o, c) - wd
    idx = pd.date_range("2020-01-01", periods=n, freq="1h", tz="UTC")
    return pd.DataFrame({"open": o, "high": h, "low": l, "close": c,
                         "spread": np.full(n, 0.4), "volume": np.ones(n)},
                        index=idx)

CUT = 1000
def guarded_discovery_scores(m, hold):
    """The guarded path: fit thresholds on discovery, resolve with the shared
    engine, purge straddlers, score what is left."""
    P = M.prep(m)
    split = Split(m.index, m.index[CUT])
    cost = P["spread"] + 0.07
    th = Thresholds().fit({"spread": P["spread"], "vol": P["vol"]}, split)
    ph, pl = M.rolling_edges(P, 20)
    rows = []
    for i in range(30, P["N"] - 1):
        a = P["A"][i]
        if not np.isfinite(a) or a <= 0: continue
        d = 1 if P["c"][i] > ph[i] + 0.1 * a else (-1 if P["c"][i] < pl[i] - 0.1 * a else 0)
        if d == 0: continue
        pl_ = plan_from_signal(P["c"][i], a, ph[i], pl[i], d, "atr2", 0.1, 2.0,
                               cost=cost[min(i + 1, P["N"] - 1)])
        if pl_ is None: continue
        stop, risk, tgt = pl_
        # a filter that uses the FROZEN discovery threshold
        if P["spread"][i] > th["spread"]: continue
        t = execute(P["o"], P["h"], P["l"], P["c"], P["N"], i, d, stop, risk,
                    tgt, hold, cost)
        if t is None or t["reason"] == GAP_SKIP: continue
        rows.append((i, t["exit_bar"], t["R"]))
    if not rows: return np.array([]), np.array([]), None
    sig = np.array([r[0] for r in rows]); exi = np.array([r[1] for r in rows])
    R = np.array([r[2] for r in rows], float)
    keep, rep = purge(sig, exi, split, "discovery")
    return sig[keep], R[keep], rep

def unguarded_discovery_scores(m, hold):
    """The old path: whole-series threshold, filter on signal index only."""
    P = M.prep(m)
    cost = P["spread"] + 0.07
    whole_med = float(np.nanmedian(P["spread"]))       # LEAK 2
    ph, pl = M.rolling_edges(P, 20)
    rows = []
    for i in range(30, P["N"] - 1):
        a = P["A"][i]
        if not np.isfinite(a) or a <= 0: continue
        d = 1 if P["c"][i] > ph[i] + 0.1 * a else (-1 if P["c"][i] < pl[i] - 0.1 * a else 0)
        if d == 0: continue
        pl_ = plan_from_signal(P["c"][i], a, ph[i], pl[i], d, "atr2", 0.1, 2.0,
                               cost=cost[min(i + 1, P["N"] - 1)])
        if pl_ is None: continue
        stop, risk, tgt = pl_
        if P["spread"][i] > whole_med: continue
        t = execute(P["o"], P["h"], P["l"], P["c"], P["N"], i, d, stop, risk,
                    tgt, hold, cost)
        if t is None or t["reason"] == GAP_SKIP: continue
        rows.append((i, t["R"]))
    sig = np.array([r[0] for r in rows]); R = np.array([r[1] for r in rows], float)
    keep = sig < CUT                                    # LEAK 1
    return sig[keep], R[keep]

HOLD = 400     # long enough that many trades would straddle the boundary
base = build(7)
alt = build(7, tail_shift=300.0)
assert np.allclose(base.close.to_numpy()[:CUT], alt.close.to_numpy()[:CUT]), \
    "the two paths must be identical before the boundary"

s1, r1, rep1 = guarded_discovery_scores(base, HOLD)
s2, r2, rep2 = guarded_discovery_scores(alt, HOLD)
same_n = len(r1) == len(r2)
maxdiff = np.abs(r1 - r2).max() if same_n and len(r1) else (0.0 if len(r1) == len(r2) == 0 else np.inf)
ck("GUARDED: discovery results are bit-identical after the future is rewritten",
   same_n and maxdiff == 0.0,
   f"n={len(r1)} vs {len(r2)}, max |dR| = {maxdiff:.3e}, "
   f"purge report = {rep1}")

u1, ur1 = unguarded_discovery_scores(base, HOLD)
u2, ur2 = unguarded_discovery_scores(alt, HOLD)
nn = min(len(ur1), len(ur2))
u_changed = int((np.abs(ur1[:nn] - ur2[:nn]) > 1e-12).sum()) if nn else 0
u_meandiff = (ur1[:nn].mean() - ur2[:nn].mean()) if nn else 0.0
ck("UNGUARDED: the same test DETECTS the leak (must change, or the test is vacuous)",
   u_changed > 0,
   f"{u_changed} of {nn} discovery trades changed R; "
   f"mean R moved {ur1[:nn].mean():+.4f} -> {ur2[:nn].mean():+.4f} "
   f"({u_meandiff:+.4f})")

# the single-seed result above is one draw. Repeat it so neither the pass nor
# the leak is an accident of one path.
print("\nGROUP 5  the same invariance across many seeds")
g_bad, u_leaky, u_total_changed, seeds = [], 0, 0, range(101, 121)
for sd in seeds:
    b, a = build(sd), build(sd, tail_shift=300.0)
    gs1, gr1, _ = guarded_discovery_scores(b, HOLD)
    gs2, gr2, _ = guarded_discovery_scores(a, HOLD)
    if len(gr1) != len(gr2) or (len(gr1) and np.abs(gr1 - gr2).max() != 0.0):
        g_bad.append(sd)
    _, x1 = unguarded_discovery_scores(b, HOLD)
    _, x2 = unguarded_discovery_scores(a, HOLD)
    k = min(len(x1), len(x2))
    ch = int((np.abs(x1[:k] - x2[:k]) > 1e-12).sum()) if k else 0
    u_total_changed += ch
    if ch: u_leaky += 1
ck("GUARDED: bit-identical on every seed",
   not g_bad, f"{len(list(seeds))} seeds, {len(g_bad)} mismatches "
              f"{('at seeds ' + str(g_bad)) if g_bad else ''}")
ck("UNGUARDED: leaks on most seeds, so the guard is doing real work",
   u_leaky >= len(list(seeds)) // 2,
   f"{u_leaky} of {len(list(seeds))} seeds leaked, {u_total_changed} "
   f"discovery trades changed R in total")

print("\n" + "=" * 66)
if fails:
    print(f"{len(fails)} FAILED:")
    for f in fails: print(f"  - {f}")
    sys.exit(1)
print("all split-guard tests passed")
sys.exit(0)
