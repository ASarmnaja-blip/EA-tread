"""WRWR gate statistics (docs/WRWR_CONTRACT_PREREG.md v6): stationary bootstrap, studentized White Reality Check,
BASE-alone test, CSCV PBO with embargo and an outer-bootstrap upper bound, cost gate helpers. Pure numpy; no data access."""
from __future__ import annotations

import itertools

import numpy as np


def stationary_indices(T, mean_block, K, rng):
    """K x T matrix of Politis-Romano stationary-bootstrap indices (one set of week indices per replicate)."""
    p = 1.0 / mean_block
    idx = np.empty((K, T), np.int64)
    idx[:, 0] = rng.integers(0, T, K)
    new = rng.random((K, T)) < p
    jump = rng.integers(0, T, (K, T))
    for t in range(1, T):
        idx[:, t] = np.where(new[:, t], jump[:, t], (idx[:, t - 1] + 1) % T)
    return idx


def reality_check(D, mean_block=10, K=999, seed=12345):
    """D: T x J matrix of weekly excess returns d_{j,k}. Studentized White Reality Check (least-favourable recentring).
    Returns dict(t=per-config t, V=max t, p=family p, p_each=per-config one-sided p, mean=mean d, lb95_each=per-config
    95% lower bound of the mean)."""
    D = np.asarray(D, float)
    T, J = D.shape
    rng = np.random.default_rng(seed)
    idx = stationary_indices(T, mean_block, K, rng)
    m = D.mean(0); sd = D.std(0, ddof=1); sd = np.where(sd > 0, sd, np.nan)
    t = m / (sd / np.sqrt(T))
    Vstar = np.empty(K); dmean = np.empty((K, J))
    for b in range(K):
        Db = D[idx[b]]
        mb = Db.mean(0); sb = Db.std(0, ddof=1); sb = np.where(sb > 0, sb, np.nan)
        tb = (mb - m) / (sb / np.sqrt(T))
        Vstar[b] = np.nanmax(tb); dmean[b] = mb - m
    V = np.nanmax(t)
    p = (1 + np.sum(Vstar >= V)) / (K + 1)
    p_each = (1 + (dmean >= m[None, :]).sum(0)) / (K + 1)
    lb95 = m - np.quantile(dmean, 0.95, axis=0)
    return dict(t=t, V=float(V), p=float(p), p_each=p_each, mean=m, lb95_each=lb95, Vstar=Vstar, T=T, K=K)


def lower_bound_mean(x, mean_block=10, K=999, seed=777):
    """One-sided 95% stationary-bootstrap lower bound of mean(x) and the point estimate."""
    x = np.asarray(x, float)
    rng = np.random.default_rng(seed)
    idx = stationary_indices(len(x), mean_block, K, rng)
    bm = x[idx].mean(1)
    return float(x.mean() - np.quantile(bm - x.mean(), 0.95)), float(x.mean())


def _block_ranges(T, nblocks):
    T2 = T - T % nblocks
    bl = T2 // nblocks
    start = T - T2
    return [(start + i * bl, start + (i + 1) * bl) for i in range(nblocks)]


_SPLITS = {}


def _splits(nblocks):
    if nblocks not in _SPLITS:
        half = nblocks // 2
        combos = np.array(list(itertools.combinations(range(nblocks), half)))
        test = np.zeros((len(combos), nblocks), bool)
        test[np.arange(len(combos))[:, None], combos] = True
        _SPLITS[nblocks] = test
    return _SPLITS[nblocks]


def pbo(R, nblocks=16, embargo=5):
    """CSCV probability of backtest overfitting. R: T x J weekly returns. Splits: all C(nblocks, nblocks/2); in-sample =
    training blocks with `embargo` weeks removed from each training-block edge touching a test block. Returns
    (pbo, lambdas). Vectorised over splits."""
    R = np.asarray(R, float)
    T, J = R.shape
    rng_ = _block_ranges(T, nblocks)
    cs = np.vstack([np.zeros((1, J)), np.cumsum(R, axis=0)])
    test = _splits(nblocks); S = len(test)
    ins = np.zeros((S, J)); nin = np.zeros(S)
    oos = np.zeros((S, J)); nout = np.zeros(S)
    for i, (a, b) in enumerate(rng_):
        full = cs[b] - cs[a]
        left = cs[b] - cs[min(a + embargo, b)]          # first `embargo` weeks dropped (previous block is a test block)
        right = cs[max(b - embargo, a)] - cs[a]         # last `embargo` weeks dropped (next block is a test block)
        both = cs[max(b - embargo, a + embargo)] - cs[a + embargo] if b - a > 2 * embargo else np.zeros(J)
        lt = np.zeros(S, bool) if i == 0 else test[:, i - 1]
        rt = np.zeros(S, bool) if i == nblocks - 1 else test[:, i + 1]
        tr = ~test[:, i]
        sel_both, sel_l, sel_r = tr & lt & rt, tr & lt & ~rt, tr & ~lt & rt
        sel_full = tr & ~lt & ~rt
        ins += sel_full[:, None] * full + sel_l[:, None] * left + sel_r[:, None] * right + sel_both[:, None] * both
        n_full, n_one, n_both = b - a, b - a - embargo, max(b - a - 2 * embargo, 0)
        nin += sel_full * n_full + (sel_l | sel_r) * n_one + sel_both * n_both
        oos += test[:, i][:, None] * full; nout += test[:, i] * (b - a)
    best = np.argmax(ins / np.maximum(nin, 1)[:, None], axis=1)
    oo = oos / np.maximum(nout, 1)[:, None]
    ref = oo[np.arange(S), best][:, None]
    rank = 1 + (oo < ref).sum(1)                                 # 1 = worst ... J = best
    omega = rank / (J + 1)
    lam = np.log(omega / (1 - omega))
    return float(np.mean(lam <= 0)), lam


def pbo_upper(R, nblocks=16, embargo=5, mean_block=10, K=999, seed=2024):
    """95% upper bound of PBO from K stationary-bootstrap resamples of the week axis (PBO recomputed on each)."""
    R = np.asarray(R, float)
    rng = np.random.default_rng(seed)
    idx = stationary_indices(len(R), mean_block, K, rng)
    vals = np.array([pbo(R[idx[b]], nblocks, embargo)[0] for b in range(K)])
    return float(np.quantile(vals, 0.95)), vals
