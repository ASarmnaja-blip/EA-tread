#!/usr/bin/env python3
"""Search thirteen signal families on gold for any directional information.

THE QUESTION
  Not "which is best" but "is there anything at all". Every family is measured
  at ZERO SPREAD as well as at the real 0.26, because a gross expectancy of
  zero means no amount of cost reduction, filtering or exit engineering can
  help. Cost only matters once something is there to keep.

WHAT IT COVERS
  Trend: EMA 9/21 and 21/55 crosses, Donchian 20 and 55 breakouts, momentum
  flip, volatility breakout, the repo's own trend zone.
  Reversion: RSI 14, Bollinger fade, VWAP reversion, gap fade.
  Flow: volume spike with bar direction.
  Plus Bollinger break, which is the same indicator read the other way.

  All share one exit - three legs at 1R/2R/3R off a 1.5xATR stop, break-even
  after the first fills - so the comparison is of the signal alone.

RESULT ON COMEX GOLD H1, 575 TRADING DAYS
  Not one family's gross expectancy clears the Bonferroni bar for thirteen
  tests (t > 2.89). The best is Donchian 55 at t = +1.42, and its expectancy
  sits inside its own minimum detectable effect. The best R per day found
  anywhere is +0.130, against a 3.0 target.

  Read the frontier at the bottom before concluding the search was too narrow.
  Faster signals mean tighter stops and a bigger spread as a share of R; M1
  costs 0.278R per signal against a best-ever gross of +0.32R. Slower signals
  mean too few trades. Both corners are closed, and the middle is empty.

    python research/signal_family_search.py     # fetches its own data
"""
import json, math, os, urllib.request
import numpy as np, pandas as pd
from statistics import NormalDist

SPREAD, RISK_ATR, HOLD = 0.26, 1.5, 30


def load(path="gc_1h.json"):
    """Fetches its own data if the cache is absent. The hourly window is about
    875 days and stable, unlike the 1-minute one, which Yahoo serves only for
    the last four weeks - so this stays reproducible while gc_1m.csv does not."""
    if not os.path.exists(path):
        url = ("https://query1.finance.yahoo.com/v8/finance/chart/GC%3DF"
               "?range=730d&interval=1h")
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=60) as r:
            open(path, "wb").write(r.read())
        print(f"fetched {path}")
    d = json.load(open(path))["chart"]["result"][0]
    q = d["indicators"]["quote"][0]
    x = pd.DataFrame({k: q[k] for k in ("open", "high", "low", "close", "volume")},
                     index=pd.to_datetime(d["timestamp"], unit="s", utc=True)).dropna()
    return x[x.volume > 0]


def main():
    df = load()
    o, h, l, c, v = (df[k].to_numpy(float) for k in
                     ("open", "high", "low", "close", "volume"))
    N = len(df); DAYS = N / 23.0
    S = pd.Series(c)
    pc = S.shift(1)
    tr = pd.concat([pd.Series(h - l), (pd.Series(h) - pc).abs(),
                    (pd.Series(l) - pc).abs()], axis=1).max(axis=1)
    ATR = tr.ewm(alpha=1 / 14, adjust=False).mean().to_numpy()
    print(f"COMEX gold H1  {N:,} bars  {DAYS:.0f} trading days  "
          f"{df.index[0]:%Y-%m}..{df.index[-1]:%Y-%m}\n")

    def ema(f, s):
        a = S.ewm(span=f, adjust=False).mean().to_numpy()
        b = S.ewm(span=s, adjust=False).mean().to_numpy()
        return (np.concatenate([[False], (a[1:] > b[1:]) & (a[:-1] <= b[:-1])]),
                np.concatenate([[False], (a[1:] < b[1:]) & (a[:-1] >= b[:-1])]))

    def donchian(n):
        return (c > pd.Series(h).rolling(n).max().shift(1).to_numpy(),
                c < pd.Series(l).rolling(n).min().shift(1).to_numpy())

    def rsi(n, lo_, hi_):
        dl = S.diff()
        u = dl.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
        d_ = (-dl.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
        r = (100 - 100 / (1 + u / d_.replace(0, np.nan))).to_numpy()
        return (np.concatenate([[False], (r[1:] > lo_) & (r[:-1] <= lo_)]),
                np.concatenate([[False], (r[1:] < hi_) & (r[:-1] >= hi_)]))

    def boll(n, k, fade):
        m = S.rolling(n).mean(); sd = S.rolling(n).std()
        up = c > (m + k * sd).to_numpy(); dn = c < (m - k * sd).to_numpy()
        return (dn, up) if fade else (up, dn)

    def mom(n):
        r = S.pct_change(n).to_numpy()
        return (np.concatenate([[False], (r[1:] > 0) & (r[:-1] <= 0)]),
                np.concatenate([[False], (r[1:] < 0) & (r[:-1] >= 0)]))

    def volbreak(k):
        return (c - o) > k * ATR, (o - c) > k * ATR

    def zone(lo_, hi_):
        z = ((S - S.rolling(200).mean()) / pd.Series(ATR)).to_numpy()
        inz = (z >= lo_) & (z <= hi_)
        return np.concatenate([[False], inz[1:] & ~inz[:-1]]), np.zeros(N, bool)

    def volspike(k):
        big = v > k * pd.Series(v).rolling(50).median().to_numpy()
        return big & (c > o), big & (c < o)

    def vwap(n, k):
        tp = (h + l + c) / 3
        vw = (pd.Series(tp * v).rolling(n).sum() /
              pd.Series(v).rolling(n).sum()).to_numpy()
        dev = (c - vw) / ATR
        return dev < -k, dev > k

    def gapfade(k):
        g = np.concatenate([[0.0], (o[1:] - c[:-1]) / ATR[1:]])
        return g < -k, g > k

    FAMS = [("EMA 9/21 cross", ema(9, 21)), ("EMA 21/55 cross", ema(21, 55)),
            ("Donchian 20 break", donchian(20)), ("Donchian 55 break", donchian(55)),
            ("RSI 14 reversion", rsi(14, 30, 70)),
            ("Bollinger 20 fade", boll(20, 2.0, True)),
            ("Bollinger 20 break", boll(20, 2.0, False)),
            ("Momentum 10 flip", mom(10)), ("Vol breakout 1xATR", volbreak(1.0)),
            ("Trend zone 1.08-7.21", zone(1.08, 7.21)),
            ("Volume spike 2x", volspike(2.0)), ("VWAP 50 revert 1.5", vwap(50, 1.5)),
            ("Gap fade 0.5xATR", gapfade(0.5))]

    def sim(i, d, e, risk, sp):
        stop, be = e - d * risk, e + d * sp
        tg = [e + d * risk * m for m in (1, 2, 3)]
        al, t1, r, k = [True] * 3, False, 0., i + 1
        while k < min(i + 1 + HOLD, N):
            cur = be if t1 else stop
            if (d > 0 and l[k] <= cur) or (d < 0 and h[k] >= cur):
                for x in range(3):
                    if al[x]: r += ((cur - e) * d - sp) / risk; al[x] = False
                break
            for x in range(3):
                if al[x] and ((d > 0 and h[k] >= tg[x]) or (d < 0 and l[k] <= tg[x])):
                    r += ((tg[x] - e) * d - sp) / risk; al[x] = False
                    if x == 0: t1 = True
            if not any(al): break
            k += 1
        kx = min(k, N - 1)
        if any(al):
            for x in range(3):
                if al[x]: r += ((c[kx] - e) * d - sp) / risk
        return r, max(1, kx - i)

    Z = NormalDist().inv_cdf(.975) + NormalDist().inv_cdf(.80)
    print(f"{'signal family':<24}{'n':>6}{'n/day':>7}{'GROSS E':>10}{'G t':>7}"
          f"{'NET@0.26':>10}{'t':>7}{'R/day':>8}{'MDE':>7}")
    best = []
    for name, (up, dn) in FAMS:
        rows = []
        for i in range(220, N - 1):
            d = 1 if up[i] else (-1 if dn[i] else 0)
            if d == 0 or not np.isfinite(ATR[i]) or ATR[i] <= 0: continue
            risk = RISK_ATR * ATR[i]
            r0, du = sim(i, d, c[i], risk, 0.0)
            r1, _ = sim(i, d, c[i], risk, SPREAD)
            rows.append((i, r0, r1, du))
        if len(rows) < 20:
            print(f"{name:<24}{len(rows):>6}  too few"); continue
        D = pd.DataFrame(rows, columns=["bar", "r0", "r1", "dur"])
        take, busy = [], -1
        for b, du in zip(D.bar, D.dur):
            if b > busy: take.append(True); busy = b + du
            else:        take.append(False)
        D = D[np.array(take)]
        n = len(D)
        if n < 20:
            print(f"{name:<24}{n:>6}  too few after sequencing"); continue
        e0, s0 = D.r0.mean(), D.r0.std(ddof=1)
        e1, s1 = D.r1.mean(), D.r1.std(ddof=1)
        npd = n / DAYS
        best.append((name, n, npd, e0, e0 / (s0 / math.sqrt(n)), e1,
                     e1 / (s1 / math.sqrt(n)), e1 * npd, Z * s1 / math.sqrt(n)))
        b = best[-1]
        print(f"{name:<24}{n:>6}{npd:>7.2f}{b[3]:>+10.4f}{b[4]:>+7.2f}"
              f"{b[5]:>+10.4f}{b[6]:>+7.2f}{b[7]:>+8.3f}{b[8]:>7.3f}")

    K = len(best); bar = NormalDist().inv_cdf(1 - 0.025 / K)
    top = max(best, key=lambda x: x[7])
    print(f"\ntarget +3.000 R/day.  best found: {top[0]} at {top[7]:+.3f} R/day"
          f"  ({3.0 / top[7]:.0f}x short)" if top[7] > 0 else "\nnothing positive")
    print(f"{K} families tested, Bonferroni bar t > {bar:.2f}")
    print(f"families whose GROSS clears it: "
          f"{[x[0] for x in best if abs(x[4]) > bar] or 'NONE'}")

    print("\nTHE FRONTIER - why widening the search does not help")
    atr1 = ATR[np.isfinite(ATR)].mean() / math.sqrt(60)   # implied M1 ATR
    print(f"  {'timeframe':<10}{'1.5xATR stop':>14}{'cost per signal':>17}")
    for tf, mult in (("M1", 1), ("M5", 5), ("M15", 15), ("H1", 60)):
        risk = RISK_ATR * atr1 * math.sqrt(mult)
        print(f"  {tf:<10}{risk:>14.3f}{3 * SPREAD / risk:>17.4f}")
    print("  Faster means a tighter stop and a bigger spread as a share of R.")
    print("  Slower means too few trades. Best gross seen anywhere is +0.32R,")
    print("  best frequency 1.62/day, and they belong to different families.")
    print("  Even combining them gives 0.52 R/day, still six times short.")


if __name__ == "__main__":
    main()
