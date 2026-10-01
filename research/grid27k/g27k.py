"""G27K (docs/plans/G27K_PREREG.md): 27,648 setups on H4 for XAUUSD, XAGUSD and BTCUSD in one account, entries 2021-10-01..2026-09-30.
Context x entry x confirmation x entry method x stop x exit x pyramiding x direction; stops, take-profits, limits and adds walk the MT5
H1 bars inside each H4 bar; exit signals on the H4 close; broker spread + 1 bp and swap per unit. The same code runs on placebo paths.
Usage: python research/grid27k/g27k.py real | placebo <first> <k> | drift <first> <k> | check   (outputs data/grid27k/)"""
from __future__ import annotations

import heapq
import itertools
import os
import sys
import time
from multiprocessing import Pool
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path[:0] = [str(ROOT / "research" / "grid768")]
import g768 as G  # noqa: E402

C = G.C; L = G.L
MKTS = ["XAUUSD", "XAGUSD", "BTCUSD"]
OTHER = [m for m in G.MKTS if m not in MKTS]
START, SPLIT = G.START, C.ts("2024-10-01")
OUT = ROOT / "data" / "grid27k"; OUT.mkdir(parents=True, exist_ok=True)
CS = ("C1", "C2", "C3", "C4", "C5", "C6", "C7", "C8")
DS = ("D1", "D2", "D3", "D4", "D5", "D6", "D7", "D8")
ES = ("E1", "E2", "E3")
FS = ("F1", "F2")
GS = ("G1", "G2", "G3")
HS = ("H1", "H2", "H3", "H4", "H5", "H6")
IS = ("I1", "I2")
JS = ("J1", "J2")
SIG = list(itertools.product(CS, DS, ES, JS))                 # 384 signal sets
SIM = list(itertools.product(FS, GS, HS, IS))                 # 72 trade-handling sets
TP_R = {"H4": 2.0, "H5": 3.0, "H6": 5.0}
RISK = {"I1": 0.01, "I2": 0.0025}
BIG = np.iinfo(np.int64).max
T0 = time.time()
log = lambda *a: print(f"[{time.time() - T0:6.0f}s]", *a, flush=True)


# ------------------------------------------------------------------ external series, aligned to H4 signal closes (known at that time)
def _daily(path, col, lag_days):
    d = pd.read_csv(ROOT / path); d = d[pd.to_numeric(d[col], errors="coerce").notna()]
    t = pd.to_datetime(d.iloc[:, 0]).to_numpy("datetime64[s]").astype(np.int64) + lag_days * 86400
    return t, d[col].astype(float).to_numpy()


def _asof(t_src, v_src, t_query):
    j = np.searchsorted(t_src, t_query, side="right") - 1
    return np.where(j >= 0, v_src[np.maximum(j, 0)], np.nan)


def externals():
    """DFII10 20-business-day change (2 days publication lag), VIX (1 day), GPR vs its 250-day median (1 day), USD HIGH event times."""
    t, v = _daily("data/macro/fred_DFII10.csv", "DFII10", 2); chg = v - np.r_[np.full(20, np.nan), v[:-20]]
    tv, vv = _daily("data/macro/fred_VIXCLS.csv", "VIXCLS", 1)
    g = pd.read_stata(ROOT / "data/macro/gpr_daily.dta")
    tg = pd.to_datetime(g["date"]).to_numpy("datetime64[s]").astype(np.int64) + 86400
    gv = g["GPRD"].astype(float).to_numpy(); gm = pd.Series(gv).rolling(250, min_periods=120).median().to_numpy()
    cal = pd.read_csv(ROOT / "data/calendar.csv", encoding="cp1252")
    hi = cal[(cal.importance == "HIGH") & (cal.currency == "USD")]
    ev = np.sort(pd.to_datetime(hi.time, format="%Y.%m.%d %H:%M").to_numpy("datetime64[s]").astype(np.int64))
    return dict(rr=(t, chg), vix=(tv, vv), gpr=(tg, gv - gm), ev=ev, ev0=int(ev[0]))


def anchor(X, A, x_sec, a_sec):
    ac = np.minimum(np.r_[A["t"][1:], BIG], A["t"] + a_sec); xc = np.minimum(np.r_[X["t"][1:], BIG], X["t"] + x_sec)
    j = np.searchsorted(ac, xc, side="right") - 1; jj = np.maximum(j, 0)
    mid = (pd.Series(A["h"]).rolling(55).max() + pd.Series(A["l"]).rolling(55).min()).to_numpy() / 2
    with np.errstate(invalid="ignore"):
        v = np.where(j >= 0, np.sign(A["c"][jj] - mid[jj]), 0)
    return np.nan_to_num(v).astype(np.int8)


def rsi(c, n=2):
    d = np.diff(c, prepend=c[0]); up = pd.Series(np.maximum(d, 0)).ewm(alpha=1 / n, adjust=False).mean().to_numpy()
    dn = pd.Series(np.maximum(-d, 0)).ewm(alpha=1 / n, adjust=False).mean().to_numpy()
    with np.errstate(invalid="ignore", divide="ignore"):
        return 100 - 100 / (1 + up / dn)


def prepare(m, h1, ext):
    """Every H4 array, signal ingredient and mask a worker needs for one market."""
    F = G.frames(h1); X = F["H4"]; c, h, l, o = X["c"], X["h"], X["l"], X["o"]; n = len(c)
    S = pd.Series
    M = dict(m=m, t=X["t"], o=o, h=h, l=l, c=c, a14=X["a14"], a20=X["a20"], a22=X["a22"], k0=X["k0"], k1=X["k1"],
             bo=X["b"]["o"], bh=X["b"]["h"], bl=X["b"]["l"], bt=X["b"]["t"].astype(np.int64))
    for k in (10, 20, 55):
        M[f"hi{k}"] = S(h).rolling(k).max().shift(1).to_numpy(); M[f"lo{k}"] = S(l).rolling(k).min().shift(1).to_numpy()
    sw = G.last_swing(X); M["swl"], M["swh"] = sw["sl"], sw["sh"]
    tc = X["t"] + 14400                                           # signal close
    d1 = anchor(X, F["D1"], 14400, 86400); w1 = anchor(X, F["W1"], 14400, 7 * 86400)
    with np.errstate(invalid="ignore", divide="ignore"):
        sq = S((M["hi20"] - M["lo20"]) / X["a14"]).rolling(250, min_periods=100).rank(pct=True).to_numpy()
        apct = S(X["a14"]).rolling(250, min_periods=100).rank(pct=True).to_numpy()
        vr = X["v"] / S(X["v"]).rolling(20).mean().shift(1).to_numpy()
        pos = (c - l) / (h - l)
    e20 = S(c).ewm(span=20, adjust=False).mean().to_numpy(); e50 = S(c).ewm(span=50, adjust=False).mean().to_numpy()
    sma = S(c).rolling(20).mean().to_numpy(); sd = S(c).rolling(20).std(ddof=0).to_numpy(); up, dn = sma + 2 * sd, sma - 2 * sd
    r2 = rsi(c, 2)
    p = lambda a: np.r_[np.nan, a[:-1]]
    with np.errstate(invalid="ignore"):
        Dl = {"D1": c > M["hi20"], "D2": c > M["hi55"], "D3": c > M["hi10"], "D4": (sq <= 0.2) & (c > M["hi20"]),
              "D5": (e20 > e50) & (p(e20) <= p(e50)), "D6": (c > up) & (p(c) <= p(up)), "D7": (c > e50) & (r2 < 10),
              "D8": (c > M["swh"]) & (p(c) <= p(M["swh"]))}
        Ds = {"D1": c < M["lo20"], "D2": c < M["lo55"], "D3": c < M["lo10"], "D4": (sq <= 0.2) & (c < M["lo20"]),
              "D5": (e20 < e50) & (p(e20) >= p(e50)), "D6": (c < dn) & (p(c) >= p(dn)), "D7": (c < e50) & (r2 > 90),
              "D8": (c < M["swl"]) & (p(c) >= p(M["swl"]))}
        rr = _asof(*ext["rr"], tc); vix = _asof(*ext["vix"], tc); gpr = _asof(*ext["gpr"], tc)
        j = np.searchsorted(ext["ev"], tc, side="left"); nxt = np.where(j < len(ext["ev"]), ext["ev"][np.minimum(j, len(ext["ev"]) - 1)], BIG)
        news = (nxt <= tc + 8 * 3600) & (tc >= ext["ev0"])
        Cl = {"C1": np.ones(n, bool), "C2": d1 > 0, "C3": (d1 > 0) & (w1 > 0), "C4": apct >= 0.5, "C5": rr < 0, "C6": vix < 20,
              "C7": gpr >= 0, "C8": ~news}
        Cs = {"C1": np.ones(n, bool), "C2": d1 < 0, "C3": (d1 < 0) & (w1 < 0), "C4": apct >= 0.5, "C5": rr > 0, "C6": vix < 20,
              "C7": gpr >= 0, "C8": ~news}
        El = {"E1": np.ones(n, bool), "E2": vr >= 1.5, "E3": pos >= 0.75}
        Es = {"E1": np.ones(n, bool), "E2": vr >= 1.5, "E3": pos <= 0.25}
    ok = (X["t"] >= START) & np.isfinite(X["a20"]) & np.isfinite(X["a14"])
    M.update(Dl=Dl, Ds=Ds, Cl=Cl, Cs=Cs, El=El, Es=Es, d1=d1, ok=ok)
    s = C.SPECS[m]; M["cost"] = s["cost_rt_bp"] / 1e4; M["swr"] = {1: s["swap_long_bp"] / 1e4, -1: s["swap_short_bp"] / 1e4}
    M["rollover3"] = s["rollover3"]
    return M


def directions(M, Cc, D, E, J):
    d = np.zeros(len(M["c"]), np.int8)
    lo = M["Dl"][D] & M["Cl"][Cc] & M["El"][E] & M["ok"]
    if J == "J2":
        lo &= M["d1"] > 0
        sh = M["Ds"][D] & M["Cs"][Cc] & M["Es"][E] & M["ok"] & (M["d1"] < 0)
        d[sh] = -1
    d[lo] = 1
    return d


def simulate(M, s_idx, d_arr, Fm, Gm, Hm, Im):
    o, h, l, c, a14, a20, a22, t = M["o"], M["h"], M["l"], M["c"], M["a14"], M["a20"], M["a22"], M["t"]
    bo, bh, bl, bt, k0, k1 = M["bo"], M["bh"], M["bl"], M["bt"], M["k0"], M["k1"]
    lo20, hi20, lo10, hi10, swl, swh = M["lo20"], M["hi20"], M["lo10"], M["hi10"], M["swl"], M["swh"]
    n = len(c); tpk = TP_R.get(Hm); add = Im == "I2"; out = []; busy = -1
    for s, d in zip(s_idx, d_arr):
        if s <= busy or s + 1 >= n:
            continue
        N = a20[s]
        if Fm == "F1":
            e = s + 1; q0 = k0[e]; ep = o[e]
        else:
            lim = c[s] - d * 0.5 * N; e = -1
            for jj in range(s + 1, min(s + 4, n)):
                for q in range(k0[jj], k1[jj]):
                    if (d > 0 and bl[q] <= lim) or (d < 0 and bh[q] >= lim):
                        ep = min(bo[q], lim) if d > 0 else max(bo[q], lim); e = jj; q0 = q; break
                if e >= 0:
                    break
            if e < 0:
                continue
        if Gm == "G1":
            sw = swl[s] if d > 0 else swh[s]
            sl = sw - d * 0.1 * a14[s] if (sw == sw and d * (ep - sw) > 0 and abs(ep - sw) <= 4 * a14[s]) else ep - d * 2 * N
        else:
            sl = ep - d * (2.0 if Gm == "G2" else 3.0) * N
        risk = abs(ep - sl)
        if not risk > 0:
            continue
        tp = ep + d * tpk * risk if tpk else 0.0
        units = [ep]; ut = [int(bt[q0])]; stop = sl; best = ep; px = None; j = e; qs = q0
        while j < n:
            for q in range(qs, k1[j]):
                oq = ep if q == q0 else bo[q]; hq = bh[q]; lq = bl[q]
                if (d > 0 and lq <= stop) or (d < 0 and hq >= stop):
                    px = stop if d * (oq - stop) > 0 else oq; tx = int(bt[q]); break
                if tpk and ((d > 0 and hq >= tp) or (d < 0 and lq <= tp)):
                    px = tp if d * (tp - oq) > 0 else oq; tx = int(bt[q]); break
                if add and len(units) < 4:
                    n0 = len(units)
                    while len(units) < 4 and ((d > 0 and hq >= units[-1] + 0.5 * N) or (d < 0 and lq <= units[-1] - 0.5 * N)):
                        lvl = units[-1] + d * 0.5 * N; f = max(lvl, oq) if d > 0 else min(lvl, oq)
                        units.append(f); ut.append(int(bt[q])); stop = max(stop, f - 2 * N) if d > 0 else min(stop, f + 2 * N)
                    if len(units) > n0 and ((d > 0 and lq <= stop) or (d < 0 and hq >= stop)):
                        px = stop; tx = int(bt[q]); break
            if px is not None:
                break
            qs = -1
            if Hm in ("H1", "H2", "H3"):
                best = max(best, h[j]) if d > 0 else min(best, l[j])
                if Hm == "H1":
                    hit = (c[j] < best - 3 * a22[j]) if d > 0 else (c[j] > best + 3 * a22[j])
                elif Hm == "H2":
                    hit = (c[j] < lo20[j]) if d > 0 else (c[j] > hi20[j])
                else:
                    hit = (c[j] < lo10[j]) if d > 0 else (c[j] > hi10[j])
                if hit and j + 1 < n:
                    j += 1; px = o[j]; tx = int(t[j]); break
            j += 1
            if j < n:
                qs = k0[j]
        if px is None:
            j = n - 1; px = c[j]; tx = int(t[j])
        nts = C.nights(np.array(ut, np.int64), np.full(len(ut), tx, np.int64), M["rollover3"])
        sw_ = M["swr"][int(d)]
        R = (sum(d * (px - u) for u in units) - sum(u * (M["cost"] + sw_ * k) for u, k in zip(units, nts))) / risk
        out.append((int(t[e]), tx, R, int(d)))
        busy = j
    return out


def equity(te, tx, R, risk, lo=None, hi=None):
    """Balance compounding with overlapping positions: CAGR and max drawdown of realised balance."""
    sel = np.ones(len(te), bool) if lo is None else (te >= lo) & (te < hi)
    if not sel.any():
        return np.nan, np.nan
    te, tx, R = te[sel], tx[sel], R[sel]; o = np.argsort(te, kind="stable"); te, tx, R = te[o], tx[o], R[o]
    eq = 1.0; peak = 1.0; dd = 0.0; heap = []
    for i in range(len(te)):
        while heap and heap[0][0] <= te[i]:
            _, p = heapq.heappop(heap); eq += p; peak = max(peak, eq); dd = max(dd, 1 - eq / peak)
        heapq.heappush(heap, (tx[i], risk * eq * R[i]))
    while heap:
        _, p = heapq.heappop(heap); eq += p; peak = max(peak, eq); dd = max(dd, 1 - eq / peak)
    t0 = lo if lo is not None else START; t1 = hi if hi is not None else max(int(tx.max()), int(te.max()))
    yrs = max((min(t1, int(tx.max())) - t0) / (365.25 * 86400), 0.25)
    return (eq ** (1 / yrs) - 1) if eq > 0 else -1.0, dd


def summary(trades, risk):
    rows = [(m, *x) for m, tr in trades.items() for x in tr]
    if not rows:
        return dict(n=0)
    mk = np.array([r[0] for r in rows]); te = np.array([r[1] for r in rows], np.int64); tx = np.array([r[2] for r in rows], np.int64)
    R = np.array([r[3] for r in rows]); d = np.array([r[4] for r in rows])
    wk = np.searchsorted(G.CUTS, te, side="right") - 1; keys = np.char.add(np.char.add(mk.astype(str), "|"), wk.astype(str))
    out = dict(n=len(R), per_year=len(R) / 5.0, win=float((R > 0).mean()), R=float(R.mean()), totR=float(R.sum()), p=G.boot_p(R, keys),
               short_share=float((d < 0).mean()))
    ms = list(trades)
    for m in ms:
        s = mk == m; out[f"n_{m}"] = int(s.sum()); out[f"totR_{m}"] = float(R[s].sum())
    elig = [m for m in ms if out[f"n_{m}"] >= 5]
    out["pos_mkts"] = int(sum(out[f"totR_{m}"] > 0 for m in elig)); out["share_pos"] = out["pos_mkts"] / len(elig) if elig else np.nan
    out["cagr"], out["dd"] = equity(te, tx, R, risk)
    for nm, a, b in (("A", START, SPLIT), ("B", SPLIT, BIG)):
        s = (te >= a) & (te < b)
        out[f"n_{nm}"] = int(s.sum()); out[f"R_{nm}"] = float(R[s].mean()) if s.any() else np.nan; out[f"totR_{nm}"] = float(R[s].sum())
        out[f"cagr_{nm}"], out[f"dd_{nm}"] = equity(te, tx, R, risk, a, b if b < BIG else int(max(tx.max(), te.max())) + 1)
    return out


# ------------------------------------------------------------------ workers
_W = {}


def _init(h1s, label):
    ext = externals()
    _W["M"] = {m: prepare(m, b, ext) for m, b in h1s.items()}; _W["label"] = label


def _task(sig):
    Cc, D, E, J = sig; Ms = _W["M"]; res = []
    dirs = {}
    for m, M in Ms.items():
        d = directions(M, Cc, D, E, J); s = np.flatnonzero(d); dirs[m] = (s, d[s])
    for Fm, Gm, Hm, Im in SIM:
        trades = {m: simulate(Ms[m], *dirs[m], Fm, Gm, Hm, Im) for m in Ms}
        row = dict(combo="/".join((Cc, D, E, Fm, Gm, Hm, Im, J)), C=Cc, D=D, E=E, F=Fm, G=Gm, H=Hm, I=Im, J=J)
        row.update(summary(trades, RISK[Im])); res.append(row)
    return res


def run(h1s, label, sigs=None, workers=10):
    sigs = SIG if sigs is None else sigs
    with Pool(workers, initializer=_init, initargs=(h1s, label)) as pool:
        rows = []
        for i, r in enumerate(pool.imap_unordered(_task, sigs, chunksize=1)):
            rows += r
            if (i + 1) % 48 == 0:
                log(f"{label}: {i + 1}/{len(sigs)} signal sets")
    D = pd.DataFrame(rows)
    D["p_holm"] = G.holm(D.p.to_numpy())
    D["pass_basic"] = (D.p < 0.05) & (D.R > 0)
    D["pass_strict"] = (D.p_holm < 0.05) & (D.R > 0) & (D.pos_mkts == len(h1s))
    D.to_csv(OUT / f"g27k_{label}.csv", index=False)
    log(f"{label}: basic {int(D.pass_basic.sum())}, strict {int(D.pass_strict.sum())} of {len(D)}; best totR {D.totR.max():.0f}")
    return D


def placebo_paths(kind, p):
    H1s = {}
    for i, m in enumerate(MKTS):
        b = G.load_h1(m)
        if kind == "placebo":
            H1s[m] = L.mirror_base(b, 17000 + 100 * p + i)
        else:
            mu = np.mean(np.diff(np.log(b["c"]))); tr = np.exp(mu * np.arange(len(b["c"])))
            det = dict(b, o=b["o"] / tr, h=b["h"] / tr, l=b["l"] / tr, c=b["c"] / tr); mb = L.mirror_base(det, 19000 + 100 * p + i)
            H1s[m] = dict(mb, o=mb["o"] * tr, h=mb["h"] * tr, l=mb["l"] * tr, c=mb["c"] * tr)
    return H1s


def main():
    mode = sys.argv[1]
    if mode == "real":
        run({m: G.load_h1(m) for m in MKTS}, "real")
    elif mode in ("placebo", "drift"):
        first, k = int(sys.argv[2]), int(sys.argv[3]); w = int(sys.argv[4]) if len(sys.argv) > 4 else 10
        for p in range(first, first + k):
            run(placebo_paths(mode, p), f"{mode}{p}", workers=w)
    elif mode == "check":
        check()


def check():
    """The top 20 by first-three-year total R and the top 20 by five-year total R, re-run on the other 14 G768 markets."""
    D = pd.read_csv(OUT / "g27k_real.csv")
    pick = pd.concat([D.nlargest(20, "totR_A"), D.nlargest(20, "totR")]).drop_duplicates("combo")
    sigs = sorted({(r.C, r.D, r.E, r.J) for r in pick.itertuples()})
    Dx = run({m: G.load_h1(m) for m in OTHER}, "check_other14", sigs=sigs)
    Dx[Dx.combo.isin(set(pick.combo))].to_csv(OUT / "g27k_check_other14_top.csv", index=False)


if __name__ == "__main__":
    main()
