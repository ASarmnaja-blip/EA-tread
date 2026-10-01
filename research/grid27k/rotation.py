"""Market subsets and asset rotation (docs/plans/ROTATION_PREREG.md) for H4-55 + D1-1 at 0.6 % per trade each.
Rotation: at each month start rank the markets by their N-week return on closed W1 bars, keep the top k with a positive return, open
new trades only there (trades already open run to their exits). Choose N, k on 2009-09..2017-12 by MAR, test on 2018-01..2026-09."""
from __future__ import annotations

import itertools
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
RISK = 0.006
WINDOWS = [("all 2009-09..2026-09", "2009-09-01", None), ("metals bear 2011-09..2015-12", "2011-09-01", "2016-01-01"),
           ("test 2018-01..2026-09", "2018-01-01", None), ("last five years 2021-10..2026-09", "2021-10-01", None)]
SEL = ("2009-09-01", "2018-01-01")


def main():
    K.START = CP.FIRST
    ext = K.externals(); fr = {"H4": {}, "D1": {}}; pr = {"H4": {}, "D1": {}}; W = {}
    for m in K.MKTS:
        h1 = S.spliced_h1(m); F = G.frames(h1); W[m] = F["W1"]
        for tf, sec in (("H4", 14400), ("D1", 86400)):
            M = K.prepare(m, h1, ext, tf); X = G.features(F, m, tf); X["sec"] = sec; CP.extras(m, h1, X, M); fr[tf][m], pr[tf][m] = X, M
    trades = []
    for tf, Cc, D in (("D1", "C2", "D1"), ("H4", "C4", "D2")):
        for m in K.MKTS:
            d = K.directions(pr[tf][m], Cc, D, "E1", "J1"); s = np.flatnonzero(d); trades += CP.sim(fr[tf][m], m, s, d[s], 2.0, "ch20")
    items_all = [(r, RISK / 0.01) for r in trades]

    def run(items, label, windows=WINDOWS):
        out = {}
        for wname, a, b in windows:
            r = DP.evaluate(items, "Q0", C.ts(a), C.ts(b) if b else None, fr["H4"])
            if r:
                out[wname] = r
        print(f"{label:40s} | " + " | ".join(f"{w.split(' ')[0]} {r['cagr']:+.1%} DD {r['eq_dd']:.0%}" for w, r in out.items()))
        return out

    print("== market subsets (hindsight view)")
    for k in (1, 2, 3):
        for sub in itertools.combinations(K.MKTS, k):
            run([(r, m_) for r, m_ in items_all if r["mkt"] in sub], "+".join(sub))
    months = pd.period_range("2009-09", "2026-09", freq="M")
    month_start = {p: C.ts(str(p.start_time.date())) for p in months}

    def picks(N, k):
        sel = {}
        for p, t0 in month_start.items():
            sc = {}
            for m, A in W.items():
                close_t = np.r_[A["t"][1:], A["t"][-1] + 7 * 86400]; j = np.searchsorted(close_t, t0, side="right") - 1
                if j - N >= 0:
                    sc[m] = A["c"][j] / A["c"][j - N] - 1
            sel[p] = {m for m, v in sorted(sc.items(), key=lambda x: -x[1])[:k] if v > 0}
        return sel

    print("\n== rotation rules")
    res = {}
    for N, k in itertools.product((13, 26, 52), (1, 2)):
        sel = picks(N, k)
        it = [(r, m_) for r, m_ in items_all if r["mkt"] in sel[pd.Timestamp(r["t"], unit="s").to_period("M")]]
        res[(N, k)] = (run(it, f"rotate N={N} top{k}", [("selection 2009-09..2017-12", *SEL)] + WINDOWS), sel)
    base = run(items_all, "all three always (reference)", [("selection 2009-09..2017-12", *SEL)] + WINDOWS)
    best = max(res, key=lambda key: res[key][0]["selection 2009-09..2017-12"]["mar"])
    b = res[best][0]
    t, tb = b["test 2018-01..2026-09"], base["test 2018-01..2026-09"]
    verdict = t["mar"] > tb["mar"] and t["eq_dd"] <= 0.30
    print(f"\nchosen on 2009-17 by MAR: N={best[0]} top{best[1]} (selection MAR {b['selection 2009-09..2017-12']['mar']:.2f}); test MAR {t['mar']:.2f} vs all-three"
          f" {tb['mar']:.2f}, test DD {t['eq_dd']:.1%} -> {'better' if verdict else 'not better'}")
    last = months[-1]
    print("picks for", last, {f"N={N} top{k}": sorted(res[(N, k)][1][last]) for N, k in res})


if __name__ == "__main__":
    main()
