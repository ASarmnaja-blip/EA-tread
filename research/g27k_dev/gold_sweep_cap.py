#!/usr/bin/env python3
"""Experiment only, never for live use: gold_sweep with a cap on blow-ups.
Same account as gold_sweep.py (risk r x balance, profits above the capital
withdrawn at once, below 10% = blow-up, then a new deposit of the capital),
risk 5%..100% in 5% steps, on the gold M30 rule and the same rule on M15.
A risk passes if no rolling 3-month window holds more than one blow-up.
Monthly figures are in % of the capital: withdrawn minus new deposits.

Usage: python3 research/g27k_dev/gold_sweep_cap.py --root <snap>
"""
import argparse
import json
import pathlib
import pickle
import sys

import numpy as np
import pandas as pd

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))
import h1_sleeve as HS
import h4d1_pattern_search as P
import m30_new_markets as NM
import per_market_search as PMS
from gold_sweep import FLOOR

RISKS = tuple(round(0.05 * k, 2) for k in range(1, 21))
WIN = 91 * 86400


def run(T, r):
    bal, blows, flows = 1.0, [], []          # flows: (exit time, +withdrawn / -deposit)
    for R, tx in zip(T.R.to_numpy(), T.tx.to_numpy()):
        bal += r * bal * R
        if bal > 1.0:
            flows.append((tx, bal - 1.0))
            bal = 1.0
        if bal < FLOOR:
            blows.append(tx)
            flows.append((tx, -1.0))
            bal = 1.0
    b = np.array(blows)
    worst3 = int(max((np.searchsorted(b, x + WIN, "left") - i for i, x in enumerate(b)), default=0))
    f = pd.Series([v for _, v in flows], index=pd.to_datetime([t for t, _ in flows], unit="s"))
    m = f.resample("ME").sum().reindex(pd.date_range("2011-09-30", "2026-09-30", freq="ME"), fill_value=0.0)
    return dict(blowups=len(b), worst_3m_blowups=worst3, ok=worst3 <= 1, net_total=float(m.sum() - 1.0 + bal),
                month_mean=float(m.mean()), month_median=float(m.median()), months_pos=float((m > 0).mean()),
                months_ge5=float((m >= 0.05).mean()), best_month=float(m.max()), worst_month=float(m.min()),
                year=m.groupby(m.index.year).sum().round(3).to_dict())


def study(T, label):
    out = {}
    print(f"  [{label}] {len(T)} trades", flush=True)
    for r in RISKS:
        x = run(T, r)
        out[f"{r:.2f}"] = x
        print(f"    risk {r:4.0%}: blow-ups {x['blowups']:3d} (most in 3 months {x['worst_3m_blowups']}) {'OK ' if x['ok'] else '-- '}| "
              f"net per month mean {x['month_mean']:+.1%} median {x['month_median']:+.1%} | months >= +5% {x['months_ge5']:.0%} | "
              f"best month {x['best_month']:+.0%} worst {x['worst_month']:+.0%} | 15y net x{x['net_total']:+.1f}", flush=True)
    ok = [r for r in out if out[r]["ok"]]
    best = max(ok, key=lambda r: out[r]["month_mean"]) if ok else None
    print(f"    -> highest risk within 1 blow-up per 3 months: {max(ok) if ok else 'none'}; best monthly mean among those: {best}", flush=True)
    return dict(risks=out, best=best)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    a = ap.parse_args()
    S = pickle.loads((PMS.CACHE / "m30_sleeve6.pkl").read_bytes())
    out = {"M30": study(S[S.mkt == "XAUUSD"].sort_values("t").reset_index(drop=True), "gold M30")}
    NM.prepare(a.root, ("XAUUSD",))
    spec = dict(HS.spec_of(HS.pick()), tf="M15", near="brk55", thr=-1.0, vol=1.5, ctx="htf1_with", dir="both", exit="tp2")
    E, feats, cats = P.build(P._M["h1"], "M15")
    out["M15"] = study(HS.trades(E, P.no_overlap(E, HS.mask(E, feats, cats, spec), "tp2"), spec), "gold M15 (not validated)")
    (HERE / "gold_sweep_cap.json").write_text(json.dumps(out, indent=1, default=float))


if __name__ == "__main__":
    main()
