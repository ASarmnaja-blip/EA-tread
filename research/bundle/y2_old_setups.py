"""Y2 of docs/BUNDLE2_2026-10-01_PREREG.md: the 7 old setups without profit caps. Signals exactly as research/pilot/core.py s1..s6 (their
NO TRADE rules and structural initial stops kept, targets and time stops discarded); exits CHAN10 / CHAN20 / CH3; entry TFs M15, M30, H1,
H4; gold DEV / CHECK, silver, 16 MT5 markets; control = same directions on random bars with the same ATR-multiple stop (20 draws).
News acceptance / rejection on gold M5 from research/pilot/results/news_assessments.csv (descriptive).
Usage: python research/bundle/y2_old_setups.py"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import common as C  # noqa: E402

sys.path.insert(0, str(C.ROOT / "research" / "pilot"))
import core  # noqa: E402
import data as PD  # noqa: E402

L = C.L
OUT = C.ROOT / "data" / "bundle2"; OUT.mkdir(parents=True, exist_ok=True)
T0 = time.time()
log = lambda *a: print(f"[{time.time() - T0:6.0f}s]", *a, flush=True)
SETUPS = {"breakout": core.s1_breakout, "pullback": core.s2_pullback, "sweep": core.s3_sweep, "failed": core.s4_failed,
          "vwap": core.s5_vwap, "expansion": core.s6_expansion}
EXITS = {"CHAN10": ("chan", 10), "CHAN20": ("chan", 20), "CH3": ("chand", 3.0)}
TFS = ("M15", "M30", "H1", "H4")
CUTS = L.cut_grid(C.ts("2026-10-02"))


def boot_p(R, t, K=2000, seed=7):
    R = np.asarray(R, float); w = np.searchsorted(CUTS, np.asarray(t), side="right") - 1
    if len(R) < 10:
        return np.nan
    uw, inv = np.unique(w, return_inverse=True)
    S = np.bincount(inv, R); N = np.bincount(inv); mu = S.sum() / N.sum()
    rng = np.random.default_rng(seed); idx = rng.integers(0, len(uw), (K, len(uw)))
    bm = (S - mu * N)[idx].sum(1) / N[idx].sum(1)
    return float((bm >= mu).mean())


def holm(p):
    p = np.asarray(p, float); m = np.isfinite(p).sum(); out = np.full(len(p), np.nan)
    run = 0.0
    for r, i in enumerate(np.argsort(np.where(np.isfinite(p), p, np.inf))):
        if np.isfinite(p[i]):
            run = max(run, min(1.0, (m - r) * p[i])); out[i] = run
    return out


def signals(B, sym):
    pb = PD.Bars(B.t, B.o, B.h, B.l, B.c, np.where(np.isfinite(B.v), B.v, 1.0), L.TF_SECONDS[B.tf], sym)
    ctx = core.Ctx(pb, np.zeros(len(B.t), np.int64))
    out = {}
    for nm, fn in SETUPS.items():
        sig = fn(ctx)
        if not sig:
            out[nm] = (np.zeros(0, np.int64), np.zeros(0, int), np.zeros(0))
            continue
        i = np.array([x[0] for x in sig], np.int64); d = np.array([x[1] for x in sig], int)
        sd = np.abs(B.c[i] - np.array([x[2] for x in sig], float))
        out[nm] = (i, d, sd)
    return out, ctx.atr


def run_market(sym, tf, rows, periods):
    B = C.bars(sym, tf)
    sig, atr = signals(B, sym)
    n = len(B.c); rng = np.random.default_rng(11)
    for nm, (i, d, sd) in sig.items():
        if len(i) < 20:
            continue
        k_atr = sd / np.where(atr[i] > 0, atr[i], np.nan)
        for ex, spec in EXITS.items():
            T = C.simulate(B, i, d, sd, spec, sym)
            ctl = []
            for draw in range(20):
                r = rng.integers(200, n - 2, len(i))
                sd_r = k_atr * atr[r]
                ok = np.isfinite(sd_r) & (sd_r > 0)
                ctl.append(C.simulate(B, r[ok], rng.permutation(d)[ok], sd_r[ok], spec, sym))
            Ctl = pd.concat(ctl)
            for p, (a, b) in periods.items():
                x = T[(T.t >= C.ts(a)) & (T.t < C.ts(b))]; y = Ctl[(Ctl.t >= C.ts(a)) & (Ctl.t < C.ts(b))]
                if len(x) < 10:
                    continue
                cm = y.R.mean() if len(y) else np.nan
                rows.append(dict(setup=nm, exit=ex, tf=tf, mkt=sym, period=p, n=len(x), R=x.R.mean(), gR=x.gR.mean(), ctl_R=cm,
                                 excess=x.R.mean() - cm, p_net=boot_p(x.R, x.t), p_excess=boot_p(x.R - cm, x.t), bars=x.bars.mean(),
                                 big3=(x.R >= 3).mean()))
    return rows


def news():
    a = pd.read_csv(C.ROOT / "research" / "pilot" / "results" / "news_assessments.csv").sort_values("epoch")
    B = C.bars("XAUUSD", "M5")
    rows = []
    a = a[a.surprise_z.abs().ge(0.5) & a.hypothesis_dir.isin([1, -1]) & a.xau_1m.notna() & a.dxy_1m.notna()]
    ent, dirs, sd, kind, ep = [], [], [], [], []
    for r in a.itertuples():
        e = int(np.searchsorted(B.t, int(r.epoch) + 60, side="left"))
        if e < 20 or e >= len(B.t) - 2:
            continue
        A = B.atr[e - 1]
        if not np.isfinite(A) or abs(r.xau_1m) < 0.5 * A / np.sqrt(5) or np.sign(r.dxy_1m) != -np.sign(r.xau_1m):
            continue
        d = 1 if r.xau_1m > 0 else -1
        ent.append(e); dirs.append(d); sd.append(max(1.35 * A, 0.75 * abs(r.xau_1m), 1.0)); kind.append("accept" if d == int(r.hypothesis_dir) else "reject")
        ep.append(int(r.epoch))
    ent, dirs, sd, kind, ep = map(np.asarray, (ent, dirs, sd, kind, ep))
    if not len(ent):
        return pd.DataFrame()
    cut = np.sort(ep)[int(0.7 * len(ep))]
    for ex, spec in EXITS.items():
        T = C.simulate(B, ent - 1, dirs, sd, spec, "XAUUSD")
        T["kind"] = kind[: len(T)]; T["ep"] = ep[: len(T)]
        for k in ("accept", "reject"):
            for part, m in (("dev", T.ep < cut), ("holdout", T.ep >= cut)):
                x = T[(T.kind == k) & m]
                rows.append(dict(setup="news_" + k, exit=ex, tf="M5", mkt="XAUUSD", period=part, n=len(x), R=x.R.mean() if len(x) else np.nan,
                                 gR=x.gR.mean() if len(x) else np.nan, win=(x.R > 0).mean() if len(x) else np.nan, bars=x.bars.mean() if len(x) else np.nan))
    return pd.DataFrame(rows)


def main():
    if sys.argv[1:2] == ["combine"]:
        return combine()
    tfs = tuple(sys.argv[1:]) or TFS
    fname = "y2_rows.csv" if tfs == TFS else f"y2_rows_{'_'.join(tfs)}.csv"
    rows = []
    for tf in tfs:
        run_market("XAUUSD", tf, rows, {"DEV": C.GOLD_DEV, "CHECK": C.GOLD_CHECK})
        run_market("XAGUSD", tf, rows, {"ALL": ("2009-01-01", "2026-10-01")})
        log(f"metals {tf}")
        for m in C.ORIG8 + C.NEW8:
            try:
                run_market(m, tf, rows, {"ALL": ("2000-01-01", "2026-10-02")})
            except (FileNotFoundError, KeyError, ValueError) as ex:
                log(f"skip {m} {tf}: {ex}")
        log(f"markets {tf}")
        pd.DataFrame(rows).to_csv(OUT / fname, index=False)
    if tfs == TFS:
        combine()


def combine():
    D = pd.concat([pd.read_csv(f) for f in sorted(OUT.glob("y2_rows*.csv"))]).drop_duplicates(["setup", "exit", "tf", "mkt", "period"])
    g = D[(D.mkt == "XAUUSD") & (D.period == "CHECK")].copy()
    g["p_holm"] = holm(np.maximum(g.p_net.to_numpy(), g.p_excess.to_numpy()))
    sv = D[D.mkt == "XAGUSD"][["setup", "exit", "tf", "R", "n"]].rename(columns={"R": "silver_R", "n": "silver_n"})
    oth = D[D.mkt.isin([m for m in C.ORIG8 + C.NEW8 if m != "USDINR"])].groupby(["setup", "exit", "tf"]).agg(
        markets=("R", "size"), share_pos=("R", lambda x: float((x > 0).mean())), median_R=("R", "median")).reset_index()
    V = g.merge(sv, on=["setup", "exit", "tf"], how="left").merge(oth, on=["setup", "exit", "tf"], how="left")
    V["PASS"] = (V.R > 0) & (V.excess > 0) & (V.p_holm < 0.05) & (V.silver_R > 0) & (V.share_pos >= 0.6)
    V.to_csv(OUT / "y2_verdict.csv", index=False)
    N = news(); N.to_csv(OUT / "y2_news.csv", index=False)
    log(f"Y2 done: {int(V.PASS.sum())} pass of {len(V)}")


if __name__ == "__main__":
    main()
