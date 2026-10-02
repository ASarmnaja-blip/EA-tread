#!/usr/bin/env python3
"""Fine-grained pattern search on H4 and D1 for gold, silver and BTC.

Every H4 and D1 bar is a potential long and short entry. Each is described by
direction-aware measurements taken at the signal close (inside-bar H1
anatomy, breakout distances, failed attempts, volatility state, higher
timeframe position, session, cross-market agreement) and scored under five
exits. A pattern is a timeframe, an exit, a scope (pooled or gold only) and
one to three conditions on those measurements - several million in all.

Ranked on 2009-2019 only, checked on 2020-2026, and the identical search is
run on drift-placebo histories so the best pattern found in fake data sets
the bar the best pattern found in real data has to clear.

Usage: python3 h4d1_pattern_search.py --root <data-snapshot checkout>
         [--placebos 20] [--only-real]
"""
import argparse
import json
import pathlib
import sys
import time
import warnings

import numpy as np
import pandas as pd
from numba import njit

warnings.filterwarnings("ignore")
HERE = pathlib.Path(__file__).parent
TF_SEC = {"M15": 900, "M30": 1800, "H1": 3600, "H4": 14400, "D1": 86400}
EXITS = ("ch20", "ch10", "chand", "t6", "tp2")
MIN_N = {"M15": 300, "M30": 200, "H1": 150, "H4": 150, "D1": 60}
TOP_PAIRS_BEAM = 30
TOP_K = 100
WARM = 260
_M = {}
FRAMES = {}


def complete_h1(m, G):
    """Gold and silver: Candle Lab H1 for the whole span (the MT5 export behind
    spliced_h1 has ~300 H1 bars a year in 2017-2020). BTC: MT5 from 2021 only,
    the first year its export is complete."""
    if m == "BTCUSD":
        b = G.load_h1(m)
        k = b["t"] >= G.C.ts("2021-01-01")
        return {x: (v[k] if isinstance(v, np.ndarray) else v) for x, v in b.items()}
    z = np.load(G.ROOT / "data" / "bundle" / f"bars_{m}_H1.npz")
    out = {x: z[x].astype(float) for x in ("o", "h", "l", "c", "v")}
    out["t"] = z["t"].astype(np.int64)
    out["step"] = 3600
    return out


def setup(root, complete=False):
    g = pathlib.Path(root) / "research" / "grid27k"
    sys.path[:0] = [str(g), str(g.parent / "grid768"), str(g.parent / "candlelab")]
    import complement as CP
    import g27k as K
    import g768 as G
    import lab as L
    import stress_top3 as S
    _M.update(CP=CP, K=K, G=G, L=L, S=S, C=G.C,
              h1={m: complete_h1(m, G) for m in K.MKTS} if complete
              else {m: S.spliced_h1(m) for m in K.MKTS},
              FIRST=CP.FIRST, SPLIT=G.C.ts("2020-01-01"))


def drift_placebo(p):
    L = _M["L"]
    out = {}
    for i, (m, b) in enumerate(_M["h1"].items()):
        mu = np.mean(np.diff(np.log(b["c"])))
        tr = np.exp(mu * np.arange(len(b["c"])))
        det = dict(b, o=b["o"] / tr, h=b["h"] / tr, l=b["l"] / tr, c=b["c"] / tr)
        mb = L.mirror_base(det, 41000 + 100 * p + i)
        out[m] = dict(mb, o=mb["o"] * tr, h=mb["h"] * tr, l=mb["l"] * tr, c=mb["c"] * tr)
    return out


# ------------------------------------------------------------------ simulation
@njit(cache=True)
def sim_all(o, h, l, c, a20, a22, lo10, hi10, lo20, hi20, bo, bh, bl, bt, k0, k1,
            t, s_idx, d_arr, mode):
    n = len(c)
    m = len(s_idx)
    PX = np.full(m, np.nan)
    TX = np.zeros(m, np.int64)
    XJ = np.full(m, -1, np.int64)
    RK = np.full(m, np.nan)
    EP = np.full(m, np.nan)
    for i in range(m):
        s = s_idx[i]
        d = d_arr[i]
        if s + 1 >= n or not np.isfinite(a20[s]):
            continue
        e = s + 1
        ep = o[e]
        risk = 2.0 * a20[s]
        if not risk > 0:
            continue
        stop = ep - d * risk
        tp = ep + d * 2.0 * risk
        best = ep
        j = e
        px = np.nan
        tx = 0
        done = False
        while j < n:
            for q in range(k0[j], k1[j]):
                oq = ep if q == k0[e] else bo[q]
                if (d > 0 and bl[q] <= stop) or (d < 0 and bh[q] >= stop):
                    px = stop if d * (oq - stop) > 0 else oq
                    tx = bt[q]
                    done = True
                    break
                if mode == 4 and ((d > 0 and bh[q] >= tp) or (d < 0 and bl[q] <= tp)):
                    px = tp if d * (tp - oq) > 0 else oq
                    tx = bt[q]
                    done = True
                    break
            if done:
                break
            if d > 0:
                best = max(best, h[j])
            else:
                best = min(best, l[j])
            hit = False
            if mode == 0:
                hit = (c[j] < lo20[j]) if d > 0 else (c[j] > hi20[j])
            elif mode == 1:
                hit = (c[j] < lo10[j]) if d > 0 else (c[j] > hi10[j])
            elif mode == 2:
                hit = (c[j] < best - 3 * a22[j]) if d > 0 else (c[j] > best + 3 * a22[j])
            elif mode == 3:
                hit = j >= e + 5
            else:
                hit = j >= e + 29
            if hit and j + 1 < n:
                j += 1
                px = o[j]
                tx = t[j]
                done = True
                break
            j += 1
        if not done:
            j = n - 1
            px = c[j]
            tx = t[j]
        PX[i] = px
        TX[i] = tx
        XJ[i] = j
        RK[i] = risk
        EP[i] = ep
    return PX, TX, XJ, RK, EP


# ------------------------------------------------------------------ features
def roll_max(a, k):
    return pd.Series(a).rolling(k).max().shift(1).to_numpy()


def roll_min(a, k):
    return pd.Series(a).rolling(k).min().shift(1).to_numpy()


def pct_rank(a, k=250):
    return pd.Series(a).rolling(k, min_periods=100).rank(pct=True).to_numpy()


def h1_anatomy(X):
    """Inside the signal bar, from its H1 bars: where the last hour closed, the
    share of up hours, and how late in the bar the high and the low were made."""
    b = X["b"]
    k0, k1 = X["k0"], X["k1"]
    n = len(k0)
    bh, bl, bc, bo = b["h"], b["l"], b["c"], b["o"]
    last_pos = np.full(n, np.nan)
    up_share = np.full(n, np.nan)
    hi_when = np.full(n, np.nan)
    lo_when = np.full(n, np.nan)
    big_hour = np.full(n, np.nan)
    for i in range(n):
        a, z = k0[i], k1[i]
        if z - a < 2:
            continue
        hh, ll, cc, oo = bh[a:z], bl[a:z], bc[a:z], bo[a:z]
        rng = hh.max() - ll.min()
        if rng <= 0:
            continue
        last_pos[i] = (cc[-1] - ll.min()) / rng
        up_share[i] = np.mean(cc > oo)
        hi_when[i] = np.argmax(hh) / (z - a - 1)
        lo_when[i] = np.argmin(ll) / (z - a - 1)
        big_hour[i] = (hh - ll).max() / rng
    return last_pos, up_share, hi_when, lo_when, big_hour


def market_frame(m, h1, tf):
    """Bars, base measurements and simulated outcomes for one market and timeframe."""
    K, G, C = _M["K"], _M["G"], _M["C"]
    X, A1, A2, a1, a2 = _M.get("frames_for", K.frames_for)(h1, tf)
    sec = TF_SEC[tf]
    o, h, l, c, v, t = X["o"], X["h"], X["l"], X["c"], X["v"], X["t"]
    a14, a20 = X["a14"], X["a20"]
    n = len(c)
    S = pd.Series
    B = dict(t=t, sig_close=t + sec, c=c, a14=a14)
    for k in (5, 10, 20, 55, 100):
        B[f"hi{k}"], B[f"lo{k}"] = roll_max(h, k), roll_min(l, k)
    for k in (250,):
        B[f"hi{k}"], B[f"lo{k}"] = roll_max(h, k), roll_min(l, k)
    B["e20"] = S(c).ewm(span=20, adjust=False).mean().to_numpy()
    B["e50"] = S(c).ewm(span=50, adjust=False).mean().to_numpy()
    B["e200"] = S(c).ewm(span=200, adjust=False).mean().to_numpy()
    a100 = S(a14).rolling(100).mean().to_numpy()
    with np.errstate(invalid="ignore", divide="ignore"):
        B["atr_pct"] = pct_rank(a14)
        B["atr_ratio"] = a14 / a100
        B["squeeze"] = pct_rank((B["hi20"] - B["lo20"]) / a14)
        B["vr"] = v / S(v).rolling(20).mean().shift(1).to_numpy()
        B["bar_rng"] = (h - l) / a14
        rng = (h - l)
        B["body"] = (c - o) / rng
        B["clpos"] = (c - l) / rng
        B["upwick"] = (h - np.maximum(o, c)) / rng
        B["dnwick"] = (np.minimum(o, c) - l) / rng
    for k in (1, 3, 10, 30, 100):
        B[f"ret{k}"] = (c - S(c).shift(k).to_numpy()) / a14
    B["h1_last"], B["h1_up"], B["h1_hiw"], B["h1_low"], B["h1_big"] = h1_anatomy(X)
    # failed breakouts in the last 20 bars: pierced the prior 20-bar extreme, closed back inside
    with np.errstate(invalid="ignore"):
        fu = ((h > B["hi20"]) & (c <= B["hi20"])).astype(float)
        fd = ((l < B["lo20"]) & (c >= B["lo20"])).astype(float)
    B["fail_up"] = S(fu).rolling(20).sum().shift(1).to_numpy()
    B["fail_dn"] = S(fd).rolling(20).sum().shift(1).to_numpy()
    up = (c > S(c).shift(1).to_numpy()).astype(int)
    run_up = np.zeros(n)
    run_dn = np.zeros(n)
    for i in range(1, n):
        run_up[i] = run_up[i - 1] + 1 if up[i] else 0
        run_dn[i] = run_dn[i - 1] + 1 if (c[i] < c[i - 1]) else 0
    B["run_up"], B["run_dn"] = run_up, run_dn
    # bars since the last 55-bar breakout each way
    bu = np.zeros(n)
    bd = np.zeros(n)
    lu = ld = -10 ** 6
    with np.errstate(invalid="ignore"):
        is_bu = c > B["hi55"]
        is_bd = c < B["lo55"]
    for i in range(n):
        bu[i] = min(i - lu, 500)
        bd[i] = min(i - ld, 500)
        if is_bu[i]:
            lu = i
        if is_bd[i]:
            ld = i
    B["since_bu"], B["since_bd"] = bu, bd
    B["htf1"] = K.anchor(X, A1, sec, a1).astype(float)
    B["htf2"] = K.anchor(X, A2, sec, a2).astype(float)
    # position of the signal close inside the higher timeframe's last 20 bars
    ac = np.minimum(np.r_[A1["t"][1:], K.BIG], A1["t"] + a1)
    xc = np.minimum(np.r_[t[1:], K.BIG], t + sec)
    j = np.searchsorted(ac, xc, side="right") - 1
    jj = np.maximum(j, 0)
    ahi = S(A1["h"]).rolling(20).max().to_numpy()
    alo = S(A1["l"]).rolling(20).min().to_numpy()
    with np.errstate(invalid="ignore", divide="ignore"):
        B["htf_pos"] = np.where(j >= 0, (c - alo[jj]) / (ahi[jj] - alo[jj]), np.nan)
    hour = ((t + sec) % 86400) // 3600
    wday = ((t // 86400) + 3) % 7          # 0 = Monday
    B["hour"], B["wday"] = hour, wday
    B["mid55_sign"] = np.sign(c - (B["hi55"] + B["lo55"]) / 2)

    # outcomes for every bar, both directions, every exit
    ok = (t >= _M["FIRST"]) & np.isfinite(a20) & (np.arange(n) >= WARM)
    s_idx = np.flatnonzero(ok)
    s_idx = np.r_[s_idx, s_idx].astype(np.int64)
    d_arr = np.r_[np.ones(len(s_idx) // 2), -np.ones(len(s_idx) // 2)]
    Bb = X["b"]
    spec = C.SPECS[m]
    cost = spec["cost_rt_bp"] / 1e4
    out = dict(m=m, s=s_idx, d=d_arr, t=t[s_idx], n=n)
    for mi, ex in enumerate(EXITS):
        PX, TX, XJ, RK, EP = sim_all(
            o, h, l, c, a20, X["a22"], B["lo10"], B["hi10"], B["lo20"], B["hi20"],
            Bb["o"], Bb["h"], Bb["l"], Bb["t"].astype(np.int64),
            X["k0"].astype(np.int64), X["k1"].astype(np.int64), t.astype(np.int64),
            s_idx, d_arr, mi)
        good = np.isfinite(PX)
        t_ent = t[np.minimum(s_idx + 1, n - 1)]
        nts = np.zeros(len(s_idx))
        nts[good] = C.nights(t_ent[good], TX[good], spec["rollover3"])
        swr = np.where(d_arr > 0, spec["swap_long_bp"], spec["swap_short_bp"]) / 1e4
        with np.errstate(invalid="ignore", divide="ignore"):
            cst = _M["cost_fn"](EP) if "cost_fn" in _M else EP * cost
            R = (d_arr * (PX - EP) - cst - EP * swr * nts) / RK
        out[f"R_{ex}"] = R
        out[f"x_{ex}"] = XJ
        out[f"tx_{ex}"] = TX
        out[f"ep_{ex}"] = EP
        out[f"px_{ex}"] = PX
        out[f"rk_{ex}"] = RK
        out[f"nts_{ex}"] = nts
    FRAMES[(m, tf)] = X
    out["B"] = B
    return out


def direction_features(F):
    """Turn each market's bar measurements into per-event, direction-aware features."""
    B, s, d = F["B"], F["s"], F["d"]
    g = lambda k: B[k][s]
    up = d > 0
    a = g("a14")
    c = g("c")
    f = {}
    with np.errstate(invalid="ignore", divide="ignore"):
        for k in (5, 10, 20, 55, 100):
            ext = np.where(up, g(f"hi{k}"), g(f"lo{k}"))
            f[f"brk{k}"] = d * (c - ext) / a
        for k in (20, 55, 250):
            hi, lo = g(f"hi{k}"), g(f"lo{k}")
            p = (c - lo) / (hi - lo)
            f[f"pos{k}"] = np.where(up, p, 1 - p)
        for k in (1, 3, 10, 30, 100):
            f[f"ret{k}"] = d * g(f"ret{k}")
        f["ema20_50"] = d * (g("e20") - g("e50")) / a
        f["c_ema200"] = d * (c - g("e200")) / a
        f["c_ema50"] = d * (c - g("e50")) / a
        for k in ("atr_pct", "atr_ratio", "squeeze", "vr", "bar_rng", "h1_big"):
            f[k] = g(k)
        f["body"] = d * g("body")
        f["clpos"] = np.where(up, g("clpos"), 1 - g("clpos"))
        f["wick_with"] = np.where(up, g("upwick"), g("dnwick"))
        f["wick_against"] = np.where(up, g("dnwick"), g("upwick"))
        f["h1_last"] = np.where(up, g("h1_last"), 1 - g("h1_last"))
        f["h1_share"] = np.where(up, g("h1_up"), 1 - g("h1_up"))
        f["h1_ext_when"] = np.where(up, g("h1_hiw"), g("h1_low"))
        f["h1_opp_when"] = np.where(up, g("h1_low"), g("h1_hiw"))
        f["fail_with"] = np.where(up, g("fail_up"), g("fail_dn"))
        f["fail_against"] = np.where(up, g("fail_dn"), g("fail_up"))
        f["run_with"] = np.where(up, g("run_up"), g("run_dn"))
        f["since_brk"] = np.where(up, g("since_bu"), g("since_bd"))
        f["since_brk_opp"] = np.where(up, g("since_bd"), g("since_bu"))
        f["htf_pos"] = np.where(up, g("htf_pos"), 1 - g("htf_pos"))
    cat = {"htf1_with": d * g("htf1") > 0, "htf1_against": d * g("htf1") < 0,
           "htf2_with": d * g("htf2") > 0, "htf2_against": d * g("htf2") < 0,
           "mid55_with": d * g("mid55_sign") > 0, "long": up, "short": ~up}
    for hr in np.unique(g("hour")):
        cat[f"hour{int(hr):02d}"] = g("hour") == hr
    for wd in range(5):
        cat[f"wday{wd}"] = g("wday") == wd
    return f, cat


def cross_market(frames):
    """For each event: how many of the other markets are on the same side of
    their 55-bar midpoint, and their average 10-bar move, in this direction."""
    if len(frames) < 2:
        return {m: (np.zeros(len(F["s"])), np.zeros(len(F["s"]))) for m, F in frames.items()}
    ser = {}
    for m, F in frames.items():
        B = F["B"]
        ser[m] = (B["sig_close"], B["mid55_sign"], B["ret10"])
    out = {}
    for m, F in frames.items():
        tq = F["B"]["sig_close"][F["s"]]
        agree, mv = np.zeros(len(tq)), np.zeros(len(tq))
        cnt = 0
        for o, (ts, sg, rt) in ser.items():
            if o == m:
                continue
            j = np.searchsorted(ts, tq, side="right") - 1
            okj = (j >= 0) & (tq - ts[np.maximum(j, 0)] <= 3 * 86400)
            jj = np.maximum(j, 0)
            agree += np.where(okj, np.nan_to_num(sg[jj]), 0)
            mv += np.where(okj, np.nan_to_num(rt[jj]), 0)
            cnt += 1
        out[m] = (F["d"] * agree / cnt, F["d"] * mv / cnt)
    return out


def build(h1s, tf):
    frames = {m: market_frame(m, h1, tf) for m, h1 in h1s.items()}
    xm = cross_market(frames)
    rows = []
    for m, F in frames.items():
        f, cat = direction_features(F)
        f["xm_agree"], f["xm_move"] = xm[m]
        rows.append((m, F, f, cat))
    E = dict(mkt=np.concatenate([np.full(len(F["s"]), m) for m, F, _, _ in rows]),
             t=np.concatenate([F["t"] for _, F, _, _ in rows]),
             s=np.concatenate([F["s"] for _, F, _, _ in rows]),
             d=np.concatenate([F["d"] for _, F, _, _ in rows]))
    for ex in EXITS:
        for k in ("R", "x", "tx", "ep", "px", "rk", "nts"):
            E[f"{k}_{ex}"] = np.concatenate([F[f"{k}_{ex}"] for _, F, _, _ in rows])
    feats = {k: np.concatenate([f[k] for _, _, f, _ in rows]) for k in rows[0][2]}
    cats = {}
    for k in set().union(*[set(c) for _, _, _, c in rows]):
        cats[k] = np.concatenate([c.get(k, np.zeros(len(F["s"]), bool))
                                  for _, F, _, c in rows])
    return E, feats, cats


def conditions(feats, cats, disc):
    names, cols = [], []
    for k, v in feats.items():
        qs = np.unique(np.nanquantile(v[disc], np.linspace(0.1, 0.9, 9)))
        for q in qs:
            names.append(f"{k}>={q:.4g}")
            cols.append(v >= q)
            names.append(f"{k}<={q:.4g}")
            cols.append(v <= q)
    for k, v in cats.items():
        names.append(k)
        cols.append(v)
    keep_n, keep_c, seen = [], [], set()
    for nm, col in zip(names, cols):
        fr = col[disc].mean()
        if fr < 0.02 or fr > 0.98:
            continue
        key = np.packbits(col).tobytes()
        if key in seen:
            continue
        seen.add(key)
        keep_n.append(nm)
        keep_c.append(col)
    return keep_n, np.column_stack(keep_c)


# ------------------------------------------------------------------ search
@njit(cache=True)
def nov_stats(order, mcode, s, x, R, mask):
    """Mean, t and count of R taking signals in time order, one open trade per
    market - the trades an EA following the pattern would actually take."""
    n = 0
    s1 = 0.0
    s2 = 0.0
    busy = -1
    cur = -1
    for k in range(len(order)):
        i = order[k]
        if mcode[i] != cur:
            cur = mcode[i]
            busy = -1
        if not mask[i] or s[i] <= busy or not np.isfinite(R[i]):
            continue
        n += 1
        s1 += R[i]
        s2 += R[i] * R[i]
        busy = x[i]
    if n < 3:
        return n, np.nan, np.nan
    mu = s1 / n
    var = (s2 - n * mu * mu) / (n - 1)
    if var <= 0:
        return n, mu, np.nan
    return n, mu, mu / np.sqrt(var / n)


SHORTLIST = 300
MIN_NOV = {"M15": 150, "M30": 100, "H1": 80, "H4": 80, "D1": 40}
def pair_stats(Bm, R):
    """n, sum and sum of squares of R for every single (diagonal) and pair of conditions."""
    k = Bm.shape[1]
    n, s1, s2 = np.zeros((k, k)), np.zeros((k, k)), np.zeros((k, k))
    for a in range(0, len(R), 200_000):          # row chunks keep M15 memory bounded
        W = Bm[a:a + 200_000].astype(np.float32)
        r = R[a:a + 200_000].astype(np.float32)[:, None]
        n += W.T @ W
        s1 += W.T @ (W * r)
        s2 += W.T @ (W * (r * r))
    return n, s1, s2


def tstat(n, s1, s2):
    with np.errstate(invalid="ignore", divide="ignore"):
        mu = s1 / n
        var = s2 / n - mu * mu
        return mu, mu / np.sqrt(var / n)


def search(tf, E, names, Bm, disc_mask):
    """All singles and pairs (matrix form), triples by beam; the best 300 per
    cell by overlapping t are re-scored on non-overlapping discovery trades,
    which is what the final ranking uses."""
    cands = []
    total = 0
    mcode = pd.factorize(E["mkt"])[0].astype(np.int64)
    order = np.lexsort((E["s"], mcode)).astype(np.int64)
    for scope in _M.get("scopes", ("pooled", "XAUUSD")):
        sm = disc_mask & ((E["mkt"] == scope) if scope != "pooled" else True)
        for ex in EXITS:
            R = E[f"R_{ex}"]
            xj = E[f"x_{ex}"]
            rows = sm & np.isfinite(R) & (E[f"tx_{ex}"] < _M["SPLIT"])
            ridx = np.flatnonzero(rows)
            Bs = Bm[rows]
            Rs = R[rows]
            n, s1, s2 = pair_stats(Bs, Rs)
            mu, t = tstat(n, s1, s2)
            iu = np.triu_indices(len(names))
            total += len(iu[0])
            tt = t[iu].copy()
            tt[~(n[iu] >= MIN_N[tf])] = -np.inf
            order_p = np.argsort(-tt)
            short = [sorted({int(iu[0][k]), int(iu[1][k])}) for k in order_p[:SHORTLIST]]
            for k in order_p[:TOP_PAIRS_BEAM]:
                i, j = iu[0][k], iu[1][k]
                base = Bs[:, i] & Bs[:, j]
                Wb = Bs[base].astype(np.float32)
                Rb = Rs[base].astype(np.float32)
                n3 = Wb.sum(0).astype(np.float64)
                s13 = (Wb * Rb[:, None]).sum(0).astype(np.float64)
                s23 = (Wb * (Rb * Rb)[:, None]).sum(0).astype(np.float64)
                mu3, t3 = tstat(n3, s13, s23)
                total += len(names)
                t3[~(n3 >= MIN_N[tf])] = -np.inf
                for q in np.argsort(-t3)[:10]:
                    if q not in (i, j) and np.isfinite(t3[q]):
                        short.append(sorted({int(i), int(j), int(q)}))
            Rfull = np.where(rows, R, np.nan)
            seen = set()
            for conds in short:
                mask = rows.copy()
                for q in conds:
                    mask &= Bm[:, q]
                key = np.packbits(mask).tobytes()
                if key in seen:
                    continue
                seen.add(key)
                nn, mm, tv = nov_stats(order, mcode, E["s"], xj, Rfull, mask)
                if nn < MIN_NOV[tf] or not np.isfinite(tv):
                    continue
                cands.append(dict(tf=tf, exit=ex, scope=scope, conds=conds,
                                  n_disc=int(nn), R_disc=float(mm), t_disc=float(tv)))
    return cands, total


def no_overlap(E, mask, ex):
    """Greedy in time: one open trade per market, skipping signals while busy."""
    idx = np.flatnonzero(mask)
    keep = []
    for m in np.unique(E["mkt"][idx]):
        ii = idx[E["mkt"][idx] == m]
        ii = ii[np.argsort(E["s"][ii], kind="stable")]
        busy = -1
        xj = E[f"x_{ex}"]
        for i in ii:
            if E["s"][i] <= busy:
                continue
            keep.append(i)
            busy = xj[i]
    return np.array(sorted(keep), int)


def validate(E, Bm, names, c):
    ex = c["exit"]
    R = E[f"R_{ex}"]
    mask = np.ones(len(R), bool)
    for q in c["conds"]:
        mask &= Bm[:, q]
    if c["scope"] != "pooled":
        mask &= E["mkt"] == c["scope"]
    mask &= np.isfinite(R)
    val = mask & (E["t"] >= _M["SPLIT"])
    k = no_overlap(E, val, ex)
    r = R[k]
    out = dict(n_val=len(r), R_val=float(r.mean()) if len(r) else np.nan,
               t_val=float(r.mean() / (r.std(ddof=1) / np.sqrt(len(r))))
               if len(r) > 2 and r.std() > 0 else np.nan,
               totR_val=float(r.sum()))
    for m in ("XAUUSD", "XAGUSD", "BTCUSD"):
        out[f"totR_val_{m}"] = float(r[E["mkt"][k] == m].sum())
    kd = no_overlap(E, mask & (E["t"] < _M["SPLIT"]), ex)
    out["n_disc_nov"] = len(kd)
    out["R_disc_nov"] = float(R[kd].mean()) if len(kd) else np.nan
    out["names"] = [names[q] for q in c["conds"]]
    return out


def run_once(h1s, label):
    t0 = time.time()
    allc, total, store = [], 0, {}
    for tf in _M.get("tfs", ("H4", "D1")):
        E, feats, cats = build(h1s, tf)
        disc = E["t"] < _M["SPLIT"]
        names, Bm = conditions(feats, cats, disc)
        cands, tot = search(tf, E, names, Bm, disc)
        total += tot
        store[tf] = (E, names, Bm)
        allc += cands
        print(f"  [{label}] {tf}: {len(E['t']):,} events, {len(names)} conditions, "
              f"{tot:,} patterns  {time.time() - t0:.0f}s", flush=True)
    seen = set()
    uniq = []
    for c in sorted(allc, key=lambda c: -c["t_disc"]):
        key = (c["tf"], c["exit"], c["scope"], tuple(c["conds"]))
        if key in seen:
            continue
        seen.add(key)
        uniq.append(c)
        if len(uniq) == TOP_K:
            break
    for c in uniq:
        E, names, Bm = store[c["tf"]]
        c.update(validate(E, Bm, names, c))
    return dict(label=label, patterns=total, top=uniq,
                top1_val=uniq[0]["R_val"],
                median_top_val=float(np.nanmedian([c["R_val"] for c in uniq])),
                best_disc_t=uniq[0]["t_disc"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    ap.add_argument("--placebos", type=int, default=20)
    ap.add_argument("--only-real", action="store_true")
    ap.add_argument("--complete-data", action="store_true")
    ap.add_argument("--out", default="h4d1_pattern_search.json")
    a = ap.parse_args()
    t0 = time.time()
    setup(a.root, a.complete_data)
    real = run_once(_M["h1"], "real")
    out = dict(real=real, placebos=[])
    path = HERE / a.out
    path.write_text(json.dumps(out, indent=1, default=str))
    if not a.only_real:
        for p in range(a.placebos):
            r = run_once(drift_placebo(p), f"drift{p}")
            out["placebos"].append({k: v for k, v in r.items() if k != "top"}
                                   | dict(top=r["top"][:10],
                                          top100=[{k: c[k] for k in ("tf", "exit", "n_val", "R_val", "t_val")}
                                                  for c in r["top"]]))
            path.write_text(json.dumps(out, indent=1, default=str))
    report(out)
    path.write_text(json.dumps(out, indent=1, default=str))
    print(f"\n  elapsed {time.time() - t0:.0f}s")


def report(out):
    real = out["real"]
    pl = out["placebos"]
    print("\n" + "=" * 110)
    print(f"REAL: {real['patterns']:,} patterns searched; top {len(real['top'])} by "
          f"discovery t (before {pd.Timestamp(int(_M['SPLIT']), unit='s').date()}), "
          f"validated after it without overlap")
    print("=" * 110)
    for c in real["top"][:25]:
        print(f"  {c['tf']} {c['exit']:<5} {c['scope']:<6} t_disc {c['t_disc']:5.1f} "
              f"R_disc {c['R_disc']:+.3f} (n {c['n_disc']:5d}) | val n {c['n_val']:4d} "
              f"R {c['R_val']:+.3f} t {c['t_val']:+.1f} gold {c['totR_val_XAUUSD']:+.0f}R | "
              + " & ".join(c["names"]))
    if not pl:
        return
    p_top1 = np.array([p["top1_val"] for p in pl])
    p_med = np.array([p["median_top_val"] for p in pl])
    p_t = np.array([p["best_disc_t"] for p in pl])
    print("\nSELECTION-AWARE NULL: the same search on drift-placebo histories")
    print(f"  best discovery t      real {real['best_disc_t']:.2f}   placebo median "
          f"{np.median(p_t):.2f}  max {p_t.max():.2f}")
    print(f"  top-1 validation R    real {real['top1_val']:+.3f}   placebo median "
          f"{np.median(p_top1):+.3f}  max {p_top1.max():+.3f}")
    print(f"  median top-100 val R  real {real['median_top_val']:+.3f}   placebo median "
          f"{np.median(p_med):+.3f}  max {p_med.max():+.3f}")
    bar = p_top1.max()
    cands = [c for c in real["top"] if c["n_val"] >= 30 and c["R_val"] > 0
             and np.isfinite(c["t_val"]) and c["t_val"] >= 2.0 and c["R_val"] > bar
             and (c["scope"] == "XAUUSD" or c["totR_val_XAUUSD"] > 0)]
    whole = real["median_top_val"] > p_med.max()
    print(f"\n  CANDIDATES meeting all registered conditions: {len(cands)}")
    for c in cands:
        print(f"    {c['tf']} {c['exit']} {c['scope']} val R {c['R_val']:+.3f} "
              f"t {c['t_val']:+.1f} n {c['n_val']} | " + " & ".join(c["names"]))
    print(f"  search as a whole beats every placebo search: {'YES' if whole else 'NO'}")
    out["verdict"] = dict(candidates=len(cands), whole=bool(whole), bar_top1=float(bar))


if __name__ == "__main__":
    main()
