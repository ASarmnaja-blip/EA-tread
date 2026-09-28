"""Power of the repository's WPWB weekly-mean test at its used thresholds.

Run from the repository root:
    python research/wpwb_live/codex_review/simulate_power.py

The output is written beside this script, never under data/.
"""
from __future__ import annotations

import csv
from pathlib import Path

import numpy as np

from simulation_core import SimConfig, simulate_pvalues


OUT = Path(__file__).with_name("power_results.csv")
NS = (130, 142)
SDS = (150, 200)
EDGES = (5, 10, 20)
PHIS = (0.0, 0.3)
FAMILIES = (1, 6, 20, 40)


def main() -> int:
    cfg = SimConfig()
    effects = np.array(sorted({edge / sd for edge in EDGES for sd in SDS}))
    rows = []
    for n in NS:
        for phi in PHIS:
            pvalues = simulate_pvalues(n, phi, effects, cfg)
            for sd in SDS:
                for edge in EDGES:
                    p = pvalues[edge / sd]
                    for family in FAMILIES:
                        alpha = 0.025 / family
                        hits = int((p < alpha).sum())
                        rate = hits / cfg.reps
                        mc_se = np.sqrt(rate * (1.0 - rate) / cfg.reps)
                        rows.append({
                            "n": n,
                            "phi": phi,
                            "weekly_sd_bp": sd,
                            "true_edge_bp": edge,
                            "family_size": family,
                            "alpha": alpha,
                            "reps": cfg.reps,
                            "bootstrap_draws": cfg.draws,
                            "detections": hits,
                            "detection_rate": rate,
                            "mc_se": mc_se,
                        })
    with OUT.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    print(f"wrote {len(rows)} rows to {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

