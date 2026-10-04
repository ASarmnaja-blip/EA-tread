#!/usr/bin/env python3
"""Did the M15/M30 search fail because of costs? Rebuild the minute events
of per_market_free_search_minute_tfs (gold, silver from 2009, BTC from 2021,
same specs) and split each stored top pattern's R into gross (price only)
and cost (spread + swap), in discovery and validation, non-overlapping
trades as the search counted them. Also the cost per trade in R over all
events of each timeframe and market.

If the patterns died of cost, gross R stays positive in validation and only
the net turns flat. If they died of overfitting, gross R itself collapses
from discovery to validation.

Usage: python3 research/g27k_dev/minute_cost_check.py --root <snap>
"""
import argparse
import json
import pathlib
import pickle
import sys

import numpy as np

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))
import h4d1_pattern_search as P
import intraday_pattern_search as IP
import per_market_search as PMS


def tstat(x):
    x = np.asarray(x, float)
    return float(x.mean() / x.std(ddof=1) * np.sqrt(len(x))) if len(x) > 2 and x.std() > 0 else float("nan")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    a = ap.parse_args()
    P.setup(a.root)
    P._M["scopes"] = PMS.SCOPES
    res = pickle.loads((PMS.CACHE / "pms_minute.pkl").read_bytes())
    stored = [c for s in PMS.SCOPES for c in res["best"][s]]
    h1 = {m: PMS.load_m1(m) for m in PMS.MKTS}
    P._M["h1"] = h1
    P._M["frames_for"] = IP.frames_minute
    out = dict(population={}, patterns=[])
    for tf in ("M15", "M30"):
        E, feats, cats = P.build(h1, tf)
        P._M["SPLIT"] = PMS.split_for(E)
        disc = E["t"] < P._M["SPLIT"]
        names, Bm = P.conditions(feats, cats, disc)
        for ex in P.EXITS:
            R = E[f"R_{ex}"]
            ok = np.isfinite(R)
            gross = E["d"] * (E[f"px_{ex}"] - E[f"ep_{ex}"]) / E[f"rk_{ex}"]
            cost = gross - R
            for m in PMS.MKTS:
                k = ok & (E["mkt"] == m)
                out["population"][f"{tf} {ex} {m}"] = dict(cost_R=float(np.median(cost[k])), stop_pct=float(np.median(E[f"rk_{ex}"][k] / E[f"ep_{ex}"][k] * 100)),
                                                            gross_all=float(gross[k].mean()), net_all=float(R[k].mean()))
        for c in [c for c in stored if c["tf"] == tf]:
            assert [names[q] for q in c["conds"]] == list(c["names"]), (c["names"], [names[q] for q in c["conds"]])
            ex = c["exit"]
            R = E[f"R_{ex}"]
            gross = E["d"] * (E[f"px_{ex}"] - E[f"ep_{ex}"]) / E[f"rk_{ex}"]
            mask = np.isfinite(R) & P.scope_mask(E, c["scope"])
            for q in c["conds"]:
                mask &= Bm[:, q]
            row = dict(scope=c["scope"], tf=tf, exit=ex, names=list(c["names"]))
            for nm, sel in (("disc", disc), ("val", ~disc)):
                k = P.no_overlap(E, mask & sel, ex)
                row[nm] = dict(n=int(len(k)), net=float(R[k].mean()), gross=float(gross[k].mean()), cost=float((gross[k] - R[k]).mean()),
                               t_net=tstat(R[k]), t_gross=tstat(gross[k]))
            out["patterns"].append(row)
            d_, v_ = row["disc"], row["val"]
            print(f"  {row['scope']:7s} {tf} {ex:4s} disc n {d_['n']:4d} net {d_['net']:+.3f} gross {d_['gross']:+.3f} cost {d_['cost']:.3f} | "
                  f"val n {v_['n']:4d} net {v_['net']:+.3f} gross {v_['gross']:+.3f} (t {v_['t_gross']:+.2f}) cost {v_['cost']:.3f} | {' & '.join(row['names'])}", flush=True)
        for k_, v in out["population"].items():
            if k_.startswith(tf):
                print(f"    all events {k_}: median cost {v['cost_R']:.3f}R per trade, median stop {v['stop_pct']:.2f}% of price, "
                      f"mean gross {v['gross_all']:+.3f} net {v['net_all']:+.3f}", flush=True)
        del E, feats, cats, Bm
    P_ = out["patterns"]
    for nm in ("disc", "val"):
        print(f"  {nm}: mean of {len(P_)} top patterns: net {np.mean([p[nm]['net'] for p in P_]):+.3f} gross {np.mean([p[nm]['gross'] for p in P_]):+.3f} "
              f"cost {np.mean([p[nm]['cost'] for p in P_]):.3f}")
    (HERE / "minute_cost_check.json").write_text(json.dumps(out, indent=1, default=float))


if __name__ == "__main__":
    main()
