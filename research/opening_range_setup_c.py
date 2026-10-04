#!/usr/bin/env python3
"""Setup C - Opening Range Expansion, tested standalone for the first time.

WHY THIS ONE
  `docs/RESEARCH_FINDINGS.md`'s own status table: "C - Opening range expansion
  | off | never tested". The EA has shipped this logic in `Setups.mqh` since
  the beginning and nobody has ever measured it. That is a gap in the
  program's own record, not a new idea - closing it belongs in this round.

THE RULE, MIRRORING Setups.mqh / Config.mqh EXACTLY
  Opening range = the first InpORMinutes (30) minutes after London (08:00 UTC)
  or New York (13:00 UTC) session open - the EA's own defaults, unchanged.
  Breakout = a close beyond the OR high/low by >= InpORMinExpansionATR (0.8)
  x ATR. Long above, short below.

  ONE simplification from the real EA: `Setups.mqh` requires a RETEST of the
  OR edge before entering when `InpEntryMode=ENTRY_RETEST` (the EA's
  default). This file tests the breakout ALONE, without that filter, because
  isolating the breakout first is what lets a retest requirement be judged
  against it afterward rather than assumed to help.

DATA WINDOW
  GC=F M5, 60 days - the span asked for this round.

PRE-REGISTERED
  skill > +0.05R at t > 1.96 (this is the ONLY test in this round's final
  batch, so the bar is the plain two-sided 95% line, not a Bonferroni-widened
  one - stated before the run, not chosen after seeing where the number fell).
"""
import math, sys, pathlib
import numpy as np, pandas as pd

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from deep_research_signals import evaluate, HDR, line
from intermarket_signals_60d import fetch, atr

OR_MINUTES = 30
OR_EXPANSION_ATR = 0.8
LONDON_HOUR, NY_HOUR = 8, 13
HOLD = 96

def opening_range_signal(df):
    h, l, c = (df[k].to_numpy(float) for k in ("high", "low", "close"))
    A = atr(df)
    idx = df.index
    sig = np.zeros(len(df), np.int8)

    # bars-per-5-minutes assumption holds for this feed; recover OR_MINUTES
    # in BAR COUNT from the actual median spacing, so this is not silently
    # wrong if Yahoo ever changes the granularity served.
    step_min = pd.Series(idx).diff().dt.total_seconds().median() / 60.0
    or_bars = max(1, round(OR_MINUTES / step_min))

    for hour in (LONDON_HOUR, NY_HOUR):
        is_open = (idx.hour == hour) & (idx.minute < step_min)
        open_ix = np.flatnonzero(is_open)
        for oi in open_ix:
            or_end = oi + or_bars
            if or_end + 1 >= len(df): continue
            or_hi = h[oi:or_end].max()
            or_lo = l[oi:or_end].min()
            or_size = or_hi - or_lo
            if or_size <= 0: continue
            fired = False
            for k in range(or_end, min(or_end + 48, len(df))):   # watch 4h post-OR
                a = A[k-1]
                if not np.isfinite(a) or a <= 0: continue
                if not fired and c[k] > or_hi and (c[k] - or_hi) >= OR_EXPANSION_ATR*a:
                    sig[k] = 1; fired = True; break
                if not fired and c[k] < or_lo and (or_lo - c[k]) >= OR_EXPANSION_ATR*a:
                    sig[k] = -1; fired = True; break
    return sig

def main():
    print("Setup C - opening range expansion, standalone, never tested before.")
    gold = fetch("GC=F")
    print(f"gold M5 {len(gold):,} bars {gold.index[0].date()} -> "
          f"{gold.index[-1].date()}\n")

    sig = opening_range_signal(gold)
    n_fired = int((sig != 0).sum())
    print(f"raw breakout events: {n_fired}\n")

    print(HDR); print("  " + "-"*(len(HDR)-2))
    r = evaluate(gold, sig, hold=HOLD)
    line("Setup C: OR breakout, London+NY, no retest filter", r)

    if r is not None:
        bar = 1.96
        v = "CLEARS the bar" if abs(r["t"]) > bar else "does not clear"
        print(f"\n  plain two-sided 95% bar: |t| > {bar}")
        print(f"  skill t = {r['t']:+.2f}  -  {v}")

if __name__ == "__main__":
    main()
