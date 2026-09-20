"""
News decision layer — CLAUDE.md section 2.

The mandate is explicit that a release is not read as "good or bad for gold".
It sets a hypothesis; the price reaction decides whether that hypothesis is
confirmed. This module separates those two steps and refuses to collapse them.

Nothing here reads a live feed. It takes events and bars and returns a
classification, so it can be tested against cases whose answer is known.

Two inputs the mandate asks for have NO source available in this project yet:
what the market has already priced in, and positioning. They are reported as
NOT ASSESSED rather than estimated. A number invented for either would be the
fabrication section 8 forbids.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

# --- the eight situations the mandate requires a plan for --------------
POS_CONFIRM = "POSITIVE_CONFIRMED"     # gold-bullish surprise, price agrees
POS_REJECT = "POSITIVE_REJECTED"       # gold-bullish surprise, price refuses
NEG_CONFIRM = "NEGATIVE_CONFIRMED"     # gold-bearish surprise, price agrees
NEG_REJECT = "NEGATIVE_REJECTED"       # gold-bearish surprise, price refuses
IN_LINE = "IN_LINE"                    # release close to consensus
CONFLICTING = "CONFLICTING"            # simultaneous releases disagree
SWEEP_BOTH = "SWEPT_BOTH_SIDES"        # both pre-event extremes taken
NO_TRADE = "NO_TRADE"                  # conditions say stand aside

SCENARIOS = (POS_CONFIRM, POS_REJECT, NEG_CONFIRM, NEG_REJECT,
             IN_LINE, CONFLICTING, SWEEP_BOTH, NO_TRADE)

HORIZONS_MIN = (1, 5, 15, 60)          # mandate section 4


@dataclass
class Event:
    """One scheduled release.

    `higher_is_gold_negative` carries the sign convention per series: a strong
    payroll print is gold-bearish, a rising unemployment rate is gold-bullish.
    It is a property of the series, declared with the event, never inferred
    from how price happened to move.
    """
    t: int                              # epoch seconds, UTC, release time
    name: str
    importance: str = "HIGH"
    actual: float | None = None
    consensus: float | None = None
    previous: float | None = None
    previous_revised: float | None = None
    sigma: float | None = None          # historical sd of (actual - consensus)
    higher_is_gold_negative: bool = True


@dataclass
class Reaction:
    """Signed move per horizon, in ATR units, measured only AFTER the release."""
    by_horizon: dict[int, float] = field(default_factory=dict)
    swept_high: bool = False
    swept_low: bool = False
    bars_used: dict[int, int] = field(default_factory=dict)


@dataclass
class Assessment:
    scenario: str
    reason: str
    surprise_z: float | None = None
    revision: float | None = None
    hypothesis_dir: int = 0             # +1 gold up, -1 gold down, 0 none
    reaction: Reaction | None = None
    confirmed: bool | None = None
    priced_in: str = "NOT ASSESSED: no positioning or consensus-distribution feed"
    positioning: str = "NOT ASSESSED: no COT or crowding feed"
    tradeable: bool = False


# ----------------------------------------------------------------- surprise
def surprise_z(ev: Event) -> float | None:
    """Standardised surprise. None when it cannot be computed - which is a
    NO_TRADE condition, not a zero."""
    if ev.actual is None or ev.consensus is None:
        return None
    if ev.sigma is None or ev.sigma <= 0:
        return None
    return (ev.actual - ev.consensus) / ev.sigma


def revision(ev: Event) -> float | None:
    """How the PRIOR print was revised. A large revision can invert the read
    of an in-line release, so it is carried separately rather than folded in."""
    if ev.previous is None or ev.previous_revised is None:
        return None
    return ev.previous_revised - ev.previous


def hypothesis_direction(ev: Event, z: float | None) -> int:
    if z is None or z == 0:
        return 0
    stronger = 1 if z > 0 else -1
    return -stronger if ev.higher_is_gold_negative else stronger


# ----------------------------------------------------------------- reaction
def measure_reaction(t_event: int, times: np.ndarray, high: np.ndarray,
                     low: np.ndarray, close: np.ndarray, atr: float,
                     horizons=HORIZONS_MIN) -> Reaction:
    """Signed move at each horizon, in ATR units.

    Only bars that OPEN at or after the release are used. The anchor is the
    last close strictly BEFORE it. Taking the release bar itself would mix the
    move being measured into the baseline it is measured from.
    """
    r = Reaction()
    if atr <= 0 or len(times) == 0:
        return r
    after = np.flatnonzero(times >= t_event)
    before = np.flatnonzero(times < t_event)
    if len(after) == 0 or len(before) == 0:
        return r
    anchor = float(close[before[-1]])
    pre_hi = float(high[before[-min(len(before), 30):]].max())
    pre_lo = float(low[before[-min(len(before), 30):]].min())

    for h in horizons:
        window = after[times[after] < t_event + h * 60]
        if len(window) == 0:
            continue
        r.by_horizon[h] = (float(close[window[-1]]) - anchor) / atr
        r.bars_used[h] = len(window)

    longest = max(horizons)
    full = after[times[after] < t_event + longest * 60]
    if len(full):
        r.swept_high = bool(high[full].max() > pre_hi)
        r.swept_low = bool(low[full].min() < pre_lo)
    return r


# ----------------------------------------------------------------- decision
def assess(events: list[Event], reaction: Reaction | None,
           spread_over_limit: bool = False,
           in_line_z: float = 0.5,
           confirm_atr: float = 0.5,
           reject_retrace: float = 0.5) -> Assessment:
    """Classify one release window into exactly one of the eight situations.

    Order matters and is fixed: the conditions that say STAND ASIDE are tested
    before the ones that would produce a direction, so an unreadable window can
    never be rescued into a trade by a later branch.
    """
    if not events:
        return Assessment(NO_TRADE, "no event in this window")

    if spread_over_limit:
        return Assessment(NO_TRADE, "spread above the tradeable limit at release")

    zs = {ev.name: surprise_z(ev) for ev in events}
    if any(z is None for z in zs.values()):
        missing = [n for n, z in zs.items() if z is None]
        return Assessment(
            NO_TRADE,
            f"surprise not computable for {missing} (missing actual, consensus "
            f"or historical sigma) - an unknown surprise is not a zero surprise")

    dirs = {ev.name: hypothesis_direction(ev, zs[ev.name]) for ev in events}
    material = {n: d for n, d in dirs.items() if abs(zs[n]) >= in_line_z}

    if len(material) == 0:
        return Assessment(IN_LINE, "every release within {:.2f} sigma of consensus"
                          .format(in_line_z),
                          surprise_z=max(zs.values(), key=abs),
                          revision=revision(events[0]))

    signs = {d for d in material.values() if d != 0}
    if len(signs) > 1:
        return Assessment(
            CONFLICTING,
            f"simultaneous releases disagree: {material}",
            surprise_z=max((zs[n] for n in material), key=abs))

    hyp = signs.pop()
    lead = max(material, key=lambda n: abs(zs[n]))
    lead_ev = next(e for e in events if e.name == lead)
    z = zs[lead]
    rev = revision(lead_ev)

    if reaction is None or not reaction.by_horizon:
        return Assessment(NO_TRADE, "no price reaction measured yet",
                          surprise_z=z, revision=rev, hypothesis_dir=hyp)

    # A window that took both pre-event extremes has no side to read.
    if reaction.swept_high and reaction.swept_low:
        return Assessment(SWEEP_BOTH,
                          "both pre-event extremes taken inside the window",
                          surprise_z=z, revision=rev, hypothesis_dir=hyp,
                          reaction=reaction)

    early = reaction.by_horizon.get(5) or reaction.by_horizon.get(1) or 0.0
    late = (reaction.by_horizon.get(60) or reaction.by_horizon.get(15)
            or reaction.by_horizon.get(5) or 0.0)

    moved_with = hyp * late
    # Acceptance: did the move hold, or was it given back?
    retraced = (hyp * early > 0 and hyp * late < hyp * early * reject_retrace)

    if moved_with >= confirm_atr and not retraced:
        scen = POS_CONFIRM if hyp > 0 else NEG_CONFIRM
        conf, why = True, (f"reaction {late:+.2f} ATR agrees with a "
                           f"{'gold-bullish' if hyp > 0 else 'gold-bearish'} "
                           f"surprise of {z:+.2f} sigma and held")
    elif moved_with <= -confirm_atr or retraced:
        scen = POS_REJECT if hyp > 0 else NEG_REJECT
        conf, why = False, (f"reaction {late:+.2f} ATR refuses a "
                            f"{'gold-bullish' if hyp > 0 else 'gold-bearish'} "
                            f"surprise of {z:+.2f} sigma"
                            + (" (initial move given back)" if retraced else ""))
    else:
        return Assessment(NO_TRADE,
                          f"reaction {late:+.2f} ATR is inside the noise band "
                          f"of +/-{confirm_atr:.2f}",
                          surprise_z=z, revision=rev, hypothesis_dir=hyp,
                          reaction=reaction)

    return Assessment(scen, why, surprise_z=z, revision=rev, hypothesis_dir=hyp,
                      reaction=reaction, confirmed=conf, tradeable=True)
