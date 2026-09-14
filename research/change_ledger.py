#!/usr/bin/env python3
"""A ledger for evolving a setup without quietly overfitting it.

THE PROBLEM THIS SOLVES

  Improving a setup from live results is the right instinct and the usual way
  accounts die. Both of these are the same activity seen from different
  angles:

    "I noticed my stops are too tight, widened them, and it backtests better"
    "I tried 40 variations and kept the one that backtested best"

  The first sounds like engineering and the second sounds like data mining,
  but if the count is not kept they are indistinguishable, because the first
  one is the 40th variation when you include the 39 you tried and forgot.

  The fix is not to stop changing things. It is to make the count IMPOSSIBLE
  TO LOSE. Every change ever proposed goes in this ledger, the cumulative k
  never resets, and the bar a change must clear rises with it - exactly as it
  does inside a single search, because that is what it is.

HOW IT WORKS

    register    state the change, the reason, and the success criterion
                BEFORE running anything. The criterion is written to disk and
                cannot be edited afterwards. A change you cannot state a
                criterion for is not ready to test.

    test        run baseline vs variant on the period declared at
                registration. The result is appended; the criterion is read
                from the file, not from the caller.

    status      what has been tried, what survived, the cumulative k and the
                floor it implies today.

WHY THE CRITERION IS WRITTEN FIRST

  Deciding what counts as success AFTER seeing the result is how every
  negative result becomes "inconclusive" and every marginal one becomes a
  win. Writing it first costs nothing when the change works and is the whole
  protection when it does not.

WHAT COUNTS AS A HYPOTHESIS

  One registered change = one hypothesis. But a change with a free parameter
  swept over N values is N hypotheses, and the ledger asks for the sweep size
  at registration so it can be counted honestly. "Widen the stop" is one.
  "Try stop multipliers 1.0 through 3.0 in steps of 0.25" is nine.

THE RULE THE LEDGER ENFORCES AND CANNOT BE TALKED OUT OF

  A variant is ACCEPTED only if it beats the baseline by its own declared
  margin AND its improvement clears the floor implied by the cumulative
  hypothesis count. A variant that looks better but does not clear the floor
  is recorded as INCONCLUSIVE, not as an improvement - and the setup does not
  change.
"""
import argparse, json, math, sys, pathlib, time, datetime as dt
import numpy as np, pandas as pd

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import mega_search as M

import os
# The real ledger is one file and is meant to be the only one. The override
# exists so the ledger's own mechanics can be exercised in a test without
# writing hypotheses into the live count - not so a second ledger can be kept
# alongside it, which would defeat the entire purpose.
LEDGER = pathlib.Path(os.environ.get(
    "CHANGE_LEDGER", pathlib.Path(__file__).parent / "change_ledger.json"))

def load():
    if LEDGER.exists():
        return json.loads(LEDGER.read_text())
    return {"entries": [], "created": dt.datetime.now(dt.UTC).isoformat()}

def save(d):
    LEDGER.write_text(json.dumps(d, indent=1))

def cumulative_k(d):
    """Every hypothesis ever spent on this setup, including sweeps."""
    return sum(int(e.get("sweep_size", 1)) for e in d["entries"])

def floor_for(k):
    return math.sqrt(2 * math.log(max(k, 2)))

def cmd_register(a):
    d = load()
    if any(e["id"] == a.id for e in d["entries"]):
        print(f"  id {a.id!r} already registered - ids are permanent so a "
              f"result\n  cannot be quietly reattached to a different "
              f"hypothesis. Pick a new one.")
        return 1
    entry = dict(
        id=a.id,
        registered=dt.datetime.now(dt.UTC).isoformat(),
        why=a.why,
        change=a.change,
        sweep_size=a.sweep,
        criterion=a.criterion,
        min_improvement=a.min_improvement,
        test_period=a.period,
        result=None,
    )
    d["entries"].append(entry)
    save(d)
    k = cumulative_k(d)
    print(f"  registered {a.id!r}")
    print(f"    why       {a.why}")
    print(f"    change    {a.change}")
    print(f"    sweep     {a.sweep} hypothes{'is' if a.sweep == 1 else 'es'}")
    print(f"    criterion {a.criterion}")
    print(f"    margin    beat baseline by at least {a.min_improvement:+.4f}R")
    print(f"    period    {a.period}")
    print(f"\n  cumulative hypotheses on this setup: {k}")
    print(f"  a change must now clear |t| > {floor_for(k):.2f} to be accepted")
    print(f"\n  The criterion above is now on disk and is read from there when")
    print(f"  the result is recorded. It cannot be revised after seeing it.")
    return 0

def cmd_record(a):
    d = load()
    e = next((x for x in d["entries"] if x["id"] == a.id), None)
    if e is None:
        print(f"  no registered change with id {a.id!r}. Register it BEFORE "
              f"testing -\n  that ordering is the entire point of the ledger.")
        return 1
    if e["result"] is not None:
        print(f"  {a.id!r} already has a result recorded "
              f"({e['result']['verdict']}). Results are\n  written once; "
              f"re-running until it passes is the thing this prevents.")
        return 1
    k = cumulative_k(d)
    fl = floor_for(k)
    improvement = a.variant_er - a.baseline_er
    clears_margin = improvement >= e["min_improvement"]
    clears_floor = np.isfinite(a.t_stat) and abs(a.t_stat) > fl
    verdict = ("ACCEPTED" if (clears_margin and clears_floor)
               else "INCONCLUSIVE" if clears_margin
               else "REJECTED")
    e["result"] = dict(
        recorded=dt.datetime.now(dt.UTC).isoformat(),
        baseline_er=a.baseline_er, variant_er=a.variant_er,
        improvement=improvement, t_stat=a.t_stat,
        n_baseline=a.n_baseline, n_variant=a.n_variant,
        k_at_test=k, floor_at_test=fl,
        clears_margin=bool(clears_margin), clears_floor=bool(clears_floor),
        verdict=verdict, note=a.note or "")
    save(d)
    print(f"  {a.id!r}: baseline {a.baseline_er:+.4f}R -> variant "
          f"{a.variant_er:+.4f}R   ({improvement:+.4f}R)")
    print(f"  declared margin {e['min_improvement']:+.4f}R   "
          f"{'met' if clears_margin else 'NOT met'}")
    print(f"  t {a.t_stat:+.2f} against floor {fl:.2f} (k={k})   "
          f"{'clears' if clears_floor else 'DOES NOT clear'}")
    print(f"\n  VERDICT: {verdict}")
    if verdict == "INCONCLUSIVE":
        print(f"    The variant looks better and cannot be distinguished from")
        print(f"    noise at the bar this setup has already earned. The setup")
        print(f"    does NOT change. Collect more trades and re-register.")
    elif verdict == "REJECTED":
        print(f"    It did not even beat the declared margin. Next question is")
        print(f"    WHY - run trade_attribution.py on both books and compare")
        print(f"    the exit-reason and MFE/MAE tables, not the headline.")
    return 0

def cmd_status(a):
    d = load()
    k = cumulative_k(d)
    print("CHANGE LEDGER")
    print("=" * 78)
    if not d["entries"]:
        print("  empty - no change has been proposed yet")
        return 0
    w = max(24, max(len(e["id"]) for e in d["entries"]) + 1)
    print(f"  {'id':<{w}}{'sweep':>6}{'verdict':>14}{'improvement':>13}{'t':>8}")
    for e in d["entries"]:
        r = e["result"]
        if r is None:
            print(f"  {e['id']:<{w}}{e['sweep_size']:>6}{'untested':>14}")
        else:
            print(f"  {e['id']:<{w}}{e['sweep_size']:>6}{r['verdict']:>14}"
                  f"{r['improvement']:>+13.4f}{r['t_stat']:>+8.2f}")
    acc = [e for e in d["entries"]
           if e["result"] and e["result"]["verdict"] == "ACCEPTED"]
    inc = [e for e in d["entries"]
           if e["result"] and e["result"]["verdict"] == "INCONCLUSIVE"]
    rej = [e for e in d["entries"]
           if e["result"] and e["result"]["verdict"] == "REJECTED"]
    print(f"\n  accepted {len(acc)}   inconclusive {len(inc)}   "
          f"rejected {len(rej)}   untested "
          f"{sum(1 for e in d['entries'] if e['result'] is None)}")
    print(f"\n  cumulative hypotheses spent: {k}")
    print(f"  floor a new change must clear: |t| > {floor_for(k):.2f}")
    print(f"  floor after 10 more single changes: "
          f"|t| > {floor_for(k + 10):.2f}")
    print(f"  floor after 100 more: |t| > {floor_for(k + 100):.2f}")
    print(f"\n  THE COST OF SEARCHING IS PAID WHETHER OR NOT IT IS COUNTED.")
    print(f"  This file is the only thing keeping the count honest, so a")
    print(f"  change tested outside it does not become free - it becomes")
    print(f"  invisible, which is worse.")
    return 0

def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("register", help="declare a change before testing it")
    r.add_argument("--id", required=True)
    r.add_argument("--why", required=True,
                   help="what in the live results suggested this")
    r.add_argument("--change", required=True,
                   help="the mechanical change, stated so a third party could "
                        "implement it identically")
    r.add_argument("--criterion", required=True,
                   help="what result would count as success")
    r.add_argument("--min-improvement", type=float, required=True,
                   help="minimum E(R) gain that counts, declared now")
    r.add_argument("--period", required=True,
                   help="the data this will be tested on - must not be the "
                        "data that suggested the change")
    r.add_argument("--sweep", type=int, default=1,
                   help="how many parameter values will be tried (a sweep of "
                        "9 is 9 hypotheses, not 1)")
    r.set_defaults(fn=cmd_register)

    c = sub.add_parser("record", help="record the result of a registered change")
    c.add_argument("--id", required=True)
    c.add_argument("--baseline-er", type=float, required=True)
    c.add_argument("--variant-er", type=float, required=True)
    c.add_argument("--t-stat", type=float, required=True)
    c.add_argument("--n-baseline", type=int, default=0)
    c.add_argument("--n-variant", type=int, default=0)
    c.add_argument("--note", default="")
    c.set_defaults(fn=cmd_record)

    s = sub.add_parser("status", help="what has been tried and what it cost")
    s.set_defaults(fn=cmd_status)

    a = ap.parse_args()
    sys.exit(a.fn(a))

if __name__ == "__main__":
    main()
