"""Signal generators for docs/plans/P01..P15. Each gen_Pxx(B, mkt, tf) returns {variant: orders DataFrame} built only from information
known at the signal bar's close. Definitions follow the plan files exactly; comments name the plan line they implement."""
from __future__ import annotations

import numpy as np
import pandas as pd

import engine_s as E

L = E.L


def _a(B):
    return np.where(np.isfinite(B.atr) & (B.atr > 0), B.atr, np.nan)


def _side(c, sl):
    return c + np.sign(c - sl) * np.abs(c - sl)                                   # 1:1 target measured from the close (~ the next open)


# ------------------------------------------------------------------ structure helpers
def last_swings(B, k=2):
    """Per bar: the latest and previous confirmed swing highs / lows (value, pivot), and the third latest low / high."""
    S = E.swing_table(B, k)
    n = len(B.c); out = {}
    for kind, nm in ((1, "h"), (-1, "l")):
        X = S[S.kind == kind]
        conf, val, piv = X.conf.to_numpy(), X.val.to_numpy(), X.piv.to_numpy()
        j = np.searchsorted(conf, np.arange(n), side="right") - 1
        for lag, tag in ((0, "1"), (1, "2"), (2, "3")):
            jj = j - lag; ok = jj >= 0
            out[f"{nm}{tag}_val"] = np.where(ok, val[np.maximum(jj, 0)], np.nan)
            out[f"{nm}{tag}_piv"] = np.where(ok, piv[np.maximum(jj, 0)], -1)
            out[f"{nm}{tag}_conf"] = np.where(ok, conf[np.maximum(jj, 0)], -1)
    return out, S


def clean_leg(B, a, b):
    """Clean Traffic of the leg a -> b (bar indices, a < b): opposite-colour share <= 20 % and efficiency ratio >= 0.6."""
    if b - a < 2:
        return False
    c, o = B.c[a:b + 1], B.o[a:b + 1]
    up = c[-1] > c[0]
    opp = np.mean((c < o) if up else (c > o))
    er = abs(c[-1] - c[0]) / max(np.abs(np.diff(c)).sum(), 1e-12)
    return bool(opp <= 0.2 and er >= 0.6)


def first_cross(c, lvl, d):
    """True at t when close(t) crosses the level against d for the first time (close(t) beyond, close(t-1) not)."""
    prev = np.r_[np.nan, c[:-1]]
    with np.errstate(invalid="ignore"):
        return (c < lvl) & (prev >= lvl) if d < 0 else (c > lvl) & (prev <= lvl)


# ------------------------------------------------------------------ P01 Asia box -> London breakout
def gen_P01(B, mkt, tf):
    t = B.t; day = t // 86400; sec = t % 86400; wd = (day + 3) % 7
    starts = np.flatnonzero(np.r_[True, day[1:] != day[:-1]]); ends = np.r_[starts[1:], len(t)]
    V = {"main 07-16 width<=0.8%": [], "window 07-20 width<=0.8%": [], "no width filter 07-16": [], "abs $35 (2025-26)": []}
    for a, b in zip(starts, ends):
        if wd[a] >= 5:
            continue
        idx = np.arange(a, b); bx = idx[sec[idx] < 7 * 3600]
        if len(bx) < 20:
            continue
        hi, lo = B.h[bx].max(), B.l[bx].min(); W = hi - lo; mid = (hi + lo) / 2
        for lab, end, rule in (("main 07-16 width<=0.8%", 16, "pct"), ("window 07-20 width<=0.8%", 20, "pct"), ("no width filter 07-16", 16, None),
                               ("abs $35 (2025-26)", 16, "abs")):
            if rule == "pct" and W / mid > 0.008:
                continue
            if rule == "abs" and (mkt != "XAUUSD" or t[a] < E.C.ts("2025-01-01") or W > 35):
                continue
            cd = idx[(sec[idx] >= 7 * 3600) & (sec[idx] < end * 3600)]
            hit = cd[(B.c[cd] > hi) | (B.c[cd] < lo)]
            if not len(hit):
                continue
            s = hit[0]; d = 1 if B.c[s] > hi else -1
            V[lab].append((s, d, mid, B.c[s] + d * 1.5 * W))
    return {k: E.orders([x[0] for x in v], [x[1] for x in v], [x[2] for x in v], [x[3] for x in v]) for k, v in V.items() if v}


# ------------------------------------------------------------------ P02 H4 CRT + LTF MSS + FVG
def gen_P02(B, mkt, tf):
    H = E.bars(mkt, "H4"); A = _a(B)
    st = np.searchsorted(B.t, H.t); en = np.searchsorted(B.t, H.t + 14400)
    S = E.swing_table(B, 2)
    hp, hv = S[S.kind == 1].piv.to_numpy(), S[S.kind == 1].val.to_numpy()
    lp, lv = S[S.kind == -1].piv.to_numpy(), S[S.kind == -1].val.to_numpy()
    body = np.abs(B.c - B.o)
    V = {"main C3": [], "window C3-C4": []}
    for k in range(len(H.t) - 4):
        c1, c2 = k, k + 1
        for d in (1, -1):
            if d > 0 and not (H.l[c2] < H.l[c1] and H.l[c1] < H.c[c2] < H.h[c1]):
                continue
            if d < 0 and not (H.h[c2] > H.h[c1] and H.l[c1] < H.c[c2] < H.h[c1]):
                continue
            seg = np.arange(st[c2], en[c2])
            if len(seg) < 3:
                continue
            sb = seg[np.argmin(B.l[seg])] if d > 0 else seg[np.argmax(B.h[seg])]
            if d > 0:
                q = np.searchsorted(hp, sb) - 1
                if q < 0:
                    continue
                ref = hv[q]
            else:
                q = np.searchsorted(lp, sb) - 1
                if q < 0:
                    continue
                ref = lv[q]
            for lab, last_h4 in (("main C3", k + 2), ("window C3-C4", k + 3)):
                w0, w1 = st[k + 2], en[last_h4] - 1
                if w1 <= w0:
                    continue
                for j in range(max(w0, sb + 1), w1 + 1):
                    if (d > 0 and B.c[j] > ref) or (d < 0 and B.c[j] < ref):
                        if not np.isfinite(A[j]) or body[sb:j + 1].max() < A[j]:
                            break
                        ii = np.arange(sb + 2, j + 1)
                        fv = ii[(B.l[ii] > B.h[ii - 2])] if d > 0 else ii[(B.h[ii] < B.l[ii - 2])]
                        if not len(fv):
                            break
                        i = fv[-1]
                        lmt = (B.l[i] + B.h[i - 2]) / 2 if d > 0 else (B.h[i] + B.l[i - 2]) / 2
                        ext = B.l[sb:j + 1].min() if d > 0 else B.h[sb:j + 1].max()
                        sl = ext - d * 0.1 * A[j]; tp = H.h[c1] if d > 0 else H.l[c1]
                        if d * (tp - lmt) > 0 and d * (lmt - sl) > 0:
                            V[lab].append((j, d, sl, tp, lmt, w1, tp))
                        break
    out = {}
    for kk, v in V.items():
        if v:
            a = np.array(v, float)
            out[kk] = E.orders(a[:, 0], a[:, 1], a[:, 2], a[:, 3], kind="lmt", lmt=a[:, 4], valid_to=a[:, 5], cancel=a[:, 6])
    return out


# ------------------------------------------------------------------ P03 QM + Fibonacci + order block
def gen_P03(B, mkt, tf):
    S = E.swing_table(B, 2); A = _a(B)
    Hh = E.bars(mkt, "H1")
    import y1_htf_system as Y
    trend = Y.anchor_dir(B, Hh)
    Z = []; used = set(); V = {"main OB+trend 2 orders": [], "no OB": [], "no trend": [], "single 50% OB+trend": []}
    exp = 96 if tf == "M5" else 32
    for r in S.itertuples():
        kind, val, piv, conf = int(r.kind), float(r.val), int(r.piv), int(r.conf)
        if Z and Z[-1][0] == kind:
            if (kind == 1 and val > Z[-1][1]) or (kind == -1 and val < Z[-1][1]):
                Z[-1] = (kind, val, piv, conf)
            else:
                continue
        else:
            Z.append((kind, val, piv, conf))
        if len(Z) < 4:
            continue
        k1, k2, k3, k4 = Z[-4:]
        s = conf
        if s + 1 >= len(B.c) or not np.isfinite(A[s]):
            continue
        if [k1[0], k2[0], k3[0], k4[0]] == [1, -1, 1, -1] and k3[1] > k1[1] and k4[1] < k2[1]:
            d, H2, L2, a_piv, b_piv = -1, k3[1], k4[1], k3[2], k4[2]
        elif [k1[0], k2[0], k3[0], k4[0]] == [-1, 1, -1, 1] and k3[1] < k1[1] and k4[1] > k2[1]:
            d, H2, L2, a_piv, b_piv = 1, k3[1], k4[1], k3[2], k4[2]               # here H2 = the new low (extreme), L2 = the new high
        else:
            continue
        if (a_piv, d) in used:
            continue
        used.add((a_piv, d))
        Rg = abs(H2 - L2)
        lv = lambda x: L2 + x * (H2 - L2)                                          # x from the end of the leg back toward its start
        l1, l2, sl = lv(0.5), lv(0.618), lv(0.886)
        tp1 = l1 - (sl - l1); tp2 = l2 - (sl - l2)
        seg = np.arange(min(a_piv, b_piv), max(a_piv, b_piv) + 1)
        bt, bb = np.maximum(B.o[seg], B.c[seg]), np.minimum(B.o[seg], B.c[seg])
        counter = (B.c[seg] > B.o[seg]) if d < 0 else (B.c[seg] < B.o[seg])
        band_lo, band_hi = min(l1, l2), max(l1, l2)
        ob = bool(np.any(counter & (bb <= band_hi) & (bt >= band_lo)))
        tr = trend[s] == d
        if Rg <= 0:
            continue
        rows = [(s, d, sl, tp1, l1, s + exp, L2), (s, d, sl, tp2, l2, s + exp, L2)]
        if ob and tr:
            V["main OB+trend 2 orders"] += rows; V["single 50% OB+trend"].append(rows[0])
        if tr:
            V["no OB"] += rows
        if ob:
            V["no trend"] += rows
    out = {}
    for kk, v in V.items():
        if v:
            a = np.array(v, float)
            out[kk] = E.orders(a[:, 0], a[:, 1], a[:, 2], a[:, 3], kind="lmt", lmt=a[:, 4], valid_to=a[:, 5], cancel=a[:, 6])
    return out


# ------------------------------------------------------------------ P04 accumulation breakout
def _rolling_slope(y, N):
    y = np.asarray(y, float); n = len(y); idx = np.arange(n, dtype=float)
    cy = np.r_[0, np.cumsum(y)]; cxy = np.r_[0, np.cumsum(idx * y)]
    out = np.full(n, np.nan)
    sx = N * (N - 1) / 2; sxx = (N - 1) * N * (2 * N - 1) / 6
    for_end = np.arange(N, n + 1)                                                  # window [e-N, e)
    Sy = cy[for_end] - cy[for_end - N]; Sjy = cxy[for_end] - cxy[for_end - N]
    Sxy = Sjy - (for_end - N) * Sy
    out[for_end - 1] = (N * Sxy - sx * Sy) / (N * sxx - sx ** 2)
    return out


def gen_P04(B, mkt, tf):
    A = _a(B); n = len(B.c)
    has_vol = mkt not in ("XAUUSD", "XAGUSD")
    S = E.swing_table(B, 2); hp, hv = S[S.kind == 1].piv.to_numpy(), S[S.kind == 1].val.to_numpy()
    lp, lv = S[S.kind == -1].piv.to_numpy(), S[S.kind == -1].val.to_numpy()
    V = {}
    for N in (20, 40):
        Hb = pd.Series(B.h).rolling(N).max().shift(1).to_numpy(); Lb = pd.Series(B.l).rolling(N).min().shift(1).to_numpy()
        A1 = np.r_[np.nan, A[:-1]]
        pmax = pd.Series(B.c).rolling(60).max().shift(1 + N).to_numpy(); pmin = pd.Series(B.c).rolling(60).min().shift(1 + N).to_numpy()
        slope_l = np.r_[np.nan, _rolling_slope(B.l, N)[:-1]]; slope_h = np.r_[np.nan, _rolling_slope(B.h, N)[:-1]]
        body = B.c - B.o
        vavg = pd.Series(B.v).rolling(20).mean().shift(1).to_numpy()
        with np.errstate(invalid="ignore"):
            base = (Hb - Lb) <= 4 * A1
            long_c = base & (pmax >= Hb + 2 * A1) & (slope_l > 0) & (B.c > Hb) & (body >= A1)
            short_c = base & (pmin <= Lb - 2 * A1) & (slope_h < 0) & (B.c < Lb) & (-body >= A1)
        for d, cand in ((1, long_c), (-1, short_c)):
            for t in np.flatnonzero(cand):
                if d > 0:
                    m = (hp >= t - N) & (hp <= t - 3)
                    if m.sum() < 2 or hv[m].min() < Hb[t] - A1[t]:
                        continue
                    sl = Lb[t] - 0.1 * A1[t]
                else:
                    m = (lp >= t - N) & (lp <= t - 3)
                    if m.sum() < 2 or lv[m].max() > Lb[t] + A1[t]:
                        continue
                    sl = Hb[t] + 0.1 * A1[t]
                tp = B.c[t] + d * 3 * abs(B.c[t] - sl)
                lab = f"N{N} {'accumulation long' if d > 0 else 'distribution short'}"
                V.setdefault(lab + " no volume", []).append((t, d, sl, tp))
                if has_vol and np.isfinite(vavg[t]) and B.v[t] >= 1.5 * vavg[t]:
                    V.setdefault(lab + " volume", []).append((t, d, sl, tp))
    return {k: E.orders([x[0] for x in v], [x[1] for x in v], [x[2] for x in v], [x[3] for x in v]) for k, v in V.items() if v}


# ------------------------------------------------------------------ P05 E1 three-bar pause
def gen_P05(B, mkt, tf):
    A = _a(B); o, h, l, c = B.o, B.h, B.l, B.c
    b1 = np.arange(len(c)) - 2
    ok = b1 >= 1
    t = np.flatnonzero(ok)
    a1 = A[t - 3]; body1 = c[t - 2] - o[t - 2]; r1 = h[t - 2] - l[t - 2]; r2 = h[t - 1] - l[t - 1]
    with np.errstate(invalid="ignore"):
        big = np.abs(body1) >= 1.5 * a1
        small = r2 <= 0.5 * r1
        bull = big & small & (body1 > 0) & (h[t - 1] <= h[t - 2] + 0.1 * a1) & (c[t] > h[t - 1])
        bear = big & small & (body1 < 0) & (l[t - 1] >= l[t - 2] - 0.1 * a1) & (c[t] < l[t - 1])
    rows = []
    for m, d in ((bull, 1), (bear, -1)):
        tt = t[m]
        sl = (l[tt - 1] - 0.1 * A[tt]) if d > 0 else (h[tt - 1] + 0.1 * A[tt])
        cut = h[tt - 1] if d > 0 else l[tt - 1]
        rows.append(E.orders(tt, np.full(len(tt), d), sl, _side(c[tt], sl), cut=cut))
    return {"main": pd.concat(rows)}


# ------------------------------------------------------------------ P06 E2 engulfing at a zone
def gen_P06(B, mkt, tf):
    A = _a(B); o, h, l, c = B.o, B.h, B.l, B.c; n = len(c)
    rng = h - l
    with np.errstate(invalid="ignore", divide="ignore"):
        bull = (c > o) & (np.r_[False, c[:-1] < o[:-1]]) & (np.r_[False, False, c[:-2] < o[:-2]])
        bull &= (c > np.maximum(np.r_[np.nan, o[:-1]], np.r_[np.nan, np.nan, o[:-2]])) & (o <= np.minimum(np.r_[np.nan, c[:-1]], np.r_[np.nan, np.nan, c[:-2]]))
        bull &= ((np.minimum(o, c) - l) <= 0.1 * rng)
        bear = (c < o) & (np.r_[False, c[:-1] > o[:-1]]) & (np.r_[False, False, c[:-2] > o[:-2]])
        bear &= (c < np.minimum(np.r_[np.nan, o[:-1]], np.r_[np.nan, np.nan, o[:-2]])) & (o >= np.maximum(np.r_[np.nan, c[:-1]], np.r_[np.nan, np.nan, c[:-2]]))
        bear &= ((h - np.maximum(o, c)) <= 0.1 * rng)
    out = []
    for m, d in ((bull, 1), (bear, -1)):
        keep = []
        for t in np.flatnonzero(m):
            if t < 55 or not np.isfinite(A[t]):
                continue
            if d > 0:
                lvl = l[t - 2:t + 1].min(); w = l[t - 52:t - 2]
            else:
                lvl = h[t - 2:t + 1].max(); w = h[t - 52:t - 2]
            if np.sum(np.abs(w - lvl) <= 0.25 * A[t]) >= 3:
                keep.append(t)
        keep = np.array(keep, np.int64)
        if len(keep):
            sl = (l[keep] - 0.1 * A[keep]) if d > 0 else (h[keep] + 0.1 * A[keep])
            out.append(E.orders(keep, np.full(len(keep), d), sl, _side(c[keep], sl)))
    return {"main": pd.concat(out)} if out else {}


# ------------------------------------------------------------------ P07 E3 momentum candle
def gen_P07(B, mkt, tf):
    A = _a(B); o, h, l, c = B.o, B.h, B.l, B.c
    ab = np.abs(c - o); prev = pd.Series(ab).rolling(10).max().shift(1).to_numpy()
    with np.errstate(invalid="ignore"):
        m = (ab > prev) & np.isfinite(A)
    t = np.flatnonzero(m); d = np.sign(c[t] - o[t]).astype(int); t, d = t[d != 0], d[d != 0]
    sl = np.where(d > 0, l[t] - 0.1 * A[t], h[t] + 0.1 * A[t])
    return {"main": E.orders(t, d, sl, _side(c[t], sl), cut=o[t])}


# ------------------------------------------------------------------ P08 E4 slow reversal / P09 E5 fast reversal
def gen_P08(B, mkt, tf):
    A = _a(B); c, h, l = B.c, B.h, B.l
    X, _ = last_swings(B, 2)
    out = {"main SL swing": [], "SL signal bar": []}
    for d in (-1, 1):
        if d < 0:
            struct = (X["l3_val"] < X["l2_val"]) & (X["l2_val"] < X["l1_val"]) & (X["h1_piv"] > X["l1_piv"])
            lvl = X["l1_val"]; sl_main = X["h1_val"] + 0.1 * A; sl_bar = h + 0.1 * A
        else:
            struct = (X["h3_val"] > X["h2_val"]) & (X["h2_val"] > X["h1_val"]) & (X["l1_piv"] > X["h1_piv"])
            lvl = X["h1_val"]; sl_main = X["l1_val"] - 0.1 * A; sl_bar = l - 0.1 * A
        t = np.flatnonzero(struct & first_cross(c, lvl, d) & np.isfinite(A))
        for lab, slv in (("main SL swing", sl_main), ("SL signal bar", sl_bar)):
            out[lab].append(E.orders(t, np.full(len(t), d), slv[t], _side(c[t], slv[t])))
    return {k: pd.concat(v) for k, v in out.items()}


def gen_P09(B, mkt, tf):
    A = _a(B); c, h, l = B.c, B.h, B.l; n = len(c)
    X, _ = last_swings(B, 2)
    hh = pd.Series(h); ll = pd.Series(l)
    out = {"main SL top": [], "SL signal bar": []}
    for d in (-1, 1):
        if d < 0:
            first_after = (X["l1_piv"] > X["h1_piv"]) & (X["l2_piv"] < X["h1_piv"])
            top = X["h1_val"]; piv = X["h1_piv"]; lvl = X["l1_val"]
        else:
            first_after = (X["h1_piv"] > X["l1_piv"]) & (X["h2_piv"] < X["l1_piv"])
            top = X["l1_val"]; piv = X["l1_piv"]; lvl = X["h1_val"]
        t = np.flatnonzero(first_after & first_cross(c, lvl, d) & np.isfinite(A))
        keep = []
        for ti in t:
            p = int(piv[ti])
            if p < 0:
                continue
            seg = h[p + 1:ti + 1] if d < 0 else l[p + 1:ti + 1]
            if len(seg) and ((d < 0 and seg.max() > top[ti]) or (d > 0 and seg.min() < top[ti])):
                continue
            keep.append(ti)
        t = np.array(keep, np.int64)
        if not len(t):
            continue
        sl_main = top[t] - d * 0.1 * A[t]
        sl_bar = (h[t] + 0.1 * A[t]) if d < 0 else (l[t] - 0.1 * A[t])
        out["main SL top"].append(E.orders(t, np.full(len(t), d), sl_main, _side(c[t], sl_main)))
        out["SL signal bar"].append(E.orders(t, np.full(len(t), d), sl_bar, _side(c[t], sl_bar)))
    return {k: pd.concat(v) for k, v in out.items() if v}


# ------------------------------------------------------------------ P10 E6 wick fill
def gen_P10(B, mkt, tf):
    A = _a(B); o, h, l, c = B.o, B.h, B.l, B.c; n = len(c)
    rng = h - l; uw = h - np.maximum(o, c); lw = np.minimum(o, c) - l
    V = {"main TP wick": [], "TP 1:1": []}
    with np.errstate(invalid="ignore"):
        upA = np.flatnonzero((uw >= 0.5 * A) & (uw >= 0.6 * rng))
        dnA = np.flatnonzero((lw >= 0.5 * A) & (lw >= 0.6 * rng))
    for Aidx, d in ((upA, 1), (dnA, -1)):
        for a in Aidx:
            top = max(o[a], c[a]) if d > 0 else min(o[a], c[a])
            for t in range(a + 1, min(a + 6, n - 1)):
                if (d > 0 and h[a + 1:t + 1].max() > h[a]) or (d < 0 and l[a + 1:t + 1].min() < l[a]):
                    break
                if (d > 0 and c[t] > top) or (d < 0 and c[t] < top):
                    tp = h[a] if d > 0 else l[a]
                    sl = (l[a:t + 1].min() - 0.1 * A[t]) if d > 0 else (h[a:t + 1].max() + 0.1 * A[t])
                    if d * (tp - c[t]) > 0 and np.isfinite(sl):
                        V["main TP wick"].append((t, d, sl, tp)); V["TP 1:1"].append((t, d, sl, _side(c[t], sl)))
                    break
    return {k: E.orders([x[0] for x in v], [x[1] for x in v], [x[2] for x in v], [x[3] for x in v]) for k, v in V.items() if v}


# ------------------------------------------------------------------ P11 E7 fake-out
def gen_P11(B, mkt, tf):
    A = _a(B); o, h, l, c = B.o, B.h, B.l, B.c
    Hr = pd.Series(h).rolling(20).max().shift(2).to_numpy(); Lr = pd.Series(l).rolling(20).min().shift(2).to_numpy()
    A2 = np.r_[np.nan, np.nan, A[:-2]]; A1 = np.r_[np.nan, A[:-1]]
    pc = np.r_[np.nan, c[:-1]]; po = np.r_[np.nan, o[:-1]]; ph = np.r_[np.nan, h[:-1]]; pl = np.r_[np.nan, l[:-1]]
    with np.errstate(invalid="ignore"):
        rng_ok = (Hr - Lr) <= 3 * A2
        big = np.abs(pc - po) >= 1.2 * A1
        bear_break = rng_ok & big & (pc < Lr) & (c > Lr) & (c < Hr)                # fake breakdown -> buy
        bull_break = rng_ok & big & (pc > Hr) & (c < Hr) & (c > Lr)                # fake breakout -> sell
    V = {"main TP range edge": [], "TP 1:1": []}
    for m, d in ((bear_break, 1), (bull_break, -1)):
        t = np.flatnonzero(m)
        sl = (pl[t] - 0.1 * A[t]) if d > 0 else (ph[t] + 0.1 * A[t])
        tp_edge = Hr[t] if d > 0 else Lr[t]
        V["main TP range edge"].append(E.orders(t, np.full(len(t), d), sl, tp_edge).assign(grp=Hr[t] * 1e6 + Lr[t]))
        V["TP 1:1"].append(E.orders(t, np.full(len(t), d), sl, _side(c[t], sl)).assign(grp=Hr[t] * 1e6 + Lr[t]))
    return {k: pd.concat(v) for k, v in V.items()}


def post_P11(T, O):
    """Stop trading a range after two consecutive losses in it (P11)."""
    if "grp" not in O or not len(T):
        return np.ones(len(T), bool)
    g = O.grp.to_numpy()[T.oi.to_numpy()]
    keep = np.ones(len(T), bool); streak = {}
    for i in np.argsort(T.t.to_numpy(), kind="stable"):
        k = g[i]
        if streak.get(k, 0) >= 2:
            keep[i] = False; continue
        streak[k] = streak.get(k, 0) + 1 if T.R.to_numpy()[i] <= 0 else 0
    return keep


# ------------------------------------------------------------------ P12 F1 / P13 F2 / P14 F3 with Clean Traffic
def gen_P12(B, mkt, tf):
    A = _a(B); c, h, l = B.c, B.h, B.l
    X, _ = last_swings(B, 2)
    V = {"main clean SL top": [], "clean SL signal bar": [], "no filter SL top": []}
    for d in (-1, 1):
        if d < 0:
            st = (X["l2_val"] < X["l1_val"]) & (X["h1_piv"] > X["l1_piv"]); lvl = X["l1_val"]; top = X["h1_val"]
            a_leg, b_leg = X["l1_piv"], X["h1_piv"]
        else:
            st = (X["h2_val"] > X["h1_val"]) & (X["l1_piv"] > X["h1_piv"]); lvl = X["h1_val"]; top = X["l1_val"]
            a_leg, b_leg = X["h1_piv"], X["l1_piv"]
        t = np.flatnonzero(st & first_cross(c, lvl, d) & np.isfinite(A))
        for ti in t:
            sl_top = top[ti] - d * 0.1 * A[ti]; sl_bar = (h[ti] + 0.1 * A[ti]) if d < 0 else (l[ti] - 0.1 * A[ti])
            V["no filter SL top"].append((ti, d, sl_top, _side(c[ti], sl_top)))
            if clean_leg(B, int(a_leg[ti]), int(b_leg[ti])):
                V["main clean SL top"].append((ti, d, sl_top, _side(c[ti], sl_top)))
                V["clean SL signal bar"].append((ti, d, sl_bar, _side(c[ti], sl_bar)))
    return {k: E.orders([x[0] for x in v], [x[1] for x in v], [x[2] for x in v], [x[3] for x in v]) for k, v in V.items() if v}


def gen_P13(B, mkt, tf):
    A = _a(B); c, o = B.c, B.o
    X, S = last_swings(B, 2)
    lows = S[S.kind == -1]; lp = lows.piv.to_numpy(); highs = S[S.kind == 1]; hp = highs.piv.to_numpy()
    V = {"main clean": [], "no filter": []}
    for d in (-1, 1):
        if d < 0:
            st = (X["h1_val"] < X["h2_val"]) & (X["l1_piv"] > X["h2_piv"]) & (X["h1_piv"] > X["l1_piv"]); lvl = X["l1_val"]
            lhv, lhp, topp = X["h1_val"], X["h1_piv"], X["h2_piv"]
        else:
            st = (X["l1_val"] > X["l2_val"]) & (X["h1_piv"] > X["l2_piv"]) & (X["l1_piv"] > X["h1_piv"]); lvl = X["h1_val"]
            lhv, lhp, topp = X["l1_val"], X["l1_piv"], X["l2_piv"]
        t = np.flatnonzero(st & first_cross(c, lvl, d) & np.isfinite(A))
        for ti in t:
            p = int(lhp[ti])
            red = (c[p] < o[p]) or (p + 1 < len(c) and c[p + 1] < o[p + 1]) if d < 0 else (c[p] > o[p]) or (p + 1 < len(c) and c[p + 1] > o[p + 1])
            if not red:
                continue
            sl = lhv[ti] - d * 0.1 * A[ti]
            V["no filter"].append((ti, d, sl, _side(c[ti], sl)))
            tpv = int(topp[ti])
            q = (np.searchsorted(lp, tpv) - 1) if d < 0 else (np.searchsorted(hp, tpv) - 1)
            if q >= 0:
                a_leg = int(lp[q]) if d < 0 else int(hp[q])
                if clean_leg(B, a_leg, tpv):
                    V["main clean"].append((ti, d, sl, _side(c[ti], sl)))
    return {k: E.orders([x[0] for x in v], [x[1] for x in v], [x[2] for x in v], [x[3] for x in v]) for k, v in V.items() if v}


def gen_P14(B, mkt, tf):
    A = _a(B); o, h, l, c = B.o, B.h, B.l, B.c; n = len(c)
    body = np.abs(c - o); uw = h - np.maximum(o, c); lw = np.minimum(o, c) - l
    lo10 = pd.Series(l).rolling(10).min().shift(1).to_numpy(); hi10 = pd.Series(h).rolling(10).max().shift(1).to_numpy()
    pc = np.r_[np.nan, c[:-1]]; A1 = np.r_[np.nan, A[:-1]]
    base = np.maximum(body, 0.05 * A)
    with np.errstate(invalid="ignore"):
        sell = (pc - lo10 >= 3 * A1) & (uw >= 2 * base) & (lw <= 0.3 * base)
        buy = (hi10 - pc >= 3 * A1) & (lw >= 2 * base) & (uw <= 0.3 * base)
    V = {"main clean": [], "no filter": []}
    for m, d in ((sell, -1), (buy, 1)):
        for t in np.flatnonzero(m):
            if t < 12:
                continue
            sl = (h[t] + 0.1 * A[t]) if d < 0 else (l[t] - 0.1 * A[t])
            V["no filter"].append((t, d, sl, _side(c[t], sl)))
            if clean_leg(B, t - 10, t - 1):
                V["main clean"].append((t, d, sl, _side(c[t], sl)))
    return {k: E.orders([x[0] for x in v], [x[1] for x in v], [x[2] for x in v], [x[3] for x in v]) for k, v in V.items() if v}


# ------------------------------------------------------------------ P15 HL test that fails -> HH (and LH -> LL)
def gen_P15(B, mkt, tf, k=2):
    A = _a(B); h, l, c = B.h, B.l, B.c
    X, _ = last_swings(B, k)
    up = (X["h1_val"] > X["h2_val"]) & (X["l1_val"] > X["l2_val"]) & (X["h1_piv"] > X["l1_piv"])
    dn = (X["h1_val"] < X["h2_val"]) & (X["l1_val"] < X["l2_val"]) & (X["l1_piv"] > X["h1_piv"])
    B.trail_lo = X["l1_val"]; B.trail_hi = X["h1_val"]
    B.ctl_mask = {1: up, -1: dn}
    V = {f"k{k} TOUCH": [], f"k{k} WICK": []}
    used = set()
    for t in np.flatnonzero(up | dn):
        if not np.isfinite(A[t]):
            continue
        if up[t]:
            HL, HH, key = X["l1_val"][t], X["h1_val"][t], ("L", int(X["l1_piv"][t]))
            if t <= X["h1_conf"][t] or key in used:
                continue
            touch = (l[t] <= HL + 0.25 * A[t]) and (l[t] >= HL) and (c[t] > HL)
            wick = (l[t] < HL) and (c[t] > HL)
            if touch or wick:
                used.add(key)
                sl = min(HL, l[t]) - 0.1 * A[t]
                V[f"k{k} {'TOUCH' if touch else 'WICK'}"].append((t, 1, sl, HH))
        else:
            LH, LL, key = X["h1_val"][t], X["l1_val"][t], ("H", int(X["h1_piv"][t]))
            if t <= X["l1_conf"][t] or key in used:
                continue
            touch = (h[t] >= LH - 0.25 * A[t]) and (h[t] <= LH) and (c[t] < LH)
            wick = (h[t] > LH) and (c[t] < LH)
            if touch or wick:
                used.add(key)
                sl = max(LH, h[t]) + 0.1 * A[t]
                V[f"k{k} {'TOUCH' if touch else 'WICK'}"].append((t, -1, sl, LL))
    return {kk: E.orders([x[0] for x in v], [x[1] for x in v], [x[2] for x in v], [x[3] for x in v]) for kk, v in V.items() if v}
