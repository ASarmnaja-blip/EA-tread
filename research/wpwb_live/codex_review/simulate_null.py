"""Null rejection rates for the WPWB max(CBB8, NW8) rule.

This is a calibration companion to simulate_power.py.  It uses the same
10,000 replications and reports the raw per-test rule and the thresholds used
for families of 6, 20, and 40.  Output stays beside the script.
"""
from __future__ import annotations

import csv
from pathlib import Path

import numpy as np

from simulation_core import SimConfig, simulate_pvalues


OUT = Path(__file__).with_name("null_results.csv")


def main() -> int:
    cfg = SimConfig()
    rows = []
    for n in (130, 142):
        for phi in (0.0, 0.3):
            p = simulate_pvalues(n, phi, np.array([0.0]), cfg)[0.0]
            for family in (1, 6, 20, 40):
                alpha = 0.025 / family
                hits = int((p < alpha).sum())
                rate = hits / cfg.reps
                rows.append({
                    "n": n,
                    "phi": phi,
                    "family_size": family,
                    "alpha": alpha,
                    "reps": cfg.reps,
                    "bootstrap_draws": cfg.draws,
                    "rejections": hits,
                    "rejection_rate": rate,
                    "mc_se": np.sqrt(rate * (1.0 - rate) / cfg.reps),
                })
    with OUT.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    print(f"wrote {len(rows)} rows to {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
