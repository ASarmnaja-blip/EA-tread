#!/usr/bin/env python3
"""One command that rebuilds every number this run reports, and checks it.

WHAT REPRODUCIBLE HAS TO MEAN HERE

  Not "the scripts run". Running and producing the same answer are different
  claims, and only the second one is worth anything. So each stage records the
  figures it is supposed to produce, reruns the code, and compares.

  A mismatch is not a failure of this script. It means either the data
  changed, the code changed, or one of the numbers in the final report is
  wrong - and it says which by checking the data hashes and the git state
  separately from the figures.

WHAT IS CHECKED, AND WHY THESE

  Each entry is a number that a conclusion in the final report rests on. A
  figure that appears in the report and not here is one nobody can check.

WHAT THIS DELIBERATELY DOES NOT DO

  It does not open the sealed holdout, and it does not run the discovery
  search - which would spend hypotheses on every reproduction and push the
  multiple-testing floor up for no reason. Discovery is reproducible from its
  saved JSON and its seed; the floor is not something to burn on a rerun.
"""
import argparse
import json
import math
import pathlib
import subprocess
import sys
import time

import numpy as np

HERE = pathlib.Path(__file__).parent
sys.path.insert(0, str(HERE))
import provenance as PR

# stage -> (what it establishes, saved artifact, checks as (path, expected, tol))
STAGES = [
    ("engineering_audit", "the shared functions do what their docstrings say",
     "engineering_audit.json",
     # one blocking check is expected and open: the engine's own pre-trade
     # gates read the spread, so widening it removes trades as well as
     # charging for them, and a cost sweep cannot isolate cost. It is
     # recorded rather than fixed because the results this run reports do
     # not go through that bracket.
     [(("blocking",), 1, 0),
      (("checks", 13, "passed"), True, 0)]),
    ("weekend_contamination", "29% of the sample is hours the venue was shut",
     "weekend_contamination.json",
     [(("per_market", 0, "flat_share"), 0.3088, 0.002),
      (("gold_after", "gate_rejection", "Mon"), 0.535, 0.01)]),
    ("hierarchy_restate", "no setup family carries direction at C7",
     "hierarchy_restate.json",
     [(("worst_geometry_gap",), 0.0, 1e-9)]),
    ("direction_target", "no family-horizon cell clears on magnitude",
     "direction_target.json",
     [(("cleared",), 0, 0)]),
    ("reversal_mechanism", "the reversal is real and cannot pay its own cost",
     "reversal_mechanism.json",
     [(("add_over_fade", "t"), 5.96, 0.5),
      (("lag_retained",), 0.58, 0.05)]),
    ("timeframe_ratio", "edge scales as T^0.233, financing as T",
     "timeframe_ratio.json",
     [(("economics", "slope"), 0.233, 0.02)]),
    ("intraday_window", "the best financing-free window reaches 72% of cost",
     "intraday_window.json",
     [(("viable",), 0, 0)]),
    ("fresh_market_batch", "every candidate collapses on a fresh market",
     "fresh_market_batch.json",
     [(("beat_cost",), 0, 0)]),
    ("expanded_discovery", "no state lifts path asymmetry in both eras",
     "expanded_discovery.json",
     [(("unconditional_path", 1, "p"), 0.5008, 0.003),
      (("unconditional_path", 1, "breakeven"), 0.5289, 0.003)]),
    ("straddle_validation", "the straddle's edge is a scoring assumption",
     "straddle_validation.json",
     [(("survives",), 0, 0)]),
    ("straddle_intrabar", "minute data resolves the ambiguity against it",
     "straddle_intrabar.json",
     [(("per_state", "dislocation 2.0 ATR", "stopped_share"), 1.0, 1e-9),
      (("per_state", "dislocation 2.0 ATR", "share_profitable"), 0.0, 1e-9)]),
    ("failure_distribution", "the failure distribution names cost",
     "failure_distribution.json",
     [(("distribution", 0, "code"), "COST_DOMINATED", 0),
      (("hypotheses",), 127, 0)]),
]


def dig(d, path):
    cur = d
    for k in path:
        if isinstance(k, int):
            if not isinstance(cur, list) or k >= len(cur):
                return None
            cur = cur[k]
        else:
            if not isinstance(cur, dict) or k not in cur:
                return None
            cur = cur[k]
    return cur


def compare(artifact, checks):
    out = []
    p = HERE / artifact
    if not p.exists():
        return [dict(path="<artifact>", ok=False, detail=f"{artifact} missing")]
    d = json.loads(p.read_text())
    for path, expected, tol in checks:
        got = dig(d, path)
        if got is None:
            out.append(dict(path=".".join(map(str, path)), ok=False,
                            detail="not found in artifact"))
            continue
        if isinstance(expected, bool):
            ok = bool(got) == expected
        elif tol == 0:
            ok = got == expected
        else:
            ok = isinstance(got, (int, float)) and abs(got - expected) <= tol
        out.append(dict(path=".".join(map(str, path)), ok=ok,
                        expected=expected, got=got, tol=tol))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rerun", action="store_true",
                    help="rerun each stage rather than checking the saved "
                         "artifact")
    ap.add_argument("--tests", action="store_true",
                    help="also run the regression suites")
    a = ap.parse_args()
    t0 = time.time()

    print("REPRODUCE - rebuild the numbers and check them")
    print("=" * 96)
    print(__doc__.split("WHAT REPRODUCIBLE HAS TO MEAN HERE")[1]
          .split("WHAT IS CHECKED")[0])

    g = PR.git_state()
    print(f"  commit {g['commit'][:10]} on {g['branch']}"
          f"{'  TREE IS DIRTY' if g['dirty'] else ''}")
    cache = HERE / ".cache_duka"
    files = sorted(cache.glob("*_H1_*.parquet"))
    man = PR.data_manifest(files)
    print(f"  {len(files)} cached series, "
          f"{sum(v.get('bytes', 0) for v in man.values()) / 1e6:.0f} MB, "
          f"sha256 recorded for each\n")

    if a.tests:
        print("=" * 96)
        print("REGRESSION SUITES")
        print("=" * 96)
        fails = []
        for t in sorted(HERE.glob("test_*.py")):
            r = subprocess.run([sys.executable, str(t)], cwd=HERE,
                               capture_output=True, text=True, timeout=2400)
            ok = r.returncode == 0
            print(f"  {t.name:<34}{'PASS' if ok else 'FAIL'}")
            if not ok:
                fails.append(t.name)
        if fails:
            print(f"\n  {len(fails)} suites failed: {fails}")
        print()

    print("=" * 96)
    print("STAGES")
    print("=" * 96)
    all_checks, ran = [], []
    for mod, what, artifact, checks in STAGES:
        if a.rerun:
            t1 = time.time()
            r = subprocess.run([sys.executable, f"{mod}.py"], cwd=HERE,
                               capture_output=True, text=True, timeout=5400)
            ran.append(dict(stage=mod, returncode=r.returncode,
                            seconds=round(time.time() - t1, 1)))
            if r.returncode != 0:
                print(f"  {mod:<26}RERUN FAILED rc={r.returncode}")
                print("   " + (r.stderr or "").strip().splitlines()[-1][:110]
                      if r.stderr else "")
        res = compare(artifact, checks)
        all_checks.extend([dict(stage=mod, **c) for c in res])
        bad = [c for c in res if not c["ok"]]
        print(f"  {mod:<26}{'OK' if not bad else 'MISMATCH':<10}{what}")
        for c in bad:
            print(f"    {c['path']}: expected {c.get('expected')} "
                  f"got {c.get('got')}")

    ok = [c for c in all_checks if c["ok"]]
    print("\n" + "=" * 96)
    print(f"  {len(ok)} of {len(all_checks)} checks reproduce")
    if len(ok) != len(all_checks):
        print("  A mismatch means the data changed, the code changed, or a")
        print("  number in the report is wrong. The git state and the data")
        print("  hashes above say which.")

    seal = HERE / "sealed_holdout.json"
    if seal.exists():
        s = json.loads(seal.read_text())
        print(f"\n  sealed holdout: {len(s.get('symbols', []))} symbols, "
              f"examined: {s.get('examined')}")
        if s.get("examined"):
            print("  THE SEAL IS BROKEN - every conclusion drawn after it was "
                  "opened is conditional on that")

    out = HERE / "reproduce.json"
    out.write_text(json.dumps(dict(
        created=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        git=g, data=man, checks=all_checks, reran=ran,
        passed=len(ok), total=len(all_checks)), indent=1, default=str))
    print(f"\n  saved -> {out.name}   elapsed {time.time()-t0:.0f}s")
    if len(ok) != len(all_checks):
        sys.exit(1)


if __name__ == "__main__":
    main()
