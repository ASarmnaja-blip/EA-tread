#!/usr/bin/env python3
"""Does the signal predict the move - asked without an execution assumption.

WHY THE BRACKET HAD TO GO

  Every one of the 837 hypotheses in this project's ledger has been scored as
  R through a stop-and-target bracket, and the control hierarchy has just
  measured that this instrument is not neutral about direction:

    R is (exit - entry) / dist, and dist is set from the signal bar's ATR.
    Every family here fires on high-ATR bars. A larger denominator earns a
    smaller R for the same price move, so the measure charges a rule for
    selecting movement whether or not its direction is right.

  All four families came back NEGATIVE against matched controls, with
  intermediate levels reaching t -3.16, and the mechanism is a property of the
  measure rather than of the market. A synthetic rule that selects busy bars
  and faces a coin reproduces the same sign.

  So the question "is there directional information here" has been asked
  through an instrument that cannot separate it from volatility selection,
  837 times.

WHAT IS ASKED INSTEAD

  Entry at the mid open of the bar after the signal. Exit at the mid close h
  bars later. Nothing else. No stop, no target, no tie-break rule for bars
  that touch both, no one-position-at-a-time constraint. None of those exist
  in the question.

  The signed move is reported three ways, and the three are the point:

    raw          in price units. Carries no normalisation and therefore no
                 volatility-selection term, but is not comparable across
                 markets or eras.
    over ATR     divided by the PRE-SIGNAL ATR at bar t. Comparable, and
                 still divides by a volatility estimate - but by one fixed
                 before the trade, applied identically to the matched control,
                 and not used to decide when the trade ends.
    over spread  divided by the spread at bar t. This is the only one that is
                 an economic quantity: how many round trips of cost the move
                 is worth.

  If raw and over-ATR disagree in sign or significance, that difference IS the
  volatility-selection term, and it is reported rather than resolved by
  preferring whichever is more flattering.

SIGN AND SIZE ARE REPORTED APART

  A signal can be right about direction and wrong about magnitude, or the
  reverse, and a bracket conflates them into one number. Sign accuracy against
  the control's sign accuracy answers the first; the mean answers both
  together. A family with 51% sign accuracy and a negative mean is predicting
  direction and being killed by the times it is wrong, which is a different
  research problem from one with 50% and a positive mean.

THE OVERLAP CHARGE

  Signals h bars apart share h-1 bars of outcome. The within-market t is
  therefore computed on an effective sample of n/h rather than n, which is the
  standard block correction and is conservative for h small. The across-market
  t, on nine independent means, is reported beside it and is the one the
  criterion uses.
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
from p01_cross_market import MARKETS, TICKS, load_bidask_h1
from profile_setups import momentum_signal, reversion_signal
from value_area_setups import breakout_signal, prior_value_areas, rotation_signal

SEED = 17
HORIZONS = (1, 3, 6, 12, 24, 48)
FLOOR = 4.74


def forward(P, dvec, h):
    """Signed move from the mid open after the signal to the mid close h on.

    Returns (raw, over_atr, over_spread, sign) over the signals that have a
    complete forward window. The entry uses bar t+1's OPEN, never bar t's
    close, because the signal is only known once bar t has closed."""
    N = P["N"]
    o = (np.asarray(P["bid_o"], float) + np.asarray(P["ask_o"], float)) / 2
    c = np.asarray(P["c"], float)
    A = np.asarray(P["A"], float)
    sp = np.asarray(P["spread"], float)
    t = np.where(np.asarray(dvec) != 0)[0]
    t = t[(t >= 300) & (t + h < N - 1)]
    if len(t) == 0:
        return None
    d = np.asarray(dvec)[t].astype(float)
    entry = o[t + 1]
    exit_ = c[t + h]
    raw = d * (exit_ - entry)
    a, s = A[t], sp[t]
    with np.errstate(invalid="ignore", divide="ignore"):
        z = np.where(np.isfinite(a) & (a > 0), raw / a, np.nan)
        q = np.where(np.isfinite(s) & (s > 0), raw / s, np.nan)
    ok = np.isfinite(raw) & np.isfinite(z) & np.isfinite(q)
    if ok.sum() < 200:
        return None
    return dict(n=int(ok.sum()), t_idx=t[ok], raw=raw[ok], z=z[ok], q=q[ok],
                sign=(raw[ok] > 0).astype(float))


def stats(x, h):
    """Mean with an overlap-charged standard error."""
    x = np.asarray(x, float)
    x = x[np.isfinite(x)]
    if len(x) < 30:
        return dict(mean=np.nan, t=np.nan, n=0)
    n_eff = max(len(x) / h, 2.0)
    se = float(x.std(ddof=1) / math.sqrt(n_eff))
    return dict(mean=float(x.mean()), t=float(x.mean() / se) if se > 0 else np.nan,
                n=int(len(x)), n_eff=round(n_eff, 1))


def families(P):
    lo, hi, poc, _ = prior_value_areas(P)
    return [("momentum", lambda: momentum_signal(P)),
            ("reversion", lambda: reversion_signal(P)),
            ("va-rotate", lambda: rotation_signal(P, lo, hi, poc)),
            ("va-break", lambda: breakout_signal(P, lo, hi, poc))]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols", default=",".join(MARKETS))
    ap.add_argument("--levels", default="C1,C4,C7")
    a = ap.parse_args()
    t0 = time.time()
    syms = [s.strip() for s in a.symbols.split(",") if s.strip()]
    levels = [s.strip() for s in a.levels.split(",") if s.strip()]

    print("DIRECTION WITHOUT A BRACKET - the move itself, three ways")
    print("=" * 112)
    print(__doc__.split("WHAT IS ASKED INSTEAD")[1].split("SIGN AND SIZE")[0])

    rows = []
    for sym in syms:
        df = load_bidask_h1(sym)
        if df is None or len(df) < 20000:
            continue
        P = X.prep(df, 60)
        for lab, fn in families(P):
            d, I = fn()
            if int((d != 0).sum()) < 300:
                continue
            ctrl = {}
            for lv in levels:
                dc, Ic, meta = C.build(P, d, I, lv, np.random.default_rng(SEED))
                ctrl[lv] = dc
            for h in HORIZONS:
                r = forward(P, d, h)
                if r is None:
                    continue
                rec = dict(symbol=sym, setup=lab, h=h, n=r["n"])
                for key in ("raw", "z", "q", "sign"):
                    st = stats(r[key], h)
                    rec[f"{key}_mean"] = st["mean"]
                    rec[f"{key}_t"] = st["t"]
                for lv in levels:
                    rc = forward(P, ctrl[lv], h)
                    if rc is None:
                        continue
                    for key in ("raw", "z", "q", "sign"):
                        rec[f"{key}_{lv}"] = float(np.nanmean(rc[key]))
                        rec[f"{key}_skill_{lv}"] = (
                            rec[f"{key}_mean"] - float(np.nanmean(rc[key])))
                rows.append(rec)
        print(f"  {sym} done  {time.time()-t0:.0f}s", flush=True)

    if not rows:
        print("  nothing measured")
        return
    D = pd.DataFrame(rows)

    print("\n" + "=" * 112)
    print("SIGNED MOVE OVER PRE-SIGNAL ATR, AGAINST EACH CONTROL")
    print("=" * 112)
    print(f"  {'family':<11}{'h':>4}{'markets':>8}{'raw skill':>12}"
          + "".join(f"{'z vs ' + lv:>12}" for lv in levels)
          + f"{'t(C7)':>8}{'pos':>7}{'sign%':>8}")
    summary = []
    for lab in D.setup.unique():
        for h in HORIZONS:
            g = D[(D.setup == lab) & (D.h == h)]
            if len(g) < 3:
                continue
            row = dict(family=lab, h=int(h), markets=len(g))
            for lv in levels:
                col = f"z_skill_{lv}"
                if col not in g:
                    continue
                s = g[col].to_numpy(float)
                s = s[np.isfinite(s)]
                if len(s) < 3:
                    continue
                se = float(s.std(ddof=1) / math.sqrt(len(s)))
                row[f"z_{lv}"] = float(s.mean())
                row[f"t_{lv}"] = float(s.mean() / se) if se > 0 else np.nan
                row[f"pos_{lv}"] = int((s > 0).sum())
            rawc = f"raw_skill_{levels[-1]}"
            row["raw_last"] = (float(np.nanmean(g[rawc]))
                               if rawc in g else np.nan)
            row["sign"] = float(np.nanmean(g["sign_mean"]))
            sc = f"sign_skill_{levels[-1]}"
            row["sign_skill"] = float(np.nanmean(g[sc])) if sc in g else np.nan
            summary.append(row)
            last = levels[-1]
            print(f"  {lab:<11}{h:>4}{len(g):>8}{row['raw_last']:>+12.5f}"
                  + "".join(f"{row.get('z_' + lv, float('nan')):>+12.4f}"
                            for lv in levels)
                  + f"{row.get('t_' + last, float('nan')):>+8.2f}"
                  + f"{row.get('pos_' + last, 0):>5}/{len(g)}"
                  + f"{row['sign']*100:>8.2f}")
        print()

    last = levels[-1]
    print("=" * 112)
    print(f"THE DECISION QUANTITY - signed move over ATR against {last}, "
          f"floor {FLOOR}")
    print("=" * 112)
    best = None
    for r in sorted(summary, key=lambda r: -abs(r.get(f"t_{last}", 0) or 0))[:8]:
        t = r.get(f"t_{last}", np.nan)
        clears = np.isfinite(t) and t > FLOOR and r.get(f"pos_{last}", 0) >= 6
        print(f"  {r['family']:<11}h {r['h']:>3}   z skill "
              f"{r.get('z_' + last, float('nan')):>+8.4f}   t {t:>+6.2f}   "
              f"positive on {r.get('pos_' + last, 0)}/{r['markets']}   "
              f"sign {r['sign']*100:.2f}%   "
              f"{'CLEARS' if clears else 'does not clear'}")
        if best is None or (np.isfinite(t) and t > best[1]):
            best = (r, t)

    cleared = [r for r in summary
               if np.isfinite(r.get(f"t_{last}", np.nan))
               and r[f"t_{last}"] > FLOOR and r.get(f"pos_{last}", 0) >= 6]
    print(f"\n  {len(cleared)} of {len(summary)} family-horizon cells clear "
          f"the floor on the strongest control")
    print(f"  A null here is stronger than a null through the bracket: it")
    print(f"  says the representation carries no directional information at")
    print(f"  any horizon from one hour to two days, with no execution")
    print(f"  assumption of any kind in the measurement.")

    out = HERE / "direction_target.json"
    out.write_text(json.dumps(dict(
        created=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        horizons=list(HORIZONS), levels=levels, floor=FLOOR,
        per_market=rows, summary=summary, cleared=len(cleared),
        manifest=PR.manifest(dict(horizons=list(HORIZONS), seed=SEED),
                             [HERE / ".cache_duka" /
                              f"{s}_H1_2003_2026.parquet" for s in syms])),
        indent=1, default=str))
    PR.log("phase1-reframe-target",
           "Does the signal predict the forward move, measured with no "
           "execution assumption at all?",
           hypothesis="direction_without_bracket",
           tools=["controls", "direction_target"],
           result=dict(cleared=len(cleared), cells=len(summary),
                       best=(best[0] if best else None)),
           status="MEASURED",
           finding=f"{len(cleared)} of {len(summary)} family-horizon cells "
                   f"clear the floor against {last}",
           next_action="if nothing clears, the target itself is the problem - "
                       "move to path asymmetry and expansion probability",
           started=t0)
    print(f"\n  saved -> {out.name}   elapsed {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
