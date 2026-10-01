"""Stress test (docs/plans/STRESS_TOP3_PREREG.md): G27K setup 1 alone and the top three together through the worst periods available.
Gold and silver: Candle Lab H1 before the MT5 history starts (2016-08-09), MT5 H1 after; BTC: MT5 H1 from 2018-03. Same rules, costs
and today's swap rates. Each window starts a fresh $100,000 account and counts the trades entered inside it."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent / "grid768")]
import g27k as K  # noqa: E402
import g768 as G  # noqa: E402
import report768 as RP  # noqa: E402

C = G.C
TOP3 = ["C8/D3/E1/F1/G2/H2/I1/J1", "C1/D6/E1/F1/G2/H2/I1/J1", "C8/D6/E1/F1/G2/H2/I1/J1"]
VARIANTS = [("setup 1 alone, 1 %", TOP3[:1], 0.01), ("three together, 1 % each", TOP3, 0.01), ("three together, 0.33 % each", TOP3, 0.01 / 3)]
WINDOWS = [("2011-09..2015-12 metals bear", "2011-09-01", "2016-01-01"), ("2013 gold crash", "2013-01-01", "2014-01-01"),
           ("2018 BTC crash", "2018-01-01", "2019-01-01"), ("2022 BTC crash, metals down", "2022-01-01", "2023-01-01"),
           ("all 2009-09..2026-09", "2009-09-01", None), ("last five years 2021-10..2026-09", "2021-10-01", None)]
FIRST = C.ts("2009-09-01")


def spliced_h1(m):
    mt = G.load_h1(m)
    if m == "BTCUSD":
        return mt
    z = np.load(G.ROOT / "data" / "bundle" / f"bars_{m}_H1.npz"); keep = z["t"].astype(np.int64) < mt["t"][0]
    out = {k: np.r_[z[k][keep].astype(mt[k].dtype), mt[k]] for k in ("t", "o", "h", "l", "c", "v")}
    out["step"] = 3600
    return out


def account_window(trades, risk, w0, w1, Xs):
    sub = [dict(r) for r in trades if r["t"] >= w0 and (w1 is None or r["t"] < w1)]
    if len(sub) < 5:                                          # too few trades for the report metrics
        return None
    last = max(r["t_exit"] for r in sub)
    T = np.unique(np.concatenate([X["t"] + 14400 for X in Xs.values()] + [np.array([r["t_exit"] for r in sub])]))
    T = T[(T >= w0) & (T <= last)]
    RP.prep_marks(sub, T)
    M = RP.metrics(RP.account(sub, risk), T, risk, start=w0)
    eq = np.array(M["curve"]["eq"]); tt = np.array(M["curve"]["t"])
    worst12 = None
    if tt[-1] - tt[0] > 400 * 86400:
        j = np.searchsorted(tt, tt + 365 * 86400); ok = j < len(tt)
        r = eq[j[ok]] / eq[ok] - 1; i = int(np.argmin(r))
        worst12 = (str(pd.Timestamp(int(tt[ok][i]), unit="s").date()), float(r[i]))
    return dict(n=M["trades"], ret=M["net"] / RP.DEPOSIT, cagr=M["cagr"], eq_dd=M["equity_dd"]["relative_pct"], bal_dd=M["balance_dd"]["relative_pct"],
                low=float(eq.min() / RP.DEPOSIT), run=M["streaks"]["max_losses"], run_usd=M["streaks"]["max_losses_usd"], under=M["longest_underwater_days"],
                peak=M["dd_window"]["peak"], trough=M["dd_window"]["trough"], recovered=M["dd_window"]["recovered"], worst12=worst12,
                by_mkt={x["mkt"]: x["R"] for x in M["per_market"]}, pf=M["pf"])


def main():
    K.START = FIRST
    ext = K.externals(); Ms, Xs = {}, {}
    for m in K.MKTS:
        h1 = spliced_h1(m); Ms[m] = K.prepare(m, h1, ext); Xs[m] = G.features(G.frames(h1), m, "H4"); Xs[m]["sec"] = 14400
        print(m, "H4 bars from", pd.Timestamp(int(Xs[m]["t"][0]), unit="s").date())
    trades = {}
    for c in TOP3:
        Cc, D, E, F, Gs, H, I, J = c.split("/"); trades[c] = []
        for m in K.MKTS:
            d = K.directions(Ms[m], Cc, D, E, J); idx = np.flatnonzero(d)
            trades[c] += [dict(tr, X=Xs[m]) for tr in RP.sim_paths(Xs[m], m, idx, d[idx], "I1")]
    rows = []
    for wname, a, b in WINDOWS:
        w0 = C.ts(a); w1 = C.ts(b) if b else None
        for vname, setups, risk in VARIANTS:
            R = account_window([r for c in setups for r in trades[c]], risk, w0, w1, Xs)
            if R is None:
                continue
            rows.append(dict(window=wname, variant=vname, **{k: v for k, v in R.items() if k not in ("by_mkt", "worst12")},
                             worst12=R["worst12"], by_mkt=R["by_mkt"]))
            w12 = f"  worst 12 months from {R['worst12'][0]}: {R['worst12'][1]:+.0%}" if R["worst12"] else ""
            print(f"{wname:34s} | {vname:28s} | trades {R['n']:4d} total {R['ret']:+7.0%} CAGR {R['cagr']:+6.1%} equity DD {R['eq_dd']:5.1%} "
                  f"balance DD {R['bal_dd']:5.1%} low {R['low']:5.0%} of start | losing run {R['run']} | underwater {R['under']:4.0f}d | PF {R['pf']:.2f}"
                  f" | DD {R['peak']} -> {R['trough']}{w12} | R by market {', '.join(f'{k} {v:+.0f}' for k, v in R['by_mkt'].items())}")
    pd.DataFrame(rows).to_json(K.OUT / "stress_top3.json", orient="records", force_ascii=False, indent=1)


if __name__ == "__main__":
    main()
