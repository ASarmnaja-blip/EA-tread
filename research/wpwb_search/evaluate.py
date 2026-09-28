"""Weekly evaluation, controls, and look-ahead audit for the WPWB search."""
from __future__ import annotations

import copy

import numpy as np

import approaches as AP
import common as C
import data as D


def _rtime_expectation(m, trades, pool, stress):
    dd = np.array([t[2] for t in trades])
    if isinstance(pool, tuple) and pool and pool[0] == "entries":
        _, lo, hi = pool
        total = 0.0
        cache = {}
        for i, k, d in trades:
            length = k - i + 1
            if length not in cache:
                ent = np.arange(lo, hi)
                ex = np.array([m.exit_index(e, length, hi) for e in ent])
                cache[length] = (m.pnl_bp(ent, ex, np.ones(len(ent), int), stress).mean(),
                                 m.pnl_bp(ent, ex, -np.ones(len(ent), int), stress).mean())
            ml, ms = cache[length]
            total += ml if d > 0 else ms
        return total
    if pool:
        pi = np.array([p[0] for p in pool]); pk = np.array([p[1] for p in pool])
        ml = m.pnl_bp(pi, pk, np.ones(len(pi), int), stress).mean()
        ms = m.pnl_bp(pi, pk, -np.ones(len(pi), int), stress).mean()
        return (dd > 0).sum() * ml + (dd < 0).sum() * ms
    return np.nan


def weekly_series(fam, params, m, cuts, stress, eff_cache, runner=None):
    """Per-week sums (bp): strategy, LONG, RDIR, RTIME; plus trade counts."""
    n = len(cuts)
    strat = np.zeros(n); lng = np.zeros(n); rdir = np.zeros(n); rtime = np.zeros(n)
    ntr = np.zeros(n, int)
    for w, cut in enumerate(cuts):
        if runner is None:
            trades, pool = AP.run_week(fam, m, int(cut), params, eff_cache)
        else:
            trades, pool = runner(fam, m, int(cut), params)
        if not trades:
            continue
        ii = np.array([t[0] for t in trades]); kk = np.array([t[1] for t in trades])
        dd = np.array([t[2] for t in trades])
        pl = m.pnl_bp(ii, kk, np.ones_like(dd), stress)
        ps = m.pnl_bp(ii, kk, -np.ones_like(dd), stress)
        strat[w] = np.where(dd > 0, pl, ps).sum()
        lng[w] = pl.sum()
        rdir[w] = (0.5 * (pl + ps)).sum()
        rtime[w] = _rtime_expectation(m, trades, pool, stress)
        ntr[w] = len(trades)
    return dict(strat=strat, long=lng, rdir=rdir, rtime=rtime, ntr=ntr)


def controls_for(fam):
    return ("long", "rdir") if fam == "A" else ("long", "rdir", "rtime")


def summarize(fam, s, controls=None):
    out = dict(weeks=len(s["strat"]), active=float((s["ntr"] > 0).mean()),
               trades=int(s["ntr"].sum()), mean_week_bp=float(s["strat"].mean()))
    worst_t, worst_p = np.inf, 0.0
    for c in (controls or controls_for(fam)):
        diff = s["strat"] - np.nan_to_num(s[c])
        r = C.block_boot(diff)
        out[f"vs_{c}_mean"] = r["mean"]; out[f"vs_{c}_p"] = r["p"]
        out[f"vs_{c}_t"] = r["t"]; out[f"vs_{c}_ac1"] = r["ac1"]
        if np.isfinite(r["t"]) and r["t"] < worst_t:
            worst_t = r["t"]
        if np.isfinite(r["p"]):
            worst_p = max(worst_p, r["p"])
        else:
            worst_p = 1.0
    out["min_t"] = worst_t; out["max_p"] = worst_p
    return out


# ------------------------------------------------------------------ audit
def mutated_after(m, cut, seed):
    """Copy of Market with every bar starting at/after `cut` replaced by
    garbage (H1 and M5). Anything computed only from pre-cut data is
    unchanged; anything that peeks forward changes."""
    rng = np.random.default_rng(seed)
    mm = copy.copy(m)
    j = int(np.searchsorted(m.t, cut))
    for name in ("o", "h", "l", "c", "sp_in", "sp_out", "atr"):
        a = getattr(m, name).copy()
        a[j:] = rng.uniform(50, 9000, len(a) - j)
        setattr(mm, name, a)
    b5 = m.b5
    j5 = int(np.searchsorted(b5.t, cut))
    c5 = b5.c.copy(); c5[j5:] = rng.uniform(50, 9000, len(c5) - j5)
    mm.b5 = D.Bars(b5.t, b5.o, b5.h, b5.l, c5, b5.v, b5.step, b5.symbol, b5.sp)
    return mm


def audit_lookahead(fam, params, m, cuts, n_checks=25, seed=99, sig=None):
    rng = np.random.default_rng(seed)
    picks = rng.choice(cuts, size=min(n_checks, len(cuts)), replace=False)
    sig = sig or (lambda f, mm, c, p: AP.tool_signature(f, mm, c, p, {}))
    bad = []
    for cut in picks:
        cut = int(cut)
        real = sig(fam, m, cut, params)
        fake = sig(fam, mutated_after(m, cut, seed + cut % 1000), cut, params)
        if real != fake:
            bad.append(cut)
    return bad
