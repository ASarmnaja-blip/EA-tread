"""Hypothesis batch 2 (docs/HYPOTHESIS_BATCH2_PREREG.md): cross-asset drivers of gold. X1 equity-crash give-back, X2 yen surge, X3 oil shock,
X4 dollar trend, X5 yuan weakness, X6 residual reversal vs DXY / USDJPY / US500; drift controls; descriptive lead-lag map.
Research only. Usage: python research/hyp/batch2.py  -> data/hyp/batch2.json (+ stdout log)"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import batch1 as B1  # noqa: E402

ROOT = B1.ROOT
MT5 = ROOT / "data" / "mt5"
SPLIT = "2022-01-01"
END = {"XAUUSD": "2026-10-01", "XAGUSD": "2026-09-25"}


def mt5(sym, tf):
    z = np.load(MT5 / f"{sym}_{tf}.npz")
    return pd.DataFrame({k: z[k] for k in ("t", "o", "h", "l", "c")}).set_index("t")


def check_clock(G):
    x = mt5("XAUUSD", "H1").c
    d = pd.Series(G["H1"].c, index=G["H1"].t)
    mads = {}
    for s in (-2, -1, 0, 1, 2):
        v = d.reindex(x.index.to_numpy() + s * 3600).to_numpy(); r = (x.to_numpy() - v) / v * 1e4; r = r[np.isfinite(r)]
        mads[s] = float(np.median(np.abs(r - np.median(r))))
    best = min(mads, key=mads.get)
    print("MT5 XAUUSD vs Dukascopy H1, MAD by shift:", {k: round(v, 2) for k, v in mads.items()}, "-> best", best)
    if best != 0:
        raise SystemExit("MT5 clock is not UTC: batch 2 stops (pre-registered precondition)")


def daily_returns(sym):
    D = mt5(sym, "D1")
    r = np.log(D.c / D.c.shift(1))
    return pd.DataFrame(dict(r=r, end=D.index.to_numpy() + 86400), index=D.index).dropna()


def causal_q(x, q, n=500, minn=250):
    x = np.asarray(x, float); out = np.full(len(x), np.nan)
    for i in range(len(x)):
        w = x[max(0, i - n):i]
        if len(w) >= minn:
            out[i] = np.quantile(w, q)
    return out


def entries_after(D, times):
    return np.searchsorted(D.t, np.asarray(times, np.int64), side="left")


def daily_rule(M, sig_end, d, hold, k_stop):
    D = M["D1"]
    e = entries_after(D, sig_end)
    ok = e < len(D.t) - 1
    e, d = e[ok], np.asarray(d, float)[ok]
    return D, dict(e=e, d=d, stop=k_stop * D.atr[e], tgt=np.full(len(e), np.nan), last=e + hold - 1)


def sig_X1():
    R = daily_returns("US500"); q = causal_q(R.r.to_numpy(), 0.025)
    m = np.isfinite(q) & (R.r.to_numpy() <= q)
    return R.end.to_numpy()[m], -np.ones(int(m.sum())), int(R.index[np.flatnonzero(np.isfinite(q))[0]])


def sig_X2(sign):
    R = daily_returns("USDJPY"); q = causal_q(R.r.to_numpy(), 0.025)
    m = np.isfinite(q) & (R.r.to_numpy() <= q)
    return R.end.to_numpy()[m], float(sign) * np.ones(int(m.sum())), int(R.index[np.flatnonzero(np.isfinite(q))[0]])


def sig_X3():
    R = daily_returns("USOIL"); a = np.abs(R.r.to_numpy()); q = causal_q(a, 0.975)
    m = np.isfinite(q) & (a >= q)
    return R.end.to_numpy()[m], np.sign(R.r.to_numpy()[m]), int(R.index[np.flatnonzero(np.isfinite(q))[0]])


def sig_X5():
    D = mt5("USDCNH", "D1"); ch = np.log(D.c / D.c.shift(20)).to_numpy()
    q = causal_q(ch, 0.90)
    m = np.isfinite(q) & np.isfinite(ch) & (ch >= q)
    return D.index.to_numpy()[m] + 86400, np.ones(int(m.sum())), int(D.index[np.flatnonzero(np.isfinite(q))[0]])


def rule_X4(M):
    D = M["D1"]; X = mt5("DXY", "D1"); end = X.index.to_numpy() + 86400; lc = np.log(X.c.to_numpy())
    first = int(np.searchsorted(D.t, end[60], side="left"))
    e_list, d_list = [], []
    for e in range(first, len(D.t) - 21, 20):
        j = int(np.searchsorted(end, D.t[e], side="right")) - 1           # last DXY day that ended before this gold open
        if j < 60:
            continue
        s = np.sign(lc[j] - lc[j - 60])
        if s != 0:
            e_list.append(e); d_list.append(-s)
    e = np.array(e_list, int)
    return D, dict(e=e, d=np.array(d_list, float), stop=3 * D.atr[e], tgt=np.full(len(e), np.nan), last=e + 19), int(X.index[60])


def rule_X6(M, sym):
    H = M["H1"]
    y = pd.Series(np.r_[np.nan, np.diff(np.log(H.c))], index=H.t); y[np.r_[True, np.diff(H.t) != 3600]] = np.nan
    cols = {}
    for s in ("DXY", "USDJPY", "US500"):
        x = mt5(s, "H1").c; lr = np.log(x).diff(); lr[np.r_[True, np.diff(x.index.to_numpy()) != 3600]] = np.nan
        cols[s] = lr
    X = pd.DataFrame(cols).reindex(H.t)
    ok = np.isfinite(y.to_numpy()) & np.isfinite(X.to_numpy()).all(1)
    idx = np.flatnonzero(ok)
    yy = y.to_numpy()[idx]; XX = np.c_[np.ones(len(idx)), X.to_numpy()[idx]]
    W = 500
    e = np.full(len(idx), np.nan); sd = np.full(len(idx), np.nan)
    for i in range(W, len(idx)):
        A = XX[i - W:i]; b = yy[i - W:i]
        coef, *_ = np.linalg.lstsq(A, b, rcond=None)
        res = b - A @ coef
        e[i] = yy[i] - XX[i] @ coef; sd[i] = res.std(ddof=4)
    S6 = pd.Series(e).rolling(6, min_periods=6).sum().to_numpy()
    z = S6 / (sd * np.sqrt(6))
    bar = idx                                                              # H bar index of each common hour
    sig_long = np.flatnonzero(z <= -2.5); sig_short = np.flatnonzero(z >= 2.5)
    ent = np.r_[bar[sig_long], bar[sig_short]] + 1
    d = np.r_[np.ones(len(sig_long)), -np.ones(len(sig_short))]
    o = np.argsort(ent, kind="stable"); ent, d = ent[o], d[o]
    keep = ent < len(H.t) - 7
    ent, d = ent[keep], d[keep]
    start = int(H.t[idx[W]]) if len(idx) > W else 0
    return H, dict(e=ent, d=d, stop=1.5 * H.atr[ent], tgt=np.full(len(ent), np.nan), last=ent + 5), start


def control(M, B, hold, k_stop, a, b, dirs_share):
    """Same-direction entries at every bar open of the period (one at a time), mixed by the rule's long/short share."""
    t0, t1 = int(pd.Timestamp(a).timestamp()), int(pd.Timestamp(b).timestamp())
    e = np.flatnonzero((B.t >= t0) & (B.t < t1) & np.isfinite(B.atr)); e = e[e < len(B.t) - hold - 1]
    out = 0.0
    for d, w in dirs_share.items():
        if w == 0:
            continue
        tr = B1.simulate_events(B, M["sym"], e=e, d=np.full(len(e), d), stop=k_stop * B.atr[e], tgt=np.full(len(e), np.nan), last=e + hold - 1)
        out += w * float(tr.R.mean())
    return out


def evaluate(name, M_g, M_s, build, hold, k_stop, start_ts):
    res = {}
    for M, per in ((M_g, {"DEV": (str(pd.Timestamp(start_ts, unit="s").date()), SPLIT), "CHECK": (SPLIT, END["XAUUSD"])}),
                   (M_s, {"SILVER": (str(pd.Timestamp(start_ts, unit="s").date()), END["XAGUSD"])})):
        B, ev = build(M)
        tr = B1.simulate_events(B, M["sym"], **ev)
        for p, (a, b) in per.items():
            S, N, sub = B1.weekly(tr, M["cuts"], a, b)
            m, pv = B1.boot_p(S, N)
            share = {1.0: float((sub.d > 0).mean()) if len(sub) else 0.0, -1.0: float((sub.d < 0).mean()) if len(sub) else 0.0}
            ctl = control(M, B, hold, k_stop, a, b, share) if len(sub) else float("nan")
            res[p] = dict(**B1.summarize(sub), p=pv, control_R=ctl, excess=float(sub.R.mean() - ctl) if len(sub) else float("nan"), period=[a, b])
    return res


def leadlag(G):
    H = G["H1"]
    y = pd.Series(np.r_[np.nan, np.diff(np.log(H.c))], index=H.t); y[np.r_[True, np.diff(H.t) != 3600]] = np.nan
    rows = []
    for s in ("DXY", "USDJPY", "EURUSD", "USDCHF", "AUDUSD", "USDCNH", "US500", "USTEC", "JP225", "USOIL", "BTCUSD", "XAGUSD"):
        x = mt5(s, "H1").c; lr = np.log(x).diff(); lr[np.r_[True, np.diff(x.index.to_numpy()) != 3600]] = np.nan
        row = {"series": s}
        for L in range(0, 5):
            yy = y.reindex(lr.index.to_numpy() + L * 3600).to_numpy(); m = np.isfinite(yy) & np.isfinite(lr.to_numpy())
            row[f"L{L}"] = float(np.corrcoef(lr.to_numpy()[m], yy[m])[0, 1]) if m.sum() > 500 else np.nan
        rows.append(row)
    T = pd.DataFrame(rows)
    print("\nlead-lag map (descriptive): corr(r_X at hour t, gold r at t + L)")
    print(T.round(3).to_string(index=False))
    return T


def main():
    t0 = time.time()
    Gd = B1.load_gold(); Sv = B1.load_silver()
    check_clock(Gd)
    res = {}
    e1, d1, s1 = sig_X1()
    res["X1"] = evaluate("X1", Gd, Sv, lambda M: daily_rule(M, e1, d1, 10, 2), 10, 2, s1)
    # X2: DEV fixes the sign (two-sided)
    best = None
    for sgn in (1, -1):
        e2, d2, s2 = sig_X2(sgn)
        r = evaluate("X2", Gd, Sv, lambda M: daily_rule(M, e2, d2, 5, 2), 5, 2, s2)
        if best is None or r["DEV"]["mean_R"] > best[1]["DEV"]["mean_R"]:
            best = (sgn, r)
    res["X2"] = best[1]; res["X2"]["DEV"]["p"] = min(1.0, 2 * res["X2"]["DEV"]["p"]); res["X2"]["sign"] = best[0]
    e3, d3, s3 = sig_X3()
    res["X3"] = evaluate("X3", Gd, Sv, lambda M: daily_rule(M, e3, d3, 5, 2), 5, 2, s3)
    s4 = rule_X4(Gd)[2]
    res["X4"] = evaluate("X4", Gd, Sv, lambda M: rule_X4(M)[:2], 20, 3, s4)
    e5, d5, s5 = sig_X5()
    res["X5"] = evaluate("X5", Gd, Sv, lambda M: daily_rule(M, e5, d5, 20, 3), 20, 3, s5)
    s6 = rule_X6(Gd, "XAUUSD")[2]
    res["X6"] = evaluate("X6", Gd, Sv, lambda M: rule_X6(M, M["sym"])[:2], 6, 1.5, s6)
    print(f"rules done ({time.time() - t0:.0f}s)")
    order = ["X1", "X2", "X3", "X4", "X5", "X6"]
    pdev = np.array([res[h]["DEV"]["p"] for h in order], float)
    rej = np.zeros(len(order), bool)
    for r_, j in enumerate(np.argsort(pdev)):
        if pdev[j] <= 0.05 / (len(order) - r_):
            rej[j] = True
        else:
            break
    print("\nBatch 2 (net R per trade after cost and swap; p one-sided; DEV Holm over 6; control = same-direction random timing):")
    print(f"{'hyp':<4s} {'period':<7s} {'n':>5s} {'meanR':>8s} {'grossR':>8s} {'cost':>6s} {'win':>5s} {'totalR':>8s} {'p':>6s} {'ctlR':>7s} {'excess':>7s}")
    for j, h in enumerate(order):
        r = res[h]
        for p in ("DEV", "CHECK", "SILVER"):
            x = r[p]
            print(f"{h:<4s} {p:<7s} {x['n']:5d} {x['mean_R']:+8.3f} {x['mean_gross_R']:+8.3f} {x['cost_R']:6.3f} {x['win']:5.2f} {x['total_R']:+8.1f} "
                  f"{x['p']:6.3f} {x['control_R']:+7.3f} {x['excess']:+7.3f}")
        c, s = r["CHECK"], r["SILVER"]
        passed = bool(rej[j] and c["mean_R"] > 0 and c["p"] <= 0.05 and c["excess"] > 0 and s["mean_R"] > 0 and s["p"] <= 0.10)
        r["holm_dev"] = bool(rej[j]); r["PASS"] = passed
        print(f"     -> DEV Holm {'reject' if rej[j] else 'keep H0'}; {'PASS' if passed else 'FAIL'}" + (f" (sign {r['sign']:+d})" if "sign" in r else ""))
    T = leadlag(Gd)
    res["leadlag"] = T.to_dict(orient="records")
    B1.OUT.mkdir(parents=True, exist_ok=True)
    (B1.OUT / "batch2.json").write_text(json.dumps(res, indent=1, default=float))
    print(f"-> {B1.OUT / 'batch2.json'} ({time.time() - t0:.0f}s)")


if __name__ == "__main__":
    main()
