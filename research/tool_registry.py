#!/usr/bin/env python3
"""What exists, what question each thing answers, and what it is validated on.

WHY A REGISTRY RATHER THAN A README

  This repository holds 120 scripts. Most were written to answer one question
  and then left, and the cost of that is not clutter - it is that the next
  question gets a new script instead of an existing measurement, and the two
  disagree without anyone noticing. Two of this run's largest findings were
  exactly that: a control whose geometry nobody had checked against the rule's,
  and an edge metric that two files computed differently.

  So each entry records what the tool ANSWERS, not what it does, and what it
  is VALIDATED against - which for a measurement is never strategy returns.

THE FIELDS AND WHY EACH ONE IS THERE

  answers       the question, phrased as a question. A tool that cannot have
                one written for it is a script, not a tool.
  inputs        what it needs, so the selector can tell whether it can run.
  outputs       the named quantities other tools may depend on.
  assumptions   what has to be true for its output to mean anything. This is
                the field that would have caught the geometry defect.
  validated_on  the fixture or reproduction that establishes correctness.
                For a measurement this is a synthetic process with a known
                answer or an exact reproduction of an existing engine. It is
                never a backtest result.
  status        VALIDATED, PROVISIONAL, or SUPERSEDED. Superseded entries stay
                so that an old number can be traced to the tool that made it.
  version       bumped when the OUTPUT changes, not when the code is edited.
"""
import json
import pathlib
import subprocess
import sys

HERE = pathlib.Path(__file__).parent

REGISTRY = {
    # ------------------------------------------------------ measurement ---
    "measure_layers": dict(
        version="2.0", status="VALIDATED",
        answers="What does this market cost to trade, how much is happening, "
                "where does price sit, what regime is it in, could a level "
                "have been traded, and can any of it be trusted?",
        inputs=["bid/ask OHLC frame", "timeframe in minutes"],
        outputs=["tradability.cost_over_range", "tradability.h_star_nights",
                 "activity.volume_state", "structure.by_range_decile",
                 "regime.vr_vs_cost_corr", "execution_reliability.share_"
                 "two_sided_bars", "measurement_reliability.veto"],
        assumptions=["ATR windows are wall-clock hours, so a figure means the "
                     "same thing on M1 and H4",
                     "quality is coverage x precision x resolution and "
                     "contains no return column anywhere",
                     "the reliability layer can veto the other five"],
        validated_on="its own tradability coverage found the 29% of bars "
                     "where the venue was not quoting, which no inspection "
                     "of the loader had caught",
        cost="about 11s per market on H1"),

    "controls": dict(
        version="1.1", status="VALIDATED",
        answers="Is this rule's result direction, or is it timing, activity, "
                "volatility, session, regime or position in range?",
        inputs=["prepped frame", "signal direction vector",
                "invalidation vector"],
        outputs=["matched direction vector", "matched invalidation vector",
                 "match_rate", "placement_rate", "causal sketch"],
        assumptions=["every control inherits the rule's own dist/ATR ratio, "
                     "so the two books are the same instrument",
                     "matching on any post-signal variable raises rather "
                     "than warns",
                     "a cell with no donors relaxes by dropping the least "
                     "important dim, and the relaxation is reported"],
        validated_on="test_controls.py, 14 fixtures on synthetic processes "
                     "with known answers - real information survives to C7 at "
                     "t +14.5, a clock artifact dies at C4 and survives at "
                     "C7, geometry gap 0.0% against random_like's 73%",
        cost="1.9s for all eight levels on a 12,500-signal book"),

    "engine_fast": dict(
        version="1.0", status="VALIDATED",
        answers="What would this signal have returned through the project's "
                "standard bracket?",
        inputs=["prepped frame", "direction vector", "invalidation vector",
                "tick size"],
        outputs=["R per trade", "signal bar index", "holding period"],
        assumptions=["identical to bracket_bias.engine, which reproduces "
                     "run_e01 trade for trade",
                     "G12 resolves a bar touching both levels as a stop"],
        validated_on="test_engine_fast.py, bit-identical on 180 books across "
                     "9 markets, 4 families and 5 exit variants",
        cost="10x faster than the reference"),

    "discovery.score": dict(
        version="2.0", status="VALIDATED",
        answers="What is this signal worth in units of what it costs to act "
                "on?",
        inputs=["prepped frame", "signal bars", "directions", "horizon"],
        outputs=["edge (ratio of means)", "edge_mean_ratio", "sign_rate",
                 "top_year_share"],
        assumptions=["the ratio of means is the economics; the mean of ratios "
                     "sizes inversely to each trade's own spread and reads "
                     "1.3x to 2.3x higher",
                     "the spread is taken at the entry bar's open, which is "
                     "the first quote a trader would face",
                     "pooling across markets would add gold points to pip "
                     "points, so aggregation is per-market then equal weight"],
        validated_on="version 1.0 used the mean of ratios and produced five "
                     "apparent clears in the pilot; correcting it removed all "
                     "five, which is the reproduction that establishes the "
                     "difference matters",
        cost="negligible"),

    "feasibility": dict(
        version="1.0", status="VALIDATED",
        answers="How large would this effect have to be to pay for itself, "
                "expressed in whatever unit the idea is stated in?",
        inputs=["timeframe or a spread/ATR ratio", "nights held", "swap"],
        outputs=["required amplitude in ATR", "required sign accuracy",
                 "required win rate at 1:1 and 2:1", "multiple of the "
                 "largest effect measured here"],
        assumptions=["every constant is measured in this repository and "
                     "cited to the file that measured it",
                     "a resting order's requirement includes the measured "
                     "adverse selection of 7.30 round trips, because without "
                     "it the answer is a meaningless zero",
                     "it answers how big, never whether it is true"],
        validated_on="reproduces the figures the run derived the hard way - "
                     "61.28% sign accuracy at H1 against the 59.91% measured "
                     "in reversal_mechanism, and 8.9x against the venue "
                     "requirement computed in reversal_anatomy",
        cost="instant"),

    # ----------------------------------------------------------- discipline
    "change_ledger": dict(
        version="1.1", status="VALIDATED",
        answers="How many hypotheses has this project spent, and does this "
                "one clear the bar that count implies?",
        inputs=["registered id, reason, change, criterion, margin, period, "
                "sweep size"],
        outputs=["cumulative k", "floor", "verdict"],
        assumptions=["the criterion is written before the result exists and "
                     "read from disk afterwards",
                     "k never resets",
                     "the floor is the exact expected maximum of k trials at "
                     "the measured trial dispersion of 1.475, not the "
                     "asymptote"],
        validated_on="test_change_ledger.py; the floor correction is checked "
                     "against Monte Carlo in test_overfit_stats.py",
        cost="negligible"),

    "overfit_stats": dict(
        version="1.0", status="VALIDATED",
        answers="How much of this result is the best of many tries?",
        inputs=["trial statistics", "returns", "configuration matrix"],
        outputs=["expected_max_t", "deflated_sharpe", "pbo_cscv",
                 "min_backtest_length"],
        assumptions=["no scipy; norm_ppf round-trips to 1e-16"],
        validated_on="test_overfit_stats.py, 10 calibration groups on data "
                     "with known answers; it caught three of its own test "
                     "designs being wrong",
        cost="negligible"),

    "failure_codes": dict(
        version="1.1", status="VALIDATED",
        answers="Why did this hypothesis die, and what does the distribution "
                "of deaths say to rebuild?",
        inputs=["measured quantities per hypothesis"],
        outputs=["codes", "missing_inputs", "aggregate distribution",
                 "upgrade target"],
        assumptions=["every code fires from a measured number, never a "
                     "reading of the result",
                     "there is no code for 'not profitable'",
                     "the aggregate distribution chooses what to upgrade, "
                     "not the best PnL"],
        validated_on="BELOW_MULTIPLICITY_FLOOR was added because the pilot's "
                     "survivors returned UNKNOWN_FAILURE, which is what "
                     "UNKNOWN is for - a gap in the taxonomy",
        cost="negligible"),

    "provenance": dict(
        version="1.0", status="VALIDATED",
        answers="What code, what data and what parameters produced this "
                "number?",
        inputs=["config dict", "data paths"],
        outputs=["git commit and cleanliness", "sha256 per input file",
                 "config digest", "append-only progress log"],
        assumptions=["a dirty tree makes the commit a lie and is recorded as "
                     "such",
                     "the file hash is memoised on mtime and size, not on the "
                     "name, so a re-download shows up"],
        validated_on="used by every phase; the log is the run's own record",
        cost="negligible"),

    # ------------------------------------------------------------ findings
    "timeframe_ratio": dict(
        version="2.0", status="VALIDATED",
        answers="Does the ratio of predictable move to spread ever reach one, "
                "anywhere on the horizon axis?",
        inputs=["cleaned H1 frames", "minute data for the sub-hourly rows"],
        outputs=["edge by timeframe", "scaling exponent",
                 "break-even financing rate"],
        assumptions=["H1 aggregates exactly into H4 and D1; nothing is "
                     "interpolated",
                     "the spread at entry is the entry bar's own first quote, "
                     "not a daily average"],
        validated_on="the exponent was predicted at 0.50 before the run; "
                     "version 1 measured 0.536 on the mean of ratios and "
                     "version 2 measures 0.233 on the ratio of means",
        cost="10s"),

    "reversal_mechanism": dict(
        version="1.0", status="VALIDATED",
        answers="Is the short-horizon sign edge a conditional signal, a "
                "property of the price series, or microstructure?",
        inputs=["cleaned H1 frames"],
        outputs=["unconditional fade rate", "conditional add", "lag retention",
                 "breakeven win rate paying one spread"],
        assumptions=["the lag test shifts the SIGNAL, not the entry, so the "
                     "cost and horizon are unchanged"],
        validated_on="the mirror-image structure is its own check - fading "
                     "wins and following loses by comparable amounts on every "
                     "market, which the value-area pair failed",
        cost="9s"),

    # ---------------------------------------------------------- superseded
    "bracket_bias.random_like": dict(
        version="0", status="SUPERSEDED",
        answers="(intended) What would a random-timing control have returned?",
        inputs=["prepped frame", "direction vector"],
        outputs=["control direction vector", "control invalidation vector"],
        assumptions=["INVALID: takes the random bar's own high or low as the "
                     "invalidation level, so its stop sits a third as far "
                     "from entry as the rule's while R divides by that "
                     "distance"],
        validated_on="engineering_audit check 8 measured the defect: dist/ATR "
                     "median 0.559 against the rule's 1.638",
        superseded_by="controls",
        cost="n/a"),

    "discovery.score@1.0": dict(
        version="1.0", status="SUPERSEDED",
        answers="(intended) What is this signal worth per unit of cost?",
        inputs=["as version 2"],
        outputs=["edge as the mean of move/spread ratios"],
        assumptions=["INVALID as economics: implicitly sizes inversely to "
                     "each trade's own spread"],
        validated_on="produced five apparent clears in the pilot that the "
                     "corrected metric removed",
        superseded_by="discovery.score",
        cost="n/a"),
}


# question keyword -> tools that answer it
SELECTOR = {
    "cost": ["measure_layers", "timeframe_ratio", "discovery.score"],
    "direction": ["controls", "reversal_mechanism", "discovery.score"],
    "control": ["controls"],
    "overfitting": ["overfit_stats", "change_ledger"],
    "why did it fail": ["failure_codes"],
    "execution": ["engine_fast", "measure_layers"],
    "horizon": ["timeframe_ratio", "reversal_mechanism"],
    "reproducibility": ["provenance", "change_ledger"],
}


def select(question):
    """Which existing tools answer this, so a new script is not written."""
    q = question.lower()
    hits = []
    for key, tools in SELECTOR.items():
        if key in q:
            hits.extend(tools)
    if not hits:
        for name, e in REGISTRY.items():
            if e["status"] == "SUPERSEDED":
                continue
            if any(w in e["answers"].lower() for w in q.split() if len(w) > 4):
                hits.append(name)
    seen, out = set(), []
    for h in hits:
        if h not in seen and REGISTRY.get(h, {}).get("status") != "SUPERSEDED":
            seen.add(h)
            out.append(h)
    return out


def check():
    """Every live entry must have a file and a validation statement."""
    problems = []
    for name, e in REGISTRY.items():
        if e["status"] == "SUPERSEDED":
            continue
        mod = name.split(".")[0].split("@")[0]
        if not (HERE / f"{mod}.py").exists():
            problems.append(f"{name}: no module {mod}.py")
        if not e.get("validated_on"):
            problems.append(f"{name}: no validation statement")
        if not e.get("assumptions"):
            problems.append(f"{name}: no assumptions recorded")
    return problems


def main():
    print("TOOL REGISTRY")
    print("=" * 96)
    print(__doc__.split("THE FIELDS AND WHY EACH ONE IS THERE")[1])
    live = [(k, v) for k, v in REGISTRY.items() if v["status"] != "SUPERSEDED"]
    dead = [(k, v) for k, v in REGISTRY.items() if v["status"] == "SUPERSEDED"]
    for k, v in live:
        print(f"\n  {k}  v{v['version']}  [{v['status']}]")
        print(f"    answers      {v['answers']}")
        print(f"    validated on {v['validated_on']}")
        for a in v["assumptions"]:
            print(f"    assumes      {a}")
    print("\n" + "=" * 96)
    print("SUPERSEDED - kept so an old number can be traced to the tool that "
          "made it")
    print("=" * 96)
    for k, v in dead:
        print(f"\n  {k}  ->  {v['superseded_by']}")
        print(f"    {v['assumptions'][0]}")
    problems = check()
    print("\n" + "=" * 96)
    print(f"  {len(live)} live tools, {len(dead)} superseded, "
          f"{len(problems)} registry problems")
    for p in problems:
        print(f"    {p}")
    (HERE / "tool_registry.json").write_text(
        json.dumps(REGISTRY, indent=1, default=str))
    if problems:
        sys.exit(1)


if __name__ == "__main__":
    main()
