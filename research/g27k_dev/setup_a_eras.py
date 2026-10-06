#!/usr/bin/env python3
"""Setup A through the years: when did it work, when did it stop, and what
worked instead? Descriptive only - nothing here is adopted.

Setup A core (MQL5 CSetupA, stages 1-4): the Asian range (00:00-07:00 UTC) of
gold is swept and price closes back inside -> trade the reversal. The later
stages (MSS, displacement, retest) cut the sample to ~1% and were shown
unmeasurable (RESEARCH_FINDINGS, Setup 01 ablation), so they are left out.

Rules, M15 bars from Dukascopy M1 bid/ask, 2009-2026:
  sweep: between 07:00 and 16:00 UTC a bar's high goes >= 0.1 ATR14 above the
         Asian high and closes back below it (short), or the mirror at the
         Asian low (long); first sweep per side per day
  REVERSAL (Setup A): enter at the next bar's open against the sweep, stop
         0.1 ATR beyond the sweep extreme, target 2R, else exit 21:00 UTC
  CONTINUATION (the opposite trader): same moment, same stop distance and
         target, in the sweep's direction
  costs: the real bid/ask spread at entry and exit
  control: same day, direction and stop distance, entry at a random bar in
         07:00-16:00 (5 draws) -> skill = R - control R
Also G27K #1 on gold per year (dropped_markets.json) for comparison.

Usage: python3 research/g27k_dev/setup_a_eras.py
"""
import json
import pathlib
import sys

import numpy as np
import pandas as pd

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import fetch_dukascopy as DK

YEARS = range(2009, 2027)


def m15():
    parts = []
    for y in YEARS:
        p = DK.CACHE / f"XAUUSD_M1_{y}.parquet"
        if not p.exists():
            continue
        d = pd.read_parquet(p)
        mid = pd.DataFrame(dict(o=(d.bid_open + d.ask_open) / 2, h=(d.bid_high + d.ask_high) / 2, l=(d.bid_low + d.ask_low) / 2,
                                c=(d.bid_close + d.ask_close) / 2, s=d.ask_close - d.bid_close), index=d.index)
        g = mid.resample("15min").agg(dict(o="first", h="max", l="min", c="last", s="median"))
        n = mid.c.resample("15min").count()
        parts.append(g[n >= 5].dropna())
    b = pd.concat(parts).sort_index()
    pc = b.c.shift(1)
    tr = pd.concat([b.h - b.l, (b.h - pc).abs(), (b.l - pc).abs()], axis=1).max(axis=1)
    b["atr"] = tr.rolling(14).mean().shift(1)
    return b


def trade(day, i, d, stop, s_in):
    """Enter at bar i open in direction d with stop distance `stop`; 2R target; exit by 21:00 UTC. Returns net R."""
    ep = day.o.iat[i]
    sl, tp = ep - d * stop, ep + d * 2 * stop
    for j in range(i, len(day)):
        h, l = day.h.iat[j], day.l.iat[j]
        hit_sl = (l <= sl) if d > 0 else (h >= sl)
        hit_tp = (h >= tp) if d > 0 else (l <= tp)
        if hit_sl:                                   # stop first when both fall in one bar
            px = sl
            break
        if hit_tp:
            px = tp
            break
        if day.index[j].hour >= 21:
            px = day.c.iat[j]
            break
    else:
        px = day.c.iat[-1]
    return d * (px - ep) / stop - (s_in + day.s.iat[min(j, len(day) - 1)]) / 2 / stop


def main():
    b = m15()
    rng = np.random.default_rng(5)
    rows = []
    for date, day in b.groupby(b.index.date):
        asia = day[day.index.hour < 7]
        if len(asia) < 20:
            continue
        ah, al = asia.h.max(), asia.l.min()
        win = np.flatnonzero((day.index.hour >= 7) & (day.index.hour < 16))
        if len(win) < 10:
            continue
        done = set()
        for k in win[:-1]:
            a = day.atr.iat[k]
            if not np.isfinite(a) or a <= 0:
                continue
            for side, lvl, swept in (("H", ah, day.h.iat[k] >= ah + 0.1 * a and day.c.iat[k] < ah),
                                     ("L", al, day.l.iat[k] <= al - 0.1 * a and day.c.iat[k] > al)):
                if side in done or not swept:
                    continue
                done.add(side)
                d_rev = -1 if side == "H" else 1
                ext = day.h.iat[k] if side == "H" else day.l.iat[k]
                i = k + 1
                stop = abs(day.o.iat[i] - ext) + 0.1 * a
                if stop <= 0:
                    continue
                s_in = day.s.iat[i]
                rev = trade(day, i, d_rev, stop, s_in)
                con = trade(day, i, -d_rev, stop, s_in)
                ctl_r, ctl_c = [], []
                for q in rng.choice(win[:-1], 5):
                    ctl_r.append(trade(day, q + 1, d_rev, stop, day.s.iat[q + 1]))
                    ctl_c.append(trade(day, q + 1, -d_rev, stop, day.s.iat[q + 1]))
                rows.append(dict(date=str(date), year=int(str(date)[:4]), side=side, rev=rev, con=con, ctl_rev=float(np.mean(ctl_r)),
                                 ctl_con=float(np.mean(ctl_c)), stop_usd=float(stop), spread=float(s_in), asia_range=float(ah - al)))
    T = pd.DataFrame(rows)
    T["skill_rev"] = T.rev - T.ctl_rev
    T["skill_con"] = T.con - T.ctl_con
    t = lambda x: float(x.mean() / x.std(ddof=1) * np.sqrt(len(x))) if len(x) > 2 else np.nan
    g27 = {}
    dm = HERE / "dropped_markets.json"
    if dm.exists():
        for r in json.loads(dm.read_text())["panel"]:
            if r["mkt"] == "XAUUSD":
                g27[r["year"]] = r["R"]
    out = []
    for y, x in T.groupby("year"):
        r = dict(year=int(y), n=len(x), rev=float(x.rev.mean()), rev_t=t(x.rev), skill_rev=float(x.skill_rev.mean()), skill_rev_t=t(x.skill_rev),
                 con=float(x.con.mean()), con_t=t(x.con), skill_con=float(x.skill_con.mean()), cost=float((x.spread / x.stop_usd).mean()),
                 g27k=g27.get(int(y)))
        out.append(r)
        print(f"  {y}: n {r['n']:3d} | Setup A (reversal) R {r['rev']:+.3f} (t {r['rev_t']:+.1f}) skill {r['skill_rev']:+.3f} (t {r['skill_rev_t']:+.1f}) | "
              f"continuation R {r['con']:+.3f} (t {r['con_t']:+.1f}) skill {r['skill_con']:+.3f} | spread/stop {r['cost']:.3f} | "
              f"G27K gold R/trade {r['g27k'] if r['g27k'] is None else round(r['g27k'], 2)}")
    allr = dict(n=len(T), rev=float(T.rev.mean()), rev_t=t(T.rev), con=float(T.con.mean()), con_t=t(T.con),
                skill_rev=float(T.skill_rev.mean()), skill_rev_t=t(T.skill_rev))
    print(f"  ALL: n {allr['n']} reversal {allr['rev']:+.3f} (t {allr['rev_t']:+.1f}) skill {allr['skill_rev']:+.3f} (t {allr['skill_rev_t']:+.1f}) | "
          f"continuation {allr['con']:+.3f} (t {allr['con_t']:+.1f})")
    (HERE / "setup_a_eras.json").write_text(json.dumps(dict(years=out, all=allr), indent=1, default=float))


if __name__ == "__main__":
    main()
