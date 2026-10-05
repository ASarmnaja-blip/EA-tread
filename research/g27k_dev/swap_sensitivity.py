#!/usr/bin/env python3
"""How much do the published results depend on the swap model?

The research charges swap as a fixed fraction of the position per night
(bp per night, taken from today's Exness swap points at today's price, see
research/bundle/broker_specs.py) in every year. Exness charges swap in
points per lot, which it resets from interest rates and price, so neither
"today's bp" nor "today's points" is history. Four cases on the hand-off
trades (handoff/trades_*.csv.gz):

  A  as published: today's bp in every year
  B  today's points in every year (the MT5 Strategy Tester's assumption,
     raised by the MT5 session): swap bp scaled by price today / entry price
  C  rate-linked: metals' swap follows the US 2-year yield (FRED DGS2) on
     the entry day, calibrated so the last month gives today's bp:
     bp_t = bp_today * (max(y_t, 0) + m) / (y_today + m), with the broker
     margin m solved from today's swap (per year = bp * 365);
     crypto, USDJPY and JP225 as A (crypto swap is a broker rate, not a
     rate differential; USDJPY long is 0 today and JP225 0)
  D  C for metals, B for crypto (crypto swap as today's points, as the
     tester charges it); the middle case

Accounts: G27K-F, G27K-F + M30 and G27K-F + M30 + H1 at 1% + brake (sleeves
0.5%), Cent and Standard, 2011-09..2026-09, same simulator as the reports.

Usage: python3 research/g27k_dev/swap_sensitivity.py --root <snap>
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
import news_shock as NS
import suite as SU
import walkforward_controller as W

START, END = "2011-09-01", "2026-10-01"
METALS = ("XAUUSD", "XAGUSD")
CRYPTO = ("BTCUSD", "ETHUSD")
COMBOS = {"F": ("F",), "F_M30": ("F", "M30"), "F_M30_H1": ("F", "M30", "H1")}


def load(root):
    T = {}
    for b in ("F", "M30", "H1"):
        x = pd.read_csv(HERE / "handoff" / f"trades_{b}.csv.gz")
        sec = lambda c: ((pd.to_datetime(c, utc=True) - pd.Timestamp("1970-01-01", tz="UTC")) // pd.Timedelta("1s")).astype(np.int64)
        x["t"] = sec(x.entry_time_utc)
        x["tx"] = sec(x.exit_time_utc)
        T[b] = x
    # price today = last close in the hand-off period, from the latest exits per market
    allx = pd.concat(T.values())
    now = allx.sort_values("tx").groupby("market").exit_price.last().to_dict()
    y = pd.read_csv(pathlib.Path(root) / "data" / "macro" / "fred" / "DGS2.csv")
    y = y[pd.to_numeric(y.DGS2, errors="coerce").notna()]
    y = pd.Series(y.DGS2.astype(float).to_numpy() / 100, index=pd.to_datetime(y.observation_date, utc=True)).sort_index()
    return T, now, y


def recost(T, now, y, case):
    out = {}
    y_today = float(y[y.index >= pd.Timestamp("2026-09-01", tz="UTC")].mean())
    for b, x in T.items():
        x = x.copy()
        f = np.ones(len(x))
        pts = x.market.map(now).to_numpy() / x.entry_price.to_numpy()
        if case == "B":
            f = pts
        elif case in ("C", "D"):
            if case == "D":
                k = x.market.isin(CRYPTO).to_numpy()
                f[k] = pts[k]
            ys = ((y.index - pd.Timestamp("1970-01-01", tz="UTC")) // pd.Timedelta("1s")).to_numpy(np.int64)
            j = np.searchsorted(ys, x.t.to_numpy(), side="right") - 1          # last published yield at or before the entry
            yt = np.where(j >= 0, y.to_numpy()[np.maximum(j, 0)], np.nan)
            for m in METALS:
                k = (x.market == m).to_numpy()
                if not k.any():
                    continue
                f[k] = (np.maximum(np.nan_to_num(yt[k], nan=y_today), 0) + MARGIN[m]) / (y_today + MARGIN[m])
        x["R"] = x.R + x.R_swap - x.R_swap * f            # swap is a cost: R = gross - spread - swap
        out[b] = x
    return out


def frame(T, combo, ms, kg):
    parts = []
    for b in combo:
        x = T[b][T[b].market.isin(ms)]
        k = kg if b == "F" else 0.5
        parts.append(pd.DataFrame(dict(mkt=x.market + ("" if b == "F" else "_" + b), t=x.t, tx=x.tx, R=x.R * k)))
    F = pd.concat(parts, ignore_index=True)
    return F.assign(vp=0.0, sc=F.t)


MARGIN = {}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    a = ap.parse_args()
    T, now, y = load(a.root)
    sys.path.insert(0, str(HERE))
    import h4d1_pattern_search as P
    P.setup(a.root)
    C = P._M["C"]
    C.SPECS.update(NS.FM.specs(C))
    y_today = float(y[y.index >= pd.Timestamp("2026-09-01", tz="UTC")].mean())
    for m in METALS:
        per_year = C.SPECS[m]["swap_long_bp"] / 1e4 * 365
        MARGIN[m] = max(per_year - y_today, 0.0)
        print(f"  {m}: swap long today {C.SPECS[m]['swap_long_bp']:.3f} bp/night = {per_year:.2%}/yr, US 2y today {y_today:.2%} -> broker margin {MARGIN[m]:.2%}/yr", flush=True)
    news = NS.W.news_times(a.root)
    res = {}
    for case in ("A", "B", "C", "D"):
        TT = recost(T, now, y, case)
        res[case] = {"R_per_trade": {b: float(TT[b].R.mean()) for b in TT}}
        print(f"  case {case}: R per trade " + "  ".join(f"{b} {TT[b].R.mean():+.3f}" for b in TT), flush=True)
        for acct, ms in (("Cent", NS.RF.CENT), ("Standard", NS.RF.STD)):
            for c, combo in COMBOS.items():
                st, eq, _ = SU.simulate(frame(TT, combo, ms, 1.0), "brake", START, END, news=news)
                a1, _, _ = SU.simulate(frame(TT, combo, ms, 1.0), "brake", START, "2019-01-01", news=news)
                a2, _, _ = SU.simulate(frame(TT, combo, ms, 1.0), "brake", "2019-01-01", END, news=news)
                res[case][f"{acct} {c}"] = dict(cagr=st["cagr"], dd=st["dd"], mar=st["mar"], mar_h1=a1["mar"], mar_h2=a2["mar"])
                r = res[case][f"{acct} {c}"]
                f2 = lambda v: "nan" if v is None else f"{v:+.2f}"
                print(f"    {acct:8s} {c:9s} CAGR {r['cagr']:+.1%} DD {r['dd']:.1%} MAR {f2(r['mar'])} | 2011-18 MAR {f2(r['mar_h1'])} 2019-26 {f2(r['mar_h2'])}", flush=True)
    yy = y.resample("YE").mean()
    res["us2y_by_year"] = {int(d.year): float(v) for d, v in yy.items() if d.year >= 2011}
    res["margin"] = MARGIN
    (HERE / "swap_sensitivity.json").write_text(json.dumps(res, indent=1, default=float))


if __name__ == "__main__":
    main()
