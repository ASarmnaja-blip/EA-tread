#!/usr/bin/env python3
"""Does confirming the VWAP fade with DXY agreement do anything the VWAP fade
alone does not?

WHERE THIS CAME FROM, AND THE CAVEAT THAT COMES WITH IT
  Round 2 measured two signals with small positive (not significant) skill:
  VWAP fade +0.206R (t +1.21) and DXY lead-lag +0.128R (t +0.87). Neither
  cleared its bar alone. The multi-factor question is whether requiring them
  to AGREE removes noise rather than signal - the same logic
  `qc_4part_filter_test.py` uses to ask whether a filter selects a genuinely
  different population or just shrinks the sample.

  THIS IS NOT A FRESH TEST. It is built on which two signals round 2 already
  showed looked (mildly) promising, on the SAME 60-day window. That is nested
  selection - the same caveat `wick_tip_finetune.py` had to carry - and it
  means any positive result here is a LEAD, not a confirmation. A real
  confirmation needs a window this file's design was never exposed to, which
  a single 60-day pull cannot supply. Stated before the run, not after.

THREE COMBINATIONS, EACH A DIFFERENT CLAIM
  M1  VWAP fade EVENT (the entry trigger), DXY's own momentum SIGN must agree
      at that moment - DXY treated as a confirming filter on a VWAP trigger.
  M2  the mirror: DXY momentum EVENT triggers, VWAP's distance SIGN must
      agree - VWAP treated as a confirming filter on a DXY trigger.
  M3  STRICT confluence: both signals fire their OWN event within 3 bars of
      each other, in agreeing directions. The tightest, smallest-sample form.

  Each is compared against its own single-factor parent (does confirmation
  raise skill, or just cut the sample and leave skill where it was) as well
  as against the matched random control everything else in this repo uses.

PRE-REGISTERED
  skill > +0.10R at t > 1.96 for M1/M2 (a plain two-sided 95% line - this is
  exploratory follow-up work, not a fresh independent test, so no new
  Bonferroni widening is claimed; the honesty is in calling it a lead, not in
  a harsher bar). M3's small expected n is stated before the run: if n < 20,
  the result is reported as "cannot resolve," not as a negative.
"""
import math, sys, pathlib
import numpy as np, pandas as pd

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from deep_research_signals import evaluate, HDR, line
from intermarket_signals_60d import fetch, atr, session_vwap

HOLD = 96
VWAP_K = 1.5
DXY_LOOK, DXY_K = 12, 0.6

def build_states(gold, dxy):
    """VWAP distance (z, in ATR units) and DXY momentum (in DXY's own ATR
    units, shifted 1 bar so only completed information is used), aligned on
    gold's index."""
    j = pd.concat([gold[["open","high","low","close"]],
                   dxy.close.rename("dxy")], axis=1, join="inner").dropna()
    c = j.close.to_numpy()
    A = atr(j)
    vwap = session_vwap(j)
    dist = (c - vwap) / np.where(A > 0, A, np.nan)

    A_dxy = atr(pd.DataFrame({"high": j.dxy, "low": j.dxy, "close": j.dxy}))
    mom = (j.dxy - j.dxy.shift(DXY_LOOK)) / np.where(A_dxy > 0, A_dxy, np.nan)
    mom = mom.shift(1).to_numpy()
    return j, dist, mom

def events(cond_pos, cond_neg):
    """First-bar-of-run boolean masks for a condition entering true."""
    active = cond_pos | cond_neg
    fire = active & ~pd.Series(active).shift(1).fillna(False).to_numpy().astype(bool)
    return fire

def m1_vwap_trigger_dxy_confirm(j, dist, mom):
    vwap_pos, vwap_neg = dist >= VWAP_K, dist <= -VWAP_K
    fire = events(vwap_pos, vwap_neg)
    sig = np.zeros(len(j), np.int8)
    dxy_agrees_short = mom > 0      # DXY up -> agrees with gold short
    dxy_agrees_long = mom < 0       # DXY down -> agrees with gold long
    sig[fire & vwap_pos & dxy_agrees_short] = -1
    sig[fire & vwap_neg & dxy_agrees_long] = 1
    return sig

def m2_dxy_trigger_vwap_confirm(j, dist, mom):
    dxy_pos, dxy_neg = mom >= DXY_K, mom <= -DXY_K
    fire = events(dxy_pos, dxy_neg)
    sig = np.zeros(len(j), np.int8)
    vwap_agrees_short = dist > 0
    vwap_agrees_long = dist < 0
    sig[fire & dxy_pos & vwap_agrees_short] = -1
    sig[fire & dxy_neg & vwap_agrees_long] = 1
    return sig

def m3_strict_confluence(j, dist, mom, window=3):
    vwap_pos, vwap_neg = dist >= VWAP_K, dist <= -VWAP_K
    dxy_pos, dxy_neg = mom >= DXY_K, mom <= -DXY_K
    vwap_fire = events(vwap_pos, vwap_neg)
    dxy_fire = events(dxy_pos, dxy_neg)
    n = len(j)
    sig = np.zeros(n, np.int8)
    vwap_ix = {i: (1 if vwap_neg[i] else -1) for i in np.flatnonzero(vwap_fire)}
    dxy_ix = {i: (1 if dxy_neg[i] else -1) for i in np.flatnonzero(dxy_fire)}
    for i, d in vwap_ix.items():
        for k in range(max(0, i-window), min(n, i+window+1)):
            if dxy_ix.get(k) == d:
                sig[max(i, k)] = d      # act once both have fired
                break
    return sig

def main():
    print("VWAP / DXY confluence - a lead from round 2, not a fresh test.")
    print("(nested selection: see the module docstring before trusting a")
    print(" positive number here)\n")
    gold, dxy = fetch("GC=F"), fetch("DX-Y.NYB")
    j, dist, mom = build_states(gold, dxy)
    print(f"joined bars: {len(j):,}  {j.index[0].date()} -> {j.index[-1].date()}\n")

    print(HDR); print("  " + "-"*(len(HDR)-2))
    r1 = evaluate(j, m1_vwap_trigger_dxy_confirm(j, dist, mom), hold=HOLD)
    line("M1 VWAP trigger, DXY sign confirms", r1)
    r2 = evaluate(j, m2_dxy_trigger_vwap_confirm(j, dist, mom), hold=HOLD)
    line("M2 DXY trigger, VWAP sign confirms", r2)
    sig3 = m3_strict_confluence(j, dist, mom)
    n3_raw = int((sig3 != 0).sum())
    if n3_raw < 20:
        print(f"  {'M3 strict confluence (both fire, agree)':<40}"
              f"  {n3_raw} raw events - cannot resolve, too few by design")
    else:
        r3 = evaluate(j, sig3, hold=HOLD)
        line("M3 strict confluence (both fire, agree)", r3)

    print(f"\n  T1 VWAP alone (round 2, same window):  skill +0.206R  t +1.21")
    print(f"  T2 DXY alone  (round 2, same window):  skill +0.128R  t +0.87")
    print(f"  plain two-sided 95% bar: |t| > 1.96\n")
    for nm, r in (("M1", r1), ("M2", r2)):
        if r is None: continue
        v = "CLEARS the bar" if abs(r["t"]) > 1.96 else "does not clear"
        print(f"  {nm}: skill t = {r['t']:+.2f}  -  {v}")

    print("\nHOW TO READ THIS")
    print("  Compare M1's skill/t to T1 alone, and M2's to T2 alone. If")
    print("  confirmation is removing noise, skill rises AND n falls less than")
    print("  proportionally. If confirmation only cuts the sample, skill stays")
    print("  roughly where the parent signal was, with a wider error bar from")
    print("  fewer trades - noise, not information, was removed.")

if __name__ == "__main__":
    main()
