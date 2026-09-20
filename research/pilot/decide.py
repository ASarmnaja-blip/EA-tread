"""
The decision assembler — CLAUDE.md section 6.

Takes what is known about the market right now and returns exactly one of:
a signal carrying all fifteen required fields, or NO TRADE with the reason.

Two rules shape the whole file.

**Stand-aside conditions are tested first.** Protocol v2 section 11 allows
NO TRADE as a conclusion but not as an unexamined default, so a refusal has to
name which gate refused and what had been evaluated by then. Ordering the gates
before the candidate search also means an unreadable state can never be
rescued into a trade by a later branch.

**A grade is capped by the weakest thing it rests on.** Protocol v2 section 3
puts SHADOW CANDIDATE out of reach without the real instrument and a measured
cost, and section 6 forbids a confidence number that has not been fitted to
realised outcomes. Those caps are enforced here rather than left to whoever
reads the output, so today every path tops out at RESEARCH WATCH and nothing
in this module can emit a tradeable signal.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# grades, weakest first
NO_TRADE = "NO_TRADE"
RESEARCH_WATCH = "RESEARCH_WATCH"
SHADOW_CANDIDATE = "SHADOW_CANDIDATE"
PAPER = "PAPER"
LIVE = "LIVE"
GRADES = (NO_TRADE, RESEARCH_WATCH, SHADOW_CANDIDATE, PAPER, LIVE)

COST_R_CEILING = 0.25       # cost above a quarter of R: the edge would have to
                            # be implausibly large to survive it


@dataclass
class Candidate:
    """One setup's view of the current bar. Nothing about its past results."""
    id: str
    direction: int                  # +1 long, -1 short
    entry_low: float
    entry_high: float
    stop: float
    exit_logic: str
    invalidation: float
    invalidation_rule: str
    evidence: str
    premise: str
    expiry_bars: int | None = None


@dataclass
class Inputs:
    symbol: str
    timeframe: str
    instrument_is_target: bool      # False while running on any proxy
    bars_ready: bool
    atr: float | None
    regime: object | None           # RegimeScore, or None
    news: object | None             # news.Assessment, or None
    cost_r: float | None            # cost as a fraction of R
    cost_measured: bool             # False = assumed, not measured
    confidence_calibrated: bool
    candidates: list[Candidate] = field(default_factory=list)
    evaluated_ids: list[str] = field(default_factory=list)


@dataclass
class Decision:
    # --- the fifteen fields CLAUDE.md section 6 requires ---------------
    symbol: str
    timeframe: str
    direction: int
    regime: str
    setup: str
    confidence: float               # -1.0 until fitted to realised outcomes
    entry_zone: tuple[float, float] | None
    stop: float | None
    exit_logic: str
    risk_r: float
    evidence: str
    priced_in: str
    invalidation: str
    expiry: str
    news_risk: str
    decision_reason: str
    # --- how far it may travel ----------------------------------------
    grade: str
    tradeable: bool
    evaluated: list[str] = field(default_factory=list)
    caps: list[str] = field(default_factory=list)


def _blank(inp: Inputs, reason: str, regime_label: str = "UNKNOWN") -> Decision:
    return Decision(
        symbol=inp.symbol, timeframe=inp.timeframe, direction=0,
        regime=regime_label, setup="", confidence=-1.0, entry_zone=None,
        stop=None, exit_logic="", risk_r=0.0, evidence="",
        priced_in="NOT ASSESSED: no positioning or consensus-distribution feed",
        invalidation="", expiry="",
        news_risk=(inp.news.scenario if inp.news is not None
                   else "NOT ASSESSED: no calendar feed"),
        decision_reason=reason, grade=NO_TRADE, tradeable=False,
        evaluated=list(inp.evaluated_ids))


def decide(inp: Inputs) -> Decision:
    """One bar in, one decision out."""
    rl = getattr(inp.regime, "label", "UNKNOWN")

    # ---- stand-aside gates, in a fixed order -------------------------
    if not inp.bars_ready:
        return _blank(inp, "data not ready: insufficient bar history", rl)

    if inp.atr is None or not (inp.atr > 0):
        return _blank(inp, "volatility not measurable: ATR unavailable or zero", rl)

    if inp.regime is None or getattr(inp.regime, "score", None) is None:
        why = getattr(inp.regime, "reason", "no regime score supplied")
        return _blank(inp, f"regime unreadable: {why}", rl)

    if inp.cost_r is None:
        return _blank(inp, "cost unknown: no spread available, and an unknown "
                           "cost is not a zero cost", rl)

    if inp.cost_r > COST_R_CEILING:
        return _blank(inp, f"cost {inp.cost_r:.3f} R exceeds the "
                           f"{COST_R_CEILING:.2f} R ceiling", rl)

    if inp.news is not None and not getattr(inp.news, "tradeable", False):
        return _blank(inp, f"news window unreadable: {inp.news.scenario} - "
                           f"{inp.news.reason}", rl)

    if not inp.candidates:
        ev = ", ".join(inp.evaluated_ids) if inp.evaluated_ids else "none"
        return _blank(inp, f"no candidate qualified (evaluated: {ev})", rl)

    # ---- a candidate exists; how far may it travel? -------------------
    best = inp.candidates[0]

    caps: list[str] = []
    if not inp.instrument_is_target:
        caps.append("running on a proxy instrument, not the target")
    if not inp.cost_measured:
        caps.append("cost is assumed, not measured")
    if not inp.confidence_calibrated:
        caps.append("confidence has never been fitted to realised outcomes")

    grade = RESEARCH_WATCH if caps else SHADOW_CANDIDATE
    conf = -1.0 if not inp.confidence_calibrated else -1.0

    reason = (f"{best.id}: {best.premise}"
              + ("; capped at RESEARCH WATCH because "
                 + "; ".join(caps) if caps else ""))

    return Decision(
        symbol=inp.symbol, timeframe=inp.timeframe, direction=best.direction,
        regime=rl, setup=best.id, confidence=conf,
        entry_zone=(best.entry_low, best.entry_high), stop=best.stop,
        exit_logic=best.exit_logic, risk_r=1.0, evidence=best.evidence,
        priced_in="NOT ASSESSED: no positioning or consensus-distribution feed",
        invalidation=f"{best.invalidation:.2f} - {best.invalidation_rule}",
        expiry=("no expiry policy adopted (protocol v2 s.7)"
                if best.expiry_bars in (None, -1)
                else f"{best.expiry_bars} bars"),
        news_risk=(inp.news.scenario if inp.news is not None
                   else "NOT ASSESSED: no calendar feed"),
        decision_reason=reason, grade=grade,
        # A tradeable signal needs the target instrument, a measured cost and a
        # calibrated confidence. None of those hold today, and this is the line
        # that makes that a property of the code rather than a promise.
        tradeable=False,
        evaluated=list(inp.evaluated_ids), caps=caps)
