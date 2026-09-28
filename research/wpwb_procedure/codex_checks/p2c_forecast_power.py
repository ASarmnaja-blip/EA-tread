"""Pre-P1-cut development check and forward-power simulation for P2-C.

The target is next-week XAU H1 realised variance.  The candidate is an
expanding log-HAR regression and the benchmark is the arithmetic mean of the
last 26 weekly realised variances.  Historical results are development
evidence only.  This script reads frozen local snapshots and never evaluates
selector P or its real P/B'/d outcome.
"""
from __future__ import annotations

import hashlib
import math
import os
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
for p in ("research/wpwb_live", "research/wpwb_search"):
    sys.path.insert(0, str(ROOT / p))
import common as C  # noqa: E402
from run_live_hod import combined_bars  # noqa: E402

SEED = 20260928
MIN_TRAIN = 104
DIFF_CAPS = (0.25, 0.50, 1.00)
LAMBDAS = np.array((0.05, 0.10, 0.20, 0.40, 0.80))
ALPHA = 0.025
REPS = 10000
BLOCK = 8


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def weekly_rv(m: C.Market, cuts: np.ndarray, stop: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Completed-week close-to-close H1 RV, high-low range, and bar count.

    A return is assigned to the week containing its later H1 close.  Thus a
    reopening gap is included in the following week's risk, while no price
    after ``stop`` is read.
    """
    keep = m.t < stop
    t, c, h, l = m.t[keep], m.c[keep], m.h[keep], m.l[keep]
    lr = np.full(len(t), np.nan)
    lr[1:] = np.diff(np.log(c))
    rv, ran, n = [], [], []
    for a, b in zip(cuts[:-1], cuts[1:]):
        use = (t >= a) & (t < b)
        vals = lr[use]
        vals = vals[np.isfinite(vals)]
        if not len(vals):
            raise AssertionError(f"empty week at {a}")
        rv.append(float(np.sum(vals * vals) * 1e8))  # squared basis points
        first = int(np.flatnonzero(use)[0])
        ran.append(float((np.max(h[use]) - np.min(l[use])) / c[first] * 1e4))
        n.append(int(use.sum()))
    return np.asarray(rv), np.asarray(ran), np.asarray(n)


def features(log_rv: np.ndarray, t: int) -> np.ndarray:
    return np.array((1.0, log_rv[t - 1], log_rv[t - 4:t].mean(), log_rv[t - 26:t].mean()))


def expanding_har(rv: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Strictly prequential forecasts; refit only on targets before t."""
    log_rv = np.log(rv)
    candidate = np.full(len(rv), np.nan)
    benchmark = np.full(len(rv), np.nan)
    betas = np.full((len(rv), 4), np.nan)
    first = 26 + MIN_TRAIN
    all_x = np.array([features(log_rv, t) for t in range(26, len(rv))])
    all_y = log_rv[26:]
    for t in range(first, len(rv)):
        n_train = t - 26
        x, y = all_x[:n_train], all_y[:n_train]
        beta = np.linalg.lstsq(x, y, rcond=None)[0]
        resid = y - x @ beta
        sigma2 = float(resid @ resid / max(len(y) - len(beta), 1))
        candidate[t] = math.exp(float(features(log_rv, t) @ beta) + 0.5 * sigma2)
        benchmark[t] = float(rv[t - 26:t].mean())
        betas[t] = beta
    return candidate, benchmark, betas, np.arange(first, len(rv))


def qlike(y: np.ndarray, f: np.ndarray) -> np.ndarray:
    ratio = y / f
    return ratio - np.log(ratio) - 1.0


def epath(x: np.ndarray) -> np.ndarray:
    factors = 1.0 + LAMBDAS[:, None] * x[None, :]
    if np.any(factors <= 0):
        raise AssertionError("non-positive e factor")
    return np.mean(np.cumprod(factors, axis=1), axis=0)


def circular_blocks(rng: np.random.Generator, x: np.ndarray, horizon: int) -> np.ndarray:
    out: list[float] = []
    while len(out) < horizon:
        j = int(rng.integers(len(x)))
        out.extend(float(x[(j + k) % len(x)]) for k in range(BLOCK))
    return np.asarray(out[:horizon])


def power(x: np.ndarray, effect_fraction: float, horizon: int, rng: np.random.Generator) -> float:
    """Block-bootstrap power if a fraction of the development mean persists."""
    mu = float(x.mean())
    hits = 0
    for _ in range(REPS):
        z = circular_blocks(rng, x, horizon)
        z = np.clip(z - mu + effect_fraction * mu, -1.0, 1.0)
        hits += bool(np.any(epath(z) >= 1.0 / ALPHA))
    return hits / REPS


def null_size(x: np.ndarray, horizon: int, rng: np.random.Generator) -> float:
    """Stress check under independent random signs of observed magnitudes."""
    hits = 0
    for _ in range(REPS):
        z = circular_blocks(rng, np.abs(x), horizon)
        z *= rng.choice((-1.0, 1.0), len(z))
        hits += bool(np.any(epath(z) >= 1.0 / ALPHA))
    return hits / REPS


def main() -> int:
    os.chdir(ROOT)
    with np.load(ROOT / "data/wpwb_procedure_matrix.npz") as z:
        cuts = z["cuts"].copy()
        expected_canonical = str(z["sha_canonical"])
        expected_fresh = str(z["sha_fresh"])
    assert sha(ROOT / "data/canonical_XAUUSD_M5.npz") == expected_canonical
    assert sha(ROOT / "data/fresh/XAUUSD_M5.npz") == expected_fresh
    stop = int(cuts[-1])
    m = C.Market(combined_bars())
    rv, ran, nbar = weekly_rv(m, cuts, stop)
    candidate, benchmark, betas, ix = expanding_har(rv)
    lc, lb = qlike(rv[ix], candidate[ix]), qlike(rv[ix], benchmark[ix])
    uncapped = lb - lc
    final_beta = betas[ix[-1]]

    print(f"cutoff={np.datetime64(stop, 's')} completed_weeks={len(rv)} eval_weeks={len(ix)}")
    print(f"bars/week min/median/max={nbar.min()}/{np.median(nbar):.0f}/{nbar.max()}")
    print("target RV=sum squared H1 close-to-close log returns (bp^2)")
    print("final expanding log-HAR beta=" + np.array2string(final_beta, precision=4))
    print(f"QLIKE candidate={lc.mean():.4f} benchmark={lb.mean():.4f} "
          f"uncapped improvement={uncapped.mean():+.4f} ({uncapped.mean()/lb.mean():+.1%})")
    last_week = rv[ix - 1]
    ewma = np.full(len(rv), np.nan)
    ewma[0] = rv[0]
    for t in range(1, len(rv)):
        ewma[t] = 0.75 * ewma[t - 1] + 0.25 * rv[t - 1]
    for label, alt in (("last-week", last_week), ("EWMA-lambda-.75", ewma[ix])):
        la = qlike(rv[ix], alt)
        delta = la - lc
        print(f"diagnostic stronger benchmark {label}: QLIKE={la.mean():.4f}, "
              f"HAR improvement={delta.mean():+.4f} ({delta.mean()/la.mean():+.1%})")
    print(f"uncapped win_rate={(uncapped > 0).mean():.3f}")
    print(f"range median={np.median(ran):.1f} bp; RV-vol median={np.median(np.sqrt(rv)):.1f} bp")

    rng = np.random.default_rng(SEED)
    print(f"simulation seed={SEED} reps={REPS} block={BLOCK} alpha={ALPHA} threshold={1/ALPHA:.0f}")
    for cap in DIFF_CAPS:
        x = np.clip(uncapped, -cap, cap) / cap
        print(f"difference cap={cap:.2f}: mean={x.mean():+.4f} sd={x.std(ddof=1):.4f} "
              f"ac1={np.corrcoef(x[:-1], x[1:])[0,1]:+.3f}")
        for frac in (1.0, 0.5):
            vals = [power(x, frac, h, rng) for h in (26, 52)]
            print(f"  power at {frac:.0%} development mean: 26w={vals[0]:.3f} 52w={vals[1]:.3f}")
        vals = [null_size(x, h, rng) for h in (26, 52)]
        print(f"  random-sign null hit: 26w={vals[0]:.4f} 52w={vals[1]:.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
