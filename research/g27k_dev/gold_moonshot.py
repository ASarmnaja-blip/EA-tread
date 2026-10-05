#!/usr/bin/env python3
"""Experiment only, never for live use: gold, 100% of the balance at risk on
every trade, take profit at 5 / 7.5 / 10R so a win pays +500..+1000% of the
capital, every win withdrawn, every loss a blow-up followed by a new deposit
of the capital. Scored on the last 3 months (2026-07-01..2026-09-30); the
same settings over 2011-09..2026-09 are printed next to it.

Signals on XAUUSD M5 and M15 (bars from Dukascopy M1 mid, h4d1_pattern_search
features), one trade at a time:
  valid   pos250>=0.9 & atr_ratio>=1.5 & htf1_with (the M15 family candidate)
  m30rule brk55>=-1 & atr_ratio>=1.5 & htf1_with (the M30 sleeve rule)
  trend   brk55>=-1 & htf1_with
  every   brk20>=0 (every close beyond the 20-bar extreme, both ways)
Entry at the next bar's open, stop 2 x ATR20 of the signal timeframe, target
k x that distance, walked on M1 (stop first if both in one minute). Cost:
the G27K spread model (2 bp of price per round trip) plus swap per night.

Usage: python3 research/g27k_dev/gold_moonshot.py --root <snap>
"""
import argparse
import json
import pathlib
import sys

import numpy as np
import pandas as pd
from numba import njit

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))
import h4d1_pattern_search as P
import m30_new_markets as NM
import walkforward_controller as W

P.TF_SEC.setdefault("M5", 300)
TFS = ("M5", "M15")
KS = (5.0, 7.5, 10.0)
LAST = ("2026-07-01", "2026-10-01")
FULL = ("2011-09-01", "2026-10-01")
SIGNALS = {"valid": lambda f, c: (f["pos250"] >= 0.9) & (f["atr_ratio"] >= 1.5) & c["htf1_with"],
           "m30rule": lambda f, c: (f["brk55"] >= -1.0) & (f["atr_ratio"] >= 1.5) & c["htf1_with"],
           "trend": lambda f, c: (f["brk55"] >= -1.0) & c["htf1_with"],
           "every": lambda f, c: f["brk20"] >= 0.0}


@njit(cache=True)
def _walk(bo, bh, bl, q0, stop, tp, d):
    """First M1 minute from q0 that reaches the stop (checked first) or the target: (minute, price) or (-1, nan)."""
    for q in range(q0, len(bo)):
        if (d > 0 and bl[q] <= stop) or (d < 0 and bh[q] >= stop):
            return q, (stop if d * (bo[q] - stop) > 0 else bo[q])
        if (d > 0 and bh[q] >= tp) or (d < 0 and bl[q] <= tp):
            return q, (tp if d * (tp - bo[q]) > 0 else bo[q])
    return -1, np.nan


def walk(X, s, d, k, spec, C):
    """One trade from signal bar s in direction d with target k R: (entry time, exit time, R)."""
    o, a20, t = X["o"], X["a20"], X["t"]
    b = X["b"]
    e = s + 1
    if e >= len(o) or not np.isfinite(a20[s]) or a20[s] <= 0:
        return None
    ep, risk = o[e], 2.0 * a20[s]
    q, px = _walk(b["o"], b["h"], b["l"], int(X["k0"][e]), ep - d * risk, ep + d * k * risk, float(d))
    if q < 0:
        return None
    tx = int(b["t"][q])
    nts = float(C.nights(np.array([t[e]]), np.array([tx]), spec["rollover3"])[0])
    swr = (spec["swap_long_bp"] if d > 0 else spec["swap_short_bp"]) / 1e4
    R = (d * (px - ep) - ep * spec["cost_rt_bp"] / 1e4 - ep * swr * nts) / risk
    return int(t[e]), tx, float(R)


def trades(E, X, mask, k, spec, C, t0, t1):
    """Signals in time order, one trade at a time, entries inside [t0, t1)."""
    idx = np.flatnonzero(mask & (E["t"] >= t0) & (E["t"] < t1))
    idx = idx[np.argsort(E["t"][idx], kind="stable")]
    out, busy = [], -1
    for i in idx:
        if E["t"][i] < busy:
            continue
        r = walk(X, int(E["s"][i]), int(E["d"][i]), k, spec, C)
        if r is None:
            continue
        out.append(r)
        busy = r[1]
    return out


def account(T):
    """100% risk, wins withdrawn, a loss below 10% of the capital = blow-up and a new deposit."""
    bal, wd, dep, blow, best = 1.0, 0.0, 1.0, 0, 0.0
    for _, _, R in T:
        bal += bal * R
        best = max(best, R)
        if bal > 1.0:
            wd += bal - 1.0
            bal = 1.0
        if bal < 0.10:
            blow += 1
            dep += 1.0
            bal = 1.0
    n = len(T)
    wins = sum(1 for _, _, R in T if R > 0)
    return dict(trades=n, wins=wins, win=wins / n if n else float("nan"), blowups=blow, deposited=dep, withdrawn=wd,
                net=wd - dep + bal, best_trade=best, per_day=n / 92.0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    a = ap.parse_args()
    NM.prepare(a.root, ("XAUUSD",))
    C = P._M["C"]
    spec = C.SPECS["XAUUSD"]
    out = {}
    for tf in TFS:
        E, feats, cats = P.build(P._M["h1"], tf)
        X = P.FRAMES[("XAUUSD", tf)]
        for nm, fn in SIGNALS.items():
            m = np.asarray(fn(feats, cats), bool) & (E["mkt"] == "XAUUSD")
            for k in KS:
                res = {}
                for per, (s0, s1) in (("last3m", LAST), ("15y", FULL)):
                    res[per] = account(trades(E, X, m, k, spec, C, W.ts(s0), W.ts(s1)))
                out[f"{tf} {nm} {k:g}R"] = res
                l3, fy = res["last3m"], res["15y"]
                print(f"  {tf:3s} {nm:7s} TP {k:4.1f}R | last 3 months: {l3['trades']:4d} trades ({l3['per_day']:.1f}/day) win {l3['win']:5.1%} "
                      f"blow-ups {l3['blowups']:4d} | deposited x{l3['deposited']:.0f} withdrawn x{l3['withdrawn']:.1f} net x{l3['net']:+.1f} "
                      f"best +{l3['best_trade']:.0%} || 15y: {fy['trades']} trades win {fy['win']:.1%} net x{fy['net']:+.0f} "
                      f"(per trade {fy['net'] / max(fy['trades'], 1):+.2f})", flush=True)
        del E, feats, cats
    (HERE / "gold_moonshot.json").write_text(json.dumps(out, indent=1, default=float))


if __name__ == "__main__":
    main()
