#!/usr/bin/env python3
"""Risk per trade for a drawdown target: worst acceptable 40%, aim 35%.

G27K #1, brake 25%, BTC/ETH at half the base risk, Cent 5 / Standard 6,
2011-09..2026-09. For each base risk: historical equity DD (open trades
marked, as MT5 shows), balance DD, CAGR, and a 10-year block bootstrap of
monthly returns (P(DD>35%), P(DD>40%), 95th percentile DD), also with every
trade 0.10R worse. Pick: the largest base risk with historical equity DD
<= 35%, bootstrap P(DD>40%) <= 5%, and balance DD <= 40% at -0.10R.

Usage: python3 research/g27k_dev/dd_target.py --root <snap> [--start 2020-10-01]
"""
import argparse
import json
import math
import pathlib
import sys

import numpy as np
import pandas as pd

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))
import fresh_markets as FM
import fresh_search_l3 as L3
import h4d1_pattern_search as P
import multi_market_search as MMS
import report_final6 as RF
import report_suite_detail as RSD
import report_walkforward10y as RWF
import suite as SU
import walkforward_controller as W

START, END = "2011-09-01", "2026-10-01"
KS = [round(x, 2) for x in np.arange(0.50, 2.01, 0.05)]


def boot(eq, runs=4000, years=10, block=6, seed=7):
    me = eq.resample("ME").last().ffill()
    x = me.pct_change().dropna().to_numpy()
    rng = np.random.default_rng(seed)
    nb = math.ceil(years * 12 / block)
    dds = np.empty(runs)
    for k in range(runs):
        path = np.concatenate([x[s:s + block] for s in rng.integers(0, len(x) - block, nb)])[: years * 12]
        v = np.cumprod(1 + path)
        dds[k] = np.max(1 - v / np.maximum.accumulate(np.r_[1.0, v])[1:])
    return dict(p35=float((dds > 0.35).mean()), p40=float((dds > 0.40).mean()), p50=float((dds > 0.5).mean()), q95=float(np.quantile(dds, 0.95)))


def main():
    global START
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    ap.add_argument("--start", default=START)
    a = ap.parse_args()
    START = RF.START = a.start
    P.setup(a.root)
    G, K, C = P._M["G"], P._M["K"], P._M["C"]
    sys.path.insert(0, str(pathlib.Path(a.root) / "research" / "grid768"))
    import report768 as RP
    C.SPECS.update(FM.specs(C))
    H1 = {m: (MMS.load(m, G) if m in MMS.MARKETS else L3.load(m, "2009-01-01", END)) for m in RF.STD}
    RSD.START = START
    G.START = W.ts(START)
    news = W.news_times(a.root)
    rows = [r for r in RSD.g27k_rows(RF.STD, H1, RP, G, K, K.externals()) if W.ts(START) <= r["t"] < W.ts(END)]
    out = {}
    for acct, ms in (("Cent", RF.CENT), ("Standard", RF.STD)):
        rr = [r for r in rows if r["mkt"] in ms]
        RWF.UNIS["P" + acct] = list(ms)
        res = []
        for k in KS:
            scale = {m: k * (0.5 if m in ("BTCUSD", "ETHUSD") else 1.0) for m in ms}
            st, eq, _ = SU.simulate(RF.frame(rr, scale), "brake", START, END, news=news)
            s2, eq2, _ = SU.simulate(RF.frame(rr, scale, 0.10), "brake", START, END, news=news)
            vr = RF.sized(rr, "brake", news, scale)
            ent = RWF.build_entry(f"k{k}", "P" + acct, vr, 0.01, None, RP, G)
            b, b2 = boot(eq), boot(eq2)
            y = eq.resample("YE").last()
            res.append(dict(k=k, cagr=st["cagr"], bal_dd=st["dd"], eq_dd=ent["equity_dd"]["relative_pct"], worst_year=float((y / y.shift(1).fillna(1.0) - 1).min()),
                            boot=b, stress=dict(cagr=s2["cagr"], dd=s2["dd"], **{f"b_{x}": v for x, v in b2.items()})))
            r = res[-1]
            print(f"  {acct:8s} base {k:.2f}% crypto {k / 2:.3f}%: CAGR {r['cagr']:+.1%} eqDD {r['eq_dd']:.1%} balDD {r['bal_dd']:.1%} worst yr {r['worst_year']:+.0%} | "
                  f"boot P>35 {b['p35']:.1%} P>40 {b['p40']:.1%} q95 {b['q95']:.1%} | -0.10R: CAGR {s2['cagr']:+.1%} DD {s2['dd']:.1%} P>40 {b2['p40']:.1%}", flush=True)
        ok = [r for r in res if r["eq_dd"] <= 0.35 and r["boot"]["p40"] <= 0.05 and r["stress"]["dd"] <= 0.40]
        pick = max(ok, key=lambda r: r["k"]) if ok else None
        out[acct] = dict(rows=res, pick=pick["k"] if pick else None)
        print(f"  {acct} pick: base {pick['k'] if pick else None}%")
    (HERE / ("dd_target.json" if START == "2011-09-01" else f"dd_target_{START[:7]}.json")).write_text(json.dumps(out, indent=1, default=float))


if __name__ == "__main__":
    main()
