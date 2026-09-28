"""Round-2 approaches (prereg Amendment 2): HOD-MERGED, SESSION, DAYREV.
META lives in run_round2.py because it consumes the round-1 tools' series.

Pool formats understood by evaluate.weekly_series:
  list[(i, k)]            fixed placements (RTIME = mean over them)
  ("entries", lo, hi)     any entry bar in [lo, hi), each trade's own hold
                          length, truncated at gaps (m.exit_index)
"""
from __future__ import annotations

import numpy as np

from approaches import _date_spans, hod_tool
from common import HOUR, WEEK, weighted_t


# ------------------------------------------------------------------ F
def hodm_week(m, cut, W, T):
    sel = dict(hod_tool(m, cut, W, T))
    lo, hi = m.week_bars(cut)
    trades, i = [], lo
    while i < hi:
        d = sel.get(int(m.hour[i]))
        if d is None:
            i += 1
            continue
        k = i
        while (k + 1 < hi and m.t[k + 1] - m.t[k] == HOUR
               and m.day[k + 1] == m.day[i] and sel.get(int(m.hour[k + 1])) == d):
            k += 1
        trades.append((i, k, d))
        i = k + 1
    return trades, ("entries", lo, hi)


# ------------------------------------------------------------------ G
SESS = {**{h: "ASIA" for h in (22, 23, 0, 1, 2, 3, 4, 5, 6)},
        **{h: "LON" for h in range(7, 13)},
        **{h: "NY" for h in range(13, 21)}}


def session_runs(m, lo, hi):
    runs, i = [], lo
    while i < hi:
        s = SESS.get(int(m.hour[i]))
        if s is None:
            i += 1
            continue
        k = i
        while (k + 1 < hi and m.t[k + 1] - m.t[k] == HOUR
               and SESS.get(int(m.hour[k + 1])) == s):
            k += 1
        runs.append((i, k, s))
        i = k + 1
    return runs


def session_tool(m, cut, W, T):
    a = int(np.searchsorted(m.t, cut - W * WEEK))
    b = m.last_bar_before(cut) + 1
    runs = session_runs(m, a, b)
    if len(runs) < 30:
        return ()
    f = np.array([r[0] for r in runs]); e = np.array([r[1] for r in runs])
    lab = np.array([r[2] for r in runs])
    ret = (m.c[e] - m.o[f]) / m.o[f] * 1e4
    w = 0.5 ** (((cut - m.t[f]) / WEEK) / (W / 2))
    sel = []
    for s in ("ASIA", "LON", "NY"):
        mk = lab == s
        mean, t = weighted_t(ret[mk], w[mk])
        if abs(t) >= T and mean != 0:
            sel.append((s, int(np.sign(mean))))
    return tuple(sel)


def session_week(m, cut, W, T):
    sel = dict(session_tool(m, cut, W, T))
    lo, hi = m.week_bars(cut)
    runs = session_runs(m, lo, hi)
    trades = [(i, k, sel[s]) for i, k, s in runs if s in sel]
    return trades, [(i, k) for i, k, _ in runs]


# ------------------------------------------------------------------ H
def _day_table(m, a, b):
    spans = _date_spans(m, a, b)
    f = np.array([s for s, _ in spans], np.int64)
    e = np.array([x for _, x in spans], np.int64)
    rng = np.array([m.h[s:x + 1].max() - m.l[s:x + 1].min() for s, x in spans])
    ret = m.c[e] - m.o[f] if len(spans) else np.array([])
    return f, e, rng, ret


def _triggers(f, e, rng, ret, z):
    """Indices j (signal days) with |ret_j| >= z * mean(range of 14 prior days)."""
    out = []
    for j in range(14, len(f) - 1):
        atr_d = rng[j - 14:j].mean()
        if atr_d > 0 and abs(ret[j]) >= z * atr_d:
            out.append(j)
    return out


def dayrev_tool(m, cut, z, N):
    a = int(np.searchsorted(m.t, cut - 26 * WEEK - 40 * 86400))
    b = m.last_bar_before(cut) + 1
    f, e, rng, ret = _day_table(m, a, b)
    vals, wts = [], []
    for j in _triggers(f, e, rng, ret, z):
        x = j + N
        if x >= len(f) or m.t[f[j + 1]] < cut - 26 * WEEK:
            continue
        if m.t[e[x]] + HOUR > cut:
            continue
        d = -int(np.sign(ret[j]))
        if d == 0:
            continue
        vals.append(float(m.pnl_bp([f[j + 1]], [e[x]], [d])[0]))
        wts.append(0.5 ** (((cut - m.t[f[j + 1]]) / WEEK) / 13))
    if not vals:
        return 0
    v, w = np.asarray(vals), np.asarray(wts)
    return 1 if (w * v).sum() / w.sum() > 0 else -1


def dayrev_week(m, cut, z, N):
    lo, hi = m.week_bars(cut)
    if hi <= lo:
        return [], []
    a = int(np.searchsorted(m.t, cut - 40 * 86400))
    f, e, rng, ret = _day_table(m, a, hi)
    in_week = [s for s in range(len(f)) if f[s] >= lo]
    pool = []
    for s in in_week:
        x = min(s + N - 1, len(f) - 1)
        pool.append((int(f[s]), int(min(e[x], hi - 1))))
    mode = dayrev_tool(m, cut, z, N)
    if mode == 0:
        return [], pool
    trades, busy = [], -1
    for j in _triggers(f, e, rng, ret, z):
        s = j + 1
        if f[s] < lo or f[s] >= hi or f[s] <= busy:
            continue
        x = min(s + N - 1, len(f) - 1)
        k = int(min(e[x], hi - 1))
        d = -int(np.sign(ret[j])) * mode
        if d == 0:
            continue
        trades.append((int(f[s]), k, d))
        busy = k
    return trades, pool


# ------------------------------------------------------------------ registry
def variants2():
    v = []
    for T in (2.0, 3.0):
        v.append(("F", f"HODM W=52 T={T}", dict(W=52, T=T)))
    for W in (52, 104):
        for T in (1.5, 2.0):
            v.append(("G", f"SESSION W={W} T={T}", dict(W=W, T=T)))
    for z in (1.0, 1.5):
        for N in (1, 2):
            v.append(("H", f"DAYREV z={z} N={N}", dict(z=z, N=N)))
    assert len(v) == 10
    return v


def run_week2(fam, m, cut, params):
    if fam == "F":
        return hodm_week(m, cut, **params)
    if fam == "G":
        return session_week(m, cut, **params)
    if fam == "H":
        return dayrev_week(m, cut, **params)
    raise ValueError(fam)


def tool_signature2(fam, m, cut, params):
    if fam == "F":
        return hod_tool(m, cut, **params)
    if fam == "G":
        return session_tool(m, cut, **params)
    if fam == "H":
        return dayrev_tool(m, cut, **params)
    raise ValueError(fam)
