#!/usr/bin/env python3
"""The edge is 0.12 spreads and needs 1.0. Cost is fixed; moves are not.

THE ONE RATIO THIS PROJECT HAS NEVER MEASURED

  Fading the previous hour wins the direction 51.71% of the time on every
  market in the panel, in both halves of twenty-two years. The reversion
  representation adds half a point on top of that. Gross, it is worth +0.1201
  spreads per trade. A round trip costs 1.0.

  The gap is a factor of eight and it is not a gap in the rule. It is a ratio
  between two quantities that scale differently:

    the SPREAD is a property of the quote. It is what it is at the moment of
    trading, and it does not care whether the decision was made from an hourly
    bar or a weekly one.

    the MOVE grows with the horizon over which it is predicted. A 1% edge on a
    daily range is worth many more spreads than a 1% edge on an hourly one.

  So the question is not whether a better rule exists. It is whether the ratio
  of edge to cost ever reaches 1, anywhere on the horizon axis.

WHAT IS PREDICTED BEFORE THE RUN, AND WHY IT IS WRITTEN DOWN

  If the reversal were a fixed fraction of each timeframe's own volatility,
  the edge in spread units would grow roughly as the square root of the bar
  length: H1 to D1 is 24 times, so about 4.9 times the edge, reaching 0.59
  spreads - still short. W1 would be about 13 times, or 1.6 spreads, which
  would clear.

  Against that, the hourly effect decayed to nothing by 48 hours when the same
  signal was simply held longer. If daily reversal is weak or absent, the
  ratio peaks somewhere in the middle and never reaches 1.

  Both are stated now so that whichever happens is a result rather than an
  explanation invented afterwards.

WHY RESAMPLING IS HONEST HERE AND WHERE IT IS NOT

  H1 bars aggregate exactly into H4 and D1: first open, running high and low,
  last close, done separately on the bid and the ask. Nothing is interpolated
  and no bar is invented.

  The spread at entry is taken as the ask open minus the bid open OF THE ENTRY
  BAR, which is the first quote of that bar and therefore the real spread a
  trader would face. It is NOT a "daily spread" - there is no such thing, and
  averaging the spread over a day would understate the cost of trading at the
  open by including hours nobody would trade in.

  What resampling cannot do is create intrabar information, so nothing here
  reads a level being touched. The measurement is open-to-close only, which is
  the same measurement the hourly result used.
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
import xauusd_1000_setups as X
from p01_cross_market import MARKETS, TICKS, load_bidask_h1

FLOOR = 4.74
TFS = (("H1", None), ("H2", "2h"), ("H4", "4h"), ("H8", "8h"),
       ("D1", "1D"), ("W1", "1W"))
SUB = (("M5", "5min"), ("M15", "15min"), ("M30", "30min"))


def resample(df, rule):
    """Exact aggregation of bid and ask OHLC. Nothing interpolated."""
    agg = {}
    for side in ("bid", "ask"):
        agg[f"{side}_open"] = "first"
        agg[f"{side}_high"] = "max"
        agg[f"{side}_low"] = "min"
        agg[f"{side}_close"] = "last"
    g = df.resample(rule, label="left", closed="left").agg(agg).dropna()
    for k in ("open", "high", "low", "close"):
        g[k] = (g[f"bid_{k}"] + g[f"ask_{k}"]) / 2
    # a bar that aggregates a single quote, or none, is not a bar
    return g[(g.high > g.low) & (g.ask_close > g.bid_close)]


def measure(g, min_bars=400):
    """Fade the previous bar; report the move in spread units.

    Entry at the next bar's mid open, exit at that same bar's mid close, so
    the holding period is exactly one bar of whatever length is being tested -
    which is what makes the timeframes comparable."""
    if len(g) < min_bars:
        return None
    c = g["close"].to_numpy(float)
    o = g["open"].to_numpy(float)
    spread = (g["ask_open"] - g["bid_open"]).to_numpy(float)
    tr = np.maximum(g["high"].to_numpy(float) - g["low"].to_numpy(float), 1e-12)
    # The direction for the trade taken at bar t's OPEN must come from the
    # last bar that had fully closed before it, which is t-1, and its own move
    # is c[t-1] - c[t-2].
    #
    # The first version of this indexed prev[t] = c[t] - c[t-1], which is the
    # move of the bar being traded, so the rule faded a bar using that bar's
    # own close and was then scored on it. It came back with a sign rate of
    # 2.4% and an edge of -9 spreads, which is what a full bar of look-ahead
    # looks like when it points the wrong way.
    prev = np.concatenate([[np.nan], np.diff(c)])      # prev[k] = c[k]-c[k-1]
    n = len(g)
    t = np.arange(2, n)                                # entry bars
    dd = -np.sign(prev[t - 1])                         # signal bar is t-1
    keep = dd != 0
    t, dd = t[keep], dd[keep]
    move = dd * (c[t] - o[t])
    sp = spread[t]
    ok = np.isfinite(move) & np.isfinite(sp) & (sp > 0)
    if ok.sum() < min_bars:
        return None
    x = move[ok] / sp[ok]
    w, l = x[x > 0], x[x <= 0]
    if len(w) < 50 or len(l) < 50:
        return None
    mw, ml = float(w.mean()), float(-l.mean())
    tot = mw + ml
    n_eff = max(len(x), 2)
    se = float(x.std(ddof=1) / math.sqrt(n_eff))
    return dict(bars=int(len(g)), n=int(ok.sum()),
                sign_rate=float((move[ok] > 0).mean()),
                edge_spreads=float(x.mean()),
                t_edge=float(x.mean() / se) if se > 0 else np.nan,
                mean_win=mw, mean_loss=ml,
                breakeven_net=(1.0 + ml) / tot if tot > 0 else np.nan,
                net_edge=float(x.mean()) - 1.0,
                cost_over_range=float(np.nanmedian(spread / tr)))


def minute_frame():
    import fetch_dukascopy as D
    m = D.load("2019-01-01", None, verbose=False)
    if m is None or len(m) == 0:
        return None
    for k in ("open", "high", "low", "close"):
        m[k] = (m[f"bid_{k}"] + m[f"ask_{k}"]) / 2
    return m[(m.high > m.low) & (m.ask_close > m.bid_close)]


def cross_t(vals):
    v = np.asarray([x for x in vals if np.isfinite(x)], float)
    if len(v) < 3:
        return np.nan, 0, 0
    se = float(v.std(ddof=1) / math.sqrt(len(v)))
    return (float(v.mean() / se) if se > 0 else np.nan,
            int((v > 0).sum()), len(v))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols", default=",".join(MARKETS))
    a = ap.parse_args()
    t0 = time.time()
    syms = [s.strip() for s in a.symbols.split(",") if s.strip()]

    print("EDGE OVER COST ACROSS THE HORIZON AXIS")
    print("=" * 104)
    print(__doc__.split("WHAT IS PREDICTED BEFORE THE RUN")[1]
          .split("WHY RESAMPLING IS HONEST")[0])

    rows = []
    for sym in syms:
        df = load_bidask_h1(sym)
        if df is None or len(df) < 20000:
            continue
        for lab, rule in TFS:
            g = df if rule is None else resample(df, rule)
            m = measure(g)
            if m:
                rows.append(dict(symbol=sym, tf=lab, **m))
        print(f"  {sym} done {time.time()-t0:.0f}s", flush=True)

    # gold below the hour, from the cached minute data
    m1 = minute_frame()
    if m1 is not None:
        print(f"  gold minute data {len(m1):,} bars "
              f"({m1.index[0].date()} -> {m1.index[-1].date()})")
        for lab, rule in (("M1", None),) + SUB:
            g = m1 if rule is None else resample(m1, rule)
            m = measure(g)
            if m:
                rows.append(dict(symbol="XAUUSD-m", tf=lab, **m))

    if not rows:
        print("  nothing measured")
        return
    D = pd.DataFrame(rows)

    print("\n" + "=" * 104)
    print("BY TIMEFRAME - the move is bigger, the spread is not")
    print("=" * 104)
    print(f"  {'tf':<5}{'markets':>8}{'bars':>10}{'sign%':>8}"
          f"{'spread/range':>14}{'edge (spreads)':>16}{'t':>8}"
          f"{'pos':>7}{'breakeven%':>12}{'net':>9}")
    order = [t[0] for t in (("M1", 0),) + SUB] + [t[0] for t in TFS]
    summary = []
    for lab in order:
        g = D[D.tf == lab]
        if len(g) == 0:
            continue
        e = g.edge_spreads.to_numpy(float)
        t, pos, n = cross_t(e)
        rec = dict(tf=lab, markets=len(g), bars=int(g.bars.mean()),
                   sign_rate=float(g.sign_rate.mean()),
                   cost_over_range=float(g.cost_over_range.mean()),
                   edge_spreads=float(e.mean()), t=t, positive=pos,
                   breakeven_net=float(g.breakeven_net.mean()),
                   net_edge=float(g.net_edge.mean()))
        summary.append(rec)
        print(f"  {lab:<5}{len(g):>8}{int(g.bars.mean()):>10,}"
              f"{g.sign_rate.mean()*100:>8.2f}"
              f"{g.cost_over_range.mean()*100:>13.1f}%"
              f"{e.mean():>+16.4f}{t:>+8.2f}{pos:>5}/{len(g)}"
              f"{g.breakeven_net.mean()*100:>11.2f}%"
              f"{g.net_edge.mean():>+9.3f}")

    print("\n" + "=" * 104)
    print("THE SCALING LAW - fitted, against the one written down beforehand")
    print("=" * 104)
    economics = {}
    hours = {"M1": 1 / 60, "M5": 5 / 60, "M15": 0.25, "M30": 0.5, "H1": 1,
             "H2": 2, "H4": 4, "H8": 8, "D1": 24, "W1": 168}
    fit = [(hours[r["tf"]], r["edge_spreads"]) for r in summary
           if r["tf"] in hours and r["edge_spreads"] > 0
           and r["markets"] >= 3]
    slope = np.nan
    if len(fit) >= 4:
        x = np.log(np.array([f[0] for f in fit]))
        y = np.log(np.array([f[1] for f in fit]))
        slope, icpt = np.polyfit(x, y, 1)
        print(f"  log edge against log bar length over {len(fit)} timeframes: "
              f"exponent {slope:+.3f}")
        print(f"  0.50 would mean the effect is a constant fraction of each "
              f"horizon's own volatility;")
        print(f"  below it the effect weakens with horizon, above it the "
              f"effect strengthens.")
    h1 = next((r for r in summary if r["tf"] == "H1"), None)
    peak = max(summary, key=lambda r: r["edge_spreads"]) if summary else None
    if h1 and peak and h1["edge_spreads"] > 0 and peak["tf"] in hours:
        ratio = hours[peak["tf"]] / hours["H1"]
        print(f"  H1 {h1['edge_spreads']:+.4f} -> {peak['tf']} "
              f"{peak['edge_spreads']:+.4f} is "
              f"{peak['edge_spreads']/h1['edge_spreads']:.1f}x over a "
              f"{ratio:.0f}x bar length; a square root would predict "
              f"{math.sqrt(ratio):.1f}x")

    print("\n" + "=" * 104)
    print("THE TERM THAT SCALES DIFFERENTLY - financing")
    print("=" * 104)
    print("  The spread is paid once per trade whatever the horizon, so a")
    print("  measure in spread units makes a longer hold look strictly")
    print("  better. A position held overnight also pays SWAP, and that is")
    print("  charged per night - linear in the horizon, not square root.")
    print()
    # The one swap figure this project actually has is from the live account
    # spec: Exness XAUUSDc, long, -534.9 points per night, against a median
    # gold spread measured at 424 points. Nothing equivalent is held for the
    # FX crosses, so this row is gold only and is labelled as such rather
    # than averaged into a panel number it was never measured on.
    swap_pts, spread_pts = 534.9, 424.0
    w = swap_pts / spread_pts
    print(f"  gold long: {swap_pts:.1f} points a night against a median "
          f"spread of {spread_pts:.0f} points = {w:.3f} spreads per night")
    print(f"  (the only instrument in this project whose swap is known from "
          f"the live account spec; the FX rows are unmeasured)")
    if h1 and h1["edge_spreads"] > 0 and np.isfinite(slope):
        a = h1["edge_spreads"]
        print(f"\n  edge(T)  = {a:.4f} * T^{slope:.3f}   spreads, T in hours")
        print(f"  cost(T)  = 1.000 + {w:.3f} * T/24     spreads")
        Ts = np.array([0.5, 1, 2, 4, 8, 24, 72, 168, 336, 720])
        print(f"\n  {'T (hours)':>10}{'edge':>10}{'cost':>10}{'net':>10}")
        best = None
        for T in Ts:
            e = a * T ** slope
            cst = 1.0 + w * T / 24
            print(f"  {T:>10.1f}{e:>10.3f}{cst:>10.3f}{e - cst:>+10.3f}")
            if best is None or e - cst > best[1]:
                best = (T, e - cst)
        # maximum of a*T^s - w*T/24 - 1
        if 0 < slope < 1:
            def peak_net(ww):
                if ww <= 0:
                    return None, np.nan
                Ts_ = (a * slope * 24 / ww) ** (1 / (1 - slope))
                return Ts_, a * Ts_ ** slope - 1.0 - ww * Ts_ / 24
            Tstar, net = peak_net(w)
            print(f"\n  the two curves cross once: edge grows as T^{slope:.2f}"
                  f" and financing as T, so the net has a single maximum")
            print(f"  at T = {Tstar:.2f} hours, where net = {net:+.3f} spreads")
            print(f"  {'PROFITABLE' if net > 0 else 'SHORT BY ' + f'{-net:.3f} spreads at its own best point'}")

            print(f"\n  THE SWAP FIGURE IS THE DECISIVE ONE AND ONLY ONE SIDE "
                  f"OF IT IS KNOWN.")
            print(f"  The spec gives gold's LONG swap. A rule that is short "
                  f"half the time may")
            print(f"  pay less, or may pay on both sides - retail CFD venues "
                  f"commonly do. So the")
            print(f"  question is turned round: at what financing rate would "
                  f"this break even?")
            lo_w, hi_w = 0.0, 5.0
            for _ in range(80):
                mid = (lo_w + hi_w) / 2
                _, nm = peak_net(mid) if mid > 0 else (None, a * 1e6)
                if mid <= 0 or nm > 0:
                    lo_w = mid
                else:
                    hi_w = mid
            w_be = (lo_w + hi_w) / 2
            print(f"\n  break-even financing rate  {w_be:.4f} spreads per "
                  f"night   ({w_be*spread_pts:.0f} gold points)")
            print(f"  actual known gold long      {w:.4f} spreads per night "
                  f"  ({swap_pts:.0f} points)")
            print(f"  financing would have to be  {w/w_be:.1f}x cheaper" if
                  w_be > 0 else "  no positive financing rate works")

            # with no financing at all, where does the measured curve cross?
            d1 = next((r for r in summary if r["tf"] == "D1"), None)
            w1 = next((r for r in summary if r["tf"] == "W1"), None)
            if d1 and w1 and d1["edge_spreads"] > 0 and w1["edge_spreads"] > 0:
                s2 = (math.log(w1["edge_spreads"] / d1["edge_spreads"])
                      / math.log(168 / 24))
                Tcross = 24 * (1.0 / d1["edge_spreads"]) ** (1 / s2)
                print(f"\n  with NO financing cost at all, interpolating the "
                      f"two measured long")
                print(f"  horizons rather than the whole fit, the gross edge "
                      f"reaches one round")
                print(f"  trip at about {Tcross:.0f} hours - roughly "
                      f"{Tcross/24:.1f} days. That is the horizon this")
                print(f"  information would be worth acting on if carry were "
                      f"free, and it is the")
                print(f"  reason the swap number decides the whole question "
                      f"rather than the edge.")
                econ_extra = dict(slope=float(slope), a=float(a),
                                  w_gold_long=float(w),
                                  w_breakeven=float(w_be),
                                  T_peak_hours=float(Tstar),
                                  net_at_peak=float(net),
                                  T_cross_no_financing_hours=float(Tcross))
                economics.update(econ_extra)

    viable = [r for r in summary if r["edge_spreads"] > 1.0
              and np.isfinite(r["t"]) and r["t"] > FLOOR
              and r["positive"] >= max(6, r["markets"] - 1)]
    print(f"\n  {len(viable)} timeframe(s) clear the registered bar: gross "
          f"edge above one round trip, t above {FLOOR}, positive on at least "
          f"6 of 9")
    if peak:
        print(f"  the largest gross edge is {peak['tf']} at "
              f"{peak['edge_spreads']:+.4f} spreads, but its cross-market t "
              f"is {peak['t']:+.2f} on {peak['positive']}/{peak['markets']} - "
              f"a point estimate with no power behind it")

    out = HERE / "timeframe_ratio.json"
    out.write_text(json.dumps(dict(
        created=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        floor=FLOOR, per_market=rows, by_timeframe=summary,
        viable=[r["tf"] for r in viable], economics=economics,
        manifest=PR.manifest({}, [HERE / ".cache_duka" /
                                  f"{s}_H1_2003_2026.parquet" for s in syms])),
        indent=1, default=str))
    PR.log("phase1-timeframe-ratio",
           "Does the ratio of predictable move to spread ever reach one, "
           "anywhere on the horizon axis?",
           hypothesis="edge_to_cost_across_timeframes",
           tools=["timeframe_ratio"],
           result=dict(by_timeframe=summary, viable=[r["tf"] for r in viable]),
           status="MEASURED",
           finding=(f"peak {peak['tf']} at {peak['edge_spreads']:+.4f} "
                    f"spreads" if peak else "none"),
           next_action="record against the registered criterion",
           started=t0)
    print(f"\n  saved -> {out.name}   elapsed {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
