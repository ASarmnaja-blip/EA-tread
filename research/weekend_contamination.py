#!/usr/bin/env python3
"""29% of every bar in this repository is a weekend the venue did not quote.

HOW IT WAS FOUND

  Not by reading the loader. The tradability layer reported 69% coverage on
  gold H1 and the only way a cost-over-range ratio goes missing is a bar whose
  true range is zero. There are 58,233 of them out of 188,569.

WHAT THEY ARE

  Every market in the panel carries the same share, between 28.8% and 31.0%,
  stable in every year from 2004 to 2026. A property that uniform across nine
  instruments and twenty-two years is not a property of markets.

      zero-range share by weekday, gold H1
        Mon 3.9%   Tue 2.7%   Wed 2.9%   Thu 3.0%   Fri 12.6%
        Sat 100%   Sun 91.6%

  54,000 of them are Saturdays and Sundays: the feed emits a flat bar with
  open = high = low = close for every hour the market is shut. The rest are
  the daily rollover - 43.5% of weekday 21:00 bars, 36.3% of 22:00, 20.6% of
  23:00 - and the Friday close.

WHY IT MATTERS MORE THAN ITS SHARE SUGGESTS

  A flat bar has a true range of exactly zero, and Wilder's ATR is an
  exponential mean of true range. Forty-eight consecutive zeros multiply it by
  (13/14)^48 = 0.030. The volatility estimate does not merely get noisier over
  a weekend; it collapses and then takes most of the week to recover.

      Wilder ATR(14) median, as a share of Thursday's
        Mon 55.6%   Tue 86.5%   Wed 94.3%   Thu 100%   Fri 97.7%
        Sat 34.5%   Sun 6.5%

      Monday, by hour UTC
        00:00 19.8%   06:00 39.9%   12:00 61.8%   18:00 82.8%

  The engine gates every trade on the spread being at most 10% of ATR. With
  ATR understated, that gate closes:

      share of bars the spread gate rejects, gold H1
        Mon 84.8%   Tue 67.6%   Wed 61.6%   Thu 56.9%   Fri 60.8%

  So every backtest in this repository has been roughly three times less
  likely to take a Monday trade than a Thursday one, for a reason that has
  nothing to do with the market. The same distortion runs through eps, z, the
  invalidation buffer, the 0.30-to-3.0 ATR distance band, every dist/ATR
  ratio, and the activity and volatility features the new controls match on.

WHAT THIS DOES NOT CLAIM

  It does not claim any conclusion in this repository was wrong. Most results
  here are null, and a day-of-week distortion in which trades are ELIGIBLE
  does not manufacture directional skill on its own. What it does mean is that
  every number was measured on a sample selected by an artifact, and results
  that leaned on hour-of-day, session, or volatility-regime cells were
  measuring that artifact along with whatever else was there.

THE FIX AND WHY IT IS THIS ONE

  Drop bars whose true range is zero. Not "drop Saturday and Sunday" - that
  is a calendar assumption that would keep the 6,743 weekday flats and would
  break on a holiday. A zero-range bar carries no information by construction,
  so removing it removes nothing, and the Friday-to-Monday gap survives
  correctly as |high - previous close| on the first real bar.
"""
import argparse
import json
import pathlib
import sys
import time

import numpy as np
import pandas as pd

HERE = pathlib.Path(__file__).parent
sys.path.insert(0, str(HERE))
import provenance as PR
import xauusd_1000_setups as X
from bracket_bias import engine
from p01_cross_market import MARKETS, TICKS, load_bidask_h1
from profile_setups import momentum_signal

DOW = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


def drop_flat(df):
    """Remove bars the venue did not quote, identified by a zero range.

    Zero RANGE rather than zero true range on purpose: a bar that gaps and
    then does not move has a nonzero true range but told us only about the
    gap, and it is the flat bar - high == low - that is the synthetic one.

    load_bidask_h1 now applies this by default. The function stays because
    this file has to build both frames to compare them, and doing that through
    one loader flag keeps the two paths identical in every other respect."""
    h = df["high"].to_numpy(float)
    l = df["low"].to_numpy(float)
    keep = h > l
    return df[keep]


def legacy(sym):
    """The frame as it was before this filter existed."""
    return load_bidask_h1(sym, drop_flat=False)


def audit(sym):
    df = legacy(sym)
    if df is None:
        return None
    h, l = df["high"].to_numpy(float), df["low"].to_numpy(float)
    flat = h <= l
    idx = pd.DatetimeIndex(df.index)
    by_dow = {DOW[i]: float(flat[idx.dayofweek == i].mean())
              for i in range(7) if (idx.dayofweek == i).any()}
    weekend = int(flat[idx.dayofweek >= 5].sum())
    return dict(symbol=sym, bars=len(df), flat=int(flat.sum()),
                flat_share=float(flat.mean()), weekend_flat=weekend,
                weekday_flat=int(flat.sum()) - weekend, by_weekday=by_dow)


def atr_profile(df, tag):
    P = X.prep(df, 60)
    A = pd.Series(np.asarray(P["A"], float), index=pd.DatetimeIndex(P["idx"]))
    spread = pd.Series(np.asarray(P["spread"], float), index=A.index)
    gate = (spread > 0.10 * A)
    med = A.groupby(A.index.dayofweek).median()
    base = med.get(3, np.nan)
    rej = gate.groupby(gate.index.dayofweek).mean()
    return dict(tag=tag,
                atr_vs_thursday={DOW[i]: float(med[i] / base)
                                 for i in med.index if i < 7},
                gate_rejection={DOW[i]: float(rej[i])
                                for i in rej.index if i < 7},
                bars=len(df))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols", default=",".join(MARKETS))
    a = ap.parse_args()
    t0 = time.time()
    syms = [s.strip() for s in a.symbols.split(",") if s.strip()]

    print("WEEKEND CONTAMINATION - 29% of the sample is a closed market")
    print("=" * 100)
    print(__doc__.split("WHY IT MATTERS MORE THAN ITS SHARE SUGGESTS")[1]
          .split("WHAT THIS DOES NOT CLAIM")[0])

    print(f"  {'market':<9}{'bars':>10}{'flat':>10}{'share':>8}"
          f"{'weekend':>10}{'weekday':>9}")
    rows = []
    for s in syms:
        r = audit(s)
        if not r:
            continue
        rows.append(r)
        print(f"  {s:<9}{r['bars']:>10,}{r['flat']:>10,}"
              f"{r['flat_share']:>8.1%}{r['weekend_flat']:>10,}"
              f"{r['weekday_flat']:>9,}")

    print("\n" + "=" * 100)
    print("BEFORE AND AFTER, ON GOLD")
    print("=" * 100)
    df = legacy("XAUUSD")
    clean = drop_flat(df)
    before = atr_profile(df, "as-loaded")
    after = atr_profile(clean, "flat bars removed")
    print(f"  bars {before['bars']:,} -> {after['bars']:,} "
          f"({1 - after['bars']/before['bars']:.1%} removed)\n")
    print(f"  {'':<22}" + "".join(f"{d:>9}" for d in DOW[:5]))
    for lab, key in (("ATR vs Thursday", "atr_vs_thursday"),
                     ("spread gate rejects", "gate_rejection")):
        for r in (before, after):
            print(f"  {lab + ' ' + r['tag']:<22}"
                  + "".join(f"{r[key].get(d, float('nan')):>9.1%}"
                            for d in DOW[:5]))
        print()

    print("=" * 100)
    print("WHAT IT DOES TO A BOOK - same rule, same engine, both frames")
    print("=" * 100)
    print(f"  {'market':<9}{'n before':>10}{'n after':>10}{'E before':>11}"
          f"{'E after':>10}{'Mon share before':>18}{'Mon share after':>17}")
    books = []
    for s in syms:
        g = legacy(s)
        if g is None or len(g) < 20000:
            continue
        tick = TICKS.get(s, 0.00001)
        out = {}
        for tag, frame in (("before", g), ("after", drop_flat(g))):
            P = X.prep(frame, 60)
            d, I = momentum_signal(P)
            r = engine(P, d, I, tick, stop_mult=2.0)
            if r is None:
                out[tag] = None
                continue
            ent = pd.DatetimeIndex(P["idx"])[np.asarray(r[1], int)]
            out[tag] = dict(n=len(r[0]), E=float(r[0].mean()),
                            mon=float((ent.dayofweek == 0).mean()))
        if not all(out.values()):
            continue
        b, af = out["before"], out["after"]
        books.append(dict(symbol=s, before=b, after=af))
        print(f"  {s:<9}{b['n']:>10,}{af['n']:>10,}{b['E']:>+11.4f}"
              f"{af['E']:>+10.4f}{b['mon']:>17.1%}{af['mon']:>17.1%}")

    if books:
        dE = np.mean([r["after"]["E"] - r["before"]["E"] for r in books])
        mb = np.mean([r["before"]["mon"] for r in books])
        ma = np.mean([r["after"]["mon"] for r in books])
        print(f"\n  mean change in expectancy {dE:+.4f}R across "
              f"{len(books)} markets")
        print(f"  Monday's share of entries {mb:.1%} -> {ma:.1%} "
              f"(a flat week would be 20%)")
        print(f"\n  The expectancy change is the smaller half of this. The")
        print(f"  point is the sample: every result in this repository was")
        print(f"  measured on trades selected by an artifact of the feed.")

    out = HERE / "weekend_contamination.json"
    out.write_text(json.dumps(dict(
        created=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        per_market=rows, gold_before=before, gold_after=after,
        books=books,
        manifest=PR.manifest({}, [HERE / ".cache_duka" /
                                  f"{s}_H1_2003_2026.parquet" for s in syms])),
        indent=1, default=str))
    PR.log("phase0-data-integrity",
           "Is the bar series this repository has always used actually the "
           "market, or does it include hours the venue was shut?",
           tools=["measure_layers.tradability", "weekend_contamination"],
           result=dict(flat_share={r["symbol"]: r["flat_share"] for r in rows},
                       gold_gate_rejection_before=before["gate_rejection"],
                       gold_gate_rejection_after=after["gate_rejection"]),
           status="DEFECT_FOUND",
           finding="29% of every series is flat weekend and rollover bars; "
                   "Wilder ATR falls to 6.5% of its Thursday level by Sunday "
                   "and 55.6% by Monday, and the engine's spread<=10%ATR gate "
                   "rejects 84.8% of Monday bars against 56.9% of Thursday's",
           next_action="re-measure the control hierarchy on the cleaned frame "
                       "and report both",
           started=t0)
    print(f"\n  saved -> {out.name}   elapsed {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
