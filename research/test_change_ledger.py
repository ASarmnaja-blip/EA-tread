#!/usr/bin/env python3
"""Tests for the change ledger.

WHAT IS ACTUALLY BEING TESTED

  The ledger's arithmetic is trivial - a subtraction and a square root. What
  it has to get right is the ORDERING, and ordering bugs are silent: a ledger
  that quietly lets a criterion be edited after the result is in, or lets a
  failing test be re-run until it passes, produces a file that looks like
  discipline and records none. Those are the paths tested here.

  Each refusal below is tested by attempting the thing that must be refused
  and checking BOTH that the call fails AND that the file on disk is
  unchanged - a refusal that still writes is not a refusal.

Run:  python3 research/test_change_ledger.py
"""
import json, os, pathlib, subprocess, sys, tempfile

HERE = pathlib.Path(__file__).parent
LEDGER_PY = HERE / "change_ledger.py"

fails = []
def ck(name, cond, detail=""):
    print(f"  [{'PASS' if cond else '*** FAIL'}] {name}")
    if detail: print(f"          {detail}")
    if not cond: fails.append(name)

def run(path, *args):
    env = dict(os.environ, CHANGE_LEDGER=str(path))
    p = subprocess.run([sys.executable, str(LEDGER_PY), *args],
                       capture_output=True, text=True, env=env)
    return p.returncode, p.stdout + p.stderr

def register(path, ident, margin=0.02, sweep=1):
    return run(path, "register", "--id", ident,
               "--why", "a test",
               "--change", "a mechanically stated change",
               "--criterion", "beats baseline by the declared margin",
               "--min-improvement", str(margin),
               "--period", "holdout",
               "--sweep", str(sweep))

def record(path, ident, base, var, t):
    return run(path, "record", "--id", ident, "--baseline-er", str(base),
               "--variant-er", str(var), "--t-stat", str(t))

with tempfile.TemporaryDirectory() as td:
    L = pathlib.Path(td) / "ledger.json"

    # -----------------------------------------------------------------------
    print("\nGROUP 1  a result cannot be recorded before the change is declared")

    rc, out = record(L, "unregistered", 0.0, 0.5, 9.0)
    ck("recording an unregistered id fails", rc != 0)
    ck("and writes nothing at all", not L.exists(),
       "a refusal that still creates the file has already lost the ordering")

    # -----------------------------------------------------------------------
    print("\nGROUP 2  registration, and the criterion landing on disk")

    rc, out = register(L, "widen_stop", margin=0.02)
    ck("register succeeds", rc == 0)
    d = json.loads(L.read_text())
    ck("one entry on disk", len(d["entries"]) == 1)
    e = d["entries"][0]
    ck("the declared margin is stored, not recomputed later",
       e["min_improvement"] == 0.02)
    ck("the entry starts with no result", e["result"] is None)
    ck("registration reports the floor it must clear",
       "clear |t| >" in out)

    rc, out = register(L, "widen_stop")
    ck("a duplicate id is refused", rc != 0)
    ck("and the ledger is untouched",
       len(json.loads(L.read_text())["entries"]) == 1)

    # -----------------------------------------------------------------------
    print("\nGROUP 3  the three verdicts")

    # k is 1 here -> floor(2) = 1.177, so a t of 9 clears it easily
    rc, out = record(L, "widen_stop", 0.0100, 0.0500, 9.0)
    ck("record succeeds", rc == 0)
    v = json.loads(L.read_text())["entries"][0]["result"]
    ck("margin met and floor cleared -> ACCEPTED", v["verdict"] == "ACCEPTED",
       f"improvement {v['improvement']:+.4f}, floor {v['floor_at_test']:.2f}")
    ck("improvement is variant minus baseline",
       abs(v["improvement"] - 0.04) < 1e-12)

    register(L, "looks_better_is_noise")
    rc, out = record(L, "looks_better_is_noise", 0.0100, 0.0500, 0.4)
    v = [x for x in json.loads(L.read_text())["entries"]
         if x["id"] == "looks_better_is_noise"][0]["result"]
    ck("margin met but floor missed -> INCONCLUSIVE",
       v["verdict"] == "INCONCLUSIVE",
       "this is the verdict that stops a lucky variant becoming the setup")
    ck("and the report says the setup does not change",
       "does NOT change" in out)

    register(L, "no_better")
    rc, out = record(L, "no_better", 0.0100, 0.0110, 8.0)
    v = [x for x in json.loads(L.read_text())["entries"]
         if x["id"] == "no_better"][0]["result"]
    ck("margin missed -> REJECTED regardless of t", v["verdict"] == "REJECTED",
       "a large t on a change that did not beat its own margin is a "
       "precisely measured non-improvement")

    # -----------------------------------------------------------------------
    print("\nGROUP 4  a result is written once")

    before = L.read_text()
    rc, out = record(L, "widen_stop", 0.0100, 0.9000, 40.0)
    ck("re-recording an id that already has a result fails", rc != 0)
    ck("and the stored result is byte-identical", L.read_text() == before,
       "re-running until it passes is the failure mode this prevents")

    # -----------------------------------------------------------------------
    print("\nGROUP 5  the count rises, and a sweep counts as its own size")

    import importlib.util
    spec = importlib.util.spec_from_file_location("cl", LEDGER_PY)
    cl = importlib.util.module_from_spec(spec); spec.loader.exec_module(cl)
    os.environ["CHANGE_LEDGER"] = str(L)

    d = json.loads(L.read_text())
    ck("three registrations counted as three", cl.cumulative_k(d) == 3,
       f"k={cl.cumulative_k(d)} - the refused duplicate must NOT be counted, "
       f"since nothing was tested under it")

    register(L, "stop_multiplier_sweep", sweep=9)
    d = json.loads(L.read_text())
    ck("a sweep of 9 adds 9, not 1", cl.cumulative_k(d) == 12,
       f"k={cl.cumulative_k(d)} - 'try 9 values' is 9 hypotheses")

    f3, f12 = cl.floor_for(3), cl.floor_for(12)
    ck("the floor rises with the count", f12 > f3,
       f"{f3:.2f} -> {f12:.2f}")
    ck("the floor never falls when an entry is added",
       all(cl.floor_for(k) <= cl.floor_for(k + 1) for k in range(1, 200)))

    # -----------------------------------------------------------------------
    print("\nGROUP 6  the floor a test is judged against is the one at test time")

    v = [x for x in json.loads(L.read_text())["entries"]
         if x["id"] == "widen_stop"][0]["result"]
    ck("the k and floor in force at the test are stored with the result",
       v["k_at_test"] == 1 and abs(v["floor_at_test"] - cl.floor_for(1)) < 1e-12,
       f"k_at_test={v['k_at_test']} floor={v['floor_at_test']:.3f} - stored so "
       f"a later verdict cannot be re-derived under a different count")

    # -----------------------------------------------------------------------
    print("\nGROUP 7  status reads back what was written")

    rc, out = run(L, "status")
    ck("status succeeds", rc == 0)
    for want in ("ACCEPTED", "INCONCLUSIVE", "REJECTED", "untested"):
        ck(f"status shows {want}", want in out)
    ck("status prints the cumulative count",
       "cumulative hypotheses spent: 12" in out)
    ck("status prints what the count will cost after more changes",
       "floor after 100 more" in out,
       "the projection is there so the price of a long search is visible "
       "before it is paid, not after")

print("\n" + "=" * 70)
if fails:
    print(f"FAILED {len(fails)}: " + ", ".join(fails))
    sys.exit(1)
print("all ledger mechanics pass")
