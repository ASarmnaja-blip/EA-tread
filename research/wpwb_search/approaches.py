"""The five pre-registered approaches (docs/WPWB_EDGE_SEARCH_PREREG.md s.4).

Each approach exposes:
  tool(m, cut, **params)   -> hashable summary of the week's tool, computed
                              ONLY from bars that end before `cut` (audited)
  week(m, cut, **params)   -> (trades, pool)
      trades: list of (i_in, k_out, d)
      pool:   list of (i_in, k_out) candidate placements for the RTIME control
"""
from __future__ import annotations

import numpy as np

from common import HOUR, WEEK, weighted_t

CHOP_EFF_MAX = 0.05


# ------------------------------------------------------------------ A. TSM
def tsm_tool(m, cut, L):
    closes = []
    for j in range(L + 1):
        kb = m.last_bar_before(cut - j * WEEK)
        if kb < 0:
            return 0
        closes.append(m.c[kb])
    closes = np.asarray(closes)
    r = np.log(closes[:-1] / closes[1:])            # r[0] = most recent week
    w = 0.5 ** (np.arange(L) / (L / 2))
    s = float((w * r).sum() / w.sum())
    return int(np.sign(s))


def tsm_week(m, cut, L):
    d = tsm_tool(m, cut, L)
    lo, hi = m.week_bars(cut)
    if d == 0 or hi <= lo:
        return [], []
    return [(lo, hi - 1, d)], []


# ------------------------------------------------------------------ B. HOD
def hod_tool(m, cut, W, T):
    a = int(np.searchsorted(m.t, cut - W * WEEK))
    b = m.last_bar_before(cut) + 1
    if b - a < 100:
        return ()
    idx = np.arange(a, b)
    r = (m.c[idx] - m.o[idx]) / m.o[idx] * 1e4
    w = 0.5 ** (((cut - m.t[idx]) / WEEK) / (W / 2))
    hrs = m.hour[idx]
    sel = []
    for h in range(24):
        mk = hrs == h
        mean, t = weighted_t(r[mk], w[mk])
        if abs(t) >= T and mean != 0:
            sel.append((h, int(np.sign(mean))))
    return tuple(sel)


def hod_week(m, cut, W, T):
    sel = dict(hod_tool(m, cut, W, T))
    lo, hi = m.week_bars(cut)
    trades = [(i, i, sel[int(m.hour[i])]) for i in range(lo, hi)
              if int(m.hour[i]) in sel]
    pool = [(i, i) for i in range(lo, hi)]
    return trades, pool


# ------------------------------------------------------------------ C. DOW
def _date_spans(m, lo, hi):
    """(first, last) H1 index per UTC date inside [lo, hi)."""
    out = []
    if hi <= lo:
        return out
    days = m.day[lo:hi]
    starts = np.flatnonzero(np.r_[True, days[1:] != days[:-1]]) + lo
    ends = np.r_[starts[1:] - 1, hi - 1]
    return list(zip(starts.tolist(), ends.tolist()))


def dow_tool(m, cut, W, T):
    a = int(np.searchsorted(m.t, cut - W * WEEK))
    b = m.last_bar_before(cut) + 1
    spans = _date_spans(m, a, b)
    if len(spans) < 50:
        return ()
    f = np.array([s for s, _ in spans]); e = np.array([x for _, x in spans])
    r = (m.c[e] - m.o[f]) / m.o[f] * 1e4
    w = 0.5 ** (((cut - m.t[f]) / WEEK) / (W / 2))
    wd = m.wday[f]
    sel = []
    for d in range(7):
        mk = wd == d
        mean, t = weighted_t(r[mk], w[mk])
        if abs(t) >= T and mean != 0:
            sel.append((d, int(np.sign(mean))))
    return tuple(sel)


def dow_week(m, cut, W, T):
    sel = dict(dow_tool(m, cut, W, T))
    lo, hi = m.week_bars(cut)
    spans = _date_spans(m, lo, hi)
    trades = [(f, e, sel[int(m.wday[f])]) for f, e in spans if int(m.wday[f]) in sel]
    return trades, [(f, e) for f, e in spans]


# ------------------------------------------------------------------ D. CHOPREV
def chop_tool(m, cut, eff_cache):
    eff = eff_cache.get(cut)
    if eff is None:
        eff = m.efficiency_at(cut)
        eff_cache[cut] = eff
    return bool(np.isfinite(eff) and eff <= CHOP_EFF_MAX)


def chop_week(m, cut, z, H, gated, eff_cache):
    if gated and not chop_tool(m, cut, eff_cache):
        return [], []
    lo, hi = m.week_bars(cut)
    trades, busy = [], -1
    for i in range(lo, hi - 1):
        if i <= busy:
            continue
        a = m.atr[i]
        if not np.isfinite(a) or a <= 0 or m.t[i + 1] - m.t[i] != HOUR:
            continue
        ret = m.c[i] - m.o[i]
        if abs(ret) >= z * a:
            e = i + 1
            k = m.exit_index(e, H, hi)
            trades.append((e, k, -int(np.sign(ret))))
            busy = k
    pool = [(e, m.exit_index(e, H, hi)) for e in range(lo + 1, hi)]
    return trades, pool


# ------------------------------------------------------------------ E. GAP
GAP_HOLD = 4


def _gap_info(m, cut):
    lo, hi = m.week_bars(cut)
    kp = m.last_bar_before(cut)
    if hi <= lo or kp < 0 or not np.isfinite(m.atr[kp]) or m.atr[kp] <= 0:
        return None
    return lo, hi, kp, float(m.o[lo] - m.c[kp]), float(m.atr[kp])


def gap_tool(m, cut, k):
    """Follow (+1) or fade (-1), from past weeks' realised follow P&L."""
    vals, wts = [], []
    for j in range(1, 53):
        cc = cut - j * WEEK
        info = _gap_info(m, cc)
        if info is None:
            continue
        lo, hi, kp, g, a = info
        if hi + 0 > len(m.t) or abs(g) < k * a or g == 0:
            continue
        kx = m.exit_index(lo, GAP_HOLD, hi)
        if m.t[kx] + HOUR > cut:          # must be fully resolved before cut
            continue
        vals.append(float(m.pnl_bp([lo], [kx], [int(np.sign(g))])[0]))
        wts.append(0.5 ** (j / 26))
    if not vals:
        return 0
    v, w = np.asarray(vals), np.asarray(wts)
    return 1 if (w * v).sum() / w.sum() > 0 else -1


def gap_week(m, cut, k):
    info = _gap_info(m, cut)
    if info is None:
        return [], []
    lo, hi, kp, g, a = info
    pool = [(e, m.exit_index(e, GAP_HOLD, hi)) for e in range(lo, hi)]
    if abs(g) < k * a or g == 0:
        return [], pool
    mode = gap_tool(m, cut, k)
    if mode == 0:
        return [], pool
    d = int(np.sign(g)) * mode
    return [(lo, m.exit_index(lo, GAP_HOLD, hi), d)], pool


# ------------------------------------------------------------------ registry
def variants():
    """The 20 pre-registered variants, in prereg order."""
    v = []
    for L in (4, 8, 13, 26):
        v.append(("A", f"TSM L={L}", dict(L=L)))
    for W in (26, 52):
        for T in (2.0, 3.0):
            v.append(("B", f"HOD W={W} T={T}", dict(W=W, T=T)))
    for T in (1.5, 2.0):
        v.append(("C", f"DOW W=52 T={T}", dict(W=52, T=T)))
    for gated in (True, False):
        for z in (1.5, 2.5):
            for H in (2, 6):
                tag = "D" if gated else "D-ungated"
                v.append((tag, f"CHOPREV{'' if gated else '-ungated'} z={z} H={H}",
                          dict(z=z, H=H, gated=gated)))
    for k in (0.5, 1.0):
        v.append(("E", f"GAP k={k}", dict(k=k)))
    assert len(v) == 20
    return v


def run_week(fam, m, cut, params, eff_cache):
    if fam == "A":
        return tsm_week(m, cut, **params)
    if fam == "B":
        return hod_week(m, cut, **params)
    if fam == "C":
        return dow_week(m, cut, **params)
    if fam in ("D", "D-ungated"):
        return chop_week(m, cut, eff_cache=eff_cache, **params)
    if fam == "E":
        return gap_week(m, cut, **params)
    raise ValueError(fam)


def tool_signature(fam, m, cut, params, eff_cache):
    if fam == "A":
        return tsm_tool(m, cut, **params)
    if fam == "B":
        return hod_tool(m, cut, **params)
    if fam == "C":
        return dow_tool(m, cut, **params)
    if fam in ("D", "D-ungated"):
        return chop_tool(m, cut, eff_cache) if params["gated"] else True
    if fam == "E":
        return gap_tool(m, cut, params["k"])
    raise ValueError(fam)
