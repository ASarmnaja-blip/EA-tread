"""Hypothesis batch 5 (docs/HYPOTHESIS_BATCH5_PREREG.md): D4 GVZ panic, A7 quarter end, W1 Monday; J2 ensemble read-out. Light loaders (no M5).
Usage: python research/hyp/batch5.py -> data/hyp/batch5.json (+ stdout log)"""
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
import batch2 as B2  # noqa: E402
import batch3 as B3  # noqa: E402

ROOT = B1.ROOT


def light_gold():
    B, cuts, _ = B1.SG.load_xau("H1")
    D = B1.SG.load_xau("D1")[0]
    return dict(sym="XAUUSD", H1=B1.mkbars(B.t, B.o, B.h, B.l, B.c, B.spread_bp, 3600, B.atr),
                D1=B1.mkbars(D.t, D.o, D.h, D.l, D.c, D.spread_bp, 86400, D.atr), cuts=cuts)


def light_silver():
    import xag as X
    B, cuts, _ = X.load_xag("H1")
    D = X.load_xag("D1")[0]
    return dict(sym="XAGUSD", H1=B1.mkbars(B.t, B.o, B.h, B.l, B.c, B.spread_bp, 3600, B.atr),
                D1=B1.mkbars(D.t, D.o, D.h, D.l, D.c, D.spread_bp, 86400, D.atr), cuts=cuts)


def sig_D4():
    gv = pd.read_csv(ROOT / "data" / "external" / "GVZ_History.csv")
    gv["DATE"] = pd.to_datetime(gv.DATE, format="%m/%d/%Y"); gv = gv.sort_values("DATE").reset_index(drop=True)
    ch = np.log(gv.GVZ / gv.GVZ.shift(1)).to_numpy()
    q = B2.causal_q(ch, 0.975)
    m = np.isfinite(q) & np.isfinite(ch) & (ch >= q)
    end = (gv.DATE.values.astype("datetime64[s]").astype(np.int64) + 86400)[m]
    return end


def rule_D4(M, sign, end):
    return B2.daily_rule(M, end, float(sign) * np.ones(len(end)), 5, 2)


def rule_A7(M, sign):
    D = M["D1"]; lab = B3.day_label(D); ym = (lab.year * 100 + lab.month).to_numpy()
    e = []
    for i in range(3, len(D.t) - 6):
        if lab.month[i] in (3, 6, 9, 12) and ym[i + 3] != ym[i] and ym[i + 2] == ym[i]:      # 3rd-last bar of the quarter-end month
            e.append(i)
    e = np.array(e, int)
    return D, dict(e=e, d=float(sign) * np.ones(len(e)), stop=2 * D.atr[e], tgt=np.full(len(e), np.nan), last=e + 4)


def rule_W1(M, sign):
    D = M["D1"]; lab = B3.day_label(D)
    e = np.flatnonzero(lab.dayofweek.to_numpy() == 0); e = e[e < len(D.t) - 1]
    return D, dict(e=e, d=float(sign) * np.ones(len(e)), stop=2 * D.atr[e], tgt=np.full(len(e), np.nan), last=e)


def two_sided(Gd, Sv, build, hold, k_stop):
    best = None
    for s in (1, -1):
        r = B3.evaluate(Gd, Sv, lambda M, s=s: build(M, s), hold, k_stop)
        if best is None or r["DEV"]["mean_R"] > best[1]["DEV"]["mean_R"]:
            best = (s, r)
    r = best[1]; r["DEV"]["p"] = min(1.0, 2 * r["DEV"]["p"]); r["sign"] = best[0]
    return r


def ensemble():
    out = {}
    for sym, f in (("XAUUSD", ROOT / "data" / "wrwr" / "family_XAUUSD_f2.npz"), ("XAGUSD", ROOT / "data" / "wrwr" / "xag" / "family_XAGUSD_f2.npz")):
        z = np.load(f, allow_pickle=False); act = z["active"]; R = z["R_0.01"][act]
        ens = R.mean(1); tot = R.sum(0)
        med = int(np.argsort(tot)[len(tot) // 2]); best = int(np.argmax(tot))
        g = lambda x: float(np.prod(1 + 0.01 * x))
        out[sym] = dict(ensemble_total=float(ens.sum()), ensemble_growth=g(ens), median_cfg_total=float(tot[med]), best_cfg_total=float(tot[best]),
                        best_cfg=best, share_positive_cfgs=float((tot > 0).mean()), weeks=int(act.sum()))
        print(f"J2 {sym}: ensemble of 144 configurations total {ens.sum():+.1f} R (equity x{g(ens):.2f}); median configuration {tot[med]:+.1f} R; "
              f"best (in-sample) {tot[best]:+.1f} R (cfg {best}); configurations with total > 0: {(tot > 0).mean():.0%}")
    return out


def main():
    t0 = time.time()
    Gd = light_gold(); Sv = light_silver()
    end = sig_D4()
    res = {"D4": two_sided(Gd, Sv, lambda M, s: rule_D4(M, s, end), 5, 2), "A7": two_sided(Gd, Sv, rule_A7, 5, 2), "W1": two_sided(Gd, Sv, rule_W1, 1, 2)}
    order = ["D4", "A7", "W1"]
    pdev = np.array([res[h]["DEV"]["p"] for h in order], float)
    rej = np.zeros(3, bool)
    for r_, j in enumerate(np.argsort(pdev)):
        if pdev[j] <= 0.05 / (3 - r_):
            rej[j] = True
        else:
            break
    print("Batch 5 (net R per trade after cost and swap; DEV p two-sided (doubled), Holm over 3; control = same-direction random timing):")
    print(f"{'hyp':<4s} {'period':<7s} {'n':>5s} {'meanR':>8s} {'grossR':>8s} {'cost':>6s} {'win':>5s} {'totalR':>8s} {'p':>6s} {'ctlR':>7s} {'excess':>7s}")
    for j, h in enumerate(order):
        r = res[h]
        for p in ("DEV", "CHECK", "SILVER"):
            x = r[p]
            print(f"{h:<4s} {p:<7s} {x['n']:5d} {x['mean_R']:+8.3f} {x['mean_gross_R']:+8.3f} {x['cost_R']:6.3f} {x['win']:5.2f} {x['total_R']:+8.1f} "
                  f"{x['p']:6.3f} {x['control_R']:+7.3f} {x['excess']:+7.3f}")
        c, s = r["CHECK"], r["SILVER"]
        r["PASS"] = bool(rej[j] and c["mean_R"] > 0 and c["p"] <= 0.05 and c["excess"] > 0 and s["mean_R"] > 0 and s["p"] <= 0.10)
        print(f"     -> DEV Holm {'reject' if rej[j] else 'keep H0'}; {'PASS' if r['PASS'] else 'FAIL'} (sign {r['sign']:+d})")
    res["J2"] = ensemble()
    (B1.OUT / "batch5.json").write_text(json.dumps(res, indent=1, default=float))
    print(f"-> {B1.OUT / 'batch5.json'} ({time.time() - t0:.0f}s)")


if __name__ == "__main__":
    main()
