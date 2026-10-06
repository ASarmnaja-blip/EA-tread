#!/usr/bin/env python3
"""Gate 1 of the H4 trend plan: is the 17-year profit timing, or just drift?

Runs the other branch's own code unchanged (research/grid27k on the
data-snapshot-2026-10-02 branch) on the real 2009-2026 H1 history and on
placebo histories:

  DRIFT     every H1 bar's direction flipped at random around the previous
            close after removing the market's average log drift, then the
            drift put back. Volatility, clock and the average upward trend
            survive; any timing an entry or exit rule could exploit does not.
  NO-DRIFT  the same flip without restoring the drift.

If the real result sits inside the drift-placebo range, a buy-only system
earned what being long a rising asset earns, and its rules added nothing.

Usage: python3 h4_placebo.py --root <checkout of data-snapshot-2026-10-02>
"""
import argparse
import json
import pathlib
import sys
import time
import warnings
from multiprocessing import Pool

import numpy as np

warnings.filterwarnings("ignore")
HERE = pathlib.Path(__file__).parent
N_DRIFT, N_FLAT = 100, 30
SYSTEMS = {"H4-1": ("H4", "C8", "D3"), "D1-1": ("D1", "C2", "D1"),
           "H4-55": ("H4", "C4", "D2")}
COMBOS = {"H4-55": ["H4-55"], "D1-1": ["D1-1"], "pair": ["H4-55", "D1-1"],
          "H4-1": ["H4-1"]}
_M = {}


def setup(root):
    g = pathlib.Path(root) / "research" / "grid27k"
    sys.path[:0] = [str(g), str(g.parent / "grid768"), str(g.parent / "candlelab")]
    import complement as CP
    import g27k as K
    import g768 as G
    import lab as L
    import stress_top3 as S
    K.START = CP.FIRST
    _M.update(CP=CP, K=K, G=G, L=L, S=S, ext=K.externals(),
              h1={m: S.spliced_h1(m) for m in K.MKTS})


def transform(kind, p):
    L = _M["L"]
    out = {}
    for i, (m, b) in enumerate(_M["h1"].items()):
        if kind == "real":
            out[m] = b
        elif kind == "flat":
            out[m] = L.mirror_base(b, 27000 + 100 * p + i)
        else:
            mu = np.mean(np.diff(np.log(b["c"])))
            tr = np.exp(mu * np.arange(len(b["c"])))
            det = dict(b, o=b["o"] / tr, h=b["h"] / tr, l=b["l"] / tr, c=b["c"] / tr)
            mb = L.mirror_base(det, 29000 + 100 * p + i)
            out[m] = dict(mb, o=mb["o"] * tr, h=mb["h"] * tr, l=mb["l"] * tr,
                          c=mb["c"] * tr)
    return out


def run_path(args):
    kind, p = args
    CP, K, G, C = _M["CP"], _M["K"], _M["G"], _M["G"].C
    t_split = C.ts("2017-01-01")
    trades = {s: [] for s in SYSTEMS}
    hold = {}
    for m, h1 in transform(kind, p).items():
        F = G.frames(h1)
        for tf, sec in (("H4", 14400), ("D1", 86400)):
            M = K.prepare(m, h1, _M["ext"], tf)
            X = G.features(F, m, tf)
            X["sec"] = sec
            CP.extras(m, h1, X, M)
            for name, (stf, Cc, D) in SYSTEMS.items():
                if stf != tf:
                    continue
                d = K.directions(M, Cc, D, "E1", "J1")
                s = np.flatnonzero(d)
                trades[name] += [(r["t"], r["R"], m)
                                 for r in CP.sim(X, m, s, d[s], 2.0, "ch20")]
        c = h1["c"]
        ok = h1["t"] >= K.START
        hold[m] = float(np.log(c[ok][-1] / c[ok][0]))
    res = dict(kind=kind, p=p, hold_log=hold)
    for combo, parts in COMBOS.items():
        R = [(t, r, m) for nm in parts for (t, r, m) in trades[nm]]
        res[combo] = dict(
            n=len(R), totR=float(sum(r for _, r, _ in R)),
            totR_early=float(sum(r for t, r, _ in R if t < t_split)),
            by_mkt={m: float(sum(r for _, r, mm in R if mm == m))
                    for m in K.MKTS})
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    ap.add_argument("--workers", type=int, default=4)
    a = ap.parse_args()
    t0 = time.time()
    jobs = ([("real", 0)] + [("drift", p) for p in range(N_DRIFT)]
            + [("flat", p) for p in range(N_FLAT)])
    out = []
    with Pool(a.workers, initializer=setup, initargs=(a.root,)) as pool:
        for i, r in enumerate(pool.imap_unordered(run_path, jobs)):
            out.append(r)
            if (i + 1) % 10 == 0:
                print(f"  {i + 1}/{len(jobs)} paths  {time.time() - t0:.0f}s",
                      flush=True)

    real = next(r for r in out if r["kind"] == "real")
    summary = {}
    print("\nH4 TREND PLAN - GATE 1: REAL vs PLACEBO, total R of trades "
          "2009-09..2026-09")
    print("=" * 100)
    for combo in COMBOS:
        row = dict(real=real[combo]["totR"], real_early=real[combo]["totR_early"],
                   real_n=real[combo]["n"], real_by_mkt=real[combo]["by_mkt"])
        for kind in ("drift", "flat"):
            v = np.array([r[combo]["totR"] for r in out if r["kind"] == kind])
            ve = np.array([r[combo]["totR_early"] for r in out if r["kind"] == kind])
            row[kind] = dict(
                median=float(np.median(v)), p95=float(np.percentile(v, 95)),
                max=float(v.max()),
                p_value=float((1 + (v >= row["real"]).sum()) / (1 + len(v))),
                early_median=float(np.median(ve)),
                early_p95=float(np.percentile(ve, 95)),
                early_p=float((1 + (ve >= row["real_early"]).sum()) / (1 + len(ve))))
        row["pass"] = bool(row["real"] > row["drift"]["p95"])
        summary[combo] = row
        d, f = row["drift"], row["flat"]
        print(f"  {combo:<6} real {row['real']:+7.0f}R ({row['real_n']} trades) | "
              f"drift placebo median {d['median']:+6.0f}R p95 {d['p95']:+6.0f}R "
              f"max {d['max']:+6.0f}R  p={d['p_value']:.3f} | "
              f"no-drift median {f['median']:+5.0f}R p={f['p_value']:.3f}  "
              f"{'PASS' if row['pass'] else 'FAIL'}")
        print(f"         2009-2016 only: real {row['real_early']:+6.0f}R | "
              f"drift median {d['early_median']:+5.0f}R p95 {d['early_p95']:+5.0f}R "
              f"p={d['early_p']:.3f}")
    gate = summary["H4-55"]["pass"] and summary["pair"]["pass"]
    print(f"\n  GATE 1 (H4-55 and the pair both above the drift p95): "
          f"{'PASSED' if gate else 'NOT PASSED'}")
    print(f"  buy-and-hold log return of the real data: "
          + ", ".join(f"{m} {v:+.2f}" for m, v in real["hold_log"].items()))

    (HERE / "h4_placebo.json").write_text(json.dumps(dict(
        created=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        n_drift=N_DRIFT, n_flat=N_FLAT, systems=SYSTEMS, summary=summary,
        gate_passed=gate, paths=out), indent=1, default=str))
    print(f"\n  saved -> h4_placebo.json   elapsed {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
