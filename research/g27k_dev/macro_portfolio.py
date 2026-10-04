#!/usr/bin/env python3
"""Portfolio driven by external (macro) factors only (ledger ids
macro_only_portfolio and g27k_macro_overlay).

Every Monday 00:00 UTC each market gets a score in [-1, 1]: the mean of
+1/-1 votes from macro series, using only observations old enough to have
been published by then (FRED daily series dated <= D-4 days; the weekly broad
dollar, NFCI and GPR dated <= D-10 days). No price-chart input.

  gold, silver: real yield falling, dollar falling, breakeven inflation
                rising, 2-year yield falling, VIX above its 1-year median,
                geopolitical risk above its 1-year median
  BTC:          dollar falling, real yield falling, 2-year yield falling,
                VIX below its 1-year median, financial conditions loosening

Test 1 (macro only): hold each market long when its score > 0 (P1) or with
weight x max(score, 0) (P2); weekly rebalance, broker costs and long swap;
benchmark is the same weights always long.
Test 2 (overlay): G27K #1 trades unchanged; O1 skips trades with score < 0,
O2 scales risk by 1 + score (mean multiplier 1).
Null for both: 1000 circular shifts of the weekly score series.

Usage: python3 research/g27k_dev/macro_portfolio.py --root <data-snapshot checkout>
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

FIRST, LAST = "2009-09-07", "2026-09-28"
HALF = pd.Timestamp("2017-01-01")
N_NULL = 1000
DAY = 86400


def fred(name):
    s = pd.read_csv(HERE / "macro_data" / f"{name}.csv", na_values=["."])
    return pd.Series(s.iloc[:, 1].astype(float).to_numpy(), index=pd.to_datetime(s.iloc[:, 0])).dropna()


def votes(root):
    """Daily vote series and the publication lag (days) of each."""
    g = pd.read_stata(pathlib.Path(root) / "data/macro/gpr_daily.dta")
    gpr = pd.Series(g["GPRD"].astype(float).to_numpy(), index=pd.to_datetime(g["date"])).dropna()
    rr, usd, be, y2, vix, nfci = (fred(n) for n in ("DFII10", "DTWEXBGS", "T10YIE", "DGS2", "VIXCLS", "NFCI"))
    sgn = lambda b: b.astype(float) * 2 - 1
    v = dict(rr_down=(sgn(rr.diff(63) < 0)[63:], 4), usd_down=(sgn(usd.diff(63) < 0)[63:], 10),
             be_up=(sgn(be.diff(63) > 0)[63:], 4), y2_down=(sgn(y2.diff(63) < 0)[63:], 4),
             vix_hi=(sgn(vix > vix.rolling(252, min_periods=252).median())[251:], 4),
             gpr_hi=(sgn(gpr > gpr.rolling(250, min_periods=250).median())[249:], 10),
             nfci_loose=(sgn(nfci.diff(13) < 0)[13:], 10))
    v["vix_lo"] = (-v["vix_hi"][0], 4)
    return v


SCORES = {"XAUUSD": ("rr_down", "usd_down", "be_up", "y2_down", "vix_hi", "gpr_hi"),
          "XAGUSD": ("rr_down", "usd_down", "be_up", "y2_down", "vix_hi", "gpr_hi"),
          "BTCUSD": ("usd_down", "rr_down", "y2_down", "vix_lo", "nfci_loose")}


def weekly_scores(V, weeks):
    out = {}
    for m, names in SCORES.items():
        cols = []
        for n in names:
            s, lag = V[n]
            avail = s.index + pd.Timedelta(days=lag)
            j = np.searchsorted(avail.values, weeks.values, side="right") - 1
            cols.append(np.where(j >= 0, s.to_numpy()[np.maximum(j, 0)], np.nan))
        out[m] = np.nanmean(np.vstack(cols), axis=0)
    return pd.DataFrame(out, index=weeks)


def weekly_prices(H1, weeks):
    px = {}
    for m, h in H1.items():
        t = np.asarray(h["t"], np.int64)
        D = weeks.values.astype("datetime64[s]").astype(np.int64)
        j = np.searchsorted(t, D)
        ok = (j < len(t)) & (t[np.minimum(j, len(t) - 1)] - D < 3 * DAY)
        px[m] = np.where(ok, np.asarray(h["o"], float)[np.minimum(j, len(t) - 1)], np.nan)
    return pd.DataFrame(px, index=weeks)


def stats(eq, idx):
    eq = pd.Series(eq, index=idx)
    yrs = (idx[-1] - idx[0]).days / 365.25
    cagr = eq.iloc[-1] ** (1 / yrs) - 1
    dd = float((1 - eq / eq.cummax()).max())
    wk = eq.pct_change().dropna()
    return dict(cagr=float(cagr), dd=dd, mar=float(cagr / dd) if dd > 0 else np.nan,
                vol=float(wk.std() * np.sqrt(52)), final=float(eq.iloc[-1]))


def portfolio(R, S, avail, markets, mode, C):
    """Weekly equity of a long-only macro portfolio; mode 'bh', 'P1' or 'P2'."""
    n = len(R)
    w_prev = np.zeros(len(markets))
    eq = np.ones(n)
    on = []
    for i in range(n - 1):
        live = np.array([avail[m].iloc[i] for m in markets])
        base = np.where(live, 1 / max(live.sum(), 1), 0.0)
        s = np.nan_to_num(np.array([S[m].iloc[i] for m in markets]), nan=-1)
        w = base if mode == "bh" else base * (s > 0) if mode == "P1" else base * np.maximum(s, 0)
        cost = sum(abs(w[k] - w_prev[k]) * C.SPECS[m]["cost_rt_bp"] / 2e4 for k, m in enumerate(markets))
        swap = sum(w[k] * 7 * C.SPECS[m]["swap_long_bp"] / 1e4 for k, m in enumerate(markets))
        r = np.nan_to_num(np.array([R[m].iloc[i] for m in markets]))
        eq[i + 1] = eq[i] * (1 + (w * r).sum() - cost - swap)
        w_prev = w * (1 + r) / (1 + (w * r).sum()) if (1 + (w * r).sum()) > 0 else w
        on.append(w.sum())
    return eq, float(np.mean(on))


def account_m(T, mult, s0, s1):
    """phase1.account with a per-trade risk multiplier; returns CAGR, balance DD, MAR."""
    order = np.argsort(T.t.to_numpy(), kind="stable")
    t, tx, R, mu = T.t.to_numpy()[order], T.tx.to_numpy()[order], T.R.to_numpy()[order], mult[order]
    bal, peak, dd, heap = 1.0, 1.0, 0.0, []
    for i in range(len(t)):
        while heap and heap[0][0] <= t[i]:
            _, p = heapq.heappop(heap)
            bal += p
            peak, dd = max(peak, bal), max(dd, 1 - bal / max(peak, bal))
        if mu[i] > 0:
            heapq.heappush(heap, (tx[i], 0.01 * mu[i] * bal * R[i]))
    while heap:
        _, p = heapq.heappop(heap)
        bal += p
        peak, dd = max(peak, bal), max(dd, 1 - bal / max(peak, bal))
    yrs = (s1 - s0) / (365.25 * DAY)
    cagr = bal ** (1 / yrs) - 1 if bal > 0 else -1.0
    return dict(cagr=float(cagr), dd=float(dd), mar=float(cagr / dd) if dd > 0 else np.nan,
                n=int((mu > 0).sum()))


def overlay_mult(T, S, wk_t, mode):
    j = np.searchsorted(wk_t, T.t.to_numpy(), side="right") - 1
    s = np.array([S[m].to_numpy()[k] if k >= 0 else np.nan for m, k in zip(T.mkt, j)])
    s = np.nan_to_num(s, nan=0.0)
    if mode == "O1":
        return (s >= 0).astype(float)
    m = 1 + s
    return m / m.mean()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    a = ap.parse_args()
    P.setup(a.root)
    G, K, C = P._M["G"], P._M["K"], P._M["C"]
    H1 = {m: W.hybrid_h1(m, G) for m in K.MKTS}
    weeks = pd.date_range(FIRST, LAST, freq="W-MON")
    S = weekly_scores(votes(a.root), weeks)
    PX = weekly_prices(H1, weeks)
    R = (PX.shift(-1) / PX - 1)
    avail = PX.notna() & PX.shift(-1).notna()
    rng = np.random.default_rng(11)
    shifts = rng.integers(52, len(weeks) - 52, N_NULL)
    res = dict(score_share_positive={m: float((S[m] > 0).mean()) for m in S},
               score_by_year={m: S[m].groupby(S.index.year).mean().round(2).to_dict() for m in S})
    halves = [("full", weeks[0], weeks[-1]), ("2009-16", weeks[0], HALF), ("2017-26", HALF, weeks[-1])]

    def port_stats(Sx, markets, mode):
        eq, on = portfolio(R, Sx, avail, markets, mode, C)
        out = dict(time_in_market=on)
        for name, lo, hi in halves:
            k = (weeks >= lo) & (weeks <= hi)
            out[name] = stats(eq[k] / eq[k][0], weeks[k])
        return out

    print("Test 1: macro only (1x notional, long or flat)")
    t1 = {}
    for sysname, markets in PH.SYSTEMS.items():
        row = {mode: port_stats(S, markets, mode) for mode in ("bh", "P1", "P2")}
        for mode in ("P1", "P2"):
            null = []
            for sh in shifts:
                Sx = pd.DataFrame(np.roll(S.to_numpy(), sh, axis=0), index=S.index, columns=S.columns)
                eq, _ = portfolio(R, Sx, avail, markets, mode, C)
                null.append(stats(eq, weeks)["mar"])
            row[mode]["p_shift"] = float((1 + np.sum(np.array(null) >= row[mode]["full"]["mar"])) / (1 + N_NULL))
        t1[sysname] = row
        for mode in ("bh", "P1", "P2"):
            r = row[mode]
            print(f"  {sysname} {mode:3s} in-mkt {r['time_in_market']:.0%}  " + "  ".join(
                f"{h}: CAGR {r[h]['cagr']:+.1%} DD {r[h]['dd']:.0%} MAR {r[h]['mar']:.2f}" for h, _, _ in halves)
                + (f"  p {r['p_shift']:.3f}" if "p_shift" in r else ""), flush=True)
    res["macro_only"] = t1

    print("Test 2: macro overlay on G27K #1 (1% base risk)")
    ext = K.externals()
    Ds = {m: PH.prep_market(m, H1[m], ext) for m in K.MKTS}
    wk_t = weeks.values.astype("datetime64[s]").astype(np.int64)
    t2 = {}
    for sysname in PH.SYSTEMS:
        T = PH.system_trades(sysname, Ds, *PH.BASE).reset_index(drop=True)
        row = {}
        for mode in ("base", "O1", "O2"):
            mult = np.ones(len(T)) if mode == "base" else overlay_mult(T, S, wk_t, mode)
            row[mode] = {}
            for name, lo, hi in (("full", PH.START, PH.END), ("2009-16", PH.START, str(HALF.date())),
                                 ("2017-26", str(HALF.date()), PH.END)):
                k = ((T.t >= W.ts(lo)) & (T.t < W.ts(hi))).to_numpy()
                row[mode][name] = account_m(T[k], mult[k], W.ts(lo), W.ts(hi))
            if mode != "base":
                null = []
                for sh in shifts:
                    Sx = pd.DataFrame(np.roll(S.to_numpy(), sh, axis=0), index=S.index, columns=S.columns)
                    null.append(account_m(T, overlay_mult(T, Sx, wk_t, mode), W.ts(PH.START), W.ts(PH.END))["mar"])
                row[mode]["p_shift"] = float((1 + np.sum(np.array(null) >= row[mode]["full"]["mar"])) / (1 + N_NULL))
            r = row[mode]
            print(f"  {sysname} {mode:4s} " + "  ".join(
                f"{h}: n {r[h]['n']} CAGR {r[h]['cagr']:+.1%} DD {r[h]['dd']:.0%} MAR {r[h]['mar']:.2f}"
                for h in ("full", "2009-16", "2017-26")) + (f"  p {r['p_shift']:.3f}" if "p_shift" in r else ""),
                flush=True)
        t2[sysname] = row
    res["overlay"] = t2
    (HERE / "macro_portfolio.json").write_text(json.dumps(res, indent=1, default=float))


if __name__ == "__main__":
    main()
