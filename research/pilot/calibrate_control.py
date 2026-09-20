"""
Amendment 01 calibration: A1-A6.

Runs the circular-shift control against four families of data whose true skill
is exactly zero, and reports the old random-entry control beside it on C1 so
the effect of the control definition is separable from everything else.

No market price is scored anywhere. Only the bar calendar and one volatility
scalar come from GC=F, as declared in the amendment.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import core
import data as D
import run as R
import synth

OUT = Path(__file__).resolve().parent / "results"
SHIFTS = 20
W_C1 = 800          # A1 + A2 (20 blocks of 40) + A6
W_OTHER = 250       # A3
W_C4 = 400          # A4
FPR_BLOCK = 40
FPR_BUDGET = 0.10
DROP_LIMIT = 0.35


# -------------------------------------------------- C4 reference-level nulls
def ref_null_extreme(c: core.Ctx):
    """Anchored on a rolling extreme, like S3, with nothing else attached."""
    out = []
    for i in range(c.warm, len(c.b)):
        if c.atr[i] <= 0 or not np.isfinite(c.hh20[i]) or not np.isfinite(c.ll20[i]):
            continue
        a = c.atr[i]
        if c.b.c[i] > c.hh20[i]:
            out.append((i, 1, c.b.c[i] - 1.5 * a, "R", 2.0))
        elif c.b.c[i] < c.ll20[i]:
            out.append((i, -1, c.b.c[i] + 1.5 * a, "R", 2.0))
    return out


def ref_null_moving(c: core.Ctx):
    """Anchored on a MOVING reference and targeting it, like S5."""
    out = []
    for i in range(c.warm, len(c.b)):
        a = c.atr[i]
        if a <= 0:
            continue
        if c.b.c[i] < c.ema50[i] - 1.5 * a:
            out.append((i, 1, c.b.c[i] - 1.2 * a, "PRICE", c.ema50[i]))
        elif c.b.c[i] > c.ema50[i] + 1.5 * a:
            out.append((i, -1, c.b.c[i] + 1.2 * a, "PRICE", c.ema50[i]))
    return out


C4 = [("N-EXT", ref_null_extreme), ("N-MOV", ref_null_moving)]


def one_walk(b5, sigma, rng, gen, configs, controls):
    sb5 = gen(b5, sigma, rng)
    sb15, _ = D.to_15m(sb5)
    nxt = R.map_next(sb15, sb5)
    c = core.Ctx(sb15, nxt)
    res = {}
    for name, fn in configs:
        sg = fn(c)
        tr, _, acc = core.run_signals(c, sg, sb5, nxt, core.COST_ROUND_TURN,
                                      core.TIME_STOP_5M)
        if len(tr) < 2:
            continue
        e_set = float(np.mean([t.net_R for t in tr]))
        row = {"n": len(tr)}
        if "shift" in controls:
            cs, st = core.circular_shift_control(c, acc, nxt, SHIFTS, rng)
            ct, _, _ = core.run_signals(c, cs, sb5, nxt, core.COST_ROUND_TURN,
                                        core.TIME_STOP_5M)
            if len(ct) >= 2:
                row["shift"] = e_set - float(np.mean([t.net_R for t in ct]))
                row["drop"] = core.drop_rate(st)
        if "random" in controls:
            cs2 = core.control_signals(c, acc, nxt, SHIFTS, rng)
            ct2, _, _ = core.run_signals(c, cs2, sb5, nxt, core.COST_ROUND_TURN,
                                         core.TIME_STOP_5M)
            if len(ct2) >= 2:
                row["random"] = e_set - float(np.mean([t.net_R for t in ct2]))
        res[name] = row
    return res


def sweep(b5, sigma, gen, configs, controls, walks, seed0, label):
    acc = {name: {"shift": [], "random": [], "drop": [], "n": []}
           for name, _ in configs}
    t0 = time.time()
    for w in range(walks):
        rng = np.random.default_rng(seed0 + w)
        for name, row in one_walk(b5, sigma, rng, gen, configs, controls).items():
            for k in ("shift", "random", "drop", "n"):
                if k in row:
                    acc[name][k].append(row[k])
        if (w + 1) % 50 == 0:
            print(f"    {label}: {w + 1}/{walks} walks  {time.time() - t0:.0f}s",
                  flush=True)
    return acc


def ci(x):
    a = np.asarray(x, dtype=float)
    if len(a) < 3:
        return float("nan"), float("nan"), float("nan"), float("nan")
    m = float(a.mean())
    se = float(a.std(ddof=1) / np.sqrt(len(a)))
    return m, se, m - 1.96 * se, m + 1.96 * se


def table(acc, key, title, limit_report=True):
    print(f"\n    {title}")
    print(f"    {'id':7s} {'walks':>6s} {'skill':>9s} {'se':>8s} {'95% CI':>21s}  verdict")
    print("    " + "-" * 64)
    bad, mags = [], []
    for name in acc:
        m, se, lo, hi = ci(acc[name][key])
        if not np.isfinite(m):
            print(f"    {name:7s} {len(acc[name][key]):6d}   too few walks")
            bad.append(name)
            continue
        contains0 = lo <= 0 <= hi
        mags.append(abs(m))
        if not contains0:
            bad.append(name)
        print(f"    {name:7s} {len(acc[name][key]):6d} {m:9.4f} {se:8.4f} "
              f"[{lo:9.4f},{hi:9.4f}]  {'ok' if contains0 else 'EXCLUDES 0'}")
    print("    " + "-" * 64)
    print(f"    {len(acc) - len(bad)}/{len(acc)} contain zero"
          + (f"   |skill| median {np.median(mags):.4f} max {max(mags):.4f}"
             if mags and limit_report else ""))
    return bad, mags


def main():
    OUT.mkdir(exist_ok=True)
    b5 = D.load(D.SYMBOL, "60d", "5m")
    _r = np.diff(np.log(b5.c))
    sigma = float(np.std(_r[np.isfinite(_r)])) * float(np.mean(b5.c))
    cfgs = [(n, f) for n, _d, f in core.REGISTRY]

    print("=" * 84)
    print("AMENDMENT 01 CALIBRATION - circular time-shift control")
    print(f"    offsets +/-{core.SHIFT_MIN_DAYS}..{core.SHIFT_MAX_DAYS} days, "
          f"{SHIFTS} shifts, whole days, wrapped")
    print(f"    synthetic sigma ${sigma:.3f} per 5m bar, real bar calendar")
    print("=" * 84)
    report = {}

    # ---- C1: both controls side by side -------------------------------
    print(f"\n[C1] driftless random walk, {W_C1} walks, BOTH controls")
    c1 = sweep(b5, sigma, synth.c1_random_walk, cfgs, ("shift", "random"),
               W_C1, 100000, "C1")
    bad_new, mags_new = table(c1, "shift", "A1  circular-shift control")
    bad_old, mags_old = table(c1, "random", "     random-entry control (the amended one)")

    drops = {n: float(np.mean(c1[n]["drop"])) for n in c1 if c1[n]["drop"]}
    worst = max(drops.values()) if drops else float("nan")
    print(f"\n    A5  control drop rate: median {np.median(list(drops.values())):.1%} "
          f"max {worst:.1%} (limit {DROP_LIMIT:.0%})  "
          f"{'PASS' if worst < DROP_LIMIT else 'FAIL'}")

    # ---- A2: false positive rate --------------------------------------
    nblocks = W_C1 // FPR_BLOCK
    tests = excl = 0
    for name in c1:
        x = np.asarray(c1[name]["shift"], dtype=float)
        for b in range(nblocks):
            blk = x[b * FPR_BLOCK:(b + 1) * FPR_BLOCK]
            if len(blk) < 3:
                continue
            m, se, lo, hi = ci(blk)
            tests += 1
            excl += not (lo <= 0 <= hi)
    fpr = excl / tests if tests else float("nan")
    print(f"    A2  false positives: {excl}/{tests} = {fpr:.3f} "
          f"(budget {FPR_BUDGET})  {'PASS' if fpr <= FPR_BUDGET else 'FAIL'}")

    # ---- C2 / C3 ------------------------------------------------------
    print(f"\n[C2] volatility clustering, {W_OTHER} walks")
    c2 = sweep(b5, sigma, synth.c2_vol_clustering, cfgs, ("shift",),
               W_OTHER, 200000, "C2")
    bad_c2, _ = table(c2, "shift", "A3a  GARCH volatility")

    print(f"\n[C3] clustering + extra missing bars, {W_OTHER} walks")
    c3 = sweep(b5, sigma, synth.c3_extra_holes, cfgs, ("shift",),
               W_OTHER, 300000, "C3")
    bad_c3, _ = table(c3, "shift", "A3b  extra holes")

    # ---- C4 -----------------------------------------------------------
    print(f"\n[C4] reference-level nulls, {W_C4} walks")
    c4 = sweep(b5, sigma, synth.c2_vol_clustering, C4, ("shift",),
               W_C4, 400000, "C4")
    bad_c4, _ = table(c4, "shift", "A4  reference-anchored nulls")

    allm = mags_new + [abs(ci(c2[n]['shift'])[0]) for n in c2 if len(c2[n]['shift']) > 2]
    print(f"\n    A6  noise floor: median |skill| {np.median(allm):.4f} R, "
          f"max {max(allm):.4f} R")

    ok = (not bad_new and not bad_c2 and not bad_c3 and not bad_c4
          and fpr <= FPR_BUDGET and worst < DROP_LIMIT)
    print("\n" + "=" * 84)
    print(f"A1 {'PASS' if not bad_new else 'FAIL ' + str(bad_new)}")
    print(f"A2 {'PASS' if fpr <= FPR_BUDGET else 'FAIL'}   "
          f"A3a {'PASS' if not bad_c2 else 'FAIL ' + str(bad_c2)}   "
          f"A3b {'PASS' if not bad_c3 else 'FAIL ' + str(bad_c3)}")
    print(f"A4 {'PASS' if not bad_c4 else 'FAIL ' + str(bad_c4)}   "
          f"A5 {'PASS' if worst < DROP_LIMIT else 'FAIL'}")
    print(f"\nCALIBRATION {'PASS - P1 may be re-run' if ok else 'FAIL - stop, market stays closed'}")
    print("=" * 84)

    report = dict(
        sigma=sigma, shifts=SHIFTS, walks=dict(c1=W_C1, c2=W_OTHER, c3=W_OTHER, c4=W_C4),
        a1_fail=bad_new, a2_fpr=fpr, a3a_fail=bad_c2, a3b_fail=bad_c3,
        a4_fail=bad_c4, a5_max_drop=worst, pass_all=bool(ok),
        c1_shift={n: ci(c1[n]["shift"]) for n in c1},
        c1_random={n: ci(c1[n]["random"]) for n in c1},
        c2={n: ci(c2[n]["shift"]) for n in c2},
        c3={n: ci(c3[n]["shift"]) for n in c3},
        c4={n: ci(c4[n]["shift"]) for n in c4},
        drops=drops)
    (OUT / "amendment01_calibration.json").write_text(
        json.dumps(report, indent=2, default=float))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
