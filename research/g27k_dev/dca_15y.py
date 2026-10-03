#!/usr/bin/env python3
"""Monthly top-up of 100,000 (any currency unit) for 15 years into the final
system (G27K #1 on gold, silver, BTC, JP225; 1% with the 25% brake), against
the three-market system and buying gold every month.

History: deposits on the first day of each month, Oct 2011 .. Sep 2026.
Range: 15-year block-bootstrap of the system's monthly returns (1% base,
the brake applied on each path's own unit-value drawdown, deposits added).

Usage: python3 research/g27k_dev/dca_15y.py --root <data-snapshot checkout>
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
import dca as DC
import h4d1_pattern_search as P
import multi_market_search as MMS
import suite as SU
import walkforward_controller as W

MONTHLY = 100_000.0
START, END = "2011-10-01", "2026-10-01"
M4 = ("XAUUSD", "XAGUSD", "BTCUSD", "JP225")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    a = ap.parse_args()
    P.setup(a.root)
    G, K = P._M["G"], P._M["K"]
    sys.path.insert(0, str(pathlib.Path(a.root) / "research" / "grid768"))
    import report768 as RP
    DC.INITIAL, DC.MONTHLY = 0.0, MONTHLY
    H1 = {m: MMS.load(m, G) for m in M4}
    news = W.news_times(a.root)
    g = SU.g27k_trades(M4, H1, RP, G, K, K.externals())
    systems = {"4 ตลาด เบรก 25%": (g, "brake"), "4 ตลาด ปกติ 1%": (g, "normal"), "4 ตลาด AI monitor": (g, "monitor"),
               "3 ตลาด เบรก 25%": (g[g.mkt.isin(SU.TARGET)], "brake")}
    res = {}
    for name, (T, v) in systems.items():
        st, _, _ = SU.simulate(T, v, START, END, news=news, deposits=True)
        res[name] = dict(final=st["final"], deposited=st["deposited"], irr=st["irr"], dd_unit=st["dd"])
        print(f"  {name:18s} ใส่ {st['deposited']:,.0f} ได้ {st['final']:,.0f}  IRR {st['irr']:.1%}  DD หน่วยลงทุน {st['dd']:.0%}", flush=True)
    gd = DC.gold_dca(H1["XAUUSD"], START, END)
    res["ซื้อทองเก็บทุกเดือน"] = dict(final=gd["final"], deposited=gd["deposited"], irr=gd["irr"], dd_unit=gd["dd_unit"])
    print(f"  ซื้อทองเก็บ        ใส่ {gd['deposited']:,.0f} ได้ {gd['final']:,.0f}  IRR {gd['irr']:.1%}  DD {gd['dd_unit']:.0%}")
    # year-end path of the main system
    T, v = systems["4 ตลาด เบรก 25%"]
    path = []
    for y in range(2012, 2027):
        e = f"{y + 1}-01-01" if y < 2026 else END
        st, _, _ = SU.simulate(T, v, START, e, news=news, deposits=True)
        path.append(dict(year=y, deposited=st["deposited"], value=st["final"]))
    res["path"] = path
    for p in path:
        print(f"    สิ้นปี {p['year']}: ใส่สะสม {p['deposited']:>12,.0f}  มูลค่า {p['value']:>14,.0f}  ({p['value'] / p['deposited'] - 1:+.0%})")
    # range of outcomes: 15-year paths from the system's monthly returns at 1%, brake on each path
    _, eq, _ = SU.simulate(T, "normal", START, END, news=news)
    x = pd.concat([pd.Series([1.0], index=[pd.Timestamp(START)]), eq]).groupby(level=0).last().resample("ME").last().ffill().pct_change().dropna().to_numpy()
    rng = np.random.default_rng(7)
    runs, months, block = 10000, 180, 6
    fin, worst_gap = np.empty(runs), np.empty(runs)
    for k in range(runs):
        path_r = np.concatenate([x[s:s + block] for s in rng.integers(0, len(x) - block, math.ceil(months / block))])[:months]
        bal, nav, pk, mult, dep, gap = 0.0, 1.0, 1.0, 1.0, 0.0, 0.0
        for r in path_r:
            bal += MONTHLY
            dep += MONTHLY
            now = 1 - nav / pk
            mult = 0.5 if (mult == 1.0 and now >= 0.25) else 1.0 if (mult < 1.0 and now <= 0.125) else mult
            bal *= 1 + r * mult
            nav *= 1 + r * mult
            pk = max(pk, nav)
            gap = max(gap, (dep - bal) / dep)
        fin[k], worst_gap[k] = bal, gap
    dep = MONTHLY * months
    res["range_15y"] = dict(deposited=dep, p5=float(np.quantile(fin, .05)), p25=float(np.quantile(fin, .25)), p50=float(np.median(fin)),
                            p75=float(np.quantile(fin, .75)), p95=float(np.quantile(fin, .95)), p_below_deposits=float((fin < dep).mean()),
                            p_ever_below_deposits_20pct=float((worst_gap > 0.2).mean()))
    print("  ช่วงผลลัพธ์ 15 ปี (สุ่ม 10,000 รอบ):", json.dumps({k: round(v) if v > 1 else round(v, 3) for k, v in res["range_15y"].items()}))
    (HERE / "dca_15y.json").write_text(json.dumps(res, indent=1, ensure_ascii=False, default=float))


if __name__ == "__main__":
    main()
