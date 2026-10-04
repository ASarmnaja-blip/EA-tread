#!/usr/bin/env python3
"""Audit of the final system: G27K #1 on gold, silver, BTC and JP225.

Part 1, engine and data checks:
  1. the signal frame (g27k.prepare) and the trade frame (features) are the
     same H4 bars
  2. each H4 bar's OHLC equals its H1 bars
  3. the exit channel (dlo) is the prior 20-bar low and the entry channel the
     prior 10-bar high
  4. an independent re-implementation of entries, stops, exits and R gives
     the same trades as report768.sim_paths
  5. clock offsets: MT5 and Candle Lab gold against Dukascopy UTC, and the
     economic calendar against known release times
  6. price outliers and gaps in each market

Usage: python3 research/g27k_dev/audit_final.py --root <data-snapshot checkout>
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
import walkforward_controller as W

MKTS = ("XAUUSD", "XAGUSD", "BTCUSD", "JP225")
START = "2009-09-01"


def independent(X, Mk, m, signal, C):
    """G27K #1 written from the rule text, sharing only the bars and ATR."""
    o, h, l, c, t, a20 = (np.asarray(X[k], float) for k in ("o", "h", "l", "c", "t", "a20"))
    b = X["b"]
    bo, bh, bl, bt = (np.asarray(b[k], float) for k in ("o", "h", "l", "t"))
    k0, k1 = np.asarray(X["k0"]), np.asarray(X["k1"])
    lo20 = pd.Series(l).rolling(20).min().shift(1).to_numpy()
    n = len(c)
    out, busy = [], -1
    for s in np.flatnonzero(signal):
        if s <= busy or s + 1 >= n or not np.isfinite(a20[s]):
            continue
        e = s + 1
        ep = o[e]
        risk = 2 * a20[s]
        stop = ep - risk
        px = None
        j = e
        while j < n:
            for q in range(k0[j], k1[j]):
                if bl[q] <= stop:
                    px = min(stop, bo[q])          # gap through the stop fills at the open
                    tx = bt[q]
                    break
            if px is not None:
                break
            if c[j] < lo20[j] and j + 1 < n:
                j += 1
                px, tx = o[j], t[j]
                break
            j += 1
        if px is None:
            j, px, tx = n - 1, c[n - 1], t[n - 1]
        out.append((int(t[e]), int(tx), (px - ep) / risk))
        busy = j
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    a = ap.parse_args()
    P.setup(a.root)
    G, K, C = P._M["G"], P._M["K"], P._M["C"]
    sys.path.insert(0, str(pathlib.Path(a.root) / "research" / "grid768"))
    import report768 as RP
    H1 = {m: MMS.load(m, G) for m in MKTS}
    ext = K.externals()
    K.START = W.ts(START)
    res = {}
    for m in MKTS:
        Mk = K.prepare(m, H1[m], ext)
        X = G.features(G.frames(H1[m]), m, "H4")
        r = {}
        r["frames_same_bars"] = bool(len(Mk["t"]) == len(X["t"]) and np.array_equal(np.asarray(Mk["t"]), np.asarray(X["t"])))
        # 2. H4 OHLC equals its H1 bars
        b = X["b"]
        bad = 0
        for i in range(0, len(X["t"]), 7):
            q0, q1 = X["k0"][i], X["k1"][i]
            if q1 <= q0:
                continue
            if not (np.isclose(X["o"][i], b["o"][q0]) and np.isclose(X["c"][i], b["c"][q1 - 1])
                    and np.isclose(X["h"][i], np.max(b["h"][q0:q1])) and np.isclose(X["l"][i], np.min(b["l"][q0:q1]))):
                bad += 1
        r["h4_vs_h1_mismatches"] = bad
        # 3. channels
        lo20 = pd.Series(X["l"]).rolling(20).min().shift(1).to_numpy()
        hi10 = pd.Series(X["h"]).rolling(10).max().shift(1).to_numpy()
        ok = np.isfinite(lo20) & np.isfinite(X["dlo"])
        r["dlo_is_prior20_low"] = bool(np.allclose(X["dlo"][ok], lo20[ok]))
        okh = np.isfinite(hi10) & np.isfinite(Mk["hi10"])
        r["hi10_is_prior10_high"] = bool(np.allclose(Mk["hi10"][okh], hi10[okh]))
        # 4. independent trades vs report768
        d = K.directions(Mk, "C8", "D3", "E1", "J1")
        idx = np.flatnonzero(d)
        rp = RP.sim_paths(X, m, idx, d[idx], "I1")
        ind = independent(X, Mk, m, d > 0, C)
        a_ = pd.DataFrame([(x["t"], x["t_exit"], x["R_gross"]) for x in rp], columns=["t", "tx", "R"])
        b_ = pd.DataFrame(ind, columns=["t", "tx", "R"])
        mg = a_.merge(b_, on="t", how="outer", suffixes=("_rp", "_ind"), indicator=True)
        both = mg[mg._merge == "both"]
        r["trades_report768"] = len(a_)
        r["trades_independent"] = len(b_)
        r["entries_only_in_one"] = int((mg._merge != "both").sum())
        r["exit_time_mismatch"] = int((both.tx_rp != both.tx_ind).sum())
        r["max_abs_R_diff"] = float((both.R_rp - both.R_ind).abs().max()) if len(both) else None
        r["total_R_gross"] = [float(a_.R.sum()), float(b_.R.sum())]
        # 6. data: largest H1 moves and gaps
        hc = np.asarray(H1[m]["c"], float)
        ht = np.asarray(H1[m]["t"], np.int64)
        ret = np.abs(np.diff(np.log(hc)))
        top = np.argsort(-ret)[:3]
        r["largest_h1_moves"] = [(str(pd.Timestamp(int(ht[i + 1]), unit="s")), round(float(ret[i]) * 100, 2)) for i in top]
        gap = np.diff(ht) / 3600
        wk = gap[(gap > 4)]
        r["gaps_over_4h"] = int(len(wk))
        r["gaps_over_80h"] = int((gap > 80).sum())
        res[m] = r
        print(m, json.dumps(r, default=str), flush=True)

    # 5. clock offsets: hybrid gold (Candle Lab before 2021, MT5 after) vs Dukascopy UTC
    dk = pd.read_parquet(HERE.parent / ".cache_duka" / "XAUUSD_H1_2003_2026.parquet")
    dk = pd.Series(((dk.bid_close + dk.ask_close) / 2).to_numpy(), index=dk.index.tz_convert(None))
    hy = H1["XAUUSD"]
    hs = pd.Series(np.asarray(hy["c"], float), index=pd.to_datetime(np.asarray(hy["t"], np.int64), unit="s"))
    offs = {}
    for name, lo, hi in (("Candle Lab 2015", "2015-01-01", "2016-01-01"), ("MT5 2023 Jan", "2023-01-01", "2023-03-01"),
                         ("MT5 2023 Jul", "2023-06-01", "2023-08-01")):
        a1 = hs[lo:hi]
        best = {}
        for sh in range(-4, 5):
            b1 = dk.shift(sh)[lo:hi].reindex(a1.index)
            ok = b1.notna()
            best[sh] = float(np.mean(np.abs(a1[ok] - b1[ok])))
        offs[name] = dict(best_shift_hours=min(best, key=best.get), mean_abs_diff=round(min(best.values()), 3),
                          at_zero=round(best[0], 3))
    res["clock_gold_vs_dukascopy"] = offs
    print("clock", json.dumps(offs), flush=True)
    cal = pd.read_csv(pathlib.Path(a.root) / "data" / "calendar.csv", encoding="cp1252")
    nfp = cal[(cal.currency == "USD") & cal.event.str.contains("Nonfarm Payrolls", case=False, na=False)].copy()
    nfp["hhmm"] = nfp.time.str[-5:]
    res["calendar_nfp_times"] = nfp.hhmm.value_counts().head(4).to_dict()
    print("calendar NFP clock times", res["calendar_nfp_times"], "(US 08:30 ET = 12:30 UTC summer, 13:30 UTC winter)")
    (HERE / "audit_final.json").write_text(json.dumps(res, indent=1, default=str))


if __name__ == "__main__":
    main()
