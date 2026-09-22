"""Stratified direction-matched placebo controls, per Amendment 08 section 6.5.

WHY THIS MODULE EXISTS. The drift audit measured that a random LONG entry on
XAUUSD at RR 1:1 earns +0.0656 R over 2023-2026 while a random SHORT earns
-0.0507 R, a gap of +0.1163 R from nothing but the instrument's 42-percent-a-year
rise. That gap is LARGER than the long-minus-short gap of every pattern the
inverse search examined. So a raw expectancy on this sample measures mostly the
direction, and any search scored on raw expectancy will keep rediscovering the
bull market and calling it a pattern.

The fix is to score a candidate against what a random trade would have earned
UNDER THE SAME CIRCUMSTANCES. The strata below are Codex's list, frozen in
Amendment 08 section 6.5 before either search that uses them ran:

    direction, holding horizon and exit mechanics, calendar quarter, session,
    ATR tercile from prior bars, news state inside/outside 30 minutes of a USD
    HIGH release, hourly spread bucket, and the same one-position restriction

Two notes on what this control can and cannot do:

  * It removes drift, volatility, session, news-proximity and cost-environment
    selection. It does NOT remove cost: the candidate and its placebo pay the
    same cost, so cost cancels out of the EXCESS and has to be charged
    separately when asking whether a mirror is tradeable. Amendment 08 section
    6.3 requires both tests, and this module supplies the first.
  * Placebos are drawn independently of one another while the candidate's own
    entries respect one-position-at-a-time. That asymmetry is deliberate: each
    placebo is a control for ONE entry, so overlap between placebos is not a
    quantity that means anything. What matters is that each placebo faces the
    same stratum as the entry it stands in for.

An entry whose stratum holds too few eligible bars is reported UNMATCHED and
excluded, with the count printed by the caller. It is never quietly matched on
fewer variables.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import core
import data as D

DRAWS_PER_ENTRY = 20          # Amendment 08 section 6.5, fixed in advance
SEED = 20260922               # likewise
MIN_POOL = 30                 # a stratum smaller than this cannot be matched


class Strata:
    """Per-M15-bar stratum labels, plus the pools drawn from."""

    __slots__ = ("key", "pool", "labels")

    def __init__(self, key, pool, labels):
        self.key = key            # integer stratum id per bar, -1 = ineligible
        self.pool = pool          # stratum id -> np.ndarray of bar indices
        self.labels = labels      # stratum id -> human-readable tuple


def build_strata(b15: D.Bars, atr: np.ndarray, prof: np.ndarray | None,
                 news_ep: np.ndarray | None, lo_i: int, hi_i: int) -> Strata:
    """Label every bar in [lo_i, hi_i) by the strata Amendment 08 fixed.

    `prof` is the hourly spread profile; it stands in for the cost environment,
    which on this account varies by hour far more than by anything else.
    """
    n = len(b15)
    t = b15.t.astype(np.int64)
    hours = (t // 3600) % 24

    q = pd.to_datetime(t, unit="s", utc=True).tz_localize(None).to_period("Q")
    qstr = np.asarray(q.astype(str))
    qcode = pd.Series(qstr).astype("category").cat.codes.to_numpy()

    # session, by the same boundaries the rest of the pilot uses
    sess = np.where(hours < 7, 0, np.where(hours < 13, 1, 2))

    # ATR tercile from PRIOR bars only, so a label never sees its own bar
    ar = pd.Series(atr).shift(1).rolling(2880, min_periods=480)
    q33 = ar.quantile(0.33).to_numpy()
    q67 = ar.quantile(0.67).to_numpy()
    with np.errstate(invalid="ignore"):
        vt = np.where(atr <= q33, 0, np.where(atr >= q67, 2, 1))
    vt = np.where(np.isfinite(q33) & np.isfinite(q67), vt, -1)

    # news state: inside or outside 30 minutes of a USD HIGH release
    news = np.zeros(n, dtype=int)
    if news_ep is not None and len(news_ep):
        nx = np.searchsorted(news_ep, t, "left")
        pv = nx - 1
        to_n = np.where(nx < len(news_ep),
                        (news_ep[np.minimum(nx, len(news_ep) - 1)] - t) / 60,
                        1e9)
        since = np.where(pv >= 0, (t - news_ep[np.maximum(pv, 0)]) / 60, 1e9)
        news = ((to_n <= 30) | (since <= 30)).astype(int)

    # cost environment: the hourly spread profile, bucketed into terciles
    if prof is not None and len(prof) == 24:
        edges = np.nanpercentile(prof, [33, 67])
        cb = np.digitize(prof[hours], edges)
    else:
        cb = np.zeros(n, dtype=int)

    ok = np.zeros(n, dtype=bool)
    ok[lo_i:hi_i] = True
    ok &= np.isfinite(atr) & (atr > 0) & (vt >= 0)

    key = np.full(n, -1, dtype=np.int64)
    composite = (qcode.astype(np.int64) * 1000 + sess * 100 + vt * 10
                 + news * 5 + cb)
    key[ok] = composite[ok]

    pool = {}
    labels = {}
    idx = np.nonzero(ok)[0]
    for s in np.unique(key[ok]):
        members = idx[key[idx] == s]
        if len(members) >= MIN_POOL:
            pool[int(s)] = members
            j = int(members[0])
            labels[int(s)] = (qstr[j], int(sess[j]), int(vt[j]),
                              int(news[j]), int(cb[j]))
    return Strata(key, pool, labels)


def run_once(b5: D.Bars, k: int, d: int, risk: float, rr: float,
             time_stop: int):
    """Gross R and bars held for one trade, resolved worst-case.

    core.resolve tests the stop before the target on every bar, so a bar that
    could have hit both is booked as a loss. That rule applies to the candidate
    and to the placebo alike, which is what stops an inversion from harvesting
    ambiguity it has no information about.
    """
    if k < 0 or k >= len(b5) or risk <= 0:
        return None, 0
    entry = b5.o[k]
    stop = entry - d * risk
    target = entry + d * rr * risk
    px, _, nb = core.resolve(b5, k, d, entry, stop, target, time_stop)
    return d * (px - entry) / risk, nb


def make_runner(b5: D.Bars, nxt: np.ndarray, atr: np.ndarray,
                stop_atr: float, rr: float, time_stop: int):
    """A memoised (bar, direction) -> (gross R, bars held) resolver.

    The outcome of a trade entered at bar `i` in direction `d` is fully
    determined by the bar and the side, because the risk is stop_atr x atr[i]
    and the geometry is fixed. So it can be computed once and reused.

    This matters for feasibility rather than for tidiness. Scoring 150
    configurations against 20 placebos each would otherwise repeat the same
    forward walk hundreds of thousands of times, since the placebo pools overlap
    heavily between candidates. With the cache the whole search touches each
    (bar, side) at most once.
    """
    cache: dict = {}

    def run(i: int, d: int):
        key = (int(i), int(d))
        v = cache.get(key)
        if v is None:
            k = int(nxt[i])
            a = atr[i]
            if k < 0 or not np.isfinite(a) or a <= 0:
                v = (None, 0)
            else:
                v = run_once(b5, k, d, stop_atr * float(a), rr, time_stop)
            cache[key] = v
        return v

    run.cache = cache
    return run


def matched_excess(entries, st: Strata, b5: D.Bars, nxt: np.ndarray,
                   atr: np.ndarray, stop_atr: float, rr: float,
                   time_stop: int, draws: int = DRAWS_PER_ENTRY,
                   seed: int = SEED, invert: bool = False,
                   runner=None) -> dict:
    """Each entry's gross minus the mean gross of `draws` placebos drawn from
    the SAME stratum and taking the SAME side.

    `invert` mirrors the candidate's direction; the placebos mirror with it, so
    the comparison stays like-for-like. Per-entry excesses and their calendar
    days are returned so the caller can cluster by day.
    """
    rng = np.random.default_rng(seed)
    ex, days, own, ctl = [], [], [], []
    unmatched = 0
    busy_until = -1
    for (i, d0) in entries:
        k = nxt[i]
        if k < 0 or k <= busy_until:
            continue
        members = st.pool.get(int(st.key[i]))
        a = atr[i]
        if members is None or not np.isfinite(a) or a <= 0:
            unmatched += 1
            continue
        d = -d0 if invert else d0
        g, nb = run_once(b5, k, d, stop_atr * a, rr, time_stop)
        if g is None:
            unmatched += 1
            continue
        picks = rng.choice(members, size=min(draws, len(members)),
                           replace=False)
        vals = []
        for j in picks:
            aj = atr[int(j)]
            if not np.isfinite(aj) or aj <= 0:
                continue
            gj, _ = run_once(b5, nxt[int(j)], d, stop_atr * aj, rr, time_stop)
            if gj is not None:
                vals.append(gj)
        if len(vals) < 5:
            unmatched += 1
            continue
        c = float(np.mean(vals))
        ex.append(g - c)
        own.append(g)
        ctl.append(c)
        days.append(int(b5.t[k]) // 86400)
        busy_until = k + nb          # one position at a time for the candidate
    if not ex:
        return dict(n=0, unmatched=unmatched)
    e = np.asarray(ex, float)
    dy = np.asarray(days, np.int64)
    mu = float(e.mean())
    grp = pd.Series(e - mu).groupby(dy).sum().to_numpy()
    se = float(np.sqrt((grp ** 2).sum())) / len(e)
    return dict(n=len(e), unmatched=unmatched, excess=mu, se=se,
                own=float(np.mean(own)), control=float(np.mean(ctl)),
                t=(mu / se if se > 0 else np.nan), per_trade=e, days=dy,
                clusters=len(grp))


def maxt_permutation(per_candidate: dict, draws: int = 2000,
                     seed: int = SEED) -> dict:
    """Permutation maxT across candidates, per Amendment 08 section 6.4.

    Separate Bonferroni tests are the wrong shape here because the candidates
    overlap heavily in time and are therefore correlated, so Bonferroni
    overcorrects by an unknown amount. maxT builds the null of the LARGEST |t|
    across the whole family by flipping the sign of each DAY's contribution at
    random. The same day flips for every candidate at once, which is what
    preserves the correlation between them - that is the whole point, and it is
    why this is reported alongside Bonferroni rather than instead of it.
    """
    rng = np.random.default_rng(seed)
    names = [k for k, v in per_candidate.items() if v.get("n", 0) > 0]
    if not names:
        return dict(names=[], observed={}, p={}, crit=float("nan"))
    all_days = sorted({int(d) for k in names for d in per_candidate[k]["days"]})
    dpos = {d: j for j, d in enumerate(all_days)}
    pos = {k: np.asarray([dpos[int(d)] for d in per_candidate[k]["days"]])
           for k in names}
    obs = {}
    for k in names:
        v = per_candidate[k]
        obs[k] = abs(v["t"]) if np.isfinite(v["t"]) else 0.0
    nulls = []
    for _ in range(draws):
        flip = rng.choice([-1.0, 1.0], size=len(all_days))
        best = 0.0
        for k in names:
            v = per_candidate[k]
            e = v["per_trade"] * flip[pos[k]]
            mu = float(e.mean())
            grp = pd.Series(e - mu).groupby(v["days"]).sum().to_numpy()
            se = float(np.sqrt((grp ** 2).sum())) / len(e)
            if se > 0:
                best = max(best, abs(mu / se))
        nulls.append(best)
    nu = np.asarray(nulls)
    return dict(names=names, observed=obs,
                p={k: float(np.mean(nu >= obs[k])) for k in names},
                crit=float(np.percentile(nu, 95)), draws=len(nu))
