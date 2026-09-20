#!/usr/bin/env python3
"""
Mutation check: a test that cannot fail proves nothing.

Each mutation below injects one defect into the PRODUCTION source, re-extracts,
rebuilds, runs the suite, and records which tests noticed. The original bytes
are restored immediately afterwards and verified by sha256, so the working tree
is byte-identical when this finishes - including if a build blows up.
"""
import hashlib
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SETUPS = ROOT / "MQL5/Include/XAUM15/Setups.mqh"
DECLOG = ROOT / "MQL5/Include/XAUM15/DecisionLog.mqh"
EA = ROOT / "MQL5/Experts/XAUM15/XAU_M15_Institutional_Adaptive.mq5"
BIN = Path(tempfile.gettempdir()) / "mutation_test_bin"

MUTATIONS = [
    ("M1  sentinel removed", SETUPS,
     's.confidence  = -1.0;              // not calibrated - see protocol v2 s.3',
     's.confidence  = 0.5;',
     ["T1.3"]),

    ("M2  CSV escaping removed", DECLOG,
     '         CsvEscape(sig.invalidationRule),',
     '         sig.invalidationRule,',
     ["T2.2"]),

    ("M3  logger touches decision state", EA,
     '   bool traded = (g_lastEntryBarTime==g_lastBarTime);',
     '   bool traded = (g_lastEntryBarTime==g_lastBarTime);\n'
     '   if(!traded) g_blockReason="mutated by the logger";',
     ["T6.2"]),

    ("M4  POSITION_OPENED claimed", DECLOG,
     '      state=CAND_NOT_EVALUATED;',
     '      state=CAND_POSITION_OPENED;',
     ["T3.2", "T4.1", "T4.2"]),

    ("M5  header rewritten on restart", DECLOG,
     '      if(FileTell(m_h)==0)',
     '      if(true)',
     ["T5.8/9"]),

    ("M6  setup name fabricated", DECLOG,
     '         default:      setupName="";  break;',
     '         default:      setupName="D";  break;',
     ["T3.3"]),
]


def build_and_run():
    ex = subprocess.run([sys.executable, "tests/extract_source.py"],
                        cwd=ROOT, capture_output=True, text=True)
    if ex.returncode != 0:
        return None, "extract failed"
    cc = subprocess.run(["g++", "-std=c++17", "-O0", "-o", str(BIN), "tests/test_system.cpp"],
                        cwd=ROOT, capture_output=True, text=True)
    if cc.returncode != 0:
        return None, "compile failed"
    run = subprocess.run([str(BIN)], cwd=ROOT, capture_output=True, text=True)
    failed = [l.split()[1] for l in run.stdout.splitlines() if l.strip().startswith("FAIL")]
    return failed, None


def main():
    originals = {p: p.read_bytes() for p in {SETUPS, DECLOG, EA}}
    digests = {p: hashlib.sha256(b).hexdigest() for p, b in originals.items()}

    print("=" * 70)
    print("MUTATION CHECK - does the suite actually fail when the code is wrong?")
    print("=" * 70)

    base, err = build_and_run()
    if err or base is None:
        sys.exit(f"baseline build failed: {err}")
    if base:
        sys.exit(f"baseline is not green ({base}); fix that before mutating")
    print("  baseline: 0 failures\n")

    results = []
    try:
        for name, path, old, new, expect in MUTATIONS:
            src = originals[path].decode("utf-8", "surrogateescape")
            if src.count(old) != 1:
                results.append((name, "ANCHOR MISS", expect, []))
                print(f"  ERROR {name}: anchor found {src.count(old)} times")
                continue
            path.write_text(src.replace(old, new), encoding="utf-8", errors="surrogateescape")
            failed, err = build_and_run()
            path.write_bytes(originals[path])          # restore immediately
            if err:
                caught = [f"<{err}>"]
                ok = True          # a mutation that will not compile is still caught
            else:
                caught = failed
                ok = any(e in failed for e in expect)
            results.append((name, "CAUGHT" if ok else "MISSED", expect, caught))
            print(f"  {'CAUGHT' if ok else 'MISSED':7s} {name}")
            print(f"          expected one of {expect}, suite reported {caught or 'nothing'}")
    finally:
        for p, b in originals.items():
            p.write_bytes(b)
        subprocess.run([sys.executable, "tests/extract_source.py"],
                       cwd=ROOT, capture_output=True)

    print("\n  --- restoration check ---")
    clean = True
    for p, d in digests.items():
        now = hashlib.sha256(p.read_bytes()).hexdigest()
        state = "unchanged" if now == d else "MODIFIED"
        if now != d:
            clean = False
        print(f"  {state:10s} {p.relative_to(ROOT)}")

    final, err = build_and_run()
    print(f"  post-restore suite: {'0 failures' if final == [] else final}")

    missed = [r for r in results if r[1] != "CAUGHT"]
    print("-" * 70)
    print(f"{len(results) - len(missed)}/{len(results)} mutations caught; "
          f"working tree {'clean' if clean else 'DIRTY'}")
    return 0 if (not missed and clean and final == []) else 1


if __name__ == "__main__":
    sys.exit(main())
