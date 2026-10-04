#!/usr/bin/env python3
"""Fidelity check of the stage-2 L3 survivor (ledger fresh_l3_survivor_midprice_check):
the same pattern on BID and on MID ((bid+ask)/2) H1 bars built from the same
Dukascopy bid/ask files, FX markets of groups A and B, 2012-01..2023-12.

Usage: python3 research/g27k_dev/fresh_midprice_check.py --root <snap>
"""
import argparse
import glob
import json
import pathlib
import sys

import numpy as np
import pandas as pd

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))
import fresh_markets as FM
import fresh_search_l3 as L3
import fresh_validate as FV
import h4d1_pattern_search as P
import per_market_search as PMS
import walkforward_controller as W

FX = set(FM.FX)
LO, SP, HI = W.ts("2012-01-01"), W.ts("2020-01-01"), W.ts("2024-01-01")


def pair(m):
    f = sorted(glob.glob(str(PMS.CACHE.parent / ".cache_duka" / f"{m}_H1_*.parquet")), key=lambda p: -pd.read_parquet(p).shape[0])[0]
    d = pd.read_parquet(f)
    d = d[(d.index >= "2012-01-01") & (d.index < "2024-01-01") & (d.ask_close > d.bid_close) & (d.bid_high > d.bid_low)]
    d = d[~d.index.duplicated()].sort_index()
    t = ((d.index - pd.Timestamp("1970-01-01", tz="UTC")) // pd.Timedelta("1s")).to_numpy(np.int64)
    bid = dict(t=t, o=d.bid_open.to_numpy(float), h=d.bid_high.to_numpy(float), l=d.bid_low.to_numpy(float), c=d.bid_close.to_numpy(float),
               v=d.volume.to_numpy(float), step=3600)
    mid = dict(bid, **{k: ((d[f"bid_{x}"] + d[f"ask_{x}"]) / 2).to_numpy(float) for k, x in (("o", "open"), ("h", "high"), ("l", "low"), ("c", "close"))})
    return bid, mid


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    a = ap.parse_args()
    P.setup(a.root)
    C = P._M["C"]
    C.SPECS.update(FM.specs(C))
    PMS.SCOPES = ("pooled",)
    P._M.update(scopes=("pooled",), scope_sets={})
    surv = json.loads((HERE / "fresh_validate_l3.json").read_text())["survivors"][0]
    c = dict(tf=surv["tf"], exit=surv["exit"], names=surv["names"])
    print(f"  survivor: {c['tf']} {c['exit']} {' & '.join(c['names'])}")
    res = {}
    for grp, mk in (("A", [m for m in L3.GROUP_A if m in FX]), ("B", [m for m in L3.GROUP_B if m in FX])):
        bid, mid = {}, {}
        for m in mk:
            bid[m], mid[m] = pair(m)
        for kind, h in (("bid", bid), ("mid", mid)):
            ev = FV.Events(h)
            for nm, lo, hi in (("2012-2019", LO, SP), ("2020-2023", SP, HI), ("2012-2023", LO, HI)):
                mkt, R, _ = FV.l3_trades(ev, c, None, lo, hi)
                s = FV.summarize(mkt, R)
                res[f"{grp}|{kind}|{nm}"] = s
                print(f"  group {grp} FX ({len(mk)}) {kind:3s} {nm}: n {s['n']:4d}  R {s['R']:+.3f}  t {s['t']:+.2f}  markets+ {s['pos_share']:.0%}", flush=True)
    rB_mid, rB_bid = res["B|mid|2012-2023"], res["B|bid|2012-2023"]
    rA_mid = res["A|mid|2020-2023"]
    keep = bool(rB_mid["t"] > 2 and rB_mid["R"] > 0 and rA_mid["R"] > 0 and rB_mid["R"] >= 0.5 * rB_bid["R"])
    res["verdict"] = "candidate" if keep else "bid-quote rollover artifact"
    print("  verdict:", res["verdict"])
    (HERE / "fresh_midprice_check.json").write_text(json.dumps(res, indent=1, default=float))


if __name__ == "__main__":
    main()
