#!/usr/bin/env python3
"""G27K #1 on four market sets (ledger g27k_usdjpy_and_five_markets):

  S3   gold, silver, BTC
  S4J  S3 + JP225            (the current final system; JP225 is not on Exness Standard Cent)
  S4U  S3 + USDJPY           (every market exists on Standard Cent)
  S5   S3 + JP225 + USDJPY

Each in normal 1%, brake 25% and AI monitor sizing, 2011-09..2026-10 (S3 and
S4U also from 2009-09), both halves, a 10-year Monte Carlo, USDJPY on its
own, and the monthly R correlation of each added market with S3.

Usage: python3 research/g27k_dev/five_markets.py --root <data-snapshot checkout>
"""
import argparse
import json
import pathlib
import sys

import numpy as np
import pandas as pd

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))
import h4d1_pattern_search as P
import multi_market_search as MMS
import suite as SU
import walkforward_controller as W

M3 = ("XAUUSD", "XAGUSD", "BTCUSD")
SETS = {"S3": M3, "S4J": M3 + ("JP225",), "S4U": M3 + ("USDJPY",), "S5": M3 + ("JP225", "USDJPY")}
START, START17, MID, END = "2011-09-01", "2009-09-01", "2019-01-01", "2026-10-01"
VERS = ("brake", "normal", "monitor")


def tstat(x):
    x = np.asarray(x, float)
    return float(x.mean() / x.std(ddof=1) * np.sqrt(len(x))) if len(x) > 2 else float("nan")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    a = ap.parse_args()
    P.setup(a.root)
    G, K = P._M["G"], P._M["K"]
    sys.path.insert(0, str(pathlib.Path(a.root) / "research" / "grid768"))
    import report768 as RP
    allm = M3 + ("JP225", "USDJPY")
    H1 = {m: MMS.load(m, G) for m in allm}
    news = W.news_times(a.root)
    T = SU.g27k_trades(allm, H1, RP, G, K, K.externals())
    res = {"per_market": {}, "sets": {}, "corr_with_S3": {}}
    for m in allm:
        x = T[(T.mkt == m) & (T.t >= W.ts(START))]
        h1, h2 = x[x.t < W.ts(MID)], x[x.t >= W.ts(MID)]
        res["per_market"][m] = dict(n=len(x), mean=float(x.R.mean()), t=tstat(x.R), win=float((x.R > 0).mean()),
                                    mean_h1=float(h1.R.mean()), mean_h2=float(h2.R.mean()), n_h1=len(h1), n_h2=len(h2))
        print(f"  {m:7s} n {len(x):4d}  mean {x.R.mean():+.3f}R  t {tstat(x.R):+.2f}  win {(x.R > 0).mean():.0%}  "
              f"halves {h1.R.mean():+.3f} / {h2.R.mean():+.3f}", flush=True)
    mon = lambda d: pd.Series(d.R.to_numpy(), index=pd.to_datetime(d.tx, unit="s")).resample("ME").sum()
    base = mon(T[T.mkt.isin(M3) & (T.t >= W.ts(START))])
    for m in ("JP225", "USDJPY"):
        c = mon(T[(T.mkt == m) & (T.t >= W.ts(START))])
        idx = base.index.union(c.index)
        res["corr_with_S3"][m] = float(np.corrcoef(base.reindex(idx, fill_value=0), c.reindex(idx, fill_value=0))[0, 1])
    c1, c2 = (mon(T[(T.mkt == m) & (T.t >= W.ts(START))]) for m in ("JP225", "USDJPY"))
    idx = c1.index.union(c2.index)
    res["corr_JP225_USDJPY"] = float(np.corrcoef(c1.reindex(idx, fill_value=0), c2.reindex(idx, fill_value=0))[0, 1])
    print("  monthly R correlation with S3", {k: round(v, 2) for k, v in res["corr_with_S3"].items()},
          "JP225~USDJPY", round(res["corr_JP225_USDJPY"], 2))

    for s, mk in SETS.items():
        TT = T[T.mkt.isin(mk)]
        r = {}
        for v in VERS:
            st, eq, risk = SU.simulate(TT, v, START, END, news=news)
            a1, _, _ = SU.simulate(TT, v, START, MID, news=news)
            a2, _, _ = SU.simulate(TT, v, MID, END, news=news)
            st.update(mar_h1=a1["mar"], mar_h2=a2["mar"], cagr_h1=a1["cagr"], cagr_h2=a2["cagr"], dd_h1=a1["dd"], dd_h2=a2["dd"])
            if v in ("brake", "normal"):
                st["mc"] = SU.monte_carlo(eq)
            # peak simultaneous open risk at entry
            tk = TT.loc[risk.index[risk.values > 0]]
            evs = sorted([(t, 1) for t in tk.t] + [(t, -1) for t in tk.tx])
            cur = mx = 0
            for _, k in evs:
                cur += k
                mx = max(mx, cur)
            st["max_open"] = mx
            r[v] = st
            mc = st.get("mc") or {}
            print(f"  {s:4s} {v:7s} CAGR {st['cagr']:+6.1%}  DD {st['dd']:5.1%}  MAR {st['mar']:.2f}  "
                  f"halves MAR {a1['mar']:.2f}/{a2['mar']:.2f}  worst yr {st['worst_year']:+.0%} ({st['worst_year_at']})  "
                  f"n {st['n']}  max open {mx}" + (f"  MC P(DD>50%) {mc.get('p_dd50', float('nan')):.1%}" if mc else ""), flush=True)
        if s in ("S3", "S4U"):
            st, _, _ = SU.simulate(TT, "brake", START17, END, news=news)
            r["brake_from_2009"] = st
            print(f"  {s:4s} brake from 2009: CAGR {st['cagr']:+.1%} DD {st['dd']:.1%} MAR {st['mar']:.2f}")
        res["sets"][s] = r
    b = {s: res["sets"][s]["brake"] for s in SETS}
    res["flags"] = {
        "usdjpy_positive_both_halves": res["per_market"]["USDJPY"]["mean_h1"] > 0 and res["per_market"]["USDJPY"]["mean_h2"] > 0,
        "S4U_mar_ge_S3_both_halves": b["S4U"]["mar_h1"] >= b["S3"]["mar_h1"] and b["S4U"]["mar_h2"] >= b["S3"]["mar_h2"],
        "S5_mar_ge_S4J_both_halves": b["S5"]["mar_h1"] >= b["S4J"]["mar_h1"] and b["S5"]["mar_h2"] >= b["S4J"]["mar_h2"],
        "mc_p_dd50_le_5pct": {s: (b[s]["mc"] or {}).get("p_dd50", 1) <= 0.05 for s in SETS},
    }
    print("  flags", json.dumps(res["flags"]))
    (HERE / "five_markets.json").write_text(json.dumps(res, indent=1, default=float))


if __name__ == "__main__":
    main()
