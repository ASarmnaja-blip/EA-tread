"""X3 (opposite side) and X4 (trend refinements) of docs/BUNDLE_2026-10-01_PREREG.md, on the X1 every-signal trades.
X3a loser-profile fade; X3b Candle Lab reversal with a 1 ATR stop and a 1 ATR Chandelier exit; X4a candle filter; X4b multi-TF agreement;
X4c pyramiding into winners (4 units and unlimited); X4d breakeven at +1 R. Usage: python research/bundle/x3_x4_trend.py"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import common as C  # noqa: E402
import x1_every_signal as X1  # noqa: E402

L = C.L
T0 = time.time()
log = lambda *a: print(f"[{time.time() - T0:6.0f}s]", *a, flush=True)
CUTS = L.cut_grid(C.ts("2026-10-01"))
OTHERS = C.ORIG8 + C.NEW8


def week_of(t):
    return np.searchsorted(CUTS, t, side="right") - 1


def boot_p(R, t, K=2000, seed=7):
    """One-sided p for mean(R) > 0 by a weekly-cluster bootstrap of the centred week sums."""
    R = np.asarray(R, float); w = week_of(np.asarray(t))
    if len(R) < 10:
        return np.nan
    uw, inv = np.unique(w, return_inverse=True)
    S = np.bincount(inv, R); N = np.bincount(inv)
    mu = S.sum() / N.sum()
    Sc = S - mu * N
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(uw), (K, len(uw)))
    bm = Sc[idx].sum(1) / N[idx].sum(1)
    return float((bm >= mu).mean())


def holm(p):
    p = np.asarray(p, float); m = np.isfinite(p).sum(); out = np.full(len(p), np.nan)
    order = np.argsort(np.where(np.isfinite(p), p, np.inf)); run = 0.0
    for r, i in enumerate(order):
        if not np.isfinite(p[i]):
            continue
        run = max(run, min(1.0, (m - r) * p[i])); out[i] = run
    return out


def weekly_bars(B):
    k = week_of(B.t)
    g = pd.DataFrame(dict(k=k, t=B.t, o=B.o, h=B.h, l=B.l, c=B.c)).groupby("k").agg(t=("t", "first"), o=("o", "first"), h=("h", "max"),
                                                                                    l=("l", "min"), c=("c", "last"))
    W = L.Bars(tf="W1", t=g.t.to_numpy(np.int64), o=g.o.to_numpy(), h=g.h.to_numpy(), l=g.l.to_numpy(), c=g.c.to_numpy(),
               hi_pos=np.full(len(g), np.nan), lo_pos=np.full(len(g), np.nan))
    W.atr = L.atr(W.h, W.l, W.c, 14)
    return W


def market_frame(sym, tf):
    """Bars, X1 trades and the four filter features at each trade's signal bar (any market)."""
    B = C.bars(sym, tf)
    T = C.load(f"x1_trades_{sym}_{tf}.pkl")
    if sym in C.METALS:
        W = C.bars(sym, "W1")
    else:
        W = weekly_bars(B if tf == "D1" else C.bars(sym, "D1"))
    F = L.anatomy(B)
    win = {"H1": 24 * 250, "H4": 6 * 250, "D1": 250}[tf]
    F["atr_pct_1y"] = pd.Series(B.atr).rolling(win, min_periods=100).rank(pct=True).to_numpy()
    F["w1_form_pos"] = L.htf_context(B, W, "w1")["w1_form_pos"].to_numpy()
    s = T.s.to_numpy()
    for f in ("lowick_frac", "clv_mean5", "atr_pct_1y", "w1_form_pos"):
        T[f + "_q"] = F[f].to_numpy()[s]
    return B, T, W


def mtf_agree(B, H, d):
    """+1 when the last completed higher-TF bar closes above its 55-bar Donchian midpoint (for longs), -1 below; known at B's close."""
    hc = H.t + (L.TF_SECONDS[H.tf] if H.tf != "W1" else 0)
    if H.tf == "W1":
        hc = np.r_[H.t[1:], H.t[-1] + 7 * 86400]
    j = np.searchsorted(hc, B.t + L.TF_SECONDS[B.tf], side="right") - 1
    mid = (pd.Series(H.h).rolling(55).max() + pd.Series(H.l).rolling(55).min()).to_numpy() / 2
    sgn = np.where(j >= 0, np.sign(H.c[np.maximum(j, 0)] - mid[np.maximum(j, 0)]), 0)
    return np.nan_to_num(sgn) == d


def pyramid_and_be(B, sym, T, system, max_units):
    """Taken one-position trades re-run with Turtle units (add every +0.5 N from the last add, every stop to 2 N from the latest add) or,
    with max_units = 0, the breakeven rule (stop to entry after MFE >= 1 R, from the next bar). R in units of the first unit's risk."""
    entry_n, ex = C.SYSTEMS[system]
    N = L.atr(B.h, B.l, B.c, 20); A22 = L.atr(B.h, B.l, B.c, 22)
    lo, hi = C.chan_levels(B, ex[1]) if ex[0] == "chan" else (None, None)
    o, h, l, c, n = B.o, B.h, B.l, B.c, len(B.c)
    half = C.cost_rt_bp(sym) / 2 / 1e4
    out = []
    for r in T.itertuples():
        e = int(r.e); d = int(r.d); n0 = N[int(r.s)]; R0 = 2 * n0
        units = [o[e]]; stop = o[e] - d * R0; best = o[e]; j = e; px = None; be_on = False
        while j < n:
            if (d > 0 and l[j] <= stop) or (d < 0 and h[j] >= stop):
                px = stop if (d * (o[j] - stop) > 0 or j == e) else o[j]; break
            best = max(best, h[j]) if d > 0 else min(best, l[j])
            if max_units == 0 and not be_on and d * (best - units[0]) >= R0:
                be_on = True
            while max_units != 0 and (max_units < 0 or len(units) < max_units) and d * ((h[j] if d > 0 else l[j]) - units[-1]) >= 0.5 * n0:
                units.append(units[-1] + d * 0.5 * n0); stop = units[-1] - d * R0
            if ex[0] == "chan":
                hit = (c[j] < lo[j]) if d > 0 else (c[j] > hi[j])
            else:
                hit = (c[j] < best - ex[1] * A22[j]) if d > 0 else (c[j] > best + ex[1] * A22[j])
            if hit and j + 1 < n:
                px = o[j + 1]; j += 1; break
            if be_on:
                stop = units[0] if d * (units[0] - stop) > 0 else stop
            j += 1
        if px is None:
            px = c[-1]; j = n - 1
        gross = sum(d * (px - u) for u in units) / R0
        cost = sum((half * 2) * u for u in units) / R0
        sw = C.swap_bp(sym, np.full(len(units), B.t[e]), np.full(len(units), B.t[min(j, n - 1)]), np.full(len(units), d)).sum() * units[0] / 1e4 / R0
        out.append(dict(t=B.t[e], t_exit=B.t[min(j, n - 1)], s=int(r.s), d=d, ep=units[0], R=gross - cost - sw, units=len(units)))
    return pd.DataFrame(out)


def x3a(rows):
    tests = []
    for tf in C.TFS:
        G = C.load(f"x1_trades_XAUUSD_{tf}.pkl"); S = C.load(f"x1_trades_XAGUSD_{tf}.pkl")
        Bg, Bs = C.bars("XAUUSD", tf), C.bars("XAGUSD", tf)
        feats = [c for c in G.columns if G[c].dtype == np.float32]
        dev = (G.t >= C.ts(C.GOLD_DEV[0])) & (G.t < C.ts(C.GOLD_DEV[1]))
        for system in C.SYSTEMS:
            for side in (1, -1):
                g = G[dev & (G.system == system) & (G.d == side)]
                best = None
                for f in feats:
                    x = g[f].to_numpy(float); ok = np.isfinite(x)
                    if ok.sum() < 3000:
                        continue
                    edges = np.unique(np.quantile(x[ok], np.linspace(0, 1, 11)))
                    if len(edges) < 6:
                        continue
                    b = np.clip(np.searchsorted(edges, x[ok], side="right") - 1, 0, len(edges) - 2)
                    sr = pd.Series(g.gR.to_numpy()[ok]).groupby(b).agg(["mean", "size"])
                    sr = sr[sr["size"] >= 300]
                    if len(sr) and (best is None or sr["mean"].min() < best[0]):
                        k = int(sr["mean"].idxmin()); best = (float(sr["mean"].min()), f, edges[k], edges[k + 1])
                if best is None:
                    continue
                _, f, lo_e, hi_e = best
                for mkt, T_, B_ in (("gold", G, Bg), ("silver", S, Bs)):
                    sel = T_[(T_.system == system) & (T_.d == side) & (T_[f] >= lo_e) & (T_[f] <= hi_e)]
                    if not len(sel):
                        continue
                    fade = C.trend_trades(B_, "XAUUSD" if mkt == "gold" else "XAGUSD", system, -side, s=sel.s.to_numpy(), d=np.full(len(sel), -side))
                    pers = {"DEV": C.GOLD_DEV, "CHECK": C.GOLD_CHECK} if mkt == "gold" else {"ALL": ("2009-01-01", "2026-10-01")}
                    for p, (a, b) in pers.items():
                        x = fade[(fade.t >= C.ts(a)) & (fade.t < C.ts(b))]
                        tests.append(dict(part="X3a", tf=tf, system=system, side=side, feature=f, lo=lo_e, hi=hi_e, dev_gR_signal=best[0], market=mkt,
                                          period=p, n=len(x), R=x.R.mean() if len(x) else np.nan, gR=x.gR.mean() if len(x) else np.nan,
                                          p=boot_p(x.R, x.t) if len(x) else np.nan))
        log(f"X3a {tf}")
    return tests


def x3b():
    E = pd.read_csv(C.ROOT / "data" / "candlelab" / "effects.csv")
    E = E[E.consistent_all & E.outcome.isin(["ret1", "ret3", "ret5", "ret20"]) & E.tf.isin(["M5", "M15", "H1"])]
    E = E.assign(pri=E.outcome.map({"ret1": 0, "ret3": 1, "ret5": 2, "ret20": 3})).sort_values("pri").drop_duplicates(["tf", "feature"])
    import importlib.util
    spec = importlib.util.spec_from_file_location("AN", C.ROOT / "research" / "candlelab" / "analyze.py"); AN = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(AN)
    tests = []
    for tf, grp in E.groupby("tf"):
        frames = {}
        for sym in C.METALS:
            B = C.bars(sym, tf)
            F = X1.features(B, sym)
            frames[sym] = (B, F)
        Fg = frames["XAUUSD"][1]; tg = frames["XAUUSD"][0].t
        devm = (tg >= C.ts(C.GOLD_DEV[0])) & (tg < C.ts(C.GOLD_DEV[1]))
        for r in grp.itertuples():
            f = r.feature
            if f not in Fg.columns:
                continue
            xg = Fg[f].to_numpy(float)
            thr = tuple(np.quantile(xg[devm & np.isfinite(xg)], [0.1, 0.9]))
            sg = np.sign(r.DEV_eff)
            for sym in C.METALS:
                B, F = frames[sym]
                x = F[f].to_numpy(float)
                top, bot = AN.buckets(f, x, thr)
                flag = f.startswith(AN.FLAG_PREFIX)
                s = np.r_[np.flatnonzero(top)] if flag else np.r_[np.flatnonzero(top), np.flatnonzero(bot)]
                d = np.r_[np.full(int(top.sum()), sg)] if flag else np.r_[np.full(int(top.sum()), sg), np.full(int(bot.sum()), -sg)]
                T = C.simulate(B, s, d.astype(int), B.atr[s], ("chand", 1.0, B.atr), sym)
                pers = {"DEV": C.GOLD_DEV, "CHECK": C.GOLD_CHECK} if sym == "XAUUSD" else {"ALL": ("2009-01-01", "2026-10-01")}
                for p, (a, b) in pers.items():
                    xx = T[(T.t >= C.ts(a)) & (T.t < C.ts(b))]
                    tests.append(dict(part="X3b", tf=tf, feature=f, effect_outcome=r.outcome, dev_eff=r.DEV_eff, market=sym, period=p, n=len(xx),
                                      R=xx.R.mean(), gR=xx.gR.mean(), p=boot_p(xx.R, xx.t), bars=xx.bars.mean()))
            log(f"X3b {tf} {f}")
        del frames
    return tests


def x4(rows):
    """X4a candle filter and X4b multi-TF agreement on every-signal trades; X4c / X4d on the one-position trades."""
    ref = {}
    for tf in ("H1", "H4", "D1"):
        B, T, W = market_frame("XAUUSD", tf)
        dev = (T.t >= C.ts(C.GOLD_DEV[0])) & (T.t < C.ts(C.GOLD_DEV[1]))
        ref[tf] = {f: np.sort(T.loc[dev, f + "_q"].dropna().to_numpy()) for f in ("lowick_frac", "clv_mean5", "atr_pct_1y", "w1_form_pos")}

    def score(T, tf):
        z = []
        for f, sg in (("lowick_frac", 1), ("clv_mean5", 1), ("atr_pct_1y", -1), ("w1_form_pos", 1)):
            r = np.searchsorted(ref[tf][f], T[f + "_q"].to_numpy(float)) / max(len(ref[tf][f]), 1)
            z.append(r if sg > 0 else 1 - r)
        return np.nanmean(np.c_[z].T if False else np.vstack(z).T, axis=1)

    med = {}
    for tf in ("H1", "H4", "D1"):
        B, T, W = market_frame("XAUUSD", tf)
        dev = (T.t >= C.ts(C.GOLD_DEV[0])) & (T.t < C.ts(C.GOLD_DEV[1]))
        med[tf] = float(np.nanmedian(score(T[dev], tf)))
    tests, fin = [], []
    for sym in ("XAUUSD", "XAGUSD") + OTHERS:
        for tf in (("H1", "H4", "D1") if sym in C.METALS else ("H1", "D1")):
            try:
                B, T, W = market_frame(sym, tf)
            except FileNotFoundError:
                continue
            T["score"] = score(T, tf)
            H = C.bars(sym, "D1") if tf in ("H1", "H4") else W
            agree = mtf_agree(B, H, 1)[T.s.to_numpy()] & (T.d.to_numpy() > 0) | mtf_agree(B, H, -1)[T.s.to_numpy()] & (T.d.to_numpy() < 0)
            T["agree"] = agree
            for system in C.SYSTEMS:
                g = T[T.system == system]
                for name, keep in (("X4a candle filter", g.score >= med[tf]), ("X4b HTF agrees", g.agree)):
                    k = keep.to_numpy()
                    tests.append(dict(part=name.split()[0], sym=sym, tf=tf, system=system, n_all=len(g), R_all=g.R.mean(), n_keep=int(k.sum()),
                                      R_keep=g.R[k].mean() if k.any() else np.nan, R_drop=g.R[~k].mean() if (~k).any() else np.nan,
                                      diff=(g.R[k].mean() - g.R.mean()) if k.any() else np.nan, wk=list(week_of(g.t.to_numpy())),
                                      Rk=list(g.R.to_numpy()), kk=list(k)))
                if sym in C.METALS or tf == "D1":
                    for side_set in ("long", "both"):
                        gg = g[g.d > 0] if side_set == "long" else g
                        tk = gg[(gg.taken if side_set == "long" else gg.taken_ls).to_numpy()]
                        base = C.equity(tk, 0.01)
                        fin.append(dict(part="X4c/d", sym=sym, tf=tf, system=system, sides=side_set, variant="single unit", R=tk.R.mean(), units=1.0, **base))
                        for mu, lab in ((4, "pyramid 4 units"), (-1, "pyramid unlimited"), (0, "breakeven at +1R")):
                            P = pyramid_and_be(B, sym, tk, system, mu)
                            r = C.equity(P, 0.01) if len(P) else dict(n=0)
                            fin.append(dict(part="X4c/d", sym=sym, tf=tf, system=system, sides=side_set, variant=lab, R=P.R.mean() if len(P) else np.nan,
                                            units=P.units.mean() if len(P) else np.nan, **r))
            log(f"X4 {sym} {tf}")
    return tests, fin


def x4_verdicts(tests):
    out = []
    D = pd.DataFrame(tests)
    for (part, tf, system), g in D.groupby(["part", "tf", "system"]):
        silver = g[g.sym == "XAGUSD"]
        oth = g[g.sym.isin(OTHERS)]
        up_share = float((oth["diff"] > 0).mean()) if len(oth) else np.nan
        # pooled difference over the clean markets (silver + others): bootstrap over market-weeks of (kept - all) per trade
        rows = []
        for r in pd.concat([silver, oth]).itertuples():
            w = np.asarray(r.wk); R = np.asarray(r.Rk); k = np.asarray(r.kk, bool)
            rows.append(pd.DataFrame(dict(key=[f"{r.sym}|{x}" for x in w], R=R, k=k)))
        if rows:
            P = pd.concat(rows)
            gk = P[P.k].groupby("key").R.agg(["sum", "size"]); ga = P.groupby("key").R.agg(["sum", "size"])
            keys = ga.index.to_numpy(); ks = gk.reindex(keys).fillna(0)
            obs = ks["sum"].sum() / max(ks["size"].sum(), 1) - ga["sum"].sum() / ga["size"].sum()
            rng = np.random.default_rng(11); bs = []
            for _ in range(1000):
                idx = rng.integers(0, len(keys), len(keys))
                a_ = ks.to_numpy()[idx]; b_ = ga.to_numpy()[idx]
                bs.append(a_[:, 0].sum() / max(a_[:, 1].sum(), 1) - b_[:, 0].sum() / b_[:, 1].sum())
            p = float((np.asarray(bs) - obs >= obs).mean())
        else:
            obs, p = np.nan, np.nan
        sd = float(silver["diff"].iloc[0]) if len(silver) else np.nan
        out.append(dict(part=part, tf=tf, system=system, gold_diff=float(g[g.sym == "XAUUSD"]["diff"].iloc[0]) if (g.sym == "XAUUSD").any() else np.nan,
                        silver_diff=sd, others_up_share=up_share, pooled_diff=obs, p=p,
                        PASS=bool(sd > 0 and up_share >= 0.6 and p < 0.05)))
    return pd.DataFrame(out)


def main():
    rows = []
    if "x4only" in sys.argv:
        return main_x4(rows)
    a = x3a(rows)
    pd.DataFrame(a).to_csv(C.OUT / "x3a_loser_fade.csv", index=False)
    b = x3b()
    pd.DataFrame(b).to_csv(C.OUT / "x3b_candle_reversal.csv", index=False)
    for name, tests in (("x3a_loser_fade", a), ("x3b_candle_reversal", b)):
        D = pd.DataFrame(tests)
        ck = D[(D.market.isin(["gold", "XAUUSD"])) & (D.period == "CHECK")].copy()
        ck["p_holm"] = holm(ck.p.to_numpy())
        sv = D[D.market.isin(["silver", "XAGUSD"])]
        key = ["tf", "system", "side"] if name == "x3a_loser_fade" else ["tf", "feature"]
        V = ck.merge(sv[key + ["R", "n"]].rename(columns={"R": "silver_R", "n": "silver_n"}), on=key, how="left")
        V["PASS"] = (V.R > 0) & (V.p_holm < 0.05) & (V.silver_R > 0)
        V.to_csv(C.OUT / f"{name}_verdict.csv", index=False)
        log(f"{name}: {int(V.PASS.sum())} pass of {len(V)}")
    main_x4(rows)


def main_x4(rows):
    t4, f4 = x4(rows)
    V4 = x4_verdicts(t4)
    V4.to_csv(C.OUT / "x4ab_verdict.csv", index=False)
    pd.DataFrame(t4).drop(columns=["wk", "Rk", "kk"]).to_csv(C.OUT / "x4ab_tests.csv", index=False)
    pd.DataFrame(f4).to_csv(C.OUT / "x4cd_pyramid_breakeven.csv", index=False)
    log(f"X4ab: {int(V4.PASS.sum())} pass of {len(V4)}; X3/X4 done")


if __name__ == "__main__":
    main()
