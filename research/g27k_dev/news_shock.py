#!/usr/bin/env python3
"""Fast news-shock rules for G27K #1 (ledger g27k_fast_news_shock; criterion
fixed there). Hawkish news shows up within hours as a dollar jump or a jump
in the 2-year Treasury yield; on such a shock the gold/silver/crypto legs
stop new entries for 5 days (BLOCK) or also close open trades (EXIT).

Usage: python3 research/g27k_dev/news_shock.py --root <snap>
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
import report_final6 as RF
import report_suite_detail as RSD
import suite as SU
import walkforward_controller as W

START, MID, END = "2011-09-01", "2019-01-01", "2026-10-01"
HIT = ("XAUUSD", "XAGUSD", "BTCUSD", "ETHUSD")
DXY = {"EURUSD": -0.576, "USDJPY": 0.136, "GBPUSD": -0.119, "USDCAD": 0.091, "USDSEK": 0.042, "USDCHF": 0.036}
BLOCK_DAYS = 5
SCALE = {"BTCUSD": 0.375, "ETHUSD": 0.375}


def dollar_shocks():
    s = None
    for m, w in DXY.items():
        c = pd.read_parquet(MMS.CACHE / f"{m}_H1BID.parquet").c
        c = c[~c.index.duplicated()]
        x = w * np.log(c)
        s = x if s is None else s.add(x, fill_value=np.nan)
    s = s.dropna().sort_index()
    s = s.resample("1h").last().ffill()
    ch = s - s.shift(24)
    sd = ch.rolling(250 * 24, min_periods=120 * 24).std().shift(1)
    shock = ch[(ch >= 2 * sd)]
    return np.array(sorted({int(t.timestamp()) for t in shock.index}))


def fed_shocks(root):
    d = pd.read_csv(pathlib.Path(root) / "data" / "macro" / "fred" / "DGS2.csv")
    d = d[pd.to_numeric(d.DGS2, errors="coerce").notna()]
    v = pd.Series(d.DGS2.astype(float).to_numpy(), index=pd.to_datetime(d.observation_date))
    ch = v.diff()
    sd = ch.rolling(250, min_periods=120).std().shift(1)
    days = ch[ch >= 2 * sd].index
    # H.15 posts day d's yields at ~16:15 ET on the next business day; usable from 22:00 UTC that day (no weekend/holiday look-ahead)
    pub = [(t + pd.offsets.BDay(1)).tz_localize("UTC") + pd.Timedelta(hours=22) for t in days]
    return np.array(sorted(int(x.timestamp()) for x in pub))


def apply(rows, shocks, H1, exit_open):
    out = []
    for r in rows:
        r = dict(r)
        if r["mkt"] in HIT:
            j = np.searchsorted(shocks, r["t"], side="right") - 1
            if j >= 0 and r["t"] - shocks[j] < BLOCK_DAYS * 86400:
                continue
            if exit_open:
                k = np.searchsorted(shocks, r["t"], side="right")
                if k < len(shocks) and shocks[k] < r["t_exit"]:
                    b = H1[r["mkt"]]
                    i = np.searchsorted(b["t"], shocks[k] + 3600)       # open of the bar after the shock hour
                    if i < len(b["t"]) and b["t"][i] < r["t_exit"]:
                        held = (b["t"][i] - r["t"]) / max(1, r["t_exit"] - r["t"])
                        r["R"] = (b["o"][i] - r["ep"]) / r["risk"] - r.get("R_spread", 0.0) - r.get("R_swap", 0.0) * held
                        r["t_exit"] = int(b["t"][i])
        out.append(r)
    return out


def frame(rows, k=1.0, extra=0.0):
    return pd.DataFrame(dict(mkt=[r["mkt"] for r in rows], t=[r["t"] for r in rows], tx=[r["t_exit"] for r in rows],
                             R=[(r["R"] - extra) * 0.75 * k * (0.5 if r["mkt"] in SCALE else 1.0) for r in rows], vp=0.0, sc=[r["t"] for r in rows]))


def acct(rows, news, k=1.0, extra=0.0, start=START, end=END):
    st, _, _ = SU.simulate(frame(rows, k, extra), "brake", start, end, news=news)
    return dict(cagr=st["cagr"], dd=st["dd"], n=st["n"])


def same_dd(rows, news, dd, extra=0.0):
    lo, hi = 0.05, 2.5
    for _ in range(36):
        k = (lo + hi) / 2
        if acct(rows, news, k, extra)["dd"] > dd:
            hi = k
        else:
            lo = k
    return lo


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    a = ap.parse_args()
    P.setup(a.root)
    G, K, C = P._M["G"], P._M["K"], P._M["C"]
    sys.path.insert(0, str(pathlib.Path(a.root) / "research" / "grid768"))
    import report768 as RP
    C.SPECS.update(FM.specs(C))
    H1 = {m: (MMS.load(m, G) if m in MMS.MARKETS else L3.load(m, "2009-01-01", END)) for m in RF.STD}
    RSD.START = START
    news = W.news_times(a.root)
    rows = [r for r in RSD.g27k_rows(RF.STD, H1, RP, G, K, K.externals()) if W.ts(START) <= r["t"] < W.ts(END)]
    rows = [{k: v for k, v in r.items() if k != "X"} for r in rows]
    shocks = {"DOLLAR": dollar_shocks(), "FED": fed_shocks(a.root)}
    for nm, s in shocks.items():
        s2 = s[(s >= W.ts(START)) & (s < W.ts(END))]
        days = len({x // 86400 for x in s2})
        print(f"  {nm} shocks 2011-2026: {len(s2)} hours on {days} days")
    variants = {"unchanged": rows}
    for nm, s in shocks.items():
        variants[f"{nm}-BLOCK"] = apply(rows, s, H1, False)
        variants[f"{nm}-EXIT"] = apply(rows, s, H1, True)
    out = {}
    for acct_nm, ms in (("Cent", RF.CENT), ("Standard", RF.STD)):
        out[acct_nm] = {}
        print(f"\n  {acct_nm}")
        base_dd = None
        for vn, rr in variants.items():
            rr = [r for r in rr if r["mkt"] in ms]
            full, h1, h2, st = acct(rr, news), acct(rr, news, end=MID), acct(rr, news, start=MID), acct(rr, news, extra=0.10)
            base = [r for r in variants["unchanged"] if r["mkt"] in ms]
            k = same_dd(base, news, full["dd"])
            p, p1, p2 = acct(base, news, k), acct(base, news, k, end=MID), acct(base, news, k, start=MID)
            ks = same_dd(base, news, st["dd"], 0.10)
            pst = acct(base, news, ks, 0.10)
            if vn == "unchanged":
                base_dd = full["dd"]
            ok = None if vn == "unchanged" else bool(full["cagr"] > p["cagr"] and h1["cagr"] > p1["cagr"] and h2["cagr"] > p2["cagr"]
                                                      and st["cagr"] > pst["cagr"] and full["dd"] <= base_dd + 1e-9)
            out[acct_nm][vn] = dict(full=full, h1=h1, h2=h2, stress=st, plain=dict(k=k, full=p, h1=p1, h2=p2, stress=pst), pass_=ok)
            print(f"    {vn:14s} trades {full['n']:4d} CAGR {full['cagr']:+6.1%} DD {full['dd']:5.1%} | 2011-18 {h1['cagr']:+.1%} 2019-26 {h2['cagr']:+.1%} | "
                  f"-0.10R {st['cagr']:+.1%} DD {st['dd']:.1%} || same-DD plain x{k:.2f}: {p['cagr']:+.1%} ({p1['cagr']:+.1%}/{p2['cagr']:+.1%}) "
                  f"-0.10R {pst['cagr']:+.1%}" + ("" if ok is None else f"  -> {'PASS' if ok else 'FAIL'}"), flush=True)
    (HERE / "news_shock.json").write_text(json.dumps(out, indent=1, default=float))


if __name__ == "__main__":
    main()
