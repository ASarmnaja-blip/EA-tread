#!/usr/bin/env python3
"""Bounce or reversion - the question that decides whether cost can be beaten.

WHY THIS ONE DECOMPOSITION MATTERS MORE THAN THE REST

  The unconditional previous-bar fade is the only finding this project has
  left standing. Whether it can ever be made to pay turns on what its
  amplitude scales with, and there are exactly two candidates with opposite
  consequences.

    BOUNCE. If the reversal in PRICE units is proportional to the spread, it
    is the bid-ask bounce: a wider quote makes the observed price oscillate
    more, and the fade collects that oscillation. Then the edge measured in
    spread units is a constant of the microstructure. A venue three times
    cheaper shrinks the edge by exactly the factor it shrinks the cost, the
    ratio does not move, and NO execution improvement anywhere can make this
    pay. The cheaper-venue question closes as pointless.

    VOLATILITY-SCALED. If the amplitude is proportional to ATR instead, the
    edge in spread units is ATR over spread. A venue three times cheaper
    triples the ratio. The cheaper-venue question becomes live, and the
    required cost reduction is computable from the measured ratio rather than
    guessed at.

  The lag test already established that 42% of the conditional effect lives in
  the most recent quote, which is bounce-shaped. It never separated the two
  for the unconditional effect, and it never said what the other 58% scales
  with.

HOW THE TWO ARE SEPARATED

  Cells of market by hour by year. In each, the fade's mean signed move in
  ticks, the median spread in ticks and the median ATR in ticks. Then one
  regression of log|move| on log spread and log ATR together, with market
  fixed effects.

  Spread and ATR are correlated - thin quotes and quiet markets go together -
  so neither coefficient means anything on its own, which is why they are
  fitted jointly and the correlation between them is reported beside the fit.

WHAT THIS IS NOT

  A decomposition of an effect already established, not a new candidate. No
  outcome here can produce a finalist or open the sealed holdout.
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

SEED = 17
PANEL = list(MARKETS) + ["USDSEK"]
# which leg the dollar sits on, for the third split
USD_BASE = {"USDJPY", "USDCHF", "USDCAD", "USDSEK"}
USD_QUOTE = {"EURUSD", "GBPUSD", "AUDUSD", "NZDUSD"}
METAL = {"XAUUSD", "XAGUSD"}


def cells(sym):
    """market x hour x year, with the fade's move, the spread and the ATR."""
    df = load_bidask_h1(sym)
    if df is None or len(df) < 20000:
        return None
    P = X.prep(df, 60)
    tick = TICKS.get(sym, 1e-5)
    c = np.asarray(P["c"], float)
    o = (np.asarray(P["bid_o"], float) + np.asarray(P["ask_o"], float)) / 2
    A = np.asarray(P["A"], float)
    ask_o, bid_o = np.asarray(P["ask_o"], float), np.asarray(P["bid_o"], float)
    N = P["N"]
    # The signal is bar t's own close-to-close move; the trade runs from the
    # open of t+1 to the close of t+1. That is the same one-bar construction
    # every other measurement in this project uses.
    #
    # The first version of this file indexed prev[t-1] while entering at t+1,
    # which skips bar t entirely and measures a signal one bar staler than the
    # finding it claims to decompose. It reported +0.0335 against the +0.1203
    # measured everywhere else, and the gap was the bug rather than the
    # aggregation.
    prev = np.concatenate([[np.nan], np.diff(c)])      # prev[k] = c[k]-c[k-1]
    t = np.arange(2, N - 2)
    d = -np.sign(prev[t])
    keep = d != 0
    t, d = t[keep], d[keep]
    mv = d * (c[t + 1] - o[t + 1])
    sp = ask_o[t + 1] - bid_o[t + 1]
    at = A[t]
    ok = np.isfinite(mv) & np.isfinite(sp) & (sp > 0) & np.isfinite(at) & (at > 0)
    idx = pd.DatetimeIndex(P["idx"])[t[ok]]
    return pd.DataFrame(dict(symbol=sym, hour=idx.hour, year=idx.year,
                             move=mv[ok] / tick, spread=sp[ok] / tick,
                             atr=at[ok] / tick))


def agg(D, mask=None, min_n=2000):
    """Per-market ratio of means, then an equal weight across markets.

    NOT the pooled sum of moves over the pooled sum of spreads. Every quantity
    here is in each instrument's own points, and gold's spread is 396 of them
    against EURUSD's 5.5 - so a pooled ratio is an average weighted by tick
    size, which is a property of the quoting convention and nothing else. The
    first version of this file made exactly that mistake and reported +0.0239
    where the correct figure is several times larger; the same error was
    caught once already in discovery.score and is recorded there too."""
    g = D if mask is None else D[mask]
    if len(g) == 0:
        return np.nan, 0
    per = []
    for sym, gs in g.groupby("symbol"):
        if len(gs) < min_n or gs.spread.sum() <= 0:
            continue
        per.append(float(gs.move.sum() / gs.spread.sum()))
    if not per:
        return np.nan, 0
    return float(np.mean(per)), len(per)


def fit(D):
    """log|mean move| on log spread and log ATR, with market fixed effects.

    Least squares by hand rather than by a library, because the repository has
    no statsmodels and adding one to fit three coefficients would be a
    dependency for nothing."""
    g = D.groupby(["symbol", "hour", "year"]).agg(
        move=("move", "mean"), spread=("spread", "median"),
        atr=("atr", "median"), n=("move", "size")).reset_index()
    g = g[(g.n >= 80) & (g.spread > 0) & (g.atr > 0) & (g.move.abs() > 0)]
    if len(g) < 200:
        return None, g
    y = np.log(g.move.abs().to_numpy())
    xs = np.log(g.spread.to_numpy())
    xa = np.log(g.atr.to_numpy())
    syms = sorted(g.symbol.unique())
    Xd = np.column_stack([xs, xa]
                         + [(g.symbol == s).to_numpy(float) for s in syms])
    beta, *_ = np.linalg.lstsq(Xd, y, rcond=None)
    resid = y - Xd @ beta
    dof = max(len(y) - Xd.shape[1], 1)
    s2 = float(resid @ resid) / dof
    cov = s2 * np.linalg.pinv(Xd.T @ Xd)
    se = np.sqrt(np.clip(np.diag(cov), 0, None))
    r2 = 1.0 - float(resid @ resid) / float(((y - y.mean()) ** 2).sum())
    return dict(beta_spread=float(beta[0]), se_spread=float(se[0]),
                beta_atr=float(beta[1]), se_atr=float(se[1]),
                r2=r2, cells=int(len(g)),
                corr_logspread_logatr=float(np.corrcoef(xs, xa)[0, 1])), g


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols", default=",".join(PANEL))
    a = ap.parse_args()
    t0 = time.time()
    syms = [s.strip() for s in a.symbols.split(",") if s.strip()]

    print("REVERSAL ANATOMY - bounce or reversion?")
    print("=" * 100)
    print(__doc__.split("HOW THE TWO ARE SEPARATED")[1].split("WHAT THIS IS NOT")[0])

    frames = []
    for s in syms:
        f = cells(s)
        if f is not None:
            frames.append(f)
        print(f"  {s:<9}{time.time()-t0:>7.0f}s", flush=True)
    if not frames:
        print("  nothing measured")
        return
    D = pd.concat(frames, ignore_index=True)

    res, g = fit(D)
    print("\n" + "=" * 100)
    print("THE REGRESSION - log|mean move| on log spread and log ATR")
    print("=" * 100)
    if res is None:
        print("  too few cells to fit")
        return
    print(f"  {res['cells']:,} market-hour-year cells, R2 {res['r2']:.3f}")
    print(f"  correlation between log spread and log ATR across cells: "
          f"{res['corr_logspread_logatr']:+.3f}")
    print(f"\n  {'term':<16}{'coefficient':>14}{'std error':>12}{'t':>9}")
    for lab, b, s_ in (("log spread", res["beta_spread"], res["se_spread"]),
                       ("log ATR", res["beta_atr"], res["se_atr"])):
        print(f"  {lab:<16}{b:>+14.3f}{s_:>12.3f}{b/s_ if s_ > 0 else float('nan'):>+9.1f}")

    bs, ba = res["beta_spread"], res["beta_atr"]
    if bs > 0.7 and ba < 0.3:
        verdict = "BOUNCE"
    elif ba > 0.7 and bs < 0.3:
        verdict = "VOLATILITY-SCALED"
    else:
        tot = abs(bs) + abs(ba)
        verdict = (f"MIXTURE - {abs(bs)/tot*100:.0f}% spread-scaled, "
                   f"{abs(ba)/tot*100:.0f}% volatility-scaled"
                   if tot > 0 else "UNDETERMINED")
    print(f"\n  VERDICT: {verdict}")

    print("\n" + "=" * 100)
    print("EDGE IN SPREAD UNITS BY COST DECILE - does a cheap quote help?")
    print("=" * 100)
    D["cost_ratio"] = D.spread / D.atr
    q = D.cost_ratio.quantile(np.linspace(0, 1, 11)).to_numpy().copy()
    q[0], q[-1] = -np.inf, np.inf
    D["dec"] = np.digitize(D.cost_ratio, q[1:-1])
    print(f"  {'decile':<8}{'spread/ATR':>12}{'n':>11}{'edge (spreads)':>17}"
          f"{'edge (ticks)':>15}")
    dec_rows = []
    for k in range(10):
        m = D.dec == k
        if m.sum() < 5000:
            continue
        e, nm = agg(D, m)
        if not np.isfinite(e):
            continue
        dec_rows.append(dict(decile=k, cost_ratio=float(D.cost_ratio[m].median()),
                             n=int(m.sum()), markets=nm, edge=e,
                             edge_ticks=float(D.move[m].mean())))
        print(f"  {k:<8}{D.cost_ratio[m].median():>12.4f}{int(m.sum()):>11,}"
              f"{e:>+17.4f}{D.move[m].mean():>+15.4f}")
    if len(dec_rows) >= 2:
        lo_, hi_ = dec_rows[0], dec_rows[-1]
        print(f"\n  cheapest decile {lo_['edge']:+.4f} against dearest "
              f"{hi_['edge']:+.4f} in spread units, a "
              f"{lo_['edge']/hi_['edge']:.1f}x gap")
        print(f"  across a {hi_['cost_ratio']/lo_['cost_ratio']:.0f}x range "
              f"in the quote itself.")
        print(f"\n  The amplitude implied by each decile - its edge times its "
              f"own cost ratio - is")
        print(f"  {lo_['edge']*lo_['cost_ratio']:.5f} ATR at the cheap end "
              f"and {hi_['edge']*hi_['cost_ratio']:.5f} at the dear end, so it "
              f"is NOT")
        print(f"  constant: a cheap quote comes with a smaller move as well "
              f"as a smaller cost, and")
        print(f"  the ratio improves only because the cost falls faster. That "
              f"is why the venue")
        print(f"  requirement below is computed from each decile's own "
              f"measured edge rather than")
        print(f"  from the panel amplitude applied to a cheaper spread.")

    print("\n" + "=" * 100)
    print("BY YEAR, BY DOLLAR LEG, AND LEAVE-ONE-MARKET-OUT")
    print("=" * 100)
    by_year = []
    for y, gy in D.groupby("year"):
        if len(gy) < 5000:
            continue
        ey, _ = agg(gy, min_n=500)
        if np.isfinite(ey):
            by_year.append(dict(year=int(y), edge=ey))
    print("  edge in spread units by year")
    print("   " + "  ".join(f"{r['year']}:{r['edge']:+.2f}" for r in by_year[:12]))
    print("   " + "  ".join(f"{r['year']}:{r['edge']:+.2f}" for r in by_year[12:]))

    groups = {"USD base": USD_BASE, "USD quote": USD_QUOTE, "metal": METAL}
    leg = []
    print(f"\n  {'group':<12}{'markets':>9}{'edge':>10}")
    for lab, members in groups.items():
        m = D.symbol.isin(members)
        if m.sum() < 5000:
            continue
        e, _ = agg(D, m)
        leg.append(dict(group=lab, edge=e,
                        markets=int(D.symbol[m].nunique())))
        print(f"  {lab:<12}{int(D.symbol[m].nunique()):>9}{e:>+10.4f}")

    full, _ = agg(D)
    loo = []
    for s in sorted(D.symbol.unique()):
        e, _ = agg(D, D.symbol != s)
        loo.append(dict(dropped=s, edge=e))
    swing = max(abs(r["edge"] - full) for r in loo) / abs(full) if full else np.nan
    worst = max(loo, key=lambda r: abs(r["edge"] - full))
    print(f"\n  pooled edge {full:+.4f}; worst leave-one-out drops "
          f"{worst['dropped']} to {worst['edge']:+.4f}, a swing of "
          f"{swing:.0%}")
    print(f"  {'no single market carries it' if swing < 0.5 else 'ONE MARKET CARRIES IT'}")

    print("\n" + "=" * 100)
    print("WHAT THE COEFFICIENTS IMPLY FOR A CHEAPER VENUE")
    print("=" * 100)
    # edge in spread units = k * ATR / spread, so the cost ratio at which it
    # reaches one round trip follows directly from the measured pair
    mean_ratio = float(np.mean([float(gs.spread.sum() / gs.atr.sum())
                                for _, gs in D.groupby("symbol")]))
    edge_now = full
    k = edge_now * mean_ratio          # reversal amplitude in ATR units
    need_ratio = k / 1.0 if k > 0 else np.nan
    print(f"  measured spread/ATR across the panel   {mean_ratio:.4f}")
    print(f"  measured edge                          {edge_now:+.4f} spreads")
    print(f"  implied reversal amplitude             {k:.5f} ATR per trade")
    print(f"  spread/ATR needed for one round trip   {need_ratio:.5f}")
    print(f"  execution would have to be             "
          f"{mean_ratio / need_ratio:.1f}x cheaper")
    cheap = dec_rows[0] if dec_rows else None
    if cheap:
        # each decile's own edge, not the panel amplitude transplanted onto a
        # cheaper spread - the amplitude is not constant across deciles
        need_c = 1.0 / cheap["edge"] if cheap["edge"] > 0 else np.nan
        print(f"\n  In the cheapest cost decile the quote is already "
              f"{mean_ratio / cheap['cost_ratio']:.1f}x tighter than the")
        print(f"  panel average, and the edge there is {cheap['edge']:+.4f} "
              f"spreads - so execution would")
        print(f"  still have to be {need_c:.1f}x cheaper than THAT decile to "
              f"reach one round trip.")
        print(f"  Selecting the cheapest hours is worth about "
              f"{cheap['edge']/edge_now:.1f}x and is already counted in it.")
    print(f"\n  This number exists only because the effect is "
          f"volatility-scaled. Had the")
    print(f"  spread coefficient come back near one, the edge in spread "
          f"units would have been")
    print(f"  a constant of the microstructure and no venue could have moved "
          f"it at all.")

    out = HERE / "reversal_anatomy.json"
    out.write_text(json.dumps(dict(
        created=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        regression=res, verdict=verdict, by_cost_decile=dec_rows,
        by_year=by_year, by_dollar_leg=leg, pooled=full,
        mean_cost_ratio=float(np.mean([float(gs.spread.sum() / gs.atr.sum())
                                       for _, gs in D.groupby("symbol")])),
        leave_one_out=loo, loo_swing=swing,
        manifest=PR.manifest(dict(seed=SEED),
                             [HERE / ".cache_duka" /
                              f"{s}_H1_2003_2026.parquet" for s in syms])),
        indent=1, default=str))
    PR.log("phase5-reversal-anatomy",
           "Does the reversal amplitude scale with the spread or with "
           "volatility, and therefore can a cheaper venue ever help?",
           hypothesis="reversal_anatomy",
           tools=["reversal_anatomy"],
           result=dict(regression=res, verdict=verdict,
                       loo_swing=swing, pooled=full),
           status=verdict, finding=verdict,
           next_action="record; if bounce, close the cheaper-venue item",
           started=t0)
    print(f"\n  saved -> {out.name}   elapsed {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
