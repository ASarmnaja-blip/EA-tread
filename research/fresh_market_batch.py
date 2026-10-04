#!/usr/bin/env python3
"""Every survivor at once, on the only market this project has not used.

WHY ALL EIGHT AND NOT THE BEST ONE

  USDSEK is the last unexamined data outside the sealed holdout. Taking
  candidates to it one at a time, stopping when one passes, is a sequential
  search of a single market and would burn it the way the nine-market panel
  has already been burned. Running the whole set in one pass and reporting
  every row makes that impossible.

  The set is also more informative than any member of it. If the panel effect
  is real the eight should tilt positive together. If it is selection they
  should scatter around the unconditional fade, and one of eight landing above
  it is exactly what noise produces.

WHAT IS BEING TESTED

  On the corrected ratio-of-means metric, zero of 127 pilot hypotheses clear
  the 1.105-spread bar with a t above 3 on at least 6 of 9 markets - where
  five appeared to on the inflated mean-of-ratios. Two shapes remain
  interesting and neither clears both conditions:

    expand-quiet-cheap   the cheap-quote filter stacked on the amplitude
                         condition. Largest edges this project has produced,
                         up to +2.631 of a round trip, but only t +1.99 on
                         345 signals a market.

    expand-after-quiet   tightened to 1.2 ATR after a bar under 0.4. t +4.92
                         on 9 of 9, which clears the floor, at an edge of
                         +1.100 against a bar of 1.105 - breakeven to within
                         half a percent.

  As the condition tightens the edge rises and the sample falls. The product
  never clears both, on the panel. Whether either survives a market that had
  no part in producing them is the question.
"""
import json
import math
import pathlib
import sys
import time

import numpy as np
import pandas as pd

HERE = pathlib.Path(__file__).parent
sys.path.insert(0, str(HERE))
import controls as C
import discovery as DIS
import provenance as PR
import xauusd_1000_setups as X
from p01_cross_market import MARKETS, load_bidask_h1

SEED = 17
H = 3
COST = DIS.COST_SPREADS
SYM = "USDSEK"


def shape_expand(V, rt, pt, cheap=None):
    r = V["ret_atr"]
    rngv = V["range_atr"]
    s = np.sign(np.nan_to_num(r, nan=0.0))
    g1 = np.roll(rngv, 1)
    m = np.nan_to_num((rngv > rt) & (g1 < pt), nan=False)
    if cheap is not None:
        sa = V["spread_atr"]
        fin = np.isfinite(sa)
        cut = np.nanquantile(sa[fin], cheap) if fin.sum() > 5000 else -np.inf
        m &= np.nan_to_num(sa <= cut, nan=False)
    m &= np.isfinite(r) & (s != 0)
    m[:300] = False
    return np.where(m)[0], -s[m].astype(float)


def shape_exhaustion(V, thr=1.2):
    r = V["ret_atr"]
    s = np.sign(np.nan_to_num(r, nan=0.0))
    r1 = np.roll(r, 1)
    m = np.nan_to_num((np.abs(r) > thr) & (np.abs(r1) > thr)
                      & (s == np.sign(np.nan_to_num(r1, nan=0.0))), nan=False)
    m &= np.isfinite(r) & (s != 0)
    m[:300] = False
    return np.where(m)[0], s[m].astype(float)


def unconditional(V):
    r = V["ret_atr"]
    s = np.sign(np.nan_to_num(r, nan=0.0))
    m = np.isfinite(r) & (s != 0)
    m[:300] = False
    return np.where(m)[0], -s[m].astype(float)


CANDIDATES = [
    ("expand-quiet-cheap/1.5", lambda V: shape_expand(V, 1.5, 0.6, 0.33)),
    ("expand-quiet-cheap/1.8", lambda V: shape_expand(V, 1.8, 0.6, 0.33)),
    ("expand-quiet-cheap/1.2", lambda V: shape_expand(V, 1.2, 0.6, 0.33)),
    ("expand-after-quiet/1.5-0.4", lambda V: shape_expand(V, 1.5, 0.4)),
    ("expand-after-quiet/1.2-0.4", lambda V: shape_expand(V, 1.2, 0.4)),
    ("expand-after-quiet/1.8-0.6", lambda V: shape_expand(V, 1.8, 0.6)),
    ("expand-after-quiet/2.2-0.6", lambda V: shape_expand(V, 2.2, 0.6)),
    ("exhaustion/follow", shape_exhaustion),
]

# the panel figures these are being checked against, recorded here so the
# comparison is against what was claimed rather than against what is found
PANEL = {
    "expand-quiet-cheap/1.5": 2.631, "expand-quiet-cheap/1.8": 2.553,
    "expand-quiet-cheap/1.2": 2.212, "expand-after-quiet/1.5-0.4": 1.574,
    "expand-after-quiet/1.2-0.4": 1.100, "expand-after-quiet/1.8-0.6": 0.934,
    "expand-after-quiet/2.2-0.6": 0.924, "exhaustion/follow": 0.751,
}


def main():
    t0 = time.time()
    print(f"EVERY SURVIVOR AT ONCE - {SYM}, never used by any hypothesis here")
    print("=" * 100)
    print(__doc__.split("WHY ALL EIGHT AND NOT THE BEST ONE")[1]
          .split("WHAT IS BEING TESTED")[0])

    df = load_bidask_h1(SYM)
    if df is None:
        print(f"  no cached series for {SYM}")
        return
    P = X.prep(df, 60)
    V = DIS.state_vars(P)
    idx = pd.DatetimeIndex(P["idx"])
    print(f"  {len(df):,} cleaned bars, {idx[0].date()} -> {idx[-1].date()}\n")

    tu, du = unconditional(V)
    su = DIS.score(P, tu, du, H, idx=P["idx"])
    print(f"  calibration: the unconditional fade on this market is "
          f"{su['edge']:+.3f} of a round trip on {su['n']:,} signals\n")

    print(f"  {'candidate':<28}{'panel':>8}{'USDSEK':>9}{'n':>8}"
          f"{'vs uncond':>11}{'vs cost':>9}{'skill C7':>10}")
    rows = []
    A = np.asarray(P["A"], float)
    c = np.asarray(P["c"], float)
    for name, fn in CANDIDATES:
        t, d = fn(V)
        if len(t) < 150:
            print(f"  {name:<28}{'too few signals on this market':>45}")
            rows.append(dict(candidate=name, n=int(len(t)), edge=None))
            continue
        s = DIS.score(P, t, d, H, idx=P["idx"])
        if s is None:
            rows.append(dict(candidate=name, n=int(len(t)), edge=None))
            continue
        dv = np.zeros(P["N"], np.int8)
        dv[t] = d.astype(np.int8)
        Iv = np.full(P["N"], np.nan)
        Iv[t] = c[t] - d * 1.2 * A[t]
        dc, Ic, _ = C.build(P, dv, Iv, "C7", np.random.default_rng(SEED))
        tc = np.where(dc != 0)[0]
        sc = DIS.score(P, tc, dc[tc].astype(float), H)
        skill = s["edge"] - sc["edge"] if sc else np.nan
        beats_u = s["edge"] > su["edge"]
        beats_c = s["edge"] > COST
        rows.append(dict(candidate=name, panel=PANEL.get(name), n=s["n"],
                         edge=s["edge"], t=s["t"], skill_c7=skill,
                         beats_unconditional=bool(beats_u),
                         beats_cost=bool(beats_c),
                         top_year_share=s.get("top_year_share"),
                         years_positive=s.get("years_positive"),
                         years=s.get("years")))
        print(f"  {name:<28}{PANEL.get(name, float('nan')):>+8.3f}"
              f"{s['edge']:>+9.3f}{s['n']:>8,}"
              f"{'yes' if beats_u else 'no':>11}{'YES' if beats_c else 'no':>9}"
              f"{skill:>+10.3f}")

    ok = [r for r in rows if r.get("edge") is not None]
    tilt = sum(1 for r in ok if r["beats_unconditional"])
    over = sum(1 for r in ok if r["beats_cost"])
    mean_edge = float(np.mean([r["edge"] for r in ok])) if ok else np.nan
    print("\n" + "=" * 100)
    print("THE SET, WHICH IS THE POINT")
    print("=" * 100)
    print(f"  {len(ok)} of 8 produced a book on this market")
    print(f"  {tilt} beat the unconditional fade of {su['edge']:+.3f}")
    print(f"  {over} exceed one round trip")
    print(f"  mean edge across the set {mean_edge:+.3f}, "
          f"against a panel mean of "
          f"{np.mean([PANEL[r['candidate']] for r in ok]):+.3f}")
    if ok:
        print(f"  best {max(ok, key=lambda r: r['edge'])['candidate']} at "
              f"{max(r['edge'] for r in ok):+.3f}")

    verdict = ("CONSISTENT" if (tilt >= 6 and over >= 4)
               else "SCATTERED - indistinguishable from the unconditional fade"
               if tilt <= 5 else "MIXED")
    print(f"\n  VERDICT: {verdict}")
    print(f"\n  A single positive among eight is what noise produces and is")
    print(f"  not a survivor. Nothing here makes a finalist or licenses")
    print(f"  opening the sealed holdout, which stays examined: false.")

    out = HERE / "fresh_market_batch.json"
    out.write_text(json.dumps(dict(
        created=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        symbol=SYM, horizon=H, cost=COST, unconditional=su,
        candidates=rows, beat_unconditional=tilt, beat_cost=over,
        mean_edge=mean_edge, verdict=verdict,
        manifest=PR.manifest(dict(horizon=H, seed=SEED),
                             [HERE / ".cache_duka" /
                              f"{SYM}_H1_2003_2026.parquet"])),
        indent=1, default=str))
    PR.log("phase3-fresh-market-batch",
           "Do any of the pilot's survivors reproduce on the one market that "
           "had no part in producing them?",
           hypothesis="fresh_market_top_candidates",
           tools=["fresh_market_batch", "controls", "discovery"],
           result=dict(rows=rows, beat_unconditional=tilt, beat_cost=over,
                       verdict=verdict),
           status=verdict, finding=verdict,
           next_action="record; the holdout stays sealed either way",
           started=t0)
    print(f"\n  saved -> {out.name}   elapsed {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
