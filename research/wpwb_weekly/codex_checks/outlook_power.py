"""Model-free power check for the WPWB Outlook draft-v0 adoption rule.

This script does not read market data.  It expresses score improvement in
units of the weekly paired score-difference standard deviation, because an
absolute RPS MDE cannot be known before a clean paired score series exists.
"""

from __future__ import annotations

import numpy as np


N_WEEKS = 130
BLOCK = 8
N_PATHS = 4_000
N_BOOT = 1_000
SEED = 20260929


def bootstrap_weights(rng: np.random.Generator) -> np.ndarray:
    """Circular moving-block bootstrap weights, exactly N_WEEKS observations."""
    n_blocks = int(np.ceil(N_WEEKS / BLOCK))
    weights = np.zeros((N_BOOT, N_WEEKS), dtype=np.float32)
    offsets = np.arange(BLOCK)
    for b in range(N_BOOT):
        starts = rng.integers(0, N_WEEKS, size=n_blocks)
        idx = ((starts[:, None] + offsets) % N_WEEKS).ravel()[:N_WEEKS]
        weights[b] = np.bincount(idx, minlength=N_WEEKS) / N_WEEKS
    return weights


def ar1_paths(
    rng: np.random.Generator,
    phi: float,
    n_paths: int,
    common: np.ndarray | None = None,
    innovation_corr: float = 0.0,
) -> np.ndarray:
    burn = 300
    noise = rng.normal(size=(n_paths, burn + N_WEEKS)).astype(np.float32)
    if common is not None:
        noise = (
            innovation_corr * common
            + np.sqrt(1.0 - innovation_corr**2) * noise
        )
    noise *= np.sqrt(1.0 - phi**2)
    x = np.zeros_like(noise)
    for t in range(1, x.shape[1]):
        x[:, t] = phi * x[:, t - 1] + noise[:, t]
    return x[:, burn:]


def lower_ci_at_zero(paths: np.ndarray, weights: np.ndarray) -> np.ndarray:
    boot_means = paths @ weights.T
    return np.quantile(boot_means, 0.025, axis=1)


def reliability_pass_rate(
    rng: np.random.Generator, n_bins: int, repetitions: int = 300_000
) -> float:
    per_bin = N_WEEKS // n_bins
    ps = (np.arange(n_bins) + 0.5) / n_bins
    counts = rng.binomial(per_bin, ps, size=(repetitions, n_bins))
    observed = counts / per_bin
    return float(np.mean(np.all(np.abs(observed - ps) <= 0.05, axis=1)))


def main() -> None:
    rng = np.random.default_rng(SEED)
    weights = bootstrap_weights(rng)
    effects = np.array([0.20, 0.25, 0.30, 0.35, 0.40, 0.45, 0.50])

    print(f"n={N_WEEKS}, circular block={BLOCK}, bootstrap={N_BOOT}, paths={N_PATHS}")
    print("Effect is mean weekly improvement / SD(paired weekly improvement).")
    for phi in (0.0, 0.3, 0.5):
        paths = ar1_paths(rng, phi, N_PATHS)
        lower = lower_ci_at_zero(paths, weights)
        powers = [np.mean(lower + effect > 0.0) for effect in effects]
        row = " ".join(f"{e:.2f}:{p:.3f}" for e, p in zip(effects, powers))
        first_80 = next((e for e, p in zip(effects, powers) if p >= 0.80), None)
        print(f"one metric phi={phi:.1f}  {row}  first>=80%={first_80}")

    # Two score streams with correlated innovations; adoption requires both CIs.
    phi = 0.3
    common = rng.normal(size=(N_PATHS, 300 + N_WEEKS)).astype(np.float32)
    first = ar1_paths(rng, phi, N_PATHS, common=common, innovation_corr=np.sqrt(0.6))
    second = ar1_paths(rng, phi, N_PATHS, common=common, innovation_corr=np.sqrt(0.6))
    lower_first = lower_ci_at_zero(first, weights)
    lower_second = lower_ci_at_zero(second, weights)
    for effect in (0.25, 0.35, 0.45, 0.55):
        joint = np.mean((lower_first + effect > 0.0) & (lower_second + effect > 0.0))
        print(f"two metrics phi=0.3 corr~0.6 effect={effect:.2f} joint_power={joint:.3f}")

    for n_bins in (5, 10):
        rate = reliability_pass_rate(rng, n_bins)
        print(
            f"calibrated binary forecast, {n_bins} equal bins, raw error <=5pp "
            f"in every bin: pass_rate={rate:.6f}"
        )


if __name__ == "__main__":
    main()
