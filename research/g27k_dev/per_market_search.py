#!/usr/bin/env python3
"""Free pattern search per market, combined into one portfolio (ledger id
per_market_free_search).

The h4d1_pattern_search engine (every H1, H4 and D1 bar a long and short
candidate, 1-3 conditions, five exits, one open trade per market) run with
four scopes: gold, silver and BTC each alone, and pooled. Discovery is
metals 2009-09..2017-12 and BTC 2021-01..2023-12; everything after is test.
PER-MARKET = each market's top-1 own pattern; SHARED = the top-1 pooled
pattern. Both are traded on the test period as one account at 1% per trade,
next to G27K #1 (system B). The same search on drift-placebo histories gives
the selection-aware null for each market's top-1.

Three stages, so the minute timeframes can run on their own data:
  --stage hourly   H1, H4, D1 from hybrid H1 bars
  --stage minute   M15, M30 from Dukascopy M1 bid/ask mid (gold, silver
                   2009-2026; BTC 2021-2026), flat minutes dropped
  --stage combine  each scope's top-1 across all five timeframes, the
                   test-period accounts and the placebo null
Costs are the broker specs used everywhere else (spread + 1 bp, swap).

Usage: python3 research/g27k_dev/per_market_search.py --root <data-snapshot checkout> --stage S [--placebos N]
"""
import argparse
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
import brake as BR
import fetch_dukascopy as DK
import h4d1_pattern_search as P
import intraday_pattern_search as IP
import phase1 as PH
import walkforward_controller as W

MKTS = ("XAUUSD", "XAGUSD", "BTCUSD")
SCOPES = ("XAUUSD", "XAGUSD", "BTCUSD", "pooled")
SPLITS = {"XAUUSD": "2018-01-01", "XAGUSD": "2018-01-01", "BTCUSD": "2024-01-01"}
TEST0, END = "2018-01-01", "2026-10-01"
KEEP = 10
CACHE = HERE.parent / ".cache_wf"
TFS = {"hourly": ("H1", "H4", "D1"), "minute": ("M15", "M30")}


def split_for(E):
    return np.select([E["mkt"] == m for m in MKTS], [W.ts(SPLITS[m]) for m in MKTS], W.ts(TEST0)).astype(np.int64)


def trades_of(E, Bm, c):
    """Non-overlapping test-period trades of one pattern: market, entry, exit, R."""
    ex = c["exit"]
    R = E[f"R_{ex}"]
    mask = np.isfinite(R) & (E["t"] >= _split(E))
    for q in c["conds"]:
        mask &= Bm[:, q]
    mask &= P.scope_mask(E, c["scope"])
    k = P.no_overlap(E, mask, ex)
    sec = P.TF_SEC[c["tf"]]
    return pd.DataFrame(dict(mkt=E["mkt"][k], t=E["t"][k] + sec, tx=E[f"tx_{ex}"][k], R=R[k]))


def _split(E):
    return P._M["SPLIT"]


def load_m1(sym):
    """Dukascopy M1 mid prices, same cleaning as intraday_pattern_search.
    BTC: Binance BTCUSDT spot 1m (Dukascopy throttles too hard through the
    session proxy); flat minutes dropped the same way."""
    if sym == "BTCUSD":
        b = pd.read_parquet(HERE.parent / ".cache_duka" / "BTCUSD_binance_M1.parquet")
        b = b[(b.h > b.l) & (b.index < pd.Timestamp(END, tz="UTC"))]
        t = ((b.index - pd.Timestamp("1970-01-01", tz="UTC")) // pd.Timedelta("1s")).to_numpy(np.int64)
        return dict(t=t, o=b.o.to_numpy(float), h=b.h.to_numpy(float), l=b.l.to_numpy(float), c=b.c.to_numpy(float),
                    v=b.v.to_numpy(float), step=60)
    m = DK.load("2009-01-01" if sym != "BTCUSD" else "2021-01-01", END, verbose=False, symbol=sym)
    m = m[(m.ask_close > m.bid_close) & (m.bid_high > m.bid_low)]
    t = ((m.index - pd.Timestamp("1970-01-01", tz="UTC")) // pd.Timedelta("1s")).to_numpy(np.int64)
    mid = {k: ((m[f"bid_{k}"] + m[f"ask_{k}"]) / 2).to_numpy(float) for k in ("open", "high", "low", "close")}
    return dict(t=t, o=mid["open"], h=mid["high"], l=mid["low"], c=mid["close"], v=m["volume"].to_numpy(float), step=60)


def run_search(h1s, label, tfs):
    t0 = time.time()
    best = {s: [] for s in SCOPES}
    store = {}
    total = 0
    for tf in tfs:
        E, feats, cats = P.build(h1s, tf)
        P._M["SPLIT"] = split_for(E)
        disc = E["t"] < P._M["SPLIT"]
        names, Bm = P.conditions(feats, cats, disc)
        cands, tot = P.search(tf, E, names, Bm, disc)
        total += tot
        for s in SCOPES:
            top = sorted([c for c in cands if c["scope"] == s], key=lambda c: -c["t_disc"])[:KEEP]
            for c in top:
                c.update(P.validate(E, Bm, names, c))
                c["trades"] = trades_of(E, Bm, c)
            best[s] += top
        store[tf] = None
        print(f"  [{label}] {tf}: {len(E['t']):,} events, {len(names)} conditions, {tot:,} patterns  "
              f"{time.time() - t0:.0f}s", flush=True)
        del E, feats, cats, Bm
    for s in SCOPES:
        best[s] = sorted(best[s], key=lambda c: -c["t_disc"])[:KEEP]
    return best, total


def account(T, start=TEST0, end=END):
    if len(T) == 0:
        return dict(n=0)
    st, eq = BR.account(T[["t", "tx", "R"]].assign(R=T.R.astype(float)), 0.01, None, start, end)
    R = T.R.to_numpy()
    st["pf"] = float(R[R > 0].sum() / -R[R <= 0].sum()) if (R <= 0).any() else float("inf")
    st["totR"] = float(R.sum())
    st["per_mkt"] = {m: dict(n=int((T.mkt == m).sum()), totR=float(T.R[T.mkt == m].sum())) for m in MKTS}
    yr = eq.resample("YE").last()
    st["yearly"] = {int(d.year): float(v) for d, v in (yr / yr.shift(1).fillna(1.0) - 1).items()}
    return st


def slim(c):
    return {k: v for k, v in c.items() if k != "trades"} | dict(n_test=len(c["trades"]))


def stage_search(a):
    global MKTS, SCOPES
    G = P._M["G"]
    if a.mkts:                                    # interim run on the markets whose data is complete
        MKTS = tuple(a.mkts.split(","))
        SCOPES = MKTS + (("pooled",) if len(MKTS) == 3 else ())
    P._M["scopes"] = SCOPES
    if a.stage == "hourly":
        P._M["h1"] = {m: W.hybrid_h1(m, G) for m in MKTS}
    else:
        P._M["h1"] = {m: load_m1(m) for m in MKTS}
        P._M["frames_for"] = IP.frames_minute
        for m, b in P._M["h1"].items():
            print(f"  {m} M1: {len(b['t']):,} minutes from {pd.Timestamp(int(b['t'][0]), unit='s').date()}", flush=True)
    tfs = TFS[a.stage]
    best, total = run_search(P._M["h1"], "real", tfs)
    res = dict(total=total, best=best, placebos=[])
    CACHE.mkdir(exist_ok=True)
    path = CACHE / f"pms_{a.stage}{a.tag}.pkl"
    path.write_bytes(pickle.dumps(res))
    for s in SCOPES:
        c = best[s][0]
        print(f"  {s:7s} {c['tf']} {c['exit']:5s} {' & '.join(c['names'])}  disc t {c['t_disc']:.2f} "
              f"test n {c['n_val']} R {c['R_val']:+.3f} t {c['t_val']:.2f}", flush=True)
    for p in range(a.placebos):
        pb, _ = run_search(P.drift_placebo(p), f"drift{p}", tfs)
        res["placebos"].append({s: [dict(tf=c["tf"], t_disc=c["t_disc"], R_val=c["R_val"], t_val=c["t_val"],
                                         n_val=c["n_val"]) for c in pb[s]] for s in SCOPES})
        path.write_bytes(pickle.dumps(res))
        print(f"  drift{p}: " + "  ".join(f"{s} R {pb[s][0]['R_val']:+.3f}" for s in SCOPES), flush=True)


def stage_combine(a):
    G, K = P._M["G"], P._M["K"]
    parts = [pickle.loads((CACHE / f"pms_{st}.pkl").read_bytes()) for st in ("hourly", "minute")
             if (CACHE / f"pms_{st}.pkl").exists()]
    total = sum(x["total"] for x in parts)
    best = {s: sorted([c for x in parts for c in x["best"][s]], key=lambda c: -c["t_disc"])[:KEEP] for s in SCOPES}
    pick = {s: best[s][0] for s in SCOPES}
    per_market = pd.concat([pick[m]["trades"] for m in MKTS], ignore_index=True)
    shared = pick["pooled"]["trades"]
    h1 = {m: W.hybrid_h1(m, G) for m in MKTS}
    Ds = {m: PH.prep_market(m, h1[m], K.externals()) for m in MKTS}
    g27k = PH.system_trades("B", Ds, *PH.BASE, start=TEST0)
    acc = {"per_market": account(per_market), "shared": account(shared), "g27k_B": account(g27k)}
    for m in MKTS:
        acc[f"only_{m}"] = account(pick[m]["trades"])
    nplac = min((len(x["placebos"]) for x in parts), default=0)
    null = []
    for p in range(nplac):
        null.append({s: max((c for x in parts for c in x["placebos"][p][s]), key=lambda c: c["t_disc"]) for s in SCOPES})
    out = dict(patterns=total, stages=[len(x["best"]) for x in parts], pick={s: slim(pick[s]) for s in SCOPES},
               top={s: [slim(c) for c in best[s]] for s in SCOPES}, accounts=acc, placebo_top1=null,
               trades={s: pick[s]["trades"].assign(t=lambda d: d.t.astype(int), tx=lambda d: d.tx.astype(int)).to_dict("list")
                       for s in SCOPES})
    (HERE / "per_market_search.json").write_text(json.dumps(out, indent=1, default=str))
    print(f"  {total:,} patterns searched")
    for s in SCOPES:
        c = pick[s]
        nl = [x[s]["R_val"] for x in null if np.isfinite(x[s]["R_val"])]
        pv = (1 + sum(v >= c["R_val"] for v in nl)) / (1 + len(nl)) if nl else float("nan")
        print(f"  {s:7s} {c['tf']} {c['exit']:5s} {' & '.join(c['names'])}")
        print(f"          discovery n {c['n_disc']} R {c['R_disc']:+.3f} t {c['t_disc']:.2f} | "
              f"test n {c['n_val']} R {c['R_val']:+.3f} t {c['t_val']:.2f} totR {c['totR_val']:+.1f} | placebo p {pv:.3f}")
    for k, s in acc.items():
        if s.get("n"):
            print(f"  {k:14s} n {s['n']:4d} CAGR {s['cagr']:+.1%} DD {s['dd']:.1%} MAR {s['mar']:.2f} PF {s['pf']:.2f} "
                  + " ".join(f"{m} {v['n']}/{v['totR']:+.0f}R" for m, v in s["per_mkt"].items()))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    ap.add_argument("--stage", choices=("hourly", "minute", "combine"), required=True)
    ap.add_argument("--placebos", type=int, default=0)
    ap.add_argument("--mkts", default="", help="comma list for an interim run, e.g. XAUUSD,BTCUSD")
    ap.add_argument("--tag", default="", help="suffix of the stage pickle, keeps interim runs apart")
    a = ap.parse_args()
    t0 = time.time()
    P.setup(a.root)
    if a.stage == "combine":
        stage_combine(a)
    else:
        stage_search(a)
    print(f"  elapsed {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
