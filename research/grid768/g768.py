"""G768 (docs/plans/G768_PREREG.md): 768 combinations on the last five years of 17 MT5 markets, one position per market and combination,
then the same grid on mirrored placebo paths to count fakes. Usage: python research/grid768/g768.py real | placebo <first_seed> <n_paths>"""
from __future__ import annotations

import itertools
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path[:0] = [str(ROOT / "research" / "bundle")]
import common as C  # noqa: E402

L = C.L
OUT = ROOT / "data" / "grid768"; OUT.mkdir(parents=True, exist_ok=True)
MKTS = ["XAUUSD", "XAGUSD", "EURUSD", "USDJPY", "AUDUSD", "USDCHF", "US500", "USTEC", "USOIL", "BTCUSD", "DE30", "JP225", "XCUUSD", "XPTUSD",
        "USDCNH", "USDMXN", "USDZAR"]
START = C.ts("2021-10-01")
CUTS = L.cut_grid(C.ts("2026-10-02"))
GRID = list(itertools.product(("H4", "D1"), ("C1", "C2"), ("D1", "D8", "D11", "D12"), ("E1", "E4"), ("F1",), ("G1", "G3"), ("H6", "H7", "H4"),
                              ("I1", "I4"), ("J1", "J4")))
T0 = time.time()
log = lambda *a: print(f"[{time.time() - T0:6.0f}s]", *a, flush=True)


def load_h1(m):
    z = np.load(ROOT / "data" / "mt5" / f"{m}_H1.npz")
    return dict(t=z["t"].astype(np.int64), o=z["o"].astype(float), h=z["h"].astype(float), l=z["l"].astype(float), c=z["c"].astype(float),
                v=z["tick_volume"].astype(float), step=3600)


def agg(b, key):
    g = pd.DataFrame(dict(k=key, t=b["t"], o=b["o"], h=b["h"], l=b["l"], c=b["c"], v=b["v"])).groupby("k", sort=True).agg(
        t=("t", "first"), o=("o", "first"), h=("h", "max"), l=("l", "min"), c=("c", "last"), v=("v", "sum"))
    X = {k: g[k].to_numpy() for k in ("t", "o", "h", "l", "c", "v")}
    X["t"] = X["t"].astype(np.int64)
    X["a14"] = L.atr(X["h"], X["l"], X["c"], 14); X["a20"] = L.atr(X["h"], X["l"], X["c"], 20); X["a22"] = L.atr(X["h"], X["l"], X["c"], 22)
    return X


def frames(b):
    t = b["t"]
    return {"H4": agg(b, (t - 22 * 3600) // 14400), "D1": agg(b, t // 86400), "W1": agg(b, np.searchsorted(CUTS, t, side="right") - 1)}


def anchor_dir(X, A, a_tf):
    ac = A["t"] + (86400 if a_tf == "D1" else 0)
    if a_tf == "W1":
        ac = np.r_[A["t"][1:], A["t"][-1] + 7 * 86400]
    step = 14400 if a_tf == "D1" else 86400
    j = np.searchsorted(ac, X["t"] + step, side="right") - 1
    mid = (pd.Series(A["h"]).rolling(55).max() + pd.Series(A["l"]).rolling(55).min()).to_numpy() / 2
    v = np.where(j >= 0, np.sign(A["c"][np.maximum(j, 0)] - mid[np.maximum(j, 0)]), 0)
    return np.nan_to_num(v).astype(int)


def last_swing(X, k=2):
    h, l = pd.Series(X["h"]), pd.Series(X["l"])
    sh = ((h > h.shift(1).rolling(k).max()) & (h >= h[::-1].shift(1).rolling(k).max()[::-1])).to_numpy()
    sl = ((l < l.shift(1).rolling(k).min()) & (l <= l[::-1].shift(1).rolling(k).min()[::-1])).to_numpy()
    n = len(h); out = {}
    for nm, flags, vals in (("sh", sh, X["h"]), ("sl", sl, X["l"])):
        arr = np.full(n, np.nan)
        piv = np.flatnonzero(flags); conf = piv + k
        ok = conf < n
        arr[conf[ok]] = vals[piv[ok]]
        out[nm] = pd.Series(arr).ffill().to_numpy()
    return out


def features(F, m, tf):
    X = F[tf]; A = F["D1"] if tf == "H4" else F["W1"]
    X["dhi"] = pd.Series(X["h"]).rolling(20).max().shift(1).to_numpy(); X["dlo"] = pd.Series(X["l"]).rolling(20).min().shift(1).to_numpy()
    with np.errstate(invalid="ignore", divide="ignore"):
        rng20 = (X["dhi"] - X["dlo"]) / X["a14"]
    X["sq"] = pd.Series(rng20).rolling(250, min_periods=100).rank(pct=True).to_numpy()
    X["htf"] = anchor_dir(X, A, "D1" if tf == "H4" else "W1")
    sw = last_swing(X); X["swl"], X["swh"] = sw["sl"], sw["sh"]
    with np.errstate(invalid="ignore", divide="ignore"):
        X["vr"] = X["v"] / pd.Series(X["v"]).rolling(20).mean().shift(1).to_numpy()
    wk = np.searchsorted(CUTS, X["t"], side="right") - 1
    X["wk"] = wk; X["wfirst"] = np.r_[True, wk[1:] != wk[:-1]]
    s = C.SPECS[m]; X["carry"] = 1 if s["swap_long_bp"] < s["swap_short_bp"] else -1
    X["ret60"] = X["c"] / pd.Series(X["c"]).shift(60).to_numpy() - 1
    return X


def xs_ranks(Xs):
    """Per market: direction at each week-first bar from the cross-sectional rank of the 60-bar return known before that bar."""
    rows = []
    for m, X in Xs.items():
        idx = np.flatnonzero(X["wfirst"])
        prev = np.maximum(idx - 1, 0)
        rows.append(pd.DataFrame(dict(m=m, wk=X["wk"][idx], i=idx, r=X["ret60"][prev])))
    R = pd.concat(rows).dropna()
    R["rk"] = R.groupby("wk").r.rank(ascending=False, method="first"); R["cnt"] = R.groupby("wk").r.transform("size")
    R["d"] = np.where(R.rk <= 3, 1, np.where(R.rk > R.cnt - 3, -1, 0))
    out = {m: np.zeros(len(X["c"]), int) for m, X in Xs.items()}
    for r in R[R.d != 0].itertuples():
        out[r.m][r.i] = r.d
    return out


def signals(X, D, xs):
    n = len(X["c"]); c = X["c"]
    with np.errstate(invalid="ignore"):
        if D == "D1":
            d = np.where(c > X["dhi"], 1, np.where(c < X["dlo"], -1, 0))
        elif D == "D8":
            d = np.where(X["sq"] <= 0.2, np.where(c > X["dhi"], 1, np.where(c < X["dlo"], -1, 0)), 0)
        elif D == "D11":
            d = np.where(X["wfirst"], X["carry"], 0)
        else:
            d = xs
    return np.nan_to_num(d).astype(int)


def simulate(X, m, s_idx, d_arr, G, H, I):
    o, h, l, c, a14, a20, a22 = X["o"], X["h"], X["l"], X["c"], X["a14"], X["a20"], X["a22"]
    dhi, dlo, t = X["dhi"], X["dlo"], X["t"]; n = len(c)
    spec = C.SPECS[m]; cost = spec["cost_rt_bp"] / 1e4
    out = []; busy = -1
    for s, d in zip(s_idx, d_arr):
        if s <= busy or s + 1 >= n or not np.isfinite(a20[s]) or not np.isfinite(a14[s]):
            continue
        e = s + 1; ep = o[e]; N = a20[s]
        if G == "G1":
            sw = X["swl"][s] if d > 0 else X["swh"][s]
            if np.isfinite(sw) and d * (ep - sw) > 0 and abs(ep - sw) <= 4 * a14[s]:
                sl = sw - d * 0.1 * a14[s]
            else:
                sl = ep - d * 2 * N
        else:
            sl = ep - d * 2 * N
        risk = abs(ep - sl)
        if risk <= 0:
            continue
        tp = ep + d * 3 * risk if H == "H4" else np.nan
        units = [ep]; stop = sl; best = ep; j = e; px = None
        while j < n:
            if (d > 0 and l[j] <= stop) or (d < 0 and h[j] >= stop):
                px = stop if (j == e or d * (o[j] - stop) > 0) else o[j]; break
            if H == "H4" and ((d > 0 and h[j] >= tp) or (d < 0 and l[j] <= tp)):
                px = tp if (j == e or d * (tp - o[j]) > 0) else o[j]; break
            if I == "I4":
                while len(units) < 4 and ((d > 0 and h[j] >= units[-1] + 0.5 * N) or (d < 0 and l[j] <= units[-1] - 0.5 * N)):
                    units.append(units[-1] + d * 0.5 * N)
                    stop = max(stop, units[-1] - 2 * N) if d > 0 else min(stop, units[-1] + 2 * N)
            best = max(best, h[j]) if d > 0 else min(best, l[j])
            if H == "H6":
                hit = (c[j] < best - 3 * a22[j]) if d > 0 else (c[j] > best + 3 * a22[j])
            elif H == "H7":
                hit = (c[j] < dlo[j]) if d > 0 else (c[j] > dhi[j])
            else:
                hit = False
            if hit and j + 1 < n:
                px = o[j + 1]; j += 1; break
            j += 1
        if px is None:
            px = c[n - 1]; j = n - 1
        nights = int(C.nights(np.array([t[e]]), np.array([t[j]]), spec["rollover3"])[0])
        sw_bp = nights * (spec["swap_long_bp"] if d > 0 else spec["swap_short_bp"]) / 1e4
        gross = sum(d * (px - u) for u in units)
        costs = sum(u * (cost + sw_bp) for u in units)
        out.append((t[e], t[j], (gross - costs) / risk, d, ep))
        busy = j
    return out


def boot_p(R, keys, K=1000, seed=3):
    if len(R) < 10:
        return np.nan
    uk, inv = np.unique(keys, return_inverse=True)
    S = np.bincount(inv, R); N = np.bincount(inv); mu = S.sum() / N.sum()
    rng = np.random.default_rng(seed); idx = rng.integers(0, len(uk), (K, len(uk)))
    bm = (S - mu * N)[idx].sum(1) / N[idx].sum(1)
    return float((bm >= mu).mean())


def holm(p):
    p = np.asarray(p, float); m = np.isfinite(p).sum(); out = np.full(len(p), np.nan); run = 0.0
    for r, i in enumerate(np.argsort(np.where(np.isfinite(p), p, np.inf))):
        if np.isfinite(p[i]):
            run = max(run, min(1.0, (m - r) * p[i])); out[i] = run
    return out


def run_grid(H1s, label):
    F = {m: frames(b) for m, b in H1s.items()}
    Xs = {tf: {m: features(F[m], m, tf) for m in MKTS} for tf in ("H4", "D1")}
    XS = {tf: xs_ranks(Xs[tf]) for tf in ("H4", "D1")}
    rows = []
    for combo in GRID:
        tf, Cc, D, Ee, Ff, G, H, I, J = combo
        allR, allT, keys, trades, mk = [], [], [], [], {}
        for m in MKTS:
            X = Xs[tf][m]
            d = signals(X, D, XS[tf][m])
            ok = (d != 0) & (X["t"] >= START)
            if Ee == "E4":
                ok &= np.nan_to_num(X["vr"]) >= 1.5
            if Cc == "C2":
                ok &= X["htf"] == d
            if J == "J1":
                ok &= d > 0
            else:
                ok &= X["htf"] == d
            s_idx = np.flatnonzero(ok)
            tr = simulate(X, m, s_idx, d[s_idx], G, H, I)
            if tr:
                R = np.array([x[2] for x in tr]); te = np.array([x[0] for x in tr])
                allR.append(R); allT.append(te); keys.append(np.array([f"{m}|{w}" for w in np.searchsorted(CUTS, te, side="right") - 1]))
                mk[m] = (len(R), R.mean())
                trades.append(pd.DataFrame(dict(t=te, t_exit=[x[1] for x in tr], R=R, d=[x[3] for x in tr], ep=[x[4] for x in tr], s=0)))
        if not allR:
            rows.append(dict(combo="/".join(combo), n=0)); continue
        R = np.concatenate(allR); TT = pd.concat(trades)
        eq = C.equity(TT.sort_values("t").assign(s=np.arange(len(TT))), 0.01)
        elig = [v for v in mk.values() if v[0] >= 5]
        rows.append(dict(combo="/".join(combo), tf=tf, C=Cc, D=D, E=Ee, G=G, H=H, I=I, J=J, n=len(R), per_year=len(R) / 5.0, win=float((R > 0).mean()),
                         R=float(R.mean()), p=boot_p(R, np.concatenate(keys)), markets=len(elig),
                         share_pos=float(np.mean([v[1] > 0 for v in elig])) if elig else np.nan, cagr=eq.get("cagr"), dd=eq.get("dd")))
    Dd = pd.DataFrame(rows)
    Dd["p_holm"] = holm(Dd.p.to_numpy())
    Dd["pass_basic"] = (Dd.p < 0.05) & (Dd.R > 0)
    Dd["pass_strict"] = (Dd.p_holm < 0.05) & (Dd.R > 0) & (Dd.share_pos >= 0.6)
    Dd.to_csv(OUT / f"g768_{label}.csv", index=False)
    log(f"{label}: basic {int(Dd.pass_basic.sum())}, strict {int(Dd.pass_strict.sum())} of {len(Dd)}")
    return Dd


def main():
    mode = sys.argv[1]
    H1s = {m: load_h1(m) for m in MKTS}
    if mode == "real":
        run_grid(H1s, "real")
    elif mode == "placebo":
        first, k = int(sys.argv[2]), int(sys.argv[3])
        for p in range(first, first + k):
            P = {m: L.mirror_base(b, 7000 + 100 * p + i) for i, (m, b) in enumerate(H1s.items())}
            run_grid(P, f"placebo{p}")
    else:                                                     # "drift": added after seeing the results (not pre-registered)
        first, k = int(sys.argv[2]), int(sys.argv[3])
        for p in range(first, first + k):
            P = {}
            for i, (m, b) in enumerate(H1s.items()):
                mu = np.mean(np.diff(np.log(b["c"])))           # the market's own average drift per H1 bar
                tr = np.exp(mu * np.arange(len(b["c"])))
                det = dict(b, o=b["o"] / tr, h=b["h"] / tr, l=b["l"] / tr, c=b["c"] / tr)
                mb = L.mirror_base(det, 9000 + 100 * p + i)
                P[m] = dict(mb, o=mb["o"] * tr, h=mb["h"] * tr, l=mb["l"] * tr, c=mb["c"] * tr)
            run_grid(P, f"drift{p}")


if __name__ == "__main__":
    main()
