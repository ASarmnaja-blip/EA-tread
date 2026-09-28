"""Sensitivity of Codex's P2-B planning power to its assumed inputs, using
Codex's own matched_once() unchanged. event_sd 100 / 170 bp are the measured
direction-agnostic paired SDs for 4 h / 12 h holds (paired_residual_sd.py)."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "codex_checks"))
import round3_power as R3  # noqa: E402

rng = np.random.default_rng(20260930)
print("event_sd events corr  edge  screen  forward156")
for sd in (60.0, 100.0, 170.0):
    for ev in (4, 12):
        for corr in (0.1, 0.3):
            for edge in (10.0, 20.0):
                rows = np.array([R3.matched_once(rng, edge, sd, ev, corr) for _ in range(300)], float)
                print(f"{sd:8.0f} {ev:6d} {corr:4.1f} {edge:5.0f}  {rows[:,0].mean():6.2f}  {rows[:,3].mean():10.2f}")
