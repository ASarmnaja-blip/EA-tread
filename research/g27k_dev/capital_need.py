#!/usr/bin/env python3
"""Capital needed for G27K #1 on Exness Cent (5 markets) and Standard (6),
from the broker minimum order and the real stop distance (2 x ATR20 H4) of
G27K #1 entries in the last 24 months of data.

    min-order risk (USD) = min volume x contract x stop distance (x FX to USD)

Exness specs (help centre, read 2026-10-04): Standard XAUUSD 100 oz, XAGUSD
5,000 oz, BTCUSD 1 BTC, USDJPY 100,000, all min 0.01 lot; ETHUSD 1 ETH min 0.1
lot; JP225 contract 1 min 3 lots (profit in JPY assumed). Cent: 1 cent lot =
0.01 standard lot, min 0.01 cent lot (ETHUSDc 0.1); BTCUSDc 0.01 BTC per lot.

Three capital levels per account, at the risk of each market (1%, crypto 1%
or 0.5%):
  floor   one minimum order equals the target risk (normal conditions)
  brake   still one minimum order after a 40% drawdown with the brake
          (risk halved), so the EA never has to skip a trade
  fine    the target risk is >= 10 minimum orders, lot rounding error <= 10%

Usage: python3 research/g27k_dev/capital_need.py --root <snap>
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
import fresh_markets as FM
import fresh_search_l3 as L3
import h4d1_pattern_search as P
import multi_market_search as MMS
import report_suite_detail as RSD
import walkforward_controller as W

MKTS = ("XAUUSD", "XAGUSD", "BTCUSD", "ETHUSD", "USDJPY", "JP225")
# smallest order in units of the instrument (oz, BTC, ETH, USD, index points x 1)
MIN_UNITS = {"std": {"XAUUSD": 1.0, "XAGUSD": 50.0, "BTCUSD": 0.01, "ETHUSD": 0.1, "USDJPY": 1000.0, "JP225": 3.0},
             "cent": {"XAUUSD": 0.01, "XAGUSD": 0.5, "BTCUSD": 0.0001, "ETHUSD": 0.001, "USDJPY": 10.0}}
SINCE = "2024-10-01"
DD, BRAKE, FINE = 0.40, 0.5, 10


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    a = ap.parse_args()
    P.setup(a.root)
    sys.path.insert(0, str(pathlib.Path(a.root) / "research" / "grid768"))
    import report768 as RP
    G, K, C = P._M["G"], P._M["K"], P._M["C"]
    C.SPECS.update(FM.specs(C))
    H1 = {m: (MMS.load(m, G) if m in MMS.MARKETS else L3.load(m, "2009-01-01", "2026-10-01")) for m in MKTS}
    RSD.START = "2011-09-01"
    rows = [r for r in RSD.g27k_rows(MKTS, H1, RP, G, K, K.externals()) if r["t"] >= W.ts(SINCE)]
    jpy = pd.Series(H1["USDJPY"]["c"], index=H1["USDJPY"]["t"])
    stop = {}
    for m in MKTS:
        x = [r for r in rows if r["mkt"] == m]
        usd_per_unit = []
        for r in x:
            fx = float(jpy.asof(r["t"])) if m in ("USDJPY", "JP225") else 1.0
            usd_per_unit.append(r["risk"] / fx)        # USD lost per unit of the instrument if the stop is hit
        u = np.array(usd_per_unit)
        stop[m] = dict(n=len(x), med=float(np.median(u)), p90=float(np.quantile(u, 0.9)), mx=float(u.max()),
                       pct=float(np.median([r["risk"] / r["ep"] for r in x])))
        print(f"  {m:7s} {len(x):3d} entries since {SINCE}: stop {stop[m]['pct']:.1%} of price, USD per unit median {stop[m]['med']:.4g} p90 {stop[m]['p90']:.4g}")
    out = dict(stop=stop, accounts={})
    for acct, mk in (("cent", MKTS[:5]), ("std", MKTS)):
        for crypto in (0.01, 0.005):
            key = f"{acct}_{'1' if crypto == 0.01 else 'half'}"
            res = {}
            for m in mk:
                risk = crypto if m in ("BTCUSD", "ETHUSD") else 0.01
                need = MIN_UNITS[acct][m] * stop[m]["p90"]                   # USD at risk for one minimum order, high-volatility case
                res[m] = dict(risk=risk, min_order_usd=need, floor=need / risk, brake=need / (risk * BRAKE * (1 - DD)),
                              fine=FINE * MIN_UNITS[acct][m] * stop[m]["med"] / risk)
            tot = {k: max(r[k] for r in res.values()) for k in ("floor", "brake", "fine")}
            tot["binding"] = {k: max(res, key=lambda m: res[m][k]) for k in ("floor", "brake", "fine")}
            out["accounts"][key] = dict(markets=res, need=tot)
            print(f"\n  {key}")
            for m, r in res.items():
                print(f"    {m:7s} risk {r['risk']:.1%}  min order risks ${r['min_order_usd']:,.2f}  floor ${r['floor']:,.0f}  brake ${r['brake']:,.0f}  fine ${r['fine']:,.0f}")
            print(f"    NEED floor ${tot['floor']:,.0f} ({tot['binding']['floor']})  brake ${tot['brake']:,.0f} ({tot['binding']['brake']})  "
                  f"fine ${tot['fine']:,.0f} ({tot['binding']['fine']})")
    (HERE / "capital_need.json").write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
