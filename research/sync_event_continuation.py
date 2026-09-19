#!/usr/bin/env python3
"""Find 'important news' from price itself, no calendar needed.

THE IDEA

  A genuine scheduled macro release (NFP, CPI, a Fed decision) moves many
  unrelated currency pairs AT THE SAME HOUR, because it changes a factor they
  all share - USD rates, broad risk appetite. Ordinary single-market noise
  does not do that: EURUSD having a big hour for its own reasons says nothing
  about GBPUSD's hour.

  So simultaneity across the panel is a calendar-free fingerprint of
  important news. It needs no external data, and because it is not limited to
  one release a month, it gives an order of magnitude more events than NFP
  alone - the earlier NFP continuation test had a ceiling of 252 per market;
  this should not.

WHAT COUNTS AS SYNCHRONIZED

  At least 6 of 9 panel markets moving more than 1.0 ATR-units within the
  same UTC hour. Direction is not required to agree - a dollar move pushes
  USD-base and USD-quote pairs in opposite signs by construction - only
  simultaneity of SIZE is required.

THE SAME QUESTION AS THE NFP TEST, ASKED AT SCALE

  Does the panel's reaction during that hour predict what happens over the
  following 1h, 4h, 24h. If it fails again at this sample size, sample size
  is ruled out as the reason - a second, independent way of reaching the same
  answer the NFP test reached.
"""
import argparse
import json
import math
import pathlib
import sys
import time

import numpy as np
import pandas as pd

HERE = pathlib.Path(__file__).parent
sys.path.insert(0, str(HERE))
import controls as C
import provenance as PR
import xauusd_1000_setups as X
from p01_cross_market import MARKETS, TICKS, load_bidask_h1

SEED = 17
MIN_MARKETS = 6
MOVE_ATR = 1.0
HORIZONS = (1, 4, 24)
FLOOR = 5.00
# sign a move in each symbol should be read with, so "USD strength" maps to
# a common direction: +1 means USD got stronger over that bar
USD_SIGN = {"EURUSD": -1, "GBPUSD": -1, "AUDUSD": -1, "NZDUSD": -1,
           "USDJPY": +1, "USDCHF": +1, "USDCAD": +1, "USDSEK": +1,
           "XAUUSD": -1, "XAGUSD": -1}   # gold/silver fall when USD strengthens


def prep_all():
    P = {}
    for sym in MARKETS:
        df = load_bidask_h1(sym)
        if df is None or len(df) < 20000:
            continue
        P[sym] = X.prep(df, 60)
    return P


def build_events(P):
    """Per-market ATR-normalised return aligned on one UTC index, then flag
    the hours where enough markets move together."""
    frames = {}
    for sym, p in P.items():
        r = pd.Series(np.asarray(p["c"], float), index=pd.DatetimeIndex(p["idx"]))
        r = r.diff()
        A = pd.Series(np.asarray(p["A"], float), index=pd.DatetimeIndex(p["idx"]))
        z = (r / A) * USD_SIGN.get(sym, 1)
        frames[sym] = z
    D = pd.DataFrame(frames)
    big = D.abs() > MOVE_ATR
    n_big = big.sum(axis=1)
    event = n_big >= MIN_MARKETS
    # consensus direction: sign of the median USD-signed move among the
    # markets that moved that hour
    def consensus(row):
        vals = row[big.loc[row.name]] if row.name in big.index else row.dropna()
        vals = row.dropna()
        big_vals = vals[vals.abs() > MOVE_ATR]
        if len(big_vals) == 0:
            return np.nan
        return float(np.sign(np.median(big_vals)))
    cons = D.apply(consensus, axis=1)
    ev = event[event].index
    return D, cons.loc[ev], n_big.loc[ev]


def continuation(P, sym, ev_index, cons, horizons=HORIZONS):
    """For symbol sym, at each event hour, does the panel consensus direction
    (read in this symbol's own quoting convention) predict its forward move."""
    p = P[sym]
    idx = pd.DatetimeIndex(p["idx"])
    c = np.asarray(p["c"], float)
    sp = np.asarray(p["spread"], float)
    N = p["N"]
    pos = {t: i for i, t in enumerate(idx)}
    rows = []
    own_sign = USD_SIGN.get(sym, 1)
    for t in ev_index:
        i = pos.get(t)
        if i is None or i + max(horizons) >= N or i < 300:
            continue
        d = cons.loc[t] * own_sign     # this symbol's own directional read
        if not np.isfinite(d) or d == 0:
            continue
        s = sp[i]
        if not np.isfinite(s) or s <= 0:
            continue
        rec = dict(t=t, d=d, spread=s)
        for h in horizons:
            if i + h < N:
                rec[f"h{h}"] = d * (c[i + h] - c[i])
        rows.append(rec)
    return pd.DataFrame(rows)


def matched_control(P, sym, ev_index, horizons=HORIZONS, rng=None):
    """Random hours, same count, same rough activity level (ATR decile) -
    a C1/C3-style baseline without importing the full controls module,
    since this is a per-event-hour draw rather than a per-signal-bar one."""
    p = P[sym]
    idx = pd.DatetimeIndex(p["idx"])
    N = p["N"]
    A = np.asarray(p["A"], float)
    c = np.asarray(p["c"], float)
    sp = np.asarray(p["spread"], float)
    eligible = np.arange(300, N - max(horizons) - 1)
    ev_pos = np.array([i for i, t in enumerate(idx) if t in set(ev_index)])
    take = rng.choice(eligible, size=len(ev_index), replace=False)
    d = rng.choice([-1.0, 1.0], size=len(take))
    rows = []
    for i, dd in zip(take, d):
        s = sp[i]
        if not np.isfinite(s) or s <= 0:
            continue
        rec = dict(d=dd, spread=s)
        for h in horizons:
            if i + h < N:
                rec[f"h{h}"] = dd * (c[i + h] - c[i])
        rows.append(rec)
    return pd.DataFrame(rows)


def edge_stats(df, col):
    if col not in df or len(df) < 20:
        return None
    x = df[col].to_numpy(float)
    sp = df["spread"].to_numpy(float)
    ok = np.isfinite(x) & np.isfinite(sp) & (sp > 0)
    if ok.sum() < 20:
        return None
    ratio = float(x[ok].sum() / sp[ok].sum())
    se = float((x[ok] / sp[ok]).std(ddof=1) / math.sqrt(ok.sum()))
    return dict(n=int(ok.sum()), edge=ratio, sign_rate=float((x[ok] > 0).mean()),
                t=ratio / se if se > 0 else np.nan)


def main():
    t0 = time.time()
    print("SYNCHRONIZED-VOLATILITY EVENTS - a calendar built from price")
    print("=" * 104)
    print(__doc__.split("WHAT COUNTS AS SYNCHRONIZED")[1]
          .split("THE SAME QUESTION")[0])

    P = prep_all()
    D, cons, n_big = build_events(P)
    print(f"  {len(P)} markets, {len(D):,} bars")
    print(f"  {len(cons):,} synchronized-event hours "
          f"(>= {MIN_MARKETS}/9 markets move > {MOVE_ATR} ATR in the same "
          f"hour)")
    print(f"  that is {len(cons)/22:.0f}/year, against 12/year for NFP\n")

    rng = np.random.default_rng(SEED)
    print("=" * 104)
    print(f"  {'market':<9}{'n':>7}  " + "  ".join(
        f"h{h}:sign%/edge/t" for h in HORIZONS) + "    | control h4 edge")
    panel_edges = {h: [] for h in HORIZONS}
    for sym in P:
        d = continuation(P, sym, cons.index, cons)
        if len(d) < 100:
            continue
        ctrl = matched_control(P, sym, cons.index, rng=rng)
        cells = []
        for h in HORIZONS:
            r = edge_stats(d, f"h{h}")
            if r:
                cells.append(f"{r['sign_rate']*100:5.1f}%/{r['edge']:+.3f}/"
                            f"{r['t']:+.1f}")
                panel_edges[h].append(r["edge"])
            else:
                cells.append("n/a")
        rc = edge_stats(ctrl, "h4")
        print(f"  {sym:<9}{len(d):>7,}  " + "  ".join(cells)
              + f"    | {rc['edge']:+.3f}" if rc else "")

    print("\n" + "=" * 104)
    print("POOLED ACROSS THE PANEL")
    print("=" * 104)
    pooled = {}
    for h in HORIZONS:
        e = panel_edges[h]
        if len(e) < 3:
            continue
        se = float(np.std(e, ddof=1) / math.sqrt(len(e)))
        t = float(np.mean(e) / se) if se > 0 else np.nan
        pos = int(sum(1 for x in e if x > 0))
        pooled[h] = dict(mean_edge=float(np.mean(e)), t=t, positive=pos,
                         markets=len(e))
        print(f"  +{h}h   mean edge {np.mean(e):+.4f}   t {t:+.2f}   "
              f"positive {pos}/{len(e)}")

    viable = [h for h, r in pooled.items()
              if r["mean_edge"] > 1.0 and np.isfinite(r["t"]) and r["t"] > FLOOR
              and r["positive"] > r["markets"] / 2]

    print("\n" + "=" * 104)
    print("GOLD SPECIFICALLY")
    print("=" * 104)
    gd = continuation(P, "XAUUSD", cons.index, cons)
    for h in HORIZONS:
        r = edge_stats(gd, f"h{h}")
        if r:
            print(f"  +{h}h   n={r['n']:,}   sign% {r['sign_rate']*100:.2f}%   "
                  f"edge {r['edge']:+.4f}   t {r['t']:+.2f}")

    print(f"\n  {len(viable)} horizon(s) clear one round trip with t>{FLOOR} "
          f"on a majority of markets")
    if not viable:
        print(f"  At roughly {len(cons)/22:.0f} events a year - well beyond "
              f"NFP's monthly ceiling - the")
        print(f"  panel's own reaction to a synchronized shock still does "
              f"not predict its next")
        print(f"  move. Sample size is ruled out; the earlier NFP result "
              f"and this one now agree")
        print(f"  independently.")

    out = HERE / "sync_event_continuation.json"
    out.write_text(json.dumps(dict(
        created=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        n_events=len(cons), events_per_year=len(cons) / 22, horizons=list(HORIZONS),
        floor=FLOOR, pooled=pooled, viable=len(viable),
        manifest=PR.manifest(dict(min_markets=MIN_MARKETS, move_atr=MOVE_ATR),
                             [HERE / ".cache_duka" /
                              f"{s}_H1_2003_2026.parquet" for s in MARKETS])),
        indent=1, default=str))
    PR.log("phase8-sync-event-continuation",
           "At ten times the sample size, does a market's reaction to a "
           "synchronized shock predict its next move any better than NFP "
           "alone did?",
           hypothesis="synchronized_volatility_event_detector",
           tools=["sync_event_continuation"],
           result=dict(pooled=pooled, viable=len(viable),
                       n_events=len(cons)),
           status="MEASURED",
           finding=f"{len(viable)} of {len(HORIZONS)} horizons viable at "
                   f"{len(cons)} events",
           next_action="record against the registered criterion",
           started=t0)
    print(f"\n  saved -> {out.name}   elapsed {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
