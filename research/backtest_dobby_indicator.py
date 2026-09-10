#!/usr/bin/env python3
"""Backtest of pine/Dobby_Indicator.pine, replicated line for line.

WHY A SEPARATE SCRIPT
  The QuantConnect run resolved exits on MINUTE bars. The indicator cannot -
  it only sees chart bars. That difference was worth about +0.20 R at a 3R
  target in earlier testing, so the indicator's own numbers had never actually
  been measured. This measures THEM, on the indicator's own terms.

WHAT IS REPLICATED
  - EMA 9/21 crossover on the chart timeframe, entry at the signal bar close
  - one signal at a time (the `flat = not active` gate), so every signal is
    tradeable
  - trend filter: EMA 50 on the trend timeframe, lagged one closed bar
  - stop at the last CONFIRMED pivot (5,5) - the five-bar confirmation lag is
    honoured, so no pivot is used before the chart could have drawn it
  - risk band [0.30, 3.00] x ATR14; outside it the setup is skipped
  - three legs at 1R / 2R / 3R, stop to BE = entry +/- spread after TP1
  - spread charged once per leg round trip (three legs = three spreads)
  - exits resolved on chart bars, STOP TESTED BEFORE TARGETS
  - management starts the bar AFTER entry, exactly as `bar_index > openBar`

THE CONTROL
  Random entries, matched count, matched long/short mix, same stop structure,
  same risk band, same non-overlap rule, same exit machinery. If the crossover
  carries information the real signals must beat this. Direction is matched
  because a long-biased rule on an asset that rose inherits the drift for free.

DATA
  COMEX gold futures (GC=F) from Yahoo. Not XAUUSD spot, and the continuous
  contract is back-adjusted, so treat the level as indicative. The PATH is
  what the test needs and the path is real.

    python research/backtest_dobby_indicator.py
"""
import json, math, urllib.request
import numpy as np, pandas as pd

SPREAD    = 0.26      # the user's measured broker average
MINR, MAXR = 0.30, 3.00
PL, PR, FB = 5, 5, 10
SHORT, LONG, TRENDLEN, ATRLEN = 9, 21, 50, 14
NCTRL     = 400
RNG       = np.random.default_rng(20260910)

URL = "https://query1.finance.yahoo.com/v8/finance/chart/GC=F?range={r}&interval={i}"


def fetch(interval, rng):
    req = urllib.request.Request(URL.format(r=rng, i=interval),
                                 headers={"User-Agent": "Mozilla/5.0"})
    d = json.load(urllib.request.urlopen(req, timeout=90))["chart"]["result"][0]
    q = d["indicators"]["quote"][0]
    df = pd.DataFrame({k: q[k] for k in ("open", "high", "low", "close", "volume")},
                      index=pd.to_datetime(d["timestamp"], unit="s", utc=True))
    return df.dropna().sort_index()


def ema(x, n):
    return pd.Series(x).ewm(span=n, adjust=False).mean().to_numpy()


def atr_wilder(h, l, c, n=ATRLEN):
    pc = pd.Series(c).shift(1)
    tr = pd.concat([pd.Series(h - l), (pd.Series(h) - pc).abs(),
                    (pd.Series(l) - pc).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / n, adjust=False).mean().to_numpy()


def confirmed_pivots(h, l):
    """lastLow[t], lastHigh[t] as the CHART would know them at bar t.

    Pine's ta.pivotlow(low, 5, 5) reports at bar t that bar t-5 was a pivot.
    So the value only becomes usable five bars after it printed."""
    n = len(l)
    lastLow = np.full(n, np.nan)
    lastHigh = np.full(n, np.nan)
    cl = ch = np.nan
    for t in range(n):
        c = t - PR
        if c - PL >= 0:
            wl = l[c - PL:c + PR + 1]
            wh = h[c - PL:c + PR + 1]
            if l[c] == wl.min():
                cl = l[c]
            if h[c] == wh.max():
                ch = h[c]
        lastLow[t] = cl
        lastHigh[t] = ch
    return lastLow, lastHigh


def trend_series(df, trend_tf_minutes, chart_tf_minutes):
    """EMA50 of the trend timeframe, as known at each chart bar.

    Only bins that have already CLOSED are used, then one more bar of lag for
    the `[1]` in the Pine. No left-edge labelling, so no look-ahead."""
    if trend_tf_minutes <= chart_tf_minutes:
        return ema(df.close.to_numpy(), TRENDLEN)  # same TF: plain EMA, lag below
    rule = f"{trend_tf_minutes}min"
    agg = df.resample(rule, closed="left", label="right").agg(
        {"close": "last"}).dropna()
    agg["e"] = ema(agg.close.to_numpy(), TRENDLEN)
    agg["e1"] = agg.e.shift(1)                       # the [1] lag
    j = np.searchsorted(agg.index.values, df.index.values, side="right") - 1
    out = np.where(j >= 0, agg.e1.to_numpy()[np.clip(j, 0, None)], np.nan)
    return out


def simulate(h, l, c, sigs, spread, strict=True):
    """sigs: list of (bar, is_long, entry, sl, risk). Returns per-signal R.

    Within one bar the true path is unknown, so both readings are computed:

    strict=False  the Pine's own reading. The stop is tested before the
                  targets, but once TP1 fills the new BE stop is not re-tested
                  against the SAME bar - legs 2 and 3 hold a free option on a
                  bar that already collapsed back through BE.
    strict=True   that option is removed: after TP1 fills, the BE stop is
                  tested against that same bar, and if it is touched legs 2
                  and 3 close at BE without being credited TP2 or TP3.

    Neither is the truth. The truth is between them, and a negative control on
    a driftless walk puts the free option at about +0.14 R per signal, so the
    strict column is the one to trust."""
    out = []
    for (b, up, entry, sl, risk) in sigs:
        d = 1.0 if up else -1.0
        be = entry + d * spread
        tp = [entry + d * risk * k for k in (1, 2, 3)]
        tp1done = False
        leg2 = leg3 = True
        R = 0.0
        n = len(c)
        t = b + 1
        while t < n:
            liveSL = be if tp1done else sl
            hitSL = l[t] <= liveSL if up else h[t] >= liveSL
            if hitSL:
                legs = (0 if tp1done else 1) + (1 if leg2 else 0) + (1 if leg3 else 0)
                R += ((liveSL - entry) * d - spread) / risk * legs
                leg2 = leg3 = False
                break
            if not tp1done and (h[t] >= tp[0] if up else l[t] <= tp[0]):
                tp1done = True
                R += ((tp[0] - entry) * d - spread) / risk
                if strict and (l[t] <= be if up else h[t] >= be):
                    # this bar came back through BE after tagging TP1
                    R += ((be - entry) * d - spread) / risk * 2
                    leg2 = leg3 = False
                    break
            if leg2 and (h[t] >= tp[1] if up else l[t] <= tp[1]):
                leg2 = False
                R += ((tp[1] - entry) * d - spread) / risk
            if leg3 and (h[t] >= tp[2] if up else l[t] <= tp[2]):
                leg3 = False
                R += ((tp[2] - entry) * d - spread) / risk
            if tp1done and not leg2 and not leg3:
                break
            t += 1
        else:
            # ran out of data: mark to last close, legs still open
            legs = (0 if tp1done else 1) + (1 if leg2 else 0) + (1 if leg3 else 0)
            if legs:
                R += ((c[-1] - entry) * d - spread) / risk * legs
        out.append((R, t if t < n else n - 1))
    return out


def valid(up, entry, base):
    """A long needs its stop BELOW entry and a short ABOVE it.

    When the last confirmed pivot sits on the wrong side, the Pine still takes
    the setup: risk = |close - SL|, so TP1 = entry + risk lands on the STOP
    price itself and the trade books a guaranteed +3R that no broker would ever
    fill (a buy with the stop above market is rejected). Excluding these is not
    a filter on the signal - it is refusing to count trades that cannot exist."""
    return (base < entry) if up else (base > entry)


def build_signals(df, trend_tf, chart_tf, use_trend=True):
    o, h, l, c = (df[k].to_numpy() for k in ("open", "high", "low", "close"))
    s, L = ema(c, SHORT), ema(c, LONG)
    a = atr_wilder(h, l, c)
    lastLow, lastHigh = confirmed_pivots(h, l)
    tre = trend_series(df, trend_tf, chart_tf)
    if trend_tf <= chart_tf:
        tre = pd.Series(tre).shift(1).to_numpy()      # the [1] lag, same TF
    fbL = pd.Series(l).rolling(FB).min().to_numpy()
    fbH = pd.Series(h).rolling(FB).max().to_numpy()

    bull = (s > L) & (np.r_[np.nan, s[:-1]] <= np.r_[np.nan, L[:-1]])
    bear = (s < L) & (np.r_[np.nan, s[:-1]] >= np.r_[np.nan, L[:-1]])

    warm = max(LONG, ATRLEN, FB, PL + PR) + 5
    sigs, skipped, inverted, active_until = [], 0, 0, -1
    for t in range(warm, len(c) - 1):
        if t <= active_until:
            continue
        up = bool(bull[t]); dn = bool(bear[t])
        if not (up or dn):
            continue
        if use_trend:
            if np.isnan(tre[t]):
                continue
            if up and not (c[t] > tre[t]):
                continue
            if dn and not (c[t] < tre[t]):
                continue
        base = (fbL[t] if np.isnan(lastLow[t]) else lastLow[t]) if up else \
               (fbH[t] if np.isnan(lastHigh[t]) else lastHigh[t])
        if np.isnan(base) or np.isnan(a[t]):
            continue
        if not valid(up, c[t], base):
            inverted += 1
            continue
        risk = abs(c[t] - base)
        if not (MINR * a[t] <= risk <= MAXR * a[t]):
            skipped += 1
            continue
        sigs.append((t, up, c[t], base, risk))
        # reserve the bars this signal will occupy
        rr = simulate(h, l, c, [(t, up, c[t], base, risk)], SPREAD)
        active_until = rr[0][1]
    return sigs, skipped, inverted, (h, l, c, a, lastLow, lastHigh, fbL, fbH), warm


def control(pack, sigs, warm, spread, reps=NCTRL, strict=True):
    h, l, c, a, lastLow, lastHigh, fbL, fbH = pack
    nlong = sum(1 for s in sigs if s[1])
    n = len(sigs)
    means = []
    for _ in range(reps):
        dirs = [True] * nlong + [False] * (n - nlong)
        RNG.shuffle(dirs)
        picked, k = [], 0
        order = RNG.permutation(np.arange(warm, len(c) - 1))
        for t in order:
            if k >= n:
                break
            t = int(t)
            up = dirs[k]
            base = (fbL[t] if np.isnan(lastLow[t]) else lastLow[t]) if up else \
                   (fbH[t] if np.isnan(lastHigh[t]) else lastHigh[t])
            if np.isnan(base) or np.isnan(a[t]) or not valid(up, c[t], base):
                continue
            risk = abs(c[t] - base)
            if not (MINR * a[t] <= risk <= MAXR * a[t]):
                continue
            picked.append((t, up, c[t], base, risk))
            k += 1
        if len(picked) < n * 0.8:
            continue
        means.append(np.mean([x[0] for x in
                              simulate(h, l, c, picked, spread, strict=strict)]))
    return np.array(means)


def report(name, df, trend_tf, chart_tf):
    sigs, skipped, inverted, pack, warm = build_signals(df, trend_tf, chart_tf)
    h, l, c = pack[0], pack[1], pack[2]
    days = (df.index[-1] - df.index[0]).total_seconds() / 86400
    n = len(sigs)
    nlong = sum(1 for s in sigs if s[1])
    print(f"\n=== {name} ===")
    print(f"  bars {len(df):>6}   span {days:6.1f} days   signals {n} "
          f"({nlong} long / {n-nlong} short)   {n/days:.2f} per day")
    print(f"  skipped: risk band {skipped}, inverted stop {inverted}")
    if n < 10:
        print("  too few signals to measure")
        return
    print(f"  {'reading':<13} {'NET R/sig':>10} {'t':>7} "
          f"{'GROSS':>9} {'t':>7} {'R/day':>8} {'random':>9} {'skill':>9} {'z':>7}")
    for lab, st in (("pine", False), ("strict", True)):
        net = np.array([x[0] for x in simulate(h, l, c, sigs, SPREAD, strict=st)])
        gro = np.array([x[0] for x in simulate(h, l, c, sigs, 0.0, strict=st)])
        tn = net.mean() / (net.std(ddof=1) / math.sqrt(n))
        tg = gro.mean() / (gro.std(ddof=1) / math.sqrt(n))
        ct = control(pack, sigs, warm, SPREAD, strict=st)
        cm = ct.mean() if len(ct) else float("nan")
        se = ct.std(ddof=1) if len(ct) > 1 else float("nan")
        z = (net.mean() - cm) / se if se == se else float("nan")
        print(f"  {lab:<13} {net.mean():>+10.4f} {tn:>+7.2f} "
              f"{gro.mean():>+9.4f} {tg:>+7.2f} {net.sum()/days:>+8.4f} "
              f"{cm:>+9.4f} {net.mean()-cm:>+9.4f} {z:>+7.2f}")
        if st:
            print(f"  spread cost {gro.mean()-net.mean():+.4f} R/signal   "
                  f"worst {net.min():+.2f} R   best {net.max():+.2f} R   "
                  f"3-leg stopout {100*np.mean(net < -2.5):.0f}%")
            mde = 2.80 * net.std(ddof=1) / math.sqrt(n)
            print(f"  MDE at n={n}: {mde:.2f} R/signal. Anything smaller than "
                  f"that this sample cannot see.")
            if net.mean() > 0:
                need = 3.0 / net.mean()
                print(f"  3R/day would need {need:.1f} signals/day "
                      f"= {need/(n/days):.0f}x the current frequency")
            half = len(sigs) // 2
            for lab2, sub in (("first half", sigs[:half]), ("second half", sigs[half:])):
                r = np.array([x[0] for x in simulate(h, l, c, sub, SPREAD, strict=True)])
                tt = r.mean() / (r.std(ddof=1) / math.sqrt(len(r)))
                print(f"    {lab2:<12} n {len(r):>4}  {r.mean():+.4f} R  t {tt:+.2f}")


if __name__ == "__main__":
    print(f"Dobby indicator, replicated. spread = {SPREAD}, "
          f"risk band [{MINR}, {MAXR}] x ATR, control = {NCTRL} draws")
    m15 = fetch("15m", "60d")
    report("M15 chart, trend EMA50 on M15 (the indicator's defaults)", m15, 15, 15)
    m5 = fetch("5m", "60d")
    report("M5 chart, trend EMA50 on M15", m5, 15, 5)
    h1 = fetch("1h", "730d")
    report("H1 chart, trend EMA50 on H1", h1, 60, 60)
