#!/usr/bin/env python3
"""The last lever: do not pay the spread, be paid it.

WHY THIS IS THE ONE THAT MATTERS

  Four levers are closed on measured data - conditioning states, horizon,
  financing, venue cheapness - and the shortfall is unchanged: the edge is
  +0.1120 of a round trip and needs 1.0.

  Every one of those measurements assumed the trade CROSSES the spread. A
  resting order does not.

      market in, market out     pays one full spread
      limit in, market out      pays nothing
      limit in, limit out       EARNS one full spread

  Against a +0.1120 edge that is a swing of one to two round trips, which is
  the entire shortfall. No other lever in this project was ever worth that
  much.

  It is also the execution the mechanism argues for. The signal fades an
  extension: it buys what is being sold. That is liquidity provision, and
  short-horizon reversal is the textbook compensation for providing it. The
  project has been measuring a market-making edge as though it were a
  directional one, and paying the spread twice for the privilege.

WHY IT MIGHT STILL FAIL, AND HOW THAT IS MEASURED RATHER THAN ASSUMED

  Adverse selection. A resting bid fills precisely when the market is coming
  at it, so the filled subset is not a random sample of the windows - it is
  the subset where price kept falling. The saved spread can be smaller than
  what the selection costs.

  That is measurable from the same bars: what would the FILLED windows have
  earned on a market entry, against what the UNFILLED ones would have earned?
  If the filled subset is the worse half, the fill is buying a discount on
  something that was going to be cheaper anyway.

WHAT IS BEING MEASURED IS AN UPPER BOUND, NOT A STRATEGY

  Fills are assumed whenever the quote trades THROUGH the level by a tick -
  no queue, no partial fill, no rejection, no requote. A real venue gives less
  than that and a retail CFD venue may give none of it; an earlier note in
  this project asserted exactly that, though as a claim about venue policy
  rather than a measurement.

  So the result has one honest use. If even this bound falls short, no venue
  policy anywhere can rescue it and the cost question is closed for the last
  time. If it clears, all that is established is that the tape contains the
  money - and whether a broker will hand it over is not a research question.

  Requiring a through-trade rather than a touch is the one conservatism that
  is cheap to apply and removes the largest source of optimism.
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
import reversal_anatomy as RA
import xauusd_1000_setups as X
from p01_cross_market import MARKETS, TICKS, load_bidask_h1

SEED = 17
HOLD = 2      # the order rests in bar e; the trade ends at the
              # close of bar e+1, so a resting exit has a bar of
              # its own and never competes with the entry inside one
OFFSETS = (0.0, 0.1, 0.25, 0.5, 1.0)
YEARS = 22.0


def run(sym, k, hold=HOLD, exit_passive=False):
    """Fade the previous bar with a resting order k ATR away from the open.

    THE EXIT MUST NOT PRECEDE THE FILL, AND THE FIRST VERSION LET IT

      That version exited at the OPEN of the same bar the order rested in.
      The fill happens somewhere inside that bar, so the exit came before the
      entry - a full bar of look-ahead running backwards. It reported the
      market baseline as exactly -1.0000 of a round trip on every offset and
      every market, which is the spread and nothing else, and that constant
      is what gave it away.

      Corrected: the order rests during bar e and the position is closed at
      the CLOSE of bar e+hold-1. A close is the last quote of its bar, so any
      fill inside that bar precedes it.

      The passive exit is only live from bar e+1 onward. Resting an exit in
      the same bar as the entry would ask which of two intrabar events came
      first, which is the question that killed the straddle, and this data
      cannot answer it.

    A buy limit at P fills when the ASK trades through P, because that is the
    side a buyer lifts; a sell limit fills when the BID trades through. Using
    the mid, or the favourable side, would manufacture fills the book never
    offered.

    The market baseline is computed over the IDENTICAL window, so the
    difference between them is execution and nothing else."""
    df = load_bidask_h1(sym)
    if df is None or len(df) < 20000:
        return None
    P = X.prep(df, 60)
    tick = TICKS.get(sym, 1e-5)
    N = P["N"]
    c = np.asarray(P["c"], float)
    A = np.asarray(P["A"], float)
    ask_o, bid_o = np.asarray(P["ask_o"], float), np.asarray(P["bid_o"], float)
    ask_c, bid_c = np.asarray(P["ask"], float), np.asarray(P["bid"], float)
    ask_l = np.asarray(P["ask_l"], float)
    bid_h = np.asarray(P["bid_h"], float)

    prev = np.concatenate([[np.nan], np.diff(c)])
    t = np.arange(2, N - hold - 3)
    d = -np.sign(prev[t])
    keep = d != 0
    t, d = t[keep], d[keep]
    e = t + 1                      # the bar the order rests in
    x = e + hold - 1               # the bar whose CLOSE ends the trade
    long_ = d > 0

    mid_o = (ask_o[e] + bid_o[e]) / 2
    sp = ask_o[e] - bid_o[e]
    off = k * A[t]
    level = np.where(long_, mid_o - off, mid_o + off)
    filled = np.where(long_, ask_l[e] <= level - tick,
                      bid_h[e] >= level + tick)

    # crossing exit at the close of bar x
    cross_px = np.where(long_, bid_c[x], ask_c[x])
    exit_px = cross_px
    if exit_passive and hold >= 2:
        # a resting exit, live only on bars e+1 .. x
        exit_mid = (ask_o[e + 1] + bid_o[e + 1]) / 2
        tgt = np.where(long_, exit_mid + off, exit_mid - off)
        hit = np.zeros(len(t), bool)
        for j in range(1, hold):
            b = e + j
            with np.errstate(invalid="ignore"):
                hit |= np.where(long_, bid_h[b] >= tgt + tick,
                                ask_l[b] <= tgt - tick)
        exit_px = np.where(hit, tgt, cross_px)

    pnl_passive = d * (exit_px - level)
    # the identical window entered and exited at market
    entry_mkt = np.where(long_, ask_o[e], bid_o[e])
    pnl_mkt = d * (cross_px - entry_mkt)

    ok = (np.isfinite(level) & np.isfinite(exit_px) & np.isfinite(cross_px)
          & np.isfinite(sp) & (sp > 0) & np.isfinite(A[t]) & (A[t] > 0))
    filled = filled & ok
    if filled.sum() < 200:
        return None
    n_fill, n_all = int(filled.sum()), int(ok.sum())
    unf = ok & ~filled
    adv_f = float(pnl_mkt[filled].sum() / sp[filled].sum())
    adv_u = (float(pnl_mkt[unf].sum() / sp[unf].sum())
             if unf.sum() > 200 else np.nan)
    return dict(symbol=sym, k=k, n_windows=n_all, n_filled=n_fill,
                fill_rate=n_fill / n_all,
                fills_per_year=n_fill / YEARS,
                edge_filled=float(pnl_passive[filled].sum() / sp[filled].sum()),
                edge_all=float(pnl_passive[filled].sum() / sp[ok].sum()),
                mkt_baseline=float(pnl_mkt[ok].sum() / sp[ok].sum()),
                mkt_on_filled=adv_f, mkt_on_unfilled=adv_u,
                adverse=adv_f - adv_u if np.isfinite(adv_u) else np.nan)


def summarise(rows):
    if not rows:
        return None
    def m(k):
        v = [r[k] for r in rows if np.isfinite(r.get(k, np.nan))]
        return float(np.mean(v)) if v else np.nan

    ea = [r["edge_all"] for r in rows if np.isfinite(r["edge_all"])]
    return dict(markets=len(rows), fill_rate=m("fill_rate"),
                fills_per_year=m("fills_per_year"),
                edge_filled=m("edge_filled"), edge_all=m("edge_all"),
                mkt_baseline=m("mkt_baseline"),
                mkt_on_filled=m("mkt_on_filled"),
                mkt_on_unfilled=m("mkt_on_unfilled"),
                adverse=m("adverse"),
                positive=int(sum(1 for v in ea if v > 0)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols", default=",".join(RA.PANEL))
    a = ap.parse_args()
    t0 = time.time()
    syms = [s.strip() for s in a.symbols.split(",") if s.strip()]

    print("PASSIVE EXECUTION - the upper bound of not paying the spread")
    print("=" * 108)
    print(__doc__.split("WHY IT MIGHT STILL FAIL")[1]
          .split("WHAT IS BEING MEASURED IS AN UPPER BOUND")[0])

    out = {}
    for mode, passive in (("limit in, market out", False),
                          ("limit in, limit out", True)):
        print("=" * 108)
        print(mode.upper())
        print("=" * 108)
        print(f"  {'offset':<9}{'fill rate':>11}{'fills/yr':>11}"
              f"{'edge on fills':>15}{'edge all windows':>18}"
              f"{'market same':>13}{'mkt|filled':>12}"
              f"{'mkt|missed':>12}{'adverse':>10}{'pos':>7}")
        rows = []
        for k in OFFSETS:
            per = [r for r in (run(s, k, exit_passive=passive) for s in syms)
                   if r]
            s_ = summarise(per)
            if not s_:
                continue
            s_["k"] = k
            s_["mode"] = mode
            rows.append(s_)
            print(f"  {k:<9.2f}{s_['fill_rate']*100:>10.1f}%"
                  f"{s_['fills_per_year']:>11,.0f}{s_['edge_filled']:>+15.4f}"
                  f"{s_['edge_all']:>+18.4f}"
                  f"{s_['mkt_baseline']:>+13.4f}{s_['mkt_on_filled']:>+12.4f}"
                  f"{s_['mkt_on_unfilled']:>+12.4f}{s_['adverse']:>+10.4f}"
                  f"{s_['positive']:>4}/{s_['markets']}")
        out[mode] = rows
        print()

    print("=" * 108)
    print("WHAT THE ADVERSE-SELECTION COLUMN SAYS")
    print("=" * 108)
    ref = out["limit in, market out"]
    if ref:
        mid = [r for r in ref if r["k"] == 0.25] or ref[:1]
        r = mid[0]
        print(f"  At an offset of {r['k']} ATR the resting order fills "
              f"{r['fill_rate']*100:.1f}% of the time.")
        print(f"  Those same windows, entered at market, would have earned "
              f"{r['mkt_on_filled']:+.4f} of a")
        print(f"  round trip; the windows that did NOT fill would have earned "
              f"{r['mkt_on_unfilled']:+.4f}.")
        print(f"  The difference, {r['adverse']:+.4f}, is what the fill "
              f"selects for.")
        print(f"  A large negative here means the order fills exactly when "
              f"the trade was going")
        print(f"  to be bad anyway, and the saved spread is buying a discount "
              f"on a loser.")

    print("\n" + "=" * 108)
    print("VERDICT")
    print("=" * 108)
    best = None
    for mode, rows in out.items():
        for r in rows:
            if best is None or r["edge_all"] > best["edge_all"]:
                best = r
    viable = [r for rows in out.values() for r in rows
              if r["edge_all"] > 1.0 and r["positive"] >= 6
              and r["fills_per_year"] >= 200]
    if best:
        print(f"  best: {best['mode']} at an offset of {best['k']} ATR, "
              f"{best['edge_all']:+.4f} of a round trip")
        print(f"        over all windows, {best['edge_filled']:+.4f} over the "
              f"fills, {best['fills_per_year']:,.0f} fills a year,")
        print(f"        positive on {best['positive']}/{best['markets']} "
              f"markets")
        print(f"  against the market-order baseline of +0.1120")
    print(f"\n  {len(viable)} configuration(s) clear one round trip with at "
          f"least 6 of 9 markets and 200 fills a year")
    if not viable:
        print(f"\n  Fills are assumed at the level with no queue, no partial "
              f"fill, no rejection")
        print(f"  and no requote. A real venue gives less. If the UPPER BOUND "
              f"falls short, no")
        print(f"  venue policy can rescue it, and the cost question is closed "
              f"for the last time")
        print(f"  rather than deferred to what a broker might allow.")

    p = HERE / "passive_execution.json"
    p.write_text(json.dumps(dict(
        created=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        hold=HOLD, offsets=list(OFFSETS), results=out,
        viable=len(viable), best=best,
        manifest=PR.manifest(dict(hold=HOLD, seed=SEED),
                             [HERE / ".cache_duka" /
                              f"{s}_H1_2003_2026.parquet" for s in syms])),
        indent=1, default=str))
    PR.log("phase6-passive-execution",
           "Does not paying the spread close the ninefold gap, or does "
           "adverse selection take back more than the spread is worth?",
           hypothesis="passive_execution_bound",
           tools=["passive_execution", "reversal_anatomy"],
           result=dict(results=out, viable=len(viable), best=best),
           status="MEASURED",
           finding=(f"best {best['edge_all']:+.4f} at {best['mode']} offset "
                    f"{best['k']}" if best else "none"),
           next_action="record against the registered criterion",
           started=t0)
    print(f"\n  saved -> {p.name}   elapsed {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
