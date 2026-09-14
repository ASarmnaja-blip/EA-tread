#!/usr/bin/env python3
"""Is the skill directional, or just a preference for busy bars?

THE PROBLEM WITH EVERY CONTROL USED IN THIS SESSION

  All of them randomise TIMING only: same number of trades, same direction
  mix, placed at bars drawn uniformly from the whole sample. A rule that
  fires only when something is happening will beat that control even if it
  has no idea which way the something goes, because the control spends part
  of its time in dead bars and the rule never does.

  Two results point at exactly that. The ordinary momentum and reversion
  entries both beat the timing control. More tellingly, value-area rotation
  and value-area breakout are near-opposite readings of one structure - one
  fades re-entry toward the point of control, the other follows the break
  away - and BOTH beat it, on 7 of 9 and 8 of 9 markets. If the zone carried
  directional information, one should win and the other should lose by a
  similar amount.

THE STRONGER CONTROL

  Match on movement. Record each real signal's own bar true range over ATR,
  bin those into deciles, and draw the control's entries from the same
  deciles in the same proportions. The control then sits in equally active
  conditions and differs from the real rule only in WHERE it enters and which
  way it faces.

  Skill measured against this is directional skill. Skill that exists against
  the timing control and vanishes against this one was never direction.

WHAT EACH OUTCOME RETRACTS

  Survives across families - the skill figures in this session stand and the
  weaker control was merely conservative.

  Collapses across families - then the +0.02 to +0.05 readings in the
  regime-matched entries, the wider-stop comparison and the value-area setups
  were all measuring activity selection, and all of them need restating. That
  includes numbers I reported as encouraging.

  Mixed - the families where it survives are the ones worth keeping.
"""
import argparse
import math
import pathlib
import sys
import time

import numpy as np
import pandas as pd

HERE = pathlib.Path(__file__).parent
sys.path.insert(0, str(HERE))
import market_profile as MP
import xauusd_1000_setups as X
from bracket_bias import engine, random_like
from p01_cross_market import MARKETS, TICKS, load_bidask_h1
from profile_setups import momentum_signal, reversion_signal
from value_area_setups import (STOP_MULT, breakout_signal, prior_value_areas,
                               rotation_signal)

SEED = 17
NBIN = 10


def vol_matched(P, dvec, rng, lo=300):
    """Random entries drawn from the same movement deciles as the real ones.

    The real rule's own bars define the deciles; the control then samples
    other bars from the same deciles in the same proportions, so it is as
    busy as the rule is and differs only in where it enters."""
    tr = P["h"] - P["l"]
    with np.errstate(invalid="ignore", divide="ignore"):
        m = tr / P["A"]
    m = np.where(np.isfinite(m), m, np.nan)
    live = np.where(dvec != 0)[0]
    live = live[live >= lo]
    if len(live) == 0:
        return np.zeros_like(dvec), np.full(len(dvec), np.nan)
    ok = np.isfinite(m)
    ok[:lo] = False
    ok[len(dvec) - X.HOLD_BARS - 2:] = False
    edges = np.nanquantile(m[live], np.linspace(0, 1, NBIN + 1))
    edges[0], edges[-1] = -np.inf, np.inf
    real_bin = np.digitize(m[live], edges[1:-1])
    pool_bin = np.digitize(m, edges[1:-1])
    out = np.zeros_like(dvec)
    Iout = np.full(len(dvec), np.nan)
    dirs = dvec[live]
    for b in range(NBIN):
        want = np.where(real_bin == b)[0]
        if len(want) == 0:
            continue
        cand = np.where(ok & (pool_bin == b))[0]
        cand = np.setdiff1d(cand, live, assume_unique=False)
        if len(cand) == 0:
            continue
        take = rng.choice(cand, size=min(len(want), len(cand)), replace=False)
        out[take] = dirs[want[:len(take)]]
        Iout[take] = np.where(dirs[want[:len(take)]] > 0,
                              P["l"][take], P["h"][take])
    return out, Iout


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols", default=",".join(MARKETS))
    a = ap.parse_args()
    t0 = time.time()
    syms = [s.strip() for s in a.symbols.split(",") if s.strip()]

    print("VOLATILITY-MATCHED CONTROL - is the skill direction or activity?")
    print("=" * 104)
    print(__doc__.split("THE STRONGER CONTROL")[1].split("WHAT EACH OUTCOME")[0])
    print(f"  {'market':<9}{'setup':<10}{'n':>7}{'real E':>10}"
          f"{'ctrl:time':>11}{'ctrl:vol':>10}{'skill vs time':>14}"
          f"{'skill vs vol':>13}")

    rows = []
    for sym in syms:
        df = load_bidask_h1(sym)
        if df is None or len(df) < 20000:
            continue
        P = X.prep(df, 60)
        tick = TICKS.get(sym, 0.00001)
        lo, hi, poc, _ = prior_value_areas(P)
        fams = [
            ("momentum", lambda: momentum_signal(P)),
            ("reversion", lambda: reversion_signal(P)),
            ("va-rotate", lambda: rotation_signal(P, lo, hi, poc)),
            ("va-break", lambda: breakout_signal(P, lo, hi, poc)),
        ]
        for lab, fn in fams:
            d, I = fn()
            if int((d != 0).sum()) < 300:
                continue
            real = engine(P, d, I, tick, stop_mult=STOP_MULT)
            rt, rtI = random_like(P, d, np.random.default_rng(SEED))
            ct = engine(P, rt, rtI, tick, stop_mult=STOP_MULT)
            rv, rvI = vol_matched(P, d, np.random.default_rng(SEED))
            cv = engine(P, rv, rvI, tick, stop_mult=STOP_MULT)
            if real is None or ct is None or cv is None:
                continue
            e = float(real[0].mean())
            t_e, v_e = float(ct[0].mean()), float(cv[0].mean())
            rows.append(dict(symbol=sym, setup=lab, n=len(real[0]), E=e,
                             ctrl_time=t_e, ctrl_vol=v_e,
                             skill_time=e - t_e, skill_vol=e - v_e))
            print(f"  {sym:<9}{lab:<10}{len(real[0]):>7,}{e:>+10.4f}"
                  f"{t_e:>+11.4f}{v_e:>+10.4f}{e-t_e:>+14.4f}"
                  f"{e-v_e:>+13.4f}", flush=True)

    if not rows:
        print("\n  nothing produced a book")
        return
    D = pd.DataFrame(rows)
    print("\n" + "=" * 104)
    print("BY FAMILY - the two controls side by side")
    print("=" * 104)
    print(f"  {'family':<12}{'markets':>8}{'skill vs time':>15}"
          f"{'skill vs vol':>14}{'retained':>11}{'t (vol)':>10}"
          f"{'vol>0 on':>10}")
    for lab in D.setup.unique():
        g = D[D.setup == lab]
        st, sv = float(g.skill_time.mean()), float(g.skill_vol.mean())
        se = float(g.skill_vol.std(ddof=1) / math.sqrt(len(g)))
        t = sv / se if se > 0 else np.nan
        keep = (sv / st * 100) if abs(st) > 1e-9 else np.nan
        print(f"  {lab:<12}{len(g):>8}{st:>+15.4f}{sv:>+14.4f}"
              f"{keep:>10.0f}%{t:>+10.2f}"
              f"{int((g.skill_vol > 0).sum()):>7}/{len(g)}")

    st_all = float(D.skill_time.mean())
    sv_all = float(D.skill_vol.mean())
    print(f"\n  all families   skill vs timing control {st_all:+.4f}   "
          f"vs volatility-matched {sv_all:+.4f}   "
          f"retained {sv_all/st_all*100 if abs(st_all)>1e-9 else float('nan'):.0f}%")
    print(f"\n  A large drop across every family means the controls used")
    print(f"  throughout this session were too weak, and the skill figures")
    print(f"  they produced measured activity selection rather than")
    print(f"  direction. That would retract readings I reported as")
    print(f"  encouraging, not just ones I reported as null.")
    D.to_csv(HERE / "vol_matched_control.csv", index=False)
    print(f"\n  elapsed {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
