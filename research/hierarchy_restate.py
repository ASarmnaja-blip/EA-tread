#!/usr/bin/env python3
"""The four families, re-measured through a control that is the same instrument.

WHY THE PREVIOUS ANSWER DOES NOT STAND EITHER WAY

  vol_matched_control concluded that 91% of this session's apparent skill was
  activity selection. That conclusion was measured through random_like, and
  audit check 8 has since measured what random_like actually does: it takes
  the RANDOM bar's own high or low as the invalidation level, so the control's
  stop sits a third as far away as the rule's - dist/ATR median 0.559 against
  1.638 on gold momentum.

  R is (exit - entry) / dist. A control whose dist is a third of the rule's
  reports returns scaled up roughly threefold. So the +0.0171 against the
  timing control and the +0.0015 against the volatility-matched one were both
  read across that gap, and the ratio between them was too.

  That does not make the retraction wrong. It makes it unmeasured. The claim
  and its retraction rest on the same broken instrument, and the honest
  position until this runs is that nothing is known about these four families.

WHAT IS DIFFERENT HERE

  Every control inherits its real signal's own dist/ATR ratio and rebuilds an
  invalidation level at that ratio on the donor bar. The measured geometry gap
  across all eight levels is 0.0%. The two books are the same instrument and
  differ only in WHEN they enter and WHICH WAY they face.

READING THE PROFILE RATHER THAN A NUMBER

  Eight levels are reported, not one. The shape is the finding:

    skill high at C1 and gone by C3      activity selection
    skill high at C1 and gone by C4      session selection
    skill surviving C5 but not C6        regime selection
    skill surviving to C7                directional information

  A single figure cannot distinguish those, which is why no number in this
  file is printed without its level.
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
import controls as C
import provenance as PR
import xauusd_1000_setups as X
from bracket_bias import engine
from p01_cross_market import MARKETS, TICKS, load_bidask_h1
from profile_setups import momentum_signal, reversion_signal
from value_area_setups import (STOP_MULT, breakout_signal, prior_value_areas,
                               rotation_signal)

SEED = 17
FLOOR = 4.73          # the ledger's floor at k = 837, printed not recomputed


def families(P):
    lo, hi, poc, _ = prior_value_areas(P)
    return [("momentum", lambda: momentum_signal(P)),
            ("reversion", lambda: reversion_signal(P)),
            ("va-rotate", lambda: rotation_signal(P, lo, hi, poc)),
            ("va-break", lambda: breakout_signal(P, lo, hi, poc))]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols", default=",".join(MARKETS))
    ap.add_argument("--levels", default=",".join(C.LEVELS))
    a = ap.parse_args()
    t0 = time.time()
    syms = [s.strip() for s in a.symbols.split(",") if s.strip()]
    levels = [s.strip() for s in a.levels.split(",") if s.strip()]

    print("THE FOUR FAMILIES THROUGH C0-C7 - geometry held constant")
    print("=" * 108)
    print(__doc__.split("WHAT IS DIFFERENT HERE")[1].split("READING THE")[0])

    rows, gaps = [], []
    for sym in syms:
        df = load_bidask_h1(sym)
        if df is None or len(df) < 20000:
            continue
        P = X.prep(df, 60)
        tick = TICKS.get(sym, 0.00001)
        for lab, fn in families(P):
            d, I = fn()
            if int((d != 0).sum()) < 300:
                continue
            real = engine(P, d, I, tick, stop_mult=STOP_MULT)
            if real is None:
                continue
            e = float(real[0].mean())
            vr = float(real[0].var(ddof=1))
            for lv in levels:
                dc, Ic, meta = C.build(P, d, I, lv,
                                       np.random.default_rng(SEED))
                g = C.geometry_gap(P, d, I, dc, Ic)
                gaps.append(g.get("rel_gap", np.nan))
                r = engine(P, dc, Ic, tick, stop_mult=STOP_MULT)
                if r is None:
                    continue
                ce = float(r[0].mean())
                se = math.sqrt(vr / len(real[0])
                               + float(r[0].var(ddof=1)) / len(r[0]))
                rows.append(dict(
                    symbol=sym, setup=lab, level=lv, n=len(real[0]),
                    n_ctrl=len(r[0]), E=e, control_E=ce, skill=e - ce,
                    t_within=(e - ce) / se if se > 0 else np.nan,
                    placement=meta["placement_rate"],
                    match_rate=meta["match_rate"],
                    geom_gap=g.get("rel_gap", np.nan)))
            print(f"  {sym:<9}{lab:<11}n {len(real[0]):>6,}  E {e:>+8.4f}  "
                  + "  ".join(
                      f"{lv} {next((x['skill'] for x in rows if x['symbol'] == sym and x['setup'] == lab and x['level'] == lv), float('nan')):+.4f}"
                      for lv in levels), flush=True)

    if not rows:
        print("\n  nothing produced a book")
        return
    D = pd.DataFrame(rows)
    mg = float(np.nanmax(gaps)) if gaps else np.nan
    print(f"\n  worst geometry gap across every control built: {mg:.2%} "
          f"(random_like measured 73%)")

    print("\n" + "=" * 108)
    print("BY FAMILY - the profile across the hierarchy")
    print("=" * 108)
    print(f"  {'family':<12}{'level':<6}{'markets':>8}{'skill':>10}"
          f"{'t across':>10}{'pos':>6}  what the level holds constant")
    summary = []
    for lab in D.setup.unique():
        for lv in levels:
            g = D[(D.setup == lab) & (D.level == lv)]
            if len(g) < 3:
                continue
            s = g.skill.to_numpy(float)
            se = float(s.std(ddof=1) / math.sqrt(len(s)))
            t = float(s.mean() / se) if se > 0 else np.nan
            summary.append(dict(family=lab, level=lv, markets=len(g),
                                skill=float(s.mean()), t=t,
                                positive=int((s > 0).sum())))
            print(f"  {lab:<12}{lv:<6}{len(g):>8}{s.mean():>+10.4f}"
                  f"{t:>+10.2f}{int((s > 0).sum()):>4}/{len(g)}  "
                  f"{C.DESCRIPTION[lv]}")
        print()

    print("=" * 108)
    print("THE DECISION QUANTITY - skill against C7, which is the only level "
          "that needs a direction")
    print("=" * 108)
    verdicts = []
    for lab in D.setup.unique():
        c1 = next((r for r in summary if r["family"] == lab
                   and r["level"] == "C1"), None)
        c7 = next((r for r in summary if r["family"] == lab
                   and r["level"] == "C7"), None)
        if not c7:
            continue
        kept = (c7["skill"] / c1["skill"] * 100
                if c1 and abs(c1["skill"]) > 1e-9 else float("nan"))
        cleared = np.isfinite(c7["t"]) and c7["t"] > FLOOR
        verdicts.append(dict(family=lab, c1=c1["skill"] if c1 else None,
                             c7=c7["skill"], t=c7["t"], retained=kept,
                             clears_floor=bool(cleared)))
        print(f"  {lab:<12}vs C1 {c1['skill'] if c1 else float('nan'):>+8.4f}"
              f"   vs C7 {c7['skill']:>+8.4f}   retained {kept:>6.0f}%"
              f"   t {c7['t']:>+6.2f}   floor {FLOOR}   "
              f"{'CLEARS' if cleared else 'does not clear'}")

    best = max(verdicts, key=lambda r: r["t"]) if verdicts else None
    print(f"\n  best family against C7: {best['family'] if best else 'none'}"
          f" at t {best['t'] if best else float('nan'):+.2f}")
    print(f"  A profile that is large at C1 and gone by C3 is activity")
    print(f"  selection; gone by C4 is session; gone by C6 is regime. Only a")
    print(f"  figure that survives C7 is a statement about direction.")

    out = HERE / "hierarchy_restate.json"
    out.write_text(json.dumps(dict(
        created=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        stop_mult=STOP_MULT, seed=SEED, floor=FLOOR,
        worst_geometry_gap=mg, levels=levels,
        per_market=rows, by_family=summary, verdicts=verdicts,
        manifest=PR.manifest(
            dict(stop_mult=STOP_MULT, seed=SEED, levels=levels),
            [HERE / ".cache_duka" / f"{s}_H1_2003_2026.parquet"
             for s in syms])), indent=1, default=str))
    PR.log("phase1-control-hierarchy",
           "Do any of the four families carry directional information once "
           "geometry, timing, activity, volatility, session, regime and range "
           "position are all held constant?",
           hypothesis="control_hierarchy_restatement",
           tools=["controls", "bracket_bias.engine", "hierarchy_restate"],
           result=dict(verdicts=verdicts, worst_geometry_gap=mg),
           status="MEASURED",
           finding=("; ".join(f"{v['family']} C1 {v['c1']:+.4f} -> C7 "
                              f"{v['c7']:+.4f} t {v['t']:+.2f}"
                              for v in verdicts)),
           next_action="record in the ledger against the registered criterion",
           started=t0)
    print(f"\n  saved -> {out.name}   elapsed {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
