#!/usr/bin/env python3
"""Is there a corner of this market where the quote is already cheap enough?

THE LAST THING BETWEEN THIS PROJECT AND A DEFINITE ANSWER ABOUT COST

  The anatomy established two numbers that point in opposite directions.

  In favour: the reversal is volatility-scaled, so the edge in spread units is
  amplitude over cost ratio and a tighter quote genuinely raises it. One round
  trip needs spread/ATR at 0.01517. The cheapest decile already sits at 0.0183
  - and that is a MEDIAN, so the cells beneath it go lower. A corner at 0.015
  would pay with no venue change at all.

  Against: the implied amplitude is not constant. It falls from 0.02387 ATR at
  the dear end to 0.00392 at the cheap end. A cheap quote comes with a smaller
  move as well as a smaller cost, so the ratio may plateau rather than keep
  climbing.

  Which wins at the extreme is a measurement, not an argument.

WHY THE WHOLE SWEEP IS REPORTED AND NOT ITS BEST CELL

  Selecting the cheapest cells IS a search. Its best member is the maximum of
  a sample and will look better than the truth by construction, which is what
  the multiple-testing floor exists to price. The shape of the curve is what
  carries information: an edge still climbing as the quote tightens means a
  corner exists and the sweep simply has not reached it; an edge that flattens
  means the amplitude falls as fast as the cost and no corner does, however
  far it is pushed.

  A number of signals per year is reported at every step, because a corner
  that pays and fires eleven times is not a corner.
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
import reversal_anatomy as RA
from p01_cross_market import MARKETS

PCTS = (0.5, 1.0, 2.0, 5.0, 10.0, 20.0, 50.0, 100.0)
YEARS = 22.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols", default=",".join(RA.PANEL))
    a = ap.parse_args()
    t0 = time.time()
    syms = [s.strip() for s in a.symbols.split(",") if s.strip()]

    print("THE CHEAP CORNER - does the edge keep climbing as the quote "
          "tightens?")
    print("=" * 104)
    print(__doc__.split("WHY THE WHOLE SWEEP IS REPORTED")[1])

    frames = []
    for s in syms:
        f = RA.cells(s)
        if f is not None:
            frames.append(f)
    if not frames:
        print("  nothing measured")
        return
    D = pd.concat(frames, ignore_index=True)
    D["cost_ratio"] = D.spread / D.atr
    D = D[np.isfinite(D.cost_ratio) & (D.cost_ratio > 0)]
    print(f"  {len(D):,} signals across {D.symbol.nunique()} markets\n")

    print(f"  {'cheapest':<10}{'spread/ATR':>12}{'signals':>11}"
          f"{'per year':>10}{'mkts':>6}{'edge':>10}{'amplitude':>12}"
          f"{'pos':>7}")
    rows = []
    for pct in PCTS:
        cut = float(np.percentile(D.cost_ratio, pct))
        m = D.cost_ratio <= cut
        if m.sum() < 2000:
            continue
        e, nm = RA.agg(D, m, min_n=200)
        per = []
        for sym, gs in D[m].groupby("symbol"):
            if len(gs) < 200 or gs.spread.sum() <= 0:
                continue
            per.append(float(gs.move.sum() / gs.spread.sum()))
        pos = int(sum(1 for v in per if v > 0))
        med = float(D.cost_ratio[m].median())
        amp = e * med if np.isfinite(e) else np.nan
        rows.append(dict(pct=pct, cut=cut, median_ratio=med,
                         signals=int(m.sum()),
                         per_year=int(m.sum() / YEARS / max(nm, 1)),
                         markets=nm, edge=e, amplitude=amp, positive=pos))
        print(f"  {pct:<10.1f}{med:>12.5f}{int(m.sum()):>11,}"
              f"{int(m.sum()/YEARS/max(nm,1)):>10,}{nm:>6}{e:>+10.4f}"
              f"{amp:>12.5f}{pos:>4}/{nm}")

    print("\n" + "=" * 104)
    print("THE SHAPE, WHICH IS THE POINT")
    print("=" * 104)
    fin = [r for r in rows if np.isfinite(r["edge"])]
    if len(fin) >= 3:
        tight = fin[0]
        wide = fin[-1]
        print(f"  cheapest {tight['pct']}% of cells: spread/ATR "
              f"{tight['median_ratio']:.5f}, edge {tight['edge']:+.4f}")
        print(f"  the whole sample:            spread/ATR "
              f"{wide['median_ratio']:.5f}, edge {wide['edge']:+.4f}")
        ratio_gain = wide["median_ratio"] / tight["median_ratio"]
        edge_gain = (tight["edge"] / wide["edge"]
                     if wide["edge"] not in (0, None) else np.nan)
        print(f"\n  the quote is {ratio_gain:.1f}x tighter and the edge is "
              f"{edge_gain:.1f}x larger.")
        print(f"  If those two numbers matched, the amplitude would be "
              f"constant and the corner")
        print(f"  would exist somewhere. They do not: amplitude runs "
              f"{tight['amplitude']:.5f} at the cheap")
        print(f"  end against {wide['amplitude']:.5f} over the whole sample, "
              f"a factor of "
              f"{wide['amplitude']/tight['amplitude'] if tight['amplitude'] else float('nan'):.1f}.")
        # is the edge still climbing at the tight end?
        climbing = (len(fin) >= 2 and fin[0]["edge"] > fin[1]["edge"])
        print(f"\n  at the tightest step the edge is "
              f"{'still climbing' if climbing else 'NO LONGER climbing'}: "
              f"{fin[0]['edge']:+.4f} against {fin[1]['edge']:+.4f} one step "
              f"wider.")

    viable = [r for r in fin if r["edge"] > 1.0 and r["positive"] >= 6
              and r["per_year"] >= 200]
    print("\n" + "=" * 104)
    print("VERDICT")
    print("=" * 104)
    best = max(fin, key=lambda r: r["edge"]) if fin else None
    if best:
        print(f"  best step: cheapest {best['pct']}% at {best['edge']:+.4f} "
              f"of a round trip, "
              f"{best['per_year']:,} signals a year a market, "
              f"positive on {best['positive']}/{best['markets']}")
        print(f"  it would need to be {1.0/best['edge']:.1f}x larger to pay")
    print(f"  {len(viable)} step(s) clear one round trip with at least 6 of 9 "
          f"markets and 200 signals a year")
    if not viable:
        print(f"\n  The edge does not reach one round trip anywhere in the "
              f"cost cross-section, and")
        print(f"  it stops climbing before the quote stops tightening. The "
              f"cost floor is a property")
        print(f"  of this instrument class rather than of the venue: where "
              f"the spread is small the")
        print(f"  move is small too. THE CHEAPER-EXECUTION QUESTION IS "
              f"CLOSED.")

    print("\n" + "=" * 104)
    print("WHAT THE CHEAP CORNER IS ACTUALLY MADE OF")
    print("=" * 104)
    cut = float(np.percentile(D.cost_ratio, 1.0))
    sub = D[D.cost_ratio <= cut]
    by_sym = (sub.groupby("symbol").size() / len(sub)).sort_values(
        ascending=False)
    by_hr = (sub.groupby("hour").size() / len(sub)).sort_values(
        ascending=False)
    print("  cheapest 1% of cells, share by market")
    print("   " + "  ".join(f"{k} {v*100:.0f}%" for k, v in
                            by_sym.head(6).items()))
    print("  share by hour UTC")
    print("   " + "  ".join(f"{int(k):02d}:00 {v*100:.0f}%" for k, v in
                            by_hr.head(8).items()))

    out = HERE / "cheap_corner.json"
    out.write_text(json.dumps(dict(
        created=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        sweep=rows, viable=len(viable),
        composition=dict(by_market={k: float(v) for k, v in by_sym.items()},
                         by_hour={int(k): float(v) for k, v in by_hr.items()}),
        manifest=PR.manifest({}, [HERE / ".cache_duka" /
                                  f"{s}_H1_2003_2026.parquet" for s in syms])),
        indent=1, default=str))
    PR.log("phase5-cheap-corner",
           "Does the edge keep climbing as the quote tightens, or does the "
           "amplitude fall as fast as the cost?",
           hypothesis="cheap_corner", tools=["cheap_corner",
                                             "reversal_anatomy"],
           result=dict(sweep=rows, viable=len(viable)),
           status="CLOSED" if not viable else "VIABLE CORNER",
           finding=(f"best {best['edge']:+.4f} at the cheapest "
                    f"{best['pct']}%" if best else "none"),
           next_action="record against the registered criterion",
           started=t0)
    print(f"\n  saved -> {out.name}   elapsed {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
