"""Hypothesis batch 3 (docs/HYPOTHESIS_BATCH3_PREREG.md): T1 12-month time-series momentum, K1 autumn effect, K2 turn of the year, K3 before
Chinese New Year; drift controls. Research only. Usage: python research/hyp/batch3.py -> data/hyp/batch3.json (+ stdout log)"""
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

CNY = ["2004-01-22", "2005-02-09", "2006-01-29", "2007-02-18", "2008-02-07", "2009-01-26", "2010-02-14", "2011-02-03", "2012-01-23", "2013-02-10",
       "2014-01-31", "2015-02-19", "2016-02-08", "2017-01-28", "2018-02-16", "2019-02-05", "2020-01-25", "2021-02-12", "2022-02-01", "2023-01-22",
       "2024-02-10", "2025-01-29", "2026-02-17"]


def rule_T1(M, L=252):
    D = M["D1"]; lc = np.log(D.c)
    e = np.arange(L + 1, len(D.t) - 22, 21)
    d = np.sign(lc[e - 1] - lc[e - 1 - L])
    m = d != 0
    e, d = e[m], d[m]
    return D, dict(e=e, d=d, stop=3 * D.atr[e], tgt=np.full(len(e), np.nan), last=e + 20)


def day_label(D):
    """Calendar date of each 22:00-anchored D1 bar (the day it mostly covers)."""
    return pd.to_datetime(D.t + 2 * 3600, unit="s")


def rule_K1(M):
    D = M["D1"]; lab = day_label(D)
    ym = lab.year * 100 + lab.month
    e = []
    for i in range(1, len(D.t) - 22):
        if lab.month[i] in (9, 11) and ym[i] != ym[i - 1]:
            e.append(i)
    e = np.array(e, int)
    return D, dict(e=e, d=np.ones(len(e)), stop=3 * D.atr[e], tgt=np.full(len(e), np.nan), last=e + 20)


def rule_K2(M):
    D = M["D1"]; lab = day_label(D)
    e = []
    for i in range(6, len(D.t) - 11):
        if lab.month[i] == 1 and lab.month[i - 1] == 12:                   # first January bar
            e.append(i - 5)
    e = np.array(e, int)
    return D, dict(e=e, d=np.ones(len(e)), stop=3 * D.atr[e], tgt=np.full(len(e), np.nan), last=e + 9)


def rule_K3(M):
    D = M["D1"]; lab = day_label(D).normalize()
    e = []
    for s in CNY:
        j = int(np.searchsorted(lab.values, np.datetime64(pd.Timestamp(s)), side="left"))
        if 10 <= j < len(D.t):
            e.append(j - 10)
    e = np.array(e, int)
    return D, dict(e=e, d=np.ones(len(e)), stop=3 * D.atr[e], tgt=np.full(len(e), np.nan), last=e + 9)


def evaluate(Gd, Sv, build, hold, k_stop):
    res = {}
    for M, per in ((Gd, {k: v for k, v in B1.PERIODS.items() if k != "SILVER"}), (Sv, {"SILVER": B1.PERIODS["SILVER"]})):
        B, ev = build(M)
        tr = B1.simulate_events(B, M["sym"], **ev)
        for p, (a, b) in per.items():
            S, N, sub = B1.weekly(tr, M["cuts"], a, b)
            m, pv = B1.boot_p(S, N)
            share = {1.0: float((sub.d > 0).mean()) if len(sub) else 0.0, -1.0: float((sub.d < 0).mean()) if len(sub) else 0.0}
            ctl = B2.control(M, B, hold, k_stop, a, b, share) if len(sub) else float("nan")
            res[p] = dict(**B1.summarize(sub), p=pv, control_R=ctl, excess=float(sub.R.mean() - ctl) if len(sub) else float("nan"))
    return res


def main():
    t0 = time.time()
    Gd = B1.load_gold(); Sv = B1.load_silver()
    res = {"T1": evaluate(Gd, Sv, rule_T1, 21, 3), "K1": evaluate(Gd, Sv, rule_K1, 21, 3), "K2": evaluate(Gd, Sv, rule_K2, 10, 3),
           "K3": evaluate(Gd, Sv, rule_K3, 10, 3)}
    desc = {f"T1_L{L}": evaluate(Gd, Sv, lambda M, L=L: rule_T1(M, L), 21, 3) for L in (21, 63, 126)}
    order = ["T1", "K1", "K2", "K3"]
    pdev = np.array([res[h]["DEV"]["p"] for h in order], float)
    rej = np.zeros(len(order), bool)
    for r_, j in enumerate(np.argsort(pdev)):
        if pdev[j] <= 0.05 / (len(order) - r_):
            rej[j] = True
        else:
            break
    print("Batch 3 (net R per trade after cost and swap; p one-sided; DEV Holm over 4; control = same-direction random timing):")
    print(f"{'hyp':<7s} {'period':<7s} {'n':>5s} {'meanR':>8s} {'grossR':>8s} {'cost':>6s} {'win':>5s} {'totalR':>8s} {'p':>6s} {'ctlR':>7s} {'excess':>7s}")
    for h in order + list(desc):
        r = res.get(h, desc.get(h))
        for p in ("DEV", "CHECK", "SILVER"):
            x = r[p]
            print(f"{h:<7s} {p:<7s} {x['n']:5d} {x['mean_R']:+8.3f} {x['mean_gross_R']:+8.3f} {x['cost_R']:6.3f} {x['win']:5.2f} {x['total_R']:+8.1f} "
                  f"{x['p']:6.3f} {x['control_R']:+7.3f} {x['excess']:+7.3f}")
        if h in order:
            j = order.index(h); c, s = r["CHECK"], r["SILVER"]
            r["PASS"] = bool(rej[j] and c["mean_R"] > 0 and c["p"] <= 0.05 and c["excess"] > 0 and s["mean_R"] > 0 and s["p"] <= 0.10)
            print(f"        -> DEV Holm {'reject' if rej[j] else 'keep H0'}; {'PASS' if r['PASS'] else 'FAIL'}")
        else:
            print("        (descriptive)")
    (B1.OUT / "batch3.json").write_text(json.dumps({"primaries": res, "descriptive": desc}, indent=1, default=float))
    print(f"-> {B1.OUT / 'batch3.json'} ({time.time() - t0:.0f}s)")


if __name__ == "__main__":
    main()
