"""EXPLORATION (operator 2026-10-01: "เราเข้าไม้ในจุดไหน hh hl ll lh ไหม เพราะกำไรก่อนหักต้นทุนคือบางมาก"): entry location on market structure.
Swings: fractal (2 bars each side), known only when confirmed (2 bars after the swing bar). Structure at bar i from the last two confirmed swing
highs and lows: UP = higher high and higher low; DOWN = lower high and lower low.
Entries (next bar open after the condition at bar i's close):
  BREAK_HH  : UP and close > last swing high (buy the breakout, as the current breakout rules)      stop: below the last swing low (HL) - 0.1 ATR
  PULL_HL   : UP and a new higher low just confirmed at this bar (buy the pullback)                  stop: below that HL - 0.1 ATR
  BREAK_LL  : DOWN and close < last swing low (sell the breakdown)                                  stop: above the last swing high (LH) + 0.1 ATR
  PULL_LH   : DOWN and a new lower high just confirmed at this bar (sell the rally)                  stop: above that LH + 0.1 ATR
Exits: (a) time only (hold 10 D1 / 30 H4 bars); (b) target 2R. R = the structural stop distance (min 0.5 ATR). Costs C4 + swap; one position at a
time per rule. Gold DEV 2004-15 / CHECK 2016-26, silver 2010-26; each with the same-direction random-timing control.
Usage: python research/hyp/structure_entries.py -> data/hyp/structure_entries.csv"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import batch1 as B1  # noqa: E402
import batch2 as B2  # noqa: E402
import explore_scale as ES  # noqa: E402

HOLD = {"D1": 10, "H4": 30}


def structure_events(B):
    h, l, c, a = B.h, B.l, B.c, B.atr
    n = len(c)
    sh = [np.nan, np.nan]; sl = [np.nan, np.nan]                   # [older, latest] confirmed swing highs / lows
    out = {k: [] for k in ("BREAK_HH", "PULL_HL", "BREAK_LL", "PULL_LH")}
    broke_hi = broke_lo = False
    for i in range(4, n - 1):
        j = i - 2
        new_low = new_high = False
        if h[j] >= h[j - 2:j + 3].max():
            sh = [sh[1], h[j]]; broke_hi = False; new_high = True
        if l[j] <= l[j - 2:j + 3].min():
            sl = [sl[1], l[j]]; broke_lo = False; new_low = True
        if not (np.isfinite(sh[0]) and np.isfinite(sl[0]) and np.isfinite(a[i + 1])):
            continue
        up = sh[1] > sh[0] and sl[1] > sl[0]
        dn = sh[1] < sh[0] and sl[1] < sl[0]
        if up and not broke_hi and c[i] > sh[1]:
            out["BREAK_HH"].append((i + 1, 1.0, sl[1])); broke_hi = True
        if up and new_low:
            out["PULL_HL"].append((i + 1, 1.0, sl[1]))
        if dn and not broke_lo and c[i] < sl[1]:
            out["BREAK_LL"].append((i + 1, -1.0, sh[1])); broke_lo = True
        if dn and new_high:
            out["PULL_LH"].append((i + 1, -1.0, sh[1]))
    return out


def limit_events(B, hold):
    """PULL_50_LIMIT (UP: after a new swing high is confirmed, a buy limit at 50 % of the last leg HL -> HH, valid `hold` bars, cancelled if the
    price trades below the HL first) and RALLY_50_LIMIT (the mirror in DOWN). Fill at the limit (or at a better open); the fill bar is checked
    conservatively for the stop. Returns specs for simulate_events with eprice / pre_stop."""
    h, l, o, c, a = B.h, B.l, B.o, B.c, B.atr
    n = len(c); sh = [np.nan, np.nan]; sl = [np.nan, np.nan]
    out = {"PULL_50_LIMIT": [], "RALLY_50_LIMIT": []}
    for i in range(4, n - 2):
        j = i - 2
        nh = h[j] >= h[j - 2:j + 3].max(); nl = l[j] <= l[j - 2:j + 3].min()
        if nh:
            sh = [sh[1], h[j]]
        if nl:
            sl = [sl[1], l[j]]
        if not (np.isfinite(sh[0]) and np.isfinite(sl[0]) and np.isfinite(a[i])):
            continue
        up = sh[1] > sh[0] and sl[1] > sl[0]; dn = sh[1] < sh[0] and sl[1] < sl[0]
        if up and nh:
            lim = sh[1] - 0.5 * (sh[1] - sl[1]); stp = sl[1] - 0.1 * a[i]
            for k in range(i + 1, min(i + 1 + hold, n - 2)):
                if l[k] <= stp and o[k] > lim:
                    break                                              # never filled before the HL broke (gap through both is ignored)
                if l[k] <= lim:
                    fill = min(o[k], lim); out["PULL_50_LIMIT"].append((k, 1.0, fill, stp, l[k] <= stp)); break
        if dn and nl:
            lim = sl[1] + 0.5 * (sh[1] - sl[1]); stp = sh[1] + 0.1 * a[i]
            for k in range(i + 1, min(i + 1 + hold, n - 2)):
                if h[k] >= stp and o[k] < lim:
                    break
                if h[k] >= lim:
                    fill = max(o[k], lim); out["RALLY_50_LIMIT"].append((k, -1.0, fill, stp, h[k] >= stp)); break
    return out


def build_limit(B, evs, hold, target):
    k = np.array([x[0] for x in evs], int); d = np.array([x[1] for x in evs]); fill = np.array([x[2] for x in evs])
    stp = np.array([x[3] for x in evs]); pre = np.array([x[4] for x in evs], bool)
    ok = k < len(B.t) - hold - 2
    k, d, fill, stp, pre = k[ok], d[ok], fill[ok], stp[ok], pre[ok]
    stop = np.maximum(np.abs(fill - stp), 0.5 * B.atr[k])
    tgt = 2 * stop if target else np.full(len(k), np.nan)
    return dict(e=k + 1, d=d, stop=stop, tgt=tgt, last=k + hold, eprice=fill, pre_stop=pre)


def build(B, evs, hold, target):
    e = np.array([x[0] for x in evs], int); d = np.array([x[1] for x in evs]); lvl = np.array([x[2] for x in evs])
    ok = e < len(B.t) - hold - 1
    e, d, lvl = e[ok], d[ok], lvl[ok]
    a = B.atr[e]; ep = B.o[e]
    stop = np.where(d > 0, ep - (lvl - 0.1 * a), (lvl + 0.1 * a) - ep)
    stop = np.maximum(stop, 0.5 * a)
    tgt = 2 * stop if target else np.full(len(e), np.nan)
    return dict(e=e, d=d, stop=stop, tgt=tgt, last=e + hold - 1)


def main():
    t0 = time.time()
    G, gcuts = ES.bars("XAUUSD"); S, scuts = ES.bars("XAGUSD")
    rows = []
    for tf in ("D1", "H4"):
        for M, B, cuts, pers in (("XAUUSD", G[tf], gcuts, ("DEV", "CHECK")), ("XAGUSD", S[tf], scuts, ("SILVER",))):
            ev = structure_events(B); ev.update(limit_events(B, HOLD[tf]))
            for kind, evs in ev.items():
                for target in (False, True):
                    spec = build_limit(B, evs, HOLD[tf], target) if kind.endswith("LIMIT") else build(B, evs, HOLD[tf], target)
                    tr = B1.simulate_events(B, M, **spec)
                    for p in pers:
                        a, b = ES.PER[p]
                        Sx, N, sub = B1.weekly(tr, cuts, a, b)
                        m, pv = B1.boot_p(Sx, N)
                        share = {1.0: float((sub.d > 0).mean()) if len(sub) else 0.0, -1.0: float((sub.d < 0).mean()) if len(sub) else 0.0}
                        k_med = float(np.median(spec["stop"] / B.atr[spec["e"]])) if len(spec["e"]) else 1.0
                        ctl = B2.control({"sym": M}, B, HOLD[tf], k_med, a, b, share) if len(sub) else np.nan
                        rows.append(dict(tf=tf, entry=kind, exit="2R target" if target else "time", period=p, n=len(sub),
                                         gross_R=float(sub.gR.mean()) if len(sub) else np.nan, net_R=float(sub.R.mean()) if len(sub) else np.nan,
                                         cost_R=float((sub.cost_bp / sub.stop_bp).mean()) if len(sub) else np.nan, win=float((sub.R > 0).mean()) if len(sub) else np.nan,
                                         p=pv, stop_atr=k_med, ctl_R=ctl, excess=(float(sub.R.mean()) - ctl) if len(sub) else np.nan))
        print(f"{tf} done ({time.time() - t0:.0f}s)", flush=True)
    T = pd.DataFrame(rows)
    T.to_csv(B1.OUT / "structure_entries.csv", index=False)
    pd.set_option("display.width", 250)
    P = T.pivot_table(index=["tf", "entry", "exit"], columns="period", values=["n", "gross_R", "net_R", "excess"], aggfunc="first")
    P = P[[(m, p) for m in ("n", "gross_R", "net_R", "excess") for p in ("DEV", "CHECK", "SILVER")]]
    print(P.round(3).to_string())
    print(f"({time.time() - t0:.0f}s)")


if __name__ == "__main__":
    main()
