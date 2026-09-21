"""Small, locked walk-forward search for a current-regime XAUUSD edge.

Two predeclared models see the same compact feature set.  They are ranked only
on rolling out-of-sample development predictions.  The last ten calendar days
are opened once for the development winner.  This is deliberately a small
search rather than a parameter sweep.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

ROOT = Path(__file__).resolve().parents[2]
HORIZON = 12                 # one hour on M5
TRAIN_DAYS = 60
TEST_CHUNK_DAYS = 5
HOLDOUT_DAYS = 10
PRED_GATE_ATR = 0.60
STOP_ATR = 1.50
TARGET_R = 1.50
SPREAD = 0.09
SLIP_SIDE = 0.10


@dataclass
class Trade:
    time: pd.Timestamp
    direction: int
    pred_atr: float
    net_r: float
    why: str


def load_csv(symbol: str) -> pd.DataFrame:
    p = ROOT / "data" / f"{symbol}_M5.csv"
    d = pd.read_csv(p, parse_dates=["time"])
    d["time"] = pd.to_datetime(d.time, utc=True)
    return d.set_index("time").sort_index()


def dataset() -> tuple[pd.DataFrame, list[str]]:
    x = load_csv("XAUUSD")
    d = load_csv("DXY")[["close"]].rename(columns={"close": "dxy"})
    s = load_csv("XAGUSD")[["close"]].rename(columns={"close": "xag"})
    z = x.join(d, how="inner").join(s, how="inner")
    prev = z.close.shift(1)
    tr = pd.concat([z.high-z.low, (z.high-prev).abs(), (z.low-prev).abs()], axis=1).max(axis=1)
    z["atr"] = tr.rolling(14).mean()
    atr_slow = tr.rolling(288).mean()
    ema20 = z.close.ewm(span=20, adjust=False).mean()
    ema50 = z.close.ewm(span=50, adjust=False).mean()
    feats: list[str] = []
    for k in (1, 3, 12, 48, 96):
        name = f"xret{k}"; z[name] = (z.close-z.close.shift(k))/z.atr; feats.append(name)
    for col in ("dxy", "xag"):
        scale = z[col].diff().rolling(288).std()
        for k in (3, 12, 48):
            name=f"{col}ret{k}"; z[name]=(z[col]-z[col].shift(k))/(scale*np.sqrt(k)); feats.append(name)
    z["ema20gap"]=(z.close-ema20)/z.atr; feats.append("ema20gap")
    z["ema2050"]=(ema20-ema50)/z.atr; feats.append("ema2050")
    z["volratio"]=z.atr/atr_slow; feats.append("volratio")
    z["body"]=(z.close-z.open)/z.atr; feats.append("body")
    z["range"]=(z.high-z.low)/z.atr; feats.append("range")
    z["hour_sin"]=np.sin(2*np.pi*z.index.hour/24); feats.append("hour_sin")
    z["hour_cos"]=np.cos(2*np.pi*z.index.hour/24); feats.append("hour_cos")
    z["y"]=(z.close.shift(-HORIZON)-z.close)/z.atr
    return z.replace([np.inf,-np.inf],np.nan), feats


def models():
    return {
        "ridge": make_pipeline(StandardScaler(), Ridge(alpha=10.0)),
        "hist_gb": HistGradientBoostingRegressor(max_depth=3, max_iter=120,
                    learning_rate=.05, l2_regularization=2.0,
                    min_samples_leaf=80, random_state=20260921),
    }


def rolling_predictions(z: pd.DataFrame, feats: list[str], name: str,
                        start: pd.Timestamp, end: pd.Timestamp) -> pd.Series:
    out=[]; cursor=start
    while cursor < end:
        stop=min(cursor+pd.Timedelta(days=TEST_CHUNK_DAYS),end)
        train=z.loc[(z.index >= cursor-pd.Timedelta(days=TRAIN_DAYS)) & (z.index < cursor)].dropna(subset=feats+["y"])
        test=z.loc[(z.index >= cursor) & (z.index < stop)].dropna(subset=feats)
        if len(train)>5000 and len(test):
            model=models()[name]
            model.fit(train[feats],train.y)
            out.append(pd.Series(model.predict(test[feats]),index=test.index))
        cursor=stop
    return pd.concat(out).sort_index() if out else pd.Series(dtype=float)


def simulate(z: pd.DataFrame, pred: pd.Series) -> list[Trade]:
    loc=z.index.get_indexer(pred.index)
    candidates=[]
    for t,i in zip(pred.index,loc):
        p=float(pred.loc[t])
        if i>=0 and abs(p)>=PRED_GATE_ATR and 7 <= t.hour < 20:
            candidates.append((i,p))
    out=[]; last_exit=-1
    for i,p in candidates:
        if i+1>=len(z) or i<last_exit: continue
        d=1 if p>0 else -1; atr=float(z.atr.iloc[i]); entry=float(z.open.iloc[i+1])
        if not np.isfinite(atr) or atr<=0: continue
        risk=STOP_ATR*atr; stop=entry-d*risk; target=entry+d*TARGET_R*risk
        end=min(i+1+HORIZON,len(z)-1); px=float(z.close.iloc[end]); why="TIME"; exit_i=end
        for k in range(i+1,end+1):
            hs=z.low.iloc[k]<=stop if d>0 else z.high.iloc[k]>=stop
            ht=z.high.iloc[k]>=target if d>0 else z.low.iloc[k]<=target
            if hs and ht: px,why,exit_i=stop,"BOTH_STOP_FIRST",k; break
            if hs: px,why,exit_i=stop,"STOP",k; break
            if ht: px,why,exit_i=target,"TARGET",k; break
        net=d*(px-entry)/risk-(SPREAD+2*SLIP_SIDE)/risk
        out.append(Trade(z.index[i+1],d,p,float(net),why)); last_exit=exit_i
    return out


def stats(tr: list[Trade]) -> dict:
    if not tr:return dict(n=0,mean=np.nan,win=np.nan,lo=np.nan,hi=np.nan)
    x=np.array([q.net_r for q in tr]); day=pd.Series(x,index=[q.time.floor('D') for q in tr]).groupby(level=0).mean().to_numpy()
    rng=np.random.default_rng(20260921)
    b=np.array([rng.choice(day,len(day),True).mean() for _ in range(2000)])
    return dict(n=len(x),mean=float(x.mean()),win=float((x>0).mean()),lo=float(np.quantile(b,.025)),hi=float(np.quantile(b,.975)))


def fmt(name,s):
    print(f"{name:12s} n={s['n']:4d} mean={s['mean']:+.4f}R win={100*s['win']:.1f}% CI=[{s['lo']:+.4f},{s['hi']:+.4f}]")


def main()->int:
    z,feats=dataset(); end=z.index[-1]; hold=end-pd.Timedelta(days=HOLDOUT_DAYS); dev_start=end-pd.Timedelta(days=60)
    print("LOCKED WALK-FORWARD CURRENT-REGIME SEARCH")
    print("end",end,"development",dev_start,"to",hold,"holdout",hold,"to",end)
    dev={}
    for name in models():
        p=rolling_predictions(z,feats,name,dev_start,hold); tr=simulate(z,p); s=stats(tr); dev[name]=(s,p); fmt(name+" dev",s)
    eligible=[(v[0]['mean'],k) for k,v in dev.items() if v[0]['n']>=30 and v[0]['lo']>0]
    if not eligible:
        print("DECISION FAIL: no development model has positive lower confidence bound")
        return 2
    winner=max(eligible)[1]; print("development winner",winner)
    hp=rolling_predictions(z,feats,winner,hold,end); ht=simulate(z,hp); hs=stats(ht); fmt(winner+" HOLD",hs)
    passed=hs['n']>=8 and hs['mean']>0 and hs['lo']>0
    print("DECISION", "PASS" if passed else "FAIL")
    if len(hp): print("last historical prediction",hp.index[-1],f"{hp.iloc[-1]:+.3f} ATR")
    return 0 if passed else 2


if __name__=="__main__": raise SystemExit(main())
