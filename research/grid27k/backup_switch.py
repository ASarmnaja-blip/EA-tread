"""Backup plan and switch rules (docs/plans/BACKUP_SWITCH_PREREG.md). P = G27K setup 1; S = the same, longs only while D1 and W1 are
both up. K1: per market, P while W1 is up, S (no new longs) while W1 is down. K2: champion/challenger on the trailing six months of
shadow R (switch to S when P's is negative and below S's, back when P's turns positive). Gold, silver 2009-09.., BTC 2018-03..; 1 % per
trade; one open trade per market."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent / "grid768")]
import complement as CP  # noqa: E402
import g27k as K  # noqa: E402
import g768 as G  # noqa: E402
import stress_top3 as S  # noqa: E402

C = G.C
WINDOWS = [("all 2009-09..2026-09", "2009-09-01", None), ("metals bear 2011-09..2015-12", "2011-09-01", "2016-01-01"), ("2013", "2013-01-01", "2014-01-01"),
           ("2018", "2018-01-01", "2019-01-01"), ("2022", "2022-01-01", "2023-01-01"), ("last five years 2021-10..2026-09", "2021-10-01", None)]


def no_overlap(trades):
    busy = {}; out = []
    for r in sorted(trades, key=lambda x: (x["t"], x["mkt"])):
        if busy.get(r["mkt"], -1) > r["t"]:
            continue
        out.append(r); busy[r["mkt"]] = r["t_exit"]
    return out


def main():
    K.START = CP.FIRST
    ext = K.externals(); Ms, Xs, W1, D1 = {}, {}, {}, {}
    for m in K.MKTS:
        h1 = S.spliced_h1(m); Ms[m] = K.prepare(m, h1, ext); F = G.frames(h1); X = G.features(F, m, "H4"); X["sec"] = 14400
        CP.extras(m, h1, X, Ms[m]); Xs[m] = X
        W1[m] = K.anchor(X, F["W1"], 14400, 7 * 86400); D1[m] = Ms[m]["d1"]
    plans = {"P": {}, "S": {}, "K1": {}}
    for m in K.MKTS:
        d = K.directions(Ms[m], "C8", "D3", "E1", "J1")
        dS = d.copy(); dS[~Ms[m]["Cl"]["C3"]] = 0
        dK = d.copy(); dK[~(W1[m] > 0)] = 0
        for nm, dd in (("P", d), ("S", dS), ("K1", dK)):
            s = np.flatnonzero(dd); plans[nm][m] = CP.sim(Xs[m], m, s, dd[s], 2.0, "ch20")
    tr = {nm: [x for m in K.MKTS for x in v[m]] for nm, v in plans.items()}
    mP, mS = CP.monthly(tr["P"]), CP.monthly(tr["S"])
    months = pd.period_range(pd.Timestamp(CP.FIRST, unit="s").to_period("M"), pd.Timestamp(max(x["t"] for x in tr["P"]), unit="s").to_period("M"), freq="M")
    champ = "P"; mode = {}
    for mo in months:
        win = pd.period_range(mo - 6, mo - 1, freq="M")
        rp, rs = float(mP.reindex(win).fillna(0).sum()), float(mS.reindex(win).fillna(0).sum())
        if champ == "P" and rp < 0 and rs > rp:
            champ = "S"
        elif champ == "S" and rp > 0:
            champ = "P"
        mode[mo] = champ
    pick = [x for nm in ("P", "S") for x in tr[nm] if mode.get(pd.Timestamp(x["t"], unit="s").to_period("M")) == nm]
    tr["K2"] = no_overlap(pick)
    s_months = [str(k) for k, v in mode.items() if v == "S"]
    spans = []
    for k, v in mode.items():
        if v == "S" and (not spans or spans[-1][1] != str(k - 1)):
            spans.append([str(k), str(k)])
        elif v == "S":
            spans[-1][1] = str(k)
    print(f"K2 used S in {len(s_months)} of {len(mode)} months: {', '.join(a if a == b else a + '..' + b for a, b in spans)}")
    rows = []
    for wname, a, b in WINDOWS:
        for nm in ("P", "S", "K1", "K2"):
            R = S.account_window(tr[nm], 0.01, C.ts(a), C.ts(b) if b else None, Xs)
            if R is None:
                continue
            rows.append(dict(window=wname, plan=nm, **{k: v for k, v in R.items() if k != "by_mkt"}))
            print(f"{wname:34s} | {nm:2s} | trades {R['n']:4d} total {R['ret']:+7.0%} CAGR {R['cagr']:+6.1%} equity DD {R['eq_dd']:5.1%} balance DD {R['bal_dd']:5.1%}"
                  f" low {R['low']:4.0%} | PF {R['pf']:.2f} | underwater {R['under']:5.0f}d")
    now = {m: dict(W1="up" if W1[m][-1] > 0 else "down", D1="up" if D1[m][-1] > 0 else "down",
                   K1="P" if W1[m][-1] > 0 else "S (no new longs)", S_allows="yes" if (W1[m][-1] > 0 and D1[m][-1] > 0) else "no") for m in K.MKTS}
    last = months[-1]; win = pd.period_range(last - 5, last, freq="M")
    nxt = dict(P_6m=float(mP.reindex(win).fillna(0).sum()), S_6m=float(mS.reindex(win).fillna(0).sum()), champion_now=mode[last])
    print("now (last bar", pd.Timestamp(int(Xs["XAUUSD"]["t"][-1]), unit="s"), "):", json.dumps(now), "| K2:", json.dumps(nxt))
    (K.OUT / "backup_switch.json").write_text(json.dumps(dict(rows=rows, s_spans=spans, now=now, k2=nxt), ensure_ascii=False, default=float, indent=1),
                                               encoding="utf-8")


if __name__ == "__main__":
    main()
