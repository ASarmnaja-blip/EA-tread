"""Round-3 power checks that never evaluate P on the unscrambled matrix.

The real outcome matrix supplies only fixed magnitudes, activity, validity,
cost increments and internal sizes.  A fresh, independent Rademacher sign is
applied to each whole weekly cross-section.  This gives every row conditional
mean zero while preserving row identity, row scale, structural zeros,
within-week cross-tool products, market-wide volatility clustering, VALID and
INNER.  Persistent alternatives are added only after this randomization.

The script also estimates forward power for two candidate P2 designs:

1. A fixed two-basket volatility router.  The state is lagged cross-sectional
   absolute return versus its trailing-52-week median.  The high/low basket
   map is fixed; no P&L rank is estimated.  Its simulated excess is the routed
   basket minus the whole eligible menu, plus a stated policy-level edge.
2. A trade-level matched design, aggregated to one weekly risk-budgeted
   contrast.  Its assumptions (12 events/week, 60 bp event residual SD,
   within-week correlation 0.10, stochastic-volatility rho 0.81) are explicit.

For forward power, c is estimated on an independent 216-week training path;
the e-process is then run on 156 new weeks.  This avoids using c from the same
weeks on which detection is assessed.
"""
from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE.parent))
import procedure as P  # noqa: E402

MATRIX = ROOT / "data" / "wpwb_procedure_matrix.npz"
SEED = 20260929
FUTURE_WEEKS = 156
BLOCK_BOOT = 13


def family(name: str) -> str:
    return name.split()[0]


def bootstrap_indices(rng, pool, n, block=BLOCK_BOOT):
    """Circular fixed-length block bootstrap from an integer index pool."""
    out = []
    m = len(pool)
    while len(out) < n:
        j = int(rng.integers(m))
        out.extend(pool[(j + k) % m] for k in range(block))
    return np.asarray(out[:n], int)


def sign_randomized_stream(z, rng, future_weeks=FUTURE_WEEKS):
    """Training matrix plus new block-bootstrapped, sign-randomized weeks."""
    R10, R15 = z["R10"], z["R15"]
    NTR, VALID, INNER = z["NTR"], z["VALID"], z["INNER"]
    w0 = P.first_scored_cut(VALID)
    n = R10.shape[1]

    s0 = rng.choice((-1.0, 1.0), size=n)
    A0 = R10 * s0[None, :]
    # Keep the observed incremental stress cost rather than reversing costs.
    B0 = A0 + (R15 - R10)

    ix = bootstrap_indices(rng, np.arange(w0, n), future_weeks)
    sf = rng.choice((-1.0, 1.0), size=future_weeks)
    Af = R10[:, ix] * sf[None, :]
    Bf = Af + (R15 - R10)[:, ix]

    A = np.c_[A0, Af]
    B = np.c_[B0, Bf]
    N = np.c_[NTR, NTR[:, ix]]
    V = np.c_[VALID, np.ones((VALID.shape[0], future_weeks), bool)]
    I = np.c_[INNER, INNER[:, ix]]
    return A, B, N, V, I, w0, n


def plant_calendar_edge(A, B, N, V, rows, edge, w0):
    """Give each planted row `edge` bp per calendar week before outer sizing.

    Additions occur on traded cells only, divided by that row's activity over
    the scored stream.  This differs deliberately from harness.py's
    `edge`-per-traded-cell alternative.
    """
    for r in rows:
        use = V[r, w0:] & (N[r, w0:] > 0)
        activity = float(use.mean())
        if activity == 0:
            continue
        add = np.zeros(A.shape[1])
        add[w0:][use] = edge / activity
        A[r] += add
        B[r] += add


def current_p_once(z, names, fams, rng, edge):
    A, B, N, V, I, w0, split = sign_randomized_stream(z, rng)
    fam = fams[int(rng.integers(len(fams)))]
    rows = [i for i, name in enumerate(names) if family(name) == fam]
    if edge:
        plant_calendar_edge(A, B, N, V, rows, edge, w0)
    res = P.run_fast(A, N, V, I, w0, {"base": A, "stress": B})
    n_train = split - w0
    train = {
        "base": {k: v[:n_train] for k, v in res["base"].items()},
        "stress": {k: v[:n_train] for k, v in res["stress"].items()},
    }
    screen, _, _ = P.resource_screen(train)
    d_train = train["base"]["d"]
    d_future = res["base"]["d"][n_train:n_train + FUTURE_WEEKS]
    hit = bool((P.e_process(d_future, P.clip_scale(d_train)) >= 40).any())
    pick = float(np.isin(res["choice"][:n_train], rows).mean())
    return screen, float(d_train.mean()), float(d_train.std(ddof=1)), hit, pick


HIGH = {"TSM", "TSMI", "HOD", "HODM", "SESSION", "VOLMAN"}
LOW = {"CHOPREV", "CHOPREV-ungated", "CHOPREV-X", "DAYREV", "DOW", "GAP"}


def router_d(A, N, V, I, names, first_w):
    """Fixed volatility-state router excess versus the whole eligible menu."""
    fam = np.asarray([family(n) for n in names])
    n_tools, n = A.shape
    proxy_cells = np.where((N > 0) & V, np.abs(A), np.nan)
    proxy = np.zeros(n)
    has_proxy = np.isfinite(proxy_cells).any(axis=0)
    proxy[has_proxy] = np.nanmedian(proxy_cells[:, has_proxy], axis=0)
    sd = np.full((n_tools, n), np.nan)
    for t in range(P.SCALE_W, n):
        sd[:, t] = P.scale_at(A, V, t)
    z = A / np.maximum(sd, P.SD_FLOOR)
    z[~V | ~np.isfinite(sd)] = np.nan
    act = np.cumsum(np.c_[np.zeros(n_tools), N > 0], axis=1)
    out = []
    for w in range(first_w, n):
        zz = z[:, w - P.SCORE_W:w]
        active = act[:, w] - act[:, w - P.SCORE_W]
        eligible = (np.isfinite(zz).all(axis=1) & np.isfinite(sd[:, w])
                    & (active >= P.MIN_ACTIVE) & V[:, w])
        if not eligible.any():
            out.append(0.0)
            continue
        sizes = np.minimum(P.CAP / np.maximum(I[:, w], 1e-9),
                           P.TARGET / np.maximum(sd[:, w], P.SD_FLOOR))
        hist = proxy[max(0, w - 52):w]
        high = proxy[w - 1] > np.nanmedian(hist)
        basket = np.isin(fam, list(HIGH if high else LOW)) & eligible
        whole = float(np.mean(sizes[eligible] * A[eligible, w]))
        routed = float(np.mean(sizes[basket] * A[basket, w])) if basket.any() else 0.0
        out.append(routed - whole)
    return np.asarray(out)


def router_once(z, names, rng, edge):
    A, _, N, V, I, w0, split = sign_randomized_stream(z, rng)
    d = router_d(A, N, V, I, names, w0)
    n_train = split - w0
    d_train = d[:n_train] + edge
    d_future = d[n_train:n_train + FUTURE_WEEKS] + edge
    bm = np.array([d_train[a:b].mean() for a, b in P.blocks(len(d_train))])
    screen = (d_train.mean() >= P.EXCESS_FLOOR
              and (bm > 0).mean() >= P.BLOCK_SHARE)
    hit = bool((P.e_process(d_future, P.clip_scale(d_train)) >= 40).any())
    return screen, float(d_train.mean()), float(d_train.std(ddof=1)), hit


def ar1_logvol(rng, n, rho=0.81, log_sd=0.35):
    x = np.zeros(n)
    innovation = log_sd * math.sqrt(1 - rho * rho)
    for t in range(1, n):
        x[t] = rho * x[t - 1] + rng.normal(0, innovation)
    v = np.exp(x)
    return v / v.mean()


def matched_once(rng, edge, event_sd=60.0, events=12, intra_corr=0.10):
    """Weekly equal-risk average of matched event contrasts."""
    train_n = 216
    n = train_n + FUTURE_WEEKS
    vol = ar1_logvol(rng, n)
    common = rng.normal(size=n)
    idio = rng.normal(size=(n, events))
    event_noise = event_sd * vol[:, None] * (
        math.sqrt(intra_corr) * common[:, None]
        + math.sqrt(1 - intra_corr) * idio
    )
    d = edge + event_noise.mean(axis=1)
    train, future = d[:train_n], d[train_n:]
    bm = np.array([train[a:b].mean() for a, b in P.blocks(train_n)])
    screen = train.mean() >= P.EXCESS_FLOOR and (bm > 0).mean() >= P.BLOCK_SHARE
    hit = bool((P.e_process(future, P.clip_scale(train)) >= 40).any())
    return screen, float(train.mean()), float(train.std(ddof=1)), hit


def summarize(label, edge, rows):
    a = np.asarray(rows, float)
    # columns: screen, mean, [sd], hit, [pick]
    se_screen = math.sqrt(a[:, 0].mean() * (1 - a[:, 0].mean()) / len(a))
    se_hit = math.sqrt(a[:, -2 if a.shape[1] == 5 else -1].mean()
                       * (1 - a[:, -2 if a.shape[1] == 5 else -1].mean()) / len(a))
    if a.shape[1] == 4:
        print(f"{label:18s} edge={edge:>4.0f}: screen={a[:,0].mean():.3f} +/- {se_screen:.3f}  "
              f"mean_d={a[:,1].mean():6.2f}  sd(d)={a[:,2].mean():6.1f}  "
              f"forward156={a[:,3].mean():.3f} +/- {se_hit:.3f}")
    else:
        print(f"{label:18s} edge={edge:>4.0f}: screen={a[:,0].mean():.3f} +/- {se_screen:.3f}  "
              f"mean_d={a[:,1].mean():6.2f}  sd(d)={a[:,2].mean():6.1f}  "
              f"forward156={a[:,3].mean():.3f} +/- {se_hit:.3f}  "
              f"planted_pick={a[:,4].mean():.3f}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--reps", type=int, default=500)
    args = ap.parse_args()
    z = np.load(MATRIX)
    names = [str(x) for x in z["names"]]
    fams = sorted({family(n) for n in names})
    rng = np.random.default_rng(SEED)

    print(f"seed={SEED}, reps={args.reps}, independent forward={FUTURE_WEEKS} weeks")
    print("Current P; scale-preserving weekly sign null; edge is bp/calendar-week per planted row:")
    for edge in (0.0, 10.0, 20.0):
        rows = [current_p_once(z, names, fams, rng, edge) for _ in range(args.reps)]
        summarize("current-P", edge, rows)

    print("\nP2-A fixed lagged-volatility router; edge is policy-level excess bp/week:")
    for edge in (0.0, 10.0, 20.0):
        rows = [router_once(z, names, rng, edge) for _ in range(args.reps)]
        summarize("vol-router", edge, rows)

    print("\nP2-B matched events; 12/week, event SD=60 bp, ICC=.10, log-vol rho=.81:")
    for edge in (0.0, 10.0, 20.0):
        rows = [matched_once(rng, edge) for _ in range(args.reps)]
        summarize("matched-events", edge, rows)


if __name__ == "__main__":
    main()
