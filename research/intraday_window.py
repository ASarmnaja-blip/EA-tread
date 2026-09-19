#!/usr/bin/env python3
"""The last lever: a hold that never spans a rollover pays no financing.

THE ERROR IN THE MODEL THAT KILLED EVERY HORIZON

  timeframe_ratio charged financing as w * T / 24, continuously. That is right
  on average and wrong in a way that matters: swap is charged at ONE MOMENT,
  the daily rollover. A position opened and closed inside the same session
  pays exactly none of it.

  This repository's own cost rules already say so - force a close thirty
  minutes before rollover, never hold through it. The economic model ignored
  its own rules.

WHAT THAT DOES TO THE SHAPE

  With the linear financing term gone there is no single maximum. The cost is
  a constant, so longer is strictly better and the only cap is the session
  itself.

  The exponent this was first written against was +0.536, and on that number
  the edge reached the live account's quoted 260-point gold spread at about
  thirteen hours - inside one session, and close enough to breakeven to be
  worth measuring rather than trusting.

  That exponent was wrong. It came from a mean of move-over-spread ratios,
  which is what a trader earns only by sizing inversely to each trade's own
  spread. On the ratio of means - total move over total spread, which is what
  a constant-lot trader earns - the exponent is +0.233 and H1 to W1 is 3.7x
  over a 168x bar length where a square root would give 13x. At +0.233 the
  edge would not reach one round trip until about 8,900 hours, which is a
  year, so the extrapolation this file was built to check no longer points
  anywhere reachable.

  The measurement below stands on its own regardless, and is the reason the
  extrapolation was never trusted in the first place.

WHY THE SIGNAL IS RECOMPUTED RATHER THAN HELD

  The scaling law was measured on BARS: a four-hour edge means a signal formed
  from four-hour bars, not a one-hour signal held four times as long. The
  hourly effect decayed to nothing by 48 hours when the same signal was simply
  held longer, so reusing it here would measure decay and call it horizon. For
  a hold of L hours the signal is the market's own move over the previous L
  hours.

WHAT THIS CANNOT RESCUE

  If the best cell falls short, there is nothing behind it. Financing was the
  last lever the economics leaves - the spread cannot be negotiated, the
  effect cannot be made larger by searching, and the horizon is capped by the
  session. The size of the shortfall, measured rather than extrapolated, is
  then the final answer.
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
HOLDS = (1, 2, 3, 4, 6, 8, 12)
LAST_EXIT = 20            # 21:00 UTC is the rollover; be out before it
FLOOR = 4.85
LIVE_GOLD_SPREAD_POINTS = 260.0     # from the live account spec


def build_rows(P):
    """Index bars by day and hour so a window can be located exactly."""
    idx = pd.DatetimeIndex(P["idx"])
    return idx.normalize().values, idx.hour.to_numpy()


def window_trades(P, day, hour, entry_h, L):
    """Entry at entry_h's open, exit at (entry_h+L-1)'s close, same day.

    The signal is the market's own move over the previous L hours, which must
    also sit inside the same day - so a window that would reach back across a
    rollover or a weekend is not formed at all rather than formed from a gap.
    """
    exit_h = entry_h + L - 1
    if exit_h > LAST_EXIT:
        return None
    c = np.asarray(P["c"], float)
    o = (np.asarray(P["bid_o"], float) + np.asarray(P["ask_o"], float)) / 2
    ask_o, bid_o = np.asarray(P["ask_o"], float), np.asarray(P["bid_o"], float)
    N = P["N"]

    at = {}
    for h in (entry_h, exit_h, entry_h - L, entry_h - 1):
        m = hour == h
        idxs = np.where(m)[0]
        at[h] = dict(zip(day[idxs].tolist(), idxs.tolist()))
    days = sorted(set(at[entry_h]) & set(at[exit_h])
                  & set(at.get(entry_h - L, {})) & set(at.get(entry_h - 1, {})))
    if len(days) < 300:
        return None
    e = np.array([at[entry_h][d] for d in days])
    x = np.array([at[exit_h][d] for d in days])
    s0 = np.array([at[entry_h - L][d] for d in days])
    s1 = np.array([at[entry_h - 1][d] for d in days])
    ok = (e >= 300) & (x < N) & (s0 >= 0) & (s1 >= 0) & (x >= e)
    e, x, s0, s1 = e[ok], x[ok], s0[ok], s1[ok]
    if len(e) < 300:
        return None
    prev_move = c[s1] - c[s0]
    d = -np.sign(prev_move)
    keep = d != 0
    e, x, d = e[keep], x[keep], d[keep]
    sp = ask_o[e] - bid_o[e]
    move = d * (c[x] - o[e])
    fin = np.isfinite(move) & np.isfinite(sp) & (sp > 0)
    if fin.sum() < 300:
        return None
    return dict(entry=e[fin], exit=x[fin], d=d[fin],
                move=move[fin], spread=sp[fin])


def month_boot(move, spread, stamps, rng, draws=1500, cost=1.0):
    x = move / spread
    uniq = np.unique(stamps)
    if len(uniq) < 24:
        return None
    by = {m: x[stamps == m] for m in uniq}
    out = np.empty(draws)
    for i in range(draws):
        pick = rng.choice(uniq, size=len(uniq), replace=True)
        out[i] = np.concatenate([by[m] for m in pick]).mean()
    sd = float(out.std(ddof=1))
    ci = np.quantile(out, [0.025, 0.975])
    return dict(edge=float(x.mean()), se=sd,
                t=float(x.mean() / sd) if sd > 0 else np.nan,
                ci_low=float(ci[0]), ci_high=float(ci[1]),
                p_above_cost=float((out > cost).mean()))


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

    print("INTRADAY WINDOW - no rollover, therefore no financing")
    print("=" * 104)
    print(__doc__.split("WHAT THAT DOES TO THE SHAPE")[1]
          .split("WHY THE SIGNAL IS RECOMPUTED")[0])

    cells = {}
    prepped = {}
    for sym in syms:
        df = load_bidask_h1(sym)
        if df is None or len(df) < 20000:
            continue
        P = X.prep(df, 60)
        day, hour = build_rows(P)
        prepped[sym] = (P, day, hour)
        tick = TICKS.get(sym, 1e-5)
        for L in HOLDS:
            for eh in range(L, LAST_EXIT - L + 2):
                r = window_trades(P, day, hour, eh, L)
                if r is None:
                    continue
                # ratio of means, not the mean of ratios - see the note in
                # discovery.score. The mean of ratios sizes inversely to each
                # trade's own spread and reads 1.3x to 2.3x high on this data.
                x = r["move"].sum() / r["spread"].sum()
                cells.setdefault((L, eh), []).append(dict(
                    symbol=sym, n=len(r["move"]), edge=float(x),
                    edge_mean_ratio=float((r["move"] / r["spread"]).mean()),
                    points=float(np.mean(r["move"]) / tick),
                    spread_points=float(np.mean(r["spread"]) / tick),
                    sign=float((r["move"] > 0).mean())))
        print(f"  {sym:<9}{time.time()-t0:>6.0f}s", flush=True)

    rows = []
    for (L, eh), gs in cells.items():
        if len(gs) < 3:
            continue
        e = [g["edge"] for g in gs]
        t, pos, n = cross_t(e)
        rows.append(dict(hold=L, entry_hour=eh, markets=n,
                         n_per_market=int(np.mean([g["n"] for g in gs])),
                         edge=float(np.mean(e)), t=t, positive=pos,
                         points=float(np.mean([g["points"] for g in gs])),
                         spread_points=float(np.mean(
                             [g["spread_points"] for g in gs]))))
    R = pd.DataFrame(rows)
    if R.empty:
        print("  nothing measured")
        return

    print("\n" + "=" * 104)
    print("THE SURFACE - gross edge in spread units, one round trip = 1.000")
    print("=" * 104)
    print(f"  {'hold':<6}" + "".join(f"{h:>7}" for h in range(0, LAST_EXIT + 1))
          + "   <- entry hour UTC")
    for L in HOLDS:
        g = R[R.hold == L]
        line = []
        for h in range(0, LAST_EXIT + 1):
            v = g[g.entry_hour == h]
            line.append(float(v.edge.iloc[0]) if len(v) else np.nan)
        print(f"  {L:<6}" + "".join(
            ("  .   " if not np.isfinite(v) else f"{v:>7.2f}") for v in line))

    print("\n" + "=" * 104)
    print("BY HOLD LENGTH - does the scaling law hold inside a session?")
    print("=" * 104)
    print(f"  {'hold':<6}{'cells':>7}{'mean edge':>12}{'best':>9}"
          f"{'best t':>9}{'mean points':>14}{'spread pts':>13}")
    by_hold = []
    for L in HOLDS:
        g = R[R.hold == L]
        if g.empty:
            continue
        b = g.loc[g.edge.idxmax()]
        by_hold.append(dict(hold=L, cells=len(g), mean=float(g.edge.mean()),
                            best=float(b.edge), best_t=float(b.t),
                            best_hour=int(b.entry_hour),
                            points=float(g.points.mean()),
                            spread_points=float(g.spread_points.mean())))
        print(f"  {L:<6}{len(g):>7}{g.edge.mean():>+12.3f}{b.edge:>+9.3f}"
              f"{b.t:>+9.2f}{g.points.mean():>+14.1f}"
              f"{g.spread_points.mean():>13.1f}")

    if len(by_hold) >= 4:
        x = np.log([r["hold"] for r in by_hold])
        y = [r["mean"] for r in by_hold]
        pos = [(a_, b_) for a_, b_ in zip(x, y) if b_ > 0]
        if len(pos) >= 4:
            sl, ic = np.polyfit([p[0] for p in pos],
                                np.log([p[1] for p in pos]), 1)
            print(f"\n  fitted exponent inside the session {sl:+.3f}, against "
                  f"+0.536 measured across bar lengths")

    print("\n" + "=" * 104)
    print("THE BEST CELLS, BOOTSTRAPPED AND CONTROLLED")
    print("=" * 104)
    top = R.sort_values("edge", ascending=False).head(5)
    detail = []
    for _, r in top.iterrows():
        L, eh = int(r.hold), int(r.entry_hour)
        allx, stamps, skills = [], [], []
        for sym, (P, day, hour) in prepped.items():
            w = window_trades(P, day, hour, eh, L)
            if w is None:
                continue
            allx.append(w["move"] / w["spread"].mean())
            stamps.append(np.asarray(pd.DatetimeIndex(P["idx"])[w["entry"]]
                                     .tz_localize(None).to_period("M")
                                     .astype(str)))
            dv = np.zeros(P["N"], np.int8)
            dv[w["entry"]] = w["d"].astype(np.int8)
            Iv = np.full(P["N"], np.nan)
            A = np.asarray(P["A"], float)
            c = np.asarray(P["c"], float)
            Iv[w["entry"]] = c[w["entry"]] - w["d"] * 1.2 * A[w["entry"]]
            dc, Ic, _ = C.build(P, dv, Iv, "C7", np.random.default_rng(SEED))
            tc = np.where(dc != 0)[0]
            sc = DIS.score(P, tc, dc[tc].astype(float), L)
            if sc:
                skills.append(float(w["move"].sum() / w["spread"].sum())
                              - sc["edge"])
        if not allx:
            continue
        # each market contributes its own move-over-spread series already
        # normalised, so the pooled bootstrap is over normalised trades and
        # the months are resampled with every market moving together
        b = month_boot(np.concatenate(allx), np.ones(sum(len(v) for v in allx)),
                       np.concatenate(stamps), np.random.default_rng(SEED))
        sk_t, sk_pos, sk_n = cross_t(skills)
        detail.append(dict(hold=L, entry_hour=eh, edge=float(r.edge),
                           cross_t=float(r.t), positive=int(r.positive),
                           markets=int(r.markets),
                           n_per_market=int(r.n_per_market),
                           boot_t=b["t"] if b else np.nan,
                           boot_ci=[b["ci_low"], b["ci_high"]] if b else None,
                           p_above_cost=b["p_above_cost"] if b else np.nan,
                           skill_c7=float(np.mean(skills)) if skills else np.nan,
                           skill_c7_t=sk_t, skill_c7_positive=sk_pos))
        print(f"  hold {L:>2}h entry {eh:02d}:00   edge {r.edge:+.3f}   "
              f"cross-market t {r.t:+.2f} on {int(r.positive)}/{int(r.markets)}"
              f"   bootstrap t {b['t'] if b else float('nan'):+.2f}")
        print(f"  {'':<22}P(edge>1 round trip) "
              f"{(b['p_above_cost'] if b else float('nan'))*100:.0f}%   "
              f"skill vs C7 {np.mean(skills) if skills else float('nan'):+.3f} "
              f"(t {sk_t:+.2f} on {sk_pos}/{sk_n})   "
              f"n/market {int(r.n_per_market):,}")

    best = max(detail, key=lambda r: r["edge"]) if detail else None
    viable = [r for r in detail if r["edge"] > 1.0
              and np.isfinite(r["boot_t"]) and r["boot_t"] > FLOOR
              and r["positive"] >= 6 and r["skill_c7"] > 0]
    print("\n" + "=" * 104)
    print("VERDICT")
    print("=" * 104)
    if best:
        print(f"  best cell: hold {best['hold']}h from {best['entry_hour']:02d}"
              f":00   edge {best['edge']:+.3f} of one round trip")
        print(f"  shortfall {1.0 - best['edge']:+.3f} spreads per trade, "
              f"MEASURED rather than extrapolated")
    print(f"  {len(viable)} cell(s) clear the registered bar")
    print(f"\n  Financing was the last lever. The spread cannot be negotiated,")
    print(f"  the effect cannot be made larger by searching - the floor rises")
    print(f"  faster than any search improves the best result - and the")
    print(f"  horizon is capped by the session. If the best cell falls short,")
    print(f"  the size of the shortfall is the answer.")

    out = HERE / "intraday_window.json"
    out.write_text(json.dumps(dict(
        created=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        holds=list(HOLDS), last_exit=LAST_EXIT, floor=FLOOR,
        live_gold_spread_points=LIVE_GOLD_SPREAD_POINTS,
        surface=rows, by_hold=by_hold, detail=detail,
        viable=len(viable),
        manifest=PR.manifest(dict(holds=list(HOLDS), seed=SEED),
                             [HERE / ".cache_duka" /
                              f"{s}_H1_2003_2026.parquet" for s in syms])),
        indent=1, default=str))
    PR.log("phase3-intraday-window",
           "With financing removed by never spanning a rollover, does the "
           "reversal reach one round trip inside a single session?",
           hypothesis="intraday_no_rollover_window",
           tools=["intraday_window", "controls"],
           result=dict(best=best, viable=len(viable), by_hold=by_hold),
           status="MEASURED",
           finding=(f"best {best['edge']:+.3f} of a round trip at "
                    f"{best['hold']}h from {best['entry_hour']:02d}:00"
                    if best else "none"),
           next_action="record; if short, this is the final economic statement",
           started=t0)
    print(f"\n  saved -> {out.name}   elapsed {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
