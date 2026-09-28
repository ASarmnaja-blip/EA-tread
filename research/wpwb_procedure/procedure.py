"""Selector P and benchmarks of docs/WPWB_PROCEDURE_PREREG.md (draft v2).

Pure functions of the outcome matrix. Every quantity used at cut w is
computed from columns < w only (plus the past-known INNER[:, w] and the
metadata VALID[:, w]); `decide` must not read R or NTR at column w or later
(tested by future-garbage on synthetic and real matrices).

Decisions are made once, from base-cost history; stressed outcomes are
evaluated on that same decision path (STRESS_PATH).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

SCALE_W = 26
SCORE_W = 26
HALF_LIFE = 8.0
MIN_ACTIVE = 13
SD_FLOOR = 10.0
TARGET = 100.0
CAP = 3.0            # cap on TOTAL notional multiple, including a tool's own sizing
BLOCK = 26           # resource-screen block length (weeks)
BLOCK_SHARE = 0.60
EXCESS_FLOOR = 2.0   # bp/week, economic floor on mean excess (base)
MARGIN_BP = 2.0      # e-process margin on clipped excess
C_FLOOR = 20.0       # bp, floor on the e-process clip scale c
LAMBDAS = (0.05, 0.1, 0.2, 0.3, 0.5)
MIN_LOOKBACK_VALID = 10

_A = 0.5 ** (np.arange(SCORE_W) / HALF_LIFE)      # a_j for j = 1..26 (lag 1 first)


def scale_at(R, VALID, t):
    """sd_{i,t} from r_{i, t-26..t-1}; NaN unless all 26 inputs valid."""
    if t < SCALE_W:
        return np.full(R.shape[0], np.nan)
    win = R[:, t - SCALE_W:t]
    ok = VALID[:, t - SCALE_W:t].all(axis=1)
    sd = win.std(axis=1, ddof=1)
    return np.where(ok, sd, np.nan)


@dataclass
class Decision:
    w: int
    eligible: np.ndarray
    score: np.ndarray
    choice: int                 # -1 = flat
    size: float                 # outer multiplier; 0 when flat
    sizes: np.ndarray           # outer multiplier for every eligible tool


def decide(R, NTR, VALID, INNER, w):
    n_tools = R.shape[0]
    sd_w = scale_at(R, VALID, w)
    z = np.full((n_tools, SCORE_W), np.nan)
    for j in range(1, SCORE_W + 1):
        t = w - j
        if t < 0:
            break
        sd_t = scale_at(R, VALID, t)
        z[:, j - 1] = R[:, t] / np.maximum(sd_t, SD_FLOOR)
        z[~VALID[:, t], j - 1] = np.nan
    lo = max(0, w - SCORE_W)
    active = (NTR[:, lo:w] > 0).sum(axis=1)
    elig = (np.isfinite(z).all(axis=1) & np.isfinite(sd_w)
            & (active >= MIN_ACTIVE) & VALID[:, w])
    score = np.full(n_tools, np.nan)
    if elig.any():
        score[elig] = (z[elig] * _A).sum(axis=1) / _A.sum()
    inner = np.maximum(INNER[:, w], 1e-9)
    outer = np.minimum(CAP / inner, TARGET / np.maximum(sd_w, SD_FLOOR))
    sizes = np.where(elig, outer, np.nan)
    choice, size = -1, 0.0
    if elig.any():
        best = int(np.nanargmax(score))          # first max = lowest menu index
        if score[best] > 0:
            choice, size = best, float(sizes[best])
    return Decision(w, elig, score, choice, size, sizes)


def run(R_base, NTR, VALID, INNER, first_w, R_eval=None):
    """Decide from R_base history; evaluate P, B' (primary, always-trading
    random eligible tool), B (exposure-matched diagnostic) on each outcome
    matrix in R_eval (default {'base': R_base})."""
    R_eval = R_eval or {"base": R_base}
    n = R_base.shape[1]
    path = [decide(R_base, NTR, VALID, INNER, w) for w in range(first_w, n)]
    res = dict(w=np.arange(first_w, n),
               choice=np.array([d.choice for d in path]),
               size=np.array([d.size for d in path]),
               n_elig=np.array([int(d.eligible.sum()) for d in path]))
    for key, R in R_eval.items():
        P, Bp, B = [], [], []
        for d in path:
            e = d.eligible
            menu = float(np.mean(d.sizes[e] * R[e, d.w])) if e.any() else 0.0
            p = d.size * R[d.choice, d.w] if d.choice >= 0 else 0.0
            P.append(p); Bp.append(menu); B.append(menu if d.choice >= 0 else 0.0)
        P, Bp, B = map(np.asarray, (P, Bp, B))
        res[key] = dict(P=P, Bp=Bp, B=B, d=P - Bp, d_cond=P - B)
    return res, path


def first_scored_cut(VALID, min_tools=MIN_LOOKBACK_VALID):
    """First w at which >= min_tools tools are lookback-valid on w-52..w.
    Metadata only (VALID), never activity or outcomes."""
    n = VALID.shape[1]
    need = SCALE_W + SCORE_W
    for w in range(need, n):
        if (VALID[:, w - need:w + 1].all(axis=1)).sum() >= min_tools:
            return w
    return None


def blocks(n, size=BLOCK):
    """Non-overlapping blocks from the first scored week; a remainder shorter
    than `size` is merged into the last block."""
    k = max(1, n // size)
    edges = [i * size for i in range(k)] + [n]
    return [(edges[i], edges[i + 1]) for i in range(k)]


def resource_screen(res):
    """Non-inferential affordability screen for starting the forward shadow."""
    d = res["base"]["d"]
    bm = np.array([d[a:b].mean() for a, b in blocks(len(d))])
    checks = dict(
        excess_base=float(d.mean()) >= EXCESS_FLOOR,
        excess_stress=float(res["stress"]["d"].mean()) > 0,
        abs_P_stress=float(res["stress"]["P"].mean()) > 0,
        block_share=float((bm > 0).mean()) >= BLOCK_SHARE,
    )
    return all(checks.values()), checks, bm


def clip_scale(d_hist):
    sd = float(np.std(d_hist, ddof=1)) if len(d_hist) > 1 else np.nan
    return max(3 * sd, C_FLOOR) if np.isfinite(sd) else C_FLOOR


def e_process(d, c, margin_bp=MARGIN_BP, lambdas=LAMBDAS):
    """Mixture betting e-process for H0: E[clip(d,-c,c)/c | past] <= margin/c.
    Every week (flat or not) updates; a missing week is not allowed."""
    d = np.asarray(d, float)
    assert np.isfinite(d).all(), "missing forward week"
    assert c >= C_FLOOR
    m = margin_bp / c
    assert 0 <= m <= 1
    x = np.clip(d, -c, c) / c
    factors = [1 + lam * (x - m) for lam in lambdas]
    assert all((f > 0).all() for f in factors)
    return np.mean([np.cumprod(f) for f in factors], axis=0)


def run_fast(R_base, NTR, VALID, INNER, first_w, R_eval=None):
    """Vectorised equivalent of run() for simulations; test_procedure asserts
    identical output. Column t of SD / Z uses only columns < t / <= t."""
    R_eval = R_eval or {"base": R_base}
    n_tools, n = R_base.shape
    SD = np.full((n_tools, n), np.nan)
    for t in range(SCALE_W, n):
        SD[:, t] = scale_at(R_base, VALID, t)
    Z = R_base / np.maximum(SD, SD_FLOOR)
    Z[~VALID | ~np.isfinite(SD)] = np.nan
    ACT = np.cumsum(np.c_[np.zeros(n_tools), NTR > 0], axis=1)
    ws = np.arange(first_w, n)
    choice = np.full(len(ws), -1); size = np.zeros(len(ws))
    ELIG = np.zeros((n_tools, len(ws)), bool); SIZES = np.full((n_tools, len(ws)), np.nan)
    for k, w in enumerate(ws):
        zz = Z[:, w - SCORE_W:w][:, ::-1] if w >= SCORE_W else np.full((n_tools, SCORE_W), np.nan)
        active = ACT[:, w] - ACT[:, max(0, w - SCORE_W)]
        e = (np.isfinite(zz).all(axis=1) & np.isfinite(SD[:, w])
             & (active >= MIN_ACTIVE) & VALID[:, w])
        ELIG[:, k] = e
        outer = np.minimum(CAP / np.maximum(INNER[:, w], 1e-9),
                           TARGET / np.maximum(SD[:, w], SD_FLOOR))
        SIZES[e, k] = outer[e]
        if e.any():
            sc = np.where(e, (np.nan_to_num(zz) * _A).sum(axis=1) / _A.sum(), -np.inf)
            b = int(np.argmax(sc))
            if sc[b] > 0:
                choice[k], size[k] = b, outer[b]
    res = dict(w=ws, choice=choice, size=size, n_elig=ELIG.sum(axis=0))
    for key, R in R_eval.items():
        Rw = R[:, ws]
        menu = np.where(ELIG.any(axis=0),
                        np.nansum(np.where(ELIG, SIZES * Rw, 0.0), axis=0)
                        / np.maximum(ELIG.sum(axis=0), 1), 0.0)
        P = np.where(choice >= 0, size * Rw[np.maximum(choice, 0), np.arange(len(ws))], 0.0)
        B = np.where(choice >= 0, menu, 0.0)
        res[key] = dict(P=P, Bp=menu, B=B, d=P - menu, d_cond=P - B)
    return res
