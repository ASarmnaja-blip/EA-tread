"""Freeze the latest past-only M5 K=5 weekly selection to JSON."""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import evolution_candidate_validation as valid
import evolution_portfolio_audit as audit


OUTPUT = Path("data/weekly_evolution_selection.json")


def build() -> dict:
    b5 = audit.hist.load_history()
    first, last = int(b5.t[0]), int(b5.t[-1] + b5.step)
    uni, meta = audit.load_universe(b5)
    rankings, purged = audit.weekly_rankings(uni, first, last)
    cut, end, ranked = rankings[-1]
    m5 = [tag for tag in ranked if meta[tag]["tf"] == "M5"]
    chosen = valid.choose_five(m5, meta)
    return {
        "policy": "weekly_m5_k5_diverse_v1",
        "research_only_until_demo_runner_verifies_account": True,
        "selected_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "cutoff_epoch": cut,
        "cutoff_utc": datetime.fromtimestamp(cut, timezone.utc).isoformat(),
        "valid_until_epoch": end,
        "valid_until_utc": datetime.fromtimestamp(end, timezone.utc).isoformat(),
        "selection_days": audit.weekly.SELECT_DAYS,
        "unresolved_outcomes_purged_all_rolls": purged,
        "cost": {"spread_floor": 0.090, "commission_round_turn": 0.140,
                 "slippage_round_turn": 0.033, "swap_long_night": 0.5493},
        "cells": [{"tag": tag, **meta[tag]} for tag in chosen],
    }


def main() -> int:
    payload = build()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
