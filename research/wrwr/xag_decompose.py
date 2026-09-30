"""Descriptive cost decomposition of the silver runs (Test B read-out, not an endpoint): for a configuration's live C2 path, the
weekly-R contributions of every realised trade split into gross move, round-trip cost and swap
(R_week = sum over exits of pnl / U_exit-week, pnl = R x stop dollars, R = (gross - cost - swap) / stop, all in bp of entry).
Usage: python research/wrwr/xag_decompose.py   -> data/wrwr/xag/decompose.csv"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import contracts as K  # noqa: E402
import portfolio as PF  # noqa: E402
import xag as X  # noqa: E402
import xag_run as XR  # noqa: E402


def decompose(P, z, j, label):
    ch = [[int(x) for x in w] for w in json.loads(str(z["champs"]))[str(j)]]
    vs = z["vol_scale"]
    log = []
    wr, eq, cnt = PF.simulate(P, ch, vs, f=0.01, log=log)
    cuts = P.cuts
    g = c_ = s_ = n_ = 0.0
    ntr = 0; longs = 0
    for (k, c, te, xt, lots, R_i, pnl, eqe) in log:
        kx = int(np.searchsorted(cuts, xt, side="left")) - 1               # exit week: exits in (cut_k, cut_k+1]
        if kx >= len(cuts) - 1:
            continue                                                       # still open when the data ends: not realised
        i = int(np.searchsorted(P.entry_t[c], te))
        sb = float(P.stop_bp[c][i]); U = 0.01 * eq[kx]
        stop_d = lots * float(P.stop_px[c][i]) * P.contract
        w = stop_d / U
        g += w * float(P.gross_bp[c][i]) / sb; c_ += w * float(P.cost_bp[c][i]) / sb; s_ += w * float(P.swap_bp[c][i]) / sb
        n_ += pnl / U; ntr += 1; longs += int(P.dir[c][i] > 0)
    act = z["active"]
    return dict(config=label, trades=ntr, long_share=longs / max(ntr, 1), gross_R=g, cost_R=-c_, swap_R=-s_, net_R=n_,
                net_check=float(wr[act].sum()), cost_per_trade_R=c_ / max(ntr, 1))


def main():
    X.patch_marks()
    rows = []
    for sigset, tfs in (("f2", XR.TFS), ("zoo", ["H1"])):
        z = np.load(XR.fam_path(sigset), allow_pickle=False)
        fam = json.loads(str(z["family"]))
        B1, cuts, _ = X.load_xag("H1")
        P = PF.load_pool(X.SYM, tfs, cuts, verify=True, loader=X.make_loader(sigset))
        act = z["active"]; R = z["R_0.01"][act]
        pick = {"zoo": {"zoo BASE": 0}, "f2": dict(XR.SHADOW)}[sigset]
        if sigset == "f2":
            pick["best total R (in-sample)"] = int(np.argmax(R.sum(0))); pick["worst total R"] = int(np.argmin(R.sum(0)))
        for nm, j in pick.items():
            c = fam[j]
            r = decompose(P, z, j, f"{nm} [{c['window']}w z{c['lcb_z']:g} {c['pool']} m{c['m']} eq{c['equity_filter']}]")
            rows.append(r)
            print(f"{r['config']:<52s} trades {r['trades']:5d} (long {r['long_share']:.0%}): gross {r['gross_R']:+8.1f}R  cost {r['cost_R']:+8.1f}R  "
                  f"swap {r['swap_R']:+6.1f}R  = net {r['net_R']:+7.1f}R (weekly sum {r['net_check']:+7.1f}); cost {r['cost_per_trade_R']:.3f} R/trade", flush=True)
    pd.DataFrame(rows).to_csv(X.OUT / "decompose.csv", index=False)


if __name__ == "__main__":
    main()
