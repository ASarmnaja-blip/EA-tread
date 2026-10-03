#!/usr/bin/env python3
"""Stage 2, layer L1 (ledger fresh_markets_search_v2): 60 mechanism variants
in 6 families, parameters fixed in docs/PLAN_FRESH_MARKETS_SEARCH.md.

  F1 two-way Donchian breakout: N 10/20/55 on H4 and D1, with/without the D1
     SMA200 filter, stop 2 or 3 ATR20, exit on the opposite N/2 channel   (24)
  F2 pullback in the D1 SMA200 trend: close beyond the prior k-day extreme
     against the trend (k 3/5/10) or RSI2 <10 / >90; exit on the SMA5 cross
     or after 5 days; stop 2.5 ATR20, time stop 10 days                    (8)
  F3 range fade: close beyond SMA20 +- z sd (z 1.5/2/2.5) on H4 and D1,
     with/without ADX14 < 20; exit when the close crosses SMA20 or after
     10 bars; stop 2.5 ATR20                                              (12)
  F4 compression breakout: Bollinger width in the lowest 10/20% of 250
     bars, then a close outside the prior 20-bar range, both ways, H4 and
     D1; exit on the 10-bar channel or a 2R target; stop 2 ATR20           (8)
  F5 Asian-range breakout: range of 00-07 UTC, an H1 close beyond it at
     07-11 UTC enters at the next open, stop at the far side, exit at
     20:00 UTC; with/without the D1 SMA200 filter                          (2)
  F6 F1 (N 20, stop 2, H4 and D1) and F2 (k 5, SMA5 exit) only when US500 is
     above / below its D1 SMA200                                            (6)

All: entry at the next bar open, stops and targets walked on H1 bars (a gap
fills at the H1 open), exit signals on the bar close fill at the next open,
one position per market per variant, cost and swap as stage 1. Bars use the
22:00 UTC day boundary.

Usage: python3 research/g27k_dev/fresh_search_l1.py --root <snap> real
       python3 research/g27k_dev/fresh_search_l1.py --root <snap> placebo <first> <count>
"""
import argparse
import itertools
import pickle
import sys
import time

import numpy as np
import pandas as pd

import pathlib
HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))
import fresh_markets as FM
import fresh_search_l3 as L3
import h4d1_pattern_search as P
import per_market_search as PMS
import walkforward_controller as W


def variants():
    V = []
    for tf, N, filt, sk in itertools.product(("H4", "D1"), (10, 20, 55), (False, True), (2.0, 3.0)):
        V.append(dict(fam="F1", tf=tf, N=N, filt=filt, stop=sk, regime=None))
    for trig, ex in itertools.product(("k3", "k5", "k10", "rsi2"), ("sma5", "t5")):
        V.append(dict(fam="F2", tf="D1", trig=trig, exit=ex, stop=2.5, regime=None))
    for tf, z, adx in itertools.product(("H4", "D1"), (1.5, 2.0, 2.5), (False, True)):
        V.append(dict(fam="F3", tf=tf, z=z, adx=adx, stop=2.5, regime=None))
    for tf, q, ex in itertools.product(("H4", "D1"), (0.10, 0.20), ("ch10", "tp2")):
        V.append(dict(fam="F4", tf=tf, q=q, exit=ex, stop=2.0, regime=None))
    for filt in (False, True):
        V.append(dict(fam="F5", tf="H1", filt=filt, regime=None))
    for reg in ("on", "off"):
        V.append(dict(fam="F1", tf="H4", N=20, filt=False, stop=2.0, regime=reg))
        V.append(dict(fam="F1", tf="D1", N=20, filt=False, stop=2.0, regime=reg))
        V.append(dict(fam="F2", tf="D1", trig="k5", exit="sma5", stop=2.5, regime=reg))
    for i, v in enumerate(V):
        v["id"] = i
        v["name"] = f"{v['fam']}#{i} " + " ".join(f"{k}={v[k]}" for k in v if k not in ("fam", "id", "name") and v[k] is not None)
    return V


def bars(b, tf):
    """Aggregate H1 to H4 / D1 (22:00 UTC boundary) or pass H1 through; keeps each bar's H1 index range."""
    t = np.asarray(b["t"], np.int64)
    if tf == "H1":
        key = np.arange(len(t))
    else:
        key = (t - 22 * 3600) // (14400 if tf == "H4" else 86400)
    cut = np.flatnonzero(np.diff(key)) + 1
    k0, k1 = np.r_[0, cut], np.r_[cut, len(t)]
    o, h, l, c = (np.asarray(b[x], float) for x in "ohlc")
    X = dict(t=t[k0], o=o[k0], h=np.maximum.reduceat(h, k0), l=np.minimum.reduceat(l, k0), c=c[k1 - 1], k0=k0, k1=k1,
             bo=o, bh=h, bl=l, bt=t)
    S = pd.Series
    pc = np.r_[np.nan, X["c"][:-1]]
    tr = np.nanmax(np.c_[X["h"] - X["l"], np.abs(X["h"] - pc), np.abs(X["l"] - pc)], axis=1)
    X["atr"] = S(tr).rolling(20).mean().to_numpy()
    cs = S(X["c"])
    X["sma20"], X["sd20"], X["sma5"] = cs.rolling(20).mean().to_numpy(), cs.rolling(20).std(ddof=0).to_numpy(), cs.rolling(5).mean().to_numpy()
    X["sma200"] = cs.rolling(200).mean().to_numpy()
    # Wilder ADX14
    up, dn = np.r_[np.nan, np.diff(X["h"])], np.r_[np.nan, -np.diff(X["l"])]
    pdm = np.where((up > dn) & (up > 0), up, 0.0)
    ndm = np.where((dn > up) & (dn > 0), dn, 0.0)
    w = lambda x: S(x).ewm(alpha=1 / 14, adjust=False).mean().to_numpy()
    atrw = w(tr)
    with np.errstate(invalid="ignore", divide="ignore"):
        pdi, ndi = 100 * w(pdm) / atrw, 100 * w(ndm) / atrw
        X["adx"] = w(100 * np.abs(pdi - ndi) / (pdi + ndi))
        bbw = 4 * X["sd20"] / X["sma20"]
    X["bbw_pct"] = S(bbw).rolling(250, min_periods=100).rank(pct=True).to_numpy()
    # RSI2
    dlt = np.diff(X["c"], prepend=np.nan)
    g, ls = S(np.where(dlt > 0, dlt, 0.0)).ewm(alpha=1 / 2, adjust=False).mean(), S(np.where(dlt < 0, -dlt, 0.0)).ewm(alpha=1 / 2, adjust=False).mean()
    with np.errstate(invalid="ignore", divide="ignore"):
        X["rsi2"] = (100 - 100 / (1 + g / ls)).to_numpy()
    return X


def daily_asof(Dd, t_query, arr):
    """Value of a D1 array for the last D1 bar CLOSED before t_query (bar closes 1 day after its start)."""
    j = np.searchsorted(Dd["t"] + 86400, t_query, side="right") - 1
    out = np.full(len(t_query), np.nan)
    ok = j >= 0
    out[ok] = arr[j[ok]]
    return out


def signals(v, X, Dd, us):
    n = len(X["c"])
    c, S = X["c"], pd.Series
    tclose = X["t"] + (14400 if v["tf"] == "H4" else 86400 if v["tf"] == "D1" else 3600)
    trend = None
    if v.get("filt") or v["fam"] == "F2":
        dc, ds = daily_asof(Dd, tclose, Dd["c"]), daily_asof(Dd, tclose, Dd["sma200"])
        trend = np.where(dc > ds, 1, np.where(dc < ds, -1, 0))
        if v["tf"] == "D1":
            trend = np.where(X["c"] > X["sma200"], 1, np.where(X["c"] < X["sma200"], -1, 0))
    d = np.zeros(n, np.int8)
    if v["fam"] == "F1":
        hi, lo = S(X["h"]).rolling(v["N"]).max().shift(1).to_numpy(), S(X["l"]).rolling(v["N"]).min().shift(1).to_numpy()
        d[c > hi] = 1
        d[c < lo] = -1
        if v["filt"]:
            d[d != trend] = 0
    elif v["fam"] == "F2":
        if v["trig"] == "rsi2":
            d[(trend > 0) & (X["rsi2"] < 10)] = 1
            d[(trend < 0) & (X["rsi2"] > 90)] = -1
        else:
            k = int(v["trig"][1:])
            lowk, highk = S(c).shift(1).rolling(k).min().to_numpy(), S(c).shift(1).rolling(k).max().to_numpy()
            d[(trend > 0) & (c < lowk)] = 1
            d[(trend < 0) & (c > highk)] = -1
    elif v["fam"] == "F3":
        d[c < X["sma20"] - v["z"] * X["sd20"]] = 1
        d[c > X["sma20"] + v["z"] * X["sd20"]] = -1
        if v["adx"]:
            d[~(X["adx"] < 20)] = 0
    elif v["fam"] == "F4":
        hi, lo = S(X["h"]).rolling(20).max().shift(1).to_numpy(), S(X["l"]).rolling(20).min().shift(1).to_numpy()
        sq = np.r_[False, (X["bbw_pct"] <= v["q"])[:-1]]
        d[sq & (c > hi)] = 1
        d[sq & (c < lo)] = -1
    elif v["fam"] == "F5":
        hr = (X["t"] // 3600) % 24
        day = X["t"] // 86400
        asia = hr < 7
        df = pd.DataFrame(dict(day=day, h=np.where(asia, X["h"], np.nan), l=np.where(asia, X["l"], np.nan)))
        rh, rl = df.groupby("day").h.transform("max").to_numpy(), df.groupby("day").l.transform("min").to_numpy()
        win = (hr >= 7) & (hr <= 11)
        d[win & (c > rh)] = 1
        d[win & (c < rl)] = -1
        # first breakout of each day only
        first = pd.Series(np.where(d != 0, np.arange(n), n)).groupby(day).transform("min").to_numpy()
        d[np.arange(n) != first] = 0
        X["_rh"], X["_rl"] = rh, rl
        if v["filt"]:
            d[d != trend] = 0
    if v["regime"] is not None:
        uc, usma = daily_asof(us, tclose, us["c"]), daily_asof(us, tclose, us["sma200"])
        on = uc > usma
        d[~(on if v["regime"] == "on" else ~on & np.isfinite(uc))] = 0
    d[~np.isfinite(X["atr"])] = 0
    return d


def simulate(v, X, m, d, C, t0, t1):
    n = len(X["c"])
    spec = C.SPECS[m]
    out, busy = [], -1
    idx = np.flatnonzero((d != 0) & (X["t"] >= t0) & (X["t"] < t1))
    N2 = max(2, v.get("N", 20) // 2)
    if v["fam"] == "F1":
        S = pd.Series
        exh, exl = S(X["h"]).rolling(N2).max().shift(1).to_numpy(), S(X["l"]).rolling(N2).min().shift(1).to_numpy()
    elif v["fam"] == "F4":
        S = pd.Series
        exh, exl = S(X["h"]).rolling(10).max().shift(1).to_numpy(), S(X["l"]).rolling(10).min().shift(1).to_numpy()
    for s in idx:
        dr = int(d[s])
        if s <= busy or s + 1 >= n:
            continue
        e = s + 1
        ep = X["o"][e]
        if v["fam"] == "F5":
            stop = X["_rl"][s] if dr > 0 else X["_rh"][s]
            risk = dr * (ep - stop)
        else:
            risk = v["stop"] * X["atr"][s]
            stop = ep - dr * risk
        if not risk > 0:
            continue
        tp = ep + dr * 2 * risk if (v["fam"] == "F4" and v["exit"] == "tp2") else None
        px, j = None, e
        while j < n:
            for q in range(X["k0"][j], X["k1"][j]):
                oq = X["bo"][q]
                if (dr > 0 and X["bl"][q] <= stop) or (dr < 0 and X["bh"][q] >= stop):
                    px = min(stop, oq) if dr > 0 else max(stop, oq)
                    tx = X["bt"][q]
                    break
                if tp is not None and ((dr > 0 and X["bh"][q] >= tp) or (dr < 0 and X["bl"][q] <= tp)):
                    px = max(tp, oq) if dr > 0 else min(tp, oq)
                    tx = X["bt"][q]
                    break
            if px is not None:
                break
            held = j - e + 1
            c = X["c"][j]
            if v["fam"] == "F1" or (v["fam"] == "F4" and v["exit"] == "ch10"):
                ex = (c < exl[j]) if dr > 0 else (c > exh[j])
            elif v["fam"] == "F2":
                ex = (held >= 5) if v["exit"] == "t5" else ((c > X["sma5"][j]) if dr > 0 else (c < X["sma5"][j]))
                ex = ex or held >= 10
            elif v["fam"] == "F3":
                ex = ((c >= X["sma20"][j]) if dr > 0 else (c <= X["sma20"][j])) or held >= 10
            elif v["fam"] == "F5":
                ex = (X["t"][j] + 3600) % 86400 >= 20 * 3600 or (X["t"][j] // 86400) != (X["t"][e] // 86400)
            else:
                ex = False
            if ex and j + 1 < n:
                j += 1
                px, tx = X["o"][j], X["t"][j]
                break
            j += 1
        if px is None:
            break
        nights = int(C.nights(np.array([X["t"][e]]), np.array([tx]), spec["rollover3"])[0])
        sw = spec["swap_long_bp"] if dr > 0 else spec["swap_short_bp"]
        R = dr * (px - ep) / risk - (spec["cost_rt_bp"] + sw * nights) * 1e-4 * ep / risk
        out.append((m, int(X["t"][e]), int(tx), float(R), dr))
        busy = j
    return out


def run_all(h1s, us_h1, C, t0, t1, V=None):
    V = V or variants()
    us = bars(us_h1, "D1")
    cache = {}
    res = {}
    for m, b in h1s.items():
        for tf in ("H1", "H4", "D1"):
            cache[(m, tf)] = bars(b, tf)
    for v in V:
        rows = []
        for m in h1s:
            X = cache[(m, v["tf"])]
            Dd = cache[(m, "D1")]
            d = signals(v, X, Dd, us)
            rows += simulate(v, X, m, d, C, t0, t1)
        res[v["id"]] = pd.DataFrame(rows, columns=["mkt", "t", "tx", "R", "d"])
    return V, res


def score(V, res, split):
    out = []
    for v in V:
        T = res[v["id"]]
        row = dict(id=v["id"], name=v["name"])
        for nm, sel in (("disc", T.t < split), ("val", T.t >= split)):
            R = T.R[sel].to_numpy()
            row[f"n_{nm}"] = len(R)
            row[f"R_{nm}"] = float(R.mean()) if len(R) else np.nan
            row[f"t_{nm}"] = float(R.mean() / R.std(ddof=1) * np.sqrt(len(R))) if len(R) > 2 and R.std() > 0 else np.nan
        out.append(row)
    return pd.DataFrame(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    ap.add_argument("mode", choices=("real", "placebo"))
    ap.add_argument("first", nargs="?", type=int, default=0)
    ap.add_argument("count", nargs="?", type=int, default=1)
    a = ap.parse_args()
    t0 = time.time()
    P.setup(a.root)
    C = P._M["C"]
    C.SPECS.update(FM.specs(C))
    h1 = {m: L3.load(m) for m in L3.GROUP_A}
    us = L3.load("US500", "2010-01-01")
    lo, sp, hi = W.ts(L3.D0), W.ts(L3.SPLIT), W.ts(L3.SEAL)
    if a.mode == "real":
        V, res = run_all(h1, us, C, lo, hi)
        S = score(V, res, sp)
        (PMS.CACHE / "fresh_l1_real.pkl").write_bytes(pickle.dumps(dict(V=V, res=res, score=S)))
        S = S.sort_values("t_disc", ascending=False)
        print(S.head(15).to_string(index=False, float_format=lambda x: f"{x:+.3f}"))
        print(f"  median disc t of all {len(S)}: {S.t_disc.median():.2f}  {time.time() - t0:.0f}s")
    else:
        P._M["h1"] = h1
        for p in range(a.first, a.first + a.count):
            V, res = run_all(P.drift_placebo(p), us, C, lo, hi)
            S = score(V, res, sp)
            (PMS.CACHE / f"fresh_l1_drift{p}.pkl").write_bytes(pickle.dumps(dict(score=S)))
            print(f"  drift{p}: top-1 disc t {S.t_disc.max():.2f}  median {S.t_disc.median():.2f}  {time.time() - t0:.0f}s", flush=True)


if __name__ == "__main__":
    main()
