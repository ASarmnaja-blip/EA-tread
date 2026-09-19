#!/usr/bin/env python3
"""Eight controls, each removing one more explanation that is not direction.

WHAT A CONTROL IS FOR

  A rule's expectancy is not evidence of anything on its own, because the
  instrument it is measured through has its own expectancy. The bracket loses
  0.09R to 0.12R per trade on random timing at zero cost; the spread costs
  more; and a rule that only fires when the market is moving collects a
  different slice of the tape than one that fires anywhere.

  A control is a second book that shares everything with the rule except the
  one thing being tested. The difference between them is the only number
  worth reading, and it means exactly as much as the control is strong.

WHY THE EXISTING CONTROLS WERE NOT ENOUGH, MEASURED

  Two defects, both found by measurement rather than reading:

  1. random_like takes the RANDOM bar's own high or low as the invalidation
     level. The rule's level comes from a breakout bar and sits far away; the
     random bar is an ordinary bar and its level sits close. Measured on gold
     momentum, dist/ATR has median 1.638 for the rule and 0.559 for the
     control. R is (exit - entry)/dist, so the control's returns are scaled up
     roughly threefold. That is not a different entry, it is a different
     instrument. Every figure in bracket_bias, wider_stop, value_area_setups
     and vol_matched_control was read across that gap.

  2. run_e01_control matches the risk ratio but draws its timing uniformly, so
     it spends part of its life in bars where nothing happens. The rule never
     does. Measured across four families, 91% of the apparent skill was that
     difference and not direction.

  Both are fixed here the same way: the control never invents its own
  geometry. It inherits each real signal's dist/ATR ratio and rebuilds an
  invalidation level at that ratio on the donor bar, so the two books have the
  same risk shape by construction and differ only in WHEN and WHICH WAY.

THE HIERARCHY

  Each level holds constant everything the level above it did, plus one more.

    C0  random time, random direction      the weakest thing that is not the
                                           rule at all
    C1  random time, same directions       removes the direction MIX
    C2  volatility matched                 ambient ATR/price decile
    C3  activity matched                   the signal bar's own TR/ATR decile
    C4  session matched                    hour of day
    C5  C2 + C3 + C4 jointly               the three selection effects at once
    C6  regime matched                     trend/range state as well
    C7  structure-context matched,         the same place in the same market,
        direction randomised               facing a coin

  C7 is the one that answers the question. Everything above it can be beaten
  by a rule that knows only WHEN to be in the market. Only C7 requires knowing
  which way.

THE WORD "SKILL" IS NEVER USED WITHOUT ITS CONTROL

  skill_vs_C1 and skill_vs_C7 are different quantities and the first is not
  evidence for the second. Every report from this module carries the level.

WHAT MATCHING CANNOT FIX

  Matching removes a confounder from the COMPARISON. It cannot remove it from
  the world, and it cannot tell a confounder from a mediator - if the rule
  works BECAUSE it selects volatile bars, and that selection is genuinely
  available, then C2 subtracts the edge rather than the artifact. That is why
  the causal role of each matched variable is recorded at
  registration (see causal_sketch below) and why matching on anything measured
  AFTER the signal is refused outright rather than left to judgement.
"""
import json
import math
import pathlib
import sys

import numpy as np
import pandas as pd

HERE = pathlib.Path(__file__).parent
sys.path.insert(0, str(HERE))
import xauusd_1000_setups as X

LEVELS = ("C0", "C1", "C2", "C3", "C4", "C5", "C6", "C7")

# Variables that exist only after the signal bar closes. Matching on any of
# these conditions the control on the outcome and is refused, not warned
# about: a control matched on the trade's own realised move cannot lose.
POST_SIGNAL = frozenset({
    "realised_move", "forward_return", "mfe", "mae", "exit_price", "hold_bars",
    "outcome", "R", "pnl", "future_atr", "next_bar_range",
})


# =========================================================== features ======
def _safe_ratio(a, b):
    with np.errstate(invalid="ignore", divide="ignore"):
        r = np.asarray(a, float) / np.asarray(b, float)
    return np.where(np.isfinite(r), r, np.nan)


def feat_volatility(P):
    """Ambient volatility: ATR over price. Slow, regime-like."""
    return _safe_ratio(P["A"], P["c"])


def feat_activity(P):
    """How busy THIS bar is relative to normal: true range over ATR.

    Uses the classic true range, not high-low, so a gap counts as movement.
    This is the variable the volatility-matched control in vol_matched_control
    used, and naming it activity rather than volatility is the point: it is
    what a rule that fires on breakouts is really selecting."""
    h, l = np.asarray(P["h"], float), np.asarray(P["l"], float)
    c = np.asarray(P["c"], float)
    pc = np.concatenate([[np.nan], c[:-1]])
    tr = np.nanmax(np.vstack([h - l, np.abs(h - pc), np.abs(l - pc)]), axis=0)
    return _safe_ratio(tr, P["A"])


def feat_session(P):
    """Hour of day in UTC, as an integer label rather than a quantile."""
    idx = pd.DatetimeIndex(P["idx"])
    return idx.hour.to_numpy().astype(float)


def feat_regime(P):
    """Trend against range, as the efficiency ratio over 20 bars.

    |net move| / sum|bar moves|. Near 1 the market went somewhere; near 0 it
    covered the same ground repeatedly. Signed by the EMA stack so an
    uptrend and a downtrend land in different cells - a control matched on
    unsigned trend strength would happily donate a downtrend bar to an
    uptrend signal."""
    c = pd.Series(np.asarray(P["c"], float))
    net = (c - c.shift(20)).abs()
    path = c.diff().abs().rolling(20).sum()
    er = _safe_ratio(net.to_numpy(), path.to_numpy())
    sgn = np.sign(np.asarray(P["ema20"], float) - np.asarray(P["ema50"], float))
    return er * np.where(sgn == 0, 1.0, sgn)


def feat_structure(P):
    """Where price sits inside its own recent range, 0 at the low, 1 at the
    high. The context a breakout or a fade is reacting to."""
    h = pd.Series(np.asarray(P["h"], float)).rolling(50).max().to_numpy()
    l = pd.Series(np.asarray(P["l"], float)).rolling(50).min().to_numpy()
    return _safe_ratio(np.asarray(P["c"], float) - l, h - l)


FEATURES = {
    "volatility": feat_volatility,
    "activity": feat_activity,
    "session": feat_session,
    "regime": feat_regime,
    "structure": feat_structure,
}

# dims matched at each level, and whether direction is inherited or coined.
# The relaxation order is the reverse of this tuple: when a joint cell has no
# donors the LAST dim is dropped first, so the most important match survives
# longest. Session goes first because it is the coarsest and the most likely
# to be genuinely available to a trader anyway.
SPEC = {
    "C0": (("",), "random"),
    "C1": ((), "inherit"),
    "C2": (("volatility",), "inherit"),
    "C3": (("activity",), "inherit"),
    "C4": (("session",), "inherit"),
    "C5": (("activity", "volatility", "session"), "inherit"),
    "C6": (("activity", "volatility", "session", "regime"), "inherit"),
    "C7": (("activity", "volatility", "session", "regime", "structure"),
           "random"),
}

DESCRIPTION = {
    "C0": "random time, random direction",
    "C1": "random time, rule's own direction mix",
    "C2": "matched on ambient volatility (ATR/price decile)",
    "C3": "matched on bar activity (TR/ATR decile)",
    "C4": "matched on session (hour of day)",
    "C5": "matched on activity + volatility + session",
    "C6": "C5 plus trend/range regime (signed efficiency ratio)",
    "C7": "C6 plus position in range, direction randomised",
}

# Quantile counts fall as the number of matched dims rises, because the cell
# count is their product and a cell with two donors is not a match. These were
# chosen so the joint cell count stays near 200 - roughly one cell per 25
# signals on a typical 5,000-signal book - and NOT tuned against any result.
NQ_BY_NDIM = {1: 10, 2: 6, 3: 5, 4: 4, 5: 3}


def causal_sketch(dims):
    """What role each matched variable is being assumed to play.

    Recorded rather than inferred. A variable matched as a CONFOUNDER is one
    believed to drive both the rule's firing and the outcome; matching it
    removes an artifact. A variable matched as a MEDIATOR is one the rule
    works THROUGH; matching it removes the edge itself. The hierarchy is built
    so that reading C1 through C7 shows which of the two each one is - a drop
    that appears at C3 and not before says activity was doing the work, and
    whether that is artifact or edge is then an economic question, not a
    statistical one."""
    roles = {
        "volatility": ("confounder", "ambient volatility raises both the "
                       "chance a rule fires and the size of any move"),
        "activity": ("confounder-or-mediator", "a rule that fires on busy "
                     "bars is selecting movement; whether that selection is "
                     "itself the edge is the open question"),
        "session": ("confounder", "liquidity and spread vary by hour, and so "
                    "does the rate at which most rules fire"),
        "regime": ("confounder-or-mediator", "trend state changes both firing "
                   "rate and the sign of the conditional move"),
        "structure": ("mediator-suspect", "position in range is usually what "
                      "the rule is reading, so matching it may subtract the "
                      "signal rather than a bias"),
    }
    return {d: {"role": roles[d][0], "why": roles[d][1]}
            for d in dims if d in roles}


# ============================================================ matching =====
def _bin(vals, nq, live_mask):
    """Quantile bins fitted on the REAL signals' values, applied to all bars.

    Fitted on the signals rather than the whole sample so the cells are where
    the signals are: quantiles of the full series would put most signals in
    one extreme bin when the rule is selective, which is the case that needs
    resolution most."""
    v = np.asarray(vals, float)
    ref = v[live_mask]
    ref = ref[np.isfinite(ref)]
    if len(ref) < nq * 2:
        return None
    edges = np.unique(np.nanquantile(ref, np.linspace(0, 1, nq + 1)))
    if len(edges) < 3:
        return None
    edges[0], edges[-1] = -np.inf, np.inf
    out = np.digitize(v, edges[1:-1]).astype(float)
    out[~np.isfinite(v)] = np.nan
    return out


def _entry_price(P, t, d):
    e = t + 1
    if e >= P["N"]:
        return np.nan
    return P["ask_o"][e] if d > 0 else P["bid_o"][e]


def signal_geometry(P, dvec, Ivec):
    """Each real signal's dist/ATR ratio - the shape the control inherits."""
    live = np.where(np.asarray(dvec) != 0)[0]
    live = live[(live >= 300) & (live < P["N"] - 1)]
    rows = []
    for t in live:
        d = int(dvec[t])
        a = P["A"][t]
        entry = _entry_price(P, t, d)
        inv = Ivec[t]
        if not (np.isfinite(a) and a > 0 and np.isfinite(entry)
                and np.isfinite(inv)):
            continue
        rows.append((int(t), d, float(abs(entry - inv) / a)))
    return rows


def build(P, dvec, Ivec, level, rng, lo=300, exclude_real=True):
    """Return (d_ctrl, I_ctrl, meta) for one control level.

    The control has one entry per real signal that the geometry step could
    read, placed on a donor bar drawn from the same matched cell, facing
    either the same way or a coin, with an invalidation level SYNTHESISED at
    the real signal's own dist/ATR ratio. Nothing about the donor bar's own
    high or low is used, which is the defect this replaces."""
    if level not in SPEC:
        raise ValueError(f"unknown control level {level!r}")
    dims, dirmode = SPEC[level]
    dims = tuple(x for x in dims if x)
    bad = [d for d in dims if d in POST_SIGNAL]
    if bad:
        raise ValueError(f"refusing to match on post-signal variables: {bad}")

    geo = signal_geometry(P, dvec, Ivec)
    N = P["N"]
    d_out = np.zeros(N, np.int8)
    I_out = np.full(N, np.nan)
    meta = dict(level=level, description=DESCRIPTION[level], dims=list(dims),
                direction=dirmode, requested=len(geo), placed=0,
                relaxed=0, unmatched=0,
                causal=causal_sketch(dims))
    if not geo:
        return d_out, I_out, meta

    live_idx = np.array([g[0] for g in geo])
    live_mask = np.zeros(N, bool)
    live_mask[live_idx] = True

    eligible = np.ones(N, bool)
    eligible[:lo] = False
    eligible[N - X.HOLD_BARS - 2:] = False
    eligible &= np.isfinite(np.asarray(P["A"], float))
    eligible &= np.asarray(P["A"], float) > 0
    if exclude_real:
        eligible[live_idx] = False

    nq = NQ_BY_NDIM.get(len(dims), 3)
    binned = []
    for dim in dims:
        v = FEATURES[dim](P)
        if dim == "session":
            b = np.asarray(v, float)          # already a label
        else:
            b = _bin(v, nq, live_mask)
        if b is None:
            meta.setdefault("dropped_dims", []).append(dim)
            continue
        binned.append((dim, b))

    def key_at(idxs, k):
        """Composite cell label using the first k matched dims."""
        if k == 0:
            return np.zeros(len(idxs))
        out = np.zeros(len(idxs), float)
        for dim, b in binned[:k]:
            out = out * 1000.0 + np.nan_to_num(b[idxs], nan=-1.0)
            out = np.where(np.isfinite(b[idxs]), out, np.nan)
        return out

    pool = np.where(eligible)[0]
    if len(pool) == 0:
        meta["unmatched"] = len(geo)
        return d_out, I_out, meta

    # donor pools by cell, at every relaxation depth, built once
    pools = {}
    for k in range(len(binned), -1, -1):
        kk = key_at(pool, k)
        tbl = {}
        order = np.argsort(np.nan_to_num(kk, nan=np.inf), kind="stable")
        ks = kk[order]
        ps = pool[order]
        start = 0
        for i in range(1, len(ks) + 1):
            if i == len(ks) or not (ks[i] == ks[start]
                                    or (np.isnan(ks[i]) and np.isnan(ks[start]))):
                if np.isfinite(ks[start]):
                    tbl[float(ks[start])] = ps[start:i]
                start = i
        pools[k] = tbl

    sig_keys = {k: key_at(live_idx, k) for k in range(len(binned) + 1)}
    # a boolean mask rather than a set: the membership test runs once per
    # candidate per signal, and np.isin against a growing list turned an
    # 8,000-signal book into minutes
    taken = np.zeros(N, bool)
    for j, (t, d, ratio) in enumerate(geo):
        placed = False
        for k in range(len(binned), -1, -1):
            key = sig_keys[k][j]
            if not np.isfinite(key):
                continue
            cand = pools[k].get(float(key))
            if cand is None or len(cand) == 0:
                continue
            free = cand[~taken[cand]]
            if len(free) == 0:
                continue
            t2 = int(rng.choice(free))
            dd = int(rng.choice((-1, 1))) if dirmode == "random" else d
            entry = _entry_price(P, t2, dd)
            a2 = P["A"][t2]
            if not (np.isfinite(entry) and np.isfinite(a2) and a2 > 0):
                continue
            d_out[t2] = dd
            I_out[t2] = entry - dd * ratio * a2
            taken[t2] = True
            meta["placed"] += 1
            if k < len(binned):
                meta["relaxed"] += 1
            placed = True
            break
        if not placed:
            meta["unmatched"] += 1
    meta["match_rate"] = (meta["placed"] - meta["relaxed"]) / max(len(geo), 1)
    meta["placement_rate"] = meta["placed"] / max(len(geo), 1)
    return d_out, I_out, meta


def geometry_gap(P, dvec, Ivec, d2, I2):
    """How far the control's risk shape sits from the rule's.

    This is audit check 8, callable. Anything above ~0.15 means the two books
    are not the same instrument and their expectancies are not comparable."""
    def q(dv, Iv):
        rows = signal_geometry(P, dv, Iv)
        if len(rows) < 50:
            return None
        return np.nanquantile([r[2] for r in rows], [0.25, 0.5, 0.75])
    a, b = q(dvec, Ivec), q(d2, I2)
    if a is None or b is None:
        return dict(ok=False, reason="too few trades to compare")
    rel = float(np.max(np.abs(b - a) / np.maximum(a, 1e-9)))
    return dict(ok=rel < 0.15, rel_gap=rel,
                rule=[round(float(x), 4) for x in a],
                control=[round(float(x), 4) for x in b])


def report(rows, level_order=LEVELS):
    """Format a per-level skill table. The level is never dropped."""
    out = []
    for lv in level_order:
        g = [r for r in rows if r["level"] == lv]
        if not g:
            continue
        s = np.array([r["skill"] for r in g], float)
        se = float(s.std(ddof=1) / math.sqrt(len(s))) if len(s) > 1 else np.nan
        out.append(dict(level=lv, description=DESCRIPTION[lv], markets=len(g),
                        skill=float(s.mean()),
                        t=float(s.mean() / se) if se and se > 0 else np.nan,
                        positive=int((s > 0).sum())))
    return out


if __name__ == "__main__":
    print(__doc__.split("THE HIERARCHY")[1].split("THE WORD")[0])
    for lv in LEVELS:
        dims, dm = SPEC[lv]
        dims = tuple(x for x in dims if x)
        print(f"  {lv}  {DESCRIPTION[lv]}")
        for d, info in causal_sketch(dims).items():
            print(f"        {d:<12}{info['role']:<24}{info['why']}")
