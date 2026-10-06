#!/usr/bin/env python3
"""Open the sealed universe. Once.

WHAT MAKES THIS TEST WORTH ANYTHING

  Not the statistics - they are the same block bootstrap used everywhere in
  this repo. What makes it worth something is that the fourteen crosses below
  have never been looked at, the finalists were fixed in a file before this
  script could run, and this script refuses to run twice.

  Those three facts are what let the result be judged at k = the number of
  finalists rather than at k = 824. Remove any one of them and the number
  this prints is worth exactly what a 825th backtest on gold is worth.

WHAT THIS SCRIPT ENFORCES, MECHANICALLY

  - every holdout file's sha256 must match the manifest written at sealing.
    A refetch, a reorder, or an edit between sealing and testing breaks the
    hash and stops the run.
  - rigorous_finalists.json must exist, must list the finalists, and must
    say holdout_opened: false. After a successful run it says true, and the
    next invocation refuses.
  - the finalists are read from that file. This script cannot choose, rank,
    or filter them, which is the point - by the time it runs, every decision
    that could be tuned has already been made and written down.

WHY THERE IS NO SECOND CHANCE

  If this comes back negative, the correct response is not to adjust a
  parameter and re-open. There is no third universe. Every liquid FX cross
  without a USD leg is in here; the next holdout would have to be a different
  asset class, a different decade, or live trading. That scarcity is the
  reason the protocol is this rigid.
"""
import hashlib
import json
import math
import pathlib
import sys
import time

import numpy as np
import pandas as pd

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import mega_search as M
import xauusd_1000_setups as X
from liquidity_sweep_crossmarket import block_se
from overfit_stats import (deflated_sharpe_from_returns, expected_max_t,
                           norm_ppf)

from rigorous_engine_stage import evaluate, rule_mask, signals, zero_cost

HERE = pathlib.Path(__file__).parent
CACHE = HERE / ".cache_duka"
MANIFEST = HERE / "sealed_holdout.json"
FINALISTS = HERE / "rigorous_finalists.json"
SEED = 17


def norm_ppf_two_sided(alpha):
    """|z| such that a two-sided test rejects at `alpha`."""
    return norm_ppf(1.0 - alpha / 2.0)


def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_cross(sym, entry):
    p = CACHE / entry["file"]
    if not p.exists():
        return None, "missing"
    if sha(p) != entry["sha256"]:
        return None, "HASH MISMATCH"
    d = pd.read_parquet(p)
    d = d[(d["ask_close"] - d["bid_close"]) > 0]
    for k in ("open", "high", "low", "close"):
        d[k] = (d[f"bid_{k}"] + d[f"ask_{k}"]) / 2
    d = d[(d.high >= d.low) & (d.close > 0)]
    d = d[(d.index.dayofweek < 5) |
          ((d.index.dayofweek == 5) & (d.index.hour == 0))]
    return d, "ok"


def main():
    t0 = time.time()
    print("SEALED HOLDOUT - OPENING")
    print("=" * 92)

    if not FINALISTS.exists():
        print("  rigorous_finalists.json missing. The engine stage has not run,")
        print("  so there is nothing fixed to test and the holdout stays sealed.")
        return 1
    fin = json.loads(FINALISTS.read_text())
    if fin.get("holdout_opened"):
        print("  This holdout has ALREADY BEEN OPENED, on "
              f"{fin.get('holdout_opened_at', 'an earlier run')}.")
        print("  It is not opened again. A second look would make the first")
        print("  one meaningless, and re-running until the answer changes is")
        print("  the exact failure this whole protocol exists to prevent.")
        return 1
    cands = fin.get("finalists") or []
    if not cands:
        print("  No finalists were nominated - nothing cleared the zero-cost")
        print("  gate on the discovery markets. The holdout stays sealed.")
        print("  That is the result: a search of "
              f"{fin.get('n_searched', '?'):,} rules produced nothing")
        print("  worth spending untouched data on.")
        return 0
    print(f"  finalists fixed at {fin['created']}: {len(cands)}")
    print(f"  criterion on file: {fin['criterion']}\n")

    man = json.loads(MANIFEST.read_text())
    frames = {}
    print("  verifying the seal:")
    for sym, entry in man["symbols"].items():
        d, why = load_cross(sym, entry)
        if d is None:
            print(f"    {sym:<8} {why}")
            if why == "HASH MISMATCH":
                print("\n  A holdout file does not match the hash recorded when")
                print("  it was sealed. It cannot be treated as untouched data.")
                print("  Stopping.")
                return 1
            continue
        frames[sym] = d
    print(f"    {len(frames)} of {len(man['symbols'])} verified, "
          f"{sum(len(d) for d in frames.values()):,} bars\n")
    if len(frames) < 8:
        print("  Too few verified markets to test on. Stopping.")
        return 1

    registered = expected_max_t(max(len(cands), 2))
    # AN ERROR IN THE REGISTERED CRITERION, CORRECTED BEFORE ANY DATA IS SEEN.
    # The ledger entry names "the expected maximum of three draws, about 1.02"
    # as the bar. That is the MEAN of the maximum under the null, not a
    # critical value - using it as a threshold would pass roughly half of all
    # null results. At large k the two are close enough that the repo's
    # sqrt(2 ln k) floor behaves like a threshold; at k=3 they are not.
    # The bar used here is therefore Bonferroni at alpha=0.05 two-sided over
    # the finalists, which is STRICTER than what was registered. Tightening a
    # pre-registered bar before the evidence exists cannot be self-serving;
    # loosening one after seeing it is the thing the ledger exists to stop.
    floor = float(norm_ppf_two_sided(0.05 / max(len(cands), 1)))
    print("=" * 92)
    print(f"  THE BAR: |t| > {floor:.2f}")
    print(f"  Bonferroni at 5% over {len(cands)} finalists. The criterion on file")
    print(f"  says {registered:.2f}, the expected MAXIMUM of {len(cands)} draws - that was")
    print(f"  a mis-specification: the mean of a maximum is not a critical")
    print(f"  value, and it would pass about half of all null results. The")
    print(f"  stricter number governs; the registered one is printed so the")
    print(f"  correction is visible rather than silent.")
    print(f"\n  Either way it is not 4.72. The {fin['n_searched']:,} rules searched were")
    print(f"  selected on data already spent, so they cost this test nothing.")
    print(f"  Only these {len(cands)} were ever charged against the sealed universe.")
    print("=" * 92)

    rows = []
    for i, c in enumerate(cands):
        names, d = c["rule"], c["direction"]
        per_free, per_real = {}, {}
        for sym, df in frames.items():
            rf = evaluate(df, names, d, 0.00001, free=True)
            rr = evaluate(df, names, d, 0.00001, free=False)
            if rf:
                per_free[sym] = rf
            if rr:
                per_real[sym] = rr
        if len(per_real) < 8:
            print(f"\n  {i+1}. {' & '.join(names)}  -  too few markets fired")
            continue
        Ef = np.array([v["E"] for v in per_free.values()])
        Er = np.array([v["E"] for v in per_real.values()])
        Sk = np.array([v.get("skill", np.nan) for v in per_real.values()])
        se = Er.std(ddof=1) / math.sqrt(len(Er))
        t = float(Er.mean() / se) if se > 0 else float("nan")
        rows.append(dict(rule=" & ".join(names),
                         direction="long" if d > 0 else "short",
                         markets=len(per_real),
                         n=int(sum(v["n"] for v in per_real.values())),
                         e_free=float(Ef.mean()), e_real=float(Er.mean()),
                         skill=float(np.nanmean(Sk)), t=t,
                         npos=int((Er > 0).sum()),
                         disc_e_free=c["e_free"], disc_e_real=c["e_real"]))
        print(f"\n  {i+1}. {' & '.join(names)}   ({rows[-1]['direction']})")
        print(f"     discovery:  E free {c['e_free']:+.4f}   "
              f"E real {c['e_real']:+.4f}   skill {c['skill']:+.4f}")
        print(f"     HOLDOUT:    E free {Ef.mean():+.4f}   "
              f"E real {Er.mean():+.4f}   skill {np.nanmean(Sk):+.4f}")
        print(f"     across-market t {t:+.2f}   positive on "
              f"{int((Er > 0).sum())} of {len(per_real)}   "
              f"n {int(sum(v['n'] for v in per_real.values())):,}")

    print("\n" + "=" * 92)
    print("VERDICT")
    print("=" * 92)
    passed = [r for r in rows if r["t"] > floor and r["e_real"] > 0]
    if passed:
        for r in passed:
            print(f"  CLEARS: {r['rule']}  t {r['t']:+.2f} > {floor:.2f}, "
                  f"E {r['e_real']:+.4f}")
        print(f"\n  This is the first thing in this project to clear its bar on")
        print(f"  data that was never searched. It is not a finished strategy -")
        print(f"  it is one result on one holdout, and the next step is forward")
        print(f"  evidence, not another backtest.")
    else:
        print(f"  Nothing clears. Of {len(rows)} finalists selected as the best")
        print(f"  of {fin['n_searched']:,} rules on nine markets, none reproduces on")
        print(f"  fourteen markets that were never searched.")
        signflip = [r for r in rows if r["disc_e_free"] > 0 and r["e_free"] < 0]
        if signflip:
            print(f"\n  {len(signflip)} of them flip sign at ZERO COST between")
            print(f"  discovery and holdout. That is not a cost problem or a")
            print(f"  venue problem - the directional information itself does")
            print(f"  not exist outside the sample it was found in.")

    fin["holdout_opened"] = True
    fin["holdout_opened_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    fin["holdout_markets"] = sorted(frames)
    fin["holdout_floor"] = floor
    fin["holdout_results"] = rows
    FINALISTS.write_text(json.dumps(fin, indent=1))
    man["examined"] = True
    man["examined_at"] = fin["holdout_opened_at"]
    MANIFEST.write_text(json.dumps(man, indent=1))
    pd.DataFrame(rows).to_csv(HERE / "holdout_test.csv", index=False)
    print(f"\n  The seal is now marked open. This script will refuse to run")
    print(f"  again, and these fourteen crosses are spent.")
    print(f"  elapsed {time.time()-t0:.0f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
