#!/usr/bin/env python3
"""What caused the bad periods of G27K #1? Drawdown episodes of the Standard
6-market account (brake, BTC/ETH 0.5%, others 1%), 2011-09..2026-09: every
balance drawdown deeper than 12%, from its peak to its trough and on to
recovery. Per episode: depth, length, trades closed peak->trough with their R
by market, win rate, stop-outs, gap losses (worse than -1.2R), and how each
market's price moved (change and 20-day efficiency) over the same span.

Usage: python3 research/g27k_dev/dd_episodes.py --root <snap>
"""
import argparse
import json
import pathlib
import sys

import numpy as np
import pandas as pd

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))
import fresh_markets as FM
import fresh_search_l3 as L3
import h4d1_pattern_search as P
import multi_market_search as MMS
import report_final6 as RF
import report_suite_detail as RSD
import suite as SU
import walkforward_controller as W

START, END = "2011-09-01", "2026-10-01"
DEPTH = 0.12
HALF = {"BTCUSD": 0.5, "ETHUSD": 0.5}


def episodes(eq):
    pk, pk_t, out, cur = eq.iloc[0], eq.index[0], [], None
    for t, v in eq.items():
        if v >= pk:
            if cur and cur["depth"] >= DEPTH:
                cur["recovered"] = t
                out.append(cur)
            pk, pk_t, cur = v, t, None
            continue
        d = 1 - v / pk
        if cur is None or d > cur["depth"]:
            cur = dict(peak=pk_t, trough=t, depth=d, recovered=None)
    if cur and cur["depth"] >= DEPTH:
        out.append(cur)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    a = ap.parse_args()
    P.setup(a.root)
    G, K, C = P._M["G"], P._M["K"], P._M["C"]
    sys.path.insert(0, str(pathlib.Path(a.root) / "research" / "grid768"))
    import report768 as RP
    C.SPECS.update(FM.specs(C))
    H1 = {m: (MMS.load(m, G) if m in MMS.MARKETS else L3.load(m, "2009-01-01", END)) for m in RF.STD}
    RSD.START = START
    news = W.news_times(a.root)
    rows = [r for r in RSD.g27k_rows(RF.STD, H1, RP, G, K, K.externals()) if W.ts(START) <= r["t"] < W.ts(END)]
    T = pd.DataFrame(dict(mkt=[r["mkt"] for r in rows], t=[int(r["t"]) for r in rows], tx=[int(r["t_exit"]) for r in rows], R=[r["R"] for r in rows],
                          stop=[bool(r["px"] <= r["ep"] - r["risk"] + 1e-9) for r in rows], hold=[(r["t_exit"] - r["t"]) / 86400 for r in rows]))
    F = pd.DataFrame(dict(mkt=T.mkt, t=T.t, tx=T.tx, R=T.R * T.mkt.map(HALF).fillna(1.0), vp=0.0, sc=T.t))
    st, eq, _ = SU.simulate(F, "brake", START, END, news=news)
    close = {m: pd.Series(H1[m]["c"], index=pd.to_datetime(H1[m]["t"], unit="s")).resample("D").last().dropna() for m in RF.STD}
    eff = {m: (c.diff(20).abs() / c.diff().abs().rolling(20).sum()) for m, c in close.items()}
    out = []
    for e in episodes(eq):
        p0, p1 = e["peak"], e["trough"]
        x = T[(pd.to_datetime(T.tx, unit="s") > p0) & (pd.to_datetime(T.tx, unit="s") <= p1)]
        x = x.assign(Rw=x.R * x.mkt.map(HALF).fillna(1.0))
        per = {}
        for m in RF.STD:
            y = x[x.mkt == m]
            c = close[m][(close[m].index >= p0) & (close[m].index <= p1)]
            per[m] = dict(n=int(len(y)), sumR=float(y.Rw.sum()), win=float((y.R > 0).mean()) if len(y) else np.nan,
                          move=float(c.iloc[-1] / c.iloc[0] - 1) if len(c) > 1 else np.nan,
                          er=float(eff[m][(eff[m].index >= p0) & (eff[m].index <= p1)].median()) if len(c) > 20 else np.nan)
        rec = e["recovered"]
        ep = dict(peak=str(p0.date()), trough=str(p1.date()), recovered=str(rec.date()) if rec is not None else None, depth=float(e["depth"]),
                  days_down=int((p1 - p0).days), days_total=int(((rec if rec is not None else eq.index[-1]) - p0).days), n=int(len(x)),
                  win=float((x.R > 0).mean()), sumR=float(x.Rw.sum()), stops=float(x.stop.mean()), gaps=int((x.R < -1.2).sum()), gapR=float(x.R[x.R < -1.2].sum()),
                  max_losing_streak=int(max((len(list(g)) for k, g in __import__("itertools").groupby(x.sort_values("tx").R <= 0) if k), default=0)),
                  markets=per)
        out.append(ep)
        print(f"\n  {ep['peak']} -> {ep['trough']} (recovered {ep['recovered']}): DD {ep['depth']:.1%}, {ep['days_down']} days down, {ep['days_total']} days to recover | "
              f"{ep['n']} trades win {ep['win']:.0%} sum {ep['sumR']:+.1f}R  stop exits {ep['stops']:.0%}  gaps {ep['gaps']} ({ep['gapR']:+.1f}R)  losing streak {ep['max_losing_streak']}")
        for m, v in sorted(per.items(), key=lambda kv: kv[1]["sumR"]):
            print(f"     {m:7s} n {v['n']:3d} sum {v['sumR']:+6.1f}R win {v['win']:.0%} | price {v['move']:+.1%} ER {v['er']:.3f}")
    # all trades: losses in drawdowns vs elsewhere, by market
    inside = np.zeros(len(T), bool)
    for ep in out:
        tx = pd.to_datetime(T.tx, unit="s")
        inside |= (tx > pd.Timestamp(ep["peak"])) & (tx <= pd.Timestamp(ep["trough"]) + pd.Timedelta(days=1))
    W_ = T.R * T.mkt.map(HALF).fillna(1.0)
    share = {m: float(W_[inside & (T.mkt == m)].sum()) for m in RF.STD}
    print("\n  R lost inside drawdowns by market:", {m: round(v, 1) for m, v in share.items()}, " total", round(sum(share.values()), 1))
    print(f"  overall: win {(T.R > 0).mean():.0%}  stop exits {T.stop.mean():.0%}  inside DDs win {(T.R[inside] > 0).mean():.0%}  outside {(T.R[~inside] > 0).mean():.0%}")
    (HERE / "dd_episodes.json").write_text(json.dumps(dict(episodes=out, lost_by_market=share), indent=1, default=float))


if __name__ == "__main__":
    main()
