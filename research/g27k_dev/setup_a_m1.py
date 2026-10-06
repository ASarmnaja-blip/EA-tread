#!/usr/bin/env python3
"""Setup A again, with the path inside each M15 bar resolved on M1.

setup_a_eras.py walked M15 bars and, when one bar touched both the stop and
the 2R target, counted the stop. With Setup A's tight stops that happens
often, so the M15 walk is biased against it. Here signals are the same (M15
Asian sweep + close back inside), but stop / target / 21:00 exit are walked on
the M1 mid path; only when one M1 bar touches both is the stop counted.
Reported per year: net R (real Dukascopy bid/ask spread), gross R (zero
cost), the matched random-entry control, the share of trades where the old
M15 walk was ambiguous, and the median spread in USD.

Usage: python3 research/g27k_dev/setup_a_m1.py
"""
import json
import pathlib
import sys

import numpy as np
import pandas as pd

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))
import fetch_dukascopy as DK
import setup_a_eras as SA


def m1_year(y):
    d = pd.read_parquet(DK.CACHE / f"XAUUSD_M1_{y}.parquet")
    return pd.DataFrame(dict(h=(d.bid_high + d.ask_high) / 2, l=(d.bid_low + d.ask_low) / 2, c=(d.bid_close + d.ask_close) / 2,
                             o=(d.bid_open + d.ask_open) / 2, s=d.ask_close - d.bid_close), index=d.index)


def walk(m1, t0, d, stop):
    """Entry at the M1 open at t0; returns (gross R, spread at exit, exit time)."""
    x = m1[(m1.index >= t0)]
    x = x[x.index.normalize() == t0.normalize()]
    if not len(x):
        return None
    ep = x.o.iat[0]
    sl, tp = ep - d * stop, ep + d * 2 * stop
    h, l = x.h.to_numpy(), x.l.to_numpy()
    hit_sl = (l <= sl) if d > 0 else (h >= sl)
    hit_tp = (h >= tp) if d > 0 else (l <= tp)
    late = x.index.hour >= 21
    i_sl = np.argmax(hit_sl) if hit_sl.any() else 10 ** 9
    i_tp = np.argmax(hit_tp) if hit_tp.any() else 10 ** 9
    i_lt = np.argmax(late) if late.any() else len(x) - 1
    i = min(i_sl, i_tp, i_lt)
    px = sl if i == i_sl else tp if i == i_tp else x.c.iat[i]
    return d * (px - ep) / stop, x.s.iat[min(i, len(x) - 1)], ep


def main():
    b = SA.m15()
    rng = np.random.default_rng(5)
    rows = []
    for y in SA.YEARS:
        p = DK.CACHE / f"XAUUSD_M1_{y}.parquet"
        if not p.exists():
            continue
        m1 = m1_year(y)
        by = b[b.index.year == y]
        for date, day in by.groupby(by.index.date):
            asia = day[day.index.hour < 7]
            if len(asia) < 20:
                continue
            ah, al = asia.h.max(), asia.l.min()
            win = np.flatnonzero((day.index.hour >= 7) & (day.index.hour < 16))
            if len(win) < 10:
                continue
            m1d = m1[m1.index.normalize() == pd.Timestamp(date, tz="UTC")]
            done = set()
            for k in win[:-1]:
                a = day.atr.iat[k]
                if not np.isfinite(a) or a <= 0:
                    continue
                for side, swept in (("H", day.h.iat[k] >= ah + 0.1 * a and day.c.iat[k] < ah),
                                    ("L", day.l.iat[k] <= al - 0.1 * a and day.c.iat[k] > al)):
                    if side in done or not swept:
                        continue
                    done.add(side)
                    d = -1 if side == "H" else 1
                    ext = day.h.iat[k] if side == "H" else day.l.iat[k]
                    t0 = day.index[k + 1]
                    stop = abs(day.o.iat[k + 1] - ext) + 0.1 * a
                    r = walk(m1d, t0, d, stop)
                    if r is None or stop <= 0:
                        continue
                    g, s_out, ep = r
                    s_in = day.s.iat[k + 1]
                    # was the old M15 walk ambiguous for this trade (stop and target inside one M15 bar)?
                    amb = False
                    sl, tp = ep - d * stop, ep + d * 2 * stop
                    for j in range(k + 1, len(day)):
                        hh, ll = day.h.iat[j], day.l.iat[j]
                        s_hit = (ll <= sl) if d > 0 else (hh >= sl)
                        t_hit = (hh >= tp) if d > 0 else (ll <= tp)
                        if s_hit or t_hit:
                            amb = bool(s_hit and t_hit)
                            break
                    ctl = []
                    for q in rng.choice(win[:-1], 5):
                        rc = walk(m1d, day.index[q + 1], d, stop)
                        if rc is not None:
                            ctl.append(rc[0] - (day.s.iat[q + 1] + rc[1]) / 2 / stop)
                    rows.append(dict(year=y, gross=g, net=g - (s_in + s_out) / 2 / stop, ctl=float(np.mean(ctl)) if ctl else np.nan,
                                     amb=amb, spread=float(s_in), stop=float(stop)))
        print(f"  {y} done ({sum(1 for r in rows if r['year'] == y)} trades)", flush=True)
    T = pd.DataFrame(rows)
    t = lambda x: float(x.mean() / x.std(ddof=1) * np.sqrt(len(x))) if len(x) > 2 else np.nan
    out = []
    for y, x in T.groupby("year"):
        r = dict(year=int(y), n=len(x), net=float(x.net.mean()), net_t=t(x.net), gross=float(x.gross.mean()), gross_t=t(x.gross),
                 skill=float((x.net - x.ctl).mean()), skill_t=t(x.net - x.ctl), amb=float(x.amb.mean()), spread_usd=float(x.spread.median()),
                 stop_usd=float(x.stop.median()), win=float((x.net > 0).mean()))
        out.append(r)
        print(f"  {y}: n {r['n']:3d} | net {r['net']:+.3f} (t {r['net_t']:+.1f}) | zero-cost {r['gross']:+.3f} (t {r['gross_t']:+.1f}) | "
              f"vs random {r['skill']:+.3f} (t {r['skill_t']:+.1f}) | win {r['win']:.0%} | M15-ambiguous {r['amb']:.0%} | spread ${r['spread_usd']:.2f} stop ${r['stop_usd']:.2f}")
    allr = dict(n=len(T), net=float(T.net.mean()), net_t=t(T.net), gross=float(T.gross.mean()), gross_t=t(T.gross), amb=float(T.amb.mean()))
    print(f"  ALL: n {allr['n']} net {allr['net']:+.3f} (t {allr['net_t']:+.1f}) zero-cost {allr['gross']:+.3f} (t {allr['gross_t']:+.1f}) M15-ambiguous {allr['amb']:.0%}")
    (HERE / "setup_a_m1.json").write_text(json.dumps(dict(years=out, all=allr), indent=1, default=float))


if __name__ == "__main__":
    main()
