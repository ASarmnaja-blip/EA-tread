#!/usr/bin/env python3
"""Mechanism-designed setups for the markets where G27K #1 loses
(ledger designed_setups_losing_markets). Parameters are the literature
defaults, fixed before the run.

  A IDX_DIP     US500 USTEC DE30 JP225: long when the D1 close is above its
                SMA200 and below the lowest close of the prior 5 days; exit
                when the close is back above SMA5, or after 10 days
  B IDX_TOM     same indices: long from the open of the last trading day of
                the month to the open after the 3rd trading day of the next
  C FX_BB_FADE  EURUSD AUDUSD USDCHF USDCNH USDMXN USDZAR USDJPY: fade a close
                outside the 20-day 2-sd Bollinger band; exit when the close
                crosses back over SMA20, or after 10 days

All: D1 bars from H1 with the day boundary at 22:00 UTC, entry at the next D1
open, stop 2.5 x ATR20(D1) from entry walked on H1 bars (a gap fills at the H1
open), exit at the next D1 open after the exit condition, one position per
market, broker round-trip cost and broker swap per night.

Usage: python3 research/g27k_dev/designed_setups.py --root <data-snapshot checkout>
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
import h4d1_pattern_search as P
import multi_market_search as MMS
import suite as SU
import walkforward_controller as W

START, MID, END = "2009-09-01", "2018-01-01", "2026-10-01"
PSTART = "2011-09-01"
IDX = ("US500", "USTEC", "DE30", "JP225")
FX = ("EURUSD", "AUDUSD", "USDCHF", "USDCNH", "USDMXN", "USDZAR", "USDJPY")
FAMILIES = {"A_IDX_DIP": IDX, "B_IDX_TOM": IDX, "C_FX_BB_FADE": FX}
S5 = ("XAUUSD", "XAGUSD", "BTCUSD", "JP225", "USDJPY")
STOP_K, NDRAW = 2.5, 200


def daily(b):
    t = np.asarray(b["t"], np.int64)
    key = (t - 22 * 3600) // 86400
    cut = np.flatnonzero(np.diff(key)) + 1
    k0 = np.r_[0, cut]
    k1 = np.r_[cut, len(t)]
    o, h, l, c = (np.asarray(b[x], float) for x in "ohlc")
    D = dict(t=t[k0], o=o[k0], h=np.maximum.reduceat(h, k0), l=np.minimum.reduceat(l, k0), c=c[k1 - 1], k0=k0, k1=k1,
             bo=o, bh=h, bl=l, bt=t)
    pc = np.r_[np.nan, D["c"][:-1]]
    tr = np.nanmax(np.c_[D["h"] - D["l"], np.abs(D["h"] - pc), np.abs(D["l"] - pc)], axis=1)
    cs = pd.Series(D["c"])
    D["atr"] = pd.Series(tr).rolling(20).mean().to_numpy()
    D["sma200"] = cs.rolling(200).mean().to_numpy()
    D["sma20"] = cs.rolling(20).mean().to_numpy()
    D["sd20"] = cs.rolling(20).std(ddof=0).to_numpy()
    D["sma5"] = cs.rolling(5).mean().to_numpy()
    D["low5"] = cs.shift(1).rolling(5).min().to_numpy()
    lab = pd.to_datetime(D["t"] + 2 * 3600, unit="s")        # 22:00 UTC session start -> its trading date
    D["ym"] = (lab.year * 12 + lab.month).to_numpy()
    nxt = np.r_[D["ym"][1:], -1]
    D["last_of_month"] = D["ym"] != nxt
    first = np.r_[True, D["ym"][1:] != D["ym"][:-1]]
    D["dom"] = np.zeros(len(D["t"]), int)                    # trading day of month, 1-based
    n = 0
    for i in range(len(D["t"])):
        n = 1 if first[i] else n + 1
        D["dom"][i] = n
    return D


def signals(fam, D):
    n = len(D["c"])
    d = np.zeros(n, np.int8)
    if fam == "A_IDX_DIP":
        d[(D["c"] > D["sma200"]) & (D["c"] < D["low5"])] = 1
    elif fam == "B_IDX_TOM":
        nxt_last = np.r_[D["last_of_month"][1:], False]     # day s+1 is the month's last trading day
        d[nxt_last] = 1
    else:
        d[D["c"] < D["sma20"] - 2 * D["sd20"]] = 1
        d[D["c"] > D["sma20"] + 2 * D["sd20"]] = -1
    d[~np.isfinite(D["atr"])] = 0
    return d


def exit_now(fam, D, j, e, dr, hold=None):
    """True when the position entered on day e should exit at the open after day j's close."""
    if hold is not None:
        return j - e + 1 >= hold
    if fam == "A_IDX_DIP":
        return D["c"][j] > D["sma5"][j] or j - e + 1 >= 10
    if fam == "B_IDX_TOM":
        return (D["ym"][j] != D["ym"][e] and D["dom"][j] >= 3) or j - e + 1 >= 8
    return (D["c"][j] >= D["sma20"][j] if dr > 0 else D["c"][j] <= D["sma20"][j]) or j - e + 1 >= 10


def run(fam, D, m, sig_idx, dirs, holds=None, C=None):
    """Trades from signal days (sorted). holds: fixed holding length per signal (control)."""
    n = len(D["c"])
    out, busy = [], -1
    spec = C.SPECS[m]
    for q, (s, dr) in enumerate(zip(sig_idx, dirs)):
        if s <= busy or s + 1 >= n:
            continue
        e = s + 1
        ep = D["o"][e]
        risk = STOP_K * D["atr"][s]
        if not risk > 0:
            continue
        stop = ep - dr * risk
        px, j = None, e
        while j < n:
            hit_day = D["l"][j] <= stop if dr > 0 else D["h"][j] >= stop
            for k in (range(D["k0"][j], D["k1"][j]) if hit_day else ()):
                if (dr > 0 and D["bl"][k] <= stop) or (dr < 0 and D["bh"][k] >= stop):
                    px = min(stop, D["bo"][k]) if dr > 0 else max(stop, D["bo"][k])
                    tx = D["bt"][k]
                    break
            if px is not None:
                break
            if exit_now(fam, D, j, e, dr, None if holds is None else holds[q]) and j + 1 < n:
                j += 1
                px, tx = D["o"][j], D["t"][j]
                break
            j += 1
        if px is None:
            break
        nights = int(C.nights(np.array([D["t"][e]]), np.array([tx]), spec["rollover3"])[0])
        sw = spec["swap_long_bp"] if dr > 0 else spec["swap_short_bp"]
        R = dr * (px - ep) / risk - (spec["cost_rt_bp"] + sw * nights) * 1e-4 * ep / risk
        out.append(dict(mkt=m, t=int(D["t"][e]), tx=int(tx), R=float(R), d=int(dr), hold=int(j - e + (0 if px is None else 0)), s=int(s)))
        busy = j
    return out


def tstat(x):
    x = np.asarray(x, float)
    return float(x.mean() / x.std(ddof=1) * np.sqrt(len(x))) if len(x) > 2 else float("nan")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    a = ap.parse_args()
    P.setup(a.root)
    G, K, C = P._M["G"], P._M["K"], P._M["C"]
    sys.path.insert(0, str(pathlib.Path(a.root) / "research" / "grid768"))
    import report768 as RP
    mk = sorted(set(IDX + FX))
    Ds = {m: daily(MMS.load(m, G)) for m in mk}
    s0, s1, smid = W.ts(START), W.ts(END), W.ts(MID)
    rng = np.random.default_rng(11)
    res = {"families": {}}
    trades = {}
    for fam, mkts in FAMILIES.items():
        rows, ctrl_means = [], np.zeros(NDRAW)
        per_ctrl = [[] for _ in range(NDRAW)]
        for m in mkts:
            D = Ds[m]
            d = signals(fam, D)
            ok = (D["t"] >= s0) & (D["t"] < s1)
            idx = np.flatnonzero((d != 0) & ok)
            tr = run(fam, D, m, idx, d[idx], C=C)
            rows += tr
            # matched control: same count, direction and holding length, random eligible entry days
            elig = np.flatnonzero(ok & np.isfinite(D["atr"]) & ((D["c"] > D["sma200"]) if fam == "A_IDX_DIP" else True))
            elig = elig[elig + 12 < len(D["c"])]
            if not len(tr) or not len(elig):
                continue
            dirs = np.array([x["d"] for x in tr])
            holds = np.array([max(1, x["hold"]) for x in tr])
            for k in range(NDRAW):
                pick = np.sort(rng.choice(elig, size=len(tr), replace=len(tr) > len(elig)))
                order = rng.permutation(len(tr))
                c = run(fam, D, m, pick, dirs[order], holds=holds[order], C=C)
                per_ctrl[k] += [x["R"] for x in c]
        T = pd.DataFrame(rows)
        trades[fam] = T
        ctrl_means = np.array([np.mean(x) if x else np.nan for x in per_ctrl])
        h1, h2 = T[T.t < smid], T[T.t >= smid]
        bym = T.groupby("mkt").R.agg(["count", "mean"])
        r = dict(n=len(T), mean=float(T.R.mean()), t=tstat(T.R), win=float((T.R > 0).mean()),
                 mean_h1=float(h1.R.mean()) if len(h1) else None, mean_h2=float(h2.R.mean()) if len(h2) else None,
                 n_h1=len(h1), n_h2=len(h2), markets_positive=int((bym["mean"] > 0).sum()), markets=len(bym),
                 by_market={k: dict(n=int(v["count"]), mean=float(v["mean"])) for k, v in bym.iterrows()},
                 control_mean=float(np.nanmean(ctrl_means)), control_p=float(np.mean(ctrl_means >= T.R.mean())),
                 long_mean=float(T[T.d > 0].R.mean()) if (T.d > 0).any() else None,
                 short_mean=float(T[T.d < 0].R.mean()) if (T.d < 0).any() else None)
        r["checks"] = dict(t_gt_2=r["mean"] > 0 and r["t"] > 2.0,
                           both_halves=bool(r["mean_h1"] and r["mean_h1"] > 0 and r["mean_h2"] and r["mean_h2"] > 0),
                           majority_markets=r["markets_positive"] > r["markets"] / 2, beats_control=r["control_p"] <= 0.05)
        r["pass"] = all(r["checks"].values())
        res["families"][fam] = r
        print(f"  {fam:13s} n {r['n']:4d}  mean {r['mean']:+.3f}R  t {r['t']:+.2f}  win {r['win']:.0%}  halves {r['mean_h1']:+.3f}/{r['mean_h2']:+.3f}  "
              f"markets + {r['markets_positive']}/{r['markets']}  control {r['control_mean']:+.3f}R p {r['control_p']:.3f}  -> {'PASS' if r['pass'] else 'FAIL'}", flush=True)
        for k, v in r["by_market"].items():
            print(f"      {k:7s} n {v['n']:4d}  {v['mean']:+.3f}R")
        if r["long_mean"] is not None and r["short_mean"] is not None:
            print(f"      long {r['long_mean']:+.3f}R  short {r['short_mean']:+.3f}R")

    # portfolio: S5 alone and S5 + each family (brake 25%), whether or not it passed (reported, judged only for passes)
    H1 = {m: MMS.load(m, G) for m in S5}
    news = W.news_times(a.root)
    g = SU.g27k_trades(S5, H1, RP, G, K, K.externals())
    base = g[["mkt", "t", "tx", "R", "vp", "sc"]]
    res["portfolio"] = {}
    for name, extra in [("S5", None)] + [(f"S5+{f}", trades[f]) for f in FAMILIES]:
        T = base if extra is None else pd.concat([base, extra.assign(mkt=extra.mkt + "#" + name[-6:], vp=0.0, sc=extra.t)[base.columns]],
                                                 ignore_index=True)
        st, eq, _ = SU.simulate(T, "brake", PSTART, END, news=news)
        a1, _, _ = SU.simulate(T, "brake", PSTART, MID, news=news)
        a2, _, _ = SU.simulate(T, "brake", MID, END, news=news)
        st.update(mar_h1=a1["mar"], mar_h2=a2["mar"], mc=SU.monte_carlo(eq))
        res["portfolio"][name] = st
        print(f"  {name:18s} brake CAGR {st['cagr']:+6.1%}  DD {st['dd']:5.1%}  MAR {st['mar']:.2f}  halves {a1['mar']:+.2f}/{a2['mar']:+.2f}  "
              f"worst yr {st['worst_year']:+.0%}  n {st['n']}", flush=True)
    (HERE / "designed_setups.json").write_text(json.dumps(res, indent=1, default=float))


if __name__ == "__main__":
    main()
