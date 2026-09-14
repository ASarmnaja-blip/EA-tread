#!/usr/bin/env python3
"""The one measurement from the instrument that was never turned into a test.

WHAT WAS MEASURED AND THEN LEFT ALONE

  market_profile.py builds a volume-at-price profile per session and reports:
  the value area holds about 60% of the daily range, the next session touches
  the prior session's value area 93.8% of the time, and price closes inside
  its own value area 66.2% of the time.

  I reported the 93.8% as a near-tautology - two overlapping daily ranges
  touch almost by construction - and then tested nothing against it. That is
  the part of "read where volume sits and what each zone does" which produced
  a measurement and no test.

THE TWO READINGS, BOTH OF WHICH ARE CONVENTIONAL

  ROTATION says the value area is where price belongs, so leaving it and
  coming back is a return to fair value and should continue toward the point
  of control.

  BREAKOUT says the value area is where price was, so leaving it is
  information and should continue away.

  They are opposite and both are widely believed. Testing them against each
  other and against random timing is the point; neither is being advocated.

WHY NOW RATHER THAN EARLIER

  At the engine's 1x stop the exit's own penalty was about 0.048R per trade
  after correcting for the measured 73.3% stop-first rate - the same size as
  the largest edge this project has ever found, so a test there could not
  separate a real difference from the bracket. At 2x it falls to about
  0.005R. The measurement only became worth making once the instrument
  stopped dominating it.

WHAT A DOUBLE FAILURE WOULD MEAN

  If neither reading carries skill, the value-area structure is real as a
  description of where price spends its time and carries no directional
  information at this horizon. That is the same answer the variance ratio
  gave, and two independent outputs of the instrument landing there would say
  something specific about the instrument: that it describes the market
  accurately and does not predict it.
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

SEED = 17
STOP_MULT = 2.0
VA_FRAC = 0.70


def prior_value_areas(P, bins=40):
    """Per-session value area and point of control, from CLOSED sessions only.

    Session t's zone is built from session t-1's bars, so nothing a signal
    sees on day t includes day t's own volume."""
    idx = P["idx"]
    day = pd.DatetimeIndex(idx).normalize()
    vol = P.get("vol")
    use_vol = vol is not None and float(np.nanmedian(vol)) > 0 and \
        float(np.mean(np.asarray(vol) == 0)) < 0.5
    h, l = P["h"], P["l"]
    w_all = np.asarray(vol, float) if use_vol else np.ones(len(h))
    out_lo = np.full(P["N"], np.nan)
    out_hi = np.full(P["N"], np.nan)
    out_poc = np.full(P["N"], np.nan)
    days = pd.unique(day)
    prev = None
    starts = {d: np.where(day == d)[0] for d in days}
    for i, d in enumerate(days):
        cur = starts[d]
        if prev is not None and len(prev) >= 4:
            lo, hi = float(l[prev].min()), float(h[prev].max())
            if np.isfinite([lo, hi]).all() and hi > lo:
                edges = np.linspace(lo, hi, bins + 1)
                mid = (h[prev] + l[prev]) / 2
                hist, _ = np.histogram(mid, bins=edges, weights=w_all[prev])
                if hist.sum() > 0:
                    centers = (edges[:-1] + edges[1:]) / 2
                    order = np.argsort(-hist)
                    cum = np.cumsum(hist[order]) / hist.sum()
                    keep = centers[order[:int(np.searchsorted(cum, VA_FRAC)) + 1]]
                    out_lo[cur] = keep.min()
                    out_hi[cur] = keep.max()
                    out_poc[cur] = centers[int(np.argmax(hist))]
        prev = cur
    return out_lo, out_hi, out_poc, use_vol


def rotation_signal(P, va_lo, va_hi, poc):
    """Outside the prior value area on the previous bar, back inside now,
    faded toward the point of control."""
    c, N = P["c"], P["N"]
    cp = np.concatenate([[np.nan], c[:-1]])
    inside = (c >= va_lo) & (c <= va_hi)
    was_out = (cp < va_lo) | (cp > va_hi)
    fire = np.nan_to_num(inside & was_out, nan=False)
    d = np.zeros(N, np.int8)
    I = np.full(N, np.nan)
    up = fire & (c < poc)          # below value: fade upward toward POC
    dn = fire & (c > poc)
    d[up] = 1
    I[up] = P["l"][up]
    d[dn] = -1
    I[dn] = P["h"][dn]
    return d, I


def breakout_signal(P, va_lo, va_hi, poc):
    """Inside the prior value area on the previous bar, closed outside now,
    taken in the direction of the break."""
    c, N = P["c"], P["N"]
    cp = np.concatenate([[np.nan], c[:-1]])
    was_in = (cp >= va_lo) & (cp <= va_hi)
    d = np.zeros(N, np.int8)
    I = np.full(N, np.nan)
    up = np.nan_to_num(was_in & (c > va_hi), nan=False)
    dn = np.nan_to_num(was_in & (c < va_lo), nan=False)
    d[up] = 1
    I[up] = P["l"][up]
    d[dn] = -1
    I[dn] = P["h"][dn]
    return d, I


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols", default=",".join(MARKETS))
    a = ap.parse_args()
    t0 = time.time()
    syms = [s.strip() for s in a.symbols.split(",") if s.strip()]

    print("VALUE AREA - rotation against breakout, on the corrected bracket")
    print("=" * 100)
    print(__doc__.split("THE TWO READINGS")[1].split("WHY NOW RATHER")[0])
    print(f"  stop {STOP_MULT}x, value area {VA_FRAC:.0%}, zones from CLOSED "
          f"sessions only\n")
    print(f"  {'market':<9}{'setup':<10}{'n':>8}{'net E':>10}{'bracket':>10}"
          f"{'skill':>10}")

    rows = []
    for sym in syms:
        df = load_bidask_h1(sym)
        if df is None or len(df) < 20000:
            continue
        P = X.prep(df, 60)
        tick = TICKS.get(sym, 0.00001)
        lo, hi, poc, used_vol = prior_value_areas(P)
        for lab, fn in (("rotation", rotation_signal),
                        ("breakout", breakout_signal)):
            d, I = fn(P, lo, hi, poc)
            if int((d != 0).sum()) < 300:
                continue
            real = engine(P, d, I, tick, stop_mult=STOP_MULT)
            rd, rI = random_like(P, d, np.random.default_rng(SEED))
            ctrl = engine(P, rd, rI, tick, stop_mult=STOP_MULT)
            if real is None or ctrl is None:
                continue
            e, cE = float(real[0].mean()), float(ctrl[0].mean())
            rows.append(dict(symbol=sym, setup=lab, n=len(real[0]),
                             E=e, bracket=cE, skill=e - cE,
                             vol_weighted=used_vol))
            print(f"  {sym:<9}{lab:<10}{len(real[0]):>8,}{e:>+10.4f}"
                  f"{cE:>+10.4f}{e-cE:>+10.4f}", flush=True)

    if not rows:
        print("\n  nothing produced a book")
        return
    D = pd.DataFrame(rows)
    print("\n" + "=" * 100)
    print("THE TWO READINGS, POOLED")
    print("=" * 100)
    for lab in ("rotation", "breakout"):
        g = D[D.setup == lab]
        if len(g) < 3:
            continue
        se = float(g.skill.std(ddof=1) / math.sqrt(len(g)))
        t = float(g.skill.mean() / se) if se > 0 else np.nan
        print(f"  {lab:<10} markets {len(g)}   net E {g.E.mean():+.4f}   "
              f"bracket {g.bracket.mean():+.4f}   skill {g.skill.mean():+.4f}"
              f"   t {t:+.2f}   skill>0 on {int((g.skill > 0).sum())}/{len(g)}"
              f"   E>0 on {int((g.E > 0).sum())}/{len(g)}")
        print(f"  {'':<10} signals/year {g.n.sum()/(len(g)*22):.0f} per market")
    print(f"\n  If both readings come back with skill near zero, the value area")
    print(f"  is real as a description of where price spends its time and")
    print(f"  carries no directional information at this horizon - the same")
    print(f"  answer the variance ratio gave. Two independent outputs of the")
    print(f"  instrument landing there would say it describes the market")
    print(f"  accurately and does not predict it.")
    D.to_csv(HERE / "value_area_setups.csv", index=False)
    print(f"\n  elapsed {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
