#!/usr/bin/env python3
"""Stage 2, layer L2 (ledger fresh_markets_search_v2): the full G27K grid of
27,648 setups (research/grid27k/g27k.py; simulate via the numba port g27k_fast.py, checked equal trade by trade) on group A, H4,
discovery 2012-01..2019-12 and validation 2020-01..2023-12. Data from
2024-01-01 on is cut at load (sealed holdout). Per setup: pooled per-trade net
R, its t, and the share of markets positive, in each period.

Usage: python3 research/g27k_dev/fresh_search_l2.py --root <snap> real [--workers 4]
       python3 research/g27k_dev/fresh_search_l2.py --root <snap> placebo <first> <count> [--workers 4]
"""
import argparse
import sys
import time
from multiprocessing import Pool

import numpy as np
import pandas as pd

import pathlib
HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))
import fresh_markets as FM
import fresh_search_l3 as L3
import g27k_fast as GF
import h4d1_pattern_search as P
import per_market_search as PMS
import walkforward_controller as W

_W = {}


def _init(root, h1s):
    P.setup(root)
    K, C = P._M["K"], P._M["C"]
    C.SPECS.update(FM.specs(C))
    K.START, K.SPLIT = W.ts(L3.D0), W.ts(L3.SPLIT)
    ext = K.externals()
    _W["K"] = K
    _W["nights"] = C.nights
    _W["M"] = {m: K.prepare(m, b, ext, "H4") for m, b in h1s.items()}


def _stats(R):
    n = len(R)
    if n < 3 or R.std(ddof=1) == 0:
        return n, (float(R.mean()) if n else np.nan), np.nan
    return n, float(R.mean()), float(R.mean() / R.std(ddof=1) * np.sqrt(n))


def _task(sig):
    K, Ms = _W["K"], _W["M"]
    Cc, D, E, J = sig
    dirs = {}
    for m, M in Ms.items():
        d = K.directions(M, Cc, D, E, J)
        s = np.flatnonzero(d)
        dirs[m] = (s, d[s])
    out = []
    split = K.SPLIT
    for Fm, Gm, Hm, Im in K.SIM:
        te, R, mk = [], [], []
        for m in Ms:
            for x in GF.simulate(Ms[m], *dirs[m], Fm, Gm, Hm, Im, _W["nights"]):
                te.append(x[0]); R.append(x[2]); mk.append(m)
        te, R, mk = np.array(te, np.int64), np.array(R, float), np.array(mk)
        row = dict(combo="/".join((Cc, D, E, Fm, Gm, Hm, Im, J)))
        for nm, sel in (("disc", te < split), ("val", te >= split)):
            n, mu, t = _stats(R[sel])
            row.update({f"n_{nm}": n, f"R_{nm}": mu, f"t_{nm}": t})
            if nm == "val" and n:
                pm = pd.Series(R[sel]).groupby(mk[sel]).sum()
                row["val_pos_share"] = float((pm > 0).mean())
        out.append(row)
    return out


def run(root, h1s, label, workers):
    t0 = time.time()
    import itertools
    CS = ("C1", "C2", "C3", "C4", "C5", "C6", "C7", "C8"); DS = tuple(f"D{i}" for i in range(1, 9))
    sigs = list(itertools.product(CS, DS, ("E1", "E2", "E3"), ("J1", "J2")))
    rows = []
    with Pool(workers, initializer=_init, initargs=(root, h1s)) as pool:
        for i, r in enumerate(pool.imap_unordered(_task, sigs, chunksize=1)):
            rows += r
            if (i + 1) % 48 == 0:
                print(f"  [{label}] {i + 1}/{len(sigs)} signal sets  {time.time() - t0:.0f}s", flush=True)
    D = pd.DataFrame(rows)
    D.to_parquet(PMS.CACHE / f"fresh_l2_{label}.parquet")
    ok = D[D.n_disc >= 300].sort_values("t_disc", ascending=False)
    print(f"  [{label}] {len(D):,} setups; with n_disc >= 300: {len(ok):,}; top-1 disc t {ok.t_disc.iloc[0]:.2f}; "
          f"top-100 median {ok.t_disc.head(100).median():.2f}  {time.time() - t0:.0f}s", flush=True)
    return D


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    ap.add_argument("mode", choices=("real", "placebo", "probe"))
    ap.add_argument("first", nargs="?", type=int, default=0)
    ap.add_argument("count", nargs="?", type=int, default=1)
    ap.add_argument("--workers", type=int, default=4)
    a = ap.parse_args()
    h1 = {m: L3.load(m) for m in L3.GROUP_A}
    if a.mode == "probe":
        _init(a.root, h1)
        t0 = time.time()
        r = _task(("C8", "D3", "E1", "J1"))
        print(f"  one signal set (72 setups) on {len(h1)} markets: {time.time() - t0:.1f}s; e.g. {r[0]}")
    elif a.mode == "real":
        run(a.root, h1, "real", a.workers)
    else:
        P.setup(a.root)
        P._M["h1"] = h1
        for p in range(a.first, a.first + a.count):
            run(a.root, P.drift_placebo(p), f"drift{p}", a.workers)


if __name__ == "__main__":
    main()
