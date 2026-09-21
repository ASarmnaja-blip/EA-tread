"""Cross-asset residual mean-reversion candidate, declared before inspection.

Estimate XAUUSD's contemporaneous M5 return from DXY and XAGUSD using only
the preceding five trading days.  Accumulate the unexplained return for one
hour and trade only a 2.5-sigma residual that has begun to turn back.  This is
a relative-value hypothesis, not another raw-price direction predictor.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[2]
ROLL=5*288
ZWIN=10*288
H=12
ZENTRY=2.5
STOP_ATR=1.5
TARGET_R=1.0
COST=0.09+2*0.10

@dataclass
class Trade:
    t:pd.Timestamp; d:int; r:float; why:str

def load(sym):
    d=pd.read_csv(ROOT/'data'/f'{sym}_M5.csv',parse_dates=['time'])
    d.time=pd.to_datetime(d.time,utc=True)
    return d.set_index('time').sort_index()

def build():
    z=load('XAUUSD')
    z=z.join(load('DXY')[['close']].rename(columns={'close':'dxy'}),how='inner')
    z=z.join(load('XAGUSD')[['close']].rename(columns={'close':'xag'}),how='inner')
    rx=np.log(z.close).diff(); rd=np.log(z.dxy).diff(); rs=np.log(z.xag).diff()
    def cov(a,b):
        return a.rolling(ROLL).mean() if a is b else (a*b).rolling(ROLL).mean()-a.rolling(ROLL).mean()*b.rolling(ROLL).mean()
    vd=rd.rolling(ROLL).var(); vs=rs.rolling(ROLL).var()
    cds=(rd*rs).rolling(ROLL).mean()-rd.rolling(ROLL).mean()*rs.rolling(ROLL).mean()
    cdy=(rd*rx).rolling(ROLL).mean()-rd.rolling(ROLL).mean()*rx.rolling(ROLL).mean()
    csy=(rs*rx).rolling(ROLL).mean()-rs.rolling(ROLL).mean()*rx.rolling(ROLL).mean()
    det=vd*vs-cds*cds
    bd=((cdy*vs-csy*cds)/det).shift(1); bs=((csy*vd-cdy*cds)/det).shift(1)
    resid=rx-bd*rd-bs*rs
    hour=resid.rolling(H).sum()
    mu=hour.rolling(ZWIN).mean().shift(1); sd=hour.rolling(ZWIN).std().shift(1)
    z['rz']=(hour-mu)/sd
    z['rz_prev']=z.rz.shift(1)
    prev=z.close.shift(1)
    tr=pd.concat([z.high-z.low,(z.high-prev).abs(),(z.low-prev).abs()],axis=1).max(axis=1)
    z['atr']=tr.rolling(14).mean()
    # Enter only after the residual has started reverting toward zero.
    z['dir']=np.where((z.rz>ZENTRY)&(z.rz<z.rz_prev),-1,
              np.where((z.rz<-ZENTRY)&(z.rz>z.rz_prev),1,0))
    z.loc[~((z.index.hour>=7)&(z.index.hour<20)),'dir']=0
    return z

def simulate(z):
    out=[]; last=-1
    for i in np.flatnonzero(z.dir.to_numpy()):
        if i<last or i+1>=len(z):continue
        d=int(z.dir.iloc[i]); atr=float(z.atr.iloc[i]); entry=float(z.open.iloc[i+1])
        if not np.isfinite(atr):continue
        risk=STOP_ATR*atr; stop=entry-d*risk; target=entry+d*TARGET_R*risk
        end=min(i+1+H,len(z)-1); px=float(z.close.iloc[end]); why='TIME'; ex=end
        for k in range(i+1,end+1):
            hs=z.low.iloc[k]<=stop if d>0 else z.high.iloc[k]>=stop
            ht=z.high.iloc[k]>=target if d>0 else z.low.iloc[k]<=target
            if hs and ht:px,why,ex=stop,'BOTH_STOP_FIRST',k;break
            if hs:px,why,ex=stop,'STOP',k;break
            if ht:px,why,ex=target,'TARGET',k;break
        out.append(Trade(z.index[i+1],d,float(d*(px-entry)/risk-COST/risk),why));last=ex
    return out

def stats(tr):
    if not tr:return dict(n=0,e=np.nan,w=np.nan,lo=np.nan,hi=np.nan)
    x=np.array([q.r for q in tr]); days=pd.Series(x,index=[q.t.floor('D') for q in tr]).groupby(level=0).mean().to_numpy()
    rng=np.random.default_rng(260921); b=np.array([rng.choice(days,len(days),True).mean() for _ in range(2000)])
    return dict(n=len(x),e=x.mean(),w=(x>0).mean(),lo=np.quantile(b,.025),hi=np.quantile(b,.975))

def show(name,tr):
    s=stats(tr);print(f'{name:18s} n={s["n"]:4d} E={s["e"]:+.4f}R win={100*s["w"]:.1f}% CI=[{s["lo"]:+.4f},{s["hi"]:+.4f}]');return s

def main():
    z=build();tr=simulate(z);end=z.index[-1];cut=end-pd.Timedelta(days=10);recent=end-pd.Timedelta(days=60)
    old=[q for q in tr if q.t<recent];dev=[q for q in tr if recent<=q.t<cut];hold=[q for q in tr if q.t>=cut]
    print('CROSS-ASSET RESIDUAL CANDIDATE',z.index[0],'->',end)
    show('older sanity',old);sd=show('recent 50d dev',dev);sh=show('locked 10d',hold)
    passed=sd['n']>=30 and sd['lo']>0 and sh['n']>=8 and sh['lo']>0
    print('latest residual z',round(float(z.rz.iloc[-1]),3),'signal',int(z.dir.iloc[-1]))
    print('DECISION','PASS' if passed else 'FAIL')
    return 0 if passed else 2

if __name__=='__main__':raise SystemExit(main())
