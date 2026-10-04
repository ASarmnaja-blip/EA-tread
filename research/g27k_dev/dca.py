#!/usr/bin/env python3
"""G27K systems A (gold) and B (gold + silver + BTC) with a monthly top-up.

The account starts with INITIAL and adds MONTHLY on the first trading day
of every month; risk per trade stays a fixed percent of the balance at
entry. Reported per start date: money in, final value, money-weighted
annual return (IRR), the worst drawdown of a unit-value series (contributions
do not mask losses) and the worst dollar fall from a peak. Benchmark: the same
deposits used to buy gold at the month's first price and hold.

Usage: python3 research/g27k_dev/dca.py --root <data-snapshot checkout>
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
import h4d1_pattern_search as P
import phase1 as PH
import walkforward_controller as W

INITIAL, MONTHLY = 100.0, 100.0
STARTS = [("2009-10-01", "ตั้งแต่ 2009 (17 ปี)"), ("2011-09-01", "เริ่มที่ยอดทองปี 2011 (15 ปี)"),
          ("2016-10-01", "10 ปีล่าสุด"), ("2021-10-01", "5 ปีล่าสุด")]
END = "2026-10-01"


def irr(flows, times, final, t_end):
    """Money-weighted annual return: deposits negative, final value positive."""
    yrs = (np.asarray(times) - t_end) / (365.25 * 86400)

    def npv(r):
        return np.sum(-np.asarray(flows) * (1 + r) ** (-yrs)) + final

    lo, hi = -0.99, 5.0
    for _ in range(200):
        mid = (lo + hi) / 2
        if npv(mid) > 0:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def run_dca(T, risk, start, end):
    s0, s1 = W.ts(start), W.ts(end)
    T = T[(T.t >= s0) & (T.t < s1)].sort_values("t")
    months = [W.ts(d) for d in pd.date_range(start, end, freq="MS", inclusive="left")]
    events = [(m, 0, "dep", None) for m in months] + [(r.t, 2, "in", r) for r in T.itertuples()]
    events.sort(key=lambda x: (x[0], x[1]))
    bal, units, nav = 0.0, 0.0, 1.0
    heap, flows, ftimes = [], [], []
    peak_nav, dd_nav, peak_bal, dd_usd = 1.0, 0.0, 0.0, 0.0
    curve = []

    def settle(t):
        nonlocal bal, nav, peak_nav, dd_nav, peak_bal, dd_usd
        while heap and heap[0][0] <= t:
            tx, k, pnl = heapq.heappop(heap)
            if bal > 0:
                nav *= (bal + pnl) / bal
            bal += pnl
            peak_nav = max(peak_nav, nav)
            dd_nav = max(dd_nav, 1 - nav / peak_nav)
            peak_bal = max(peak_bal, bal)
            dd_usd = max(dd_usd, peak_bal - bal)
            curve.append((tx, bal, nav, sum(flows)))

    for i, (t, pri, kind, r) in enumerate(events):
        settle(t)
        if kind == "dep":
            amt = INITIAL + MONTHLY if not flows else MONTHLY
            bal += amt
            flows.append(amt)
            ftimes.append(t)
            peak_bal = max(peak_bal, bal)
            curve.append((t, bal, nav, sum(flows)))
        else:
            heapq.heappush(heap, (r.tx, i, risk * bal * r.R))
    settle(2 ** 62)
    return dict(deposited=float(sum(flows)), final=float(bal), profit=float(bal - sum(flows)),
                irr=float(irr(flows, ftimes, bal, s1)), dd_unit=float(dd_nav), dd_usd=float(dd_usd)), curve


def gold_dca(h1, start, end):
    px = pd.Series(np.asarray(h1["c"], float), index=pd.to_datetime(np.asarray(h1["t"], np.int64), unit="s"))
    months = pd.date_range(start, end, freq="MS", inclusive="left")
    oz, flows, ftimes = 0.0, [], []
    for i, m in enumerate(months):
        p = px[px.index >= m].iloc[0]
        amt = INITIAL + MONTHLY if i == 0 else MONTHLY
        oz += amt / p
        flows.append(amt)
        ftimes.append(int(m.timestamp()))
    final = oz * px[px.index < pd.Timestamp(end)].iloc[-1]
    win = px[(px.index >= months[0]) & (px.index < pd.Timestamp(end))]
    bought = [f / px[px.index >= m].iloc[0] for f, m in zip(flows, months)]
    value = pd.Series(np.cumsum(bought), index=months).reindex(win.index, method="ffill") * win
    return dict(deposited=float(sum(flows)), final=float(final), profit=float(final - sum(flows)),
                irr=float(irr(flows, ftimes, final, W.ts(end))),
                dd_unit=float((1 - win / win.cummax()).max()),
                dd_usd=float((value.cummax() - value).max()))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    a = ap.parse_args()
    P.setup(a.root)
    G, K = P._M["G"], P._M["K"]
    ext = K.externals()
    H1 = {m: W.hybrid_h1(m, G) for m in K.MKTS}
    Ds = {m: PH.prep_market(m, H1[m], ext) for m in K.MKTS}
    out = []
    for start, label in STARTS:
        row = dict(start=start, label=label, gold_dca=gold_dca(H1["XAUUSD"], start, END))
        for name, sysname, risk in (("A 1%", "A", 0.01), ("B 0.5%", "B", 0.005), ("B 1%", "B", 0.01)):
            T = PH.system_trades(sysname, Ds, *PH.BASE, start=start)
            row[name], _ = run_dca(T, risk, start, END)
        out.append(row)
        g = row["gold_dca"]
        print(f"\n{label}: deposited ${g['deposited']:,.0f}")
        print(f"  {'DCA buy gold':10s} final ${g['final']:>10,.0f}  profit ${g['profit']:>+10,.0f}  IRR {g['irr']:+.1%}  "
              f"DD (unit) {g['dd_unit']:.1%}  worst $ fall ${g['dd_usd']:,.0f}")
        for name in ("A 1%", "B 0.5%", "B 1%"):
            r = row[name]
            print(f"  {name:10s} final ${r['final']:>10,.0f}  profit ${r['profit']:>+10,.0f}  IRR {r['irr']:+.1%}  "
                  f"DD (unit) {r['dd_unit']:.1%}  worst $ fall ${r['dd_usd']:,.0f}")
    (HERE / "dca.json").write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
