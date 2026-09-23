"""Freeze one broker-history snapshot; refuses to replace an existing one."""
from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import canonical_history as canonical
import historical_regime_walkforward as hist


def main() -> int:
    bars = hist.load_mutable_history()
    meta = canonical.save(
        hist.CANONICAL_M5, bars,
        "annual MT5 XAUUSD M5 before local CSV boundary plus local XAUUSD_M5.csv")
    print(meta)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
