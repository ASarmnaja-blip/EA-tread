"""P16 (docs/plans/P16_LONG_HISTORY_TREND_VS_HOLD.md): trend following vs holding on 14 FRED daily close series (1949-2026). Close-only bars
(open = previous close, high = max(open, close), low = min(open, close)); costs 2 bp (FX, indices) / 3 bp (oil, gas); no swap or carry.
Tests 1-3 of docs/TREND_VS_HOLD_PREREG.md plus a per-decade read. Usage: python research/setups/p16_long_history.py"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path[:0] = [str(ROOT / "research" / "bundle")]
import common as C  # noqa: E402
import z1_trend_vs_hold as Z  # noqa: E402

L = C.L
SRC = ROOT / "data" / "macro" / "fred_long"
OUT = ROOT / "data" / "setups"; OUT.mkdir(parents=True, exist_ok=True)
SERIES = {"NIKKEI225": 2.0, "NASDAQCOM": 2.0, "DEXJPUS": 2.0, "DEXUSUK": 2.0, "DEXSZUS": 2.0, "DEXUSAL": 2.0, "DEXCAUS": 2.0, "DEXSDUS": 2.0,
          "DEXSFUS": 2.0, "DEXMXUS": 2.0, "DEXUSEU": 2.0, "DCOILWTICO": 3.0, "DCOILBRENTEU": 3.0, "DHHNGSP": 3.0}


def fred_bars(sid):
    d = pd.read_csv(SRC / f"{sid}.csv")
    d.columns = ["date", "v"]
    d["v"] = pd.to_numeric(d.v, errors="coerce")
    d = d.dropna()
    d = d[d.v > 0]
    t = ((pd.to_datetime(d.date) - pd.Timestamp("1970-01-01")) // pd.Timedelta(seconds=1)).to_numpy(np.int64) + 21 * 3600
    c = d.v.to_numpy(float); o = np.r_[c[0], c[:-1]]
    B = L.Bars(tf="D1", t=t, o=o, h=np.maximum(o, c), l=np.minimum(o, c), c=c, v=np.ones(len(c)), n=np.full(len(c), 12),
               hi_pos=np.full(len(c), np.nan), lo_pos=np.full(len(c), np.nan))
    B.atr = L.atr(B.h, B.l, B.c, 14)
    return B


def main():
    for sid, cost in SERIES.items():
        C.SPECS[sid] = dict(cost_rt_bp=cost, swap_long_bp=0.0, swap_short_bp=0.0, rollover3=3)
    rng = np.random.default_rng(1949)
    rows, draws, bears, dec = [], {}, [], []
    for sid in SERIES:
        B = fred_bars(sid)
        tk = Z.taken_trades(B, sid)
        Z.markets_cache[sid] = (B, sid, None)
        for (system, sides), T in tk.items():
            Z.taken_cache[(sid, system, sides)] = T
            if len(T) < 5:
                continue
            real = Z.net_pct(T).mean(); ctl = Z.control_draws(B, sid, T, rng); draws[(sid, system, sides)] = ctl
            eq = C.equity(T, 0.01)
            r = Z.bh_returns(B, sid); r = r[r.index >= int(T.t.min())].to_numpy()
            yrs = len(r) / 252.0
            L1, bh1 = Z.lev_curve(r, 1.0)
            Lm, cagr_m, _ = Z.dd_matched(r, max(eq.get("dd", 0.0), 1e-4), yrs)
            rows.append(dict(mkt=sid, first=str(pd.Timestamp(int(B.t[0]), unit="s").date()), system=system, sides=sides, n=len(T),
                             real_pct=real * 100, ctl_pct=np.nanmean(ctl) * 100, alpha_pct=(real - np.nanmean(ctl)) * 100, p_mkt=float(np.mean(ctl >= real)),
                             trend_cagr=eq.get("cagr"), trend_dd=eq.get("dd"), bh_cagr_L1=L1[-1] ** (1 / yrs) - 1, bh_dd_L1=bh1, bh_cagr_matched=cagr_m))
            T2 = T.assign(dec=(pd.to_datetime(T.t, unit="s").dt.year // 10) * 10, net=Z.net_pct(T))
            for dcd, g in T2.groupby("dec"):
                dec.append(dict(mkt=sid, system=system, sides=sides, decade=int(dcd), n=len(g), net_pct=g.net.mean() * 100, R=g.R.mean()))
        for (pk, tr) in Z.bear_phases(B):
            a_t, b_t = int(B.t[pk]), int(B.t[tr])
            for (system, sides), T in tk.items():
                TT = T[(T.t >= a_t) & (T.t <= b_t)]
                e2 = C.equity(TT, 0.01) if len(TT) else dict(end=10_000.0)
                bears.append(dict(mkt=sid, peak=str(pd.Timestamp(a_t, unit="s").date()), trough=str(pd.Timestamp(b_t, unit="s").date()),
                                  bh_pct=(B.c[tr] / B.c[pk] - 1) * 100, system=system, sides=sides, trades=len(TT), trend_pct=(e2.get("end", 10_000.0) / 10_000 - 1) * 100))
        print(sid, "done", flush=True)
    D = pd.DataFrame(rows); D.to_csv(OUT / "P16_rows.csv", index=False)
    pd.DataFrame(bears).to_csv(OUT / "P16_bear_phases.csv", index=False)
    pd.DataFrame(dec).to_csv(OUT / "P16_decades.csv", index=False)
    V = []
    for system in C.SYSTEMS:
        for sides in ("long", "both"):
            x = D[(D.system == system) & (D.sides == sides)]
            M = np.vstack([draws[(m, system, sides)] for m in x.mkt])
            null = np.nanmean(M - np.nanmean(M, axis=1, keepdims=True), axis=0) * 100
            pa = x.alpha_pct.mean(); p = float(np.mean(null >= pa)); share = float((x.alpha_pct > 0).mean())
            beat = float((x.trend_cagr > x.bh_cagr_matched).mean())
            V.append(dict(system=system, sides=sides, markets=len(x), pooled_alpha_pct=pa, p=p, share_alpha_pos=share, share_beats_dd_matched_bh=beat,
                          PASS_timing=bool(pa > 0 and p < 0.05 and share >= 0.6), PASS_vs_bh_markets=beat >= 0.6))
    V = pd.DataFrame(V); V.to_csv(OUT / "P16_verdict.csv", index=False)
    pd.set_option("display.width", 220)
    print(V.round(4).to_string(index=False))


if __name__ == "__main__":
    main()
