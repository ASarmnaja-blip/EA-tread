#!/usr/bin/env python3
"""How big would this have to be? Ask before writing the backtest.

WHAT THIS RUN LEARNED THAT IS WORTH KEEPING

  837 hypotheses were tested without anyone knowing how large an effect had to
  be to matter. Every one of them could have been screened in a minute.

  The arithmetic is not subtle. A trade must clear its own cost:

      amplitude  >  (1 + swap_per_night * nights) * (spread / ATR)

  where amplitude is the predictable move as a fraction of ATR. Everything
  else - win rate, sign accuracy, R multiple - is that inequality written in a
  different unit, and this file converts between them so the requirement can
  be checked against whatever the idea is naturally expressed in.

THE NUMBERS ON THE RIGHT-HAND SIDE ARE MEASURED, NOT ASSUMED

  spread / ATR    0.1354 across ten markets on H1, from reversal_anatomy.
                  0.0183 in the cheapest decile of market-hour-year cells.
                  0.0068 in the cheapest 1%, which is 62% EURUSD.
  swap            1.2616 spreads per night for gold long, from the live
                  account spec. The short side is not in this repository.

THE NUMBER ON THE LEFT IS ALSO MEASURED, AND IT IS THE POINT

  The unconditional one-hour reversal has an amplitude of 0.0152 ATR. That is
  the largest directional effect this project has established on any horizon
  after twenty-two years, ten markets and 1,677 hypotheses. Conditioning
  states ranged from 0.0039 to 0.0239 ATR and none survived a fresh market.

  So when this file says an idea needs 0.12 ATR, it is saying it needs to be
  eight times larger than anything found here. That is not a prediction that
  it cannot exist. It is the size of the claim being made, stated before the
  work rather than discovered after it.

WHAT IT DELIBERATELY WILL NOT DO

  Say whether an idea is true. It answers one question - how big would it have
  to be - and a requirement that looks reachable is permission to go and
  measure, never evidence of anything.
"""
import argparse
import json
import math
import pathlib
import sys

import numpy as np

HERE = pathlib.Path(__file__).parent
sys.path.insert(0, str(HERE))

# every constant here is measured in this repository and cited to the file
MEASURED = {
    "spread_over_atr_h1": (0.1354, "reversal_anatomy, ten markets"),
    "spread_over_atr_cheap_decile": (0.0183, "reversal_anatomy, decile 0"),
    "spread_over_atr_cheapest_1pct": (0.0068, "cheap_corner, 62% EURUSD"),
    "gold_swap_spreads_per_night": (1.2616, "live account spec, long side"),
    "unconditional_amplitude_atr": (0.01517, "reversal_anatomy"),
    "best_conditioned_amplitude_atr": (0.0239, "reversal_anatomy, dear end"),
    "mean_abs_move_1bar_atr": (0.60, "typical |close-open| over one H1 bar"),
    "passive_adverse_selection_round_trips": (
        7.3033, "passive_execution, resting order at 0.25 ATR"),
}

# cost ratios by timeframe, measured in financing_closure
BY_TF = {"M15": 0.175, "H1": 0.1354, "H4": 0.063, "D1": 0.028, "W1": 0.032}


def required_amplitude(cost_ratio, nights=0.0, swap=0.0, passive=False):
    """The predictable move, as a fraction of ATR, that just breaks even.

    passive=True sets the round trip to zero, which is the upper bound a
    resting order could reach. It is charged nothing for adverse selection,
    and passive_execution measured that at -7.3 round trips - so the passive
    figure here is a floor on the requirement, not a realistic one."""
    round_trip = 0.0 if passive else 1.0
    return (round_trip + swap * nights) * cost_ratio


def as_sign_accuracy(amplitude, mean_move=None):
    """Amplitude expressed as the share of moves called correctly.

    amplitude = (2p - 1) * E|move|, so p = 0.5 + amplitude / (2 E|move|).
    Returns None when the requirement is impossible - an amplitude above the
    mean absolute move cannot be reached at any win rate, because being right
    every single time still only earns E|move|."""
    m = mean_move or MEASURED["mean_abs_move_1bar_atr"][0]
    p = 0.5 + amplitude / (2 * m)
    return p if p < 1.0 else None


def as_win_rate(amplitude, payoff=1.0, mean_move=None):
    """Win rate needed at a given payoff ratio, paying the round trip."""
    m = mean_move or MEASURED["mean_abs_move_1bar_atr"][0]
    win, loss = payoff * m, m
    tot = win + loss
    return (amplitude + loss) / tot if tot > 0 else np.nan


def verdict(required, available):
    if not np.isfinite(required) or required <= 0:
        return "UNDEFINED"
    r = required / available
    if r <= 1.0:
        return f"REACHABLE - needs {r:.1f}x the largest effect measured here"
    if r <= 3.0:
        return f"AMBITIOUS - needs {r:.1f}x the largest effect measured here"
    return f"IMPLAUSIBLE - needs {r:.1f}x the largest effect measured here"


def screen(cost_ratio, nights, swap, label, available=None):
    av = available or MEASURED["unconditional_amplitude_atr"][0]
    rows = []
    req = required_amplitude(cost_ratio, nights, swap, passive=False)
    rows.append(dict(label=label, mode="crossing the spread",
                     cost_ratio=cost_ratio, nights=nights, swap=swap,
                     required_amplitude_atr=req,
                     required_sign_accuracy=as_sign_accuracy(req),
                     required_win_rate_1to1=as_win_rate(req, 1.0),
                     required_win_rate_2to1=as_win_rate(req, 2.0),
                     available_amplitude_atr=av,
                     multiple=req / av if av > 0 else np.nan,
                     verdict=verdict(req, av)))
    # A resting order pays no spread, so the amplitude requirement collapses
    # to whatever the carry costs - which is zero intraday. Reporting that as
    # "needs 0.0000 ATR, UNDEFINED" is arithmetically right and useless: the
    # binding constraint is no longer the spread, it is adverse selection, and
    # that was measured rather than left as a caveat.
    adv = MEASURED["passive_adverse_selection_round_trips"][0]
    carry = required_amplitude(cost_ratio, nights, swap, passive=True)
    rows.append(dict(label=label, mode="resting order", cost_ratio=cost_ratio,
                     nights=nights, swap=swap,
                     required_amplitude_atr=carry,
                     adverse_selection_round_trips=adv,
                     required_amplitude_incl_adverse=(carry
                                                      + adv * cost_ratio),
                     available_amplitude_atr=av,
                     multiple=(carry + adv * cost_ratio) / av if av > 0
                     else np.nan,
                     verdict=verdict(carry + adv * cost_ratio, av)))
    return rows


def main():
    ap = argparse.ArgumentParser(
        description="How large would an effect have to be to pay for itself?")
    ap.add_argument("--timeframe", default="H1",
                    help=f"one of {', '.join(BY_TF)} or a spread/ATR number")
    ap.add_argument("--nights", type=float, default=0.0,
                    help="nights held through a rollover")
    ap.add_argument("--swap", type=float, default=None,
                    help="swap in spreads per night (default: gold long)")
    ap.add_argument("--cheap", action="store_true",
                    help="use the cheapest decile's cost ratio instead")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    try:
        cr = float(a.timeframe)
        label = f"spread/ATR {cr}"
    except ValueError:
        if a.cheap:
            cr = MEASURED["spread_over_atr_cheap_decile"][0]
            label = f"{a.timeframe}, cheapest decile"
        else:
            cr = BY_TF.get(a.timeframe.upper())
            label = a.timeframe.upper()
        if cr is None:
            print(f"  unknown timeframe {a.timeframe}; "
                  f"known: {', '.join(BY_TF)}")
            return
    swap = (a.swap if a.swap is not None
            else MEASURED["gold_swap_spreads_per_night"][0])

    rows = screen(cr, a.nights, swap, label)
    if a.json:
        print(json.dumps(rows, indent=1, default=str))
        return

    print("FEASIBILITY - how big would it have to be?")
    print("=" * 92)
    print(__doc__.split("THE NUMBERS ON THE RIGHT-HAND SIDE")[0]
          .split("WHAT THIS RUN LEARNED THAT IS WORTH KEEPING")[1])
    print(f"  {label}:  spread/ATR {cr:.4f}, "
          f"{a.nights:g} night(s) at {swap:g} spreads each\n")

    av = MEASURED["unconditional_amplitude_atr"][0]
    for r in rows:
        print(f"  {r['mode']}")
        if r["mode"] == "crossing the spread":
            print(f"    needs a predictable move of "
                  f"{r['required_amplitude_atr']:.4f} ATR")
            sa = r["required_sign_accuracy"]
            print(f"    which is a sign accuracy of "
                  + (f"{sa*100:.2f}%" if sa else
                     "OVER 100% - unreachable at any win rate, because being "
                     "right every time still only earns the mean move"))
            print(f"    or a win rate of "
                  f"{r['required_win_rate_1to1']*100:.2f}% at 1:1, "
                  f"{r['required_win_rate_2to1']*100:.2f}% at 2:1")
        else:
            print(f"    pays no spread, so the move needed to cover CARRY "
                  f"alone is {r['required_amplitude_atr']:.4f} ATR")
            print(f"    but a resting order fills when the market is coming "
                  f"at it, and that")
            print(f"    adverse selection was measured at "
                  f"{r['adverse_selection_round_trips']:.2f} round trips - so "
                  f"the real")
            print(f"    requirement is "
                  f"{r['required_amplitude_incl_adverse']:.4f} ATR, WORSE "
                  f"than crossing")
        print(f"    {r['verdict']}")
        print()

    print("=" * 92)
    print("WHAT THIS MARKET ACTUALLY OFFERS, MEASURED")
    print("=" * 92)
    for k, (v, src) in MEASURED.items():
        print(f"  {k:<36}{v:>10.4f}   {src}")
    print(f"\n  The largest directional amplitude established anywhere in this")
    print(f"  project is {av:.4f} ATR, after twenty-two years, ten markets and")
    print(f"  1,677 hypotheses. Every conditioned state that beat it died on a")
    print(f"  market that had no part in producing it.")
    print(f"\n  A requirement that looks reachable is permission to go and")
    print(f"  measure. It is not evidence of anything.")


if __name__ == "__main__":
    main()
