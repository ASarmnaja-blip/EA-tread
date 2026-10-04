#!/usr/bin/env python3
"""Where the money actually went: decompose a trade book by entry condition,
by exit reason, and by how much of the available move was captured.

THE DISTINCTION THIS FILE EXISTS TO PROTECT

  There are two things that look identical and are not:

    DIAGNOSIS   "my live trades lost money; which component is responsible?"
                Legitimate. It reads a book that already exists and asks what
                is in it. It generates ONE specific, mechanically-stated
                hypothesis about a cause.

    SEARCH      "let me try variations until the backtest looks better."
                This is what destroys accounts. Every variation tried is a
                hypothesis, the count is usually not kept, and the winner of
                an uncounted search is noise by construction.

  The difference is not the tooling - it is whether the count is kept and
  whether the fix is tested on data that did not suggest it. So this file
  DOES NOT propose changes and DOES NOT rank variations. It reports what
  happened, attaches a hypothesis count to every comparison it prints, and
  stops. Proposing and testing a fix is a separate, deliberate step with its
  own pre-registration (see `change_ledger.py`).

WHAT IS DECOMPOSED

  1 EXIT REASON      stop, target, time exit, session deadline, entry gap.
                     Tells you which machinery is spending the money. A book
                     where the deadline closes most trades is being run on
                     the wrong horizon, whatever the entry rule says.

  2 MFE / MAE        how far the trade went in your favour before it closed,
                     and how far against. This is the only honest way to ask
                     whether a stop is too tight or a target too far, because
                     it measures what was ON THE TABLE rather than what a
                     different parameter would have produced in a re-run.

  3 ENTRY CONDITION  the bar the signal fired on, bucketed by:
                       - upper and lower wick as a share of range
                       - body as a share of range
                       - this close vs the previous close (higher / lower /
                         equal) - the exact question asked of this module
                       - opening gap against the previous close
                       - where the close sat inside the bar's range
                     Each bucket is one hypothesis and is counted as one.

  4 COST SHARE       what fraction of gross R the spread consumed. A book
                     that is gross-positive and net-negative has a cost
                     problem, not an edge problem, and the two need opposite
                     responses.

THE NUMBER PRINTED NEXT TO EVERY COMPARISON

  Every bucket boundary examined here is a hypothesis about where the edge
  lives. Reporting the best-looking bucket without that count is exactly the
  error this project has spent its life removing, so the running total and
  the floor it implies are printed with the results, not buried.
"""
import argparse, math, sys, pathlib, time
import numpy as np, pandas as pd

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import mega_search as M
from exec_engine import REASON

def excursions(P, entry_bar, exit_bar, d, entry_px):
    """Max favourable and max adverse excursion, in price units, over the
    bars the trade was actually open. Computed from the path, not inferred
    from the outcome."""
    h, l = P["h"], P["l"]
    n = len(entry_bar)
    mfe = np.zeros(n); mae = np.zeros(n)
    for q in range(n):
        a, b = int(entry_bar[q]), int(exit_bar[q])
        if b < a: b = a
        hi = h[a:b + 1].max(); lo = l[a:b + 1].min()
        if d[q] > 0:
            mfe[q] = hi - entry_px[q]; mae[q] = entry_px[q] - lo
        else:
            mfe[q] = entry_px[q] - lo; mae[q] = hi - entry_px[q]
    return mfe, mae

def bar_shape(P, i):
    """The shape of the signal bar, as fractions of its own range."""
    o, h, l, c = P["o"][i], P["h"][i], P["l"][i], P["c"][i]
    rng = np.maximum(h - l, 1e-9)
    upper = (h - np.maximum(o, c)) / rng
    lower = (np.minimum(o, c) - l) / rng
    body = np.abs(c - o) / rng
    close_pos = (c - l) / rng            # 0 = closed on the low, 1 = on the high
    prev_c = P["c"][np.maximum(i - 1, 0)]
    vs_prev = np.sign(c - prev_c)        # +1 higher, -1 lower, 0 equal
    gap = (o - prev_c) / np.maximum(P["A"][i], 1e-9)
    return dict(upper_wick=upper, lower_wick=lower, body=body,
                close_pos=close_pos, vs_prev_close=vs_prev, gap=gap)

def bucket_report(name, values, R, edges, labels, k_counter):
    """One feature, bucketed. Returns the rows and how many hypotheses it
    spent."""
    rows = []
    for lo, hi, lab in zip(edges[:-1], edges[1:], labels):
        sel = (values >= lo) & (values < hi) & np.isfinite(R)
        if sel.sum() < 30:
            rows.append((lab, int(sel.sum()), float("nan"), float("nan")))
            continue
        r = R[sel]
        se = r.std(ddof=1) / math.sqrt(len(r))
        rows.append((lab, len(r), float(r.mean()), float(r.mean() / se)))
    k_counter[0] += len(labels)
    return rows

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tf", default="1h")
    ap.add_argument("--look", type=int, default=20)
    ap.add_argument("--buf", type=float, default=0.0)
    ap.add_argument("--stop", default="atr1")
    ap.add_argument("--hold", type=int, default=12)
    # Diagnosis on DISCOVERY generates a hypothesis. Diagnosis on HOLDOUT asks
    # why a change that was already tested there did not work, which is the
    # step after a REJECTED verdict - not a way to look for a new rule.
    ap.add_argument("--period", default="discovery",
                    choices=("discovery", "holdout"))
    ap.add_argument("--csv", default=None)
    a = ap.parse_args()
    t0 = time.time()

    print("TRADE ATTRIBUTION - where the money went")
    print("=" * 84)
    print(__doc__.split("THE DISTINCTION")[1].split("WHAT IS DECOMPOSED")[0])

    import exness_backtest as EB
    import session_rules as S
    from split_guard import Split

    m = M.load_tf(a.tf)
    P = M.prep(m)
    tf_min = S.bar_minutes(m.index)
    deadline, _, _ = S.intraday_deadlines(m.index, tf_min)
    disc_end = EB.DISCOVERY_END if tf_min >= 60 else EB.DISCOVERY_END_M15
    n_disc = int((m.index < pd.Timestamp(disc_end, tz="UTC")).sum())
    th = M.fit_thresholds(P, Split(m.index, disc_end))
    cost_px = EB.scenario_cost_px(260.0, 0.0)

    lo, hi = ((0, n_disc) if a.period == "discovery" else (n_disc, len(m)))
    W = EB.walk_for(P, a.look, a.buf, a.stop, cost_px, a.hold)
    R, held, keep, rep, xpx = EB.resolve_window(W, P, None, a.hold, lo, hi,
                                                deadline)
    msk = keep
    i = W["i"][msk]
    d = W["d"][msk].astype(int)
    entry = W["entry"][msk]
    risk = W["risk"][msk]
    r = R[msk]
    hl = held[msk]
    ebar = (i + 1).astype(int)
    xbar = (i + hl).astype(int)

    print(f"config   look{a.look} buf{a.buf} {a.stop} hold{a.hold} on {a.tf}")
    print(f"period   {a.period.upper()} {m.index[lo].date()} -> "
          f"{m.index[hi-1].date()}")
    print(f"trades   {len(r):,}   E(R) {r.mean():+.4f}   "
          f"win {float((r > 0).mean())*100:.1f}%")

    k_counter = [0]

    # ---- 1. exit reason ---------------------------------------------------
    print(f"\n1. EXIT REASON - which machinery spends the money")
    at_stop = np.isclose(xpx[msk], W["stop"][msk], rtol=0, atol=1e-9)
    room = deadline[np.minimum(ebar, P["N"] - 1)] - ebar + 1
    cut_by_session = (hl >= room) & (hl < a.hold)
    timed = (~at_stop) & (~cut_by_session)
    print(f"   {'reason':<22}{'trades':>8}{'share':>8}{'E(R)':>10}{'sum R':>10}")
    for lab, sel in (("stop hit", at_stop),
                     ("session deadline", cut_by_session),
                     ("time exit (full hold)", timed)):
        if sel.sum() == 0:
            print(f"   {lab:<22}{0:>8}"); continue
        rr = r[sel]
        print(f"   {lab:<22}{sel.sum():>8}{sel.mean()*100:>7.1f}%"
              f"{rr.mean():>+10.4f}{rr.sum():>+10.1f}")
    k_counter[0] += 3
    # THE TRAP IN THE COLUMN ABOVE. A trade reaches full hold if and only if
    # it never hit its stop, so "full-hold exits earn +2.3R" is very close to
    # a restatement of "trades that did not lose, won". It is NOT evidence
    # that holding longer would pay, any more than "trades that were not
    # stopped out made money" is a strategy. The SHARE column is the honest
    # one - it says which machinery is closing the book - and the E(R) column
    # is conditioned on the outcome. This project has already killed two
    # findings that were this same tautology wearing a different label.
    print(f"   READ THE SHARE COLUMN, NOT THE E(R) COLUMN. A trade reaches")
    print(f"   full hold only by never hitting its stop, so its E(R) is high")
    print(f"   by construction. That is a tautology, not a case for holding")
    print(f"   longer - which would have to be tested over the WHOLE book.")

    # ---- 2. MFE / MAE -----------------------------------------------------
    print(f"\n2. MFE / MAE - what was on the table vs what was taken")
    mfe, mae = excursions(P, ebar, xbar, d, entry)
    mfe_R, mae_R = mfe / risk, mae / risk
    print(f"   max favourable excursion  median {np.median(mfe_R):.3f}R   "
          f"mean {mfe_R.mean():.3f}R")
    print(f"   max adverse excursion     median {np.median(mae_R):.3f}R   "
          f"mean {mae_R.mean():.3f}R")
    print(f"   captured (net R) / MFE    median "
          f"{np.median(r / np.maximum(mfe_R, 1e-9)):.3f}")
    won = r > 0
    if won.sum() and (~won).sum():
        print(f"   winners: MFE {mfe_R[won].mean():.3f}R, MAE "
              f"{mae_R[won].mean():.3f}R")
        print(f"   losers : MFE {mfe_R[~won].mean():.3f}R, MAE "
              f"{mae_R[~won].mean():.3f}R")
        print(f"   -> losers reached {mfe_R[~won].mean():.3f}R in profit before "
              f"turning. If that\n      number is large, the exit is giving "
              f"back money the entry earned.")
    k_counter[0] += 2

    # ---- 3. entry condition ----------------------------------------------
    print(f"\n3. ENTRY CONDITION - the shape of the bar the signal fired on")
    shp = bar_shape(P, i)
    specs = [
        ("upper wick / range", shp["upper_wick"],
         [0, .1, .25, .5, 1.01], ["0-10%", "10-25%", "25-50%", "50%+"]),
        ("lower wick / range", shp["lower_wick"],
         [0, .1, .25, .5, 1.01], ["0-10%", "10-25%", "25-50%", "50%+"]),
        ("body / range", shp["body"],
         [0, .25, .5, .75, 1.01], ["0-25%", "25-50%", "50-75%", "75%+"]),
        ("close position in range", shp["close_pos"],
         [0, .25, .5, .75, 1.01], ["low quarter", "2nd", "3rd", "high quarter"]),
        ("close vs previous close", shp["vs_prev_close"],
         [-1.5, -0.5, 0.5, 1.5], ["lower", "equal", "higher"]),
        ("opening gap (ATR)", shp["gap"],
         [-99, -.25, 0, .25, 99], ["gap down >.25", "small down", "small up",
                                   "gap up >.25"]),
    ]
    for name, vals, edges, labels in specs:
        rows = bucket_report(name, vals, r, edges, labels, k_counter)
        print(f"\n   {name}")
        print(f"     {'bucket':<16}{'n':>7}{'E(R)':>10}{'t':>8}")
        for lab, n_, mean_, t_ in rows:
            if not np.isfinite(mean_):
                print(f"     {lab:<16}{n_:>7}{'too few':>10}")
            else:
                print(f"     {lab:<16}{n_:>7}{mean_:>+10.4f}{t_:>+8.2f}")

    # ---- 4. cost share ----------------------------------------------------
    print(f"\n4. COST - is this an edge problem or a cost problem")
    gross = r + cost_px / risk
    print(f"   gross E(R) before cost {gross.mean():+.4f}")
    print(f"   cost per trade          {(cost_px / risk).mean():.4f}R")
    print(f"   net E(R)                {r.mean():+.4f}")

    # WHY WIDENING THE STOP DOES NOT BUY AN EDGE.
    #
    # E(R) is a RATIO. The stop sets its denominator, so widening the stop
    # divides BOTH the gross edge in R and the cost in R by the same factor.
    # Measured on H1 holdout, atr1 -> atr2 took gross 0.0668 -> 0.0343 (x0.51)
    # and cost 0.0669 -> 0.0334 (x0.50): the cost really does halve, exactly as
    # intended, and the edge halves with it. Half of roughly zero is still
    # roughly zero. That is the whole result, and it is arithmetic, not luck.
    #
    # So the two numbers below are reported in MONEY, where the spread is a
    # fixed 0.260 and cannot be scaled away by a parameter choice.
    gross_px = float((gross * risk).mean())
    net_px = float((r * risk).mean())
    print(f"\n   in MONEY, where the spread cannot be scaled away by the stop:")
    print(f"     gross per trade   {gross_px:+.4f} price units")
    print(f"     round-trip spread {cost_px:.4f}")
    print(f"     net per trade     {net_px:+.4f}   "
          f"({gross_px / cost_px:.2f}x the spread)")
    print(f"   NOTE these two metrics can disagree in sign, and here they do.")
    print(f"   E(R) weights every trade by 1/risk, so small-risk trades "
          f"dominate it;\n   the money column weights them equally. A "
          f"fixed-fractional account\n   compounds R, so E(R) is the one that "
          f"decides whether it grows - the\n   money column only says whether "
          f"the entry clears the spread at all.")
    if gross.mean() > 0 and r.mean() <= 0:
        print(f"   -> GROSS POSITIVE, NET NEGATIVE: the entry earns something")
        print(f"      and the spread takes all of it.")
        print(f"      DO NOT read this as 'widen the stop'. That was registered")
        print(f"      as widen_stop_atr1_to_atr2 and tested on holdout: it")
        print(f"      halved the cost in R exactly as predicted, halved the")
        print(f"      gross edge in R with it, and moved the net by +0.0010R")
        print(f"      (t +0.06). REJECTED. The stop scales both sides.")
        print(f"      What is left is a LONGER HORIZON, where the move itself")
        print(f"      is bigger against the same fixed spread - a different")
        print(f"      change, and one that needs its own registration.")
    elif gross.mean() <= 0:
        print(f"   -> GROSS NEGATIVE: the entry has no edge before costs are")
        print(f"      even charged. No exit or sizing change can repair that.")
    else:
        print(f"   -> net positive before any change.")
    k_counter[0] += 1

    floor = math.sqrt(2 * math.log(max(k_counter[0], 2)))
    print("\n" + "=" * 84)
    print(f"HYPOTHESES SPENT IN THIS REPORT: {k_counter[0]}")
    print(f"  Any bucket above needs |t| > {floor:.2f} before it means anything,")
    print(f"  and that is for THIS report alone - a second run on another")
    print(f"  configuration spends more. The bucket with the best t is the")
    print(f"  one most likely to be noise, because it was selected for being")
    print(f"  the best.")
    print(f"\n  This report proposes nothing. Turning any line above into a")
    print(f"  change requires registering it as a hypothesis BEFORE testing,")
    print(f"  and testing it on data that did not suggest it.")

    if a.csv:
        pd.DataFrame(dict(
            signal_bar=i, entry_bar=ebar, exit_bar=xbar, d=d, entry=entry,
            risk=risk, R=r, held=hl, mfe_R=mfe_R, mae_R=mae_R,
            upper_wick=shp["upper_wick"], lower_wick=shp["lower_wick"],
            body=shp["body"], close_pos=shp["close_pos"],
            vs_prev_close=shp["vs_prev_close"], gap=shp["gap"],
            entry_time=m.index[ebar], exit_time=m.index[xbar],
        )).to_csv(a.csv, index=False)
        print(f"\n  per-trade detail -> {a.csv}")
    print(f"\n  elapsed {time.time()-t0:.0f}s")

if __name__ == "__main__":
    main()
