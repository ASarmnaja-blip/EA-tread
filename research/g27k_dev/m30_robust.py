#!/usr/bin/env python3
"""Ledger m30_sleeve_new_markets, part 3: robustness of the final M30 sleeve
(original three markets plus those part 1 added), pooled non-overlapping
trades 2011-09..2026-09.

  (a) every trade 0.05 / 0.10 / 0.15R worse, and modelled cost x2
  (b) 18 neighbours: brk55 >= -0.75 / -1 / -1.25 x atr_ratio >= 1.25 / 1.5 /
      1.75 x with / without htf1_with
  (c) entry one M30 bar later (the signal bar's next event, its own ATR stop)
  (d) the same rule on 5 drift placebos of every sleeve market's M1
  (e) leave one market out
  (f) share of calendar years with positive mean R

ROBUST only if (b) >= 14 of 18 with net > 0 and t >= 2, (c) net > 0,
(d) real t above all 5 placebos, (e) net > 0 with each market left out,
(a) net > 0 at 0.10R worse.

Usage: python3 research/g27k_dev/m30_robust.py --root <snap> [--markets XAUUSD,...]
"""
import argparse
import itertools
import json
import pathlib
import sys
import time

import numpy as np
import pandas as pd

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))
import h4d1_pattern_search as P
import m30_new_markets as NM
import news_shock as NS

EX = NM.EX


def window(T):
    return T[(T.t >= NS.W.ts(NM.START)) & (T.t < NS.W.ts(NM.END))]


def st(T):
    return dict(n=int(len(T)), net=float(T.R.mean()), t=NM.tstat(T.R))


def delayed(E, mask):
    """Each selected event replaced by the same market and direction one bar later."""
    code = pd.factorize(E["mkt"])[0].astype(np.int64)
    key = (code * 2 + (E["d"] > 0)) * 10 ** 10 + E["s"].astype(np.int64)
    order = np.argsort(key, kind="stable")
    ks = key[order]
    want = key[np.flatnonzero(mask)] + 1
    pos = np.minimum(np.searchsorted(ks, want), len(ks) - 1)
    hit = ks[pos] == want
    m2 = np.zeros(len(mask), bool)
    m2[order[pos[hit]]] = True
    return P.no_overlap(E, m2 & np.isfinite(E[f"R_{EX}"]), EX)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    ap.add_argument("--markets", default="")
    ap.add_argument("--placebos", type=int, default=5)
    a = ap.parse_args()
    t0 = time.time()
    p1 = json.loads((HERE / "m30_new_markets.json").read_text())
    mk = a.markets.split(",") if a.markets else list(NM.OLD) + list(p1["added"])
    print(f"  final sleeve markets: {mk}", flush=True)
    NM.prepare(a.root, mk)
    E, feats, cats = P.build(P._M["h1"], "M30")
    base = window(NM.trades(E, P.no_overlap(E, NM.rule_mask(E, feats, cats), EX)))
    out = dict(markets=mk, base=st(base))
    print(f"  base: n {len(base)} net {base.R.mean():+.3f} t {NM.tstat(base.R):+.2f}", flush=True)
    # (a) costs
    cost = base.gross - base.R
    out["a"] = {f"-{x:.2f}R": st(base.assign(R=base.R - x)) for x in (0.05, 0.10, 0.15)}
    out["a"]["cost x2"] = st(base.assign(R=base.R - cost))
    out["a"]["median cost R"] = float(cost.median())
    for k, v in out["a"].items():
        print(f"  (a) {k}: {v}", flush=True)
    # (b) neighbours
    nb = []
    for brk, atr, htf in itertools.product((-0.75, -1.0, -1.25), (1.25, 1.5, 1.75), (True, False)):
        T = window(NM.trades(E, P.no_overlap(E, NM.rule_mask(E, feats, cats, brk, atr, htf), EX)))
        r = dict(brk=brk, atr=atr, htf=htf, **st(T), ok=bool(T.R.mean() > 0 and NM.tstat(T.R) >= 2))
        nb.append(r)
        print(f"  (b) brk55>={brk:+.2f} atr_ratio>={atr:.2f} htf1_with={htf!s:5s}: n {r['n']:5d} net {r['net']:+.3f} t {r['t']:+.2f} {'ok' if r['ok'] else '--'}", flush=True)
    out["b"] = dict(rows=nb, n_ok=sum(r["ok"] for r in nb))
    # (c) delayed entry
    D = window(NM.trades(E, delayed(E, NM.rule_mask(E, feats, cats))))
    out["c"] = st(D)
    print(f"  (c) one bar later: {out['c']}", flush=True)
    # (e) leave one out, (f) years, per market
    out["e"] = {m: st(base[base.mkt != m]) for m in mk}
    out["per_market"] = {m: st(base[base.mkt == m]) for m in mk}
    yr = base.groupby(pd.to_datetime(base.t, unit="s").dt.year).R.mean()
    out["f"] = dict(years={int(y): float(v) for y, v in yr.items()}, share_pos=float((yr > 0).mean()))
    print(f"  (e) leave one out: " + "  ".join(f"-{m} {v['net']:+.3f}" for m, v in out["e"].items()), flush=True)
    print(f"  (f) positive years {out['f']['share_pos']:.0%}: " + " ".join(f"{y}:{v:+.2f}" for y, v in out["f"]["years"].items()), flush=True)
    del E, feats, cats
    # (d) drift placebos
    pl = []
    for p in range(a.placebos):
        Ep, fp, cp = P.build(P.drift_placebo(p), "M30")
        T = window(NM.trades(Ep, P.no_overlap(Ep, NM.rule_mask(Ep, fp, cp), EX)))
        pl.append(st(T))
        print(f"  (d) drift placebo {p}: {pl[-1]}  {time.time() - t0:.0f}s", flush=True)
        del Ep, fp, cp
    out["d"] = pl
    tb = out["base"]["t"]
    checks = dict(a=out["a"]["-0.10R"]["net"] > 0, b=out["b"]["n_ok"] >= 14, c=out["c"]["net"] > 0,
                  d=all(tb > x["t"] for x in pl), e=all(v["net"] > 0 for v in out["e"].values()))
    out["checks"] = checks
    out["robust"] = bool(all(checks.values()))
    print(f"  PART 3: {checks} -> {'ROBUST' if out['robust'] else 'NOT ROBUST'}  {time.time() - t0:.0f}s")
    (HERE / "m30_robust.json").write_text(json.dumps(out, indent=1, default=float))


if __name__ == "__main__":
    main()
