#!/usr/bin/env python3
"""Lowest capital that still delivers the backtest, by replaying G27K #1 with
real Exness minimum orders (brake 25% version, 2011-09..2026-09).

Each trade's stop, as a share of its entry price, is applied to today's price
(last close in the data), so the minimum-order risk reflects current price
levels across 15 years of volatility. Lots are rounded down to the volume
step; a trade whose target risk is below one minimum order is skipped. The
account is in dollars from the chosen start, and the result is compared with
the same account without lot limits. Start years 2011..2023 test whether an
early drawdown on a small account pushes it below the minimum order.

Usage: python3 research/g27k_dev/capital_stat.py --root <snap>
"""
import argparse
import heapq
import json
import pathlib
import sys

import numpy as np
import pandas as pd

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))
import capital_need as CN
import walkforward_controller as W

END = "2026-10-01"
# volume step in instrument units (minimum order in CN.MIN_UNITS)
STEP = {"std": {"XAUUSD": 1.0, "XAGUSD": 50.0, "BTCUSD": 0.01, "ETHUSD": 0.01, "USDJPY": 1000.0, "JP225": 1.0},
        "cent": {"XAUUSD": 0.01, "XAGUSD": 0.5, "BTCUSD": 0.0001, "ETHUSD": 0.0001, "USDJPY": 10.0}}
CAPS = {"cent": [100, 150, 200, 300, 400, 500, 750, 1000, 1500, 2000, 3000],
        "std": [10_000, 15_000, 20_000, 30_000, 40_000, 50_000, 75_000, 100_000, 150_000, 200_000, 300_000]}


def run(T, acct, cap, crypto, start, limited=True):
    T = T[T.t >= W.ts(start)]
    bal, peak, dd, braked = float(cap), float(cap), 0.0, False
    heap, skipped, taken, under = [], 0, 0, []
    for i in range(len(T)):
        t = T.t.iat[i]
        while heap and heap[0][0] <= t:
            _, pnl = heapq.heappop(heap)
            bal += pnl
            peak = max(peak, bal)
            now = 1 - bal / peak
            dd = max(dd, now)
            braked = now >= 0.25 or (braked and now > 0.125)
        m = T.mkt.iat[i]
        r = (crypto if m in ("BTCUSD", "ETHUSD") else 0.01) * (0.5 if braked else 1.0)
        want = r * bal
        if limited:
            per_unit = T.usd_per_unit.iat[i]
            mn, st = CN.MIN_UNITS[acct][m], STEP[acct][m]
            units = np.floor(want / per_unit / st + 1e-9) * st
            if units < mn - 1e-12:
                skipped += 1
                continue
            risk = units * per_unit
            under.append(risk / want)
        else:
            risk = want
        taken += 1
        heapq.heappush(heap, (T.tx.iat[i], risk * T.R.iat[i]))
    while heap:
        bal += heapq.heappop(heap)[1]
        peak = max(peak, bal)
        dd = max(dd, 1 - bal / peak)
    yrs = (W.ts(END) - W.ts(start)) / (365.25 * 86400)
    cagr = (bal / cap) ** (1 / yrs) - 1 if bal > 0 else -1.0
    return dict(cagr=cagr, dd=dd, mar=cagr / dd if dd > 0 else np.nan, skip=skipped / max(1, skipped + taken),
                fill=float(np.mean(under)) if under else 1.0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    a = ap.parse_args()
    P = CN.P
    P.setup(a.root)
    G, K, C = P._M["G"], P._M["K"], P._M["C"]
    C.SPECS.update(CN.FM.specs(C))
    sys.path.insert(0, str(pathlib.Path(a.root) / "research" / "grid768"))
    import report768 as RP
    H1 = {m: (CN.MMS.load(m, G) if m in CN.MMS.MARKETS else CN.L3.load(m, "2009-01-01", END)) for m in CN.MKTS}
    CN.RSD.START = "2011-09-01"
    rows = [r for r in CN.RSD.g27k_rows(CN.MKTS, H1, RP, G, K, K.externals()) if W.ts("2011-09-01") <= r["t"] < W.ts(END)]
    last = {m: float(H1[m]["c"][-1]) for m in CN.MKTS}
    usd = {m: last[m] / last["USDJPY"] if m == "JP225" else (1.0 if m == "USDJPY" else last[m]) for m in CN.MKTS}
    T = pd.DataFrame(dict(mkt=[r["mkt"] for r in rows], t=[int(r["t"]) for r in rows], tx=[int(r["t_exit"]) for r in rows],
                          R=[r["R"] for r in rows], pct=[r["risk"] / r["ep"] for r in rows]))
    T["usd_per_unit"] = T.pct * T.mkt.map(usd)       # USD lost per unit at today's price if the stop is hit
    T = T.sort_values(["t", "mkt"], kind="mergesort").reset_index(drop=True)
    print("  today's price:", {m: round(v, 2) for m, v in last.items()})
    starts = ["2011-09-01"] + [f"{y}-01-01" for y in range(2012, 2024)]
    out = {}
    for acct, mk in (("cent", CN.MKTS[:5]), ("std", CN.MKTS)):
        Ta = T[T.mkt.isin(mk)]
        for crypto in (0.01, 0.005):
            key = f"{acct}_{'1' if crypto == 0.01 else 'half'}"
            ref = {s: run(Ta, acct, 1e9, crypto, s, limited=False) for s in starts}
            print(f"\n  {key}: unlimited 2011 start CAGR {ref[starts[0]]['cagr']:.1%} DD {ref[starts[0]]['dd']:.1%} MAR {ref[starts[0]]['mar']:.2f}")
            res = []
            for cap in CAPS[acct]:
                rs = {s: run(Ta, acct, cap, crypto, s) for s in starts}
                ratio = np.array([rs[s]["mar"] / ref[s]["mar"] for s in starts])
                gap = np.array([rs[s]["cagr"] - ref[s]["cagr"] for s in starts])
                skip = np.array([rs[s]["skip"] for s in starts])
                r0 = rs[starts[0]]
                row = dict(cap=cap, cagr=r0["cagr"], dd=r0["dd"], mar=r0["mar"], skip=r0["skip"], fill=r0["fill"],
                           mar_ratio_med=float(np.median(ratio)), mar_ratio_min=float(ratio.min()), cagr_gap_worst=float(gap.min()),
                           skip_max=float(skip.max()))
                res.append(row)
                print(f"    ${cap:>8,}  2011: CAGR {r0['cagr']:+6.1%} DD {r0['dd']:5.1%} MAR {r0['mar']:.2f} skip {r0['skip']:5.1%} lot fill {r0['fill']:.0%} | "
                      f"13 starts: MAR vs unlimited median {np.median(ratio):.0%} worst {ratio.min():.0%}  CAGR gap worst {gap.min():+.1%}  skip max {skip.max():.1%}")
            out[key] = dict(ref=ref[starts[0]], rows=res)
    (HERE / "capital_stat.json").write_text(json.dumps(out, indent=1, default=float))


if __name__ == "__main__":
    main()
