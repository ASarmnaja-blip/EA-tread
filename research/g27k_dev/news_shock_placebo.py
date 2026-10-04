#!/usr/bin/env python3
"""Placebo and neighbourhood checks for FED-EXIT / FED-BLOCK (news_shock.py).

Measure: MAR on the Standard account (scale-free). Placebo: 200 sets of random business days, as many as the real Fed shocks,
same timing (22:00 UTC next business day) and same actions. If random days
help as much, the gain is from trading less, not from the news. Neighbours:
shock threshold 1.5/2.5 sigma and block 3/10 days (informational).

Usage: python3 research/g27k_dev/news_shock_placebo.py --root <snap>
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

def edge(rows, base, news):
    """MAR (CAGR / max balance DD, full period, Standard): scale-free, so no same-DD search is needed."""
    f = NS.acct(rows, news)
    return f["cagr"] / f["dd"], f


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    a = ap.parse_args()
    P, RF, RSD, W, MMS, L3, FM = NS.P, NS.RF, NS.RSD, NS.W, NS.MMS, NS.L3, NS.FM
    P.setup(a.root)
    G, K, C = P._M["G"], P._M["K"], P._M["C"]
    sys.path.insert(0, str(pathlib.Path(a.root) / "research" / "grid768"))
    import report768 as RP
    C.SPECS.update(FM.specs(C))
    H1 = {m: (MMS.load(m, G) if m in MMS.MARKETS else L3.load(m, "2009-01-01", NS.END)) for m in RF.STD}
    RSD.START = NS.START
    news = W.news_times(a.root)
    rows = [{k: v for k, v in r.items() if k != "X"} for r in RSD.g27k_rows(RF.STD, H1, RP, G, K, K.externals()) if W.ts(NS.START) <= r["t"] < W.ts(NS.END)]
    real = NS.fed_shocks(a.root)
    real = real[(real >= W.ts(NS.START)) & (real < W.ts(NS.END))]
    res = {}
    for act, ex in (("EXIT", True), ("BLOCK", False)):
        e_real, f = edge(NS.apply(rows, real, H1, ex), rows, news)
        n_exit = sum(1 for r0, r1 in zip(rows, NS.apply(rows, real, H1, True)) if r0["t_exit"] != r1["t_exit"]) if ex else None
        bdays = pd.bdate_range(NS.START, NS.END)
        rng = np.random.default_rng(11)
        pl = []
        for i_ in range(200):
            d = np.sort(rng.choice(len(bdays), len(real), replace=False))
            s = np.array([int((bdays[i] + pd.offsets.BDay(1)).tz_localize("UTC").timestamp()) + 22 * 3600 for i in d])
            pl.append(edge(NS.apply(rows, s, H1, ex), rows, news)[0])
            if i_ % 50 == 49:
                print(f'    {act} placebo {i_ + 1}/200', flush=True)
        pl = np.array(pl)
        res[act] = dict(edge=e_real, cagr=f["cagr"], dd=f["dd"], placebo_mean=float(pl.mean()), placebo_p95=float(np.quantile(pl, 0.95)),
                        p_value=float((pl >= e_real).mean()), trades_cut_short=n_exit)
        print(f"  FED-{act}: MAR {e_real:.2f} (unchanged {edge(rows, rows, news)[0]:.2f}) | placebo MAR mean {pl.mean():.2f}, 95th pct {np.quantile(pl, 0.95):.2f}, "
              f"share of placebos >= real {res[act]['p_value']:.1%}" + (f" | trades closed early {n_exit}" if n_exit else ""), flush=True)
    # neighbourhood
    nb = {}
    for z in (1.5, 2.0, 2.5):
        for days in (3, 5, 10):
            NS.BLOCK_DAYS = days
            d = pd.read_csv(pathlib.Path(a.root) / "data" / "macro" / "fred" / "DGS2.csv")
            d = d[pd.to_numeric(d.DGS2, errors="coerce").notna()]
            v = pd.Series(d.DGS2.astype(float).to_numpy(), index=pd.to_datetime(d.observation_date))
            ch = v.diff()
            sd = ch.rolling(250, min_periods=120).std().shift(1)
            s = np.array(sorted(int(((t + pd.offsets.BDay(1)).tz_localize("UTC") + pd.Timedelta(hours=22)).timestamp()) for t in ch[ch >= z * sd].index))
            e, f = edge(NS.apply(rows, s, H1, True), rows, news)
            nb[f"z{z}_d{days}"] = dict(edge=e, cagr=f["cagr"], dd=f["dd"])
            print(f"  EXIT z {z} block {days}d: MAR {e:.2f}  CAGR {f['cagr']:+.1%} DD {f['dd']:.1%}", flush=True)
    NS.BLOCK_DAYS = 5
    (HERE / "news_shock_placebo.json").write_text(json.dumps(dict(standard=res, neighbours=nb), indent=1, default=float))


if __name__ == "__main__":
    main()
