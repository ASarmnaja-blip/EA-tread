#!/usr/bin/env python3
"""The same fine-grained pattern search, on gold M15, M30 and H1 bars.

Base data is real Dukascopy XAUUSD M1 bid/ask (mid prices). Inside-bar
anatomy and stop walking use the M1 bars, so a stop inside an M15 bar is
resolved minute by minute. Cost per round trip is the user's live spread
($0.26, Exness XAUUSDc) plus 1 bp of price for slippage, and the broker's
real long swap. Gold only - silver and BTC have no minute history here.

Discovery is the first part of the history and validation the rest, set by
--split; the identical search runs on drift-placebo M1 histories as the
selection-aware null, exactly as in h4d1_pattern_search.py.

Usage: python3 intraday_pattern_search.py --root <data-snapshot checkout>
         [--start 2019-01-01] [--split 2023-01-01] [--placebos 20] [--only-real]
"""
import argparse
import json
import pathlib
import sys
import time

import numpy as np
import pandas as pd

HERE = pathlib.Path(__file__).parent
sys.path.insert(0, str(HERE))
import fetch_dukascopy as DK
import h4d1_pattern_search as P

SPREAD_USD = 0.26
TFS = ("M15", "M30", "H1")


def load_m1(start):
    m = DK.load(start, None, verbose=False)
    m = m[(m.ask_close > m.bid_close) & (m.bid_high >= m.bid_low)]
    t = ((m.index - pd.Timestamp("1970-01-01", tz="UTC")) // pd.Timedelta("1s")).to_numpy(np.int64)
    mid = {k: ((m[f"bid_{k}"] + m[f"ask_{k}"]) / 2).to_numpy(float)
           for k in ("open", "high", "low", "close")}
    return dict(t=t, o=mid["open"], h=mid["high"], l=mid["low"], c=mid["close"],
                v=m["volume"].to_numpy(float), step=60)


def frames_minute(base, tf):
    G = P._M["G"]
    F = G.frames(base)
    sec = P.TF_SEC[tf]
    off = 22 * 3600 if tf == "H4" else 0
    X = G.agg(base, (base["t"] - off) // sec)
    return X, F["D1"], F["W1"], 86400, 7 * 86400


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    ap.add_argument("--start", default="2019-01-01")
    ap.add_argument("--split", default="2023-01-01")
    ap.add_argument("--placebos", type=int, default=20)
    ap.add_argument("--only-real", action="store_true")
    ap.add_argument("--out", default="intraday_pattern_search.json")
    a = ap.parse_args()
    t0 = time.time()
    P.setup(a.root)
    C = P._M["C"]
    base = load_m1(a.start)
    print(f"  gold M1: {len(base['t']):,} minutes from "
          f"{pd.Timestamp(int(base['t'][0]), unit='s').date()}", flush=True)
    P._M.update(h1={"XAUUSD": base}, frames_for=frames_minute, tfs=TFS,
                scopes=("XAUUSD",), FIRST=C.ts(a.start) + 60 * 86400,
                SPLIT=C.ts(a.split),
                cost_fn=lambda ep: SPREAD_USD + 1e-4 * ep)
    real = P.run_once(P._M["h1"], "real")
    out = dict(start=a.start, split=a.split, spread_usd=SPREAD_USD, real=real,
               placebos=[])
    path = HERE / a.out
    path.write_text(json.dumps(out, indent=1, default=str))
    if not a.only_real:
        for p in range(a.placebos):
            r = P.run_once(P.drift_placebo(p), f"drift{p}")
            out["placebos"].append({k: v for k, v in r.items() if k != "top"}
                                   | dict(top=r["top"][:10]))
            path.write_text(json.dumps(out, indent=1, default=str))
    P.report(out)
    path.write_text(json.dumps(out, indent=1, default=str))
    print(f"\n  elapsed {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
