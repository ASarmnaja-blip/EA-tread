#!/usr/bin/env python3
"""One execution function. Strategy and control both call it, or neither is
comparable to the other.

WHY THIS FILE REPLACES THE OLD PATH
  `bug_reproductions.py` demonstrates, on hand-built paths whose right answer
  is known before any code runs, that the previous engine:

    1. booked +0.667R on a long whose entry bar opened at 90 with the stop at
       98 - it filled the exit at a price that never traded after entry. The
       mirror case on the short side returned the same fabricated +0.667R.
    2. expired the matched control one bar later than the strategy: the
       strategy's hold-H exit is the close of bar e+H-1, the control's was
       c[e+H]. One free bar of information on every control trade.
    3. let the control draw its random bars from the whole history, so a
       discovery-period control trade could land inside the holdout.

  Those are not tuning differences. A strategy measured by one set of rules
  against a control measured by another is not measured at all.

THE RULES, DECLARED ONCE AND APPLIED TO BOTH SIDES

  entry          the OPEN of the bar after the signal bar. The plan - stop,
                 target, risk - is frozen at the signal bar's close and never
                 recomputed from the fill.
  risk           |signal close - stop|, so a gap between signal and fill
                 changes the realised loss but not the denominator. This is
                 the convention the supplied external audit used and it is
                 kept deliberately: it means a gap can lose MORE than 1R,
                 which is true of real trading.
  ENTRY GAP      checked BEFORE anything else. If the entry open is already
                 beyond the stop, or already beyond the target, the plan was
                 void by the time it could be acted on. `on_gap` declares what
                 happens: "skip" drops the trade (default - a resting order
                 that can no longer be placed at its planned risk), "open"
                 fills and exits at that opening price. Neither may report a
                 profit taken at a bracket level that never traded after
                 entry.
  intrabar       from the entry bar onward: a bar whose OPEN is beyond a
                 bracket fills AT THAT OPEN; otherwise the bracket fills at
                 its own level. Stop wins when both are touched in one bar,
                 because the bar's internal order is unknown and the
                 conservative reading is the one that does not flatter.
  horizon        hold H exits at the CLOSE OF BAR e+H-1. The entry bar counts
                 as bar 1. Strategy and control share this line.
  cost           one round trip, taken from the cost series AT THE ENTRY BAR.
                 A control trade drawn at a different time pays THAT time's
                 cost, not the cost of the signal it is standing in for.
"""
import numpy as np

# exit reasons, kept as small ints so a trade log stays compact
GAP_SKIP, GAP_STOP, GAP_TP, HIT_STOP, HIT_TP, TIME_EXIT, NO_ROOM = range(7)
REASON = {GAP_SKIP: "gap_skip", GAP_STOP: "gap_stop", GAP_TP: "gap_tp",
          HIT_STOP: "stop", HIT_TP: "target", TIME_EXIT: "time",
          NO_ROOM: "no_room"}

def execute(o, h, l, c, N, sig_i, d, stop, risk, target, hold, cost_at,
            on_gap="skip"):
    """Resolve exactly one trade. Returns a dict, or None when no trade exists.

    o,h,l,c,N   price arrays and their length
    sig_i       index of the SIGNAL bar (entry is sig_i+1)
    d           +1 long, -1 short
    stop, risk  frozen at the signal close; target may be None for no target
    hold        maximum bars held, counting the entry bar as bar 1
    cost_at     per-bar round-trip cost array; the ENTRY bar's value is used
    on_gap      "skip" or "open" - what to do when the entry open is already
                beyond a bracket
    """
    e = sig_i + 1
    if e >= N:
        return None
    entry = float(o[e])
    if not np.isfinite(entry) or risk <= 0:
        return None
    cost = float(cost_at[e]) if e < len(cost_at) else float(cost_at[-1])

    def out(exit_px, exit_bar, reason):
        r = ((exit_px - entry) * d - cost) / risk
        return dict(R=float(r), entry=entry, exit=float(exit_px),
                    entry_bar=e, exit_bar=int(exit_bar), held=int(exit_bar - e + 1),
                    reason=reason, risk=float(risk), cost=cost, d=int(d))

    # ---- entry-bar gap, checked before any bracket can be credited ---------
    gapped_stop = (entry <= stop) if d > 0 else (entry >= stop)
    gapped_tp = target is not None and ((entry >= target) if d > 0 else (entry <= target))
    if gapped_stop or gapped_tp:
        if on_gap == "skip":
            return dict(R=np.nan, entry=entry, exit=np.nan, entry_bar=e,
                        exit_bar=e, held=0,
                        reason=GAP_SKIP, risk=float(risk), cost=cost, d=int(d))
        return out(entry, e, GAP_STOP if gapped_stop else GAP_TP)

    last = min(e + hold, N)              # exclusive; hold H -> last bar e+H-1
    if last <= e:
        return dict(R=np.nan, entry=entry, exit=np.nan, entry_bar=e, exit_bar=e,
                    held=0, reason=NO_ROOM, risk=float(risk), cost=cost, d=int(d))

    for k in range(e, last):
        if k > e:
            # an open already beyond a bracket fills AT THAT OPEN
            if (o[k] <= stop) if d > 0 else (o[k] >= stop):
                return out(o[k], k, GAP_STOP)
            if target is not None and ((o[k] >= target) if d > 0 else (o[k] <= target)):
                return out(o[k], k, GAP_TP)
        # stop wins ties - the bar's internal order is unknown
        if (l[k] <= stop) if d > 0 else (h[k] >= stop):
            return out(stop, k, HIT_STOP)
        if target is not None and ((h[k] >= target) if d > 0 else (l[k] <= target)):
            return out(target, k, HIT_TP)
    kx = last - 1                         # close of bar e+H-1
    return out(c[kx], kx, TIME_EXIT)

def plan_from_signal(c_sig, atr, ph, pl, d, stop_mode, buf, tp_mult,
                     min_stop_atr=0.25, max_stop_atr=8.0,
                     min_risk_cost=3.0, cost=0.0):
    """The frozen plan, computed from the SIGNAL BAR only. Returns
    (stop, risk, target) or None when the plan is ineligible.

    Separated from `execute` so the identical plan can be handed to a control
    trade drawn at a different time - the control gets the same SHAPE of plan
    (same stop mode, same multiples), recomputed from its own bar's state."""
    if not np.isfinite(atr) or atr <= 0:
        return None
    if stop_mode == "range":
        stop = (pl - buf * atr) if d > 0 else (ph + buf * atr)
    else:
        k_atr = float(stop_mode[3:])
        stop = c_sig - d * k_atr * atr
    if not np.isfinite(stop):
        return None
    risk = (c_sig - stop) * d
    if risk <= 0:
        return None
    if not (min_stop_atr * atr <= risk <= max_stop_atr * atr):
        return None
    if cost and risk < min_risk_cost * cost:
        return None
    target = None if tp_mult is None else c_sig + d * tp_mult * risk
    return float(stop), float(risk), (None if target is None else float(target))
