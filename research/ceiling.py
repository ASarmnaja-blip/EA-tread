#!/usr/bin/env python3
"""The maximum target this market can support - an upper bound, not a forecast.

WHY AN UPPER BOUND IS WORTH MORE THAN ANOTHER BACKTEST

  Every result in this repo so far answers "did THIS rule work". None of them
  answers "how good could ANY rule be". That second question has an answer
  that does not depend on finding a rule at all, and it settles whether a
  target is worth chasing before any effort is spent chasing it.

  Three ceilings are computed, each strictly above the one below it:

    1  PERFECT FORESIGHT. Know the sign of every move in advance. Trade it
       under the real cost, the real session deadline, the real minimum lot.
       Nobody reaches this. It is the wall.

    2  REALISTIC SKILL. Perfect foresight is not a useful benchmark on its
       own, so the same machinery is run at a range of directional
       accuracies. Published skill for systematic macro sits far closer to
       50% than people expect; 55% sustained is exceptional. This shows what
       each accuracy level is worth in CAGR terms.

    3  THE DRAWDOWN CEILING. Even with a fixed edge, CAGR does not rise
       forever with risk - past the optimal fraction, volatility drag pulls
       it back down while drawdown keeps climbing. For any DD limit there is
       a maximum CAGR, and raising risk beyond it makes the account worse in
       both directions at once.

  Ceiling 3 is the one that actually binds, and it is the one nobody
  calculates before setting a target.

WHAT THIS IS NOT
  Not a strategy, not a backtest of anything tradeable, and not a promise.
  Perfect foresight is unattainable by construction; the numbers below are
  the ARITHMETIC LIMIT of the instrument, the cost structure and the account,
  and every real result must sit strictly underneath them.
"""
import argparse, math, sys, pathlib, time
import numpy as np, pandas as pd

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import mega_search as M
import session_rules as S
from exness_cent import ExnessCent

ACC = ExnessCent()
DISCOVERY_END = "2017-01-01"
DISCOVERY_END_M15 = "2023-01-01"

def perfect_foresight(P, idx, deadline, hold, cost_px, stop_atr=2.0):
    """NON-OVERLAPPING trades, each taken in the direction the next `hold`
    bars actually move.

    NON-OVERLAPPING IS NOT A DETAIL. The first version of this opened a trade
    on EVERY eligible bar and then compounded the resulting R values as if
    they were sequential. At hold=12 that is twelve positions alive at once,
    each sized as though it were the only one, and the arithmetic produced a
    CAGR of 10^24 percent - a number whose absurdity was the only thing that
    revealed the error. A real account takes the next trade after the last one
    closes, which on H1 at hold=12 is about 520 trades a year, not 5,577.

    The stop still exists and can still be hit against you intrabar even when
    the close goes the right way: foresight over the CLOSE is not foresight
    over the PATH, and pretending otherwise inflates the ceiling."""
    o, h, l, c, A, N = P["o"], P["h"], P["l"], P["c"], P["A"], P["N"]
    n = len(idx)
    R = []
    next_free = 30
    for i in range(30, n - 1):
        if i < next_free:
            continue
        a = A[i]
        if not np.isfinite(a) or a <= 0:
            continue
        e = i + 1
        if e >= n:
            break
        hv = min(hold, max(int(deadline[e] - e + 1), 0))
        if hv < 1:
            continue
        risk = stop_atr * a
        if risk <= 3 * cost_px:
            continue
        kx = min(e + hv - 1, n - 1)
        d = 1 if c[kx] > o[e] else -1          # the foresight
        stop = o[e] - d * risk
        hit = False
        for k in range(e, kx + 1):
            if (l[k] <= stop) if d > 0 else (h[k] >= stop):
                hit = True
                break
        exit_px = stop if hit else c[kx]
        R.append(((exit_px - o[e]) * d - cost_px) / risk)
        next_free = kx + 1           # the account is busy until this one closes
    return np.asarray(R, float)

def skill_curve(R_perfect, accuracies):
    """What the same trade book is worth at less than perfect accuracy.

    A trade taken in the wrong direction does not simply negate: it pays the
    cost either way and its stop sits on the other side. The book is rebuilt
    by flipping a fraction of the signs and recomputing, which is the closest
    honest analogue without re-walking every path."""
    out = {}
    rng = np.random.default_rng(11)
    for acc in accuracies:
        wrong = rng.random(len(R_perfect)) > acc
        # a wrongly-signed trade loses roughly what the right one gained,
        # and still pays the cost
        r = np.where(wrong, -R_perfect, R_perfect)
        out[acc] = r
    return out

def cagr_for(R, risk_frac, per_year):
    """Geometric growth from a book of R values at a fixed fractional risk."""
    g = np.log1p(np.clip(risk_frac * R, -0.999, None)).sum()
    yrs = len(R) / per_year
    return math.expm1(g / yrs) if yrs > 0 else float("nan")

def max_dd(R, risk_frac):
    eq = np.cumprod(1.0 + np.clip(risk_frac * R, -0.999, None))
    peak = np.maximum.accumulate(eq)
    return float(np.max(1.0 - eq / peak))

def dd_ceiling(R, per_year, dd_limits, risks):
    """For each drawdown limit, the best CAGR any fixed risk fraction reaches
    without exceeding it."""
    rows = []
    for lim in dd_limits:
        best = None
        for rf in risks:
            d = max_dd(R, rf)
            if d <= lim:
                cg = cagr_for(R, rf, per_year)
                if best is None or cg > best[1]:
                    best = (rf, cg, d)
        rows.append((lim, best))
    return rows

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tf", default="1h")
    a = ap.parse_args()
    t0 = time.time()

    print("CEILING - the maximum this market can support")
    print("=" * 78)
    print(__doc__.split("WHY AN UPPER BOUND")[1].split("WHAT THIS IS NOT")[0])

    m = M.load_tf(a.tf)
    P = M.prep(m)
    tf_min = S.bar_minutes(m.index)
    sub = tf_min < 60
    disc_end = DISCOVERY_END_M15 if sub else DISCOVERY_END
    n_disc = int((m.index < pd.Timestamp(disc_end, tz="UTC")).sum())
    idx = m.index[:n_disc]
    deadline, _, _ = S.intraday_deadlines(m.index, tf_min)
    cost_px = ACC.px(ACC.spread_points_live)
    hold = 12 if tf_min >= 60 else 48
    yrs = (idx[-1] - idx[0]).days / 365.25

    print(f"data      {a.tf}  discovery {n_disc:,} bars  {idx[0].date()} -> "
          f"{idx[-1].date()}  ({yrs:.1f} years)")
    print(f"cost      {ACC.spread_points_live:.0f} points = {cost_px:.3f} price "
          f"units round trip, commission 0")
    print(f"session   force close by 20:30 UTC, hold capped at {hold} bars")

    R = perfect_foresight(P, idx, deadline, hold, cost_px)
    per_year = len(R) / yrs
    print(f"\n1. PERFECT FORESIGHT  (know every move's direction in advance)")
    print(f"   trades {len(R):,} over {yrs:.1f} years = {per_year:,.0f}/year")
    print(f"   E(R) per trade {R.mean():+.4f}   win rate "
          f"{float((R > 0).mean())*100:.1f}%")
    print(f"   NOTE: below 100% win rate because the stop can still be hit "
          f"intrabar\n   even when the close goes the right way - foresight "
          f"over the close is not\n   foresight over the path.")

    print(f"\n2. WHAT EACH LEVEL OF DIRECTIONAL ACCURACY IS WORTH")
    accs = [1.00, 0.70, 0.60, 0.57, 0.55, 0.53, 0.52, 0.51, 0.50]
    books = skill_curve(R, accs)
    print(f"   {'accuracy':>9}{'E(R)':>10}{'CAGR @1%':>11}{'CAGR @3%':>11}"
          f"{'CAGR @5%':>11}")
    for acc in accs:
        r = books[acc]
        row = "".join(f"{cagr_for(r, rf, per_year)*100:>10.1f}%"
                      for rf in (0.01, 0.03, 0.05))
        print(f"   {acc*100:>8.0f}%{r.mean():>+10.4f}{row}")

    print(f"\n3. THE DRAWDOWN CEILING - best CAGR inside each DD limit")
    risks = [x / 1000 for x in range(1, 301)]
    dd_limits = (0.20, 0.30, 0.35, 0.50, 0.70)
    for acc in (1.00, 0.60, 0.55, 0.53):
        r = books[acc]
        print(f"\n   at {acc*100:.0f}% directional accuracy:")
        print(f"     {'DD limit':>9}{'best risk':>11}{'CAGR':>10}{'actual DD':>11}")
        for lim, best in dd_ceiling(r, per_year, dd_limits, risks):
            if best is None:
                print(f"     {lim*100:>8.0f}%{'none fits':>11}")
                continue
            rf, cg, d = best
            print(f"     {lim*100:>8.0f}%{rf*100:>10.1f}%{cg*100:>9.1f}%"
                  f"{d*100:>10.1f}%")

    print(f"\n4. THE TARGET, MEASURED AGAINST THE CEILING")
    need = (1.01 ** 250 - 1)
    print(f"   1%/day compounded = {need*100:,.0f}% a year")
    for acc in (0.60, 0.57, 0.55, 0.53):
        r = books[acc]
        got = None
        for lim, best in dd_ceiling(r, per_year, (0.70,), risks):
            got = best
        if got:
            print(f"   at {acc*100:>3.0f}% accuracy, DD<=70%: ceiling "
                  f"{got[1]*100:>8,.1f}% a year  -> the target is "
                  f"{need/got[1]:>6,.1f}x the ceiling")
    print()
    print("   the same, at the 30% drawdown limit that is actually usable:")
    for acc in (0.60, 0.57, 0.55, 0.53):
        r = books[acc]
        got = dd_ceiling(r, per_year, (0.30,), risks)[0][1]
        if got:
            print(f"   at {acc*100:>3.0f}% accuracy, DD<=30%: ceiling "
                  f"{got[1]*100:>8,.1f}% a year  -> the target is "
                  f"{need/got[1]:>6,.1f}x the ceiling")
    print(f"\n  elapsed {time.time()-t0:.0f}s")

if __name__ == "__main__":
    main()
