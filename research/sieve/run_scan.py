"""Layers 1-2 of the sieve (docs/SIEVE_PREREG.md): build scans A / B / B2, leak-check every feature, then the
monthly-Spearman-IC information scan over feature x horizon x mask with BH-FDR on DEV and sign/t checks on CHECK.
Writes data/sieve/scan_<X>.pkl (every test) and data/sieve/layer2.xlsx. Read-only research."""
from __future__ import annotations

import copy
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import sparse, stats

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path[:0] = [str(HERE), str(ROOT / "research" / "foundry"), str(ROOT / "research" / "pilot"), str(ROOT / "research" / "wpwb_weekly")]
import engine as E  # noqa: E402
import features as FT  # noqa: E402

OUT = ROOT / "data" / "sieve"; OUT.mkdir(parents=True, exist_ok=True)
CONDITIONERS = ["rsi14", "adx14", "bb_width_ratio", "atr_pctile", "ret24", "ret120", "z100", "donch55_pos", "c_sma200",
                "eff_ratio24", "var_ratio", "pd_range_pos", "wpwb_vol_ratio", "wpwb_trend_z", "vol_z", "dist_52w_high",
                "rv_ratio", "macd_hist", "cloud_pos", "di_diff"]
CELLS = [f"{a}/{b}" for a in ("CALM", "NORMAL", "HIGH") for b in ("DOWN", "FLAT", "UP")]
SESS = {"S_ASIA": (0, 7), "S_LONDON": (7, 12), "S_NY": (12, 17), "S_LATE": (17, 24)}
T0 = time.time()
log = lambda *a: print(f"[{time.time() - T0:6.0f}s]", *a, flush=True)


# ------------------------------------------------------------------ externals
def externals(include_cross=False):
    import external_traces as X
    import calendar_pit as P
    g = pd.read_csv(ROOT / "data" / "external" / "GVZ_History.csv")
    g = pd.Series(g.GVZ.to_numpy(float), index=pd.to_datetime(g.DATE, format="%m/%d/%Y")).sort_index()
    y2 = X.treasury("nominal")["BC_2YEAR"].dropna().astype(float); y2.index = pd.to_datetime(y2.index)
    rr = X.treasury("real").TC_10YEAR.astype(float); rr.index = pd.to_datetime(rr.index)
    daily = {"gvz_z": (g - g.rolling(252, min_periods=126).mean()) / g.rolling(252, min_periods=126).std(),
             "gvz_chg5": g / g.shift(5) - 1, "us2y_chg5": y2.diff(5), "real10y_chg5": rr.diff(5)}
    cf = X.cftc()
    z = (cf.net - cf.net.rolling(52, min_periods=26).mean()) / cf.net.rolling(52, min_periods=26).std()
    released = {"cftc_mm_z": (cf.release.values.astype("datetime64[s]").astype(np.int64), z.to_numpy(float))}
    cal = P.load_pit()
    hi = cal[(cal.currency == "USD") & (cal.importance == "HIGH") & cal.actual.notna() & cal.forecast.notna()].copy()
    hi["d"] = hi.actual - hi.forecast
    hi["sd"] = hi.groupby("event").d.transform(lambda s: s.shift(1).expanding(6).std())
    hi["sz"] = (hi.d / hi.sd).clip(-5, 5)
    hi = hi.dropna(subset=["sz"])
    hi["abs"] = hi.sz.abs()
    hi = hi.sort_values(["epoch", "abs"]).groupby("epoch").tail(1)
    news = (hi.epoch.to_numpy(np.int64), hi.sz.to_numpy(float))
    return {"daily": daily, "released": released, "news": news}


def cross_aligned(t, step, gold_c):
    out = {}
    lr_g = np.log(gold_c)
    ser = {}
    for sym in ("DXY", "XAGUSD", "US500"):
        z = np.load(ROOT / "data" / "fresh" / f"{sym}_M5.npz")
        s = pd.DataFrame(dict(k=z["t"].astype(np.int64), c=z["c"].astype(float))).sort_values("k")
        q = pd.DataFrame(dict(k=t + step - 300))            # the last M5 bar inside the gold bar (closes with it)
        m = pd.merge_asof(q, s, on="k", direction="backward", tolerance=0)
        ser[sym] = m.c.to_numpy()
    for sym, lab in (("DXY", "dxy"), ("XAGUSD", "xag"), ("US500", "spx")):
        x = pd.Series(np.log(ser[sym]))
        out[f"{lab}_ret24"] = (x - x.shift(24)).to_numpy()
    ratio = pd.Series(lr_g - np.log(ser["XAGUSD"]))
    out["gold_silver_z"] = ((ratio - ratio.rolling(100).mean()) / ratio.rolling(100).std()).to_numpy()
    dv = (pd.Series(lr_g) - pd.Series(lr_g).shift(24)) + pd.Series(out["dxy_ret24"])
    out["gold_dxy_div_z"] = ((dv - dv.rolling(100).mean()) / dv.rolling(100).std()).to_numpy()
    return out


# ------------------------------------------------------------------ bar sets
class Bars:
    pass


def mkbars(t, o, h, l, c, v, step):
    B = Bars(); B.t = np.asarray(t, np.int64); B.o, B.h, B.l, B.c, B.v = (np.asarray(x, float) for x in (o, h, l, c, v)); B.step = step
    B.atr = E._atr(B.h, B.l, B.c, 14); return B


def exness(step):
    import bars as BR
    b5 = BR.load_bars(frozen=False)
    half = np.asarray(b5.sp, float) / 2
    o, h, l, c = (np.asarray(getattr(b5, x), float) + half for x in ("o", "h", "l", "c"))
    df = pd.DataFrame(dict(k=np.asarray(b5.t, np.int64) // step, t=np.asarray(b5.t, np.int64), o=o, h=h, l=l, c=c, v=np.asarray(b5.v, float)))
    g = df.groupby("k").agg(t=("t", "first"), o=("o", "first"), h=("h", "max"), l=("l", "min"), c=("c", "last"), v=("v", "sum"), n=("t", "size"))
    g = g[g.n >= max(1, step // 600)]
    g["t"] = g.index.to_numpy() * step
    return mkbars(g.t, g.o, g.h, g.l, g.c, g.v, step)


def dataset(name):
    ext = externals()
    if name == "A":
        H, _, cuts, cell = E.load()
        B = mkbars(H.t, H.o, H.h, H.l, H.c, H.v, 3600)
        periods = {"DEV": ("2003-05", "2015-01"), "C1": ("2015-01", "2021-01"), "C2": ("2021-01", "2026-09")}
        horizons = (1, 4, 24, 120)
    else:
        B = exness(900)
        H1 = exness(3600)
        cuts, cell = E.regimes(H1.t, H1.c, H1.h, H1.l)
        if name == "B":
            periods = {"DEV": ("2021-01", "2024-07"), "C1": ("2024-07", "2026-10")}
        else:
            periods = {"DEV": ("2023-09", "2025-03"), "C1": ("2025-03", "2026-10")}
            ext["aligned"] = cross_aligned(B.t, 900, B.c)
        horizons = (4, 16, 96)
    return B, cuts, cell, ext, periods, horizons


def leak_check(B, cuts, cell, ext, cols_ref):
    base, _ = FT.build(B, cuts, cell, ext)
    rng = np.random.default_rng(3)
    n = len(B.t)
    for j in (n // 5, n // 2, n - 3000):
        G = copy.copy(B)
        for f in ("o", "h", "l", "c", "v"):
            a = getattr(B, f).copy(); a[j + 1:] *= rng.uniform(0.5, 1.5, n - j - 1); setattr(G, f, a)
        hi = np.maximum.reduce([G.o, G.h, G.l, G.c]); lo = np.minimum.reduce([G.o, G.h, G.l, G.c])
        G.h, G.l = np.r_[B.h[: j + 1], hi[j + 1:]], np.r_[B.l[: j + 1], lo[j + 1:]]
        if "aligned" in ext:
            ext2 = dict(ext); ext2["aligned"] = cross_aligned(G.t, G.step, G.c)
        else:
            ext2 = ext
        g2, _ = FT.build(G, cuts, cell, ext2)
        a, b = base.iloc[: j + 1].to_numpy(), g2.iloc[: j + 1].to_numpy()
        same = (a == b) | (np.isnan(a) & np.isnan(b))
        bad = [base.columns[k] for k in np.flatnonzero(~same.all(0))]
        assert not bad, f"LEAK at j={j}: {bad}"
    log(f"leak check PASS: {base.shape[1]} features x 3 cut points")
    return base


# ------------------------------------------------------------------ scan
def mirror(B, seed=20260930):
    """Placebo (Amendment 1): each bar mirrored at random around the previous close (log moves sign-flipped, high and
    low swapped) - volatility, clock and volume kept, direction destroyed."""
    rng = np.random.default_rng(seed)
    c1 = np.r_[B.o[0], B.c[:-1]]
    lo, lh, ll, lc = (np.log(x / c1) for x in (B.o, B.h, B.l, B.c))
    sgn = np.where(rng.random(len(B.t)) < 0.5, -1.0, 1.0)
    ncl = np.log(B.c[0]) + np.cumsum(np.r_[0.0, (sgn * lc)[1:]])
    nc1 = np.r_[ncl[0] - lc[0], ncl[:-1]]
    o = np.exp(nc1 + sgn * lo); c = np.exp(ncl)
    h = np.exp(nc1 + np.where(sgn > 0, lh, -ll)); l = np.exp(nc1 + np.where(sgn > 0, ll, -lh))
    return mkbars(B.t, o, h, l, c, B.v, B.step)


def scan(name):
    placebo = name.endswith("_PLACEBO")
    B, cuts, cell, ext, periods, horizons = dataset(name.replace("_PLACEBO", ""))
    if placebo:
        B = mirror(B)
        ext = {k: v for k, v in ext.items() if k != "aligned"}
    log(f"scan {name}: {len(B.t):,} bars {pd.to_datetime(B.t[0], unit='s'):%Y-%m}..{pd.to_datetime(B.t[-1], unit='s'):%Y-%m}")
    X, kinds = FT.build(B, cuts, cell, ext)
    X = leak_check(B, cuts, cell, ext, X.columns)
    names = list(X.columns)
    kinds_of = {f: k for k, fs in kinds.items() for f in fs}
    n = len(B.t); step = B.step
    a14 = pd.Series(FT._atr(pd.Series(B.h), pd.Series(B.l), pd.Series(B.c), 14)).to_numpy()
    win = int(104 * 7 * 86400 / step * 5 / 7)
    Y = {}
    for hz in horizons:
        y = np.full(n, np.nan)
        y[: n - 1 - hz] = (B.o[1 + hz:] - B.o[1: n - hz]) / a14[: n - 1 - hz]
        Y[hz] = np.clip(y, -5, 5)
    dt = pd.to_datetime(B.t, unit="s")
    month = (dt.year * 12 + dt.month).to_numpy()
    wk = np.searchsorted(cuts, B.t, side="left") - 1
    cb = np.where((wk >= 0) & (wk < len(cell)), cell[np.clip(wk, 0, len(cell) - 1)], "")
    ent_hour = pd.to_datetime(np.r_[B.t[1:], B.t[-1] + step], unit="s").hour.to_numpy()
    masks = {"ALL": np.ones(n, bool)}
    for c_ in CELLS:
        masks[c_] = cb == c_
    for s, (a, b) in SESS.items():
        masks[s] = (ent_hour >= a) & (ent_hour < b)
    for f in CONDITIONERS:
        s = X[f].astype(float)
        q1 = s.rolling(win, min_periods=win // 4).quantile(1 / 3); q2 = s.rolling(win, min_periods=win // 4).quantile(2 / 3)
        masks[f"{f}_LO"] = (s < q1).to_numpy(); masks[f"{f}_HI"] = (s > q2).to_numpy()
    per_of = np.full(n, "", object)
    for p, (a, b) in periods.items():
        per_of[(dt >= a) & (dt < b)] = p
    valid_y = np.isfinite(Y[max(horizons)]) & (per_of != "")
    for hz in horizons:                        # Amendment 2: one constant drift per period, never a moving one
        for p in periods:
            m_ = (per_of == p) & np.isfinite(Y[hz])
            Y[hz][m_] -= Y[hz][m_].mean()
    # Amendment 1: causal exposure x (trailing percentile rank - 0.5 for levels; raw for events / flags)
    Xc = np.empty((n, len(names)))
    for fi, fn in enumerate(names):
        col = X[fn].astype(float)
        if kinds_of[fn] in ("cont", "ext"):
            Xc[:, fi] = (col.rolling(win, min_periods=win // 4).rank(pct=True) - 0.5).to_numpy()
        else:
            Xc[:, fi] = col.to_numpy()
    log("causal exposures ready")
    rows = []
    for mi, (mname, mk) in enumerate(masks.items()):
        idx = np.flatnonzero(mk & valid_y)
        if len(idx) < 500:
            continue
        um, inv = np.unique(month[idx], return_inverse=True)
        M = sparse.csr_matrix((np.ones(len(idx)), (inv, np.arange(len(idx)))), shape=(len(um), len(idx)))
        per_m = pd.Series(per_of[idx]).groupby(inv).first().to_numpy()
        xs = Xc[idx]; W = np.isfinite(xs); x0 = np.where(W, xs, 0.0)
        for hz in horizons:
            yy = Y[hz][idx]; Wy = np.isfinite(yy); y0 = np.where(Wy, yy, 0.0)
            WW = W & Wy[:, None]
            nn = M @ WW.astype(float)
            P = M @ (np.where(WW, x0, 0.0) * y0[:, None]); Q = M @ np.abs(np.where(WW, x0, 0.0))
            with np.errstate(invalid="ignore", divide="ignore"):
                ed = np.where((nn >= 20) & (Q > 1e-9), P / Q, np.nan)
            for p in periods:
                pm = per_m == p
                icp = ed[pm]
                k = np.isfinite(icp).sum(0)
                with np.errstate(invalid="ignore", divide="ignore"):
                    mu = np.nanmean(icp, axis=0) if pm.any() else np.full(len(names), np.nan)
                    sd = np.nanstd(icp, axis=0, ddof=1) if pm.sum() > 1 else np.full(len(names), np.nan)
                    tt = mu / sd * np.sqrt(k)
                for fi, fn in enumerate(names):
                    rows.append((name, fn, hz, mname, p, float(mu[fi]), float(tt[fi]), int(k[fi])))
        if mi % 10 == 0:
            log(f"  mask {mi + 1}/{len(masks)} {mname}")
    T = pd.DataFrame(rows, columns=["scan", "feature", "h", "mask", "period", "ed", "t", "months"])
    W_ = T.pivot_table(index=["scan", "feature", "h", "mask"], columns="period", values=["ed", "t", "months"])
    W_.columns = [f"{a}_{b}" for a, b in W_.columns]
    W_ = W_.reset_index()
    min_m = 36 if not name.startswith("B2") else 12
    ok = W_["months_DEV"] >= min_m
    W_["p_dev"] = np.where(ok, 2 * stats.t.sf(np.abs(W_["t_DEV"]), np.maximum(W_["months_DEV"] - 1, 1)), np.nan)
    pv = W_.loc[ok, "p_dev"].to_numpy(); m = len(pv)
    order = np.argsort(pv); q = np.empty(m); q[order] = np.minimum.accumulate((pv[order] * m / np.arange(1, m + 1))[::-1])[::-1]
    W_["q_dev"] = np.nan; W_.loc[ok, "q_dev"] = np.minimum(q, 1)
    chk = [p for p in periods if p != "DEV"]
    surv = (W_.q_dev <= 0.05)
    for p in chk:
        surv &= (np.sign(W_[f"ed_{p}"]) == np.sign(W_.ed_DEV)) & (W_[f"t_{p}"].abs() >= 1.5)
    W_["layer2_pass"] = surv
    W_["kind"] = W_.feature.map({f: k for k, fs in kinds.items() for f in fs})
    W_.to_pickle(OUT / f"scan_{name}.pkl")
    log(f"scan {name}: {ok.sum():,} valid DEV tests, {int((W_.q_dev <= 0.05).sum())} pass FDR on DEV, "
        f"{int(surv.sum())} also hold on {chk}")
    return W_


if __name__ == "__main__":
    which = sys.argv[1:] or ["A", "B", "B2"]
    for s in which:
        scan(s)
