#!/usr/bin/env python3
"""Setups for down-trends and sideways markets on the G27K markets (ledger
regime_setups_down_side). Regime from the last D1 bar closed before the
signal: UP = close > SMA200 and SMA200 up over 20 days, DOWN = close < SMA200
and SMA200 down over 20 days, SIDE = neither.

  DN1  G27K #1 mirrored short, DOWN only (H4 close < prior-10 low; stop 2 ATR20;
       exit after an H4 close > prior-20 high)
  DN2  sell the rally, DOWN only (D1 close > highest close of the prior 5
       days; exit when the close is back below SMA5 or after 10 days; stop 2.5 ATR20)
  SD1  range fade, SIDE only, D1 (close outside SMA20 +- 2 sd; exit on the SMA20
       cross or after 10 bars; stop 2.5 ATR20)
  SD2  the same on H4

Usage: python3 research/g27k_dev/regime_setups.py --root <snap>
"""
import argparse
import json
import pathlib
import sys

import numpy as np
import pandas as pd

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))
import fresh_markets as FM
import fresh_search_l1 as L1
import h4d1_pattern_search as P
import multi_market_search as MMS
import suite as SU
import walkforward_controller as W

MKTS = ("XAUUSD", "XAGUSD", "BTCUSD", "JP225", "USDJPY", "ETHUSD")
S5 = ("XAUUSD", "XAGUSD", "BTCUSD", "JP225", "USDJPY")
S4U = ("XAUUSD", "XAGUSD", "BTCUSD", "USDJPY")
START, MID, END = "2011-09-01", "2019-01-01", "2026-10-01"
PSTART, PMID = "2011-09-01", "2018-01-01"
SETUPS = {
    "DN1": dict(fam="X", tf="H4", side=-1, regime="DOWN"),
    "DN2": dict(fam="F2x", tf="D1", side=-1, regime="DOWN"),
    "SD1": dict(fam="F3", tf="D1", z=2.0, regime="SIDE"),
    "SD2": dict(fam="F3", tf="H4", z=2.0, regime="SIDE"),
}
NDRAW = 200


def regime(Dd, tq):
    sma = Dd["sma200"]
    slope = sma - np.r_[np.full(20, np.nan), sma[:-20]]
    reg = np.where((Dd["c"] > sma) & (slope > 0), 1, np.where((Dd["c"] < sma) & (slope < 0), -1, 0)).astype(float)
    reg[~np.isfinite(sma) | ~np.isfinite(slope)] = np.nan
    return L1.daily_asof(Dd, tq, reg)


def signals(name, X, Dd):
    v = SETUPS[name]
    n = len(X["c"])
    c, S = X["c"], pd.Series
    tclose = X["t"] + (14400 if v["tf"] == "H4" else 86400)
    reg = regime(Dd, tclose)
    want = {"DOWN": -1, "SIDE": 0, "UP": 1}[v["regime"]]
    d = np.zeros(n, np.int8)
    if name == "DN1":
        lo10 = S(X["l"]).rolling(10).min().shift(1).to_numpy()
        d[c < lo10] = -1
    elif name == "DN2":
        hi5 = S(c).shift(1).rolling(5).max().to_numpy()
        d[c > hi5] = -1
    else:
        d[c < X["sma20"] - v["z"] * X["sd20"]] = 1
        d[c > X["sma20"] + v["z"] * X["sd20"]] = -1
    d[reg != want] = 0
    d[~np.isfinite(X["atr"])] = 0
    return d, reg


def simulate(name, X, m, d, C, t0, t1, idx=None, holds=None):
    v = SETUPS[name]
    n = len(X["c"])
    spec = C.SPECS[m]
    S = pd.Series
    hi20, lo20 = S(X["h"]).rolling(20).max().shift(1).to_numpy(), S(X["l"]).rolling(20).min().shift(1).to_numpy()
    if idx is None:
        idx = np.flatnonzero((d != 0) & (X["t"] >= t0) & (X["t"] < t1))
    out, busy = [], -1
    for q, s in enumerate(idx):
        dr = int(d[s])
        if s <= busy or s + 1 >= n or dr == 0:
            continue
        e = s + 1
        ep = X["o"][e]
        risk = (2.0 if name == "DN1" else 2.5) * X["atr"][s]
        if not risk > 0:
            continue
        stop = ep - dr * risk
        px, j = None, e
        while j < n:
            hit_day = X["l"][j] <= stop if dr > 0 else X["h"][j] >= stop
            for k in (range(X["k0"][j], X["k1"][j]) if hit_day else ()):
                if (dr > 0 and X["bl"][k] <= stop) or (dr < 0 and X["bh"][k] >= stop):
                    px = min(stop, X["bo"][k]) if dr > 0 else max(stop, X["bo"][k])
                    tx = X["bt"][k]
                    break
            if px is not None:
                break
            held = j - e + 1
            cj = X["c"][j]
            if holds is not None:
                ex = held >= holds[q]
            elif name == "DN1":
                ex = cj > hi20[j]
            elif name == "DN2":
                ex = cj < X["sma5"][j] or held >= 10
            else:
                ex = ((cj >= X["sma20"][j]) if dr > 0 else (cj <= X["sma20"][j])) or held >= 10
            if ex and j + 1 < n:
                j += 1
                px, tx = X["o"][j], X["t"][j]
                break
            j += 1
        if px is None:
            break
        nights = int(C.nights(np.array([X["t"][e]]), np.array([tx]), spec["rollover3"])[0])
        sw = spec["swap_long_bp"] if dr > 0 else spec["swap_short_bp"]
        R = dr * (px - ep) / risk - (spec["cost_rt_bp"] + sw * nights) * 1e-4 * ep / risk
        out.append(dict(mkt=m, t=int(X["t"][e]), tx=int(tx), R=float(R), d=dr, hold=int(j - e), s=int(s)))
        busy = j
    return out


def tstat(x):
    x = np.asarray(x, float)
    return float(x.mean() / x.std(ddof=1) * np.sqrt(len(x))) if len(x) > 2 and x.std() > 0 else float("nan")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    a = ap.parse_args()
    P.setup(a.root)
    G, K, C = P._M["G"], P._M["K"], P._M["C"]
    sys.path.insert(0, str(pathlib.Path(a.root) / "research" / "grid768"))
    import report768 as RP
    C.SPECS["ETHUSD"] = dict(C.SPECS["BTCUSD"])
    H1 = {m: MMS.load(m, G) for m in MKTS}
    bars = {(m, tf): L1.bars(H1[m], tf) for m in MKTS for tf in ("H4", "D1")}
    t0, t1, tm = W.ts(START), W.ts(END), W.ts(MID)
    rng = np.random.default_rng(5)
    res = {"setups": {}, "g27k_by_regime": {}}
    # diagnostic: G27K #1 by regime
    g = SU.g27k_trades(MKTS, H1, RP, G, K, K.externals())
    g = g[(g.t >= t0) & (g.t < t1)]
    for m in MKTS:
        Dd = bars[(m, "D1")]
        gm = g[g.mkt == m]
        g.loc[gm.index, "reg"] = regime(Dd, gm.t.to_numpy())
    for r, nm in ((1, "UP"), (0, "SIDE"), (-1, "DOWN")):
        x = g[g.reg == r].R
        res["g27k_by_regime"][nm] = dict(n=len(x), mean=float(x.mean()), t=tstat(x))
    print("  G27K #1 by regime at entry:", {k: f"n {v['n']} {v['mean']:+.3f}R t {v['t']:+.2f}" for k, v in res["g27k_by_regime"].items()})
    trades = {}
    for name, v in SETUPS.items():
        rows, ctrl = [], [[] for _ in range(NDRAW)]
        for m in MKTS:
            X, Dd = bars[(m, v["tf"])], bars[(m, "D1")]
            d, reg = signals(name, X, Dd)
            tr = simulate(name, X, m, d, C, t0, t1)
            rows += tr
            if not tr:
                continue
            want = {"DOWN": -1, "SIDE": 0}[v["regime"]]
            elig = np.flatnonzero((reg == want) & (X["t"] >= t0) & (X["t"] < t1) & np.isfinite(X["atr"]))
            elig = elig[elig + 30 < len(X["c"])]
            dirs = np.array([x["d"] for x in tr])
            holds = np.array([max(1, x["hold"]) for x in tr])
            for k in range(NDRAW):
                pick = np.sort(rng.choice(elig, size=len(tr), replace=len(tr) > len(elig)))
                o = rng.permutation(len(tr))
                dd = np.zeros(len(X["c"]), np.int8)
                dd[pick] = dirs[o]
                ctrl[k] += [x["R"] for x in simulate(name, X, m, dd, C, t0, t1, idx=pick, holds=holds[o])]
        T = pd.DataFrame(rows)
        trades[name] = T
        cm = np.array([np.mean(x) if x else np.nan for x in ctrl])
        h1, h2 = T[T.t < tm], T[T.t >= tm]
        bym = T.groupby("mkt").R.agg(["count", "mean"])
        r = dict(n=len(T), mean=float(T.R.mean()), t=tstat(T.R), mean_h1=float(h1.R.mean()), mean_h2=float(h2.R.mean()),
                 markets_pos=int((bym["mean"] > 0).sum()), by_market={k: dict(n=int(x["count"]), mean=float(x["mean"])) for k, x in bym.iterrows()},
                 control_mean=float(np.nanmean(cm)), control_p=float(np.nanmean(cm >= T.R.mean())))
        r["checks"] = dict(t=r["mean"] > 0 and r["t"] > 2, halves=r["mean_h1"] > 0 and r["mean_h2"] > 0, markets=r["markets_pos"] >= 4,
                           control=r["control_p"] <= 0.05)
        r["pass"] = all(r["checks"].values())
        res["setups"][name] = r
        print(f"  {name}: n {r['n']:4d}  {r['mean']:+.3f}R  t {r['t']:+.2f}  halves {r['mean_h1']:+.3f}/{r['mean_h2']:+.3f}  "
              f"markets+ {r['markets_pos']}/6  control {r['control_mean']:+.3f} p {r['control_p']:.3f}  -> {'PASS' if r['pass'] else 'FAIL'}", flush=True)
        print("      " + "  ".join(f"{k} {x['mean']:+.3f}({x['n']})" for k, x in r["by_market"].items()))
    # portfolio check for passing setups (and reported for all)
    news = W.news_times(a.root)
    base = g[["mkt", "t", "tx", "R", "vp", "sc"]]
    res["portfolio"] = {}
    for bname, bset in (("S5", S5), ("S4U", S4U)):
        B = base[base.mkt.isin(bset)]
        for name in [None] + list(SETUPS):
            TT = B if name is None else pd.concat([B, trades[name][trades[name].mkt.isin(bset)].assign(
                mkt=lambda x: x.mkt + "#" + name, vp=0.0, sc=lambda x: x.t)[B.columns]], ignore_index=True)
            st, _, _ = SU.simulate(TT, "brake", PSTART, END, news=news)
            a1, _, _ = SU.simulate(TT, "brake", PSTART, PMID, news=news)
            a2, _, _ = SU.simulate(TT, "brake", PMID, END, news=news)
            key = bname + ("" if name is None else "+" + name)
            res["portfolio"][key] = dict(cagr=st["cagr"], dd=st["dd"], mar=st["mar"], mar_h1=a1["mar"], mar_h2=a2["mar"], worst=st["worst_year"])
            print(f"  {key:9s} CAGR {st['cagr']:+6.1%}  DD {st['dd']:5.1%}  MAR {st['mar']:.2f}  halves {a1['mar']:+.2f}/{a2['mar']:+.2f}", flush=True)
    (HERE / "regime_setups.json").write_text(json.dumps(res, indent=1, default=float))


if __name__ == "__main__":
    main()
