#!/usr/bin/env python3
"""Intraday-only trading: force-close before rollover, never hold a weekend.

THE RULES BEING ENFORCED (as supplied)
  5. no position may be held across rollover
  6. force close at least 30 minutes before rollover
  7. no position may be held from Friday into Monday
  8. the main test therefore runs with swap = 0, because nothing is ever held
     overnight for a swap to be charged on

HOW A SESSION IS DEFINED
  Rollover is taken to be 00:00 server time. Exness MT5 servers run GMT+3,
  so rollover is 21:00 UTC. Force-closing 30 minutes early puts the deadline
  at 20:30 UTC. THE 21:00 UTC ROLLOVER IS AN ASSUMPTION - it is not in the
  supplied spec, and if the server is on GMT+2 (or GMT+3 with DST) the
  deadline moves by an hour. It is stated here so it can be corrected in one
  place.

  A session is therefore the span from one 20:30 UTC deadline to the next,
  and every bar is labelled with the session it belongs to:

      sid(t) = floor( (t - 20:30) / 1 day )

  A bar at 22:00 Monday and a bar at 10:00 Tuesday get the SAME session id,
  which is correct: they are the same server day and a position opened at the
  first may legitimately still be open at the second. A bar at 21:00 Tuesday
  gets the next id.

  The weekend needs no special case and gets none. Friday's last bars and
  Sunday's opening bars fall in different sessions because deadlines pass in
  between, so rule 7 is enforced by the same arithmetic as rule 5 rather than
  by a second rule that could disagree with it.

WHAT A DEADLINE DOES TO A TRADE
  Each bar gets `deadline[i]`: the last bar index a position opened at i may
  still be held through. A trade's effective horizon is therefore
  min(its configured hold, deadline - entry + 1), and a signal whose entry bar
  has no room left (deadline < entry) produces NO TRADE AT ALL rather than a
  zero-length one.
"""
import numpy as np, pandas as pd

ROLLOVER_UTC_HOUR = 21          # 00:00 server time at GMT+3. ASSUMPTION.
FORCE_CLOSE_MINUTES_EARLY = 30  # rule 6

def deadline_minutes():
    return ROLLOVER_UTC_HOUR * 60 - FORCE_CLOSE_MINUTES_EARLY   # 20:30 UTC

def session_ids(index):
    """Integer session label per bar. Bars sharing a label are the same
    server day and may share a position."""
    shifted = index - pd.Timedelta(minutes=deadline_minutes())
    # Convert through datetime64[D] rather than dividing a raw integer by a
    # hard-coded nanoseconds-per-day. pandas 2 stores some indexes in
    # MICROSECONDS, and asi8 // 86400e9 then silently returns a number a
    # thousand times too small - every bar lands in the same "session" and the
    # deadline machinery quietly stops working. Asking numpy for days is
    # unit-safe by construction.
    naive = shifted.tz_localize(None) if shifted.tz is not None else shifted
    return np.asarray(naive, dtype="datetime64[D]").astype("int64")

def bar_minutes(index):
    """Infer the bar length from the index, in minutes."""
    naive = index.tz_localize(None) if index.tz is not None else index
    mins = np.asarray(naive, dtype="datetime64[m]").astype("int64")
    d = np.diff(mins)
    d = d[d > 0]
    if len(d) == 0:
        raise ValueError("cannot infer bar length from a single-bar index")
    return int(np.bincount(d.astype(int)).argmax())

def intraday_deadlines(index, tf_minutes=None):
    """For each bar, the last bar index a position opened there may be held to.

    Returns (deadline, sid, closable). `closable[i]` is False for a bar whose
    CLOSE falls after the deadline - a 20:00 hourly bar closes at 21:00, which
    is rollover itself, so it cannot be the bar a position exits on."""
    if tf_minutes is None:
        tf_minutes = bar_minutes(index)
    sid = session_ids(index)
    # A bar is closable if its CLOSE still falls inside its own session.
    # Measuring from the session start (20:30 UTC) and wrapping at a day makes
    # this one comparison for every bar, including the 21:00-23:59 bars whose
    # clock time belongs to the next calendar day but the same server day.
    mins_from_start = ((index.hour * 60 + index.minute).to_numpy()
                       - deadline_minutes()) % 1440
    closable = (mins_from_start + tf_minutes) <= 1440

    n = len(index)
    deadline = np.full(n, -1, int)
    i = 0
    while i < n:
        j = i
        while j + 1 < n and sid[j + 1] == sid[i]:
            j += 1
        # session spans [i, j]; its last closable bar:
        last = -1
        for k in range(j, i - 1, -1):
            if closable[k]:
                last = k
                break
        deadline[i:j + 1] = last
        i = j + 1
    return deadline, sid, closable

def effective_holds(index, entry_bars, configured_hold, tf_minutes=None,
                    deadline=None):
    """Per-trade horizon after the intraday deadline is applied.

    Returns (hold, ok). `ok` is False where the entry bar has no room left in
    its session - those signals must be DROPPED, not traded with a zero hold."""
    if deadline is None:
        deadline, _, _ = intraday_deadlines(index, tf_minutes)
    e = np.asarray(entry_bars, int)
    dl = deadline[e]
    room = dl - e + 1
    ok = room >= 1
    hold = np.minimum(int(configured_hold), np.maximum(room, 1))
    return hold.astype(int), ok

def audit(index, tf_minutes=None):
    """Human-readable check that the session machinery did what it claims."""
    if tf_minutes is None:
        tf_minutes = bar_minutes(index)
    deadline, sid, closable = intraday_deadlines(index, tf_minutes)
    n_sessions = len(np.unique(sid))
    ends = np.unique(deadline[deadline >= 0])
    end_times = index[ends]
    L = []
    L.append(f"  bar length inferred      {tf_minutes} minutes")
    L.append(f"  rollover assumed at      {ROLLOVER_UTC_HOUR:02d}:00 UTC "
             f"(00:00 server, GMT+3) - ASSUMPTION")
    L.append(f"  force-close deadline     "
             f"{deadline_minutes()//60:02d}:{deadline_minutes()%60:02d} UTC "
             f"({FORCE_CLOSE_MINUTES_EARLY} min early, rule 6)")
    L.append(f"  sessions in the data     {n_sessions:,}")
    L.append(f"  bars not closable        {int((~closable).sum()):,} of {len(index):,} "
             f"(their close lands after the deadline)")
    if len(end_times):
        hh = pd.Series(end_times.hour).value_counts().sort_index()
        top = hh.sort_values(ascending=False).head(4)
        L.append(f"  session-end bar hours    "
                 + ", ".join(f"{h:02d}:00 x{c:,}" for h, c in top.items())
                 + (f", +{len(hh)-len(top)} rarer" if len(hh) > len(top) else ""))
        # Measured FROM THE SESSION START, not off the wall clock. A 21:00 bar
        # closes at 22:00 by the clock, which looks like a breach but is not -
        # it sits 90 minutes into the NEXT session, which runs to 20:30 the
        # following day. Thin holidays leave sessions whose only bars are late
        # in the evening, and judging those by clock time reports a violation
        # that did not happen.
        mfs = ((end_times.hour * 60 + end_times.minute).to_numpy()
               - deadline_minutes()) % 1440
        worst = int((mfs + tf_minutes).max())
        L.append(f"  latest exit, measured from the session start: "
                 f"{worst//60}h{worst%60:02d}m of a 24h00m session "
                 f"-> {'OK' if worst <= 1440 else '*** BREACH'}")
    return "\n".join(L)
