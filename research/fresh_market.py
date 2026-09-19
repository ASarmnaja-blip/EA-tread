#!/usr/bin/env python3
"""One market that no hypothesis in this repository has ever touched.

WHY THIS IS WORTH RUNNING AND WHAT IT CANNOT DO

  The candidate survives everything structural: the control hierarchy to C7,
  a parameter plateau with a monotone gradient, both halves of twenty-two
  years, leave-one-market-out, a delayed entry, and the contiguity check that
  would have exposed it as a rollover-gap artifact. Its point estimate of
  +1.316 spreads exceeds the 1.105 that the round trip plus financing costs.

  It is held back by one number: a bootstrap t of 3.67 against a floor of 4.84
  that 1,085 hypotheses have earned. No amount of further searching on the
  same nine markets can resolve that, because the floor rises with every
  hypothesis spent looking.

  USDSEK sits in the cache with a full 2003-2026 series. The engineering audit
  flagged it as present and outside the nine-market panel, and no hypothesis
  in this repository has ever used it. It carries a USD leg, so it is not part
  of the sealed holdout either.

  One market cannot confirm an effect. A positive result here does NOT make
  this a finalist and does NOT license opening the sealed holdout. A negative
  one would end the line. That asymmetry is the entire reason to run it, and
  saying so before the result is what keeps a positive from being promoted
  afterwards.

WHAT IS FROZEN

  The parameters 1.5 and 0.7 come from the panel and were fixed before this
  file loaded USDSEK. The surface is computed too, but as description: if the
  gradient reproduces - quieter preceding bars giving larger edges - that is
  worth more than the point estimate, because a gradient is much harder for
  noise to imitate than a level.
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
from p01_cross_market import load_bidask_h1

SEED = 17
H = 3
COST = DIS.COST_SPREADS
FROZEN = (1.5, 0.7)
PANEL_CI = (0.627, 2.022)
PANEL_EDGE = 1.316
SYM = "USDSEK"


def candidate(V, rng_thr, prev_thr):
    r = V["ret_atr"]
    rngv = V["range_atr"]
    s = np.sign(np.nan_to_num(r, nan=0.0))
    g1 = np.roll(rngv, 1)
    m = np.nan_to_num((rngv > rng_thr) & (g1 < prev_thr), nan=False)
    m &= np.isfinite(r) & (s != 0)
    m[:300] = False
    return np.where(m)[0], -s[m].astype(float)


def unconditional(V):
    r = V["ret_atr"]
    s = np.sign(np.nan_to_num(r, nan=0.0))
    m = np.isfinite(r) & (s != 0)
    m[:300] = False
    return np.where(m)[0], -s[m].astype(float)


def month_bootstrap(P, t, d, h, rng, draws=2000):
    N = P["N"]
    keep = (t >= 300) & (t + h < N - 1)
    t, d = t[keep], d[keep]
    o = (np.asarray(P["bid_o"], float) + np.asarray(P["ask_o"], float)) / 2
    c = np.asarray(P["c"], float)
    sp = (np.asarray(P["ask_o"], float)[t + 1]
          - np.asarray(P["bid_o"], float)[t + 1])
    mv = d * (c[t + h] - o[t + 1])
    ok = np.isfinite(mv) & np.isfinite(sp) & (sp > 0)
    if ok.sum() < 200:
        return None
    x = mv[ok] / sp[ok]
    mo = np.asarray(pd.DatetimeIndex(P["idx"])[t[ok]]
                    .tz_localize(None).to_period("M").astype(str))
    uniq = np.unique(mo)
    by = {m: x[mo == m] for m in uniq}
    out = np.empty(draws)
    for i in range(draws):
        pick = rng.choice(uniq, size=len(uniq), replace=True)
        out[i] = np.concatenate([by[m] for m in pick]).mean()
    ci = np.quantile(out, [0.025, 0.975])
    return dict(n=int(len(x)), months=len(uniq), edge=float(x.mean()),
                se=float(out.std(ddof=1)),
                t=float(x.mean() / out.std(ddof=1)) if out.std() > 0 else np.nan,
                ci_low=float(ci[0]), ci_high=float(ci[1]),
                p_above_cost=float((out > COST).mean()))


def main():
    t0 = time.time()
    print(f"FRESH MARKET - {SYM}, never used by any hypothesis here")
    print("=" * 96)
    print(__doc__.split("WHAT IS FROZEN")[1])

    df = load_bidask_h1(SYM)
    if df is None:
        print(f"  no cached series for {SYM}")
        return
    P = X.prep(df, 60)
    V = DIS.state_vars(P)
    idx = pd.DatetimeIndex(P["idx"])
    print(f"  {len(df):,} cleaned bars, {idx[0].date()} -> {idx[-1].date()}")
    print(f"  median spread / ATR {np.nanmedian(np.asarray(P['spread'], float) / np.asarray(P['A'], float)):.4f}\n")

    rng = np.random.default_rng(SEED)
    print("=" * 96)
    print("THE FROZEN TEST")
    print("=" * 96)
    tu, du = unconditional(V)
    su = DIS.score(P, tu, du, H)
    tc, dc = candidate(V, *FROZEN)
    sc = DIS.score(P, tc, dc, H)
    if sc is None or su is None:
        print("  not enough signals to measure")
        return
    bu = month_bootstrap(P, tu, du, H, np.random.default_rng(SEED))
    bc = month_bootstrap(P, tc, dc, H, np.random.default_rng(SEED))

    print(f"  {'rule':<30}{'n':>8}{'edge':>10}{'boot t':>9}"
          f"{'95% interval':>22}{'sign%':>8}")
    for lab, s, b in (("unconditional fade", su, bu),
                      (f"expand-after-quiet {FROZEN}", sc, bc)):
        print(f"  {lab:<30}{s['n']:>8,}{s['edge']:>+10.3f}"
              f"{b['t'] if b else float('nan'):>+9.2f}"
              f"   [{b['ci_low'] if b else float('nan'):+.3f}, "
              f"{b['ci_high'] if b else float('nan'):+.3f}]"
              f"{s['sign_rate']*100:>8.2f}")

    # the C7 control on the fresh market
    A = np.asarray(P["A"], float)
    c = np.asarray(P["c"], float)
    dv = np.zeros(P["N"], np.int8)
    dv[tc] = dc.astype(np.int8)
    Iv = np.full(P["N"], np.nan)
    Iv[tc] = c[tc] - dc * 1.2 * A[tc]
    dctl, Ictl, meta = C.build(P, dv, Iv, "C7", np.random.default_rng(SEED))
    tctl = np.where(dctl != 0)[0]
    sctl = DIS.score(P, tctl, dctl[tctl].astype(float), H)
    skill = sc["edge"] - sctl["edge"] if sctl else np.nan
    print(f"\n  C7 control on this market {sctl['edge'] if sctl else float('nan'):+.3f}"
          f"   skill {skill:+.3f}")

    print("\n" + "=" * 96)
    print("THE SURFACE - description only, the decision rests on the frozen "
          "point")
    print("=" * 96)
    prevs = (0.5, 0.6, 0.7, 0.8, 0.9)
    rngs = (1.2, 1.35, 1.5, 1.65, 1.8)
    print(f"  {'':<8}" + "".join(f"{p:>9.2f}" for p in prevs)
          + "      <- previous bar range, ATR")
    grid = []
    for rt in rngs:
        line = []
        for pt in prevs:
            t, d = candidate(V, rt, pt)
            s = DIS.score(P, t, d, H) if len(t) >= 100 else None
            v = s["edge"] if s else np.nan
            grid.append(dict(rng_thr=rt, prev_thr=pt, edge=v,
                             n=s["n"] if s else 0))
            line.append(v)
        print(f"  {rt:>6.2f}  " + "".join(f"{v:>+9.3f}" for v in line))
    # does the gradient reproduce: edge should fall as prev_thr rises
    cols = {p: np.nanmean([g["edge"] for g in grid if g["prev_thr"] == p])
            for p in prevs}
    order = [cols[p] for p in prevs]
    mono = sum(1 for i in range(len(order) - 1)
               if np.isfinite(order[i]) and np.isfinite(order[i + 1])
               and order[i] >= order[i + 1])
    print(f"\n  column means " + "  ".join(f"{p}: {cols[p]:+.3f}"
                                           for p in prevs))
    print(f"  the panel's gradient falls as the previous bar gets noisier; "
          f"here {mono} of 4 steps fall")

    print("\n" + "=" * 96)
    print("VERDICT AGAINST THE CRITERION REGISTERED BEFORE THIS RAN")
    print("=" * 96)
    beats_uncond = sc["edge"] > su["edge"]
    in_ci = PANEL_CI[0] <= sc["edge"] <= PANEL_CI[1]
    positive = sc["edge"] > 0
    if not positive or not beats_uncond:
        verdict = "FALSIFIED on fresh data"
    elif in_ci:
        verdict = "CONSISTENT with the panel"
    else:
        verdict = "POSITIVE BUT OUTSIDE THE PANEL INTERVAL"
    print(f"  edge {sc['edge']:+.3f}   unconditional {su['edge']:+.3f}   "
          f"beats it: {beats_uncond}")
    print(f"  panel 95% interval [{PANEL_CI[0]:+.3f}, {PANEL_CI[1]:+.3f}]   "
          f"inside: {in_ci}")
    print(f"\n  VERDICT: {verdict}")
    print(f"\n  One market confirms nothing. This does not make the candidate")
    print(f"  a finalist and does not license opening the sealed holdout,")
    print(f"  which remains examined: false.")

    out = HERE / "fresh_market.json"
    out.write_text(json.dumps(dict(
        created=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        symbol=SYM, frozen=list(FROZEN), horizon=H, cost=COST,
        bars=len(df), unconditional=su, candidate=sc,
        boot_unconditional=bu, boot_candidate=bc,
        c7_control=sctl, skill_vs_c7=skill, grid=grid,
        column_means={str(k): float(v) for k, v in cols.items()},
        monotone_steps=mono, verdict=verdict,
        manifest=PR.manifest(dict(frozen=FROZEN, horizon=H, seed=SEED),
                             [HERE / ".cache_duka" /
                              f"{SYM}_H1_2003_2026.parquet"])),
        indent=1, default=str))
    PR.log("phase2-fresh-market",
           "Does the candidate reproduce on a market no hypothesis in this "
           "repository has ever used?",
           hypothesis="fresh_market_usdsek",
           tools=["fresh_market", "controls"],
           result=dict(edge=sc["edge"], unconditional=su["edge"],
                       boot=bc, skill_vs_c7=skill, verdict=verdict),
           status=verdict, finding=verdict,
           next_action="record; the holdout stays sealed either way",
           started=t0)
    print(f"\n  saved -> {out.name}   elapsed {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
