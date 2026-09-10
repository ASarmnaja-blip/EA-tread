#!/usr/bin/env python3
"""Smart-money entries tested as ENTRIES, each against a random control.

WHY THIS EXISTS
  An earlier round tested CHoCH and order blocks only as a FILTER stacked on an
  EMA cross, and never tested BOS, fair value gaps, liquidity sweeps or any
  multi-timeframe combination at all. Those are different claims and they
  deserved their own test.

WHAT IS TESTED, STANDALONE
  CHoCH alone                a close beyond the last opposing swing, flipping structure
  BOS continuation           a close beyond the swing in the prevailing direction
  CHoCH then OB retrace      price returns to the last opposite candle before the impulse
  CHoCH then FVG retrace     price returns into an unfilled three-bar imbalance
  Liquidity sweep reclaim    a wick clears the prior 20-bar extreme, the body closes back
  Sweep then CHoCH           the full sequence, sweep followed by a structure flip
  MTF 4h bias + CHoCH        higher-timeframe direction gates the entry
  MTF 4h bias + sweep
  MTF 4h bias + OB retrace

THE COLUMN THAT MATTERS IS 'skill'
  Every rule is measured against the SAME NUMBER of random entries with random
  direction and identical exits. Expectancy on its own is not evidence: a long
  book on a rising market earns without knowing anything, which is how a
  Donchian rule on 199 equities reached t = +4.33 while being measurably WORSE
  than darts. Skill = rule minus random is the part that cannot be drift.

RESULT ON 26 CME FUTURES, H1, 730 DAYS
  All nine lose money, from -0.065R to -0.218R. Random entry itself returns
  -0.143R, so the exit structure and the cost lose about that much before any
  signal is involved, and every rule starts from there.

  Most rules show a SMALL POSITIVE skill, +0.03 to +0.10, none significant.
  The best is the liquidity sweep at +0.079, t = +1.60. Paired with a single
  2R leg and break-even at 1R its skill reaches +0.0367 at t = +2.26 - the only
  reading above 2 anywhere in this program - and its expectancy is still
  -0.031, because the drag to beat is 0.068 per leg.

  On DAILY bars, where the cost is a fifth as large, that skill flips to
  -0.05 on five of six exit designs. A sign flip between horizons is the same
  noise signature that killed every earlier candidate.
"""
import json, math, urllib.parse, urllib.request
import numpy as np, pandas as pd
from concurrent.futures import ThreadPoolExecutor

UNI = {"GC=F":"gold","SI=F":"silver","HG=F":"copper","CL=F":"crude","NG=F":"natgas",
       "ES=F":"S&P500","NQ=F":"nasdaq","YM=F":"dow","RTY=F":"russell",
       "ZB=F":"30y","ZN=F":"10y","6E=F":"euro","6J=F":"yen","6B=F":"pound",
       "6A=F":"aud","6C=F":"cad","ZC=F":"corn","ZS=F":"soy","ZW=F":"wheat",
       "KC=F":"coffee","SB=F":"sugar","CT=F":"cotton","PL=F":"platinum",
       "HO=F":"heatoil","RB=F":"gasoline","LE=F":"cattle"}

def fetch(item):
    sym, name = item
    try:
        u = ("https://query1.finance.yahoo.com/v8/finance/chart/"
             + urllib.parse.quote(sym) + "?range=730d&interval=1h")
        r = urllib.request.Request(u, headers={"User-Agent":"Mozilla/5.0"})
        d = json.load(urllib.request.urlopen(r, timeout=40))["chart"]["result"][0]
        q = d["indicators"]["quote"][0]
        x = pd.DataFrame({k:q[k] for k in ("open","high","low","close")},
                         index=pd.to_datetime(d["timestamp"],unit="s",utc=True)).dropna()
        return name, (x if len(x) > 3000 else None)
    except Exception:
        return name, None

DATA = {}
with ThreadPoolExecutor(max_workers=10) as ex:
    for n, df in ex.map(fetch, UNI.items()):
        if df is not None: DATA[n] = df
print(f"{len(DATA)} markets, H1, 730 days\n")

COST, RMULT, HOLD = 0.0002, 2.0, 240
RNG = np.random.default_rng(17)

def prep(df):
    o,h,l,c = (df[k].to_numpy(float) for k in ("open","high","low","close"))
    N=len(c); pc=pd.Series(c).shift(1)
    A=pd.concat([pd.Series(h-l),(pd.Series(h)-pc).abs(),(pd.Series(l)-pc).abs()],
                axis=1).max(axis=1).ewm(alpha=1/14,adjust=False).mean().to_numpy()
    def piv(s,low):
        s=pd.Series(s)
        ok=((s<s.rolling(5).min().shift(1))&(s<s.rolling(5).min().shift(-5))) if low \
           else ((s>s.rolling(5).max().shift(1))&(s>s.rolling(5).max().shift(-5)))
        return pd.Series(np.where(ok.fillna(False),s,np.nan)).shift(5).ffill().to_numpy()
    sh, sl = piv(h,False), piv(l,True)

    # structure walk: BOS continues the prevailing direction, CHoCH flips it
    st=np.zeros(N,np.int8); bos=np.zeros(N,np.int8); ch=np.zeros(N,np.int8)
    ob_lo=np.full(N,np.nan); ob_hi=np.full(N,np.nan); ob_dir=np.zeros(N,np.int8)
    cur=0; _lo=_hi=np.nan; _d=0
    for i in range(N):
        a=A[i]
        if np.isfinite(a) and a>0:
            brk=0.10*a; ev=0
            if np.isfinite(sh[i]) and c[i]>sh[i]+brk: ev=1
            elif np.isfinite(sl[i]) and c[i]<sl[i]-brk: ev=-1
            if ev!=0:
                if ev==cur: bos[i]=ev
                else:
                    ch[i]=ev; cur=ev
                    _lo=_hi=np.nan; _d=ev
                    for k in range(i,max(-1,i-30),-1):
                        if (ev>0 and c[k]<o[k]) or (ev<0 and c[k]>o[k]):
                            _lo,_hi=l[k],h[k]; break
        st[i]=cur; ob_lo[i],ob_hi[i],ob_dir[i]=_lo,_hi,_d

    # fair value gap: a three-bar imbalance left unfilled
    fvg_lo=np.full(N,np.nan); fvg_hi=np.full(N,np.nan); fvg_d=np.zeros(N,np.int8)
    _flo=_fhi=np.nan; _fd=0
    for i in range(2,N):
        if l[i]>h[i-2]: _flo,_fhi,_fd=h[i-2],l[i],1
        elif h[i]<l[i-2]: _flo,_fhi,_fd=h[i],l[i-2],-1
        fvg_lo[i],fvg_hi[i],fvg_d[i]=_flo,_fhi,_fd

    # liquidity sweep: a wick clears the prior 20-bar extreme, body closes back
    ph=pd.Series(h).rolling(20).max().shift(1).to_numpy()
    pl=pd.Series(l).rolling(20).min().shift(1).to_numpy()
    with np.errstate(invalid="ignore"):
        swp_hi=(h>ph)&(c<ph)&((h-ph)<1.0*A)
        swp_lo=(l<pl)&(c>pl)&((pl-l)<1.0*A)
    swp_hi=np.nan_to_num(swp_hi,nan=0).astype(bool)
    swp_lo=np.nan_to_num(swp_lo,nan=0).astype(bool)
    return dict(o=o,h=h,l=l,c=c,N=N,A=A,sh=sh,sl=sl,st=st,bos=bos,ch=ch,
                ob_lo=ob_lo,ob_hi=ob_hi,ob_dir=ob_dir,
                fvg_lo=fvg_lo,fvg_hi=fvg_hi,fvg_d=fvg_d,swp_hi=swp_hi,swp_lo=swp_lo)

def htf_bias(df, mult):
    """Higher-timeframe direction, forward-filled without look-ahead."""
    hi=df.resample(f"{mult}h").agg({"close":"last"}).dropna()
    e=hi.close.ewm(span=50,adjust=False).mean().shift(1)
    e.index=e.index+pd.Timedelta(hours=mult)
    al=e.reindex(df.index,method="ffill")
    return np.sign(df.close.to_numpy()-al.to_numpy())

ENTRIES = {}
def entry(name):
    def deco(f): ENTRIES[name]=f; return f
    return deco

@entry("CHoCH alone")
def _(P,B): return P["ch"]
@entry("BOS continuation")
def _(P,B): return P["bos"]
@entry("CHoCH then OB retrace")
def _(P,B):
    s=np.zeros(P["N"],np.int8)
    for i in range(P["N"]):
        d=P["ob_dir"][i]
        if d==0 or not np.isfinite(P["ob_lo"][i]): continue
        if P["ob_lo"][i]-0.25*P["A"][i]<=P["c"][i]<=P["ob_hi"][i]+0.25*P["A"][i]:
            s[i]=d
    return s
@entry("CHoCH then FVG retrace")
def _(P,B):
    s=np.zeros(P["N"],np.int8)
    for i in range(P["N"]):
        d=P["fvg_d"][i]
        if d==0 or d!=P["st"][i] or not np.isfinite(P["fvg_lo"][i]): continue
        if P["fvg_lo"][i]<=P["c"][i]<=P["fvg_hi"][i]: s[i]=d
    return s
@entry("Liquidity sweep reclaim")
def _(P,B):
    s=np.zeros(P["N"],np.int8)
    s[P["swp_lo"]]=1; s[P["swp_hi"]]=-1
    return s
@entry("Sweep then CHoCH")
def _(P,B):
    s=np.zeros(P["N"],np.int8)
    for i in range(6,P["N"]):
        if P["ch"][i]==1 and P["swp_lo"][max(0,i-6):i].any(): s[i]=1
        elif P["ch"][i]==-1 and P["swp_hi"][max(0,i-6):i].any(): s[i]=-1
    return s
@entry("MTF 4h bias + CHoCH")
def _(P,B):
    s=P["ch"].copy(); s[(s!=0)&(s!=B.astype(np.int8))]=0
    return s
@entry("MTF 4h bias + sweep")
def _(P,B):
    s=np.zeros(P["N"],np.int8)
    s[P["swp_lo"]&(B>0)]=1; s[P["swp_hi"]&(B<0)]=-1
    return s
@entry("MTF 4h bias + OB retrace")
def _(P,B):
    s=np.zeros(P["N"],np.int8)
    for i in range(P["N"]):
        d=P["ob_dir"][i]
        if d==0 or d!=B[i] or not np.isfinite(P["ob_lo"][i]): continue
        if P["ob_lo"][i]-0.25*P["A"][i]<=P["c"][i]<=P["ob_hi"][i]+0.25*P["A"][i]:
            s[i]=d
    return s

def trade(P,i,d):
    c,h,l,A,N=P["c"],P["h"],P["l"],P["A"],P["N"]
    e=c[i]; risk=RMULT*A[i]
    if risk<=0: return None
    stop=e-d*risk; tg=[e+d*risk*m for m in (1,2,3)]
    al,t1,r,k,be=[True]*3,False,0.0,i+1,e
    while k<min(i+1+HOLD,N):
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
    return r,kx

PREP={n:prep(df) for n,df in DATA.items()}
BIAS={n:htf_bias(df,4) for n,df in DATA.items()}

def evaluate(sig_fn, randomise=False):
    allr,days=[],0
    for n,P in PREP.items():
        s=sig_fn(P,BIAS[n])
        idx=[i for i in range(320,P["N"]-1)
             if s[i]!=0 and np.isfinite(P["A"][i]) and P["A"][i]>0]
        if randomise and idx:
            pool=[i for i in range(320,P["N"]-1) if np.isfinite(P["A"][i]) and P["A"][i]>0]
            pick=sorted(RNG.choice(pool,size=min(len(idx),len(pool)),replace=False))
            idx=[(i,int(np.sign(RNG.integers(0,2)*2-1))) for i in pick]
        else:
            idx=[(i,int(s[i])) for i in idx]
        busy=-1
        for i,d in idx:
            if i<=busy: continue
            t=trade(P,i,d)
            if t is None: continue
            allr.append(t[0]); busy=t[1]
        days=max(days,P["N"]/23.0)
    a=np.array(allr); n=len(a)
    if n<30: return n,float("nan"),float("nan"),float("nan"),float("nan")
    e,sd=a.mean(),a.std(ddof=1)
    return n,e,e/(sd/math.sqrt(n)),a.sum()/days,sd

print(f"{'entry rule':<26}{'n':>6}{'E':>9}{'t':>7}{'R/day':>8}"
      f"{'rand E':>9}{'skill':>9}{'skill t':>9}")
res=[]
for name,fn in ENTRIES.items():
    n,e,t,rpd,sd=evaluate(fn)
    if n<30: print(f"{name:<26}{n:>6}  too few"); continue
    rn,re,rt,rrpd,rsd=evaluate(fn,randomise=True)
    sk=e-re; se=math.sqrt(sd**2/n+rsd**2/rn) if rn>1 else float("nan")
    res.append((name,n,e,t,rpd,re,sk,sk/se))
    print(f"{name:<26}{n:>6}{e:>+9.4f}{t:>+7.2f}{rpd:>8.3f}"
          f"{re:>+9.4f}{sk:>+9.4f}{sk/se:>+9.2f}")
print("\n'skill' is the entry rule minus a random entry with matched count and")
print("identical exits. Only a positive skill column means the rule knows")
print("something. E on its own can be pure drift.")
