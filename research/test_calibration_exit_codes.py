#!/usr/bin/env python3
"""Prove the calibration harness's exit code, without paying for a real
10-minute-per-seed run.

calibrate_pipeline.py's exit code is the mechanism the review demanded
("calibration failure must exit non-zero"). It is worth proving directly
rather than trusting that the printed verdict and the process exit code
agree, because they are two different pieces of code (the print statements
and the sys.exit calls) and nothing enforces that they cannot drift apart.

This patches `one_seed`/`one_run` to return FABRICATED results - no backtest
runs at all - and drives main() through each branch:
  1. every seed reports 0 survivors           -> exit 0 (PASS)
  2. one seed reports a survivor              -> exit 1 (FAIL, false positive)
  3. one seed raises inside the worker        -> exit 1 (FAIL, crash)
  4. the generator-drift self-check fails     -> exit 2 (refuses to calibrate)

Run:  python3 research/test_calibration_exit_codes.py
"""
import sys, pathlib, io, contextlib
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).parent))

fails = []
def ck(name, cond, detail=""):
    print(f"  [{'PASS' if cond else '*** FAIL'}] {name}")
    if detail: print(f"          {detail}")
    if not cond: fails.append(name)

def run_main_with(fake_results, argv, drift_ok=True):
    """Run calibrate_pipeline.main() with one_seed patched to return
    `fake_results` in order (cycled if fewer than --seeds), and the
    generator's own drift self-check patched to `drift_ok`. Returns
    (exit_code, captured_stdout)."""
    import calibrate_pipeline as C
    it = iter(fake_results)
    def fake_pool_map(self, func, jobs):
        for _ in jobs:
            yield next(it)
    buf = io.StringIO()
    old_argv = sys.argv
    sys.argv = ["calibrate_pipeline.py"] + argv
    try:
        with mock.patch("multiprocessing.pool.Pool.imap_unordered", fake_pool_map), \
             mock.patch("numpy.mean", side_effect=(lambda a, *k, **kw:
                        (-0.1 if drift_ok else 5.0) if
                        (hasattr(a, "__len__") and len(a) == 10) else
                        __import__("numpy").asarray(a).mean(*k, **kw))), \
             contextlib.redirect_stdout(buf):
            try:
                C.main()
                code = 0
            except SystemExit as e:
                code = e.code if e.code is not None else 0
    finally:
        sys.argv = old_argv
    return code, buf.getvalue()

def result(seed, survivors, **extra):
    base = dict(seed=seed, survivors=survivors, tested=1000, bar=5.5,
               n_final=5, best_boot_t=1.0, best_naive_t=2.0, elapsed=1.0)
    base.update(extra)
    return base

print("CALIBRATION HARNESS - EXIT CODE VERIFICATION (no real backtests run)")
print("=" * 70)

print("\n1. all seeds clean -> PASS, exit 0")
fake = [result(101 + i, 0) for i in range(4)]
code, out = run_main_with(fake, ["--seeds", "4", "--jobs", "1"])
ck("exit code is 0 when nothing survives", code == 0,
   f"exit={code}, verdict line: "
   f"{[l for l in out.splitlines() if 'CALIBRATION' in l]}")

print("\n2. one seed produces a survivor -> FAIL, exit 1")
fake = [result(101, 0), result(102, 1), result(103, 0), result(104, 0)]
code, out = run_main_with(fake, ["--seeds", "4", "--jobs", "1"])
ck("exit code is 1 when any seed survives the gate", code == 1,
   f"exit={code}, verdict line: "
   f"{[l for l in out.splitlines() if 'CALIBRATION' in l]}")

print("\n3. a worker raises -> FAIL, exit 1, not silently ignored")
fake = [result(101, 0), dict(seed=102, error="RuntimeError: boom", elapsed=1.0),
       result(103, 0)]
code, out = run_main_with(fake, ["--seeds", "3", "--jobs", "1"])
ck("exit code is 1 when a worker crashes rather than reports 0 survivors",
   code == 1,
   f"exit={code}, error line present: "
   f"{[l for l in out.splitlines() if 'ERROR' in l or 'crashes' in l]}")

print("\n4. the generator itself has drift -> refuses to calibrate, exit 2")
fake = [result(101, 0)]
code, out = run_main_with(fake, ["--seeds", "1", "--jobs", "1"], drift_ok=False)
ck("exit code is 2 when the driftless-generator self-check fails", code == 2,
   f"exit={code}, message: "
   f"{[l for l in out.splitlines() if 'drift' in l.lower()]}")

print("\n" + "=" * 70)
if fails:
    print(f"{len(fails)} FAILED:")
    for f in fails: print(f"  - {f}")
    sys.exit(1)
print("all calibration exit-code paths behave as documented")
sys.exit(0)
