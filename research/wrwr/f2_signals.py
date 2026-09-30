"""WRWR Family 2 signals (docs/WRWR_FAMILY2_PREREG.md): SMC structure, levels, calendar and volatility events.
f2_signals(B, cuts) -> {name: (long_event_bool[N], short_event_bool[N])}, each event evaluated at bar close t (entry at the
next bar open). B: bar object with t (open time, int64), o, h, l, c, step, atr (14-bar ATR known at each bar's open,
i.e. ATR_{t-1}). Every definition uses only bars <= t (levels from completed days / weeks). Research only."""
from __future__ import annotations

import numpy as np
import pandas as pd

FVG_LIFE, OB_LIFE = 20, 30
CLOCK_SIGNALS = ("fix_am", "fix_pm", "ny_open")


def _cross_up(a, b):
    a, b = np.asarray(a, float), np.asarray(b, float)
    out = np.zeros(len(a), bool)
    out[1:] = (a[1:] > b[1:]) & (a[:-1] <= b[:-1])
    return out


def _cross_dn(a, b):
    a, b = np.asarray(a, float), np.asarray(b, float)
    out = np.zeros(len(a), bool)
    out[1:] = (a[1:] < b[1:]) & (a[:-1] >= b[:-1])
    return out


def day_ids(t):
    return (np.asarray(t, np.int64) - 22 * 3600) // 86400          # 22:00 UTC day anchor


def prior_day_levels(t, h, l, c):
    """Prior COMPLETED trading day's high / low / close for every bar (shift by existing days, not calendar arithmetic)."""
    import pandas as pd
    d = day_ids(t)
    g = pd.DataFrame(dict(d=d, h=h, l=l, c=c)).groupby("d").agg(h=("h", "max"), l=("l", "min"), c=("c", "last"))
    prev = g.shift(1)
    rng = g.h - g.l
    nr7 = (rng <= rng.rolling(7).min()).shift(1)
    inside = ((g.h < g.h.shift(1)) & (g.l > g.l.shift(1))).shift(1)
    ix = pd.Index(d)
    return (prev.h.reindex(ix).to_numpy(float), prev.l.reindex(ix).to_numpy(float), prev.c.reindex(ix).to_numpy(float),
            nr7.reindex(ix).fillna(False).to_numpy(bool), inside.reindex(ix).fillna(False).to_numpy(bool), d)


def prior_week_levels(t, h, l, cuts):
    wk = np.searchsorted(cuts, t, side="left") - 1
    g = pd.DataFrame(dict(w=wk, h=h, l=l)).groupby("w").agg(h=("h", "max"), l=("l", "min")).shift(1)
    ix = pd.Index(wk)
    return g.h.reindex(ix).to_numpy(float), g.l.reindex(ix).to_numpy(float)


def f2_signals(B, cuts):
    t = np.asarray(B.t, np.int64); n = len(t); step = int(B.step)
    o, h, l, c = (np.asarray(x, float) for x in (B.o, B.h, B.l, B.c))
    atr_prev = np.asarray(B.atr, float)                             # ATR_{t-1}: known at the open of bar t
    S = {}

    def put(name, lg, sh):
        S[name] = (np.asarray(lg, bool), np.asarray(sh, bool))

    # ---- fair value gaps
    lg = np.zeros(n, bool); sh = np.zeros(n, bool)
    lg[2:] = l[2:] > h[:-2]; sh[2:] = h[2:] < l[:-2]
    put("fvg_form", lg, sh)
    lg = np.zeros(n, bool); sh = np.zeros(n, bool)
    bulls, bears = [], []                                           # (created, lower, upper)
    for i in range(2, n):
        # retest of zones created before bar i (age 1..FVG_LIFE); zones consumed at the first retest; filled zones dropped
        nb = []
        for z in bulls:
            if i - z[0] > FVG_LIFE or l[i] <= z[1]:
                if l[i] <= z[1] and i - z[0] <= FVG_LIFE:
                    pass                                              # traded through the lower edge: filled, no event
                continue
            if l[i] <= z[2] and c[i] > z[1]:
                lg[i] = True; continue                                # first retest: event, zone consumed
            nb.append(z)
        bulls = nb
        nb = []
        for z in bears:
            if i - z[0] > FVG_LIFE or h[i] >= z[2]:
                continue
            if h[i] >= z[1] and c[i] < z[2]:
                sh[i] = True; continue
            nb.append(z)
        bears = nb
        if l[i] > h[i - 2]:
            bulls.append((i, h[i - 2], l[i]))
        if h[i] < l[i - 2]:
            bears.append((i, h[i], l[i - 2]))
    put("fvg_retest", lg, sh)
    # ---- market structure: fractal(2,2) swings confirmed 2 bars late
    bos_l = np.zeros(n, bool); bos_s = np.zeros(n, bool); ch_l = np.zeros(n, bool); ch_s = np.zeros(n, bool)
    sh_v = sl_v = np.nan; sh_brk = sl_brk = True; st = 0
    for i in range(4, n):
        j = i - 2
        if h[j] >= h[j - 2:j + 3].max():
            sh_v = h[j]; sh_brk = False
        if l[j] <= l[j - 2:j + 3].min():
            sl_v = l[j]; sl_brk = False
        new = st
        if np.isfinite(sh_v) and c[i] > sh_v:
            new = 1
        elif np.isfinite(sl_v) and c[i] < sl_v:
            new = -1
        if st == 1 and np.isfinite(sh_v) and c[i] > sh_v and not sh_brk:
            bos_l[i] = True
        if st == -1 and np.isfinite(sl_v) and c[i] < sl_v and not sl_brk:
            bos_s[i] = True
        if np.isfinite(sh_v) and c[i] > sh_v:
            sh_brk = True
        if np.isfinite(sl_v) and c[i] < sl_v:
            sl_brk = True
        if new != st and st != 0:
            (ch_l if new == 1 else ch_s)[i] = True
        st = new
    put("bos", bos_l, bos_s); put("choch", ch_l, ch_s)
    # ---- previous-day / 20-bar liquidity sweeps, displacement, order blocks
    pdh, pdl, pdc, nr7, inside, dday = prior_day_levels(t, h, l, c)
    put("sweep_pd", (l < pdl) & (c > pdl), (h > pdh) & (c < pdh))
    hh20 = pd.Series(h).rolling(20).max().shift(1).to_numpy(); ll20 = pd.Series(l).rolling(20).min().shift(1).to_numpy()
    put("sweep20", (l < ll20) & (c > ll20), (h > hh20) & (c < hh20))
    rng = h - l
    with np.errstate(invalid="ignore", divide="ignore"):
        big = rng > 2 * atr_prev
        body_ok = np.abs(c - o) > 0.6 * rng
        d_up = big & body_ok & (c >= l + 0.75 * rng); d_dn = big & body_ok & (c <= l + 0.25 * rng)
    put("disp", d_up, d_dn)
    lg = np.zeros(n, bool); sh = np.zeros(n, bool)
    bz, sz = [], []                                                # (created, low, high)
    for i in range(n):
        nb = []
        for z in bz:
            if i - z[0] > OB_LIFE or c[i] < z[1]:
                continue
            if l[i] <= z[2] and c[i] >= z[1]:
                lg[i] = True; continue
            nb.append(z)
        bz = nb
        nb = []
        for z in sz:
            if i - z[0] > OB_LIFE or c[i] > z[2]:
                continue
            if h[i] >= z[1] and c[i] <= z[2]:
                sh[i] = True; continue
            nb.append(z)
        sz = nb
        if d_up[i]:
            for j in (i - 1, i - 2, i - 3):
                if j >= 0 and c[j] < o[j]:
                    bz.append((i, l[j], h[j])); break
        if d_dn[i]:
            for j in (i - 1, i - 2, i - 3):
                if j >= 0 and c[j] > o[j]:
                    sz.append((i, l[j], h[j])); break
    put("ob_retest", lg, sh)
    # ---- levels
    put("pd_break", _cross_up(c, pdh), _cross_dn(c, pdl))
    pwh, pwl = prior_week_levels(t, h, l, cuts)
    put("pw_break", _cross_up(c, pwh), _cross_dn(c, pwl))
    piv = (pdh + pdl + pdc) / 3
    put("pivot_x", _cross_up(c, piv), _cross_dn(c, piv))
    for step_, nm in ((50.0, "round50_x"), (100.0, "round100_x")):
        fl = np.floor(c / step_)
        up = np.zeros(n, bool); dn = np.zeros(n, bool)
        up[1:] = fl[1:] > fl[:-1]; dn[1:] = fl[1:] < fl[:-1]
        put(nm, up, dn)
    first_of_day = np.r_[True, dday[1:] != dday[:-1]]
    gap = np.full(n, np.nan); gap[1:] = (o[1:] - c[:-1])
    with np.errstate(invalid="ignore"):
        put("gap_day", first_of_day & (gap > 0.5 * atr_prev), first_of_day & (gap < -0.5 * atr_prev))
    # ---- volatility structure
    put("nr7_break", nr7 & _cross_up(c, pdh), nr7 & _cross_dn(c, pdl))
    put("inside_break", inside & _cross_up(c, pdh), inside & _cross_dn(c, pdl))
    cs = pd.Series(c)
    m20 = cs.rolling(20).mean(); s20 = cs.rolling(20).std()
    width = (4 * s20 / m20); ratio = width / width.rolling(120).median()
    sq_prev = (ratio.shift(1) < 0.7).fillna(False).to_numpy(bool)
    put("squeeze_break", sq_prev & _cross_up(c, (m20 + 2 * s20).to_numpy()), sq_prev & _cross_dn(c, (m20 - 2 * s20).to_numpy()))
    # ---- calendar / clock (the NEXT bar is known in advance)
    tn = np.r_[t[1:], t[-1] + step]
    u = pd.to_datetime(tn, unit="s", utc=True)
    lon = u.tz_convert("Europe/London"); ny = u.tz_convert("America/New_York")

    def contains(local, hh, mm):
        start = local.hour * 60 + local.minute
        return ((start <= hh * 60 + mm) & (hh * 60 + mm < start + step // 60))
    none = np.zeros(n, bool)
    if step <= 3600:
        put("fix_am", contains(lon, 10, 30), none); put("fix_pm", contains(lon, 15, 0), none); put("ny_open", contains(ny, 9, 30), none)
    dn_ = (tn + 7200) // 86400; dc_ = (t + 7200) // 86400                   # calendar day of the bar (22:00 UTC rolls the day)
    dates = pd.to_datetime(dn_ * 86400, unit="s")
    # last trading day of the month by CALENDAR (last weekday; the day is labelled by the date on which it ends at 22:00 UTC),
    # never by which days happen to be present in the data (that would use the future at the end of a series)
    is_last = (dates.dayofweek < 5) & ((dates + pd.offsets.BDay(1)).month != dates.month)
    put("tom", (dn_ != dc_) & np.asarray(is_last), none)
    return S
