#!/usr/bin/env python3
"""Why a setup died, named - so that a hundred deaths become a direction.

THE POINT OF NAMING A FAILURE

  A search that returns "nothing worked" has produced one bit. A search that
  returns "of 200 hypotheses, 118 died of activity selection, 41 of cost, 9 of
  intrabar ambiguity and 6 were never measurable" has produced a research
  plan: the measurement layer that decides 118 outcomes is the one worth
  rebuilding, and the one that decides 6 is not.

  This is the reason the run does not stop at a rejection. The rejection is
  the cheap part; the diagnosis is the output.

THE RULE THIS ENFORCES

  A failure code is assigned from MEASURED quantities, never from a reading of
  the result. "It looked like overfitting" is not a code. Each code below
  names the specific number that triggers it and the threshold, and the
  classifier returns every code that fires rather than the first, because a
  setup that is both cost-dominated and undersized is both.

WHAT THE CODES DELIBERATELY DO NOT INCLUDE

  There is no code for "not profitable". Profitability is not a failure mode,
  it is the absence of one; a setup with no directional skill and no cost
  problem and a large sample has failed as NO_DIRECTIONAL_SKILL, which is a
  statement about the market. Folding that into a PnL verdict would put the
  single most misleading number in the project at the centre of its own
  diagnosis.
"""
import math

import numpy as np

# ------------------------------------------------------------------------
# code -> (what it means, what number decides it)
CODES = {
    "NO_DIRECTIONAL_SKILL": (
        "Skill against the strongest control reached is indistinguishable "
        "from zero. The setup may still select good moments; it does not "
        "know which way.",
        "|t| of skill vs C7 below 2.0 with an adequate sample"),
    "ACTIVITY_SELECTION": (
        "Skill present against a timing control and gone once the signal "
        "bar's own true range is matched. The rule knows when something is "
        "happening, not what.",
        "skill vs C1 significant, |skill vs C3| < 40% of it"),
    "VOLATILITY_SELECTION": (
        "Skill survives activity matching and dies on ambient volatility. "
        "The rule is a volatility-regime filter.",
        "|skill vs C2| < 40% of skill vs C1, and C3 retains more than C2"),
    "SESSION_SELECTION": (
        "Skill is an hour-of-day effect. It dies when the control is drawn "
        "from the same session.",
        "|skill vs C4| < 40% of skill vs C1"),
    "REGIME_SELECTION_ONLY": (
        "Skill survives volatility, activity and session and dies on trend "
        "state. The rule is a regime detector with no edge inside a regime.",
        "|skill vs C6| < 40% of |skill vs C5|"),
    "COST_DOMINATED": (
        "Skill is real at zero cost and smaller than the spread it must pay. "
        "An information finding, not a trading one.",
        "zero-cost skill positive, net expectancy negative, "
        "cost > 3x the measured skill"),
    "BRACKET_BIAS": (
        "The exit design accounts for most of the measured expectancy. The "
        "number describes the stop and target, not the entry.",
        "|control expectancy| > 2x |skill|"),
    "INTRABAR_AMBIGUITY": (
        "Enough trades touch both stop and target inside one bar that the "
        "G12 tie-break decides the result.",
        "ambiguous share > 8%, or flipping the tie-break changes the sign"),
    "EXECUTION_UNRELIABLE": (
        "The result depends on fills the venue would not give: gapped "
        "entries, spreads above the gate, or stops inside typical bar noise.",
        "gap-rejected share > 15%, or dist/ATR median below 0.5"),
    "SAMPLE_TOO_SMALL": (
        "Too few trades for the standard error to mean anything at the floor "
        "the hypothesis count implies.",
        "n < 200, or the floor implies a detectable effect larger than any "
        "plausible edge"),
    "CROSS_MARKET_INSTABILITY": (
        "Works on some markets and not others in a way a single mechanism "
        "does not explain.",
        "positive on fewer than 6 of 9, or leave-one-out t swings by > 50%"),
    "CROSS_PERIOD_INSTABILITY": (
        "Concentrated in one era. The mechanism, if any, is not standing.",
        "one period contributes > 60% of total skill, or sign flips "
        "between halves"),
    "PARAMETER_FRAGILITY": (
        "A sharp optimum rather than a plateau. Neighbouring parameters lose "
        "most of the effect.",
        "mean skill of the immediate neighbourhood < 50% of the peak"),
    "FEED_INVALID": (
        "The data underneath cannot support the measurement: missing bars, "
        "synthetic flat quotes, a venue change mid-sample.",
        "coverage < 90% of expected bars, or a structural break in spread"),
    "CONTROL_TOO_WEAK": (
        "The strongest control reached does not hold constant something the "
        "rule plainly selects on.",
        "the rule's distribution over an unmatched feature differs from the "
        "control's by TV > 0.15"),
    "REDUNDANT_SIGNAL": (
        "Not a distinct hypothesis - its trades overlap an existing one "
        "enough that it is the same bet.",
        "Jaccard overlap of entry bars > 0.7 with an already-tested setup"),
    "TIMEFRAME_INAPPROPRIATE": (
        "The horizon cannot pay its own costs regardless of skill.",
        "spread / median true range on that timeframe > 0.33"),
    "MEASUREMENT_INCONSISTENT": (
        "Two measurements of the same thing disagree, so neither can be "
        "read until the disagreement is resolved.",
        "a repeat under a changed nuisance parameter moves skill by more "
        "than its own standard error x3"),
    "UNKNOWN_FAILURE": (
        "Died without matching any named pattern. Every one of these is a "
        "gap in this taxonomy and is listed individually rather than "
        "counted.",
        "no other code fired"),
}

RETENTION = 0.40      # "most of it is gone" - fixed here, not per-setup
SIG_T = 2.0


def _ret(a, b):
    """|b| as a share of |a|, with the sign-flip case treated as total loss."""
    if a is None or b is None or not np.isfinite(a) or not np.isfinite(b):
        return np.nan
    if abs(a) < 1e-9:
        return np.nan
    if np.sign(a) != np.sign(b):
        return 0.0
    return abs(b) / abs(a)


def classify(m):
    """Return every code that fires, from a dict of MEASURED quantities.

    Expected keys, all optional - a code whose inputs are absent simply does
    not fire, and the absence is reported so that a diagnosis built on missing
    measurements is not mistaken for a clean one:

      skill_c1..skill_c7, t_c7, n_trades, control_E, zero_cost_skill,
      net_expectancy, cost_per_trade, ambiguous_share, tie_break_flips_sign,
      gap_rejected_share, dist_over_atr_median, markets_positive,
      markets_total, loo_t_swing, period_concentration, period_sign_flip,
      neighbourhood_ratio, coverage, spread_over_range, max_unmatched_tv,
      max_overlap_jaccard, repeat_shift_in_se
    """
    out, missing = [], []

    def g(k):
        v = m.get(k)
        if v is None:
            missing.append(k)
            return None
        return v

    c1, t7 = m.get("skill_c1"), m.get("t_c7")
    n = m.get("n_trades")

    # --- sample and feed come first: they invalidate everything after ------
    if n is not None and n < 200:
        out.append("SAMPLE_TOO_SMALL")
    if m.get("coverage") is not None and m["coverage"] < 0.90:
        out.append("FEED_INVALID")
    if (m.get("spread_over_range") is not None
            and m["spread_over_range"] > 0.33):
        out.append("TIMEFRAME_INAPPROPRIATE")

    # --- is it a distinct hypothesis at all -------------------------------
    if (m.get("max_overlap_jaccard") is not None
            and m["max_overlap_jaccard"] > 0.70):
        out.append("REDUNDANT_SIGNAL")

    # --- is the measurement usable ----------------------------------------
    if (m.get("ambiguous_share") is not None and m["ambiguous_share"] > 0.08) \
            or m.get("tie_break_flips_sign"):
        out.append("INTRABAR_AMBIGUITY")
    if (m.get("gap_rejected_share") is not None
            and m["gap_rejected_share"] > 0.15) or \
       (m.get("dist_over_atr_median") is not None
            and m["dist_over_atr_median"] < 0.5):
        out.append("EXECUTION_UNRELIABLE")
    if (m.get("max_unmatched_tv") is not None
            and m["max_unmatched_tv"] > 0.15):
        out.append("CONTROL_TOO_WEAK")
    if (m.get("repeat_shift_in_se") is not None
            and m["repeat_shift_in_se"] > 3.0):
        out.append("MEASUREMENT_INCONSISTENT")
    if (m.get("control_E") is not None and m.get("skill_c7") is not None
            and abs(m["skill_c7"]) > 1e-9
            and abs(m["control_E"]) > 2 * abs(m["skill_c7"])):
        out.append("BRACKET_BIAS")

    # --- what kind of selection, if the C1 skill was real to begin with ---
    c1_real = c1 is not None and m.get("t_c1") is not None \
        and abs(m["t_c1"]) >= SIG_T
    if c1_real:
        r3 = _ret(c1, m.get("skill_c3"))
        r2 = _ret(c1, m.get("skill_c2"))
        r4 = _ret(c1, m.get("skill_c4"))
        r6 = _ret(m.get("skill_c5"), m.get("skill_c6"))
        if np.isfinite(r3) and r3 < RETENTION:
            out.append("ACTIVITY_SELECTION")
        if np.isfinite(r2) and r2 < RETENTION and \
                (not np.isfinite(r3) or r3 > r2):
            out.append("VOLATILITY_SELECTION")
        if np.isfinite(r4) and r4 < RETENTION:
            out.append("SESSION_SELECTION")
        if np.isfinite(r6) and r6 < RETENTION:
            out.append("REGIME_SELECTION_ONLY")

    # --- did direction survive at all -------------------------------------
    if t7 is not None and abs(t7) < SIG_T and (n is None or n >= 200):
        out.append("NO_DIRECTIONAL_SKILL")

    # --- economics, only once skill is established ------------------------
    zc, net, cost = (m.get("zero_cost_skill"), m.get("net_expectancy"),
                     m.get("cost_per_trade"))
    if (zc is not None and net is not None and cost is not None
            and zc > 0 and net < 0 and cost > 3 * zc):
        out.append("COST_DOMINATED")

    # --- stability --------------------------------------------------------
    mp, mt = m.get("markets_positive"), m.get("markets_total")
    if mp is not None and mt:
        if mp / mt < 6 / 9:
            out.append("CROSS_MARKET_INSTABILITY")
    if m.get("loo_t_swing") is not None and m["loo_t_swing"] > 0.50:
        if "CROSS_MARKET_INSTABILITY" not in out:
            out.append("CROSS_MARKET_INSTABILITY")
    if (m.get("period_concentration") is not None
            and m["period_concentration"] > 0.60) or \
            m.get("period_sign_flip"):
        out.append("CROSS_PERIOD_INSTABILITY")
    if (m.get("neighbourhood_ratio") is not None
            and m["neighbourhood_ratio"] < 0.50):
        out.append("PARAMETER_FRAGILITY")

    if not out:
        out.append("UNKNOWN_FAILURE")
    # order by the sequence in CODES so aggregation is stable
    order = list(CODES)
    return dict(codes=sorted(set(out), key=order.index),
                missing_inputs=sorted(set(missing)))


def aggregate(classifications):
    """Failure distribution over many setups - the thing that decides what to
    upgrade next. Counts every code a setup earned, not just a primary."""
    tally = {}
    for c in classifications:
        for code in c.get("codes", ()):
            tally[code] = tally.get(code, 0) + 1
    n = max(len(classifications), 1)
    return sorted(({"code": k, "n": v, "share": v / n}
                   for k, v in tally.items()),
                  key=lambda r: -r["n"])


def upgrade_target(dist, exclude=("SAMPLE_TOO_SMALL", "UNKNOWN_FAILURE")):
    """Which measurement layer the failure distribution says to rebuild.

    The mapping is fixed here rather than chosen per run, because choosing it
    after seeing which setups had the best PnL is the mechanism this whole
    structure exists to prevent."""
    layer = {
        "ACTIVITY_SELECTION": "controls + activity layer",
        "VOLATILITY_SELECTION": "controls + regime layer",
        "SESSION_SELECTION": "controls + session/liquidity layer",
        "REGIME_SELECTION_ONLY": "regime layer",
        "COST_DOMINATED": "tradability layer",
        "BRACKET_BIAS": "execution layer (exit design)",
        "INTRABAR_AMBIGUITY": "execution layer (intrabar resolution)",
        "EXECUTION_UNRELIABLE": "execution reliability layer",
        "CROSS_MARKET_INSTABILITY": "representation (mechanism, not fit)",
        "CROSS_PERIOD_INSTABILITY": "representation (mechanism, not fit)",
        "PARAMETER_FRAGILITY": "representation (state machine over threshold)",
        "FEED_INVALID": "data layer",
        "CONTROL_TOO_WEAK": "controls",
        "REDUNDANT_SIGNAL": "discovery dedup",
        "TIMEFRAME_INAPPROPRIATE": "tradability layer",
        "MEASUREMENT_INCONSISTENT": "measurement reliability layer",
        "NO_DIRECTIONAL_SKILL": "hypothesis generation, not measurement",
    }
    ranked = [r for r in dist if r["code"] not in exclude]
    return [dict(code=r["code"], n=r["n"], share=r["share"],
                 upgrade=layer.get(r["code"], "unmapped"))
            for r in ranked[:3]]


if __name__ == "__main__":
    print("FAILURE CODES - each triggered by a measured number, never a "
          "reading")
    print("=" * 96)
    for k, (what, when) in CODES.items():
        print(f"\n  {k}")
        print(f"    {what}")
        print(f"    fires when: {when}")
