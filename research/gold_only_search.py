#!/usr/bin/env python3
"""Gold on its own, daily and weekly, 20 years - the gap the rest of this
program left open.

WHAT WAS MISSING
  Gold had been searched on H1 (thirteen families, nothing) and had appeared as
  one of 27 markets in the futures book, where it happened to be the best
  performer. It had never been searched on DAILY bars as a single market. That
  is what this does, across eleven rules with a random control on each.

THE CONTROL BUG THIS FILE EXISTS TO AVOID
  A long-only rule must be compared against random LONG entries, not against
  random-direction ones. Compared against a half-long/half-short control, the
  asset's own drift shows up as skill for free - and gold went from about $450
  to $4,400 over this sample, so that error is worth more than any signal.

  Getting it wrong the first time turned Donchian 55 long's apparent skill from
  t = +3.18 into t = +2.78 once the control matched the direction mix.

RESULT
  Donchian 55, LONG ONLY, daily: +1.6476R per trade over 75 trades at t = +3.85,
  skill over a matched random control +1.4655R at t = +2.78. The Bonferroni bar
  for eleven tests is 2.84, so it lands just under - the closest anything in
  this program has come on a properly controlled basis.

  Every two-sided variant collapses once the control is matched: Donchian 55
  both ways falls to skill -0.098, Donchian 20 to -0.067.

  AND IT DOES NOT MATTER, because the rule fires 3.8 times a YEAR. That is
  0.0247 R/day, and reaching 1 R/day from gold alone needs 40x the frequency -
  which lands squarely in the intraday range where the same structure measures
  t = -6.23 across 26 markets.

    python research/gold_only_search.py
"""
import json, math, urllib.parse, urllib.request
import numpy as np, pandas as pd
from statistics import NormalDist

def get(interval, rng):
    u=("https://query1.finance.yahoo.com/v8/finance/chart/GC%3DF"
       f"?range={rng}&interval={interval}")
    r=urllib.request.Request(u,headers={"User-Agent":"Mozilla/5.0"})
    d=json.load(urllib.request.urlopen(r,timeout=45))["chart"]["result"][0]
    q=d["indicators"]["quote"][0]
    x=pd.DataFrame({k:q[k] for k in ("open","high","low","close","volume")},
                   index=pd.to_datetime(d["timestamp"],unit="s",utc=True)).dropna()
    return x[~x.index.duplicated()]

D=get("1d","20y"); W=D.resample("W").agg({"open":"first","high":"max","low":"min",
                                          "close":"last","volume":"sum"}).dropna()
print(f"gold daily  {len(D):,} bars  {D.index[0]:%Y-%m} .. {D.index[-1]:%Y-%m}")
print(f"gold weekly {len(W):,} bars\n")
RNG=np.random.default_rng(31)
COST=0.0002

def engine(df, sigfn, hold, rmult, per_year, rand=False):
    o,h,l,c=(df[k].to_numpy(float) for k in ("open","high","low","close"))
    N=len(c); pc=pd.Series(c).shift(1)
    A=pd.concat([pd.Series(h-l),(pd.Series(h)-pc).abs(),(pd.Series(l)-pc).abs()],
                axis=1).max(axis=1).ewm(alpha=1/14,adjust=False).mean().to_numpy()
    up,dn=sigfn(df,A)
    idx=[i for i in range(260,N-1) if (up[i] or dn[i]) and np.isfinite(A[i]) and A[i]>0]
    live=[(i,1 if up[i] else -1) for i in idx]
    if rand:
        # Match the REAL direction mix. A long-only rule compared against a
        # half-long/half-short control is compared against a driftless
        # benchmark, and inherits the asset's drift as fake skill.
        pool=[i for i in range(260,N-1) if np.isfinite(A[i]) and A[i]>0]
        pick=sorted(RNG.choice(pool,size=min(len(idx),len(pool)),replace=False)) if idx else []
        dirs=[d for _,d in live]
        pairs=[(i,dirs[j%len(dirs)]) for j,i in enumerate(pick)] if dirs else []
    else:
        pairs=live
    rows,busy=[],-1
    for i,d in pairs:
        if i<=busy: continue
        e=c[i]; risk=rmult*A[i]
        if risk<=0: continue
        stop=e-d*risk; tg=[e+d*risk*m for m in (1,2,3)]
        al,t1,r,k,be=[True]*3,False,0.0,i+1,e
        while k<min(i+1+hold,N):
            cur=be if t1 else stop
            if (d>0 and l[k]<=cur) or (d<0 and h[k]>=cur):
                for x in range(3):
                    if al[x]: r+=((cur-e)*d-COST*e)/risk; al[x]=False
                break
            for x in range(3):
                if al[x] and ((d>0 and h[k]>=tg[x]) or (d<0 and l[k]<=tg[x])):
                    r+=((tg[x]-e)*d-COST*e)/risk; al[x]=False
                    if x==0: t1=True
            if not any(al): break
            k+=1
        kx=min(k,N-1)
        if any(al):
            for x in range(3):
                if al[x]: r+=((c[kx]-e)*d-COST*e)/risk
        rows.append(r); busy=kx
    a=np.array(rows); n=len(a)
    if n<15: return n,float("nan"),float("nan"),float("nan"),float("nan")
    e_,sd=a.mean(),a.std(ddof=1)
    yrs=(df.index[-1]-df.index[0]).days/365.25
    return n,e_,e_/(sd/math.sqrt(n)),a.sum()/(yrs*250),sd

def don(nb, longs=False):
    def f(df,A):
        hi=df.high.rolling(nb).max().shift(1).to_numpy()
        lo=df.low.rolling(nb).min().shift(1).to_numpy()
        c=df.close.to_numpy(float)
        return c>hi, (np.zeros(len(c),bool) if longs else c<lo)
    return f
def ma(f_,s_):
    def f(df,A):
        a=df.close.ewm(span=f_,adjust=False).mean().to_numpy()
        b=df.close.ewm(span=s_,adjust=False).mean().to_numpy()
        return (np.concatenate([[False],(a[1:]>b[1:])&(a[:-1]<=b[:-1])]),
                np.concatenate([[False],(a[1:]<b[1:])&(a[:-1]>=b[:-1])]))
    return f
def zone(lo_,hi_):
    def f(df,A):
        z=((df.close-df.close.rolling(200).mean())/pd.Series(A,index=df.index)).to_numpy()
        inz=(z>=lo_)&(z<=hi_)
        return np.concatenate([[False],inz[1:]&~inz[:-1]]), np.zeros(len(z),bool)
    return f
def mom(n):
    def f(df,A):
        r=df.close.pct_change(n).to_numpy()
        return (np.concatenate([[False],(r[1:]>0)&(r[:-1]<=0)]),
                np.concatenate([[False],(r[1:]<0)&(r[:-1]>=0)]))
    return f

TESTS=[("daily Donchian 55",D,don(55),60,2.0),
       ("daily Donchian 55 long",D,don(55,True),60,2.0),
       ("daily Donchian 20",D,don(20),60,2.0),
       ("daily Donchian 100",D,don(100),90,2.0),
       ("daily EMA 20/50",D,ma(20,50),60,2.0),
       ("daily EMA 50/200",D,ma(50,200),120,2.0),
       ("daily momentum 250",D,mom(250),90,2.0),
       ("daily trend zone",D,zone(1.08,7.21),90,2.0),
       ("weekly Donchian 20",W,don(20),20,2.0),
       ("weekly Donchian 12",W,don(12),16,2.0),
       ("weekly EMA 10/30",W,ma(10,30),20,2.0)]
bar=NormalDist().inv_cdf(1-0.025/len(TESTS))
print(f"{'gold, one market only':<26}{'n':>5}{'E':>9}{'t':>7}{'R/day':>8}"
      f"{'rand E':>9}{'skill':>9}{'sk t':>7}")
best=None
for lab,df,fn,hold,rm in TESTS:
    n,e,t,rpd,sd=engine(df,fn,hold,rm,250)
    if n<15: print(f"{lab:<26}{n:>5}  too few"); continue
    rn,re,rt,rr,rsd=engine(df,fn,hold,rm,250,rand=True)
    sk=e-re if rn>1 else float("nan")
    se=math.sqrt(sd**2/n+rsd**2/rn) if rn>1 else float("nan")
    print(f"{lab:<26}{n:>5}{e:>+9.4f}{t:>+7.2f}{rpd:>8.4f}"
          f"{re:>+9.4f}{sk:>+9.4f}{sk/se:>+7.2f}")
    if best is None or (sk/se)>best[1]: best=(lab,sk/se,e,t,n,rpd)
print(f"\n{len(TESTS)} tests on one market -> Bonferroni bar t > {bar:.2f}")
print(f"best skill: {best[0]}  skill t {best[1]:+.2f}  E {best[2]:+.4f}  R/day {best[5]:.4f}")
print("\nFREQUENCY IS THE WALL. Gold alone, per year:")
for lab,df,fn,hold,rm in TESTS[:4]:
    n,e,t,rpd,sd=engine(df,fn,hold,rm,250)
    if n<15: continue
    yrs=(df.index[-1]-df.index[0]).days/365.25
    print(f"  {lab:<26}{n/yrs:>6.1f} trades/yr   {rpd:>8.4f} R/day"
          f"   need {1.0/max(rpd,1e-9):>6.0f}x for 1 R/day")
