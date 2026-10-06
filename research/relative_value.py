#!/usr/bin/env python3
"""The last untested strategy class: trade the difference, not the direction.

WHAT EVERY HYPOTHESIS HERE HAS HAD IN COMMON

  All 1,677 of them are single-instrument and directional. They predict where
  one price goes. That is one strategy class, and this project has now
  established that it cannot pay its costs at retail spreads by five
  independent routes.

  Relative value is a different class with different arithmetic. Take two
  correlated instruments, remove the shared driver, and what is left has an
  equilibrium to return to - a property no outright price has.

THE ARITHMETIC THAT SAYS IT SHOULD FAIL

  Two legs means two round trips. If the pairs are 90% correlated the
  residual's volatility is about sqrt(2*(1-0.9)) = 44% of a single leg's, so
  the cost ratio is

      2 * spread / (0.44 * ATR)  =  4.5 * (spread / ATR)

  which on this panel is 0.61 against the 0.135 an outright trade faces. On
  that calculation relative value is four and a half times WORSE.

THE ASSUMPTION INSIDE THAT ARITHMETIC, WHICH IS THE WHOLE QUESTION

  It assumes the residual's predictable fraction is the same 0.0152 ATR
  measured on outright direction. The entire reason relative value exists as a
  discipline is that it is not: the residual has a mechanism the outright
  price does not.

  So the question is a race. The cost goes up 4.5 times by construction. Does
  the amplitude go up by more? That is a measurement and it has never been
  made here.

HOW THE HEDGE RATIO AVOIDS LOOKING FORWARD

  Rolling ordinary least squares on bars strictly before t, refitted as the
  window moves. A ratio fitted on the whole sample would know the future
  relationship and would make any residual revert by construction - which is
  the standard way this class of test fools itself.

  Log prices throughout, so both legs are unit-free and the spread enters as a
  relative cost rather than in points that cannot be added across
  instruments - the unit error this run has already made twice.
"""
import argparse
import itertools
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
from p01_cross_market import MARKETS, load_bidask_h1

SEED = 17
PANEL = list(MARKETS) + ["USDSEK"]
WINDOWS = (250, 1000)
ZS = (1.5, 2.0, 2.5)
HOLDS = (1, 3, 12)
SPLIT = pd.Timestamp("2017-01-01", tz="UTC")
YEARS = 22.0


def load_logs():
    """log mid open/close and the relative spread, per market, on one index."""
    out = {}
    for s in PANEL:
        df = load_bidask_h1(s)
        if df is None or len(df) < 20000:
            continue
        mid_o = (df["bid_open"] + df["ask_open"]) / 2
        mid_c = (df["bid_close"] + df["ask_close"]) / 2
        rel_sp = (df["ask_open"] - df["bid_open"]) / mid_o
        out[s] = pd.DataFrame(dict(lo=np.log(mid_o), lc=np.log(mid_c),
                                   rs=rel_sp), index=df.index)
    return out


def rolling_beta(y, x, w):
    """OLS slope and intercept of y on x over a trailing window of w bars.

    Computed from rolling moments rather than by refitting, which is the same
    estimator and runs in one pass. Everything is shifted by one bar so the
    value at t uses bars t-w .. t-1 and never t itself."""
    sy = pd.Series(y)
    sx = pd.Series(x)
    mx = sx.rolling(w).mean()
    my = sy.rolling(w).mean()
    cxy = (sx * sy).rolling(w).mean() - mx * my
    vx = (sx * sx).rolling(w).mean() - mx * mx
    beta = (cxy / vx.replace(0, np.nan))
    alpha = my - beta * mx
    return beta.shift(1).to_numpy(), alpha.shift(1).to_numpy()


def pair_run(A, B, w, z0, hold):
    """Fade the residual. Returns per-trade arrays and the cost."""
    j = A.index.intersection(B.index)
    if len(j) < 20000:
        return None
    a, b = A.loc[j], B.loc[j]
    beta, alpha = rolling_beta(a.lc.to_numpy(), b.lc.to_numpy(), w)
    resid = a.lc.to_numpy() - (alpha + beta * b.lc.to_numpy())
    rs_ = pd.Series(resid)
    mu = rs_.rolling(w).mean().shift(1).to_numpy()
    sd = rs_.rolling(w).std().shift(1).to_numpy()
    with np.errstate(invalid="ignore", divide="ignore"):
        z = (resid - mu) / sd
    n = len(j)
    t = np.arange(w + 2, n - hold - 2)
    zt = z[t]
    d = np.where(zt > z0, -1.0, np.where(zt < -z0, 1.0, 0.0))
    keep = d != 0
    t, d = t[keep], d[keep]
    if len(t) < 200:
        return None
    e, x = t + 1, t + hold
    bt = beta[t]
    # the residual's move, entering at the open and exiting at the close
    move = d * ((a.lc.to_numpy()[x] - a.lo.to_numpy()[e])
                - bt * (b.lc.to_numpy()[x] - b.lo.to_numpy()[e]))
    # one round trip on each leg, the second scaled by the hedge ratio
    cost = a.rs.to_numpy()[e] + np.abs(bt) * b.rs.to_numpy()[e]
    ok = (np.isfinite(move) & np.isfinite(cost) & (cost > 0)
          & np.isfinite(bt) & (np.abs(bt) < 10))
    if ok.sum() < 200:
        return None
    return dict(n=int(ok.sum()), move=move[ok], cost=cost[ok],
                stamp=j[t[ok]], beta_med=float(np.nanmedian(np.abs(bt[ok]))))


def summarise(r, split=SPLIT):
    edge = float(r["move"].sum() / r["cost"].sum())
    early = r["stamp"] < split
    out = dict(n=r["n"], edge=edge, per_year=r["n"] / YEARS,
               beta=r["beta_med"])
    for lab, m in (("early", early), ("late", ~early)):
        if m.sum() > 100 and r["cost"][m].sum() > 0:
            out[lab] = float(r["move"][m].sum() / r["cost"][m].sum())
        else:
            out[lab] = np.nan
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true",
                    help="one window and hold, for a first look")
    a = ap.parse_args()
    t0 = time.time()

    print("RELATIVE VALUE - trade the difference, not the direction")
    print("=" * 104)
    print(__doc__.split("THE ARITHMETIC THAT SAYS IT SHOULD FAIL")[1]
          .split("HOW THE HEDGE RATIO")[0])

    L = load_logs()
    pairs = list(itertools.combinations(sorted(L), 2))
    print(f"  {len(L)} markets, {len(pairs)} pairs\n")

    windows = (1000,) if a.quick else WINDOWS
    holds = (3,) if a.quick else HOLDS

    print("=" * 104)
    print("THE CONFIGURATION GRID - pooled across all pairs")
    print("=" * 104)
    print(f"  {'window':<8}{'z':<6}{'hold':<6}{'pairs':>7}{'sig/yr':>9}"
          f"{'edge':>10}{'pairs +':>10}{'early':>9}{'late':>9}"
          f"{'both +':>9}")
    grid = []
    detail = {}
    for w in windows:
        for z0 in ZS:
            for hold in holds:
                per = []
                for pa, pb in pairs:
                    r = pair_run(L[pa], L[pb], w, z0, hold)
                    if r:
                        s = summarise(r)
                        s["pair"] = f"{pa}/{pb}"
                        per.append(s)
                if len(per) < 10:
                    continue
                e = np.array([p["edge"] for p in per], float)
                early = np.array([p["early"] for p in per], float)
                late = np.array([p["late"] for p in per], float)
                both = int(np.sum((early > 0) & (late > 0)))
                rec = dict(window=w, z=z0, hold=hold, pairs=len(per),
                           per_year=float(np.mean([p["per_year"] for p in per])),
                           edge=float(np.mean(e)),
                           pairs_positive=int((e > 0).sum()),
                           early=float(np.nanmean(early)),
                           late=float(np.nanmean(late)),
                           both_positive=both)
                grid.append(rec)
                detail[(w, z0, hold)] = per
                print(f"  {w:<8}{z0:<6.1f}{hold:<6}{len(per):>7}"
                      f"{rec['per_year']:>9,.0f}{rec['edge']:>+10.4f}"
                      f"{rec['pairs_positive']:>7}/{len(per)}"
                      f"{rec['early']:>+9.4f}{rec['late']:>+9.4f}"
                      f"{both:>7}/{len(per)}", flush=True)

    if not grid:
        print("  nothing measured")
        return
    best = max(grid, key=lambda r: r["edge"])
    print("\n" + "=" * 104)
    print("THE BEST CONFIGURATION, PAIR BY PAIR")
    print("=" * 104)
    per = detail[(best["window"], best["z"], best["hold"])]
    per = sorted(per, key=lambda p: -p["edge"])
    print(f"  window {best['window']}, z {best['z']}, hold {best['hold']}h  "
          f"-  pooled {best['edge']:+.4f} of a two-leg round trip")
    print(f"  {'pair':<20}{'n':>8}{'edge':>10}{'early':>9}{'late':>9}"
          f"{'|beta|':>9}")
    for p in per[:8]:
        print(f"  {p['pair']:<20}{p['n']:>8,}{p['edge']:>+10.4f}"
              f"{p['early']:>+9.4f}{p['late']:>+9.4f}{p['beta']:>9.3f}")
    print(f"  ...")
    for p in per[-3:]:
        print(f"  {p['pair']:<20}{p['n']:>8,}{p['edge']:>+10.4f}"
              f"{p['early']:>+9.4f}{p['late']:>+9.4f}{p['beta']:>9.3f}")

    viable = [r for r in grid if r["edge"] > 1.0
              and r["pairs_positive"] > r["pairs"] / 2
              and r["both_positive"] > r["pairs"] / 2
              and r["per_year"] >= 200]
    print("\n" + "=" * 104)
    print("VERDICT")
    print("=" * 104)
    print(f"  best pooled edge {best['edge']:+.4f} of a two-leg round trip "
          f"at window {best['window']}, z {best['z']}, hold {best['hold']}h")
    print(f"  positive on {best['pairs_positive']}/{best['pairs']} pairs, "
          f"positive in BOTH halves on {best['both_positive']}/{best['pairs']}")
    print(f"  it would need to be {1.0/best['edge']:.1f}x larger to pay"
          if best["edge"] > 0 else "  it is negative")
    print(f"\n  {len(viable)} configuration(s) clear the registered bar")
    if not viable:
        print(f"\n  Doubling the cost to halve the volatility is a losing "
              f"trade at these spreads")
        print(f"  however much stronger residual reversion is. That closes "
              f"the last untested")
        print(f"  strategy class in this repository.")

    out = HERE / "relative_value.json"
    out.write_text(json.dumps(dict(
        created=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        windows=list(windows), zs=list(ZS), holds=list(holds),
        pairs=len(pairs), grid=grid, best=best,
        best_detail=[{k: v for k, v in p.items()} for p in per],
        viable=len(viable),
        manifest=PR.manifest(dict(seed=SEED),
                             [HERE / ".cache_duka" /
                              f"{s}_H1_2003_2026.parquet" for s in PANEL])),
        indent=1, default=str))
    PR.log("phase7-relative-value",
           "Does residual reversion rise by more than the doubled cost of a "
           "second leg?",
           hypothesis="relative_value_pairs",
           tools=["relative_value"],
           result=dict(grid=grid, best=best, viable=len(viable)),
           status="MEASURED",
           finding=f"best pooled {best['edge']:+.4f} of a two-leg round trip",
           next_action="record against the registered criterion",
           started=t0)
    print(f"\n  saved -> {out.name}   elapsed {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
