"""EXPLORATION: fast level scan ("sieve-lite"; the full C11 sieve with 999 placebo paths stays the rigorous follow-up). Every one of the 158
sieve features on gold H1: extreme deciles (continuous, thresholds from gold DEV 2004-15), event signs and time flags; forward target
open(t+1) -> open(t+1+h) / ATR for h = 4 and 24 bars; DEV cluster-t (weekly) of the conditional mean minus the DEV mean. Candidates with
|t| >= 3 become trading rules (direction = DEV sign, hold h, stop 1.5 / 2 ATR, C4 cost and swap, one position at a time), read on gold CHECK
2016-26 and on silver 2016-26 (silver thresholds from silver 2010-15), each with the same-direction random-timing control.
Usage: python research/hyp/sieve_lite.py -> data/hyp/sieve_lite.csv"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import batch1 as B1  # noqa: E402
import batch2 as B2  # noqa: E402

ROOT = B1.ROOT
sys.path[:0] = [str(ROOT / "research" / "sieve")]
import features as FT  # noqa: E402
import run_scan as RS  # noqa: E402

HS = {4: 1.5, 24: 2.0}


def feats_gold():
    B, cuts, cell, ext, _, _ = RS.dataset("A")
    X, kinds = FT.build(B, cuts, cell, ext)
    return B, cuts, X, kinds


def feats_silver():
    import xag as XG
    import engine as E
    a, _ = XG.load_bars()
    H, _, cuts, cell = E.build(a["t"], a["o"], a["h"], a["l"], a["c"], a["sp"], a["c"], a["h"], a["l"])
    B = RS.mkbars(a["t"], a["o"], a["h"], a["l"], a["c"], a["v"], 3600)
    ext = {k: v for k, v in RS.externals().items() if k != "aligned"}
    X, kinds = FT.build(B, cuts, cell, ext)
    return B, cuts, X, kinds


def target(B, h):
    a14 = pd.Series(FT._atr(pd.Series(B.h), pd.Series(B.l), pd.Series(B.c), 14)).to_numpy()
    n = len(B.t); y = np.full(n, np.nan)
    y[: n - 1 - h] = (B.o[1 + h:] - B.o[1: n - h]) / a14[: n - 1 - h]
    return np.clip(y, -5, 5)


def conds(x, kind, thr_mask):
    x = np.asarray(x, float)
    if kind in ("cont", "ext"):
        v = x[thr_mask & np.isfinite(x)]
        if len(v) < 1000:
            return {}
        lo, hi = np.quantile(v, [0.1, 0.9])
        if lo == hi:
            return {}
        return {"D1": x <= lo, "D10": x >= hi}
    if kind == "event":
        return {"EV-": x == -1, "EV+": x == 1}
    return {"FLAG": x == 1}


def cluster_t(y, cond, mask, wk):
    m = mask & cond & np.isfinite(y)
    base = np.nanmean(y[mask & np.isfinite(y)])
    if m.sum() < 100:
        return np.nan, np.nan, int(m.sum())
    dev = y[m] - base
    s = pd.Series(dev).groupby(wk[m]).sum().to_numpy()
    return float(dev.mean()), float(dev.sum() / np.sqrt((s ** 2).sum())), int(m.sum())


def trade(Bx, sym, cuts, cond, d, h, k, a, b):
    ta, tb = int(pd.Timestamp(a).timestamp()), int(pd.Timestamp(b).timestamp())
    idx = np.flatnonzero(cond[:-1]) + 1
    idx = idx[(Bx.t[idx] >= ta) & (Bx.t[idx] < tb) & (idx < len(Bx.t) - h - 1)]
    B = B1.mkbars(Bx.t, Bx.o, Bx.h, Bx.l, Bx.c, getattr(Bx, "spread_bp", np.full(len(Bx.t), np.nan)), 3600)
    if len(idx) < 10:
        return None
    tr = B1.simulate_events(B, sym, e=idx, d=np.full(len(idx), d), stop=k * B.atr[idx], tgt=np.full(len(idx), np.nan), last=idx + h - 1)
    S, N, sub = B1.weekly(tr, cuts, a, b)
    m, p = B1.boot_p(S, N)
    ctl = B2.control({"sym": sym}, B, h, k, a, b, {float(d): 1.0})
    return dict(n=int(len(sub)), R=float(sub.R.mean()), p=p, ctl=ctl, excess=float(sub.R.mean() - ctl))


def main():
    t0 = time.time()
    Bg, cg, Xg, kinds = feats_gold()
    G1 = B1.SG.load_xau("H1")[0]
    assert np.array_equal(G1.t, Bg.t), "gold bars differ"
    Bg.spread_bp = G1.spread_bp
    Bs, cs, Xs, _ = feats_silver()
    import xag as XG
    Bs.spread_bp = XG.load_xag("H1")[0].spread_bp
    print(f"features: gold {Xg.shape}, silver {Xs.shape} ({time.time() - t0:.0f}s)", flush=True)
    kind_of = {f: k for k, fs in kinds.items() for f in fs}
    tg = pd.to_datetime(Bg.t, unit="s"); ts = pd.to_datetime(Bs.t, unit="s")
    dev_g = (tg >= "2004-01-01") & (tg < "2016-01-01"); dev_s = (ts >= "2010-01-01") & (ts < "2016-01-01")
    wk = np.searchsorted(cg, Bg.t, side="left") - 1
    Y = {h: target(Bg, h) for h in HS}
    rows = []
    for f in Xg.columns:
        cg_ = conds(Xg[f].to_numpy(), kind_of[f], np.asarray(dev_g))
        for cname, cond in cg_.items():
            for h, k in HS.items():
                mean, t, n = cluster_t(Y[h], cond, np.asarray(dev_g), wk)
                if np.isfinite(t) and abs(t) >= 3:
                    rows.append(dict(feature=f, kind=kind_of[f], cond=cname, h=h, k=k, dev_n=n, dev_mean=mean, dev_t=t))
    C = pd.DataFrame(rows)
    print(f"DEV candidates with |t| >= 3: {len(C)} ({time.time() - t0:.0f}s)", flush=True)
    out = []
    for _, r in C.iterrows():
        d = 1.0 if r.dev_mean > 0 else -1.0
        cg_ = conds(Xg[r.feature].to_numpy(), r.kind, np.asarray(dev_g))[r.cond]
        g = trade(Bg, "XAUUSD", cg, cg_, d, int(r.h), r.k, "2016-01-01", "2026-10-01")
        if r.feature in Xs.columns:
            cs_ = conds(Xs[r.feature].to_numpy(), r.kind, np.asarray(dev_s)).get(r.cond)
            s = trade(Bs, "XAGUSD", cs, cs_, d, int(r.h), r.k, "2016-01-01", "2026-09-25") if cs_ is not None else None
        else:
            s = None
        out.append({**r.to_dict(), "dir": d, **({f"check_{k}": v for k, v in g.items()} if g else {}), **({f"silver_{k}": v for k, v in s.items()} if s else {})})
    T = pd.DataFrame(out)
    for c in ("check_R", "check_excess", "silver_R", "silver_excess"):
        if c not in T:
            T[c] = np.nan
    T["consistent"] = (T.check_R > 0) & (T.check_excess > 0) & (T.silver_R > 0) & (T.silver_excess > 0)
    T.to_csv(B1.OUT / "sieve_lite.csv", index=False)
    pd.set_option("display.width", 260)
    cols = ["feature", "cond", "h", "dir", "dev_n", "dev_t", "check_n", "check_R", "check_p", "check_excess", "silver_n", "silver_R", "silver_p", "silver_excess"]
    print(T.sort_values(["consistent", "check_R"], ascending=False)[[c for c in cols if c in T]].head(30).round(3).to_string(index=False))
    print(f"consistent: {int(T.consistent.sum())} of {len(T)} candidates ({time.time() - t0:.0f}s)")


if __name__ == "__main__":
    main()
