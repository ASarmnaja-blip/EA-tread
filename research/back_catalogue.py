#!/usr/bin/env python3
"""The repository's own catalogue, through every correction this run made.

THE LAST UNVERIFIED ASSUMPTION IN THIS PROJECT

  Everything measured in this run used a frame with 29% of its bars removed,
  a control that inherits the rule's geometry, and an edge metric that is a
  ratio of means. The back catalogue used none of those.

  The thirteen P-series templates, and the 837 hypotheses built on them, were
  scored as R through a bracket whose denominator charges volatility
  selection, on a sample where the engine rejected 84.8% of Monday bars
  against 56.9% of Thursday's because weekend flat bars had collapsed the
  ATR, against a control whose stop sat a third as far from entry as the
  rule's while R divides by that distance.

  Each of those defects has since been measured and fixed. So the catalogue's
  conclusions are not wrong - they are UNVERIFIED, and this run has been built
  on the principle that an unmeasured assumption is more dangerous than a
  negative result.

WHAT IS REPORTED AND WHY BOTH

  Each template twice: as R through the bracket, which is the number the
  catalogue produced, and as the signed move over the spread on the ratio of
  means, which is what this run uses and what the economics actually is.

  Then skill against C1 and against C7. The pair is the point. A template
  whose apparent skill sits at C1 and is gone at C7 was selecting activity,
  session or regime, and that shows up as a profile rather than as a single
  number that could be argued about.

WHAT WOULD BE SURPRISING

  That none clears is what 837 hypotheses of prior work predicts, and it is
  the likely outcome. The informative case is the opposite one: a template
  that looked dead on the contaminated frame and is alive on the clean one.
  The weekend defect biased against Monday trades by a factor of three, so a
  rule concentrated early in the week was measured on a third of the sample it
  should have had. Nothing rules that out in advance, which is the reason to
  look.
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
import discovery as DIS
import provenance as PR
import reversal_anatomy as RA
import xauusd_1000_setups as X
from engine_fast import engine
from p01_cross_market import MARKETS, TICKS, load_bidask_h1

SEED = 17
H = 3
STOP_MULT = 2.0
FLOOR = 5.00


def cross_t(v):
    v = np.asarray([y for y in v if np.isfinite(y)], float)
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

    print("THE BACK CATALOGUE, RESTATED")
    print("=" * 112)
    print(__doc__.split("WHAT IS REPORTED AND WHY BOTH")[1]
          .split("WHAT WOULD BE SURPRISING")[0])

    book = {}
    for sym in syms:
        df = load_bidask_h1(sym)
        if df is None or len(df) < 20000:
            continue
        P = X.prep(df, 60)
        tick = TICKS.get(sym, 1e-5)
        tm = X.make_templates(P)
        A = np.asarray(P["A"], float)
        c = np.asarray(P["c"], float)
        for name, fn in tm.items():
            try:
                d, I = fn()
            except Exception:
                continue
            t = np.where(np.asarray(d) != 0)[0]
            if len(t) < 500:
                continue
            dd = np.asarray(d)[t].astype(float)
            rec = dict(symbol=sym, n=int(len(t)))
            # the catalogue's own number
            r = engine(P, d, I, tick, stop_mult=STOP_MULT)
            rec["R"] = float(r[0].mean()) if r is not None else np.nan
            rec["n_bracket"] = len(r[0]) if r is not None else 0
            # this run's number
            s = DIS.score(P, t, dd, H, idx=P["idx"])
            rec["edge"] = s["edge"] if s else np.nan
            # and against the corrected controls
            for lv in ("C1", "C7"):
                dc, Ic, _ = C.build(P, d, I, lv, np.random.default_rng(SEED))
                tc = np.where(dc != 0)[0]
                sc = DIS.score(P, tc, dc[tc].astype(float), H)
                rec[f"edge_{lv}"] = sc["edge"] if sc else np.nan
                rec[f"skill_{lv}"] = ((rec["edge"] - sc["edge"])
                                      if (s and sc) else np.nan)
            book.setdefault(name, []).append(rec)
        print(f"  {sym:<9}{time.time()-t0:>7.0f}s", flush=True)

    rows = []
    for name, gs in book.items():
        if len(gs) < 3:
            continue
        e = np.array([g["edge"] for g in gs], float)
        t_e, pos_e, n_e = cross_t(e)
        s7 = np.array([g["skill_C7"] for g in gs], float)
        t7, pos7, n7 = cross_t(s7)
        s1 = np.array([g["skill_C1"] for g in gs], float)
        rows.append(dict(
            template=name, markets=len(gs),
            n_per_market=int(np.mean([g["n"] for g in gs])),
            R=float(np.nanmean([g["R"] for g in gs])),
            edge=float(np.nanmean(e)), t_edge=t_e, pos_edge=pos_e,
            skill_C1=float(np.nanmean(s1)),
            skill_C7=float(np.nanmean(s7)), t_C7=t7, pos_C7=pos7))
    R = pd.DataFrame(rows).sort_values("edge", ascending=False)

    print("\n" + "=" * 112)
    print("ALL THIRTEEN, BOTH NUMBERS, BOTH CONTROLS")
    print("=" * 112)
    print(f"  {'template':<10}{'mkts':>5}{'n/mkt':>8}{'R (bracket)':>13}"
          f"{'edge (spreads)':>16}{'t':>7}{'pos':>7}"
          f"{'skill C1':>11}{'skill C7':>11}{'t(C7)':>8}{'pos':>7}")
    for _, r in R.iterrows():
        print(f"  {r.template:<10}{r.markets:>5}{r.n_per_market:>8,}"
              f"{r.R:>+13.4f}{r.edge:>+16.4f}{r.t_edge:>+7.2f}"
              f"{int(r.pos_edge):>4}/{r.markets}"
              f"{r.skill_C1:>+11.4f}{r.skill_C7:>+11.4f}"
              f"{r.t_C7:>+8.2f}{int(r.pos_C7):>4}/{r.markets}")

    print("\n" + "=" * 112)
    print("WHAT THE TWO NUMBERS DISAGREE ABOUT")
    print("=" * 112)
    best_R = R.loc[R.R.idxmax()]
    best_e = R.loc[R.edge.idxmax()]
    print(f"  best by the catalogue's own R:  {best_R.template} at "
          f"{best_R.R:+.4f}R, whose edge is {best_R.edge:+.4f} spreads")
    print(f"  best by edge over the spread:   {best_e.template} at "
          f"{best_e.edge:+.4f} spreads, whose R is {best_e.R:+.4f}")
    rho = float(R.R.corr(R.edge))
    print(f"  rank correlation between the two across thirteen templates: "
          f"{rho:+.2f}")
    if abs(rho) < 0.5:
        print(f"  The two measures do not agree on which templates are best, "
              f"which is what the")
        print(f"  bracket's ATR denominator predicts: it charges the rules "
              f"that fire on big bars.")

    clear = R[(R.edge > 1.0) & (R.pos_edge >= 6) & (R.skill_C7 > 0)]
    print("\n" + "=" * 112)
    print("VERDICT")
    print("=" * 112)
    print(f"  {len(clear)} of {len(R)} templates clear one round trip on at "
          f"least 6 of 9 markets with positive skill against C7")
    if len(clear):
        for _, r in clear.iterrows():
            print(f"    {r.template}  edge {r.edge:+.4f}  t {r.t_edge:+.2f}  "
                  f"skill C7 {r.skill_C7:+.4f}")
        print(f"\n  Any of these must reproduce on USDSEK before it is called "
              f"anything - two")
        print(f"  candidates have already died at that step.")
    else:
        print(f"\n  The catalogue's conclusions survive their own correction. "
              f"The contaminated")
        print(f"  frame and the broken control did not hide a live setup: "
              f"the best template")
        print(f"  reaches {R.edge.max():+.4f} of a round trip against the "
              f"1.0 it needs.")
        print(f"  That is a result about this repository rather than about "
              f"the market, and it")
        print(f"  was the last unverified assumption the project held.")

    out = HERE / "back_catalogue.json"
    out.write_text(json.dumps(dict(
        created=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        horizon=H, stop_mult=STOP_MULT, floor=FLOOR,
        templates=R.to_dict("records"), clear=int(len(clear)),
        rank_corr_R_vs_edge=rho,
        manifest=PR.manifest(dict(horizon=H, seed=SEED),
                             [HERE / ".cache_duka" /
                              f"{s}_H1_2003_2026.parquet" for s in syms])),
        indent=1, default=str))
    PR.log("phase6-back-catalogue",
           "Do the repository's own templates read differently on the cleaned "
           "frame with the corrected control and metric?",
           hypothesis="back_catalogue_restated",
           tools=["back_catalogue", "controls", "discovery", "engine_fast"],
           result=dict(templates=R.to_dict("records"), clear=int(len(clear))),
           status="MEASURED",
           finding=f"{len(clear)} of {len(R)} templates clear",
           next_action="record against the registered criterion",
           started=t0)
    print(f"\n  saved -> {out.name}   elapsed {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
