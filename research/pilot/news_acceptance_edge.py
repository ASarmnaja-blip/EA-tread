"""Non-circular M1 news acceptance/rejection execution test.

Only information available one minute after a USD HIGH release is used:
surprise direction, the first XAU minute, and the first DXY minute.  Entry is
the following M1 open.  No 5/15/60-minute value or hindsight scenario label is
an input.  Acceptance and rejection are predeclared candidates; development
chooses one and the final 30% of events are opened once.
"""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[2]
POINT=.001; H=59; SLIP_SIDE=.20; TARGET_R=1.5

@dataclass
class Trade:
    ep:int; kind:str; d:int; r:float

def load(sym):
    d=pd.read_csv(ROOT/'data'/f'{sym}_M1.csv',parse_dates=['time']);d.time=pd.to_datetime(d.time,utc=True)
    return d.set_index('time').sort_index()

def atr_at(x,i,n=60):
    q=x.iloc[max(0,i-n):i];pc=q.close.shift(1).fillna(q.close.iloc[0]);tr=np.maximum(q.high-q.low,np.maximum((q.high-pc).abs(),(q.low-pc).abs()))
    return float(tr.mean())

def candidates():
    a=pd.read_csv(ROOT/'research/pilot/results/news_assessments.csv').sort_values('epoch')
    x=load('XAUUSD');d=load('DXY')
    out=[]
    for _,row in a.iterrows():
        ep=int(row.epoch);t=pd.to_datetime(ep,unit='s',utc=True)
        i=x.index.searchsorted(t);j=d.index.searchsorted(t)
        if i<60 or i+H+2>=len(x) or j<1 or j+1>=len(d):continue
        anchor=float(x.close.iloc[i-1]); first=float(x.close.iloc[i]-anchor); ax=atr_at(x,i)
        dfirst=float(d.close.iloc[j]-d.close.iloc[j-1])
        if not np.isfinite(row.surprise_z) or abs(row.surprise_z)<.5 or not row.hypothesis_dir:continue
        if abs(first)<.5*ax or np.sign(dfirst)!=-np.sign(first):continue
        direction=1 if first>0 else -1;kind='accept' if direction==int(row.hypothesis_dir) else 'reject'
        entry=float(x.open.iloc[i+1]);risk=max(3*ax,.75*abs(first),1.0);stop=entry-direction*risk;target=entry+direction*TARGET_R*risk
        end=min(i+1+H,len(x)-1);px=float(x.close.iloc[end])
        for k in range(i+1,end+1):
            hs=x.low.iloc[k]<=stop if direction>0 else x.high.iloc[k]>=stop
            ht=x.high.iloc[k]>=target if direction>0 else x.low.iloc[k]<=target
            if hs and ht:px=stop;break
            if hs:px=stop;break
            if ht:px=target;break
        spread=max(float(x.spread.iloc[i])*POINT,.09) if 'spread' in x else .09
        net=direction*(px-entry)/risk-(spread+2*SLIP_SIDE)/risk
        out.append(Trade(ep,kind,direction,float(net)))
    return out

def stats(q):
    if not q:return dict(n=0,e=np.nan,w=np.nan,lo=np.nan,hi=np.nan)
    x=np.array([v.r for v in q]);rng=np.random.default_rng(921);b=np.array([rng.choice(x,len(x),True).mean() for _ in range(5000)])
    return dict(n=len(x),e=x.mean(),w=(x>0).mean(),lo=np.quantile(b,.025),hi=np.quantile(b,.975))

def show(name,q):
    s=stats(q);print(f'{name:16s} n={s["n"]:3d} E={s["e"]:+.4f}R win={100*s["w"]:.1f}% CI=[{s["lo"]:+.4f},{s["hi"]:+.4f}]');return s

def main():
    q=candidates();eps=sorted(set(v.ep for v in q));cut=eps[int(.70*len(eps))] if eps else 0
    print('M1 NEWS REACTION - NON-CIRCULAR','events',len(eps),'holdout starts',pd.to_datetime(cut,unit='s',utc=True) if cut else '-')
    dev={}
    for kind in ('accept','reject'):
        v=[x for x in q if x.kind==kind and x.ep<cut];dev[kind]=show(kind+' dev',v)
    elig=[(s['e'],k) for k,s in dev.items() if s['n']>=20 and s['lo']>0]
    if not elig:print('DECISION FAIL: neither mechanism passes development');return 2
    win=max(elig)[1];print('development winner',win)
    ho=[x for x in q if x.kind==win and x.ep>=cut];s=show(win+' HOLDOUT',ho)
    passed=s['n']>=8 and s['lo']>0
    print('DECISION','PASS' if passed else 'FAIL')
    return 0 if passed else 2

if __name__=='__main__':raise SystemExit(main())
