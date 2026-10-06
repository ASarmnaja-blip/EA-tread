#!/usr/bin/env python3
"""The one thing that survived, attacked with everything that could kill it.

WHAT IT IS

  Arm a breakout straddle after a large move: stops half an ATR either side of
  the next bar's open, take whichever triggers first, hold to the close of a
  three-bar window. It needs no direction - the market picks the side.

  Armed on EVERY bar it loses 0.140 of a round trip. Armed only after a
  2-ATR dislocation, or when the quote is in its cheapest quartile and a
  dislocation has just happened, it gains two to five round trips, in both
  halves of the sample, on 8 or 9 markets of 9 in each.

  That is the first result in this project where the conditional number is
  large against a measured unconditional baseline rather than against zero.

WHY IT IS PLAUSIBLE, WHICH IS NOT THE SAME AS TRUE

  Volatility clusters. After a two-ATR move the next three hours are also
  volatile, so a barrier set at half of a now-elevated ATR is reached often
  and the move that reaches it tends to continue. Nothing about that requires
  knowing direction, which is exactly why it escapes the arithmetic that
  killed every directional target here: the payoff is the SIZE of the move
  the straddle catches, and size is what the state predicts.

THE SEVEN WAYS THIS COULD STILL BE WRONG, AND ALL ARE TESTED

  1 IT IS THE STRADDLE, NOT THE STATE. Tested against a C7 control armed on
    matched bars - same activity, volatility, session, regime and range
    position - rather than against zero.

  2 WHIPSAW IS SCORED AS A FREEBIE. Windows where both barriers are touched
    in the same bar are currently counted as no trade. In reality one side
    fills and the other may stop it out. Re-scored pessimistically: both
    touched means entered and stopped, paying the full width.

  3 STOP ORDERS SLIP, AND THIS IS EXACTLY WHEN. A breakout stop in a volatile
    state is the worst case for slippage. Charged at 0, half, one and two
    extra spreads on entry.

  4 THE EXIT IS ARBITRARY. Held to the window close because that is what the
    target was defined as. Also measured at one, two, four and six bars.

  5 THE BARRIER WIDTH WAS NOT DERIVED FROM ANYTHING. Half an ATR was a
    guess. Swept.

  6 IT IS ONE ERA. Already split 2004-2016 and 2017-2026; both reported.

  7 IT IS THE NINE MARKETS THAT PRODUCED IT. Taken to USDSEK, which has
    already falsified one candidate that passed every other test here.
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
import controls as C
import discovery as DIS
import provenance as PR
import xauusd_1000_setups as X
from p01_cross_market import MARKETS, TICKS, load_bidask_h1

SEED = 17
SPLIT = pd.Timestamp("2017-01-01", tz="UTC")


def straddle(P, t, h=3, k=0.5, slip=0.0, whipsaw="skip"):
    """Breakout straddle armed at the bars in t.

    whipsaw='skip'   a window whose barriers are both touched in one bar is
                     scored as no trade. Optimistic.
    whipsaw='stop'   it is scored as entered and immediately stopped at the
                     full width plus cost. Pessimistic, and the honest bound
                     when the intrabar order is unknown."""
    N = P["N"]
    A = np.asarray(P["A"], float)
    o = (np.asarray(P["bid_o"], float) + np.asarray(P["ask_o"], float)) / 2
    c = np.asarray(P["c"], float)
    hi, lo = np.asarray(P["h"], float), np.asarray(P["l"], float)
    ask_o, bid_o = np.asarray(P["ask_o"], float), np.asarray(P["bid_o"], float)
    t = np.asarray(t)
    t = t[(t >= 300) & (t + h + 1 < N)]
    if len(t) < 100:
        return None
    e = t + 1
    entry, X, sp = o[e], k * A[t], ask_o[e] - bid_o[e]
    ok = np.isfinite(entry) & np.isfinite(X) & (X > 0) & np.isfinite(sp) & (sp > 0)
    t, e, entry, X, sp = t[ok], e[ok], entry[ok], X[ok], sp[ok]
    if len(t) < 100:
        return None
    up, dn = entry + X, entry - X
    K = e[:, None] + np.arange(h)[None, :]
    valid = K < N
    Kc = np.clip(K, 0, N - 1)
    H, L = hi[Kc], lo[Kc]
    with np.errstate(invalid="ignore"):
        hu, hd = (H >= up[:, None]) & valid, (L <= dn[:, None]) & valid
    BIG = h + 1
    fu = np.where(hu.any(1), hu.argmax(1), BIG)
    fd = np.where(hd.any(1), hd.argmax(1), BIG)
    both = (fu == fd) & (fu < BIG)
    took_up, took_dn = (fu < fd) & (fu < BIG), (fd < fu) & (fd < BIG)
    exit_px = c[np.clip(e + h - 1, 0, N - 1)]
    cost = sp * (1.0 + slip)
    pnl = np.zeros(len(t))
    pnl[took_up] = (exit_px[took_up] - up[took_up]) - cost[took_up]
    pnl[took_dn] = (dn[took_dn] - exit_px[took_dn]) - cost[took_dn]
    if whipsaw == "stop":
        # entered on one side and stopped at the other: the full width, twice
        pnl[both] = -2 * X[both] - cost[both]
    traded = took_up | took_dn | (both if whipsaw == "stop" else
                                  np.zeros(len(t), bool))
    if traded.sum() < 50:
        return None
    return dict(n=int(len(t)), n_traded=int(traded.sum()),
                trigger_rate=float(traded.mean()),
                both_rate=float(both.mean()),
                edge=float(pnl.sum() / sp.sum()),
                edge_per_trade=float(pnl[traded].sum() / sp[traded].sum())
                if traded.sum() else np.nan)


def state_dislocation(V, k=2.0):
    r = V["ret_atr"]
    m = np.isfinite(r) & (np.abs(r) > k)
    m[:300] = False
    return np.where(m)[0]


def state_cheap_dislocation(V, q=0.25, k=1.5):
    r, sa = V["ret_atr"], V["spread_atr"]
    fin = np.isfinite(sa)
    if fin.sum() < 5000:
        return np.array([], int)
    cut = np.nanquantile(sa[fin], q)
    m = np.isfinite(r) & (np.abs(r) > k) & np.nan_to_num(sa <= cut, nan=False)
    m[:300] = False
    return np.where(m)[0]


def state_all(V):
    r = V["ret_atr"]
    m = np.isfinite(r)
    m[:300] = False
    return np.where(m)[0]


STATES = {
    "dislocation 2.0 ATR": state_dislocation,
    "cheap + dislocation 1.5": state_cheap_dislocation,
    "every bar (baseline)": state_all,
}


def cross_t(v):
    v = np.asarray([y for y in v if np.isfinite(y)], float)
    if len(v) < 3:
        return np.nan, 0, 0
    se = float(v.std(ddof=1) / math.sqrt(len(v)))
    return (float(v.mean() / se) if se > 0 else np.nan,
            int((v > 0).sum()), len(v))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols", default=",".join(MARKETS))
    a = ap.parse_args()
    t0 = time.time()
    syms = [s.strip() for s in a.symbols.split(",") if s.strip()]

    print("THE STRADDLE, ATTACKED")
    print("=" * 100)
    print(__doc__.split("WHY IT IS PLAUSIBLE")[1].split("THE SEVEN WAYS")[0])

    prepped = {}
    for sym in syms + ["USDSEK"]:
        df = load_bidask_h1(sym)
        if df is None or len(df) < 20000:
            continue
        P = X.prep(df, 60)
        prepped[sym] = (P, DIS.state_vars(P))
    panel = [s for s in prepped if s != "USDSEK"]
    print(f"  {len(panel)} panel markets plus USDSEK held back\n")

    out = {}

    # ---------------------------------------------- 1 and 2: control, whipsaw
    print("=" * 100)
    print("1-2  AGAINST A MATCHED CONTROL, AND WITH WHIPSAW SCORED HONESTLY")
    print("=" * 100)
    print(f"  {'state':<26}{'whipsaw':<10}{'edge':>9}{'C7 ctrl':>10}"
          f"{'lift':>9}{'t':>8}{'pos':>7}{'trig%':>8}{'both%':>8}")
    sec = []
    for lab, fn in STATES.items():
        for ws in ("skip", "stop"):
            per, ctl = [], []
            trig, bth = [], []
            for sym in panel:
                P, V = prepped[sym]
                t = fn(V)
                if len(t) < 300:
                    continue
                r = straddle(P, t, whipsaw=ws)
                if r is None:
                    continue
                per.append(r["edge"])
                trig.append(r["trigger_rate"])
                bth.append(r["both_rate"])
                if lab.startswith("every"):
                    continue
                d = np.ones(len(t))
                dv = np.zeros(P["N"], np.int8)
                dv[t] = 1
                Iv = np.full(P["N"], np.nan)
                Iv[t] = (np.asarray(P["c"], float)[t]
                         - 1.2 * np.asarray(P["A"], float)[t])
                dc, Ic, _ = C.build(P, dv, Iv, "C7",
                                    np.random.default_rng(SEED))
                rc = straddle(P, np.where(dc != 0)[0], whipsaw=ws)
                if rc:
                    ctl.append(rc["edge"])
            if not per:
                continue
            lift = ([p - c for p, c in zip(per, ctl)] if ctl else per)
            t_, pos, n = cross_t(lift)
            sec.append(dict(state=lab, whipsaw=ws, edge=float(np.mean(per)),
                            control=float(np.mean(ctl)) if ctl else None,
                            lift=float(np.mean(lift)), t=t_, positive=pos,
                            markets=n))
            print(f"  {lab:<26}{ws:<10}{np.mean(per):>+9.3f}"
                  f"{(np.mean(ctl) if ctl else float('nan')):>+10.3f}"
                  f"{np.mean(lift):>+9.3f}{t_:>+8.2f}{pos:>4}/{n}"
                  f"{np.mean(trig)*100:>7.1f}%{np.mean(bth)*100:>7.1f}%")
    out["control_and_whipsaw"] = sec

    # ------------------------------------------------------------ 3 slippage
    print("\n" + "=" * 100)
    print("3  SLIPPAGE ON THE STOP ENTRY - charged as extra spreads")
    print("=" * 100)
    print(f"  {'state':<26}" + "".join(f"{f'+{s}sp':>10}"
                                       for s in (0.0, 0.5, 1.0, 2.0)))
    slips = []
    for lab, fn in STATES.items():
        line, row = [], dict(state=lab)
        for sl in (0.0, 0.5, 1.0, 2.0):
            vals = []
            for sym in panel:
                P, V = prepped[sym]
                t = fn(V)
                if len(t) < 300:
                    continue
                r = straddle(P, t, slip=sl, whipsaw="stop")
                if r:
                    vals.append(r["edge"])
            v = float(np.mean(vals)) if vals else np.nan
            row[f"slip_{sl}"] = v
            line.append(v)
        slips.append(row)
        print(f"  {lab:<26}" + "".join(f"{v:>+10.3f}" for v in line))
    out["slippage"] = slips

    # ---------------------------------------------------- 4 and 5 exit, width
    print("\n" + "=" * 100)
    print("4-5  EXIT HORIZON AND BARRIER WIDTH - both were guesses")
    print("=" * 100)
    grid = []
    print(f"  {'':<10}" + "".join(f"{f'{h}bar':>10}" for h in (1, 2, 3, 4, 6)))
    for k in (0.25, 0.5, 0.75, 1.0):
        line = []
        for h in (1, 2, 3, 4, 6):
            vals = []
            for sym in panel:
                P, V = prepped[sym]
                t = state_dislocation(V)
                if len(t) < 300:
                    continue
                r = straddle(P, t, h=h, k=k, whipsaw="stop")
                if r:
                    vals.append(r["edge"])
            v = float(np.mean(vals)) if vals else np.nan
            grid.append(dict(k=k, h=h, edge=v))
            line.append(v)
        print(f"  k={k:<8.2f}" + "".join(f"{v:>+10.3f}" for v in line))
    out["grid"] = grid

    # --------------------------------------------------------- 6 and 7 splits
    print("\n" + "=" * 100)
    print("6-7  BOTH ERAS, AND THE MARKET THAT HAD NO PART IN THIS")
    print("=" * 100)
    print(f"  {'state':<26}{'2004-2016':>12}{'pos':>7}{'2017-2026':>12}"
          f"{'pos':>7}{'USDSEK':>10}")
    final = []
    for lab, fn in STATES.items():
        rec = dict(state=lab)
        for per_lab, keep in (("2004-2016", True), ("2017-2026", False)):
            vals = []
            for sym in panel:
                P, V = prepped[sym]
                t = fn(V)
                idx = pd.DatetimeIndex(P["idx"])
                m = (idx[t] < SPLIT) if keep else (idx[t] >= SPLIT)
                tt = t[m]
                if len(tt) < 300:
                    continue
                r = straddle(P, tt, whipsaw="stop")
                if r:
                    vals.append(r["edge"])
            t_, pos, n = cross_t(vals)
            rec[per_lab] = float(np.mean(vals)) if vals else np.nan
            rec[f"pos_{per_lab}"] = f"{pos}/{n}"
        if "USDSEK" in prepped:
            P, V = prepped["USDSEK"]
            t = fn(V)
            r = straddle(P, t, whipsaw="stop") if len(t) >= 300 else None
            rec["USDSEK"] = r["edge"] if r else np.nan
        final.append(rec)
        print(f"  {lab:<26}{rec['2004-2016']:>+12.3f}"
              f"{rec['pos_2004-2016']:>7}{rec['2017-2026']:>+12.3f}"
              f"{rec['pos_2017-2026']:>7}"
              f"{rec.get('USDSEK', float('nan')):>+10.3f}")
    out["splits"] = final

    print("\n" + "=" * 100)
    print("VERDICT")
    print("=" * 100)
    base = next((r for r in final if r["state"].startswith("every")), None)
    cand = [r for r in final if not r["state"].startswith("every")]
    survives = [r for r in cand
                if np.isfinite(r["2004-2016"]) and r["2004-2016"] > 0
                and np.isfinite(r["2017-2026"]) and r["2017-2026"] > 0
                and np.isfinite(r.get("USDSEK", np.nan))
                and r["USDSEK"] > (base["USDSEK"] if base else 0)]
    print(f"  {len(survives)} of {len(cand)} states stay positive in both "
          f"eras AND beat the baseline on USDSEK")
    for r in survives:
        print(f"    {r['state']}")
    print(f"\n  The baseline - a straddle armed on every bar - is "
          f"{base['2004-2016'] if base else float('nan'):+.3f} and "
          f"{base['2017-2026'] if base else float('nan'):+.3f} across the two "
          f"eras and {base.get('USDSEK', float('nan')) if base else float('nan'):+.3f} "
          f"on USDSEK.")
    print(f"  Every figure above is scored with whipsaw counted as a loss,")
    print(f"  which is the honest bound when the intrabar order is unknown.")

    p = HERE / "straddle_validation.json"
    p.write_text(json.dumps(dict(
        created=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        seed=SEED, split=str(SPLIT.date()), survives=len(survives), **out),
        indent=1, default=str))
    PR.log("phase4-straddle",
           "Does the conditional breakout straddle survive a matched control, "
           "honest whipsaw, slippage, its own parameter grid, both eras and a "
           "fresh market?",
           hypothesis="expanded_three_targets",
           tools=["straddle_validation", "controls", "expanded_discovery"],
           result=out, status="MEASURED",
           finding=f"{len(survives)} of {len(cand)} states survive everything",
           next_action="record against the registered criterion",
           started=t0)
    print(f"\n  saved -> {p.name}   elapsed {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
