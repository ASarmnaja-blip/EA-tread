#!/usr/bin/env python3
"""Experiment only, never for live use: gold on a small timeframe at extreme
risk, every profit withdrawn at once so only the starting capital trades.

Trades: the M30 sleeve rule on XAUUSD (Dukascopy M1, the 710 trades of
m30_sleeve6.pkl, 2011-09..2026-09), plus the same rule on M15 for
comparison (not validated on M15). One trade at a time.

Account per trade: risk r x current balance; P&L = r x balance x R; if the
balance ends above the starting capital (1.0) the excess is withdrawn; a
balance below 10% of the capital is a blow-up.

  lives:    a fresh account started every week; days until it blows up and
            what it withdrew before that
  restart:  one account from 2011-09; each blow-up is followed at once by a
            new deposit of the capital; total deposited vs withdrawn

Usage: python3 research/g27k_dev/gold_sweep.py --root <snap>
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

RISKS = (0.10, 0.20, 0.30, 0.50, 0.75, 1.00)
FLOOR = 0.10
DAY = 86400


def life(R, t, i0, r):
    """From trade i0: (index of the blow-up trade or None, withdrawn)."""
    bal, wd = 1.0, 0.0
    for i in range(i0, len(R)):
        bal += r * bal * R[i]
        if bal > 1.0:
            wd += bal - 1.0
            bal = 1.0
        if bal < FLOOR:
            return i, wd
    return None, wd


def restart(R, r):
    bal, wd, dep, blow = 1.0, 0.0, 1.0, 0
    for x in R:
        bal += r * bal * x
        if bal > 1.0:
            wd += bal - 1.0
            bal = 1.0
        if bal < FLOOR:
            blow += 1
            dep += 1.0
            bal = 1.0
    return dict(deposited=dep, withdrawn=wd, net=wd - dep + bal, blowups=blow)


def study(T, label):
    R, t, tx = T.R.to_numpy(), T.t.to_numpy(), T.tx.to_numpy()
    weeks = pd.date_range("2011-09-05", "2026-09-28", freq="7D", tz="UTC")
    starts = [int(np.searchsorted(t, int(w.timestamp()))) for w in weeks]
    out = dict(n=int(len(R)), win=float((R > 0).mean()), R=float(R.mean()), maxR=float(R.max()), minR=float(R.min()),
               max_losing_streak=int(max((len(s) for s in "".join("L" if x < 0 else "W" for x in R).split("W")), default=0)), risks={})
    print(f"  [{label}] {len(R)} trades, win {out['win']:.0%}, mean {out['R']:+.3f}R, best {out['maxR']:+.2f}R, worst {out['minR']:+.2f}R, "
          f"longest losing run {out['max_losing_streak']}", flush=True)
    for r in RISKS:
        days, wds, alive = [], [], 0
        for w, i0 in zip(weeks, starts):
            if i0 >= len(R):
                continue
            j, wd = life(R, t, i0, r)
            wds.append(wd)
            if j is None:
                alive += 1
                days.append(np.inf)
            else:
                days.append((tx[j] - int(w.timestamp())) / DAY)
        days, wds = np.array(days), np.array(wds)
        rs = restart(R, r)
        res = dict(lives=int(len(days)), p_blow_7d=float((days <= 7).mean()), p_blow_30d=float((days <= 30).mean()),
                   p_blow_1y=float((days <= 365).mean()), survived_to_end=int(alive),
                   median_days=float(np.median(days)), withdrawn_median=float(np.median(wds)), withdrawn_mean=float(wds.mean()),
                   withdrawn_best=float(wds.max()), best_trade_pct=float(r * R.max()), restart=rs)
        out["risks"][f"{r:.2f}"] = res
        md = "never" if not np.isfinite(res["median_days"]) else f"{res['median_days']:.0f} d"
        print(f"    risk {r:4.0%}: blow-up within 7d {res['p_blow_7d']:5.1%} 30d {res['p_blow_30d']:5.1%} 1y {res['p_blow_1y']:5.1%} | median life {md:>6} | "
              f"withdrawn per life median x{res['withdrawn_median']:.2f} mean x{res['withdrawn_mean']:.2f} best x{res['withdrawn_best']:.1f} | "
              f"best trade +{res['best_trade_pct']:.0%} | restart 15y: deposited x{rs['deposited']:.0f} withdrawn x{rs['withdrawn']:.1f} "
              f"net x{rs['net']:+.1f} blow-ups {rs['blowups']}", flush=True)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    a = ap.parse_args()
    out = {}
    S = pickle.loads((PMS.CACHE / "m30_sleeve6.pkl").read_bytes())
    out["M30"] = study(S[S.mkt == "XAUUSD"].sort_values("t").reset_index(drop=True), "gold M30 (validated rule)")
    NM.prepare(a.root, ("XAUUSD",))
    spec = dict(HS.spec_of(HS.pick()), tf="M15", near="brk55", thr=-1.0, vol=1.5, ctx="htf1_with", dir="both", exit="tp2")
    E, feats, cats = P.build(P._M["h1"], "M15")
    T15 = HS.trades(E, P.no_overlap(E, HS.mask(E, feats, cats, spec), "tp2"), spec)
    out["M15"] = study(T15, "gold M15 (same rule, not validated)")
    (HERE / "gold_sweep.json").write_text(json.dumps(out, indent=1, default=float))


if __name__ == "__main__":
    main()
