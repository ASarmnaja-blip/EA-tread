"""Prequential current-regime analog engine.

At each whole UTC hour, use only the preceding 60 calendar days and only
completed one-hour outcomes from the same coarse market context.  A trade is
allowed when at least 40 analogs agree with |t| >= 2 and the estimated move is
at least 0.30 ATR.  Every historical prediction is genuinely prequential.
"""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[2]
TRAIN_DAYS=60; H=12; STOP_ATR=1.5; MIN_N=40; MIN_T=2.0; MIN_MOVE=.30
COST=.09+.20

@dataclass
class Signal:
    t:pd.Timestamp; d:int; pred:float; n:int; tscore:float; r:float

def load(s):
    d=pd.read_csv(ROOT/'data'/f'{s}_M5.csv',parse_dates=['time']);d.time=pd.to_datetime(d.time,utc=True)
    return d.set_index('time').sort_index()

def build():
    z=load('XAUUSD').join(load('DXY')[['close']].rename(columns={'close':'dxy'}),how='inner').join(load('XAGUSD')[['close']].rename(columns={'close':'xag'}),how='inner')
    prev=z.close.shift(1);tr=pd.concat([z.high-z.low,(z.high-prev).abs(),(z.low-prev).abs()],axis=1).max(axis=1)
    z['atr']=tr.rolling(14).mean();z['volhi']=(z.atr>z.atr.rolling(10*288).median()).astype(int)
    xday=z.close-z.close.shift(288);xhour=z.close-z.close.shift(12)
    dhour=z.dxy-z.dxy.shift(12);shour=z.xag-z.xag.shift(12)
    z['trend']=(xday>0).astype(int)
    z['dxyconf']=(np.sign(dhour)==-np.sign(xhour)).astype(int)
    z['xagconf']=(np.sign(shour)==np.sign(xhour)).astype(int)
    h=z.index.hour
    z['session']=np.select([h<7,h<13,h<17,h<21],[0,1,2,3],default=4)
    z['future_atr']=(z.close.shift(-H)-z.close)/z.atr
    return z

def resolve(z,i,d):
    entry=float(z.open.iloc[i+1]);atr=float(z.atr.iloc[i]);risk=STOP_ATR*atr;stop=entry-d*risk
    end=min(i+1+H,len(z)-1);px=float(z.close.iloc[end])
    for k in range(i+1,end+1):
        hit=z.low.iloc[k]<=stop if d>0 else z.high.iloc[k]>=stop
        if hit:px=stop;break
    return float(d*(px-entry)/risk-COST/risk)

def run(z):
    out=[]; idx=np.flatnonzero((z.index.minute==0)&z.future_atr.notna().to_numpy())
    start=z.index[-1]-pd.Timedelta(days=180)
    for i in idx:
        t=z.index[i]
        if t<start or i+H>=len(z):continue
        lo=t-pd.Timedelta(days=TRAIN_DAYS); hi=t-pd.Timedelta(minutes=H*5)
        mask=(z.index>=lo)&(z.index<=hi)
        for c in ('session','trend','volhi','dxyconf','xagconf'):
            mask &= z[c].to_numpy()==z[c].iloc[i]
        a=z.loc[mask,'future_atr'].dropna().to_numpy()
        if len(a)<MIN_N:continue
        mean=float(a.mean());se=float(a.std(ddof=1)/np.sqrt(len(a)));ts=mean/se if se>0 else 0
        if abs(ts)<MIN_T or abs(mean)<MIN_MOVE:continue
        d=1 if mean>0 else -1
        out.append(Signal(t,d,mean,len(a),ts,resolve(z,i,d)))
    return out

def stats(s):
    if not s:return dict(n=0,e=np.nan,w=np.nan,lo=np.nan,hi=np.nan)
    x=np.array([q.r for q in s]);day=pd.Series(x,index=[q.t.floor('D') for q in s]).groupby(level=0).mean().to_numpy();rng=np.random.default_rng(921)
    b=np.array([rng.choice(day,len(day),True).mean() for _ in range(2000)])
    return dict(n=len(x),e=x.mean(),w=(x>0).mean(),lo=np.quantile(b,.025),hi=np.quantile(b,.975))

def show(name,s):
    q=stats(s);print(f'{name:14s} n={q["n"]:4d} E={q["e"]:+.4f}R win={100*q["w"]:.1f}% CI=[{q["lo"]:+.4f},{q["hi"]:+.4f}]');return q

def main():
    z=build();s=run(z);end=z.index[-1]
    a=[q for q in s if q.t<end-pd.Timedelta(days=60)];b=[q for q in s if end-pd.Timedelta(days=60)<=q.t<end-pd.Timedelta(days=10)];c=[q for q in s if q.t>=end-pd.Timedelta(days=10)]
    print('PREQUENTIAL CONTEXTUAL ANALOG',z.index[-1]);show('older OOS',a);sb=show('recent OOS',b);sc=show('last 10d OOS',c)
    if s:print('latest emitted',s[-1])
    passed=sb['n']>=20 and sb['lo']>0 and sc['n']>=4 and sc['e']>0
    print('DECISION','PASS' if passed else 'FAIL')
    return 0 if passed else 2

if __name__=='__main__':raise SystemExit(main())
