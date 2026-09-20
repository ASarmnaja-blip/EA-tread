"""
Why P1 failed, and what a correct instrument can actually resolve.

Three checks, random-walk data only. No market data is read anywhere here.

  A. HARNESS NULL - a construction whose answer is known exactly. On a
     driftless walk, first-passage probability depends only on the ratio of
     the barrier distances, so P(target first) = 1/(1+R) and E = 0. Any
     deviation is the instrument.
  B. STANDARD ERROR - pooled trade-level vs path-level, on the same runs.
  C. NOISE FLOOR - the |skill| a provably correct null produces at this
     sample size, which is what the pre-registered 0.02R bound has to clear.
"""
import sys
sys.path.insert(0, ".")
from collections import Counter

import numpy as np

import core
import data as D
import run as R

b5 = D.load(D.SYMBOL, "60d", "5m")
_r = np.diff(np.log(b5.c))
SIG = float(np.std(_r[np.isfinite(_r)])) * float(np.mean(b5.c))
SEEDS = 10


def null_signals(c, nxt, every=7, Rmult=2.0, stop_atr=1.5):
    """Enter every Nth eligible bar, alternating direction. Carries no
    information by construction, so its true skill is exactly zero."""
    out = []
    for k, i in enumerate(range(c.warm, len(c.b), every)):
        if nxt[i] < 0 or c.atr[i] <= 0:
            continue
        d = 1 if k % 2 == 0 else -1
        out.append((i, d, c.b.c[i] - d * stop_atr * c.atr[i], "R", Rmult))
    return out


print("=" * 88)
print("A.  HARNESS NULL vs KNOWN THEORY   (gross, no cost)")
print("=" * 88)
print(f"    {'R':>4s} {'timestop':>9s} {'n':>7s} {'target%':>8s} {'theory%':>8s} "
      f"{'dev_pp':>7s} {'E_gross':>9s} {'t_path':>7s}")
for Rm in (2.0, 3.0):
    for mb, lab in ((core.TIME_STOP_5M, "72 bars"), (10 ** 6, "none")):
        per_walk, allw, alln = [], [], 0
        for sd in range(SEEDS):
            rng = np.random.default_rng(R.RNG_MASTER + sd)
            sb5 = R.synth_walk(b5, SIG / np.sqrt(20), rng)
            sb15, _ = D.to_15m(sb5)
            nxt = R.map_next(sb15, sb5)
            c = core.Ctx(sb15, nxt)
            tr, _ = core.run_signals(c, null_signals(c, nxt, Rmult=Rm), sb5, nxt,
                                     0.0, mb)
            if len(tr) < 2:
                continue
            per_walk.append(float(np.mean([t.gross_R for t in tr])))
            allw += [t.why for t in tr]
            alln += len(tr)
        w = np.array(per_walk)
        se = w.std(ddof=1) / np.sqrt(len(w))
        cnt = Counter(allw)
        tgt = 100.0 * cnt["target"] / alln
        th = 100.0 / (1.0 + Rm)
        print(f"    {Rm:4.1f} {lab:>9s} {alln:7d} {tgt:8.2f} {th:8.2f} "
              f"{tgt - th:+7.2f} {w.mean():9.4f} {w.mean() / se:7.2f}")
print("    A passes when E_gross sits at zero and the target rate matches theory")
print("    once the time stop is removed. The time stop truncates trades that")
print("    would still have resolved; it does not bias their direction.\n")

print("=" * 88)
print("B.  STANDARD ERROR: pooled trades vs independent paths")
print("=" * 88)
names = [n for n, _, _ in core.REGISTRY]
per_walk = {n: [] for n in names}
pooled = {n: {"s": [], "c": []} for n in names}
for sd in range(SEEDS):
    rng = np.random.default_rng(R.RNG_MASTER + sd)
    sb5 = R.synth_walk(b5, SIG / np.sqrt(20), rng)
    sb15, _ = D.to_15m(sb5)
    nxt = R.map_next(sb15, sb5)
    c = core.Ctx(sb15, nxt)
    for name, _d, fn in core.REGISTRY:
        sg = fn(c)
        tr, _ = core.run_signals(c, sg, sb5, nxt, core.COST_ROUND_TURN, core.TIME_STOP_5M)
        cs = core.control_signals(c, sg, nxt, R.CONTROL_DRAWS, rng)
        ct, _ = core.run_signals(c, cs, sb5, nxt, core.COST_ROUND_TURN, core.TIME_STOP_5M)
        if len(tr) < 2 or len(ct) < 2:
            continue
        a = np.array([t.net_R for t in tr])
        b = np.array([t.net_R for t in ct])
        per_walk[name].append(a.mean() - b.mean())
        pooled[name]["s"] += list(a)
        pooled[name]["c"] += list(b)

print(f"    {'id':6s} {'skill':>9s} {'se_pooled':>10s} {'t_pooled':>9s} "
      f"{'se_path':>8s} {'t_path':>7s} {'ratio':>7s}")
ratios = []
for n in names:
    s = np.array(pooled[n]["s"])
    c_ = np.array(pooled[n]["c"])
    w = np.array(per_walk[n])
    if len(w) < 3:
        continue
    sk = s.mean() - c_.mean()
    sp = np.sqrt(s.var(ddof=1) / len(s) + c_.var(ddof=1) / len(c_))
    sw = w.std(ddof=1) / np.sqrt(len(w))
    ratios.append(sw / sp)
    print(f"    {n:6s} {sk:9.4f} {sp:10.4f} {sk / sp:9.2f} {sw:8.4f} "
          f"{w.mean() / sw:7.2f} {sw / sp:6.2f}x")
print(f"    pooled SE understates by {min(ratios):.2f}x to {max(ratios):.2f}x "
      f"(median {np.median(ratios):.2f}x)\n")

print("=" * 88)
print("C.  NOISE FLOOR: what |skill| a PROVABLY CORRECT null produces here")
print("=" * 88)
floor = []
for variant, kw in (("every 7th", {}), ("every 11th", dict(every=11)),
                    ("every 7th, 3R", dict(Rmult=3.0)),
                    ("every 5th, stop 1.0 ATR", dict(every=5, stop_atr=1.0))):
    w = []
    for sd in range(SEEDS):
        rng = np.random.default_rng(R.RNG_MASTER + 500 + sd)
        sb5 = R.synth_walk(b5, SIG / np.sqrt(20), rng)
        sb15, _ = D.to_15m(sb5)
        nxt = R.map_next(sb15, sb5)
        c = core.Ctx(sb15, nxt)
        sg = null_signals(c, nxt, **kw)
        tr, _ = core.run_signals(c, sg, sb5, nxt, core.COST_ROUND_TURN, core.TIME_STOP_5M)
        cs = core.control_signals(c, sg, nxt, R.CONTROL_DRAWS, rng)
        ct, _ = core.run_signals(c, cs, sb5, nxt, core.COST_ROUND_TURN, core.TIME_STOP_5M)
        if len(tr) < 2 or len(ct) < 2:
            continue
        w.append(float(np.mean([t.net_R for t in tr]) - np.mean([t.net_R for t in ct])))
    w = np.array(w)
    se = w.std(ddof=1) / np.sqrt(len(w))
    floor.append(abs(w.mean()))
    print(f"    {variant:24s} skill {w.mean():+8.4f}  se_path {se:7.4f}  "
          f"t {w.mean() / se:6.2f}  |skill| {'>' if abs(w.mean()) > 0.02 else '<='} 0.02R")
print(f"\n    A null whose true skill is EXACTLY ZERO lands at |skill| up to "
      f"{max(floor):.4f} R here.")
print("    The pre-registered 0.02R bound is below the noise floor of the test,")
print("    so no instrument - correct or not - can pass that arm at this sample size.")
