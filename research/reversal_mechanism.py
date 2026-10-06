#!/usr/bin/env python3
"""What the sign edge is made of, before anyone calls it a finding.

WHAT WAS MEASURED

  With no bracket, no stop, no target and no tie-break rule, the fade and the
  follow families disagree about direction in mirror image on every market:

      reversion  h=1   52.24% right   +2.60pp over control   t +16.76   9 of 9
      momentum   h=1   46.23% right   -3.46pp                t -34.07   0 of 9
      va-break   h=1   47.22% right   -2.49pp                t -11.30   0 of 9

  and all of it decays monotonically to nothing by 48 hours.

WHY THAT IS NOT YET A FINDING

  A t of 34 is not a plausible size for a market edge. And the same
  measurement weighted by MAGNITUDE gives only +0.0043 ATR at t +1.89, so
  whatever is being predicted, the wins are small and the losses are large.

  Two unexciting explanations come before any interesting one:

    the price series has unconditional one-bar negative autocorrelation, and
    any rule that fades anything inherits it without adding a thing;

    the observed price carries transient noise, the signal fires on the noise,
    and the next quote reverts by construction rather than because the market
    did anything.

  Both predict a large sign edge and a tiny magnitude edge, which is exactly
  what was seen. They are separated here rather than argued about.

THE FIVE MEASUREMENTS

  1 UNCONDITIONAL FADE   go against the previous bar's own move on every bar.
                         Whatever this earns, every fade rule gets for free.

  2 CONDITIONAL ADD      the reversion family measured against that fade
                         rather than against a random control. This is the
                         only number that says whether the representation
                         contributes anything.

  3 LAG TEST             the identical rule computed from bar t-1's close,
                         entering at the same t+1 open. Genuine multi-bar
                         reversion survives this. Anything that depends on the
                         most recent quote does not.

  4 MAGNITUDE            mean win, mean loss, and the win rate that would be
                         needed to break even - in spread units, so the
                         economic size is visible rather than implied.

  5 STABILITY            2004-2014 against 2015-2026.

WHAT EACH OUTCOME MEANS, STATED BEFORE THE RUN

  Survives the lag and beats the unconditional fade: a real conditional
  signal, and the first one this project has found.

  Survives the lag and does not beat the unconditional fade: a property of the
  price series, not of the representation. That is a genuine finding about the
  market and a negative one about 837 hypotheses of setup search, because it
  would mean the families were redundant descriptions of a single well-known
  statistic the whole time.

  Does not survive the lag: microstructure. Recorded as such and dropped.
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
import provenance as PR
import xauusd_1000_setups as X
from p01_cross_market import MARKETS, TICKS, load_bidask_h1
from profile_setups import momentum_signal, reversion_signal

SEED = 17
FLOOR = 4.74
SPLIT = "2015-01-01"


def mid_open(P):
    return (np.asarray(P["bid_o"], float) + np.asarray(P["ask_o"], float)) / 2


def move(P, t, d, h):
    """Signed move from the mid open of t+1 to the mid close of t+h."""
    o, c = mid_open(P), np.asarray(P["c"], float)
    return d * (c[t + h] - o[t + 1])


def unconditional_fade(P, h=1, lo=300):
    """Fade the previous bar's own close-to-close move, every bar."""
    N = P["N"]
    c = np.asarray(P["c"], float)
    prev = np.concatenate([[np.nan], np.diff(c)])
    t = np.arange(lo, N - h - 1)
    d = -np.sign(prev[t])
    keep = d != 0
    t, d = t[keep], d[keep]
    return t, d


def lagged(sig_fn, P, lag=1):
    """Run a signal function on a frame shifted back by `lag` bars.

    The signal is computed as if the last `lag` bars had not printed, and the
    entry stays at the same t+1 open. A rule whose edge lives in the most
    recent quote loses it; one that is reading a multi-bar extension does not.
    Shifting the SIGNAL rather than the entry is what keeps the comparison
    honest - moving the entry would change the cost and the horizon too."""
    Q = dict(P)
    for k in ("o", "h", "l", "c", "A", "ema20", "ema50", "sma200", "bb_u",
              "bb_l", "bb_m", "eps", "z", "rsi2", "rsi14"):
        if k in P:
            v = np.asarray(P[k], float)
            Q[k] = np.concatenate([np.full(lag, np.nan), v[:-lag]])
    d, I = sig_fn(Q)
    return d, I


def sign_rate(P, t, d, h):
    m = move(P, t, d, h)
    ok = np.isfinite(m)
    if ok.sum() < 200:
        return None
    return dict(n=int(ok.sum()), rate=float((m[ok] > 0).mean()),
                mean=float(m[ok].mean()), vals=m[ok], t_idx=t[ok])


def magnitude(m, spread_at, cost_spreads=1.0):
    """Win/loss asymmetry and the breakeven win rate, in spread units.

    TWO BREAKEVENS, AND THE SECOND IS THE ONE THAT DECIDES

      breakeven_gross is ml/(mw+ml): the win rate needed for the wins to pay
      for the losses. It ignores the cost of trading entirely, and quoting it
      alone would say a 52% win rate against a 51.75% requirement is a
      profitable edge.

      breakeven_net adds the round trip. The move here is measured mid to mid;
      a real trade buys at the ask and sells at the bid, so it pays one full
      spread. The win rate then has to satisfy

          p*mw - (1-p)*ml = cost      ->   p = (cost + ml) / (mw + ml)

      which on this book is around 57%, not 51.75%. The gap between the two
      numbers is the entire distance between an information finding and a
      trading one."""
    ok = np.isfinite(m) & np.isfinite(spread_at) & (spread_at > 0)
    if ok.sum() < 200:
        return None
    x = m[ok] / spread_at[ok]
    w, l = x[x > 0], x[x <= 0]
    if len(w) < 50 or len(l) < 50:
        return None
    mw, ml = float(w.mean()), float(-l.mean())
    tot = mw + ml
    return dict(win_rate=float(len(w) / len(x)), mean_win=mw, mean_loss=ml,
                payoff=mw / ml if ml > 0 else np.nan,
                breakeven_gross=ml / tot if tot > 0 else np.nan,
                breakeven_net=((cost_spreads + ml) / tot
                               if tot > 0 else np.nan),
                edge_spreads=float(x.mean()),
                net_edge_spreads=float(x.mean()) - cost_spreads)


def cross_t(vals):
    v = np.asarray([x for x in vals if np.isfinite(x)], float)
    if len(v) < 3:
        return np.nan, 0, 0
    se = float(v.std(ddof=1) / math.sqrt(len(v)))
    return (float(v.mean() / se) if se > 0 else np.nan,
            int((v > 0).sum()), len(v))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols", default=",".join(MARKETS))
    ap.add_argument("--h", type=int, default=1)
    a = ap.parse_args()
    t0 = time.time()
    syms = [s.strip() for s in a.symbols.split(",") if s.strip()]
    h = a.h

    print(f"WHAT THE SIGN EDGE IS MADE OF - horizon {h} bar(s)")
    print("=" * 110)
    print(__doc__.split("THE FIVE MEASUREMENTS")[1]
          .split("WHAT EACH OUTCOME MEANS")[0])

    rows = []
    print(f"  {'market':<9}{'uncond fade':>13}{'reversion':>11}"
          f"{'vs C7':>9}{'vs fade':>10}{'lag-1':>9}{'lag add':>10}"
          f"{'n':>9}")
    for sym in syms:
        df = load_bidask_h1(sym)
        if df is None or len(df) < 20000:
            continue
        P = X.prep(df, 60)
        spread = np.asarray(P["spread"], float)

        tf, dfd = unconditional_fade(P, h)
        u = sign_rate(P, tf, dfd, h)

        d, I = reversion_signal(P)
        tr = np.where(np.asarray(d) != 0)[0]
        tr = tr[(tr >= 300) & (tr + h < P["N"] - 1)]
        r = sign_rate(P, tr, np.asarray(d)[tr].astype(float), h)

        dc, Ic, _ = C.build(P, d, I, "C7", np.random.default_rng(SEED))
        tc = np.where(dc != 0)[0]
        tc = tc[(tc >= 300) & (tc + h < P["N"] - 1)]
        cc = sign_rate(P, tc, np.asarray(dc)[tc].astype(float), h)

        dl, Il = lagged(reversion_signal, P, lag=1)
        tl = np.where(np.asarray(dl) != 0)[0]
        tl = tl[(tl >= 300) & (tl + h < P["N"] - 1)]
        lg = sign_rate(P, tl, np.asarray(dl)[tl].astype(float), h)

        if not all((u, r, cc, lg)):
            continue
        mg = magnitude(r["vals"], spread[r["t_idx"]])
        mgu = magnitude(u["vals"], spread[u["t_idx"]])

        idx = pd.DatetimeIndex(P["idx"])
        early = idx[r["t_idx"]] < pd.Timestamp(SPLIT, tz="UTC")
        rec = dict(symbol=sym, n=r["n"], n_fade=u["n"],
                   fade_rate=u["rate"], rev_rate=r["rate"],
                   ctrl_rate=cc["rate"], lag_rate=lg["rate"],
                   skill_vs_ctrl=r["rate"] - cc["rate"],
                   skill_vs_fade=r["rate"] - u["rate"],
                   lag_skill_vs_ctrl=lg["rate"] - cc["rate"],
                   early_rate=float((r["vals"][early] > 0).mean())
                   if early.sum() > 200 else np.nan,
                   late_rate=float((r["vals"][~early] > 0).mean())
                   if (~early).sum() > 200 else np.nan,
                   magnitude=mg, magnitude_fade=mgu)
        rows.append(rec)
        print(f"  {sym:<9}{u['rate']*100:>12.2f}%{r['rate']*100:>10.2f}%"
              f"{(r['rate']-cc['rate'])*100:>+8.2f}"
              f"{(r['rate']-u['rate'])*100:>+9.2f}"
              f"{lg['rate']*100:>8.2f}%"
              f"{(lg['rate']-cc['rate'])*100:>+9.2f}{r['n']:>9,}", flush=True)

    if not rows:
        print("\n  nothing measured")
        return
    D = pd.DataFrame(rows)

    print("\n" + "=" * 110)
    print("1-2  DOES THE REPRESENTATION ADD ANYTHING TO A PLAIN FADE?")
    print("=" * 110)
    for lab, col in (("reversion vs C7 control", "skill_vs_ctrl"),
                     ("unconditional fade vs 50%", None),
                     ("reversion vs unconditional fade", "skill_vs_fade")):
        if col is None:
            v = (D.fade_rate - 0.5).to_numpy(float)
        else:
            v = D[col].to_numpy(float)
        t, pos, n = cross_t(v)
        print(f"  {lab:<34}{np.nanmean(v)*100:>+8.2f}pp   t {t:>+7.2f}   "
              f"positive on {pos}/{n}")

    print("\n" + "=" * 110)
    print("3  THE LAG TEST - is the edge in the most recent quote?")
    print("=" * 110)
    t0_, p0, n0 = cross_t(D.skill_vs_ctrl.to_numpy(float))
    t1_, p1, n1 = cross_t(D.lag_skill_vs_ctrl.to_numpy(float))
    m0 = float(D.skill_vs_ctrl.mean())
    m1 = float(D.lag_skill_vs_ctrl.mean())
    retained = m1 / m0 if abs(m0) > 1e-9 else np.nan
    print(f"  signal from bar t      {m0*100:+.2f}pp   t {t0_:+.2f}   "
          f"positive on {p0}/{n0}")
    print(f"  signal from bar t-1    {m1*100:+.2f}pp   t {t1_:+.2f}   "
          f"positive on {p1}/{n1}")
    print(f"  retained {retained:.0%} - below half is microstructure, not "
          f"multi-bar reversion")

    print("\n" + "=" * 110)
    print("4  MAGNITUDE - what the sign edge is worth in round trips")
    print("=" * 110)
    econ = []
    for lab, key in (("reversion", "magnitude"),
                     ("unconditional fade", "magnitude_fade")):
        mgs = [r[key] for r in rows if r[key]]
        if not mgs:
            continue
        wr = np.mean([m["win_rate"] for m in mgs])
        mw = np.mean([m["mean_win"] for m in mgs])
        ml = np.mean([m["mean_loss"] for m in mgs])
        bg = np.mean([m["breakeven_gross"] for m in mgs])
        bn = np.mean([m["breakeven_net"] for m in mgs])
        ed = np.mean([m["edge_spreads"] for m in mgs])
        nd = np.mean([m["net_edge_spreads"] for m in mgs])
        econ.append(dict(label=lab, win_rate=float(wr), mean_win=float(mw),
                         mean_loss=float(ml), breakeven_gross=float(bg),
                         breakeven_net=float(bn), edge_spreads=float(ed),
                         net_edge_spreads=float(nd)))
        print(f"  {lab:<22}win rate {wr*100:.2f}%   mean win {mw:+.3f} "
              f"spreads   mean loss {ml:.3f}   payoff {mw/ml:.3f}")
        print(f"  {'':<22}breakeven ignoring cost {bg*100:.2f}%   "
              f"measured {wr*100:.2f}%   "
              f"{'above' if wr > bg else 'below'} it")
        print(f"  {'':<22}breakeven PAYING ONE SPREAD {bn*100:.2f}%   "
              f"measured {wr*100:.2f}%   "
              f"{'ABOVE' if wr > bn else 'SHORT BY ' + f'{(bn-wr)*100:.2f}pp'}")
        print(f"  {'':<22}gross edge {ed:+.4f} spreads per trade, "
              f"net of the round trip {nd:+.4f}\n")

    print("=" * 110)
    print("5  STABILITY")
    print("=" * 110)
    te, pe, ne = cross_t((D.early_rate - 0.5).to_numpy(float))
    tl2, pl, nl = cross_t((D.late_rate - 0.5).to_numpy(float))
    print(f"  2004-2014   sign rate {D.early_rate.mean()*100:.2f}%   "
          f"t vs 50% {te:+.2f}   positive on {pe}/{ne}")
    print(f"  2015-2026   sign rate {D.late_rate.mean()*100:.2f}%   "
          f"t vs 50% {tl2:+.2f}   positive on {pl}/{nl}")

    t_add, pos_add, n_add = cross_t(D.skill_vs_fade.to_numpy(float))
    verdict = ("CONDITIONAL SIGNAL" if (np.isfinite(t_add) and t_add > FLOOR
                                        and pos_add >= 6
                                        and np.isfinite(retained)
                                        and retained >= 0.5)
               else "MICROSTRUCTURE" if (np.isfinite(retained)
                                         and retained < 0.5)
               else "PROPERTY OF THE SERIES, NOT THE REPRESENTATION")
    print(f"\n  VERDICT: {verdict}")

    out = HERE / "reversal_mechanism.json"
    out.write_text(json.dumps(dict(
        created=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        horizon=h, floor=FLOOR, per_market=rows,
        add_over_fade=dict(mean=float(D.skill_vs_fade.mean()), t=t_add,
                           positive=pos_add, markets=n_add),
        lag_retained=retained, verdict=verdict, economics=econ,
        manifest=PR.manifest(dict(h=h, seed=SEED),
                             [HERE / ".cache_duka" /
                              f"{s}_H1_2003_2026.parquet" for s in syms])),
        indent=1, default=str))
    PR.log("phase1-mechanism",
           "Is the short-horizon sign edge a conditional signal, a property "
           "of the price series, or microstructure?",
           hypothesis="short_horizon_reversal_mechanism",
           tools=["reversal_mechanism", "controls"],
           result=dict(add_over_fade_t=t_add, lag_retained=retained,
                       verdict=verdict),
           status=verdict, finding=verdict,
           next_action="record against the registered criterion",
           started=t0)
    print(f"\n  saved -> {out.name}   elapsed {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
