"""TF sweep (docs/plans/TF_SWEEP_PREREG.md): the report768 system on M5, M15, M30, H1, H4, D1 and W1 for gold, silver and BTC.
20-bar breakout, long only, higher timeframe agreeing (M5->H1, M15/M30->H4, H1/H4->D1, D1->W1, W1->MN), stop 2 x ATR20, exit on the
opposite 20-bar channel; A = Turtle adds up to 4 units at 0.25 % per unit, B = one unit at 1 % per trade; entries 2021-10-01..2026-09-30.
Gold and silver M5..H1 come from the Candle Lab M5 bars (stops and adds walk M5), H4/D1/W1 from MT5 H1 (as in the report, walk H1), BTC
M5..H1 from MT5 bars of that timeframe (no finer bars: a bar that adds and trades through the raised stop is stopped). Writes
data/grid768/tf_sweep.json."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import g768 as G  # noqa: E402
import report768 as RP  # noqa: E402

ROOT = G.ROOT
MKTS = ["XAUUSD", "XAGUSD", "BTCUSD"]
TFS = ["M5", "M15", "M30", "H1", "H4", "D1", "W1"]
SEC = {"M5": 300, "M15": 900, "M30": 1800, "H1": 3600, "H4": 14400, "D1": 86400, "W1": 7 * 86400, "MN": 31 * 86400}
ANCHOR = {"M5": "H1", "M15": "H4", "M30": "H4", "H1": "D1", "H4": "D1", "D1": "W1", "W1": "MN"}
SYSTEMS = {"A": ("I4", 0.0025), "B": ("I1", 0.01)}
BIG = np.iinfo(np.int64).max


def load_npz(path):
    z = np.load(path)
    v = z["tick_volume"] if "tick_volume" in z.files else z["v"]
    return dict(t=z["t"].astype(np.int64), o=z["o"].astype(float), h=z["h"].astype(float), l=z["l"].astype(float), c=z["c"].astype(float),
                v=v.astype(float), step=0)


def key(t, tf):
    if tf == "H4":
        return (t - 22 * 3600) // 14400
    if tf == "W1":
        return np.searchsorted(G.CUTS, t, side="right") - 1
    if tf == "MN":
        return t.astype("datetime64[s]").astype("datetime64[M]").astype(np.int64)
    return t // SEC[tf]


def sources(m, tf):
    """(bars the timeframe is built from and walked on, bars its anchor is built from, label)."""
    if tf in ("H4", "D1", "W1") or (m == "BTCUSD" and tf == "H1"):
        h1 = G.load_h1(m); return h1, h1, "MT5 H1"
    if m in ("XAUUSD", "XAGUSD"):
        b = load_npz(ROOT / "data" / "bundle" / f"bars_{m}_M5.npz"); return b, b, "Candle Lab M5"
    return load_npz(ROOT / "data" / "bundle" / "mt5" / f"{m}_{tf}.npz"), G.load_h1(m), f"MT5 {tf}"


def anchor_dir(X, A, x_sec, a_sec):
    """Direction of the last anchor bar closed by each bar's close: anchor close vs the midline of its 55-bar Donchian channel."""
    ac = np.minimum(np.r_[A["t"][1:], BIG], A["t"] + a_sec); xc = np.minimum(np.r_[X["t"][1:], BIG], X["t"] + x_sec)
    j = np.searchsorted(ac, xc, side="right") - 1; jj = np.maximum(j, 0)
    mid = (pd.Series(A["h"]).rolling(55).max() + pd.Series(A["l"]).rolling(55).min()).to_numpy() / 2
    with np.errstate(invalid="ignore"):
        v = np.where(j >= 0, np.sign(A["c"][jj] - mid[jj]), 0)
    return np.nan_to_num(v).astype(int)


def frame(m, tf):
    b, ab, label = sources(m, tf)
    if tf in ("H4", "D1"):
        X = G.features(G.frames(b), m, tf)                    # the grid and report code path
    else:
        X = G.agg(b, key(b["t"], tf)); A = G.agg(ab, key(ab["t"], ANCHOR[tf]))
        X["dhi"] = pd.Series(X["h"]).rolling(20).max().shift(1).to_numpy(); X["dlo"] = pd.Series(X["l"]).rolling(20).min().shift(1).to_numpy()
        X["htf"] = anchor_dir(X, A, SEC[tf], SEC[ANCHOR[tf]])
    X["sec"] = SEC[tf]
    return X, label


def trades_for(X, m, I):
    d = G.signals(X, "D1", None)
    s = np.flatnonzero((d > 0) & (X["t"] >= G.START) & (X["htf"] == d))
    return [dict(tr, X=X) for tr in RP.sim_paths(X, m, s, d[s], I)]


def brief(rows, T, risk, start):
    M = RP.metrics(rows, T, risk, start=start)
    cost = np.array([r["R_spread"] + r["R_swap"] for r in rows])
    return dict(n=M["trades"], per_year=M["trades"] / M["years"], win=M["win_n"] / M["trades"], pf=M["pf"], ret=M["net"] / RP.DEPOSIT,
                cagr=M["cagr"], eq_dd=M["equity_dd"]["relative_pct"], bal_dd=M["balance_dd"]["relative_pct"], R=M["total_R"], avgR=M["avg_R"],
                gross_avgR=M["gross_R"] / M["trades"], cost_avgR=float(cost.mean()), years=M["years"], start=M["start"] if start is None else
                str(pd.Timestamp(int(start), unit="s").date()), yearly={y["year"]: y["ret"] for y in M["yearly"]}, top1=M["top1_share"],
                hold_h=M["hold_avg_h"])


def buy_hold():
    out = {}; paths = []
    for m in MKTS:
        D = G.load_h1(m); t, c = D["t"], D["c"]
        i0 = int(np.searchsorted(t, G.START)); p = c[i0:] / c[i0]
        s = pd.Series(p, index=pd.to_datetime(t[i0:], unit="s")).resample("D").last().dropna(); paths.append(s)
        out[m] = dict(ret=float(s.iloc[-1] - 1), dd=float(((s.cummax() - s) / s.cummax()).max()))
    B = pd.concat(paths, axis=1).ffill().dropna().mean(axis=1)
    yrs = (B.index[-1] - B.index[0]).days / 365.25
    out["MET3"] = dict(ret=float(B.iloc[-1] - 1), cagr=float(B.iloc[-1] ** (1 / yrs) - 1), dd=float(((B.cummax() - B) / B.cummax()).max()))
    return out


def main():
    res = dict(buy_hold=buy_hold(), tfs={})
    for tf in TFS:
        Xs, labels = {}, {}
        for m in MKTS:
            Xs[m], labels[m] = frame(m, tf)
        row = dict(sources=labels)
        for k, (I, risk) in SYSTEMS.items():
            tr = {m: trades_for(Xs[m], m, I) for m in MKTS}
            allt = [r for m in MKTS for r in tr[m]]
            T = RP.timeline(allt, Xs); RP.prep_marks(allt, T)
            first = {m: max(G.START, int(Xs[m]["t"][min(len(Xs[m]["t"]) - 1, 60)])) for m in MKTS}
            out = {m: brief(RP.account(tr[m], risk), T, risk, first[m]) for m in MKTS if tr[m]}
            out["MET3"] = brief(RP.account(allt, risk), T, risk, G.START)
            row[k] = out
            print(f"{tf:3s} {k}: " + "  ".join(f"{m} {v['ret']:+.0%} ({v['cagr']:+.0%}/y, DD {v['eq_dd']:.0%}, {v['n']} tr, avgR {v['avgR']:+.2f}, cost {v['cost_avgR']:.2f})"
                                               for m, v in out.items()), flush=True)
        res["tfs"][tf] = row
    (G.OUT / "tf_sweep.json").write_text(json.dumps(res, ensure_ascii=False), encoding="utf-8")
    print("buy & hold:", json.dumps(res["buy_hold"]))


if __name__ == "__main__":
    main()
