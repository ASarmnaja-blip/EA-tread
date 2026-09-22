"""Vectorised engine for a search over thousands of configurations.

The 150-way search took minutes because every candidate re-walked the same M5
bars for the same placebo pools. A 3,000-way search cannot be done that way at
all, so the work is turned inside out: everything that depends only on a BAR is
computed once, and a candidate then costs little more than an array lookup.

Precomputed per M15 bar i and per side d:

    G[d][i]    gross R of entering at bar i on side d
    NET[d][i]  the same after every measured cost, charged per trade
    NB[d][i]   M5 bars held, which is what enforces one-position-at-a-time

That is 2 x 70,000 forward walks, done once, instead of millions.

THE CONTROL. The earlier searches drew 20 random placebos per entry from the
entry's stratum. Here the control is the stratum's FULL POOL MEAN, which is the
same estimator with the sampling noise removed - the limit of the 20-draw version
as the draws go to infinity. It is not a new degree of freedom: there is nothing
to choose once the strata are fixed, no seed, and no way to tune it. It is also
what makes the search vectorisable.

THE PERMUTATION. For a day-clustered t,

    mu = mean(e),  se = sqrt(sum_d (S_d - n_d*mu)^2) / n

where S_d is the sum of a candidate's excesses on day d and n_d the count. Under
a sign flip applied to whole DAYS, e_i -> f_d * e_i, so S_d -> f_d * S_d while
n_d is unchanged. Therefore

    mu(f) = (sum_d f_d S_d) / n      se(f) = sqrt(sum_d (f_d S_d - n_d mu)^2)/n

and the permuted statistic depends ONLY on the per-day sums and counts, never on
the individual trades. So the whole family becomes two matrix-vector products
against a (candidates x days) matrix, and 3,000 candidates x 1,000 draws is
seconds rather than hours. This is exact, not an approximation.

Flipping whole days, and the same day for every candidate at once, is what
preserves both the within-day dependence and the correlation between candidates
that share components.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import core
import data as D


class Pre:
    """Per-bar outcomes, plus the stratum control."""

    __slots__ = ("G", "NET", "NB", "ctl", "key", "day", "ok")

    def __init__(self, G, NET, NB, ctl, key, day, ok):
        self.G, self.NET, self.NB = G, NET, NB
        self.ctl, self.key, self.day, self.ok = ctl, key, day, ok


def precompute(b5: D.Bars, b15: D.Bars, nxt: np.ndarray, atr: np.ndarray,
               stop_atr: float, rr: float, time_stop: int,
               spread_fallback: float, commission_rt: float,
               slip_per_fill: float, swap_long: float, swap_short: float = 0.0,
               rollover_h: int = 21, cost_mult: float = 1.0) -> Pre:
    n = len(b15)
    G = {1: np.full(n, np.nan), -1: np.full(n, np.nan)}
    NET = {1: np.full(n, np.nan), -1: np.full(n, np.nan)}
    NB = {1: np.zeros(n, np.int32), -1: np.zeros(n, np.int32)}
    ok = np.zeros(n, bool)
    day = np.zeros(n, np.int64)
    sp_arr = b5.sp
    for i in range(n):
        k = int(nxt[i])
        a = atr[i]
        if k < 0 or not np.isfinite(a) or a <= 0:
            continue
        risk = stop_atr * float(a)
        entry = b5.o[k]
        t0 = int(b5.t[k])
        day[i] = t0 // 86400
        ok[i] = True
        sp = (float(sp_arr[k]) if sp_arr is not None and np.isfinite(sp_arr[k])
              and sp_arr[k] > 0 else spread_fallback)
        cost = cost_mult * (sp + commission_rt + 2.0 * slip_per_fill)
        for d in (1, -1):
            stop, target = entry - d * risk, entry + d * rr * risk
            px, _, nb = core.resolve(b5, k, d, entry, stop, target, time_stop)
            g = d * (px - entry) / risk
            net = g - cost / risk
            sw = swap_long if d > 0 else swap_short
            if sw:
                t1 = t0 + nb * b5.step
                h0 = (t0 // 3600) % 24
                cur = t0 - (t0 % 3600) + ((rollover_h - h0) % 24) * 3600
                nights = 0
                while cur <= t1:
                    nights += 1
                    cur += 86400
                net -= nights * sw / risk
            G[d][i], NET[d][i], NB[d][i] = g, net, nb
    return Pre(G, NET, NB, None, None, day, ok)


def attach_control(pre: Pre, key: np.ndarray, pool: dict,
                   min_pool: int = 30) -> None:
    """The stratum's LEAVE-ONE-DAY-OUT pool mean gross, per side.

    Amendment 10 section 4. The first draft used the stratum's full-pool mean,
    which includes the focal trade and the rest of its calendar day, so a
    candidate was being scored against a benchmark it had helped build. Removing
    only the focal trade is not enough: trades on one day share the same session,
    the same news and often the same move, so the whole day comes out.

    Computed as (stratum total - that day's contribution within the stratum)
    over (stratum count - that day's count), which stays vectorised. A bar whose
    remaining pool falls below `min_pool` gets NaN and is reported unmatched
    rather than matched against a handful of bars.

    Because calendar quarter is one of the strata, a pool never reaches more than
    three months from its focal bar. That bounds, and does not eliminate, the use
    of later observations in an earlier benchmark - a limitation Amendment 10
    records rather than claims to have solved.
    """
    ctl = {}
    day = pre.day
    for d in (1, -1):
        g = pre.G[d]
        m = np.full(len(key), np.nan)
        for s, members in pool.items():
            vals = g[members]
            fin = np.isfinite(vals)
            if fin.sum() < min_pool + 1:
                continue
            mem, vv = members[fin], vals[fin]
            dd = day[mem]
            uniq, inv = np.unique(dd, return_inverse=True)
            tot, cnt = vv.sum(), float(len(vv))
            day_sum = np.bincount(inv, weights=vv, minlength=len(uniq))
            day_cnt = np.bincount(inv, minlength=len(uniq)).astype(float)
            rem_n = cnt - day_cnt
            with np.errstate(invalid="ignore", divide="ignore"):
                loo = np.where(rem_n >= min_pool,
                               (tot - day_sum) / np.where(rem_n > 0, rem_n, np.nan),
                               np.nan)
            # every bar in this stratum takes the value for ITS day
            lut = dict(zip(uniq.tolist(), loo.tolist()))
            sel = np.nonzero(key == s)[0]
            m[sel] = [lut.get(int(day[i]), np.nan) for i in sel]
        ctl[d] = m
    pre.ctl = ctl
    pre.key = key


def score(entries, pre: Pre, lo_i: int, hi_i: int, invert: bool = False):
    """Day-clustered matched excess for one candidate.

    The loop is sequential only because one-position-at-a-time is sequential;
    everything inside it is an array lookup.
    """
    ex, dys = [], []
    unmatched = 0
    busy_until = -1
    for (i, d0) in entries:
        if i < lo_i or i >= hi_i or not pre.ok[i]:
            continue
        if i <= busy_until:
            continue
        d = -d0 if invert else d0
        g = pre.G[d][i]
        c = pre.ctl[d][i]
        nb = int(pre.NB[d][i])
        # advance the block whether or not the entry is usable, so an unmatched
        # bar cannot let a later overlapping one through
        busy_until = i + max(1, nb // 3)
        if not np.isfinite(g) or not np.isfinite(c):
            unmatched += 1
            continue
        ex.append(g - c)
        dys.append(pre.day[i])
    if len(ex) < 3:
        return None
    e = np.asarray(ex)
    dd = np.asarray(dys, np.int64)
    return dict(excess=e, days=dd, n=len(e), unmatched=unmatched)


def day_t(e: np.ndarray, dayidx: np.ndarray, ndays: int):
    """Day-clustered mean, SE and t, with the G/(G-1) finite-cluster correction
    that Amendment 10 section 5 requires and the first draft dropped."""
    n = len(e)
    mu = e.mean()
    sums = np.bincount(dayidx, weights=e, minlength=ndays)
    cnts = np.bincount(dayidx, minlength=ndays)
    g = int((cnts > 0).sum())
    resid = sums - cnts * mu
    corr = g / (g - 1) if g > 1 else 1.0
    se = np.sqrt(corr * (resid ** 2).sum()) / n
    return float(mu), float(se), (float(mu / se) if se > 0 else np.nan)


def family_permutation(cands: dict, draws: int = 1000, seed: int = 20260922):
    """maxT and marginal permutation p values for the whole family at once.

    Returns the observed t vector, the maxT null distribution, the family-wise
    p per candidate, the marginal p per candidate, and Benjamini-Hochberg
    q values on the marginal p.
    """
    names = list(cands)
    all_days = sorted({int(d) for k in names for d in cands[k]["days"]})
    dpos = {d: j for j, d in enumerate(all_days)}
    nd = len(all_days)
    nc = len(names)

    S = np.zeros((nc, nd))
    N = np.zeros((nc, nd))
    ntr = np.zeros(nc)
    for r, k in enumerate(names):
        v = cands[k]
        ix = np.asarray([dpos[int(d)] for d in v["days"]])
        np.add.at(S[r], ix, v["excess"])
        np.add.at(N[r], ix, 1.0)
        ntr[r] = v["n"]

    gcl = (N > 0).sum(axis=1).astype(float)              # active days
    corr = np.where(gcl > 1, gcl / np.maximum(gcl - 1, 1e-9), 1.0)

    def tvec(f):
        Sf = S * f                      # (nc, nd)
        mu = Sf.sum(axis=1) / ntr
        resid = Sf - N * mu[:, None]
        se = np.sqrt(corr * (resid ** 2).sum(axis=1)) / ntr
        with np.errstate(divide="ignore", invalid="ignore"):
            return np.where(se > 0, mu / se, 0.0), mu, se

    t_obs, mu_obs, se_obs = tvec(np.ones(nd))
    a_obs = np.abs(t_obs)

    rng = np.random.default_rng(seed)
    ge_marg = np.zeros(nc)
    maxnull = np.empty(draws)
    bjnull = np.empty(draws)
    nullmat = np.empty((draws, nc), dtype=np.float32)
    for j in range(draws):
        f = rng.choice([-1.0, 1.0], size=nd)
        tn, _, _ = tvec(f)
        an = np.abs(tn)
        nullmat[j] = an
        maxnull[j] = an.max()
        ge_marg += (an >= a_obs)

    p_marg = (ge_marg + 1.0) / (draws + 1.0)
    p_fwer = np.array([(np.sum(maxnull >= a) + 1.0) / (draws + 1.0)
                       for a in a_obs])

    # Berk-Jones, calibrated from the SAME permutation draws. It is the
    # companion to max|t|: max|t| detects one candidate genuinely different,
    # Berk-Jones detects many slightly shifted. Its analytical
    # independent-test distribution is unusable on a family this correlated, so
    # the statistic is recomputed on every draw and the observed value is read
    # against that empirical distribution.
    pooled = np.sort(nullmat.ravel())          # sorted ONCE, not per call
    npool = float(pooled.size)
    rk = np.arange(1, nc + 1) / nc

    def berk_jones(avals):
        """How far the family's ordered |t| values sit above what the null
        produces, measured by the largest binomial deviation over all ranks.

        `phat` is each ordered value's tail probability under the pooled
        permutation null, so no independence assumption enters; the statistic is
        then read against its own permutation distribution.
        """
        srt = np.sort(avals)[::-1]
        tail = np.searchsorted(pooled, srt, side="left")
        phat = np.clip(1.0 - tail / npool, 1e-12, 1 - 1e-12)
        with np.errstate(invalid="ignore", divide="ignore"):
            kl = (rk * np.log(rk / phat)
                  + (1 - rk) * np.log((1 - rk) / (1 - phat)))
        return float(np.nanmax(np.where(rk > phat, nc * kl, 0.0)))

    bj_obs = berk_jones(a_obs)
    for j in range(draws):
        bjnull[j] = berk_jones(nullmat[j].astype(np.float64))
    p_bj = (np.sum(bjnull >= bj_obs) + 1.0) / (draws + 1.0)

    # Benjamini-Hochberg, DESCRIPTIVE ONLY. Amendment 10 section 5: BH needs
    # independence or positive regression dependence, and a family holding both
    # agreement and contradiction stacks of the same tools has negative and
    # non-monotone relationships. Reported as a sensitivity readout, never as
    # formal FDR control.
    order = np.argsort(p_marg)
    q = np.empty(nc)
    prev = 1.0
    for rank in range(nc - 1, -1, -1):
        j = order[rank]
        prev = min(prev, p_marg[j] * nc / (rank + 1))
        q[j] = min(1.0, prev)

    return dict(names=names, t=t_obs, mu=mu_obs, se=se_obs, gcl=gcl,
                p_marg=p_marg, p_fwer=p_fwer, q=q, maxnull=maxnull,
                crit=float(np.percentile(maxnull, 95)), draws=draws, ndays=nd,
                bj=bj_obs, p_bj=float(p_bj), nullmat=nullmat)


def stepdown_maxt(t_obs: np.ndarray, nullmat: np.ndarray) -> np.ndarray:
    """Westfall-Young step-down maxT adjusted p values.

    Amendment 10 section 7 requires this rather than a raw threshold for the
    CONFIRM hypotheses. Single-step maxT judges every hypothesis against the
    maximum over the WHOLE family, which is needlessly conservative for the
    ones ranked below the top; the step-down version shrinks the comparison set
    as it descends, and keeps family-wise control by enforcing monotonicity.
    """
    a = np.abs(t_obs)
    order = np.argsort(-a)
    adj = np.empty(len(a))
    running = 0.0
    for pos, j in enumerate(order):
        sub = nullmat[:, order[pos:]]
        p = (np.sum(sub.max(axis=1) >= a[j]) + 1.0) / (nullmat.shape[0] + 1.0)
        running = max(running, p)
        adj[j] = min(1.0, running)
    return adj


def net_of(entries, pre: Pre, lo_i: int, hi_i: int, invert: bool = True):
    """Net expectancy per trade of the (by default mirrored) candidate, with
    every measured cost already charged per trade inside NET."""
    vals, dys = [], []
    busy_until = -1
    for (i, d0) in entries:
        if i < lo_i or i >= hi_i or not pre.ok[i] or i <= busy_until:
            continue
        d = -d0 if invert else d0
        nb = int(pre.NB[d][i])
        busy_until = i + max(1, nb // 3)
        x = pre.NET[d][i]
        if np.isfinite(x):
            vals.append(x)
            dys.append(pre.day[i])
    if len(vals) < 3:
        return None
    v = np.asarray(vals)
    dd = np.asarray(dys, np.int64)
    uniq = {d: j for j, d in enumerate(sorted(set(dd.tolist())))}
    ix = np.asarray([uniq[int(d)] for d in dd])
    mu, se, t = day_t(v, ix, len(uniq))
    return dict(n=len(v), net=mu, se=se, t=t, days=len(uniq))
