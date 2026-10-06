#!/usr/bin/env python3
"""Is the best candidate a market effect or a hole in the calendar?

THE WORRY, WHICH IS CREATED BY A FIX THIS SESSION MADE

  Removing the 29% of bars where the venue was not quoting was correct and is
  measured elsewhere. It has a consequence: two bars that are ADJACENT IN THE
  FRAME need not be adjacent in time. The bar before a weekend sits next to
  the bar after it. The last bar before the daily rollover sits next to the
  first one after it.

  The winning candidate is "a quiet bar followed by a bar whose range exceeds
  1.5 ATR, faded". A quiet bar at 20:00 followed by the next quoted bar hours
  later, whose range contains an overnight gap, matches that description
  perfectly and has nothing to do with expansion after quiet. It would be a
  rule that fades gaps, wearing a costume.

  It is also the kind of artifact that would survive every control in the
  hierarchy, because the controls match on activity, volatility, session,
  regime and position in range - none of which is "the clock skipped".

THE TEST

  Four contiguity requirements, applied one at a time and then together:

    PREV    the quiet bar is exactly one hour before the expansion bar
    ENTRY   the entry bar is exactly one hour after the signal bar
    EXIT    the exit bar is exactly three hours after the entry
    ALL     all three at once

  If the edge survives ALL with most of its magnitude, the sequence is a
  market effect. If it collapses, it is the calendar, and the honest reading
  is that the pilot found an artifact of this session's own data fix.

THE SECOND TEST, WHICH IS THE COMPLEMENT

  Measure the effect on the bars that are EXCLUDED by contiguity - the ones
  that span a gap. If the whole effect lives there, that settles it in the
  other direction and names the real phenomenon.
"""
import argparse
import json
import math
import pathlib
import sys
import time

import numpy as np
import pandas as pd

HERE = pathlib.Path(__file__).parent
sys.path.insert(0, str(HERE))
import discovery as DIS
import provenance as PR
import xauusd_1000_setups as X
from p01_cross_market import MARKETS, load_bidask_h1

H = 3
COST = DIS.COST_SPREADS
HOUR = pd.Timedelta(hours=1)


def contiguity_masks(P):
    """For every bar: is the previous frame bar one hour back, and is the
    next one an hour forward, and is the bar three ahead exactly three."""
    idx = pd.DatetimeIndex(P["idx"])
    N = len(idx)
    d_prev = np.full(N, False)
    d_prev[1:] = (idx[1:] - idx[:-1]) == HOUR
    d_next = np.full(N, False)
    d_next[:-1] = d_prev[1:]
    # entry at t+1, exit at t+H: the whole window t..t+H must be hourly
    win = np.full(N, False)
    if N > H + 1:
        ok = np.ones(N - H - 1, bool)
        for k in range(1, H + 1):
            ok &= (idx[k:N - H - 1 + k] - idx[k - 1:N - H - 1 + k - 1]) == HOUR
        win[:N - H - 1] = ok
    return d_prev, d_next, win


def variants(P, V, rng_thr=1.5, prev_thr=0.7):
    r = V["ret_atr"]
    rngv = V["range_atr"]
    s = np.sign(np.nan_to_num(r, nan=0.0))
    g1 = np.roll(rngv, 1)
    base = np.nan_to_num((rngv > rng_thr) & (g1 < prev_thr), nan=False)
    base &= np.isfinite(r) & (s != 0)
    base[:300] = False
    prev_ok, next_ok, win_ok = contiguity_masks(P)
    return {
        "as measured": base,
        "PREV contiguous": base & prev_ok,
        "ENTRY contiguous": base & next_ok,
        "EXIT window hourly": base & win_ok,
        "ALL contiguous": base & prev_ok & next_ok & win_ok,
        "SPANS A GAP (complement)": base & ~(prev_ok & next_ok & win_ok),
    }, s


def cross_t(v):
    v = np.asarray([x for x in v if np.isfinite(x)], float)
    if len(v) < 3:
        return np.nan, 0, 0
    se = float(v.std(ddof=1) / math.sqrt(len(v)))
    return (float(v.mean() / se) if se > 0 else np.nan,
            int((v > 0).sum()), len(v))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols", default=",".join(MARKETS))
    ap.add_argument("--rng", type=float, default=1.5)
    ap.add_argument("--prev", type=float, default=0.7)
    a = ap.parse_args()
    t0 = time.time()
    syms = [s.strip() for s in a.symbols.split(",") if s.strip()]

    print("CONTIGUITY - a market effect, or a hole in the calendar?")
    print("=" * 100)
    print(__doc__.split("THE TEST")[1].split("THE SECOND TEST")[0])

    agg = {}
    for sym in syms:
        df = load_bidask_h1(sym)
        if df is None or len(df) < 20000:
            continue
        P = X.prep(df, 60)
        V = DIS.state_vars(P)
        vs, s = variants(P, V, a.rng, a.prev)
        for lab, m in vs.items():
            t = np.where(m)[0]
            if len(t) < 60:
                agg.setdefault(lab, []).append(None)
                continue
            sc = DIS.score(P, t, -s[t].astype(float), H)
            agg.setdefault(lab, []).append(sc)
        print(f"  {sym} done", flush=True)

    print("\n" + "=" * 100)
    print(f"THE SAME RULE, WITH THE CALENDAR REQUIRED "
          f"(range>{a.rng} ATR after a bar under {a.prev})")
    print("=" * 100)
    print(f"  {'variant':<28}{'mkts':>6}{'n/mkt':>9}{'edge':>10}{'t':>8}"
          f"{'pos':>8}{'share of base':>15}")
    base_n = None
    rows = []
    for lab in ("as measured", "PREV contiguous", "ENTRY contiguous",
                "EXIT window hourly", "ALL contiguous",
                "SPANS A GAP (complement)"):
        gs = [g for g in agg.get(lab, []) if g]
        if len(gs) < 3:
            print(f"  {lab:<28}{'too few markets':>40}")
            continue
        e = [g["edge"] for g in gs]
        n = float(np.mean([g["n"] for g in gs]))
        t, pos, m = cross_t(e)
        if lab == "as measured":
            base_n = n
        share = n / base_n if base_n else float("nan")
        rows.append(dict(variant=lab, markets=m, n_per_market=n,
                         edge=float(np.mean(e)), t=t, positive=pos,
                         share_of_base=share))
        print(f"  {lab:<28}{m:>6}{n:>9,.0f}{np.mean(e):>+10.3f}{t:>+8.2f}"
              f"{pos:>5}/{m}{share*100:>14.1f}%")

    base = next((r for r in rows if r["variant"] == "as measured"), None)
    allc = next((r for r in rows if r["variant"] == "ALL contiguous"), None)
    gap = next((r for r in rows if r["variant"].startswith("SPANS")), None)
    verdict = "UNDETERMINED"
    if base and allc:
        ret = allc["edge"] / base["edge"] if abs(base["edge"]) > 1e-9 else np.nan
        print(f"\n  contiguous-only retains {ret:.0%} of the edge on "
              f"{allc['share_of_base']*100:.0f}% of the signals")
        if gap:
            print(f"  the gap-spanning complement is {gap['edge']:+.3f} on "
                  f"{gap['share_of_base']*100:.0f}% of the signals")
        if np.isfinite(ret) and ret >= 0.7:
            verdict = "MARKET EFFECT - survives the calendar requirement"
        elif np.isfinite(ret) and ret < 0.3:
            verdict = "CALENDAR ARTIFACT - the edge lives in the gaps"
        else:
            verdict = "PARTLY CALENDAR - both contribute"
        print(f"\n  VERDICT: {verdict}")
        if allc and allc["edge"] > COST:
            print(f"  the contiguous version still clears the "
                  f"{COST}-spread cost at {allc['edge']:+.3f}")
        elif allc:
            print(f"  the contiguous version does NOT clear the "
                  f"{COST}-spread cost: {allc['edge']:+.3f}")

    out = HERE / "contiguity_test.json"
    out.write_text(json.dumps(dict(
        created=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        rng_thr=a.rng, prev_thr=a.prev, horizon=H, cost=COST,
        rows=rows, verdict=verdict,
        manifest=PR.manifest(dict(rng=a.rng, prev=a.prev),
                             [HERE / ".cache_duka" /
                              f"{s}_H1_2003_2026.parquet" for s in syms])),
        indent=1, default=str))
    PR.log("phase2-falsification",
           "Is the pilot's best candidate a market effect or an artifact of "
           "this session's own removal of unquoted bars?",
           hypothesis="pilot_conditional_amplitude",
           tools=["contiguity_test"], result=dict(rows=rows),
           status=verdict, finding=verdict,
           next_action="if calendar, retract the candidate and name the real "
                       "phenomenon",
           started=t0)
    print(f"\n  saved -> {out.name}   elapsed {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
