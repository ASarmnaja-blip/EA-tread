"""Simulation helpers for the 2026-09-28 Codex WPWB methodology review.

This reproduces the decision rule in research/wpwb_search/common.py:
the larger of a centered circular-block bootstrap p-value (block 8,
5,000 draws) and a Newey-West/Bartlett p-value (lags 1..8).  The bootstrap
uses the same fixed resampling indices for every series, matching the fixed
seed used by block_boot().

The implementation exploits location/scale invariance: for a given n and
AR(1) phi, one set of standardized null paths can be shifted by each requested
effect size.  That makes the small review simulation exact with respect to the
repository's test while keeping runtime manageable.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy import stats


@dataclass(frozen=True)
class SimConfig:
    reps: int = 10_000
    draws: int = 5_000
    block: int = 8
    lags: int = 8
    bootstrap_seed: int = 12_345
    data_seed: int = 20_260_928


def _stationary_ar1(reps: int, n: int, phi: float, rng: np.random.Generator) -> np.ndarray:
    """Return zero-mean AR(1) paths with stationary marginal variance one."""
    x = np.empty((reps, n), dtype=float)
    x[:, 0] = rng.normal(size=reps)
    innovation_sd = np.sqrt(1.0 - phi * phi)
    for j in range(1, n):
        x[:, j] = phi * x[:, j - 1] + rng.normal(scale=innovation_sd, size=reps)
    return x


def _bootstrap_weights(n: int, cfg: SimConfig) -> np.ndarray:
    """Counts per observation for the exact circular blocks used by common.py."""
    rng = np.random.default_rng(cfg.bootstrap_seed)
    n_blocks = int(np.ceil(n / cfg.block))
    starts = rng.integers(0, n, size=(cfg.draws, n_blocks))
    idx = ((starts[:, :, None] + np.arange(cfg.block)) % n).reshape(cfg.draws, -1)[:, :n]
    weights = np.zeros((cfg.draws, n), dtype=np.uint8)
    rows = np.repeat(np.arange(cfg.draws), n)
    np.add.at(weights, (rows, idx.ravel()), 1)
    return weights


def _hac_scale(x: np.ndarray, lags: int) -> np.ndarray:
    """Denominator of the repository's Newey-West t statistic for each row."""
    d = x - x.mean(axis=1, keepdims=True)
    s = (d * d).mean(axis=1)
    for lag in range(1, lags + 1):
        s += 2.0 * (1.0 - lag / (lags + 1.0)) * (d[:, lag:] * d[:, :-lag]).mean(axis=1)
    return np.sqrt(np.maximum(s, 1e-18) / x.shape[1])


def simulate_pvalues(
    n: int,
    phi: float,
    standardized_effects: np.ndarray,
    cfg: SimConfig,
) -> dict[float, np.ndarray]:
    """Simulate max(CBB8, NW8) p-values for each mean/sd effect."""
    rng = np.random.default_rng(cfg.data_seed + 10_000 * n + int(round(phi * 1_000)))
    x = _stationary_ar1(cfg.reps, n, phi, rng)
    sample_mean = x.mean(axis=1)
    hac_scale = _hac_scale(x, cfg.lags)
    weights = _bootstrap_weights(n, cfg)
    cbb_counts = np.zeros((len(standardized_effects), cfg.reps), dtype=np.int32)
    correction = np.sqrt(n / (n - 1.0))

    # Chunked matrix products avoid allocating draws x reps x n arrays.
    for first in range(0, cfg.draws, 250):
        w = weights[first:first + 250].astype(float, copy=False)
        resampled = (w @ x.T) / n
        dev = (resampled - sample_mean[None, :]) * correction
        for j, effect in enumerate(standardized_effects):
            cbb_counts[j] += (dev >= sample_mean[None, :] + effect).sum(axis=0)

    out: dict[float, np.ndarray] = {}
    for j, effect in enumerate(standardized_effects):
        p_cbb = cbb_counts[j] / cfg.draws  # deliberately matches repository (no +1)
        t_hac = (sample_mean + effect) / hac_scale
        p_hac = stats.t.sf(t_hac, n - 1)
        out[float(effect)] = np.maximum(p_cbb, p_hac)
    return out
