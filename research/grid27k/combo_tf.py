"""Operator 2026-10-02: G27K setup 1 on H4 combined with the G768 system on D1, and with the H4 55-bar breakout in high volatility.
Systems (gold, silver, BTC; one open trade per market per system; systems may hold the same market together):
  H4-1  C8/D3/E1/F1/G2/H2/I1/J1 on H4 (setup 1)
  D1-1  C2/D1/E1/F1/G2/H2/I1/J1 on D1 (20-day breakout with the W1 trend agreeing)
  H4-55 C4/D2/E1/F1/G2/H2/I1/J1 on H4 (55-bar breakout while ATR14 is above its 250-bar median)
Gold and silver 2009-09.. (Candle Lab H1 before 2016-08, MT5 after), BTC 2018-03..; fresh $100,000 per window; equity marked at every
H4 close; stops walked on H1 bars inside each bar."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent / "grid768")]
import complement as CP  # noqa: E402
import g27k as K  # noqa: E402
import g768 as G  # noqa: E402
import stress_top3 as S  # noqa: E402

C = G.C
SYSTEMS = {"H4-1": ("H4", "C8", "D3"), "D1-1": ("D1", "C2", "D1"), "H4-55": ("H4", "C4", "D2")}
MIXES = [("H4-1 alone, 1 %", {"H4-1": 0.01}), ("D1-1 alone, 1 %", {"D1-1": 0.01}), ("H4-55 alone, 1 %", {"H4-55": 0.01}),
         ("H4-1 + D1-1, 1 % each", {"H4-1": 0.01, "D1-1": 0.01}), ("H4-1 + D1-1, 0.5 % each", {"H4-1": 0.005, "D1-1": 0.005}),
         ("all three, 1 % each", {"H4-1": 0.01, "D1-1": 0.01, "H4-55": 0.01}),
         ("all three, 0.33 % each", {"H4-1": 0.01 / 3, "D1-1": 0.01 / 3, "H4-55": 0.01 / 3})]
WINDOWS = [("last five years 2021-10..2026-09", "2021-10-01", None), ("before 2017-01..2021-09", "2017-01-01", "2021-10-01"),
           ("all 2009-09..2026-09", "2009-09-01", None), ("metals bear 2011-09..2015-12", "2011-09-01", "2016-01-01"),
           ("2013", "2013-01-01", "2014-01-01"), ("2018", "2018-01-01", "2019-01-01"), ("2022", "2022-01-01", "2023-01-01")]


def main():
    K.START = CP.FIRST
    ext = K.externals(); frames = {"H4": {}, "D1": {}}; preps = {"H4": {}, "D1": {}}
    for m in K.MKTS:
        h1 = S.spliced_h1(m); F = G.frames(h1)
        for tf, sec in (("H4", 14400), ("D1", 86400)):
            M = K.prepare(m, h1, ext, tf); X = G.features(F, m, tf); X["sec"] = sec; CP.extras(m, h1, X, M)
            assert np.array_equal(M["t"], X["t"]), (m, tf)
            frames[tf][m], preps[tf][m] = X, M
    trades = {}
    for name, (tf, Cc, D) in SYSTEMS.items():
        trades[name] = []
        for m in K.MKTS:
            d = K.directions(preps[tf][m], Cc, D, "E1", "J1"); s = np.flatnonzero(d)
            trades[name] += [dict(r, system=name) for r in CP.sim(frames[tf][m], m, s, d[s], 2.0, "ch20")]
        print(f"{name}: {len(trades[name])} trades 2009-2026, total {sum(r['R'] for r in trades[name]):+.0f}R")
    for wname, a, b in WINDOWS:
        print(f"\n== {wname}")
        for mname, mix in MIXES:
            # one account: each system's trades sized at its own risk share of the shared balance
            items = [r for nm, rk in mix.items() for r in trades[nm]]
            scale = {nm: rk for nm, rk in mix.items()}
            top = max(scale.values())
            for r in items:
                r["R_scaled"] = r["R"] * scale[r["system"]] / top
            R = S.account_window([dict(r, R=r["R_scaled"]) for r in items], top, C.ts(a), C.ts(b) if b else None, frames["H4"])
            if R is None:
                continue
            print(f"  {mname:26s} trades {R['n']:4d} total {R['ret']:+7.0%} CAGR {R['cagr']:+6.1%} equity DD {R['eq_dd']:5.1%} balance DD {R['bal_dd']:5.1%}"
                  f" low {R['low']:4.0%} of start | underwater {R['under'] / 365.25:4.1f} y | worst 12 m {R['worst12'][1]:+.0%}" if R["worst12"] else
                  f"  {mname:26s} trades {R['n']:4d} total {R['ret']:+7.0%} CAGR {R['cagr']:+6.1%} equity DD {R['eq_dd']:5.1%} balance DD {R['bal_dd']:5.1%}"
                  f" low {R['low']:4.0%} of start | underwater {R['under'] / 365.25:4.1f} y")


if __name__ == "__main__":
    main()
