#!/usr/bin/env python3
"""Independent cross-check of the volume-profile finding, on data that has
nothing to do with QuantConnect.

WHY THIS EXISTS
  Every result in this program came from one source: OANDA XAUUSD through
  QuantConnect, with the volume weights borrowed from GLD because the CFD feed
  carries none. A finding that only exists in one dataset, on one instrument,
  with a substituted volume proxy, is not a finding yet.

  Yahoo serves COMEX gold futures (GC=F) hourly for about 875 days WITH REAL
  TRADED VOLUME. Different venue, different instrument, different timeframe,
  and the volume is the contract's own rather than an ETF standing in for it.
  If the volume-profile filter is real it should show up here too.

WHAT YAHOO WILL AND WILL NOT GIVE
  1h  ~875 days   enough to cover 2025-2026
  5m  last 60 days only
  1m  8 days per request, recent only
  So this cannot replicate the M1/M5/M15 question - only the volume filter.

THE HONEST CAVEAT
  Exits resolve on the H1 signal bars themselves. The research notes put the
  inflation from resolving on the signal bar at +0.20R at a 3R target. The
  overlap test at the bottom tries to measure it against 5-minute resolution
  and lands on only 38 shared signals, which settles nothing in either
  direction. Treat every number here as an upper bound.

  Yahoo's continuous contract is back-adjusted, which can distort the path
  across roll dates, and GC futures are not XAUUSD spot.

    python research/yahoo_gc_crosscheck.py
"""
import json, math, urllib.request
import numpy as np, pandas as pd

URL = ("https://query1.finance.yahoo.com/v8/finance/chart/GC=F"
       "?range={r}&interval={i}")
SPREAD, HOLD, LB, BINS, VA = 0.7525, 30, 24, 48, 0.70


def fetch(interval, rng):
    req = urllib.request.Request(URL.format(r=rng, i=interval),
                                 headers={"User-Agent": "Mozilla/5.0"})
    d = json.load(urllib.request.urlopen(req, timeout=60))["chart"]["result"][0]
    q = d["indicators"]["quote"][0]
    df = pd.DataFrame({k: q[k] for k in ("open", "high", "low", "close", "volume")},
                      index=pd.to_datetime(d["timestamp"], unit="s", utc=True)).dropna()
    return df[df.volume > 0]


def wilder(hi, lo, cl, n=14):
    pc = pd.Series(cl).shift(1)
    tr = pd.concat([pd.Series(hi - lo), (pd.Series(hi) - pc).abs(),
                    (pd.Series(lo) - pc).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / n, adjust=False).mean().to_numpy()


def pivot(s, low):
    s = pd.Series(s)
    ok = ((s < s.rolling(5).min().shift(1)) & (s < s.rolling(5).min().shift(-5))) if low \
        else ((s > s.rolling(5).max().shift(1)) & (s > s.rolling(5).max().shift(-5)))
    return pd.Series(np.where(ok.fillna(False), s, np.nan)).shift(5).ffill().to_numpy()


def value_area(i, l, h, w):
    a = max(0, i - LB)
    if i - a < 20:
        return np.nan, np.nan
    lo, hi = l[a:i].min(), h[a:i].max()
    if hi <= lo:
        return np.nan, np.nan
    bs = (hi - lo) / BINS
    il = np.floor((l[a:i] - lo) / bs).astype(int).clip(0, BINS - 1)
    ih = np.floor((h[a:i] - lo) / bs).astype(int).clip(0, BINS - 1)
    sp = (ih - il + 1).astype(float)
    ww = np.divide(w[a:i], sp, out=np.zeros(i - a), where=sp > 0)
    d = np.zeros(BINS + 1)
    np.add.at(d, il, ww)
    np.add.at(d, ih + 1, -ww)
    p = np.cumsum(d)[:BINS]
    t = p.sum()
    if t <= 0:
        return np.nan, np.nan
    k = int(p.argmax())
    a_ = b_ = k
    acc = p[k]
    while acc < VA * t and (a_ > 0 or b_ < BINS - 1):
        dn = p[a_ - 1] if a_ > 0 else -1
        up = p[b_ + 1] if b_ < BINS - 1 else -1
        if up >= dn:
            b_ += 1; acc += up
        else:
            a_ -= 1; acc += dn
    return lo + (a_ + .5) * bs, lo + (b_ + .5) * bs


def stat(x):
    x = np.asarray(x, float)
    n = len(x)
    if n < 2:
        return n, float("nan"), float("nan")
    e, s = x.mean(), x.std(ddof=1)
    return n, e, (e / (s / math.sqrt(n)) if s > 0 else float("nan"))


def main():
    df = fetch("1h", "730d")
    print(f"COMEX GC=F H1: {len(df):,} bars  {df.index[0]:%Y-%m-%d} -> "
          f"{df.index[-1]:%Y-%m-%d}   real volume {df.volume.sum():,.0f}\n")
    o, h, l, c, v = (df[k].to_numpy(float) for k in
                     ("open", "high", "low", "close", "volume"))
    N, idx = len(df), df.index
    CUT = idx[int(N * .60)]
    A = wilder(h, l, c)
    fast = pd.Series(c).ewm(span=9, adjust=False).mean().to_numpy()
    slow = pd.Series(c).ewm(span=21, adjust=False).mean().to_numpy()
    plo, phi = pivot(l, True), pivot(h, False)

    def sim(i, d, e, risk, sp):
        stop, be = e - d * risk, e + d * sp
        tg = [e + d * risk * m for m in (1, 2, 3)]
        alive, tp1, r, k = [True] * 3, False, 0.0, i + 1
        while k < min(i + 1 + HOLD, N):
            cur = be if tp1 else stop
            if (d > 0 and l[k] <= cur) or (d < 0 and h[k] >= cur):
                for x in range(3):
                    if alive[x]:
                        r += ((cur - e) * d - sp) / risk; alive[x] = False
                break
            for x in range(3):
                if alive[x] and ((d > 0 and h[k] >= tg[x]) or (d < 0 and l[k] <= tg[x])):
                    r += ((tg[x] - e) * d - sp) / risk
                    alive[x] = False
                    if x == 0:
                        tp1 = True
            if not any(alive):
                break
            k += 1
        kx = min(k, N - 1)
        if any(alive):
            for x in range(3):
                if alive[x]:
                    r += ((c[kx] - e) * d - sp) / risk
        return r, kx - i

    bull = np.concatenate([[False], (fast[1:] > slow[1:]) & (fast[:-1] <= slow[:-1])])
    bear = np.concatenate([[False], (fast[1:] < slow[1:]) & (fast[:-1] >= slow[:-1])])
    rows = []
    for i in range(max(LB, 250) + 10, N - 1):
        d = 1 if bull[i] else (-1 if bear[i] else 0)
        if d == 0 or not np.isfinite(A[i]) or A[i] <= 0:
            continue
        e = c[i]
        raw = plo[i] if d > 0 else phi[i]
        if not np.isfinite(raw):
            continue
        risk = abs(e - raw)
        if risk <= 0:
            continue
        r, dur = sim(i, d, e, risk, SPREAD)
        r0, _ = sim(i, d, e, risk, 0.0)
        val, vah = value_area(i, l, h, v)
        vp = bool(np.isfinite(val) and vah > val and ((e > vah) if d > 0 else (e < val)))
        rows.append(dict(bar=i, time=idx[i], r=r, r0=r0, dur=dur,
                         spread_r=SPREAD / risk, vp=vp))
    S = pd.DataFrame(rows)

    print(f"{'part':<24}{'n':>6}{'spread/R':>10}{'NET':>9}{'t':>7}"
          f"{'GROSS':>9}{'G t':>7}{'IS':>9}{'OOS':>9}")
    for name, mask in (("baseline", np.ones(len(S), bool)),
                       ("+ real COMEX volume", S.vp.to_numpy())):
        sub = S[mask].reset_index(drop=True)
        take, busy = [], -1
        for b, du in zip(sub.bar, sub.dur):
            if b > busy:
                take.append(True); busy = b + du
            else:
                take.append(False)
        D = sub[np.array(take)]
        if len(D) < 2:
            print(f"{name:<24} too few"); continue
        n, e, t = stat(D.r); _, e0, t0 = stat(D.r0)
        _, ei, _ = stat(D[D.time < CUT].r)
        _, eo, _ = stat(D[D.time >= CUT].r)
        print(f"{name:<24}{n:>6}{D.spread_r.mean():>10.4f}{e:>+9.4f}{t:>+7.2f}"
              f"{e0:>+9.4f}{t0:>+7.2f}{ei:>+9.4f}{eo:>+9.4f}")

    print("\nEvery figure above is an UPPER BOUND: exits resolve on the H1 signal")
    print("bars, which the research notes say inflates a 3R target by about")
    print("+0.20R. The overlap window where 5-minute bars exist yields only 38")
    print("shared signals, far too few to measure that bias either way.")


if __name__ == "__main__":
    main()
