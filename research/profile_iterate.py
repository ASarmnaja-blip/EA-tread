#!/usr/bin/env python3
"""Measure, tune the instrument, measure again - and prove each round helped.

WHAT "TUNING" MEANS HERE, AND WHY IT IS NOT THE THING THAT KILLED EVERYTHING ELSE

  824 hypotheses died in this repo because searching a space of RULES and
  keeping the winner inflates whatever the winner shows. This loop searches a
  space of MEASUREMENT SETTINGS and keeps the winner, which sounds identical
  and is not.

  The difference is what the objective is made of. A rule search maximises a
  quantity that is also the claim - pick the rule with the best return, and
  the return you report is the maximum of N draws. This loop maximises
  coverage, interval tightness, and the share of cross-hour variance that
  survives sampling noise. None of those is a claim about the market. Raising
  the bootstrap count narrows an interval; it cannot move an estimate toward
  a preferred answer. Lengthening the volatility window changes what "typical
  range" means; it does not decide that 14:00 is cheap.

  The test of that distinction is built in: after tuning, ESTIMATE STABILITY
  is measured - how far the actual numbers moved across the whole search. If
  tuning were quietly selecting conclusions, the estimates would wander with
  the settings. If it is calibration, they hold still while the error bars
  shrink.

THE LOOP

  Each round does coordinate ascent on one knob at a time against the quality
  score, across every timeframe that has data, and writes the round's score,
  the knob it changed, and the estimates themselves to a log. A round that
  does not improve the score is recorded as such rather than quietly retried.
"""
import argparse
import itertools
import json
import pathlib
import sys
import time

import numpy as np
import pandas as pd

HERE = pathlib.Path(__file__).parent
sys.path.insert(0, str(HERE))
import market_profile as MP

LOG = HERE / "profile_iterations.json"

# What each knob is allowed to be. Every option is a legitimate measurement
# choice - none of them is "try until the answer changes".
GRID = dict(
    boot=[400, 800, 2000],
    atr_hours=[120, 240, 480, 960],
    bucket=[0.5, 1, 2],
    min_cell=[100, 200, 500],
    tail_q=[0.95, 0.99, 0.995],
    vap_bins=[20, 40, 80],
    vap_window=["1D", "1W"],
    vr_k=[2, 4, 8],
)


def run_all(tfs, syms):
    """One full measurement pass. Returns per-(tf,symbol) results."""
    out = {}
    for tf in tfs:
        for s in syms:
            try:
                r = MP.profile(s, tf)
            except Exception as e:
                r = None
            if r is not None:
                out[(tf, s)] = r
    return out


def aggregate_quality(res):
    """One number for the whole pass, and the pieces behind it."""
    if not res:
        return dict(score=0.0, coverage=0.0, precision=0.0, resolution=0.0,
                    cells=0, panels=0)
    q = [r["quality"] for r in res.values()]
    cells = int(sum(len(r["hours"]) for r in res.values()))
    return dict(
        score=float(np.mean([x["score"] for x in q])),
        coverage=float(np.mean([x["coverage"] for x in q])),
        precision=float(np.mean([x["precision"] for x in q])),
        resolution=float(np.mean([x["resolution"] for x in q])),
        cells=cells, panels=len(res))


def estimates(res):
    """The measurements themselves, keyed so two passes can be compared."""
    out = {}
    for (tf, s), r in res.items():
        for _, x in r["hours"].iterrows():
            out[f"{tf}|{s}|{x.hour}"] = float(x.cost_range)
    return out


def drift(a, b):
    """How far the ESTIMATES moved between two passes, in relative terms.

    This is the honesty check on the whole exercise. Tuning is supposed to
    sharpen the picture, not repaint it."""
    keys = set(a) & set(b)
    if not keys:
        return np.nan
    d = [abs(a[k] - b[k]) / max(abs(a[k]), 1e-9) for k in keys]
    return float(np.median(d))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rounds", type=int, default=10)
    ap.add_argument("--tfs", default="H1,H4,M15")
    ap.add_argument("--symbols", default="XAUUSD,EURUSD")
    a = ap.parse_args()
    tfs = [x.strip() for x in a.tfs.split(",") if x.strip()]
    syms = [x.strip() for x in a.symbols.split(",") if x.strip()]
    t0 = time.time()

    print("PROFILE ITERATION - tune the instrument, not the conclusion")
    print("=" * 96)
    print(__doc__.split("WHAT \"TUNING\" MEANS HERE")[1].split("THE LOOP")[0])
    print(f"  timeframes {tfs}   symbols {syms}   rounds {a.rounds}\n")

    log = []
    if LOG.exists():
        try:
            log = json.loads(LOG.read_text()).get("rounds", [])
        except Exception:
            log = []

    res0 = run_all(tfs, syms)
    q0 = aggregate_quality(res0)
    est0 = estimates(res0)
    print(f"  round 0 (baseline)  score {q0['score']:.4f}   "
          f"cov {q0['coverage']:.3f}  prec {q0['precision']:.3f}  "
          f"res {q0['resolution']:.3f}   {q0['panels']} panels, "
          f"{q0['cells']} cells   {time.time()-t0:.0f}s", flush=True)
    log.append(dict(round=0, params=dict(MP.PARAMS), **q0, changed=None,
                    drift_from_baseline=0.0))

    best_q = q0["score"]
    knobs = list(GRID)
    for rnd in range(1, a.rounds + 1):
        knob = knobs[(rnd - 1) % len(knobs)]
        cur = MP.PARAMS[knob]
        trials = []
        for v in GRID[knob]:
            if v == cur:
                continue
            MP.PARAMS[knob] = v
            r = run_all(tfs, syms)
            q = aggregate_quality(r)
            trials.append((q["score"], v, q, r))
            print(f"    round {rnd}: {knob}={v!r:<8} -> {q['score']:.4f}",
                  flush=True)
        MP.PARAMS[knob] = cur
        if not trials:
            continue
        trials.sort(key=lambda t: -t[0])
        top_score, top_v, top_q, top_r = trials[0]
        if top_score > best_q + 1e-6:
            MP.PARAMS[knob] = top_v
            best_q = top_score
            changed = f"{knob}: {cur!r} -> {top_v!r}"
            dr = drift(est0, estimates(top_r))
        else:
            changed = f"{knob}: kept {cur!r} (no option beat {best_q:.4f})"
            dr = drift(est0, estimates(top_r))
        print(f"  round {rnd}  score {best_q:.4f}   {changed}   "
              f"estimate drift from baseline {dr*100:.2f}%   "
              f"{time.time()-t0:.0f}s", flush=True)
        log.append(dict(round=rnd, params=dict(MP.PARAMS), score=best_q,
                        **{k: top_q[k] for k in
                           ("coverage", "precision", "resolution",
                            "cells", "panels")},
                        changed=changed, drift_from_baseline=dr))
        LOG.write_text(json.dumps(dict(
            updated=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            timeframes=tfs, symbols=syms, final_params=dict(MP.PARAMS),
            rounds=log), indent=1))

    print("\n" + "=" * 96)
    print("AFTER TUNING")
    print("=" * 96)
    print(f"  quality {q0['score']:.4f} -> {best_q:.4f}   "
          f"({(best_q/max(q0['score'],1e-9)-1)*100:+.1f}%)")
    final = run_all(tfs, syms)
    dr = drift(est0, estimates(final))
    print(f"  ESTIMATE DRIFT across the whole search: {dr*100:.2f}%")
    if dr < 0.10:
        print(f"  The numbers barely moved while the instrument was retuned,")
        print(f"  which is what calibration looks like. Had they wandered, the")
        print(f"  tuning would have been selecting conclusions and this loop")
        print(f"  would be the same mistake as the rule searches.")
    else:
        print(f"  The estimates moved by more than a tenth while only the")
        print(f"  measurement settings changed. That is a warning: the")
        print(f"  quantity being measured depends on how it is measured, and")
        print(f"  no conclusion drawn from it is safe yet.")
    print(f"\n  final params: {json.dumps(dict(MP.PARAMS))}")
    print(f"  log -> {LOG.name}   elapsed {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
