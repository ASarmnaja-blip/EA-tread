"""Hypothesis batch 1 (docs/HYPOTHESIS_BATCH1_PREREG.md): eight pre-registered primaries on gold (DEV 2004-15, CHECK 2016-26) and silver
(2010-26): A3 weekend gap fill, A4 first-hour reversal, A5 Friday de-risking, C1 / C2 round-number touch / cross vs a control grid, D3 GVZ
volatility risk premium, I2 52-week high, I3 all-time high. Research only, paper only.
Usage: python research/hyp/batch1.py   -> data/hyp/batch1.json (+ stdout log)"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "research" / "wrwr"), str(ROOT / "research" / "foundry"), str(ROOT / "research" / "history")]
import contracts as K  # noqa: E402
import signals as SG  # noqa: E402
import engine as E  # noqa: E402
import gates as G  # noqa: E402

OUT = ROOT / "data" / "hyp"
PERIODS = {"DEV": ("2004-01-01", "2016-01-01"), "CHECK": ("2016-01-01", "2026-10-01"), "SILVER": ("2010-01-01", "2026-09-25")}
SEED = 20261001
KB = 999
T2023 = int(pd.Timestamp("2023-01-01").timestamp())


# ------------------------------------------------------------------ data
class Bars:
    pass


def mkbars(t, o, h, l, c, sp, step, atr=None):
    B = Bars()
    B.t = np.asarray(t, np.int64); B.o, B.h, B.l, B.c, B.spread_bp = (np.asarray(x, float) for x in (o, h, l, c, sp))
    B.step = int(step); B.atr = E._atr(B.h, B.l, B.c, 14) if atr is None else np.asarray(atr, float)
    return B


def weekend_after(t, step):
    t = np.asarray(t, np.int64)
    d0 = (t[:-1] + step) // 86400; d1 = t[1:] // 86400
    dow = (d0 + 3) % 7
    return np.r_[d0 + (5 - dow) % 7 <= d1, False]


def h1_atr_on(t_fine, t_h, atr_h):
    """ATR(H1) known at the open of the H1 bar containing each finer bar."""
    k = np.searchsorted(t_h, (np.asarray(t_fine, np.int64) // 3600) * 3600, side="left")
    ok = (k < len(t_h)) & (t_h[np.minimum(k, len(t_h) - 1)] == (np.asarray(t_fine, np.int64) // 3600) * 3600)
    return np.where(ok, atr_h[np.minimum(k, len(t_h) - 1)], np.nan)


def load_gold():
    B1, cuts, _ = SG.load_xau("H1")
    H1 = mkbars(B1.t, B1.o, B1.h, B1.l, B1.c, B1.spread_bp, 3600, B1.atr)
    D = SG.load_xau("D1")[0]
    D1 = mkbars(D.t, D.o, D.h, D.l, D.c, D.spread_bp, 86400, D.atr)
    z = np.load(ROOT / "data" / "history" / "XAUUSD_M5_2009_2026_spliced.npz")
    t5 = z["t"].astype(np.int64)
    g = pd.DataFrame(dict(k=t5 // 3600, o=z["o"], h=z["h"], l=z["l"], c=z["c"])).groupby("k").agg(o=("o", "first"), h=("h", "max"), l=("l", "min"), c=("c", "last"))
    th = g.index.to_numpy(np.int64) * 3600
    atr_h = E._atr(g.h.to_numpy(float), g.l.to_numpy(float), g.c.to_numpy(float), 14)
    hk = (t5 // 3600) * 3600
    dk = pd.Series(H1.spread_bp, index=H1.t)
    sp = dk.reindex(hk).to_numpy(float)
    late = t5 > H1.t[-1]
    sp = np.where(late, z["sp_bp"], sp)
    M5 = mkbars(t5, z["o"], z["h"], z["l"], z["c"], sp, 300, h1_atr_on(t5, th, atr_h))
    return dict(sym="XAUUSD", H1=H1, D1=D1, M5=M5, cuts=cuts, S=50.0, seed_ath=850.0)


def load_silver():
    import xag as X
    B1, cuts, _ = X.load_xag("H1")
    H1 = mkbars(B1.t, B1.o, B1.h, B1.l, B1.c, B1.spread_bp, 3600, B1.atr)
    D = X.load_xag("D1")[0]
    D1 = mkbars(D.t, D.o, D.h, D.l, D.c, D.spread_bp, 86400, D.atr)
    M, _ = X.read_m1()
    t1 = M.t.to_numpy(np.int64)
    g = pd.DataFrame(dict(k=t1 // 300, o=M.o.to_numpy(float), h=M.h.to_numpy(float), l=M.l.to_numpy(float), c=M.c.to_numpy(float))).groupby("k").agg(
        o=("o", "first"), h=("h", "max"), l=("l", "min"), c=("c", "last"))
    t5 = g.index.to_numpy(np.int64) * 300
    sp = pd.Series(H1.spread_bp, index=H1.t).reindex((t5 // 3600) * 3600).to_numpy(float)
    M5 = mkbars(t5, g.o, g.h, g.l, g.c, sp, 300, h1_atr_on(t5, H1.t, H1.atr))
    return dict(sym="XAGUSD", H1=H1, D1=D1, M5=M5, cuts=cuts, S=0.5, seed_ath=49.45)


def cost_bp(sym, sp, t):
    if sym == "XAUUSD":
        return K.cost_bp(sym, sp)
    c = K.cost_bp(sym, sp, entry_t=t)
    return np.where((np.asarray(t) >= T2023) & ~np.isfinite(np.asarray(sp, float)), K.xag_pre2023_constant(), c)


# ------------------------------------------------------------------ trade engine
def simulate_events(B, sym, e, d, stop, tgt, last, eprice=None, pre_stop=None, chunk=20_000):
    """Vectorised first passage for independent events, then one position at a time in entry order. e: first bar of the path; eprice: fixed
    entry price (NaN = open of e); pre_stop: the entry happened inside bar e-1 and that bar already reached the stop (full stop there)."""
    n = len(e)
    e = np.asarray(e, int); d = np.asarray(d, float); stop = np.asarray(stop, float); tgt = np.asarray(tgt, float)
    last = np.minimum(np.asarray(last, int), len(B.o) - 1)
    ep_in = np.full(n, np.nan) if eprice is None else np.asarray(eprice, float)
    pre = np.zeros(n, bool) if pre_stop is None else np.asarray(pre_stop, bool)
    gross = np.zeros(n); ex = np.zeros(n, int)
    ok = (e < len(B.o)) & (last >= e) & np.isfinite(stop) & (stop > 0)
    for a in range(0, n, chunk):
        s = np.arange(a, min(a + chunk, n)); s = s[ok[s] & ~pre[s]]
        if len(s):
            g_, x_ = E.simulate(B, e[s], d[s], stop[s], tgt[s], last[s], eprice=ep_in[s])
            gross[s] = g_; ex[s] = x_
    ep = np.where(np.isfinite(ep_in), ep_in, B.o[np.minimum(e, len(B.o) - 1)])
    # a fixed entry price inside the previous bar: a first path bar opening beyond the stop fills at its open (conservative)
    fe = np.isfinite(ep_in) & ok & ~pre
    sl = ep - d * stop
    gap = fe & np.where(d > 0, B.o[np.minimum(e, len(B.o) - 1)] <= sl, B.o[np.minimum(e, len(B.o) - 1)] >= sl)
    gross[gap] = d[gap] * (B.o[e[gap]] / ep[gap] - 1) * 1e4; ex[gap] = e[gap]
    gross[pre] = -stop[pre] / ep[pre] * 1e4; ex[pre] = np.maximum(e[pre] - 1, 0)
    keep = ok | pre
    order = np.argsort(e, kind="stable")
    take = np.zeros(n, bool); busy = -1
    for i in order:
        if not keep[i]:
            continue
        start = e[i] - 1 if (np.isfinite(ep_in[i])) else e[i]
        if start <= busy:
            continue
        take[i] = True; busy = ex[i]
    idx = np.flatnonzero(take)
    tt = B.t[np.maximum(e[idx] - np.isfinite(ep_in[idx]).astype(int), 0)]
    sp = B.spread_bp[np.maximum(e[idx] - np.isfinite(ep_in[idx]).astype(int), 0)]
    c = cost_bp(sym, sp, tt)
    sw = K.swap_bp(sym, tt, B.t[ex[idx]] + B.step, d[idx])
    sbp = stop[idx] / ep[idx] * 1e4
    return pd.DataFrame(dict(t=tt, d=d[idx], gross_bp=gross[idx], cost_bp=c, swap_bp=sw, stop_bp=sbp,
                             R=(gross[idx] - c - sw) / sbp, gR=gross[idx] / sbp))


# ------------------------------------------------------------------ hypotheses
def ev_A3(M):
    B = M["H1"]; wk = np.flatnonzero(weekend_after(B.t, 3600)); wk = wk[wk + 2 < len(B.t)]
    gap = (B.o[wk + 1] / B.c[wk] - 1) * 1e4
    thr = np.full(len(wk), np.nan)
    for j in range(len(wk)):
        w = np.abs(gap[max(0, j - 104):j])
        if len(w) >= 52:
            thr[j] = np.quantile(w, 0.9)
    m = np.isfinite(thr) & (np.abs(gap) >= thr)
    e = wk[m] + 2
    return B, dict(e=e, d=-np.sign(gap[m]), stop=1.5 * B.atr[e], tgt=np.full(len(e), np.nan), last=e + 23)


def ev_A4(M):
    B = M["H1"]; f = np.flatnonzero(weekend_after(B.t, 3600)) + 1; f = f[f + 1 < len(B.t)]
    mv = B.c[f] - B.o[f]
    m = np.abs(mv) >= 0.5 * B.atr[f]
    e = f[m] + 1
    return B, dict(e=e, d=-np.sign(mv[m]), stop=1.0 * B.atr[e], tgt=np.full(len(e), np.nan), last=e + 5)


def ev_A5(M, sign):
    B = M["H1"]; wk = weekend_after(B.t, 3600)
    u = pd.to_datetime(B.t, unit="s"); e = np.flatnonzero((u.dayofweek == 4) & (u.hour == 17))
    nxt = np.flatnonzero(wk)
    j = np.searchsorted(nxt, e, side="left"); ok = j < len(nxt)
    e = e[ok]; last = nxt[j[ok]]
    ok2 = (last - e) <= 8                                        # the weekend must start the same Friday evening
    e, last = e[ok2], last[ok2]
    return B, dict(e=e, d=np.full(len(e), float(sign)), stop=1.5 * B.atr[e], tgt=np.full(len(e), np.nan), last=last)


def ev_C1(M, offset_frac):
    B = M["M5"]; S = M["S"]; off = offset_frac * S
    h, l, o, c = B.h, B.l, B.o, B.c
    pc = np.r_[np.nan, c[:-1]]
    up = off + S * np.ceil((pc - off) / S + 1e-9); dn = off + S * np.floor((pc - off) / S - 1e-9)
    hmax = pd.Series(h).rolling(288, min_periods=288).max().shift(1).to_numpy()
    lmin = pd.Series(l).rolling(288, min_periods=288).min().shift(1).to_numpy()
    a = B.atr
    with np.errstate(invalid="ignore"):
        tu = (h >= up) & (o < up) & (hmax < up) & np.isfinite(a)
        td = (l <= dn) & (o > dn) & (lmin > dn) & np.isfinite(a)
    iu, id_ = np.flatnonzero(tu), np.flatnonzero(td)
    i = np.r_[iu, id_]; d = np.r_[-np.ones(len(iu)), np.ones(len(id_))]; lev = np.r_[up[iu], dn[id_]]
    o_ = np.argsort(i, kind="stable"); i, d, lev = i[o_], d[o_], lev[o_]
    st = a[i]
    pre = np.where(d < 0, h[i] >= lev + st, l[i] <= lev - st)
    return B, dict(e=i + 1, d=d, stop=st, tgt=st.copy(), last=i + 144, eprice=lev, pre_stop=pre)


def ev_C2(M, offset_frac):
    B = M["M5"]; S = M["S"]; off = offset_frac * S
    h, l, o, c = B.h, B.l, B.o, B.c; a = B.atr; b = 0.25 * a
    with np.errstate(invalid="ignore"):
        Lu = off + S * np.floor((h - b - off) / S); Ld = off + S * np.ceil((l + b - off) / S)
    cmin = pd.Series(c).rolling(12, min_periods=12).min().shift(1).to_numpy()
    cmax = pd.Series(c).rolling(12, min_periods=12).max().shift(1).to_numpy()
    hmax = pd.Series(h).rolling(12, min_periods=12).max().shift(1).to_numpy()
    lmin = pd.Series(l).rolling(12, min_periods=12).min().shift(1).to_numpy()
    with np.errstate(invalid="ignore"):
        cu = np.isfinite(a) & (cmin < Lu) & (hmax < Lu + b) & (h >= Lu + b)
        cd = np.isfinite(a) & (cmax > Ld) & (lmin > Ld - b) & (l <= Ld - b)
    iu, id_ = np.flatnonzero(cu), np.flatnonzero(cd)
    i = np.r_[iu, id_]; d = np.r_[np.ones(len(iu)), -np.ones(len(id_))]
    trig = np.r_[Lu[iu] + b[iu], Ld[id_] - b[id_]]; lev = np.r_[Lu[iu], Ld[id_]]
    o_ = np.argsort(i, kind="stable"); i, d, trig, lev = i[o_], d[o_], trig[o_], lev[o_]
    fill = np.where(d > 0, np.maximum(o[i], trig), np.minimum(o[i], trig))
    stop_lvl = lev - d * 0.75 * a[i]
    st = np.abs(fill - stop_lvl)
    pre = np.where(d > 0, l[i] <= stop_lvl, h[i] >= stop_lvl)
    return B, dict(e=i + 1, d=d, stop=st, tgt=np.full(len(i), np.nan), last=i + 144, eprice=fill, pre_stop=pre)


def gold_vrp_z(G_):
    """z of gold's weekly VRP at every cut (known at the cut)."""
    B = G_["H1"]; cuts = G_["cuts"]
    gv = pd.read_csv(ROOT / "data" / "external" / "GVZ_History.csv")
    gv["DATE"] = pd.to_datetime(gv.DATE, format="%m/%d/%Y"); gv = gv.sort_values("DATE")
    cut_dates = pd.to_datetime(cuts, unit="s").normalize()
    j = np.searchsorted(gv.DATE.values, cut_dates.values, side="right") - 1
    gvz = np.where(j >= 0, gv.GVZ.to_numpy()[np.maximum(j, 0)], np.nan)
    gvz = np.where(cut_dates.values >= gv.DATE.values[0], gvz, np.nan)
    lr = np.r_[np.nan, np.diff(np.log(B.c))]; lr[np.r_[True, np.diff(B.t) != 3600]] = np.nan
    wk = np.searchsorted(cuts, B.t + 3600, side="left") - 1
    rv = pd.Series(lr ** 2).groupby(wk).sum(min_count=80)
    RV = rv.reindex(np.arange(len(cuts)) - 1).to_numpy()              # week ending at cut k = bars closing in (cut_{k-1}, cut_k]
    vrp = (gvz / 100) ** 2 / 52 - RV
    z = np.full(len(cuts), np.nan)
    for k in range(len(cuts)):
        w = vrp[max(0, k - 52):k]; w = w[np.isfinite(w)]
        if len(w) >= 26 and np.isfinite(vrp[k]) and w.std(ddof=1) > 0:
            z[k] = (vrp[k] - w.mean()) / w.std(ddof=1)
    return z


def ev_D3(M, z, cuts_g, sign):
    B = M["H1"]; D1 = M["D1"]
    e_list, d_list, last_list = [], [], []
    for k in range(len(cuts_g) - 1):
        if not np.isfinite(z[k]) or z[k] == 0:
            continue
        e = int(np.searchsorted(B.t, cuts_g[k], side="right"))
        last = int(np.searchsorted(B.t + 3600, cuts_g[k + 1], side="right")) - 1
        if e >= len(B.t) or last <= e:
            continue
        e_list.append(e); last_list.append(last); d_list.append(sign * np.sign(z[k]))
    e = np.array(e_list, int)
    jd = np.searchsorted(D1.t, B.t[e], side="right") - 1
    st = 2 * D1.atr[np.maximum(jd, 0)] * (jd >= 0)
    return B, dict(e=e, d=np.array(d_list), stop=np.where(st > 0, st, np.nan), tgt=np.full(len(e), np.nan), last=np.array(last_list))


def ev_I(M, ath):
    D = M["D1"]; c = D.c
    if ath:
        prev = np.maximum.accumulate(np.r_[M["seed_ath"], c[:-1]])
    else:
        prev = pd.Series(c).rolling(252, min_periods=252).max().shift(1).to_numpy()
    with np.errstate(invalid="ignore"):
        sig = np.flatnonzero(c > prev)
    e = sig + 1; e = e[e < len(c)]
    return D, dict(e=e, d=np.ones(len(e)), stop=2 * D.atr[e], tgt=np.full(len(e), np.nan), last=e + 19)


# ------------------------------------------------------------------ statistics
def weekly(tr, cuts, a, b):
    w0, w1 = np.searchsorted(cuts, int(pd.Timestamp(a).timestamp())), np.searchsorted(cuts, int(pd.Timestamp(b).timestamp()))
    wk = np.searchsorted(cuts, tr.t.to_numpy(np.int64), side="left") - 1
    m = (wk >= w0) & (wk < w1)
    S = np.bincount(wk[m] - w0, tr.R.to_numpy()[m], w1 - w0); N = np.bincount(wk[m] - w0, None, w1 - w0)
    return S, N, tr[m]


def boot_p(S, N, seed=SEED):
    if N.sum() < 5:
        return float("nan"), float("nan")
    m = S.sum() / N.sum()
    idx = G.stationary_indices(len(S), 4, KB, np.random.default_rng(seed))
    ms = S[idx].sum(1) / np.maximum(N[idx].sum(1), 1)
    return float(m), (float((1 + np.sum(ms - m >= m)) / (KB + 1)) if m > 0 else 1.0)


def boot_delta(S1, N1, S0, N0, seed=SEED):
    m1, m0 = S1.sum() / max(N1.sum(), 1), S0.sum() / max(N0.sum(), 1); dl = m1 - m0
    idx = G.stationary_indices(len(S1), 4, KB, np.random.default_rng(seed))
    ds = S1[idx].sum(1) / np.maximum(N1[idx].sum(1), 1) - S0[idx].sum(1) / np.maximum(N0[idx].sum(1), 1)
    return float(dl), (float((1 + np.sum(ds - dl >= dl)) / (KB + 1)) if dl > 0 else 1.0)


def summarize(tr):
    return dict(n=int(len(tr)), mean_R=float(tr.R.mean()) if len(tr) else float("nan"), mean_gross_R=float(tr.gR.mean()) if len(tr) else float("nan"),
                win=float((tr.R > 0).mean()) if len(tr) else float("nan"), total_R=float(tr.R.sum()), cost_R=float((tr.cost_bp / tr.stop_bp).mean()) if len(tr) else float("nan"))


def run_rule(M, gen, cuts, periods):
    B, ev = gen
    tr = simulate_events(B, M["sym"], **ev)
    out = {}
    for p, (a, b) in periods.items():
        S, N, sub = weekly(tr, cuts, a, b)
        m, pv = boot_p(S, N)
        out[p] = dict(**summarize(sub), p=pv, S=S, N=N)
    return out, tr


def main():
    t0 = time.time()
    OUT.mkdir(parents=True, exist_ok=True)
    Gd = load_gold(); print(f"gold loaded ({time.time() - t0:.0f}s): H1 {len(Gd['H1'].t):,}, M5 {len(Gd['M5'].t):,}", flush=True)
    Sv = load_silver(); print(f"silver loaded ({time.time() - t0:.0f}s): H1 {len(Sv['H1'].t):,}, M5 {len(Sv['M5'].t):,}", flush=True)
    gp = {k: v for k, v in PERIODS.items() if k != "SILVER"}; sp = {"SILVER": PERIODS["SILVER"]}
    z = gold_vrp_z(Gd)
    res = {}
    rules = {"A3": lambda M: ev_A3(M), "A4": lambda M: ev_A4(M), "I2": lambda M: ev_I(M, False), "I3": lambda M: ev_I(M, True)}
    for h, gen in rules.items():
        g_out, _ = run_rule(Gd, gen(Gd), Gd["cuts"], gp); s_out, _ = run_rule(Sv, gen(Sv), Sv["cuts"], sp)
        res[h] = {**g_out, **s_out, "sign": 1}
        print(f"{h} done ({time.time() - t0:.0f}s)", flush=True)
    for h, gen in (("A5", lambda M, s: ev_A5(M, s)), ("D3", None)):
        best = None
        for s in (1, -1):
            if h == "A5":
                g_out, _ = run_rule(Gd, gen(Gd, s), Gd["cuts"], {"DEV": PERIODS["DEV"]})
            else:
                g_out, _ = run_rule(Gd, ev_D3(Gd, z, Gd["cuts"], s), Gd["cuts"], {"DEV": PERIODS["DEV"]})
            if best is None or g_out["DEV"]["mean_R"] > best[1]["DEV"]["mean_R"]:
                best = (s, g_out)
        s = best[0]
        if h == "A5":
            g_out, _ = run_rule(Gd, ev_A5(Gd, s), Gd["cuts"], gp); s_out, _ = run_rule(Sv, ev_A5(Sv, s), Sv["cuts"], sp)
        else:
            g_out, _ = run_rule(Gd, ev_D3(Gd, z, Gd["cuts"], s), Gd["cuts"], gp); s_out, _ = run_rule(Sv, ev_D3(Sv, z, Gd["cuts"], s), Sv["cuts"], sp)
        g_out["DEV"]["p"] = min(1.0, 2 * g_out["DEV"]["p"])                 # the DEV sign was chosen from two directions
        res[h] = {**g_out, **s_out, "sign": s}
        print(f"{h} done, DEV sign {s:+d} ({time.time() - t0:.0f}s)", flush=True)
    for h, gen in (("C1", ev_C1), ("C2", ev_C2)):
        entry = {"sign": 1}
        for M, per in ((Gd, gp), (Sv, sp)):
            r_out, _ = run_rule(M, gen(M, 0.0), M["cuts"], per); c_out, _ = run_rule(M, gen(M, 0.37), M["cuts"], per)
            for p in per:
                dl, pv = boot_delta(r_out[p]["S"], r_out[p]["N"], c_out[p]["S"], c_out[p]["N"])
                entry[p] = dict(**{k: v for k, v in r_out[p].items() if k not in ("S", "N", "p")}, control_mean_R=c_out[p]["mean_R"],
                                control_n=c_out[p]["n"], delta=dl, p=pv, tradable_p=r_out[p]["p"])
        res[h] = entry
        print(f"{h} done ({time.time() - t0:.0f}s)", flush=True)
    order = ["A3", "A4", "A5", "C1", "C2", "D3", "I2", "I3"]
    pdev = np.array([res[h]["DEV"]["p"] for h in order], float)
    rej = np.zeros(len(order), bool); o_ = np.argsort(pdev)
    for r, j in enumerate(o_):
        if pdev[j] <= 0.05 / (len(order) - r):
            rej[j] = True
        else:
            break
    print("\nBatch 1 (net R per trade after C4 cost and swap; p one-sided, DEV Holm over 8; C1/C2 p = round minus control grid):")
    print(f"{'hyp':<4s} {'period':<7s} {'n':>6s} {'meanR':>8s} {'grossR':>8s} {'cost':>6s} {'win':>5s} {'totalR':>8s} {'p':>6s}  extra")
    for j, h in enumerate(order):
        r = res[h]
        for p in ("DEV", "CHECK", "SILVER"):
            x = r[p]
            extra = f"delta {x['delta']:+.3f} (control {x['control_mean_R']:+.3f}, n {x['control_n']}); tradable p {x['tradable_p']:.3f}" if "delta" in x else ""
            print(f"{h:<4s} {p:<7s} {x['n']:6d} {x['mean_R']:+8.3f} {x['mean_gross_R']:+8.3f} {x['cost_R']:6.3f} {x['win']:5.2f} {x['total_R']:+8.1f} {x['p']:6.3f}  {extra}")
        chk = r["CHECK"]; sil = r["SILVER"]
        key = "delta" if "delta" in chk else "mean_R"
        passed = bool(rej[j] and chk[key] > 0 and chk["p"] <= 0.05 and sil[key] > 0 and sil["p"] <= 0.10 and chk["mean_R"] > 0 and sil["mean_R"] > 0)
        r["holm_dev"] = bool(rej[j]); r["PASS"] = passed
        print(f"     -> DEV Holm {'reject' if rej[j] else 'keep H0'}; {'PASS' if passed else 'FAIL'}" + (f" (sign {r['sign']:+d})" if h in ("A5", "D3") else ""))
    clean = {h: {p: ({k: v for k, v in x.items() if k not in ("S", "N")} if isinstance(x, dict) else x) for p, x in r.items()} for h, r in res.items()}
    (OUT / "batch1.json").write_text(json.dumps(clean, indent=1, default=float))
    print(f"-> {OUT / 'batch1.json'} ({time.time() - t0:.0f}s)")


if __name__ == "__main__":
    main()
