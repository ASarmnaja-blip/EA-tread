"""Weekly asset rotation (docs/plans/ROTATION_WEEKLY_PREREG.md): same systems and rules as rotation.py, decided at each week start
(G768 cut grid) from closed W1 bars; N in 4 / 8 / 13 / 26 weeks, top 1 or 2 with a positive return."""
from __future__ import annotations

import itertools
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent / "grid768")]
import complement as CP  # noqa: E402
import dynamic_plan as DP  # noqa: E402
import g27k as K  # noqa: E402
import g768 as G  # noqa: E402
import rotation as RO  # noqa: E402
import stress_top3 as S  # noqa: E402

C = G.C


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
    items_all = [(r, RO.RISK / 0.01) for r in trades]
    cuts = G.CUTS
    windows = [("selection 2009-09..2017-12", *RO.SEL)] + RO.WINDOWS

    def run(items, label):
        out = {}
        for wname, a, b in windows:
            r = DP.evaluate(items, "Q0", C.ts(a), C.ts(b) if b else None, fr["H4"])
            if r:
                out[wname] = r
        print(f"{label:28s} | " + " | ".join(f"{w.split(' ')[0]} {r['cagr']:+.1%} DD {r['eq_dd']:.0%} MAR {r['mar']:.2f}" for w, r in out.items()))
        return out

    def picks(N, k):
        sel = {}
        closes = {m: np.r_[A["t"][1:], A["t"][-1] + 7 * 86400] for m, A in W.items()}
        for w, t0 in enumerate(cuts):
            sc = {}
            for m, A in W.items():
                j = np.searchsorted(closes[m], t0, side="right") - 1
                if j - N >= 0:
                    sc[m] = A["c"][j] / A["c"][j - N] - 1
            sel[w] = {m for m, v in sorted(sc.items(), key=lambda x: -x[1])[:k] if v > 0}
        return sel

    res = {}
    for N, k in itertools.product((4, 8, 13, 26), (1, 2)):
        sel = picks(N, k); wk = lambda t: int(np.searchsorted(cuts, t, side="right") - 1)
        it = [(r, m_) for r, m_ in items_all if r["mkt"] in sel.get(wk(r["t"]), set())]
        res[(N, k)] = run(it, f"weekly N={N} top{k}")
        n_sw = sum(1 for w in range(1, len(cuts)) if sel.get(w) != sel.get(w - 1))
        print(f"{'':28s}   selection changes {n_sw} times over {len(cuts)} weeks")
    base = run(items_all, "all three always")
    best = max(res, key=lambda key: res[key]["selection 2009-09..2017-12"]["mar"])
    t, tb = res[best]["test 2018-01..2026-09"], base["test 2018-01..2026-09"]
    print(f"\nchosen on 2009-17: N={best[0]} top{best[1]}; test MAR {t['mar']:.2f} vs all three {tb['mar']:.2f}, DD {t['eq_dd']:.1%} ->",
          "better" if (t["mar"] > tb["mar"] and t["eq_dd"] <= 0.30) else "not better")


if __name__ == "__main__":
    main()
