#!/usr/bin/env python3
"""Experiment only, never for live use: the risk per trade that maximises the
final balance of G27K-F + M30 sleeve + H1 sleeve over 2011-09..2026-09,
drawdown ignored. Each book gets its own risk (% of balance per trade, no
brake, no cap on open risk); the account is the suite simulator (risk taken
on the balance at entry, P&L booked at exit; a balance at or below zero ends
the account).

  1. coarse grid over (G27K-F, M30, H1) risk, Cent and Standard
  2. the best mix scaled 0.25x..4x to show what over-betting does
  3. the growth-optimal mix and the over-bet mixes on 2011-18 and 2019-26
     separately (an optimum picked on the whole history is in-sample)

The optimum is fitted on the same data it is scored on, so its numbers are an
upper bound of what this history allowed, not an expectation.

Usage: python3 research/g27k_dev/max_growth.py --root <snap>
"""
import argparse
import itertools
import json
import pathlib
import pickle
import sys
import time

import numpy as np
import pandas as pd

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))
import h1_sleeve as HS
import h4d1_pattern_search as P
import news_shock as NS
import per_market_search as PMS

START, MID, END = "2011-09-01", "2019-01-01", "2026-10-01"
KG = (1, 2, 3, 4, 5, 6, 8, 10, 12, 15)
KS = (0, 1, 2, 3, 4, 5, 6, 8, 10)
LAMBDA = (0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 2.0, 3.0, 4.0)


def run(F, start=START, end=END):
    st, eq, _ = NS.SU.simulate(F, "normal", start, end)
    out = dict(final=st["final"], cagr=st["cagr"], dd=st["dd"], n=st["n"], ruined=bool(st["final"] <= 0.0))
    if len(eq):
        m = eq.resample("ME").last().ffill()
        r = m.pct_change().dropna()
        out["worst_month"] = float(r.min()) if len(r) else float("nan")
        r3 = (m / m.shift(3) - 1).dropna()
        out["worst_3m"] = float(r3.min()) if len(r3) else float("nan")
        pk = np.maximum.accumulate(eq.to_numpy())
        under = eq.to_numpy() <= 0.5 * pk
        out["first_dd50"] = str(eq.index[np.argmax(under)].date()) if under.any() else None
        out["ruin_date"] = str(eq.index[np.argmax(eq.to_numpy() <= 0)].date()) if (eq.to_numpy() <= 0).any() else None
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    a = ap.parse_args()
    t0 = time.time()
    P.setup(a.root)
    M30 = pickle.loads((PMS.CACHE / "m30_sleeve6.pkl").read_bytes())
    M30 = M30[M30.mkt.isin(["XAUUSD", "XAGUSD", "BTCUSD", "ETHUSD", "USDJPY"])]
    H1 = pickle.loads((PMS.CACHE / "h1_sleeve6.pkl").read_bytes())
    H1 = H1[H1.mkt.isin(["XAUUSD", "XAGUSD", "BTCUSD", "ETHUSD", "USDJPY"])]
    G, K, C = P._M["G"], P._M["K"], P._M["C"]
    sys.path.insert(0, str(pathlib.Path(a.root) / "research" / "grid768"))
    import report768 as RP
    C.SPECS.update(NS.FM.specs(C))
    Hh = {m: (NS.MMS.load(m, G) if m in NS.MMS.MARKETS else NS.L3.load(m, "2009-01-01", END)) for m in NS.RF.STD}
    NS.RSD.START = START
    raw = [{k: v for k, v in r.items() if k != "X"} for r in NS.RSD.g27k_rows(NS.RF.STD, Hh, RP, G, K, K.externals()) if NS.W.ts(START) <= r["t"] < NS.W.ts(END)]
    gf = NS.apply(raw, NS.fed_shocks(a.root), Hh, True)
    out = {}
    for acct, ms in (("Cent", NS.RF.CENT), ("Standard", NS.RF.STD)):
        rows = [r for r in gf if r["mkt"] in ms]
        m30, h1 = M30[M30.mkt.isin(ms)], H1[H1.mkt.isin(ms)]
        F = lambda kg, km, kh: HS.frame(rows, [(m30, "_M30", km), (h1, "_H1", kh)], kg)
        grid = []
        for kg, km, kh in itertools.product(KG, KS, KS):
            r = run(F(kg, km, kh))
            grid.append(dict(kg=kg, km=km, kh=kh, **r))
        best = max(grid, key=lambda r: r["final"])
        print(f"  {acct}: grid of {len(grid)} done {time.time() - t0:.0f}s | best G27K-F {best['kg']}% M30 {best['km']}% H1 {best['kh']}%: "
              f"final x{best['final']:,.0f} CAGR {best['cagr']:+.0%} DD {best['dd']:.0%} worst month {best['worst_month']:+.0%} worst 3m {best['worst_3m']:+.0%}", flush=True)
        # the best single-book alternatives, for reference
        alt = {nm: max((g for g in grid if cond(g)), key=lambda r: r["final"]) for nm, cond in
               (("G27K-F only", lambda g: g["km"] == 0 and g["kh"] == 0), ("G27K-F + M30", lambda g: g["kh"] == 0))}
        scaled = []
        for lam in LAMBDA:
            kg, km, kh = best["kg"] * lam, best["km"] * lam, best["kh"] * lam
            r = dict(lam=lam, kg=kg, km=km, kh=kh, full=run(F(kg, km, kh)), h1=run(F(kg, km, kh), end=MID), h2=run(F(kg, km, kh), start=MID))
            scaled.append(r)
            f = r["full"]
            print(f"    x{lam:<4}: G {kg:5.2f}% M30 {km:5.2f}% H1 {kh:5.2f}% | final x{f['final']:,.3g} CAGR {f['cagr']:+.0%} DD {f['dd']:.0%} "
                  f"worst 3m {f.get('worst_3m', float('nan')):+.0%} first DD>50% {f.get('first_dd50')} ruin {f.get('ruin_date')} | "
                  f"2011-18 CAGR {r['h1']['cagr']:+.0%} DD {r['h1']['dd']:.0%} | 2019-26 CAGR {r['h2']['cagr']:+.0%} DD {r['h2']['dd']:.0%}", flush=True)
        out[acct] = dict(best=best, alt=alt, scaled=scaled, grid=grid)
    (HERE / "max_growth.json").write_text(json.dumps(out, indent=1, default=float))
    print(f"  done {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
