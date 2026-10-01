"""EXPLORATION (operator 2026-10-01: "ถ้าติดลบเพราะต้นทุนก็ขยายไม้ให้ใหญ่ขึ้นไปเรื่อยๆ ถ้ายิ่งขยายยิ่งแพ้ตลาดก็สลับด้าน ... ทำอะไรแปลกๆไปก่อน").
Scale-and-flip over every Family 2 and zoo signal on gold H1 / H4 / D1: stop k x ATR with k in {1, 2, 4, 8}, no target, hold = base x k bars
(H1 24, H4 6, D1 5). Rule applied on DEV (2004-15) only, per signal x TF:
  1. if FOLLOW at k = 1 is gross > 0 but net <= 0 (a cost problem): take the smallest k whose DEV net > 0 (if none: drop);
  2. if FOLLOW gross gets more negative as k grows (worse at k = 8 than at k = 1, both < 0): flip to FADE and take the k with the best DEV net;
  3. if FOLLOW is net > 0 at k = 1: keep k = 1.
The chosen (direction, k) is then read on CHECK (gold 2016-26) and SILVER (2010-26, same signal on silver bars). Exploratory: every result is
reported; survivors still need a forward record. Usage: python research/hyp/explore_scale.py -> data/hyp/explore_scale.csv"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import batch1 as B1  # noqa: E402

ROOT = B1.ROOT
sys.path[:0] = [str(ROOT / "research" / "sieve")]
import features as FT  # noqa: E402
import f2_signals as F2  # noqa: E402

KS = (1, 2, 4, 8)
BASE_HOLD = {"H1": 24, "H4": 6, "D1": 5}
PER = {"DEV": ("2004-01-01", "2016-01-01"), "CHECK": ("2016-01-01", "2026-10-01"), "SILVER": ("2010-01-01", "2026-09-25")}


def bars(sym):
    if sym == "XAUUSD":
        out = {}
        for tf in ("H1", "H4", "D1"):
            B, cuts, _ = B1.SG.load_xau(tf)
            out[tf] = B1.mkbars(B.t, B.o, B.h, B.l, B.c, B.spread_bp, B.step, B.atr); out[tf].v = B.v
        return out, cuts
    import xag as X
    out = {}
    for tf in ("H1", "H4", "D1"):
        B, cuts, _ = X.load_xag(tf)
        out[tf] = B1.mkbars(B.t, B.o, B.h, B.l, B.c, B.spread_bp, B.step, B.atr); out[tf].v = B.v
    return out, cuts


def signals(B, cuts):
    s = {f"F2:{k}": v for k, v in F2.f2_signals(B, cuts).items()}
    s.update({f"ZOO:{k}": v for k, v in FT.zoo_signals(B).items()})
    return s


def events(sig, B):
    sl, ss = sig
    il, is_ = np.flatnonzero(sl[:-1]), np.flatnonzero(ss[:-1])
    e = np.r_[il, is_] + 1; d = np.r_[np.ones(len(il)), -np.ones(len(is_))]
    o = np.argsort(e, kind="stable"); e, d = e[o], d[o]
    ok = np.isfinite(B.atr[e]) & (B.atr[e] > 0)
    return e[ok], d[ok]


def stats(M, B, e, d, k, hold, cuts, period):
    a, b = PER[period]
    ta, tb = int(pd.Timestamp(a).timestamp()), int(pd.Timestamp(b).timestamp())
    m = (B.t[e] >= ta) & (B.t[e] < tb) & (e + hold < len(B.t))
    if m.sum() < 5:
        return dict(n=0, net=np.nan, gross=np.nan, p=np.nan)
    tr = B1.simulate_events(B, M, e=e[m], d=d[m], stop=k * B.atr[e[m]], tgt=np.full(int(m.sum()), np.nan), last=e[m] + hold - 1)
    S, N, sub = B1.weekly(tr, cuts, a, b)
    mean, p = B1.boot_p(S, N)
    return dict(n=int(len(sub)), net=float(sub.R.mean()), gross=float(sub.gR.mean()), p=p)


def main():
    t0 = time.time()
    G, gcuts = bars("XAUUSD"); S, scuts = bars("XAGUSD")
    print(f"bars loaded ({time.time() - t0:.0f}s)", flush=True)
    rows = []
    for tf in ("H1", "H4", "D1"):
        Bg, Bs = G[tf], S[tf]
        sg, ss = signals(Bg, gcuts), signals(Bs, scuts)
        for name in sg:
            if name not in ss:
                continue
            e, d = events(sg[name], Bg)
            if len(e) < 30:
                continue
            fol = {k: stats("XAUUSD", Bg, e, d, k, BASE_HOLD[tf] * k, gcuts, "DEV") for k in KS}
            g1, g8 = fol[1]["gross"], fol[8]["gross"]
            choice = None
            if fol[1]["net"] > 0:
                choice = (1.0, 1, "follow k1 net>0")
            elif g1 > 0:
                ok = [k for k in KS if fol[k]["net"] > 0]
                choice = (1.0, ok[0], "cost: scaled up") if ok else None
            elif g1 < 0 and g8 < g1:
                fad = {k: stats("XAUUSD", Bg, e, -d, k, BASE_HOLD[tf] * k, gcuts, "DEV") for k in KS}
                kb = max(KS, key=lambda k: fad[k]["net"] if np.isfinite(fad[k]["net"]) else -9)
                choice = (-1.0, kb, "worse when scaled: flipped") if fad[kb]["net"] > 0 else None
            row = dict(tf=tf, signal=name, dev_follow_k1_net=fol[1]["net"], dev_follow_k1_gross=g1, dev_follow_k8_gross=g8)
            if choice is None:
                row.update(rule="drop"); rows.append(row); continue
            sgn, k, why = choice
            dv = stats("XAUUSD", Bg, e, sgn * d, k, BASE_HOLD[tf] * k, gcuts, "DEV")
            ck = stats("XAUUSD", Bg, e, sgn * d, k, BASE_HOLD[tf] * k, gcuts, "CHECK")
            es, ds = events(ss[name], Bs)
            sv = stats("XAGUSD", Bs, es, sgn * ds, k, BASE_HOLD[tf] * k, scuts, "SILVER")
            row.update(rule=why, direction="follow" if sgn > 0 else "fade", k=k, hold=BASE_HOLD[tf] * k,
                       dev_n=dv["n"], dev_net=dv["net"], check_n=ck["n"], check_net=ck["net"], check_gross=ck["gross"], check_p=ck["p"],
                       silver_n=sv["n"], silver_net=sv["net"], silver_p=sv["p"])
            rows.append(row)
        print(f"{tf} done: {len(rows)} rows ({time.time() - t0:.0f}s)", flush=True)
    X = pd.DataFrame(rows)
    X.to_csv(B1.OUT / "explore_scale.csv", index=False)
    kept = X[X.rule != "drop"].copy()
    kept["both_pos"] = (kept.check_net > 0) & (kept.silver_net > 0)
    pd.set_option("display.width", 250)
    print(f"\n{len(X)} signal x TF combos; DEV rule kept {len(kept)} ({kept.rule.value_counts().to_dict()}); positive on BOTH CHECK and SILVER: {int(kept.both_pos.sum())}")
    cols = ["tf", "signal", "rule", "direction", "k", "hold", "dev_n", "dev_net", "check_n", "check_net", "check_p", "silver_n", "silver_net", "silver_p"]
    print(kept.sort_values("check_net", ascending=False)[cols].head(25).round(3).to_string(index=False))
    print(f"-> {B1.OUT / 'explore_scale.csv'} ({time.time() - t0:.0f}s)")


if __name__ == "__main__":
    main()
