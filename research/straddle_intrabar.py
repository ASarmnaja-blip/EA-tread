#!/usr/bin/env python3
"""Twenty percent of the straddle's windows have an outcome H1 cannot see.

THE GAP THIS RESOLVES

  The conditional breakout straddle reads +2.498 of a round trip when windows
  that touch both barriers in one bar are scored as no trade, and -0.647 when
  they are scored as entered and immediately stopped. Those are not two
  opinions; they are the two bounds, and the answer is between them.

  The gap is worth three round trips per armed window, which is larger than
  every other effect this project has measured put together. It exists because
  19.9% of the candidate's windows touch both barriers inside one hour -
  against 7.9% on an unconditioned bar, since the state is selected for
  volatility and volatility is what makes a bar span both levels.

  Neither bound is a measurement. Both are assumptions about an order nobody
  looked at.

HOW IT IS RESOLVED

  The same way the G12 tie-break was: with minute data. Gold has 2019-2026 at
  one-minute resolution, so for every ambiguous H1 bar the minute path says
  which barrier was touched first, whether the other was touched afterwards,
  and where the position stood at the window's close.

  That is a real measurement of the thing both bounds were guessing at.

WHAT IT CANNOT DO

  Gold only, and only from 2019. Applying the resolved rate to EURUSD or to
  gold before 2019 would be assumption wearing a measurement's clothes, which
  is the specific error this file exists to correct. Whatever it finds is
  reported as a gold figure for a seven-year window and the panel result stays
  bounded rather than resolved.
"""
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
import straddle_validation as SV
import xauusd_1000_setups as X
from p01_cross_market import load_bidask_h1

H = 3
K = 0.5


def minute_frame():
    import fetch_dukascopy as D
    m = D.load("2019-01-01", None, verbose=False)
    if m is None or len(m) == 0:
        return None
    for k in ("open", "high", "low", "close"):
        m[k] = (m[f"bid_{k}"] + m[f"ask_{k}"]) / 2
    return m[(m.high > m.low) & (m.ask_close > m.bid_close)]


def resolve(P, t, m1, h=H, k=K):
    """Walk the ambiguous windows and ask the minutes inside them."""
    N = P["N"]
    A = np.asarray(P["A"], float)
    o = (np.asarray(P["bid_o"], float) + np.asarray(P["ask_o"], float)) / 2
    c = np.asarray(P["c"], float)
    hi, lo = np.asarray(P["h"], float), np.asarray(P["l"], float)
    ask_o, bid_o = np.asarray(P["ask_o"], float), np.asarray(P["bid_o"], float)
    idx = pd.DatetimeIndex(P["idx"])
    t = np.asarray(t)
    t = t[(t >= 300) & (t + h + 1 < N)]
    e = t + 1
    entry, X, sp = o[e], k * A[t], ask_o[e] - bid_o[e]
    ok = np.isfinite(entry) & np.isfinite(X) & (X > 0) & np.isfinite(sp) & (sp > 0)
    t, e, entry, X, sp = t[ok], e[ok], entry[ok], X[ok], sp[ok]
    up, dn = entry + X, entry - X
    K_ = e[:, None] + np.arange(h)[None, :]
    Kc = np.clip(K_, 0, N - 1)
    with np.errstate(invalid="ignore"):
        hu = hi[Kc] >= up[:, None]
        hd = lo[Kc] <= dn[:, None]
    BIG = h + 1
    fu = np.where(hu.any(1), hu.argmax(1), BIG)
    fd = np.where(hd.any(1), hd.argmax(1), BIG)
    amb = np.where((fu == fd) & (fu < BIG))[0]
    if len(amb) == 0:
        return None

    rows = []
    for j in amb:
        bar = int(e[j] + fu[j])
        t0 = idx[bar]
        t1 = t0 + pd.Timedelta(hours=1)
        w = m1.loc[(m1.index >= t0) & (m1.index < t1)]
        if len(w) < 5:
            rows.append(dict(resolved=False))
            continue
        wh = w["high"].to_numpy()
        wl = w["low"].to_numpy()
        iu = np.where(wh >= up[j])[0]
        idn = np.where(wl <= dn[j])[0]
        if len(iu) == 0 and len(idn) == 0:
            rows.append(dict(resolved=False))
            continue
        a_ = iu[0] if len(iu) else 10 ** 9
        b_ = idn[0] if len(idn) else 10 ** 9
        if a_ == b_:
            rows.append(dict(resolved=False))   # same MINUTE, still ambiguous
            continue
        first_up = a_ < b_
        # after entering on the first side, was the other side reached before
        # the window closed?
        rest = m1.loc[(m1.index >= t0 + pd.Timedelta(minutes=int(min(a_, b_))))
                      & (m1.index < idx[min(int(e[j] + h - 1), N - 1)]
                         + pd.Timedelta(hours=1))]
        if first_up:
            stopped = bool((rest["low"] <= dn[j]).any()) if len(rest) else False
            px = dn[j] if stopped else c[min(int(e[j] + h - 1), N - 1)]
            pnl = (px - up[j]) - sp[j]
        else:
            stopped = bool((rest["high"] >= up[j]).any()) if len(rest) else False
            px = up[j] if stopped else c[min(int(e[j] + h - 1), N - 1)]
            pnl = (dn[j] - px) - sp[j]
        rows.append(dict(resolved=True, first_up=bool(first_up),
                         stopped_out=stopped,
                         pnl_spreads=float(pnl / sp[j])))
    got = [r for r in rows if r.get("resolved")]
    if not got:
        return None
    pnls = np.array([r["pnl_spreads"] for r in got])
    return dict(ambiguous=int(len(amb)), resolved=len(got),
                unresolved=int(len(amb) - len(got)),
                stopped_share=float(np.mean([r["stopped_out"] for r in got])),
                mean_pnl_spreads=float(pnls.mean()),
                share_profitable=float((pnls > 0).mean()))


def main():
    t0 = time.time()
    print("RESOLVING THE STRADDLE'S AMBIGUOUS WINDOWS WITH MINUTE DATA")
    print("=" * 96)
    print(__doc__.split("HOW IT IS RESOLVED")[1].split("WHAT IT CANNOT DO")[0])

    m1 = minute_frame()
    if m1 is None:
        print("  no minute data")
        return
    print(f"  {len(m1):,} minute bars  {m1.index[0].date()} -> "
          f"{m1.index[-1].date()}")

    df = load_bidask_h1("XAUUSD")
    df = df[df.index >= m1.index[0]]
    P = X.prep(df, 60)
    V = DIS.state_vars(P)
    print(f"  {P['N']:,} H1 bars in the same window\n")

    print("=" * 96)
    print(f"  {'state':<26}{'ambiguous':>11}{'resolved':>10}"
          f"{'stopped out':>13}{'mean pnl':>11}{'profitable':>12}")
    rows = {}
    for lab, fn in SV.STATES.items():
        t = fn(V)
        if len(t) < 100:
            continue
        r = resolve(P, t, m1)
        if not r:
            print(f"  {lab:<26}{'nothing resolvable':>40}")
            continue
        rows[lab] = r
        print(f"  {lab:<26}{r['ambiguous']:>11,}{r['resolved']:>10,}"
              f"{r['stopped_share']*100:>12.1f}%"
              f"{r['mean_pnl_spreads']:>+11.3f}"
              f"{r['share_profitable']*100:>11.1f}%")

    print("\n" + "=" * 96)
    print("WHAT THAT DOES TO THE TWO BOUNDS")
    print("=" * 96)
    print(f"  {'state':<26}{'skip (optimistic)':>19}{'resolved':>11}"
          f"{'stop (pessimistic)':>20}")
    final = []
    for lab, fn in SV.STATES.items():
        t = fn(V)
        if len(t) < 100:
            continue
        a = SV.straddle(P, t, whipsaw="skip")
        b = SV.straddle(P, t, whipsaw="stop")
        r = rows.get(lab)
        if not (a and b and r):
            continue
        # replace the assumed value of the ambiguous windows with the measured
        # one, weighted by their share of all armed windows
        share = r["ambiguous"] / max(a["n"], 1)
        mid = a["edge"] + share * r["mean_pnl_spreads"]
        final.append(dict(state=lab, skip=a["edge"], resolved=mid,
                          stop=b["edge"], ambiguous_share=share,
                          measured_pnl=r["mean_pnl_spreads"]))
        print(f"  {lab:<26}{a['edge']:>+19.3f}{mid:>+11.3f}"
              f"{b['edge']:>+20.3f}")

    base = next((r for r in final if r["state"].startswith("every")), None)
    cand = [r for r in final if not r["state"].startswith("every")]
    print(f"\n  gold only, {m1.index[0].date()} to {m1.index[-1].date()}. "
          f"Nothing here transfers to the other markets or to gold before "
          f"2019.")
    if base and cand:
        best = max(cand, key=lambda r: r["resolved"])
        print(f"  on the resolved figure the best state is "
              f"{best['state']} at {best['resolved']:+.3f} against a baseline "
              f"of {base['resolved']:+.3f}")
        print(f"  {'ABOVE one round trip' if best['resolved'] > 0 else 'still below breakeven'}")

    out = HERE / "straddle_intrabar.json"
    out.write_text(json.dumps(dict(
        created=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        symbol="XAUUSD", window=[str(m1.index[0].date()),
                                 str(m1.index[-1].date())],
        horizon=H, k=K, per_state=rows, bounds=final,
        manifest=PR.manifest(dict(h=H, k=K),
                             [HERE / ".cache_duka" /
                              "XAUUSD_H1_2003_2026.parquet"])),
        indent=1, default=str))
    PR.log("phase4-straddle-intrabar",
           "What actually happens inside the 20% of straddle windows whose "
           "outcome H1 cannot determine?",
           hypothesis="expanded_three_targets",
           tools=["straddle_intrabar", "straddle_validation"],
           result=dict(per_state=rows, bounds=final),
           status="MEASURED",
           finding="; ".join(f"{r['state']}: skip {r['skip']:+.3f} resolved "
                             f"{r['resolved']:+.3f} stop {r['stop']:+.3f}"
                             for r in final),
           next_action="record; the panel result stays bounded",
           started=t0)
    print(f"\n  saved -> {out.name}   elapsed {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
