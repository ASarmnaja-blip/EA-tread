#!/usr/bin/env python3
"""Structural flow: the one source of edge this account has not tested.

WHY THIS AND NOT ANOTHER RULE SEARCH

  An entry pattern does not create an edge. An edge creates an entry pattern.
  Somebody has to be on the other side losing money for a reason, and there
  are only five reasons that exist:

    information   know it first        - we have public OHLC, same as everyone
    speed         act first            - H1 bars and a retail fill, so no
    risk bearing  paid to hold risk    - the account's own rules forbid holding
                                         overnight, and gold longs PAY 534.9
                                         points a night rather than earn it
    constraints   do what funds cannot - real, but "sit out" earns nothing by
                                         itself
    STRUCTURAL    orders that MUST be  - never tested here
    FLOW          placed at a known
                  time, by someone who
                  is not trying to
                  predict anything

  Only the last one is open, and it is the only one of the five that produces
  a repeating, clock-anchored pattern - which is exactly what a mechanical
  system needs. A pension fund rebalancing on the last day of the month is not
  forecasting; it is complying. The LBMA auction participants are not taking a
  view; they are clearing a benchmark.

WHAT IS BEING MEASURED - AND WHAT IS DELIBERATELY NOT

  NOT "does this rule make money". That question needs a stop, a target, a
  horizon and a filter, and each of those multiplies k until nothing can clear
  its own noise floor. This measures the raw conditional mean forward return
  at a moment in the clock or the calendar, in ATR units, with no rule
  parameters at all. One number per hypothesis.

  That buys two things. Statistical power: 75,668 discovery bars instead of
  the ~1,500 trades a single configuration yields. And interpretability: if
  nothing shows here, no rule built on top of these moments can work either,
  because there is nothing underneath for a rule to harvest.

THE HYPOTHESES, DECLARED BEFORE THE RUN

  Each is a moment when someone is known to be transacting for reasons that
  have nothing to do with where they think price is going. Times are handled
  in their OWN exchange timezone with DST, not as fixed UTC offsets - the
  London auction moves an hour twice a year and testing it at a fixed UTC hour
  would smear the effect across two different clock times.

    1  LBMA AM auction      10:30 Europe/London - the benchmark fix
    2  LBMA PM auction      15:00 Europe/London - the larger of the two
    3  COMEX settlement     13:30 America/New_York - futures settlement
    4  NY cash open         09:30 America/New_York
    5  London open          08:00 Europe/London
    6  month-end            last 2 trading days - rebalancing
    7  month-start          first 2 trading days - inflows
    8  quarter-end          last 3 trading days - the heavier rebalance
    9  turn of month        last 1 + first 3 - the classic combined window
   10-14  day of week       Monday through Friday, one hypothesis each
   15  Friday late          after 15:00 UTC Friday - position squaring

  Two forward horizons are tested for each: 1 bar and 4 bars. So

      k = 15 conditions x 2 horizons = 30 hypotheses
      noise floor = sqrt(2 ln 30) = 2.61

PASS / FAIL, FIXED BEFORE THE RUN

  A hypothesis is DETECTED only if the block-bootstrap 95% CI on the mean
  forward return excludes zero AND |t| exceeds the floor above.

  A detected effect is TRADEABLE only if, additionally, its absolute size
  exceeds the round-trip cost in the same units. At 260 points against a
  median H1 ATR of 2.984 that is 0.0871 ATR; at the historical median spread
  of 377 points it is 0.1263 ATR. DETECTION AND TRADEABILITY ARE DIFFERENT
  BARS and an effect can clear the first while failing the second - that is
  the expected outcome for most real market microstructure, and reporting a
  detected-but-untradeable effect as a finding would be the same error this
  repo has spent its whole history removing.

  DISCOVERY DATA ONLY. Validation and holdout are not touched.
"""
import argparse, math, sys, pathlib, json, time
import numpy as np, pandas as pd

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import mega_search as M

DISCOVERY_END = "2017-01-01"
# M15 only exists from 2019 in the M1 cache, so it needs its own split - the
# same one already declared in exness_backtest.py, not a new choice made here.
DISCOVERY_END_M15 = "2023-01-01"
# Horizons are declared per timeframe so the WALL-CLOCK windows match: 1 and 4
# hours on H1; 15 minutes, 1 hour and 4 hours on M15. Adding the third horizon
# raises k for the M15 run and the floor moves with it.
HORIZONS_H1 = (1, 4)
HORIZONS_M15 = (1, 4, 16)
HORIZONS = HORIZONS_H1
COST_ATR_LIVE = 0.0871      # 260 points / median H1 ATR
COST_ATR_HIST = 0.1263      # 377 points (the real historical median) / same

def local_hour_mask(index, tz, hour, minute=0):
    """Bars whose LOCAL time in `tz` is the given hour.

    Done by converting the index, not by offsetting UTC, so the daylight
    saving shift moves with the exchange the way the real auction does."""
    loc = index.tz_convert(tz)
    return ((loc.hour.to_numpy() == hour)
            & (loc.minute.to_numpy() == minute))

def trading_day_ordinals(index):
    """For each bar: which trading day of the month it is, counted from the
    start (1, 2, 3...) and from the end (-1 is the last, -2 the one before)."""
    days = pd.Series(index.normalize(), index=range(len(index)))
    uniq = days.drop_duplicates().to_numpy()
    # tz is dropped here deliberately: month membership is a calendar fact and
    # the warning about losing the timezone is noise for that purpose
    ym = pd.DatetimeIndex(uniq).tz_localize(None).to_period("M")
    fwd, bwd = {}, {}
    for period in pd.unique(ym):
        sel = uniq[ym == period]
        for k, d in enumerate(sel):
            fwd[d] = k + 1
            bwd[d] = k - len(sel)          # -1 for the last day
    dn = index.normalize().to_numpy()
    return (np.array([fwd[d] for d in dn]),
            np.array([bwd[d] for d in dn]))

def build_conditions(index):
    """The 15 declared conditions, as boolean masks over bars."""
    fwd_day, bwd_day = trading_day_ordinals(index)
    q_end_month = np.isin(index.month.to_numpy(), [3, 6, 9, 12])
    C = {}
    # H1 bars start on the hour, so the 10:30 auction falls inside the 10:00
    # bar; the mask is written against the bar that CONTAINS the event.
    C["lbma_am_1030_london"] = local_hour_mask(index, "Europe/London", 10, 0)
    C["lbma_pm_1500_london"] = local_hour_mask(index, "Europe/London", 15, 0)
    C["comex_settle_1330_ny"] = local_hour_mask(index, "America/New_York", 13, 0)
    C["ny_cash_open_0930"] = local_hour_mask(index, "America/New_York", 9, 0)
    C["london_open_0800"] = local_hour_mask(index, "Europe/London", 8, 0)
    C["month_end_last2"] = bwd_day >= -2
    C["month_start_first2"] = fwd_day <= 2
    C["quarter_end_last3"] = (bwd_day >= -3) & q_end_month
    C["turn_of_month"] = (bwd_day >= -1) | (fwd_day <= 3)
    for k, name in enumerate(["monday", "tuesday", "wednesday", "thursday",
                              "friday"]):
        C[f"dow_{name}"] = index.dayofweek.to_numpy() == k
    C["friday_late"] = ((index.dayofweek.to_numpy() == 4)
                        & (index.hour.to_numpy() >= 15))
    return C

def forward_returns(P, h):
    """Forward return over h bars, in ATR units, aligned to the SIGNAL bar.

    ATR is taken at the signal bar so the scaling uses only information
    available at that moment."""
    c, A, N = P["c"], P["A"], P["N"]
    fwd = np.full(N, np.nan)
    fwd[:N - h] = (c[h:] - c[:N - h]) / np.maximum(A[:N - h], 1e-9)
    return fwd

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tf", default="1h")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    t0 = time.time()

    print("STRUCTURAL FLOW - clock and calendar moments, no rule parameters")
    print("=" * 86)
    print(__doc__.split("THE HYPOTHESES")[1].split("PASS / FAIL")[0])
    print("PASS / FAIL" + __doc__.split("PASS / FAIL")[1].split('"""')[0])

    m = M.load_tf(a.tf)
    P = M.prep(m)
    sub_hourly = (m.index[1] - m.index[0]) < pd.Timedelta(minutes=60)
    disc_end = DISCOVERY_END_M15 if sub_hourly else DISCOVERY_END
    horizons = HORIZONS_M15 if sub_hourly else HORIZONS_H1
    n_disc = int((m.index < pd.Timestamp(disc_end, tz="UTC")).sum())
    idx = m.index[:n_disc]
    print(f"DISCOVERY: {n_disc:,} bars  {idx[0].date()} -> {idx[-1].date()}"
          f"   (split ends {disc_end})")

    C = build_conditions(idx)
    k = len(C) * len(horizons)
    bar = math.sqrt(2 * math.log(k))
    print(f"hypotheses: {len(C)} conditions x {len(horizons)} horizons = {k}"
          f"   noise floor |t| > {bar:.2f}")
    atr_med = float(np.median(P["A"][:n_disc][np.isfinite(P["A"][:n_disc])]))
    cost_live = 0.260 / atr_med
    cost_hist = 0.377 / atr_med
    globals()["COST_ATR_LIVE"] = cost_live
    print(f"median ATR on this timeframe: {atr_med:.4f} price units")
    print(f"tradeable bar: |effect| > {cost_live:.4f} ATR at the live 260-point "
          f"spread, {cost_hist:.4f} at the 377-point historical median")
    print(f"  (the cost bar is RECOMPUTED per timeframe - a fixed 260-point "
          f"spread is a bigger\n   fraction of a smaller bar's ATR, which is "
          f"why sub-hourly is harder, not easier)\n")

    rows = []
    print(f"  {'condition':<24}{'h':>3}{'n':>8}{'mean(ATR)':>12}{'t':>8}"
          f"{'CI low':>10}{'CI high':>10}  verdict")
    for name, mask in C.items():
        for h in horizons:
            fwd = forward_returns(P, h)[:n_disc]
            sel = mask & np.isfinite(fwd)
            x = fwd[sel]
            if len(x) < 200:
                continue
            where = np.where(sel)[0].astype(float)
            held = np.full(len(x), float(h))
            t = M.block_bootstrap_t(x, where, held, 1)
            ci = M.block_bootstrap_ci(x, where, held)
            lo, hi = (ci if ci is not None else (float("nan"), float("nan")))
            detected = (ci is not None and (lo > 0 or hi < 0)
                        and np.isfinite(t) and abs(t) > bar)
            tradeable = detected and abs(x.mean()) > cost_live
            verdict = ("TRADEABLE" if tradeable else
                       "detected, too small to trade" if detected else "-")
            rows.append(dict(condition=name, h=h, n=len(x), mean=float(x.mean()),
                             t=float(t), ci_lo=float(lo), ci_hi=float(hi),
                             detected=bool(detected), tradeable=bool(tradeable)))
            print(f"  {name:<24}{h:>3}{len(x):>8,}{x.mean():>+12.4f}{t:>+8.2f}"
                  f"{lo:>+10.4f}{hi:>+10.4f}  {verdict}")

    df = pd.DataFrame(rows)
    det = df[df.detected]
    tra = df[df.tradeable]
    print("\n" + "=" * 86)
    print(f"detected (clears the statistical bar):     {len(det)} of {len(df)}")
    print(f"tradeable (also clears the cost bar):      {len(tra)} of {len(df)}")
    if len(det):
        print("\n  detected effects:")
        for _, r in det.iterrows():
            mult = abs(r["mean"]) / cost_live
            print(f"    {r['condition']:<24} h={r['h']}  {r['mean']:+.4f} ATR "
                  f"= {mult:.2f}x the round-trip cost  (t={r['t']:+.2f})")
    if not len(tra):
        print("\n  NOTHING IS TRADEABLE. Either no structural effect is present,")
        print("  or the ones that are present are smaller than what it costs to")
        print("  act on them. Both answers close the same door, and neither is")
        print("  improved by adding a stop, a target or a filter on top - those")
        print("  only add parameters to something with nothing underneath.")
    if a.out:
        pathlib.Path(a.out).write_text(df.to_json(orient="records", indent=1))
    print(f"\n  elapsed {time.time()-t0:.0f}s")
    return df

if __name__ == "__main__":
    main()
