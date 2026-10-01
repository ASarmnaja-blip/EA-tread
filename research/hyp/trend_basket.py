"""D1 short-term trend basket confirmation (docs/HYPOTHESIS_TREND_BASKET_PREREG.md): members selected on gold DEV only (explore_scale.csv D1 rows
kept by the DEV rule), judged on eight MT5 markets never used for selection. Usage: python research/hyp/trend_basket.py"""
from __future__ import annotations

import hashlib
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import batch1 as B1  # noqa: E402
import explore_scale as ES  # noqa: E402

ROOT = B1.ROOT
E = B1.E
MARKETS = {"EURUSD": 3, "USDJPY": 3, "AUDUSD": 3, "USDCHF": 3, "US500": 4, "USTEC": 4, "USOIL": 4, "BTCUSD": 10}
SHA = "fb9a68cdbb6034c7f3e7c57e30f44ca5f2fec3481bfaf92457c069fa33b671c0"


def mt5_bars(sym):
    z = np.load(ROOT / "data" / "mt5" / f"{sym}_D1.npz")
    B = B1.mkbars(z["t"], z["o"], z["h"], z["l"], z["c"], np.zeros(len(z["t"])), 86400)
    B.v = z["tick_volume"].astype(float)
    return B


def sim(B, e, d, k, hold, cost_bp):
    """One position at a time; gross by first passage (stop k ATR, time exit), net = gross - fixed round-trip cost, no swap."""
    ok = np.isfinite(B.atr[e]) & (B.atr[e] > 0) & (e + hold < len(B.t))
    e, d = e[ok], d[ok]
    if not len(e):
        return pd.DataFrame(columns=["t", "d", "R"])
    g, ex = E.simulate(B, e, d, k * B.atr[e], np.full(len(e), np.nan), e + hold - 1)
    take = np.zeros(len(e), bool); busy = -1
    for i in np.argsort(e, kind="stable"):
        if e[i] > busy:
            take[i] = True; busy = ex[i]
    sb = k * B.atr[e] / B.o[e] * 1e4
    return pd.DataFrame(dict(t=B.t[e][take], d=d[take], R=((g - cost_bp) / sb)[take]))


def weekly(tr, cuts):
    wk = np.searchsorted(cuts, tr.t.to_numpy(np.int64), side="left") - 1
    return pd.Series(tr.R.to_numpy(), index=wk).groupby(level=0).agg(["sum", "count"])


def main():
    t0 = time.time()
    f = B1.OUT / "explore_scale.csv"
    if hashlib.sha256(f.read_bytes()).hexdigest() != SHA:
        raise SystemExit("explore_scale.csv differs from the pre-registered file")
    X = pd.read_csv(f)
    mem = X[(X.tf == "D1") & (X.rule != "drop")][["signal", "direction", "k"]].reset_index(drop=True)
    print(f"basket: {len(mem)} D1 members selected on gold DEV")
    _, cuts = ES.bars("XAUUSD")
    pooled = {}
    res = {}
    for sym, cost in MARKETS.items():
        B = mt5_bars(sym)
        sig = ES.signals(B, cuts)
        ws, wc = {}, {}
        for _, m in mem.iterrows():
            if m.signal not in sig:
                continue
            e, d = ES.events(sig[m.signal], B)
            sgn = 1.0 if m.direction == "follow" else -1.0; k = float(m.k); hold = int(5 * k)
            tr = sim(B, e, sgn * d, k, hold, cost)
            if len(tr) < 5:
                continue
            ls = float((tr.d > 0).mean())
            ee = np.arange(30, len(B.t) - hold - 1)                                   # random timing: every D1 open, same direction mix
            cl = sim(B, ee, np.ones(len(ee)), k, hold, cost); cs = sim(B, ee, -np.ones(len(ee)), k, hold, cost)
            ctl = ls * float(cl.R.mean()) + (1 - ls) * float(cs.R.mean())
            w = weekly(tr, cuts)
            ws[m.signal] = w["sum"]; wc[m.signal] = w["sum"] - w["count"] * ctl
        R = pd.DataFrame(ws).fillna(0.0).mean(1); D = pd.DataFrame(wc).fillna(0.0).mean(1)
        lo, hi = int(R.index.min()), int(R.index.max())
        R = R.reindex(range(lo, hi + 1), fill_value=0.0); D = D.reindex(range(lo, hi + 1), fill_value=0.0)
        mR, pR = B1.boot_p(R.to_numpy(), np.ones(len(R))); mD, pD = B1.boot_p(D.to_numpy(), np.ones(len(D)))
        res[sym] = dict(weeks=len(R), members=len(ws), mean_R=mR, p_R=pR, mean_excess=mD, p_excess=pD, total_R=float(R.sum()))
        pooled[sym] = D
        print(f"{sym:<7s} {len(ws):2d} members, {len(R)} weeks: basket mean {mR:+.4f} R/wk (p {pR:.3f}), total {R.sum():+.1f} R; "
              f"excess over random timing {mD:+.4f} R/wk (p {pD:.3f}) ({time.time() - t0:.0f}s)", flush=True)
    P = pd.DataFrame(pooled).mean(1).dropna()
    mP, pP = B1.boot_p(P.to_numpy(), np.ones(len(P)))
    res["POOLED"] = dict(weeks=len(P), mean_excess=mP, p_excess=pP, PASS=bool(mP > 0 and pP <= 0.05))
    print(f"\nPRIMARY pooled over 8 markets: mean weekly excess {mP:+.4f} R (p {pP:.3f}) over {len(P)} weeks -> {'PASS' if res['POOLED']['PASS'] else 'FAIL'}")
    (B1.OUT / "trend_basket.json").write_text(json.dumps(res, indent=1, default=float))


if __name__ == "__main__":
    main()
