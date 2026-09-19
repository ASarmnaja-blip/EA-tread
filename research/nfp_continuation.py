#!/usr/bin/env python3
"""After NFP prints, does the market's own first move predict the next one?

WHAT THIS IS AND IS NOT

  Not prediction of the news, and not reading its content. The initial
  reaction is measured directly from price - the signed move in the minutes
  right after the release - and the question is only whether THAT sign
  predicts the sign of the move over the following hour(s). No calendar
  value, no economic forecast, nothing but the market's own first reaction.

  This is different from event_windows.py, which tested whether direction
  could be called BEFORE the release (it can't) and whether the cost/move
  ratio improves during the release window (it does, but not enough net of
  realistic slippage). This asks the question the prior test never asked.

THE HONEST SAMPLE SIZE

  NFP prints once a month. Twenty-two years is at most 264 events per market,
  a small fraction of everything else measured in this project. Stated before
  the result, not after.
"""
import json
import math
import pathlib
import sys
import time
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

HERE = pathlib.Path(__file__).parent
sys.path.insert(0, str(HERE))
import provenance as PR
from p01_cross_market import MARKETS, load_bidask_h1

NY = ZoneInfo("America/New_York")
RELEASE_LOCAL = (8, 30)
START, END = 2004, 2026
REACT_MIN = 15          # reaction window, minutes
HORIZONS_H = (1, 4, 24)  # continuation windows, hours
FLOOR = 5.00


def nfp_utc_times():
    out = []
    for y in range(START, END + 1):
        for m in range(1, 13):
            d = date(y, m, 1)
            while d.weekday() != 4:
                d += timedelta(days=1)
            loc = datetime(d.year, d.month, d.day, *RELEASE_LOCAL, tzinfo=NY)
            out.append(pd.Timestamp(loc).tz_convert("UTC"))
    return pd.DatetimeIndex(out)


def minute_frame():
    import fetch_dukascopy as D
    m = D.load("2019-01-01", None, verbose=False)
    if m is None or len(m) == 0:
        return None
    for k in ("open", "high", "low", "close"):
        m[k] = (m[f"bid_{k}"] + m[f"ask_{k}"]) / 2
    return m[(m.high > m.low) & (m.ask_close > m.bid_close)]


def gold_reaction_and_continuation(m1, events):
    """Minute-precision reaction (15 min) then hourly continuation, gold only."""
    rows = []
    for ev in events:
        pre = m1.loc[(m1.index >= ev - pd.Timedelta(minutes=5))
                     & (m1.index < ev)]
        react = m1.loc[(m1.index >= ev)
                       & (m1.index < ev + pd.Timedelta(minutes=REACT_MIN))]
        if len(pre) < 1 or len(react) < 5:
            continue
        p0 = float(pre["close"].iloc[-1])
        p1 = float(react["close"].iloc[-1])
        d = np.sign(p1 - p0)
        if d == 0:
            continue
        spread0 = float(m1["ask_close"].asof(ev) - m1["bid_close"].asof(ev))
        if not np.isfinite(spread0) or spread0 <= 0:
            continue
        rec = dict(event=ev, d=int(d), reaction=p1 - p0, react_price=p1,
                   spread=spread0)
        for h in HORIZONS_H:
            fut = m1.loc[m1.index >= ev + pd.Timedelta(minutes=REACT_MIN)
                        + pd.Timedelta(hours=h)]
            if len(fut) == 0:
                rec[f"h{h}"] = np.nan
                continue
            p2 = float(fut["close"].iloc[0])
            rec[f"h{h}"] = d * (p2 - p1)
        rows.append(rec)
    return pd.DataFrame(rows)


def panel_reaction_and_continuation(sym, events):
    """H1-precision version for the wider panel (no minute data)."""
    df = load_bidask_h1(sym)
    if df is None:
        return None
    mid = (df["bid_close"] + df["ask_close"]) / 2
    mid_o = (df["bid_open"] + df["ask_open"]) / 2
    sp = df["ask_close"] - df["bid_close"]
    rows = []
    for ev in events:
        bar = ev.floor("h")
        idx = df.index
        if bar not in idx:
            continue
        loc = idx.get_loc(bar)
        if isinstance(loc, slice) or loc + max(HORIZONS_H) >= len(idx):
            continue
        p0 = float(mid_o.iloc[loc])
        p1 = float(mid.iloc[loc])          # reaction = the release bar itself
        d = np.sign(p1 - p0)
        if d == 0:
            continue
        s0 = float(sp.iloc[loc])
        if not np.isfinite(s0) or s0 <= 0:
            continue
        rec = dict(event=ev, d=int(d), spread=s0)
        for h in HORIZONS_H:
            j = loc + h
            if j >= len(idx):
                rec[f"h{h}"] = np.nan
                continue
            rec[f"h{h}"] = d * (float(mid.iloc[j]) - p1)
        rows.append(rec)
    return pd.DataFrame(rows)


def edge_stats(df, col, spread_col="spread"):
    x = df[col].to_numpy(float)
    sp = df[spread_col].to_numpy(float)
    ok = np.isfinite(x) & np.isfinite(sp) & (sp > 0)
    if ok.sum() < 20:
        return None
    ratio = float(x[ok].sum() / sp[ok].sum())
    sign_rate = float((x[ok] > 0).mean())
    se = float((x[ok] / sp[ok]).std(ddof=1) / math.sqrt(ok.sum()))
    return dict(n=int(ok.sum()), edge=ratio, sign_rate=sign_rate,
                t=ratio / se if se > 0 else np.nan)


def main():
    t0 = time.time()
    print("NFP POST-RELEASE CONTINUATION")
    print("=" * 100)
    print(__doc__.split("THE HONEST SAMPLE SIZE")[1])

    events = nfp_utc_times()
    print(f"  {len(events)} NFP releases, {START}-{END}\n")

    m1 = minute_frame()
    gold = None
    if m1 is not None:
        ev19 = events[events >= m1.index[0]]
        gold = gold_reaction_and_continuation(m1, ev19)
        print(f"  gold, minute-precision reaction: {len(gold)} usable events "
              f"({m1.index[0].date()} onward)")
        r = edge_stats(gold, "reaction", "spread")
        if r:
            print(f"    15-min reaction itself: sign+ {r['sign_rate']*100:.1f}% "
                  f"(direction of the move just measured, not a prediction)")
        print(f"\n  {'horizon':<10}{'n':>6}{'sign%':>9}{'edge':>10}{'t':>8}")
        for h in HORIZONS_H:
            r = edge_stats(gold, f"h{h}")
            if r:
                print(f"    +{h}h{'':<6}{r['n']:>6}{r['sign_rate']*100:>8.2f}%"
                      f"{r['edge']:>+10.4f}{r['t']:>+8.2f}")

    print("\n" + "=" * 100)
    print("PANEL (H1 precision - reaction is the release bar itself)")
    print("=" * 100)
    print(f"  {'market':<9}{'n':>6}  " + "  ".join(
        f"h{h}:sign%/edge/t" for h in HORIZONS_H))
    panel_rows = {}
    for sym in MARKETS:
        d = panel_reaction_and_continuation(sym, events)
        if d is None or len(d) < 30:
            continue
        panel_rows[sym] = d
        cells = []
        for h in HORIZONS_H:
            r = edge_stats(d, f"h{h}")
            cells.append(f"{r['sign_rate']*100:5.1f}%/{r['edge']:+.3f}/"
                        f"{r['t']:+.1f}" if r else "n/a")
        print(f"  {sym:<9}{len(d):>6}  " + "  ".join(cells))

    print("\n" + "=" * 100)
    print("POOLED ACROSS THE PANEL, BY HORIZON")
    print("=" * 100)
    pooled = {}
    for h in HORIZONS_H:
        edges, signs = [], []
        for sym, d in panel_rows.items():
            r = edge_stats(d, f"h{h}")
            if r:
                edges.append(r["edge"])
                signs.append(r["sign_rate"])
        if not edges:
            continue
        se = float(np.std(edges, ddof=1) / math.sqrt(len(edges))) if len(edges) > 1 else np.nan
        t = float(np.mean(edges) / se) if se and se > 0 else np.nan
        pos = int(sum(1 for e in edges if e > 0))
        pooled[h] = dict(mean_edge=float(np.mean(edges)),
                         mean_sign=float(np.mean(signs)), t=t,
                         positive=pos, markets=len(edges))
        print(f"  +{h}h   mean edge {np.mean(edges):+.4f}   "
              f"mean sign% {np.mean(signs)*100:.2f}%   t {t:+.2f}   "
              f"positive {pos}/{len(edges)}")

    viable = [h for h, r in pooled.items()
              if r["mean_edge"] > 1.0 and np.isfinite(r["t"]) and r["t"] > FLOOR
              and r["positive"] > r["markets"] / 2]
    print(f"\n  {len(viable)} horizon(s) clear one round trip with t>{FLOOR} "
          f"on a majority of markets")
    if not viable:
        print(f"  The initial reaction's sign does not reliably predict what "
              f"comes after it,")
        print(f"  at the sample size a once-a-month event allows.")

    out = HERE / "nfp_continuation.json"
    out.write_text(json.dumps(dict(
        created=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        n_events=len(events), horizons=list(HORIZONS_H), floor=FLOOR,
        pooled=pooled, viable=len(viable),
        manifest=PR.manifest({}, [])), indent=1, default=str))
    PR.log("phase8-nfp-continuation",
           "Does the sign of the market's own initial NFP reaction predict "
           "the sign of the subsequent move?",
           hypothesis="nfp_post_reaction_continuation",
           tools=["nfp_continuation"],
           result=dict(pooled=pooled, viable=len(viable)),
           status="MEASURED",
           finding=f"{len(viable)} of {len(HORIZONS_H)} horizons viable",
           next_action="record against the registered criterion",
           started=t0)
    print(f"\n  saved -> {out.name}   elapsed {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
