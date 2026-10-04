#!/usr/bin/env python3
"""M30 sleeve rule, unchanged, on three markets that played no part in
choosing it: ETHUSD, USDJPY, JP225 (ledger m30_sleeve_new_markets, part 1;
criterion fixed there).

Rule: M30, brk55 >= -1 ATR & atr_ratio >= 1.5 & htf1_with, both directions,
tp2 exit, non-overlapping per market, same cost model as G27K-F
(ETH = BTC spec; USDJPY and JP225 = the G27K spec).

Also writes every sleeve trade of all six markets to
.cache_wf/m30_sleeve6.pkl for the report and the robustness script.

Usage: python3 research/g27k_dev/m30_new_markets.py --root <snap>
"""
import argparse
import json
import pathlib
import pickle
import sys

import numpy as np
import pandas as pd

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))
import h4d1_pattern_search as P
import intraday_pattern_search as IP
import news_shock as NS
import per_market_search as PMS

OLD = ("XAUUSD", "XAGUSD", "BTCUSD")
NEW = ("ETHUSD", "USDJPY", "JP225")
ALL = OLD + NEW
DUKA = {"USDJPY": "USDJPY", "JP225": "JPNIDXJPY"}
START, MID, END = "2011-09-01", "2019-01-01", "2026-10-01"
OWN_MID = {"ETHUSD": "2022-03-01", "USDJPY": MID, "JP225": MID}
EX = "tp2"
CACHE_DUKA = HERE.parent / ".cache_duka"


def load_m1(sym):
    """Old markets exactly as before; ETH from Binance like BTC; USDJPY and
    JP225 from the cached Dukascopy years only (never triggers a download)."""
    if sym in OLD:
        return PMS.load_m1(sym)
    if sym == "ETHUSD":
        b = pd.read_parquet(CACHE_DUKA / "ETHUSD_binance_M1.parquet")
        b = b[(b.h > b.l) & (b.index < pd.Timestamp(END, tz="UTC"))]
        t = ((b.index - pd.Timestamp("1970-01-01", tz="UTC")) // pd.Timedelta("1s")).to_numpy(np.int64)
        return dict(t=t, o=b.o.to_numpy(float), h=b.h.to_numpy(float), l=b.l.to_numpy(float), c=b.c.to_numpy(float), v=b.v.to_numpy(float), step=60)
    parts = [pd.read_parquet(p) for p in sorted(CACHE_DUKA.glob(f"{DUKA[sym]}_M1_*.parquet"))]
    m = pd.concat(parts).sort_index()
    m = m[~m.index.duplicated()]
    m = m[(m.index < pd.Timestamp(END, tz="UTC")) & (m.ask_close > m.bid_close) & (m.bid_high > m.bid_low)]
    t = ((m.index - pd.Timestamp("1970-01-01", tz="UTC")) // pd.Timedelta("1s")).to_numpy(np.int64)
    mid = {k: ((m[f"bid_{k}"] + m[f"ask_{k}"]) / 2).to_numpy(float) for k in ("open", "high", "low", "close")}
    return dict(t=t, o=mid["open"], h=mid["high"], l=mid["low"], c=mid["close"], v=m["volume"].to_numpy(float), step=60)


def prepare(root, markets=ALL):
    """Setup, specs (ETH = BTC spec as in G27K-F), M1 histories, minute frames."""
    P.setup(root)
    C = P._M["C"]
    for m, s in NS.FM.specs(C).items():
        C.SPECS.setdefault(m, s)
    h1 = {m: load_m1(m) for m in markets}
    P._M["h1"] = h1
    P._M["frames_for"] = IP.frames_minute
    return h1


def rule_mask(E, feats, cats, brk=-1.0, atr=1.5, htf=True, ex=EX):
    m = np.isfinite(E[f"R_{ex}"]) & (feats["brk55"] >= brk) & (feats["atr_ratio"] >= atr)
    return m & cats["htf1_with"] if htf else m


def trades(E, k, ex=EX):
    sec = P.TF_SEC["M30"]
    g = E["d"][k] * (E[f"px_{ex}"][k] - E[f"ep_{ex}"][k]) / E[f"rk_{ex}"][k]
    T = pd.DataFrame(dict(mkt=E["mkt"][k], t=(E["t"][k] + sec).astype(np.int64), tx=E[f"tx_{ex}"][k].astype(np.int64),
                          R=E[f"R_{ex}"][k], gross=g, d=E["d"][k], i=k))
    return T.sort_values("t").reset_index(drop=True)


def tstat(x):
    x = np.asarray(x, float)
    return float(x.mean() / x.std(ddof=1) * np.sqrt(len(x))) if len(x) > 2 and x.std() > 0 else float("nan")


def summ(T):
    return dict(n=int(len(T)), net=float(T.R.mean()) if len(T) else float("nan"), t=tstat(T.R),
                gross=float(T.gross.mean()) if len(T) else float("nan"), cost=float((T.gross - T.R).mean()) if len(T) else float("nan"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    a = ap.parse_args()
    h1 = prepare(a.root)
    for m, b in h1.items():
        print(f"  {m}: {len(b['t']):,} minutes from {pd.Timestamp(int(b['t'][0]), unit='s').date()}", flush=True)
    E, feats, cats = P.build(h1, "M30")
    T = trades(E, P.no_overlap(E, rule_mask(E, feats, cats), EX))
    T = T[(T.t >= NS.W.ts(START)) & (T.t < NS.W.ts(END))].reset_index(drop=True)
    (PMS.CACHE / "m30_sleeve6.pkl").write_bytes(pickle.dumps(T))
    mid = NS.W.ts(MID)
    out = dict(markets={}, pooled_new={}, pooled_old={})
    for m in ALL:
        x = T[T.mkt == m]
        om = NS.W.ts(OWN_MID.get(m, MID))
        r = dict(all=summ(x), h1=summ(x[x.t < mid]), h2=summ(x[x.t >= mid]), own_h1=summ(x[x.t < om]), own_h2=summ(x[x.t >= om]),
                 years={int(y): float(v) for y, v in x.groupby(pd.to_datetime(x.t, unit="s").dt.year).R.mean().items()})
        out["markets"][m] = r
        print(f"  {m:7s} n {r['all']['n']:4d} net {r['all']['net']:+.3f} t {r['all']['t']:+.2f} gross {r['all']['gross']:+.3f} cost {r['all']['cost']:.3f} | "
              f"2011-18 {r['h1']['net']:+.3f} (n {r['h1']['n']}) 2019-26 {r['h2']['net']:+.3f} (n {r['h2']['n']}) | own halves {r['own_h1']['net']:+.3f} / {r['own_h2']['net']:+.3f}",
              flush=True)
    for nm, ms in (("pooled_new", NEW), ("pooled_old", OLD)):
        x = T[T.mkt.isin(ms)]
        out[nm] = dict(all=summ(x), h1=summ(x[x.t < mid]), h2=summ(x[x.t >= mid]))
        r = out[nm]
        print(f"  {nm}: n {r['all']['n']} net {r['all']['net']:+.3f} t {r['all']['t']:+.2f} | 2011-18 {r['h1']['net']:+.3f} 2019-26 {r['h2']['net']:+.3f}", flush=True)
    pn = out["pooled_new"]
    p_ok = bool(pn["all"]["net"] > 0 and pn["all"]["t"] >= 2.0 and pn["h1"]["net"] > 0 and pn["h2"]["net"] > 0)
    add = [m for m in NEW if p_ok and out["markets"][m]["all"]["net"] > 0 and out["markets"][m]["own_h1"]["net"] > 0 and out["markets"][m]["own_h2"]["net"] > 0]
    out.update(part1_pass=p_ok, added=add)
    print(f"  PART 1: pooled new markets {'PASS' if p_ok else 'FAIL'} -> markets added: {add or 'none'}")
    (HERE / "m30_new_markets.json").write_text(json.dumps(out, indent=1, default=float))


if __name__ == "__main__":
    main()
