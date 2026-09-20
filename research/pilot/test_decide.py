"""Executable tests for the decision assembler."""
from __future__ import annotations

import sys
from dataclasses import fields
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import decide as D
import news as N
import regime as RG

_pass, _fail, _msgs = 0, 0, []


def check(ok, tid, what):
    global _pass, _fail
    if ok:
        _pass += 1
        print(f"  PASS  {tid:6s} {what}")
    else:
        _fail += 1
        _msgs.append(f"{tid}  {what}")
        print(f"  FAIL  {tid:6s} {what}")


GOOD_REGIME = RG.RegimeScore(82.0, RG.STABLE, 4, ["cross_asset_correlation"],
                             {"atr_level": 80.0}, "4 components")
CAND = D.Candidate(id="S1", direction=1, entry_low=4000.0, entry_high=4001.0,
                   stop=3990.0, exit_logic="2R target, 24-bar time stop",
                   invalidation=3995.0,
                   invalidation_rule="close back inside the 20-bar range",
                   evidence="close above the 20-bar high",
                   premise="resting stops above the range are triggered")


def inputs(**kw):
    base = dict(symbol="XAUUSD", timeframe="M15", instrument_is_target=False,
                bars_ready=True, atr=6.3, regime=GOOD_REGIME, news=None,
                cost_r=0.07, cost_measured=False, confidence_calibrated=False,
                candidates=[CAND], evaluated_ids=["S1", "S2", "S3"])
    base.update(kw)
    return D.Inputs(**base)


def confirmed_news():
    a = N.Assessment(N.NEG_CONFIRM, "reaction agrees and held")
    a.tradeable = True
    return a


print("=" * 78)
print("DECISION ASSEMBLER - executable tests")
print("=" * 78)

# --- each stand-aside gate names itself --------------------------------
cases = [
    ("D1a", dict(bars_ready=False), "data not ready"),
    ("D1b", dict(atr=0.0), "volatility not measurable"),
    ("D1c", dict(regime=RG.RegimeScore(None, RG.UNKNOWN, 1, [], {}, "only 1 component")),
     "regime unreadable"),
    ("D1d", dict(cost_r=None), "cost unknown"),
    ("D1e", dict(cost_r=0.40), "exceeds the 0.25 R ceiling"),
    ("D1f", dict(news=N.Assessment(N.SWEEP_BOTH, "both extremes taken")),
     "news window unreadable"),
    ("D1g", dict(candidates=[]), "no candidate qualified"),
]
for tid, kw, needle in cases:
    d = D.decide(inputs(**kw))
    check(d.grade == D.NO_TRADE and needle in d.decision_reason and not d.tradeable,
          tid, f"{needle!r} -> NO_TRADE naming the gate")

# --- gate order: an earlier refusal wins --------------------------------
d = D.decide(inputs(bars_ready=False, atr=0.0, cost_r=None, candidates=[]))
check("data not ready" in d.decision_reason, "D2a",
      "with several gates failing, the earliest one is reported")
d = D.decide(inputs(cost_r=0.40, candidates=[]))
check("ceiling" in d.decision_reason, "D2b",
      "a cost refusal is reached before the candidate search")

# --- a refusal has to show what was examined ----------------------------
d = D.decide(inputs(candidates=[]))
check(d.evaluated == ["S1", "S2", "S3"] and "S1, S2, S3" in d.decision_reason,
      "D3a", "NO_TRADE lists the candidates that were evaluated")
d = D.decide(inputs(candidates=[], evaluated_ids=[]))
check("none" in d.decision_reason, "D3b",
      "nothing evaluated is stated as such, not left blank")

# --- caps hold, whatever else is true -----------------------------------
d = D.decide(inputs(news=confirmed_news()))
check(d.grade == D.RESEARCH_WATCH and not d.tradeable, "D4a",
      "every gate passed and confirmed news still tops out at RESEARCH WATCH")
check(len(d.caps) == 3, "D4b",
      f"all three caps are named: {d.caps}")
d = D.decide(inputs(news=confirmed_news(), instrument_is_target=True,
                    cost_measured=True, confidence_calibrated=True))
check(d.grade == D.SHADOW_CANDIDATE and not d.tradeable, "D4c",
      "even with the caps lifted the module cannot emit a tradeable signal")

grades = set()
for tgt in (True, False):
    for meas in (True, False):
        for cal in (True, False):
            r = D.decide(inputs(news=confirmed_news(), instrument_is_target=tgt,
                                cost_measured=meas, confidence_calibrated=cal))
            grades.add(r.grade)
            if not r.tradeable:
                continue
            check(False, "D5a", "a tradeable signal escaped")
check(D.PAPER not in grades and D.LIVE not in grades, "D5a",
      "no combination of inputs reaches PAPER or LIVE")

# --- the schema is complete on every path -------------------------------
required = {"symbol", "timeframe", "direction", "regime", "setup", "confidence",
            "entry_zone", "stop", "exit_logic", "risk_r", "evidence",
            "priced_in", "invalidation", "expiry", "news_risk",
            "decision_reason"}
have = {f.name for f in fields(D.Decision)}
check(required <= have, "D6a",
      f"Decision carries all sixteen required fields ({len(required)})")

paths = [D.decide(inputs(**kw)) for _, kw, _ in cases]
paths.append(D.decide(inputs(news=confirmed_news())))
check(all(p.decision_reason for p in paths), "D6b",
      "every path states a reason")
check(all(p.priced_in.startswith("NOT ASSESSED") for p in paths), "D6c",
      "priced-in is NOT ASSESSED everywhere - never estimated")
check(all(p.confidence == -1.0 for p in paths), "D6d",
      "confidence is the -1 sentinel on every path, never a number")
check(all(p.grade in D.GRADES for p in paths), "D6e",
      "every path carries a declared grade")
check(all(p.risk_r in (0.0, 1.0) for p in paths), "D6f",
      "risk is 1R by construction when a candidate exists, 0 otherwise")

# --- the signal itself is fully populated -------------------------------
d = D.decide(inputs(news=confirmed_news()))
check(d.entry_zone == (4000.0, 4001.0) and d.stop == 3990.0, "D7a",
      "entry zone and stop come through intact")
check("3995.00" in d.invalidation and "range" in d.invalidation, "D7b",
      "invalidation carries both the level and the rule")
check("no expiry policy adopted" in d.expiry, "D7c",
      "expiry says no policy is adopted rather than inventing one")
check(d.news_risk == N.NEG_CONFIRM, "D7d",
      "the news situation is carried onto the signal")
d2 = D.decide(inputs())
check(d2.news_risk.startswith("NOT ASSESSED"), "D7e",
      "with no calendar the news field says so")

print("-" * 78)
print(f"passed {_pass}, failed {_fail}")
for m in _msgs:
    print("  FAILED:", m)
sys.exit(0 if _fail == 0 else 1)
