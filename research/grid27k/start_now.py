"""Operator 2026-10-02: "what if we start now?" For H4-55 alone at 1.5 % and H4-55 + D1-1 at 1 % each: the spread of outcomes for a
fresh account started at every month 2009-09..2025-09 (12- and 24-month return and drawdown), the same restricted to starts in a state like
now (gold and silver W1 below the 55-week midline), and the systems' state on the last bar (open trades, distance to the next signal)."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent / "grid768")]
import complement as CP  # noqa: E402
import dynamic_plan as DP  # noqa: E402
import g27k as K  # noqa: E402
import g768 as G  # noqa: E402
import stress_top3 as S  # noqa: E402

C = G.C
PLANS = {"H4-55 alone 1.5 %": [("H4-55", 0.015)], "H4-55 + D1-1 1 % each": [("H4-55", 0.01), ("D1-1", 0.01)]}


def main():
    K.START = CP.FIRST
    ext = K.externals(); fr = {"H4": {}, "D1": {}}; pr = {"H4": {}, "D1": {}}; good = {}
    for m in K.MKTS:
        h1 = S.spliced_h1(m); F = G.frames(h1)
        for tf, sec in (("H4", 14400), ("D1", 86400)):
            M = K.prepare(m, h1, ext, tf); X = G.features(F, m, tf); X["sec"] = sec; CP.extras(m, h1, X, M); fr[tf][m], pr[tf][m] = X, M
        good[m] = DP.regimes(fr["H4"][m], F)
    T = {"H4-55": [], "D1-1": []}
    for name, (tf, Cc, D) in {"H4-55": ("H4", "C4", "D2"), "D1-1": ("D1", "C2", "D1")}.items():
        for m in K.MKTS:
            d = K.directions(pr[tf][m], Cc, D, "E1", "J1"); s = np.flatnonzero(d); T[name] += [dict(r, system=name) for r in CP.sim(fr[tf][m], m, s, d[s], 2.0, "ch20")]
    starts = pd.date_range("2009-09-01", "2025-09-01", freq="MS")
    X4 = fr["H4"]
    state_like_now = {}
    for st in starts:
        t0 = C.ts(str(st.date()))
        flags = []
        for m in ("XAUUSD", "XAGUSD"):
            i = np.searchsorted(X4[m]["t"], t0) - 1
            flags.append(i >= 0 and not good[m]["R1"][i])
        state_like_now[st] = all(flags)
    for pname, parts in PLANS.items():
        items = [(r, rk / 0.01) for key, rk in parts for r in T[key]]
        rows = []
        for st in starts:
            t0 = C.ts(str(st.date()))
            for H in (12, 24):
                t1 = C.ts(str((st + pd.DateOffset(months=H)).date()))
                if t1 > C.ts("2026-10-01"):
                    continue
                r = DP.evaluate(items, "Q0", t0, t1, X4)
                if r:
                    rows.append(dict(start=st, H=H, ret=r["ret"], dd=r["eq_dd"], like_now=state_like_now[st]))
        D = pd.DataFrame(rows)
        print(f"\n== {pname}")
        for H in (12, 24):
            for lab, sub in (("all starts", D[D.H == H]), ("starts like now (gold and silver W1 down)", D[(D.H == H) & D.like_now])):
                if not len(sub):
                    continue
                q = sub.ret.quantile([0.05, 0.25, 0.5, 0.75, 0.95])
                print(f"  {H:2d} months, {lab:42s} n {len(sub):3d} | return p5 {q[0.05]:+.0%} p25 {q[0.25]:+.0%} median {q[0.5]:+.0%} p75 {q[0.75]:+.0%} p95 {q[0.95]:+.0%}"
                      f" | losing {(sub.ret < 0).mean():.0%} | equity DD median {sub.dd.median():.0%} worst {sub.dd.max():.0%} | worst start {sub.loc[sub.ret.idxmin(), 'start'].date()} {sub.ret.min():+.0%}")
    print("\n== state on the last bar")
    for m in K.MKTS:
        X = X4[m]; M = pr["H4"][m]; i = len(X["t"]) - 1
        hi55 = M["hi55"][i]; atr = X["a14"][i]
        with np.errstate(invalid="ignore"):
            apct = pd.Series(X["a14"]).rolling(250, min_periods=100).rank(pct=True).to_numpy()[i]
        open_h4 = [r for r in T["H4-55"] if r["mkt"] == m and r["x"] == len(X["t"]) - 1]
        open_d1 = [r for r in T["D1-1"] if r["mkt"] == m and r["x"] == len(fr["D1"][m]["t"]) - 1]
        print(f"  {m}: close {X['c'][i]:,.2f} | 55-bar high {hi55:,.2f} ({(hi55 - X['c'][i]) / atr:+.1f} ATR away) | ATR14 percentile {apct:.0%}"
              f" ({'high-vol filter on' if apct >= 0.5 else 'high-vol filter off'}) | W1 55w {'up' if good[m]['R1'][i] else 'down'}, 26w {'up' if good[m]['R5'][i] else 'down'}"
              f" | open H4-55 {len(open_h4)} (entered {[str(pd.Timestamp(r['t'], unit='s').date()) for r in open_h4]}) | open D1-1 {len(open_d1)}")


if __name__ == "__main__":
    main()
