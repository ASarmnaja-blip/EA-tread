"""Mutation check for the news layer: a test that cannot fail proves nothing.

Six defects are injected into news.py one at a time, the suite is re-run, and
the file is restored and verified by sha256 afterwards - including if a run
blows up.
"""
import hashlib
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
TARGET = HERE / "news.py"
SUITE = HERE / "test_news.py"

MUTATIONS = [
    ("M1  in-line band removed",
     "    if len(material) == 0:",
     "    if False:",
     ["N4e"]),

    ("M2  unknown surprise treated as zero",
     "    if ev.sigma is None or ev.sigma <= 0:\n        return None",
     "    if ev.sigma is None or ev.sigma <= 0:\n        return 0.0",
     ["N1c"]),

    ("M3  swept-both-sides precedence dropped",
     "    if reaction.swept_high and reaction.swept_low:",
     "    if False:",
     ["N4g", "N5"]),

    ("M4  retrace no longer counts as rejection",
     "    retraced = (hyp * early > 0 and hyp * late < hyp * early * reject_retrace)",
     "    retraced = False",
     ["N6a"]),

    ("M5  spread check demoted below classification",
     "    if spread_over_limit:\n        return Assessment(NO_TRADE, \"spread above the tradeable limit at release\")",
     "    if False:\n        return Assessment(NO_TRADE, \"spread above the tradeable limit at release\")",
     ["N7a"]),

    ("M6  baseline includes the release bar",
     "    before = np.flatnonzero(times < t_event)",
     "    before = np.flatnonzero(times <= t_event)",
     ["N3c", "N3d"]),
]


def run_suite():
    """Returns the list of failing test ids.

    A crash counts as a detection. The suite always prints a "passed N,
    failed M" line when it completes, so its absence means the mutation broke
    the module hard enough to take the run down - which is the loudest possible
    failure, not a miss. Reading only FAIL lines would score that as nothing.
    """
    r = subprocess.run([sys.executable, str(SUITE)], cwd=HERE,
                       capture_output=True, text=True)
    failed = [ln.split()[1] for ln in r.stdout.splitlines()
              if ln.strip().startswith("FAIL")]
    if "passed " not in r.stdout:
        first = next((ln for ln in reversed(r.stderr.splitlines()) if ln.strip()),
                     "no traceback")
        failed.append(f"<CRASH: {first.strip()[:60]}>")
    return failed


def main():
    original = TARGET.read_bytes()
    digest = hashlib.sha256(original).hexdigest()

    print("=" * 74)
    print("NEWS LAYER MUTATION CHECK")
    print("=" * 74)
    base = run_suite()
    if base:
        sys.exit(f"baseline is not green ({base}); fix that first")
    print("  baseline: 0 failures\n")

    missed = []
    try:
        for name, old, new, expect in MUTATIONS:
            src = original.decode()
            if src.count(old) != 1:
                print(f"  ERROR {name}: anchor found {src.count(old)} times")
                missed.append(name)
                continue
            TARGET.write_text(src.replace(old, new))
            failed = run_suite()
            TARGET.write_bytes(original)
            caught = any(e in failed for e in expect) or any(
                f.startswith("<CRASH") for f in failed)
            if not caught:
                missed.append(name)
            print(f"  {'CAUGHT' if caught else 'MISSED':7s} {name}")
            print(f"          expected one of {expect}, suite reported "
                  f"{failed or 'nothing'}")
    finally:
        TARGET.write_bytes(original)

    now = hashlib.sha256(TARGET.read_bytes()).hexdigest()
    clean = now == digest
    print(f"\n  news.py after restore: {'unchanged' if clean else 'MODIFIED'}")
    print(f"  post-restore suite: {run_suite() or '0 failures'}")
    print("-" * 74)
    print(f"{len(MUTATIONS) - len(missed)}/{len(MUTATIONS)} caught; "
          f"tree {'clean' if clean else 'DIRTY'}")
    return 0 if (not missed and clean) else 1


if __name__ == "__main__":
    sys.exit(main())
