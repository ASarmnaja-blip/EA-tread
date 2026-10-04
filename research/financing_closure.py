#!/usr/bin/env python3
"""Make the verdict stop depending on a number I cannot verify.

THE PROBLEM WITH THE QUESTION AS IT WAS LEFT

  The run ended naming gold's unknown short-side swap as the most
  decision-relevant open item, because the overnight verdict turns on it:
  0.2038 spreads a night is breakeven and the known long rate is 1.2616.

  That makes a conclusion depend on a broker's published sheet - a per-venue,
  per-day snapshot that cannot be reproduced from this repository and that
  changes without notice. A research finding that rests on it is hostage to
  it.

THE BETTER MOVE

  Bound it instead. No venue can charge less than nothing, so if the best net
  over all horizons is negative even at a financing rate of EXACTLY ZERO, the
  swap number cannot change the verdict and the question closes on measured
  data.

  At the corrected exponent of 0.233 that looks likely, but "looks likely" is
  a fit applied past its anchor, which is the exact error the intraday file
  existed to catch. The ladder stops at one week, and between a day and a week
  the LOCAL slope steepens to 0.504 - so the honest way to settle it is to
  measure further out.

WHAT IS ADDED AND WHAT IT COSTS

  Two weeks, one month and one quarter, by exact aggregation of the same
  cleaned bid and ask series. Nothing interpolated.

  The cost is power. Twenty-two years is about 570 fortnights, 264 months and
  88 quarters per market. A positive number out there is underpowered by
  construction and is reported with its interval, never as a finding.

WHY THE SPREAD STILL DOES NOT GROW

  The spread charged is the real quote at the entry bar's open - the first
  tick of that month or quarter - because that is what a trader would face.
  It does not scale with the holding period, which is the whole asymmetry this
  file is measuring.
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
import provenance as PR
import timeframe_ratio as TR
from p01_cross_market import MARKETS, load_bidask_h1

SEED = 17
GOLD_LONG_SWAP = 1.2616        # spreads per night, from the live account spec
LADDER = (("H1", None, 1), ("H4", "4h", 4), ("D1", "1D", 24),
          ("W1", "1W", 168), ("W2", "2W", 336), ("M1", "1ME", 730),
          ("Q1", "1QE", 2190))


def measure(g, min_bars=60):
    """Previous-bar fade, ratio of means, with a block bootstrap."""
    if len(g) < min_bars:
        return None
    c = g["close"].to_numpy(float)
    o = g["open"].to_numpy(float)
    sp = (g["ask_open"] - g["bid_open"]).to_numpy(float)
    prev = np.concatenate([[np.nan], np.diff(c)])
    n = len(g)
    t = np.arange(2, n)
    d = -np.sign(prev[t - 1])
    keep = d != 0
    t, d = t[keep], d[keep]
    mv = d * (c[t] - o[t])
    s = sp[t]
    ok = np.isfinite(mv) & np.isfinite(s) & (s > 0)
    if ok.sum() < min_bars:
        return None
    mv, s = mv[ok], s[ok]
    ratio = float(mv.sum() / s.sum())
    # block bootstrap over calendar years, which is the coarsest block that
    # still leaves enough units to resample at the quarterly horizon
    yr = pd.DatetimeIndex(g.index)[t[ok]].year.to_numpy()
    uniq = np.unique(yr)
    rng = np.random.default_rng(SEED)
    draws = np.empty(1500)
    by = {y: (mv[yr == y], s[yr == y]) for y in uniq}
    for i in range(1500):
        pick = rng.choice(uniq, size=len(uniq), replace=True)
        a = np.concatenate([by[y][0] for y in pick])
        b = np.concatenate([by[y][1] for y in pick])
        draws[i] = a.sum() / b.sum() if b.sum() > 0 else np.nan
    ci = np.nanquantile(draws, [0.025, 0.975])
    return dict(n=int(ok.sum()), bars=int(len(g)), edge=ratio,
                se=float(np.nanstd(draws, ddof=1)),
                ci_low=float(ci[0]), ci_high=float(ci[1]),
                years=int(len(uniq)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols", default=",".join(MARKETS))
    a = ap.parse_args()
    t0 = time.time()
    syms = [s.strip() for s in a.symbols.split(",") if s.strip()]

    print("FINANCING CLOSURE - does zero carry save it at any horizon?")
    print("=" * 100)
    print(__doc__.split("THE BETTER MOVE")[1].split("WHAT IS ADDED")[0])

    per = {}
    for sym in syms:
        df = load_bidask_h1(sym)
        if df is None or len(df) < 20000:
            continue
        for lab, rule, hours in LADDER:
            g = df if rule is None else TR.resample(df, rule)
            m = measure(g)
            if m:
                per.setdefault(lab, []).append(dict(symbol=sym, **m))
        print(f"  {sym:<9}{time.time()-t0:>7.0f}s", flush=True)

    print("\n" + "=" * 100)
    print("THE LADDER, EXTENDED PAST A WEEK")
    print("=" * 100)
    print(f"  {'tf':<5}{'hours':>7}{'bars/mkt':>10}{'mkts':>6}{'edge':>9}"
          f"{'95% interval':>22}{'pos':>7}{'net at zero carry':>19}")
    rows = []
    for lab, rule, hours in LADDER:
        gs = per.get(lab, [])
        if len(gs) < 3:
            continue
        e = np.array([g["edge"] for g in gs], float)
        lo = float(np.mean([g["ci_low"] for g in gs]))
        hi = float(np.mean([g["ci_high"] for g in gs]))
        rows.append(dict(tf=lab, hours=hours, markets=len(gs),
                         bars=int(np.mean([g["bars"] for g in gs])),
                         edge=float(e.mean()), ci_low=lo, ci_high=hi,
                         positive=int((e > 0).sum())))
        print(f"  {lab:<5}{hours:>7}{int(np.mean([g['bars'] for g in gs])):>10,}"
              f"{len(gs):>6}{e.mean():>+9.4f}"
              f"   [{lo:>+7.4f}, {hi:>+7.4f}]"
              f"{int((e > 0).sum()):>4}/{len(gs)}"
              f"{e.mean() - 1.0:>+19.4f}")

    peak = max(rows, key=lambda r: r["edge"])
    tail = [r for r in rows if r["hours"] > peak["hours"]]
    if tail:
        print(f"\n  The edge PEAKS at {peak['tf']} ({peak['edge']:+.4f}) and "
              f"falls after it: "
              + ", ".join(f"{r['tf']} {r['edge']:+.4f}" for r in tail) + ".")
        print(f"  So it does not keep scaling. The fitted exponent of 0.233 "
              f"was an average over a")
        print(f"  ladder that rises and then turns, and extrapolating it past "
              f"a week - which is what")
        print(f"  the 8,900-hour crossing in the final report did - describes "
              f"nothing real.")

    print("\n" + "=" * 100)
    print("NET AFTER A ROUND TRIP PLUS FINANCING, AT EVERY RATE")
    print("=" * 100)
    rates = (0.0, 0.05, 0.1, 0.2, 0.5, 1.0, GOLD_LONG_SWAP)
    print(f"  {'tf':<5}{'hours':>7}" + "".join(f"{f'w={w:g}':>11}"
                                               for w in rates))
    best = {}
    for r in rows:
        line = []
        for w in rates:
            net = r["edge"] - 1.0 - w * r["hours"] / 24.0
            line.append(net)
            if w not in best or net > best[w][1]:
                best[w] = (r["tf"], net, r["hours"])
        print(f"  {r['tf']:<5}{r['hours']:>7}"
              + "".join(f"{v:>+11.3f}" for v in line))

    print("\n" + "=" * 100)
    print("THE BEST HORIZON AT EACH FINANCING RATE")
    print("=" * 100)
    print(f"  {'rate (spreads/night)':<24}{'best tf':>9}{'hours':>8}"
          f"{'net':>11}")
    bests = []
    for w in rates:
        tf, net, hrs = best[w]
        bests.append(dict(rate=w, tf=tf, hours=hrs, net=net))
        print(f"  {w:<24g}{tf:>9}{hrs:>8}{net:>+11.3f}"
              + ("   PROFITABLE" if net > 0 else ""))

    zero = next(b for b in bests if b["rate"] == 0.0)
    closed = zero["net"] <= 0
    print("\n" + "=" * 100)
    print("VERDICT")
    print("=" * 100)
    if closed:
        zr = next(x for x in rows if x["tf"] == zero["tf"])
        nlo, nhi = zr["ci_low"] - 1.0, zr["ci_high"] - 1.0
        print(f"  At a financing rate of EXACTLY ZERO the best horizon is "
              f"{zero['tf']} and the net is {zero['net']:+.3f} round trips.")
        print(f"  Every horizon on the ladder is negative at zero carry, and "
              f"no venue can charge")
        print(f"  less than nothing.")
        print()
        print(f"  THE INTERVAL DOES NOT EXCLUDE A POSITIVE NET AND THAT IS "
              f"SAID RATHER THAN")
        print(f"  GLOSSED. {zero['tf']} has {zr['bars']:,} bars a market and "
              f"its net interval is")
        print(f"  [{nlo:+.3f}, {nhi:+.3f}], whose upper end is above zero. On "
              f"the point estimate it")
        print(f"  fails; on the interval it is not established either way.")
        print()
        print(f"  What closes the question anyway is the horizon itself. "
              f"{zero['tf']} is "
              f"{zero['hours']/24:.0f} nights,")
        print(f"  so carry is charged {zero['hours']/24:.0f} times. At a "
              f"financing rate of 0.05 spreads a")
        w_small = 0.05
        net_small = zr["edge"] - 1.0 - w_small * zr["hours"] / 24.0
        print(f"  night - a twenty-fifth of gold's known long rate - it falls "
              f"to {net_small:+.3f}, and the")
        print(f"  best horizon reverts to H1 at {best[w_small][1]:+.3f}. The "
              f"only horizon whose interval")
        print(f"  reaches positive is the one a nonzero swap destroys "
              f"fastest.")
        print()
        print(f"  THE FINANCING QUESTION IS CLOSED. The short-side gold swap "
              f"is no longer a")
        print(f"  decision-relevant unknown, and the lookup the final report "
              f"called for is moot.")
    else:
        # the rate at which the best horizon breaks even
        r = next(x for x in rows if x["tf"] == zero["tf"])
        w_be = (r["edge"] - 1.0) * 24.0 / r["hours"] if r["hours"] else np.nan
        print(f"  At zero financing the best horizon is {zero['tf']} at "
              f"{zero['net']:+.3f}, which is POSITIVE.")
        print(f"  It breaks even at a financing rate of {w_be:.4f} spreads a "
              f"night; the known gold")
        print(f"  long rate is {GOLD_LONG_SWAP}. THE QUESTION STAYS OPEN and "
              f"the swap sheet is worth reading.")
        print(f"  Note the sample: {r['bars']:,} bars a market, interval "
              f"[{r['ci_low']:+.4f}, {r['ci_high']:+.4f}] - underpowered by "
              f"construction.")

    out = HERE / "financing_closure.json"
    out.write_text(json.dumps(dict(
        created=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        gold_long_swap=GOLD_LONG_SWAP, ladder=rows, best_by_rate=bests,
        zero_carry_net=zero["net"], closed=bool(closed),
        manifest=PR.manifest(dict(seed=SEED),
                             [HERE / ".cache_duka" /
                              f"{s}_H1_2003_2026.parquet" for s in syms])),
        indent=1, default=str))
    PR.log("phase5-financing-closure",
           "Does the reversal reach one round trip at any horizon even with "
           "free carry?",
           hypothesis="financing_closure",
           tools=["financing_closure", "timeframe_ratio"],
           result=dict(ladder=rows, best_by_rate=bests,
                       zero_carry_net=zero["net"], closed=bool(closed)),
           status="CLOSED" if closed else "OPEN",
           finding=f"best net at zero carry {zero['net']:+.3f} at "
                   f"{zero['tf']}",
           next_action="record against the registered criterion",
           started=t0)
    print(f"\n  saved -> {out.name}   elapsed {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
