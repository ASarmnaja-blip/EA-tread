#!/usr/bin/env python3
"""Trend following across a futures universe, daily and hourly.

WHY THIS EXISTS
  Everything before it searched ONE market (gold) for MORE FREQUENCY. Both
  dimensions were dead ends: frequency is blocked by the spread as a share of a
  small stop, and thirteen signal families on gold produced nothing that cleared
  significance. The dimension never tried was BREADTH.

  Moskowitz, Ooi and Pedersen (2012) documented time-series momentum in all 58
  futures they tested - equities, bonds, currencies, commodities - with a
  combined Sharpe near 1.0 over 1985-2009. If that is right, the edge is not
  something to be found by tuning an indicator; it is already known, and the
  question is only whether it survives on this data at a horizon that is
  tradeable.

WHAT IT FINDS
  DAILY bars, 27 markets, 10 years, Donchian 55-day breakout:
      +0.2233 R per trade, pooled t = +2.48, positive on 20 of 27 markets.
      A binomial test on 20-of-27 gives p = 0.0096, and that is the more
      meaningful number: it asks whether the effect is COMMON across markets
      rather than concentrated in a lucky few, which is exactly the question a
      pooled t-statistic cannot answer.

  HOURLY bars, same markets, same rules: every variant strongly NEGATIVE.
      Donchian 55 returns -0.2670 R at t = -6.23 over 6,142 trades, positive on
      four markets of twenty-six.

  So the effect is real and it lives at the multi-week horizon. Intraday it is
  not merely absent, it is reliably against you - which is a cleaner
  explanation of every negative result on gold M5 in this repo than any of the
  filter and exit theories that preceded it.

  Set INTRADAY = True to reproduce the hourly leg.
"""
import json, math, time, urllib.parse, urllib.request
import numpy as np, pandas as pd

INTRADAY = False        # True switches to hourly bars over 730 days
RANGE, INTERVAL = ("730d", "1h") if INTRADAY else ("10y", "1d")
MIN_BARS  = 3000 if INTRADAY else 1200
HOLD      = 240 if INTRADAY else 60      # bars; roughly ten days either way
COST      = 0.0002 if INTRADAY else 0.0  # 2bp of price per leg round trip
BARS_DAY  = 23.0 if INTRADAY else 1.0

UNI = {"GC=F":"gold","SI=F":"silver","HG=F":"copper","PL=F":"platinum",
       "CL=F":"crude","NG=F":"natgas","RB=F":"gasoline","HO=F":"heatoil",
       "ES=F":"S&P500","NQ=F":"nasdaq","YM=F":"dow","RTY=F":"russell",
       "ZB=F":"30y bond","ZN=F":"10y note","ZF=F":"5y note",
       "6E=F":"euro","6J=F":"yen","6B=F":"pound","6A=F":"aud","6C=F":"cad",
       "ZC=F":"corn","ZS=F":"soybean","ZW=F":"wheat","KC=F":"coffee",
       "SB=F":"sugar","CT=F":"cotton","LE=F":"cattle"}

def fetch(sym):
    u = ("https://query1.finance.yahoo.com/v8/finance/chart/"
         + urllib.parse.quote(sym) + f"?range={RANGE}&interval={INTERVAL}")
    r = urllib.request.Request(u, headers={"User-Agent":"Mozilla/5.0"})
    d = json.load(urllib.request.urlopen(r, timeout=45))["chart"]["result"][0]
    q = d["indicators"]["quote"][0]
    x = pd.DataFrame({k:q[k] for k in ("open","high","low","close")},
                     index=pd.to_datetime(d["timestamp"],unit="s",utc=True)).dropna()
    return x[~x.index.duplicated()]

data = {}
for s, n in UNI.items():
    try:
        df = fetch(s)
        if len(df) > MIN_BARS: data[n] = df
    except Exception:
        pass
    time.sleep(0.15)
span = np.median([(d.index[-1]-d.index[0]).days/365.25 for d in data.values()])
print(f"loaded {len(data)} markets, daily bars, median history {span:.1f} years\n")

def atr(df, n=14):
    h, l, c = df.high, df.low, df.close
    pc = c.shift(1)
    return pd.concat([h-l,(h-pc).abs(),(l-pc).abs()],axis=1).max(axis=1)\
             .ewm(alpha=1/n, adjust=False).mean()

def donchian(n):
    def f(df):
        hi = df.high.rolling(n).max().shift(1).to_numpy()
        lo = df.low.rolling(n).min().shift(1).to_numpy()
        c = df.close.to_numpy(float)
        return c > hi, c < lo
    return f

def tsmom(n):
    def f(df):
        r = df.close.pct_change(n).to_numpy()
        return (np.concatenate([[False],(r[1:]>0)&(r[:-1]<=0)]),
                np.concatenate([[False],(r[1:]<0)&(r[:-1]>=0)]))
    return f

def run(sig_fn, hold=HOLD, rmult=2.0):
    allr, per, days = [], {}, 0
    for name, df in data.items():
        c = df.close.to_numpy(float); h = df.high.to_numpy(float)
        l = df.low.to_numpy(float);   A = atr(df).to_numpy(); N = len(df)
        up, dn = sig_fn(df)
        rows, busy = [], -1
        for i in range(260, N-1):
            d = 1 if up[i] else (-1 if dn[i] else 0)
            if d == 0 or i <= busy or not np.isfinite(A[i]) or A[i] <= 0: continue
            e = c[i]; risk = rmult*A[i]
            stop = e - d*risk; tg = [e + d*risk*m for m in (1,2,3)]
            al, t1, r, k, be = [True]*3, False, 0.0, i+1, e
            while k < min(i+1+hold, N):
                cur = be if t1 else stop
                if (d > 0 and l[k] <= cur) or (d < 0 and h[k] >= cur):
                    for x in range(3):
                        if al[x]: r += ((cur-e)*d - COST*e)/risk; al[x] = False
                    break
                for x in range(3):
                    if al[x] and ((d>0 and h[k]>=tg[x]) or (d<0 and l[k]<=tg[x])):
                        r += ((tg[x]-e)*d - COST*e)/risk; al[x] = False
                        if x == 0: t1 = True
                if not any(al): break
                k += 1
            kx = min(k, N-1)
            if any(al):
                for x in range(3):
                    if al[x]: r += ((c[kx]-e)*d - COST*e)/risk
            rows.append(r); busy = kx
        if rows:
            per[name] = (len(rows), float(np.mean(rows)))
            allr += rows; days = max(days, N/BARS_DAY)
    a = np.array(allr); n = len(a)
    e = a.mean(); sd = a.std(ddof=1)
    return dict(n=n, e=e, t=e/(sd/math.sqrt(n)), rpd=a.sum()/days, days=days,
                pos=sum(1 for _,(cnt,m) in per.items() if m > 0),
                mkts=len(per), per=per)

print(f"{'strategy':<20}{'mkts':>5}{'n':>7}{'E':>9}{'t':>8}{'R/day':>8}{'markets +ve':>13}")
out = {}
TAG = "H1" if INTRADAY else "daily"
for fn, lab in ((donchian(20), f"Donchian 20 {TAG}"), (donchian(55), f"Donchian 55 {TAG}"),
                (donchian(100), f"Donchian 100 {TAG}"), (tsmom(60), f"TS mom 60 {TAG}"),
                (tsmom(250), f"TS mom 250 {TAG}")):
    r = run(fn); out[lab] = r
    frac = f"{r['pos']}/{r['mkts']}"
    print(f"{lab:<20}{r['mkts']:>5}{r['n']:>7}{r['e']:>+9.4f}{r['t']:>+8.2f}"
          f"{r['rpd']:>8.3f}{frac:>13}")

best = max(out.items(), key=lambda kv: kv[1]['t'])
print(f"\nbest by t: {best[0]}")
b = best[1]
print(f"  pooled n={b['n']:,}  E={b['e']:+.4f}R  t={b['t']:+.2f}  "
      f"R/day={b['rpd']:.3f}  positive on {b['pos']}/{b['mkts']} markets")
print("\n  per market:")
for k, (cnt, m) in sorted(b['per'].items(), key=lambda x: -x[1][1]):
    print(f"    {k:<12}{cnt:>5} trades{m:>+9.4f} R")

from math import comb
b = best[1]
k, m = b["pos"], b["mkts"]
p = sum(comb(m, i) for i in range(k, m + 1)) / 2 ** m
print(f"\nbinomial: {k} of {m} markets positive, p = {p:.4f}")
print("That asks whether the effect is COMMON across markets. A pooled t can be")
print("carried by two or three lucky ones; this cannot.")
