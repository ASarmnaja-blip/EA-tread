"""Three-system dynamic plan (docs/plans/DYNAMIC3_PREREG.md): H4-1 (setup 1) opens trades only while its market's W1 regime is good
(R5: W1 close above the 26-week Donchian midline; R1: 55-week as a check); D1-1 (C2/D1 on D1) and H4-55 (C4/D2 on H4) always on. Each
system sized at its own risk share of one shared balance (per-trade multipliers, so equity marks scale correctly)."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent / "grid768")]
import complement as CP  # noqa: E402
import dynamic_plan as DP  # noqa: E402
import g27k as K  # noqa: E402
import g768 as G  # noqa: E402
import stress_top3 as S  # noqa: E402

C = G.C
RISKS = {"a": (0.005, 0.0075, 0.0075), "b": (0.0075, 0.0075, 0.0075), "c": (0.01, 0.01, 0.01), "d": (0.005, 0.005, 0.01)}
WINDOWS = [("all 2009-09..2026-09", "2009-09-01", None), ("metals bear 2011-09..2015-12", "2011-09-01", "2016-01-01"),
           ("2013", "2013-01-01", "2014-01-01"), ("2018", "2018-01-01", "2019-01-01"), ("2022", "2022-01-01", "2023-01-01"),
           ("before 2017-01..2021-09", "2017-01-01", "2021-10-01"), ("last five years 2021-10..2026-09", "2021-10-01", None)]


def main():
    K.START = CP.FIRST
    ext = K.externals(); fr = {"H4": {}, "D1": {}}; pr = {"H4": {}, "D1": {}}; good = {}
    for m in K.MKTS:
        h1 = S.spliced_h1(m); F = G.frames(h1)
        for tf, sec in (("H4", 14400), ("D1", 86400)):
            M = K.prepare(m, h1, ext, tf); X = G.features(F, m, tf); X["sec"] = sec; CP.extras(m, h1, X, M)
            fr[tf][m], pr[tf][m] = X, M
        good[m] = DP.regimes(fr["H4"][m], F)
    sim = lambda tf, Cc, D, m, mask=None: CP.sim(fr[tf][m], m, *(lambda d: (np.flatnonzero(d), d[np.flatnonzero(d)]))(
        np.where(mask, K.directions(pr[tf][m], Cc, D, "E1", "J1"), 0) if mask is not None else K.directions(pr[tf][m], Cc, D, "E1", "J1")), 2.0, "ch20")
    T = {"D1-1": [r for m in K.MKTS for r in sim("D1", "C2", "D1", m)], "H4-55": [r for m in K.MKTS for r in sim("H4", "C4", "D2", m)],
         "H4-1": [r for m in K.MKTS for r in sim("H4", "C8", "D3", m)]}
    for R in ("R5", "R1"):
        T[f"H4-1|{R}"] = [r for m in K.MKTS for r in sim("H4", "C8", "D3", m, good[m][R])]
    plans = [(f"dyn {R} {k} (H4-1 {a:.2%} when good, D1 {b:.2%}, H4-55 {c:.2%})", [(f"H4-1|{R}", a), ("D1-1", b), ("H4-55", c)])
             for R in ("R5", "R1") for k, (a, b, c) in RISKS.items()]
    plans += [("static H4-55 + D1-1 0.75 % each", [("D1-1", 0.0075), ("H4-55", 0.0075)]), ("H4-1 alone 1 %", [("H4-1", 0.01)])]
    rows = []
    for name, parts in plans:
        items = [(r, risk / 0.01) for key, risk in parts for r in T[key]]
        res = {}
        for wname, a, b in WINDOWS:
            r = DP.evaluate(items, "Q0", C.ts(a), C.ts(b) if b else None, fr["H4"])
            if r:
                res[wname] = r
        full = res["all 2009-09..2026-09"]
        ok = full["bal_dd"] <= 0.25 and full["eq_dd"] <= 0.30
        rows.append((name, ok, full["cagr"]))
        print(f"\n{name}  {'PASSES the DD limits' if ok else 'fails the DD limits'}")
        for wname, r in res.items():
            print(f"   {wname:34s} trades {r['n']:4d} total {r['ret']:+7.0%} CAGR {r['cagr']:+6.1%} equity DD {r['eq_dd']:5.1%} balance DD {r['bal_dd']:5.1%}"
                  f" low {r['low']:4.0%} | underwater {r['under'] / 365.25:4.1f} y")
    passed = [x for x in rows if x[1]]
    print("\npassing plans:", [x[0] for x in passed])
    if passed:
        print("chosen (highest CAGR among passing):", max(passed, key=lambda x: x[2])[0])
    print("H4-1 regime now:", {m: {R: bool(good[m][R][-1]) for R in ("R5", "R1")} for m in K.MKTS})


if __name__ == "__main__":
    main()
