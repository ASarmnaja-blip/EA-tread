#!/usr/bin/env python3
"""Exercise the one-shot holdout protocol before it is used for real.

WHY THIS HAS TO EXIST

  holdout_test.py can be run exactly once against data that exists exactly
  once. Every other script in this project can be debugged by running it
  again; that one cannot. A bug discovered on the real run - a hash check
  that never fires, a one-shot flag that does not stick, a no-finalists path
  that crashes instead of reporting - would spend the sealed universe on a
  stack trace.

  So the protocol is exercised here against throwaway copies, on markets that
  are already burned, with the real manifest and the real finalists file
  untouched. What is tested is the MACHINERY, not any result:

    1. a clean run produces numbers and marks the seal open
    2. a second run refuses
    3. a tampered file fails its hash and stops the run
    4. no finalists means the seal is never opened at all
    5. a missing finalists file stops rather than inventing one
"""
import hashlib
import json
import pathlib
import shutil
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import holdout_test as H

FAILS = []
REAL_CACHE = pathlib.Path(__file__).parent / ".cache_duka"


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}"
          f"{('   ' + detail) if detail else ''}")
    if not cond:
        FAILS.append(name)


def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for c in iter(lambda: f.read(1 << 20), b""):
            h.update(c)
    return h.hexdigest()


def stage(tmp, symbols, finalists, opened=False, tamper=None):
    """Build a throwaway manifest + finalists pair pointing at copied files."""
    cache = tmp / ".cache_duka"
    cache.mkdir(parents=True, exist_ok=True)
    entries = {}
    for sym in symbols:
        src = REAL_CACHE / f"{sym}_H1_2003_2026.parquet"
        if not src.exists():
            continue
        dst = cache / src.name
        if not dst.exists():
            # symlink rather than copy: the parquets are ~20MB each and the
            # hash check reads through a link identically, so four staged
            # runs do not move 600MB around to prove a flag sticks
            dst.symlink_to(src.resolve())
        entries[sym] = dict(file=src.name, sha256=sha(dst), points=1.0)
    if tamper and tamper in entries:
        entries[tamper]["sha256"] = "0" * 64
    (tmp / "sealed_holdout.json").write_text(json.dumps(
        dict(created="test", years=[2004, 2026], timeframe="H1",
             examined=False, symbols=entries)))
    (tmp / "rigorous_finalists.json").write_text(json.dumps(
        dict(created="test", n_searched=21889, criterion="test",
             finalists=finalists, holdout_opened=opened)))
    H.HERE = tmp
    H.CACHE = cache
    H.MANIFEST = tmp / "sealed_holdout.json"
    H.FINALISTS = tmp / "rigorous_finalists.json"
    return tmp


def main():
    print("HOLDOUT PROTOCOL - machinery test on throwaway copies")
    print("=" * 78)
    print("  The real sealed_holdout.json and rigorous_finalists.json are not")
    print("  touched by any of this.\n")
    syms = ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCHF",
            "USDCAD", "NZDUSD", "XAUUSD"]
    rule = [dict(rule=["donch20>0.90", "atr_ratio>0.75"], direction=1,
                 e_free=0.01, e_real=-0.01, skill=0.02, npos=7, n=5000,
                 disc_score=2.9)]

    with tempfile.TemporaryDirectory() as td:
        print("1. no finalists nominated -> seal must stay shut")
        t = stage(pathlib.Path(td) / "a", syms, [])
        rc = H.main()
        man = json.loads((t / "sealed_holdout.json").read_text())
        check("returns 0 (a result, not an error)", rc == 0)
        check("seal NOT marked examined", man.get("examined") is False)

    with tempfile.TemporaryDirectory() as td:
        print("\n2. missing finalists file -> refuse, do not invent one")
        t = pathlib.Path(td) / "b"
        t.mkdir(parents=True)
        H.HERE, H.FINALISTS = t, t / "rigorous_finalists.json"
        H.MANIFEST = t / "sealed_holdout.json"
        check("returns 1", H.main() == 1)

    with tempfile.TemporaryDirectory() as td:
        print("\n3. tampered holdout file -> hash must fail and stop the run")
        t = stage(pathlib.Path(td) / "c", syms, rule, tamper="EURUSD")
        rc = H.main()
        fin = json.loads((t / "rigorous_finalists.json").read_text())
        check("returns 1", rc == 1)
        check("seal NOT marked opened after a hash failure",
              fin.get("holdout_opened") is False)

    with tempfile.TemporaryDirectory() as td:
        print("\n4. clean run -> produces numbers and marks the seal open")
        t = stage(pathlib.Path(td) / "d", syms, rule)
        rc = H.main()
        fin = json.loads((t / "rigorous_finalists.json").read_text())
        man = json.loads((t / "sealed_holdout.json").read_text())
        check("returns 0", rc == 0)
        check("holdout_opened is now true", fin.get("holdout_opened") is True)
        check("opened_at recorded", bool(fin.get("holdout_opened_at")))
        check("manifest marked examined", man.get("examined") is True)
        check("results written", len(fin.get("holdout_results") or []) >= 1)
        r = (fin.get("holdout_results") or [{}])[0]
        check("result carries E, skill and t",
              all(k in r for k in ("e_real", "e_free", "skill", "t")))
        check("a bar was applied", "holdout_floor" in fin)

        print("\n5. second run on the same files -> must refuse")
        check("returns 1 on re-open", H.main() == 1)

    print("\n" + "=" * 78)
    if FAILS:
        print(f"{len(FAILS)} FAILED: " + ", ".join(FAILS))
        print("The protocol is not safe to run against the sealed universe.")
        sys.exit(1)
    print("protocol machinery verified - the one-shot, the hash check, and")
    print("both empty paths behave as written. Safe to run for real.")


if __name__ == "__main__":
    main()
