"""Hypothesis batch 6 (docs/HYPOTHESIS_BATCH6_PREREG.md): P1 gold/silver ratio mean reversion; R1 weekend de-risking rule (Risk Manager
candidate). Usage: python research/hyp/batch6.py P1 | R1 XAUUSD | R1 XAGUSD | R1report"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import batch1 as B1  # noqa: E402

ROOT = B1.ROOT
sys.path.insert(0, str(ROOT / "research" / "wrwr"))
import contracts as K  # noqa: E402


# ------------------------------------------------------------------ P1
def p1():
    import signals as SG
    import xag as X
    Dg = SG.load_xau("D1")[0]; cuts = SG.load_xau("H1")[1]
    Ds = X.load_xag("D1")[0]
    kg = (Dg.t - 22 * 3600) // 86400; ks = (Ds.t - 22 * 3600) // 86400
    common, ig, is_ = np.intersect1d(kg, ks, return_indices=True)
    go, gc, gsp, gt = Dg.o[ig], Dg.c[ig], Dg.spread_bp[ig], Dg.t[ig]
    so, sc, ssp, st = Ds.o[is_], Ds.c[is_], Ds.spread_bp[is_], Ds.t[is_]
    r = np.log(gc) - np.log(sc)
    n = len(r); z = np.full(n, np.nan); sd = np.full(n, np.nan)
    for i in range(250, n):
        w = r[i - 250:i]; sd[i] = w.std(ddof=1); z[i] = (r[i] - w.mean()) / sd[i]
    rows = []; i = 250
    while i < n - 2:
        if not np.isfinite(z[i]) or abs(z[i]) < 2:
            i += 1; continue
        dg = -1.0 if z[i] > 0 else 1.0; ds = -dg                               # z > 0: gold rich -> short gold, long silver
        e = i + 1; s0 = sd[i]; r0 = np.log(go[e]) - np.log(so[e])
        j = e; ex = None
        while j < n and j <= e + 59:
            zj = (r[j] - np.mean(r[j - 250:j])) / np.std(r[j - 250:j], ddof=1)
            adverse = (r[j] - r0) * (-dg)                                    # ratio moving against the position (+ = against)
            if abs(zj) <= 0.5 or adverse >= 1.5 * s0:
                ex = j; break
            j += 1
        ex = ex if ex is not None else min(e + 59, n - 1)
        ret = dg * (gc[ex] / go[e] - 1) + ds * (sc[ex] / so[e] - 1)
        cost = (K.cost_bp("XAUUSD", gsp[[e]])[0] + B1.cost_bp("XAGUSD", ssp[[e]], st[[e]])[0]) / 1e4
        long_sym, lt0, lt1 = ("XAUUSD", gt[e], gt[ex] + 86400) if dg > 0 else ("XAGUSD", st[e], st[ex] + 86400)
        sw = K.swap_bp(long_sym, np.array([lt0]), np.array([lt1]), np.array([1.0]))[0] / 1e4
        risk = 1.5 * s0
        rows.append(dict(t=int(gt[e]), d=dg, gross_bp=ret * 1e4, cost_bp=cost * 1e4, swap_bp=sw * 1e4, stop_bp=risk * 1e4,
                         R=(ret - cost - sw) / risk, gR=ret / risk, days=int(ex - e + 1)))
        i = ex + 1
    tr = pd.DataFrame(rows)
    out = {}
    for p, (a, b) in (("DEV", ("2010-05-01", "2018-01-01")), ("CHECK", ("2018-01-01", "2026-10-01"))):
        S, N, sub = B1.weekly(tr, cuts, a, b)
        m, pv = B1.boot_p(S, N)
        out[p] = dict(**B1.summarize(sub), p=pv, mean_days=float(sub.days.mean()) if len(sub) else float("nan"))
        x = out[p]
        print(f"P1 {p:<6s} n {x['n']:4d} mean R {x['mean_R']:+.3f} gross {x['mean_gross_R']:+.3f} cost {x['cost_R']:.3f} win {x['win']:.2f} "
              f"total {x['total_R']:+.1f} p {x['p']:.3f} mean hold {x['mean_days']:.1f} days")
    out["PASS"] = bool(out["DEV"]["p"] <= 0.05 and out["CHECK"]["mean_R"] > 0 and out["CHECK"]["p"] <= 0.05)
    print("P1 ->", "PASS" if out["PASS"] else "FAIL")
    (B1.OUT / "batch6_P1.json").write_text(json.dumps(out, indent=1, default=float))


# ------------------------------------------------------------------ R1
def r1(sym):
    import weekend_check as WC
    import portfolio as PF
    P, z, bars, _, base = WC.setup(sym)
    t, o, c = base
    wk = WC.weekend_after(t, 3600); iw = np.flatnonzero(wk)
    gap = np.abs(o[iw + 1] / c[iw] - 1) * 1e4
    m8 = pd.Series(gap).rolling(8, min_periods=8).mean().shift(1).to_numpy()            # previous 8 weekends
    thr = pd.Series(m8).rolling(52, min_periods=26).quantile(0.75).shift(1).to_numpy()
    high = np.isfinite(m8) & np.isfinite(thr) & (m8 > thr)
    fri_week = np.searchsorted(P.cuts, t[iw], side="left") - 1                           # week of the Friday before each weekend
    high_by_week = dict(zip(fri_week.tolist(), high.tolist()))
    wk_idx = {tf: np.flatnonzero(WC.weekend_after(B.t, B.step)) for tf, B in bars.items()}
    res = {}
    for nm, j in WC.SHADOW.items():
        ch = [[int(x) for x in w] for w in json.loads(str(z["champs"]))[str(j)]]
        log = []
        wr, eq, _ = PF.simulate(P, ch, z["vol_scale"], f=0.01, log=log)
        NW = len(P.cuts); act = z["active"]
        base_w = np.zeros(NW); new_w = np.zeros(NW)
        for (k, cnd, te, xt, lots, R_i, pnl, eqe) in log:
            kx = int(np.searchsorted(P.cuts, xt, side="left")) - 1
            if kx >= NW - 1 or not act[kx]:
                continue
            cd = P.cands[cnd]; B = bars[cd["tf"]]
            i = int(np.searchsorted(P.entry_t[cnd], te)); e = int(np.searchsorted(B.t, te))
            d = float(P.dir[cnd][i]); stop = cd["k_atr"] * B.atr[e]; last = e + cd["hold"] - 1
            wl = wk_idx[cd["tf"]]; q = int(np.searchsorted(wl, e, side="left")); wlast = int(wl[q]) if q < len(wl) else 10 ** 9
            Rw = pnl / (0.01 * eq[kx]); base_w[kx] += Rw
            g1, ex1 = WC.E.simulate(B, [e], [d], [stop], [WC.MULT[cd["exit"]] * stop], [last])
            fw = int(np.searchsorted(P.cuts, B.t[wlast], side="left")) - 1 if wlast < 10 ** 9 else -1
            if int(ex1[0]) > wlast and high_by_week.get(fw, False):
                g2, ex2 = WC.E.simulate(B, [e], [d], [stop], [WC.MULT[cd["exit"]] * stop], [min(last, wlast)])
                sb = float(P.stop_bp[cnd][i]); w = lots * float(P.stop_px[cnd][i]) * P.contract / (0.01 * eq[kx]) / sb
                sw1 = float(P.swap_bp[cnd][i]); sw2 = float(K.swap_bp(sym, B.t[[e]], B.t[ex2] + B.step, [d])[0])
                cf = Rw + ((float(g2[0]) - sw2) - (float(g1[0]) - sw1)) * w
                new_w[kx] += 0.5 * Rw; new_w[max(fw, 0)] += 0.5 * cf              # the closed half is booked in the Friday week
            else:
                new_w[kx] += Rw
        a, b = base_w[act], new_w[act]
        dd = lambda x: float((np.maximum.accumulate(np.cumsum(x)) - np.cumsum(x)).max())
        res[nm] = dict(total=float(a.sum()), total_new=float(b.sum()), p1=float(np.percentile(a, 1)), p1_new=float(np.percentile(b, 1)),
                       dd=dd(a), dd_new=dd(b), worst=float(a.min()), worst_new=float(b.min()))
        x = res[nm]
        print(f"R1 {sym} {nm}: total {x['total']:+.1f} -> {x['total_new']:+.1f} R; 1st pct weekly R {x['p1']:+.2f} -> {x['p1_new']:+.2f}; "
              f"worst week {x['worst']:+.2f} -> {x['worst_new']:+.2f}; max DD {x['dd']:.1f} -> {x['dd_new']:.1f} R", flush=True)
    res["high_share"] = float(high.mean())
    print(f"R1 {sym}: high-gap regime on {high.mean():.0%} of weekends")
    (B1.OUT / f"batch6_R1_{sym}.json").write_text(json.dumps(res, indent=1, default=float))


def r1report():
    runs = []
    for sym in ("XAUUSD", "XAGUSD"):
        j = json.loads((B1.OUT / f"batch6_R1_{sym}.json").read_text())
        runs += [v for k, v in j.items() if isinstance(v, dict)]
    dp1 = np.mean([r["p1_new"] - r["p1"] for r in runs]); ddd = np.mean([r["dd_new"] - r["dd"] for r in runs])
    dtot = sum(r["total_new"] - r["total"] for r in runs); abs_tot = sum(abs(r["total"]) for r in runs)
    adopt = bool(dp1 > 0 and ddd < 0 and dtot >= -0.10 * abs_tot)
    print(f"R1 over 8 runs: mean change of the 1st-percentile week {dp1:+.3f} R, mean change of max DD {ddd:+.2f} R, total change {dtot:+.1f} R "
          f"(limit {-0.10 * abs_tot:+.1f}) -> {'ADOPT as a Risk Manager candidate' if adopt else 'do not adopt'}")
    (B1.OUT / "batch6_R1.json").write_text(json.dumps(dict(mean_dp1=dp1, mean_ddd=ddd, total_change=dtot, adopt=adopt), indent=1, default=float))


if __name__ == "__main__":
    if sys.argv[1] == "P1":
        p1()
    elif sys.argv[1] == "R1":
        r1(sys.argv[2])
    else:
        r1report()
