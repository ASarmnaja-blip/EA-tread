#!/usr/bin/env python3
"""Every market we dropped: can it turn positive, or does its price not move
enough? G27K #1 (net of costs) on all 44 markets, 2012-01..2026-09, per
market-year next to how the market moved that year.

Per market-year: trades, mean and total net R, the year's price change
(log), the 20-day efficiency ratio (net move / path), D1 ATR in % of price.
Evidence:
  (a) R per trade by the year's price change, kept vs dropped markets
      (trade-weighted, t over trades) - is it the market or the trend?
  (b) a weighted least squares of yearly mean R on yearly price change,
      efficiency and cost share, with a dropped-market dummy, standard
      errors by market-cluster bootstrap
  (c) per dropped market: positive years, best year, last 12 months, how
      often it had a year rising > 15%, and what G27K made in those years.

Usage: python3 research/g27k_dev/dropped_markets.py --root <snap>
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
import walkforward_controller as W

LO, HI = "2012-01-01", "2026-10-01"
KEPT = ("XAUUSD", "XAGUSD", "BTCUSD", "ETHUSD", "USDJPY", "JP225")
BINS = [-np.inf, -0.15, -0.05, 0.05, 0.15, 0.30, np.inf]
BIN_TH = ["ลง > 15%", "ลง 5–15%", "ทรงตัว ±5%", "ขึ้น 5–15%", "ขึ้น 15–30%", "ขึ้น > 30%"]


def tstat(R):
    R = np.asarray(R, float)
    return float(R.mean() / R.std(ddof=1) * np.sqrt(len(R))) if len(R) > 2 and R.std() > 0 else float("nan")


def yearly_moves(b, cost_bp):
    t = pd.to_datetime(np.asarray(b["t"], np.int64), unit="s")
    s = pd.DataFrame(dict(o=b["o"], h=b["h"], l=b["l"], c=b["c"]), index=t)
    s = s[(s.index >= LO) & (s.index < HI)]
    d = s.resample("D", offset="22h").agg(dict(o="first", h="max", l="min", c="last")).dropna()
    pc = d.c.shift(1)
    atr = pd.concat([d.h - d.l, (d.h - pc).abs(), (d.l - pc).abs()], axis=1).max(axis=1).rolling(20).mean() / d.c
    er = d.c.diff(20).abs() / d.c.diff().abs().rolling(20).sum()
    h4 = s.resample("4h", offset="22h").agg(dict(h="max", l="min", c="last")).dropna()
    pc4 = h4.c.shift(1)
    atr4 = (pd.concat([h4.h - h4.l, (h4.h - pc4).abs(), (h4.l - pc4).abs()], axis=1).max(axis=1).rolling(20).mean() / h4.c)
    out = {}
    for y, g in d.groupby(d.index.year):
        if len(g) < 120:
            continue
        out[int(y)] = dict(move=float(np.log(g.c.iloc[-1] / g.c.iloc[0])), er=float(er.loc[g.index].median()), atr=float(atr.loc[g.index].median() * 100),
                           cost=float(cost_bp / 1e4 / (2 * atr4[atr4.index.year == y].median())))
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
    ext = K.externals()
    mk = [m for m in MMS.MARKETS] + [m for m in FM.NEW]
    rows, trades = [], []
    for m in mk:
        b = MMS.load(m, G) if m in MMS.MARKETS else L3.load(m, "2009-01-01", HI)
        T = FM.trades(m, b, RP, G, K, ext)
        T = T[(T.t >= W.ts(LO)) & (T.t < W.ts(HI))]
        T = T.assign(year=pd.to_datetime(T.t, unit="s").dt.year, mkt=m)
        trades.append(T[["mkt", "t", "R", "year"]])
        mv = yearly_moves(b, C.SPECS[m]["cost_rt_bp"])
        for y, v in mv.items():
            x = T.R[T.year == y]
            rows.append(dict(mkt=m, kept=m in KEPT, year=y, n=int(len(x)), sumR=float(x.sum()), R=float(x.mean()) if len(x) else np.nan, **v))
        print(f"  {m:8s} trades {len(T):4d}  R {T.R.mean():+.3f}", flush=True)
    D = pd.DataFrame(rows)
    TT = pd.concat(trades, ignore_index=True).merge(D[["mkt", "year", "move", "er"]], on=["mkt", "year"], how="inner")
    TT["kept"] = TT.mkt.isin(KEPT)
    TT["bin"] = pd.cut(TT.move, BINS, labels=False)
    # (a) R per trade by the year's move
    bins = []
    for i, lab in enumerate(BIN_TH):
        r = dict(bin=lab)
        for g, nm in ((True, "kept"), (False, "dropped")):
            x = TT.R[(TT.bin == i) & (TT.kept == g)]
            r[nm] = dict(n=int(len(x)), R=float(x.mean()) if len(x) else np.nan, t=tstat(x),
                         my=int(len(D[(pd.cut(D.move, BINS, labels=False) == i) & (D.kept == g)])))
        bins.append(r)
        print(f"  {lab:12s} kept n {r['kept']['n']:4d} R {r['kept']['R']:+.3f} t {r['kept']['t']:+.1f} | dropped n {r['dropped']['n']:5d} R {r['dropped']['R']:+.3f} t {r['dropped']['t']:+.1f} "
              f"({r['dropped']['my']} market-years)")
    # (b) WLS of yearly mean R on move, efficiency, cost share and a dropped dummy, market-cluster bootstrap
    E = D[D.n >= 5].copy()
    E["drop"] = (~E.kept).astype(float)
    cols = ["move", "er", "cost", "drop"]

    def fit(F):
        X = np.column_stack([np.ones(len(F))] + [F[c].to_numpy(float) for c in cols])
        w = np.sqrt(F.n.to_numpy(float))
        return np.linalg.lstsq(X * w[:, None], F.R.to_numpy(float) * w, rcond=None)[0]
    beta = fit(E)
    rng = np.random.default_rng(7)
    ms = E.mkt.unique()
    boots = np.array([fit(pd.concat([E[E.mkt == m] for m in rng.choice(ms, len(ms))])) for _ in range(1000)])
    se = boots.std(axis=0)
    reg = {nm: dict(b=float(b_), se=float(s_), t=float(b_ / s_)) for nm, b_, s_ in zip(["const"] + cols, beta, se)}
    print("  WLS yearly mean R:", {k: f"{v['b']:+.3f} (t {v['t']:+.1f})" for k, v in reg.items()})
    # (c) per dropped market
    per = []
    last0 = W.ts("2025-10-01")
    TA = pd.concat(trades, ignore_index=True)
    for m in mk:
        d = D[D.mkt == m]
        x = TA[TA.mkt == m]
        up = d[d.move > np.log(1.15)]
        per.append(dict(mkt=m, kept=m in KEPT, n=int(len(x)), R=float(x.R.mean()), t=tstat(x.R), years=int(len(d)), pos=int((d.sumR > 0).sum()),
                        best_year=int(d.loc[d.sumR.idxmax(), "year"]) if len(d) else None, best_sumR=float(d.sumR.max()) if len(d) else np.nan,
                        last12=float(x.R[x.t >= last0].sum()), last12_n=int((x.t >= last0).sum()), up_years=int(len(up)),
                        up_R=float(TT.R[(TT.mkt == m) & (TT.move > np.log(1.15))].mean()) if len(up) else np.nan,
                        drift=float(d.move.mean()), er=float(d.er.median()), atr=float(d.atr.median()), cost=float(d.cost.median()),
                        cum={int(y): float(v) for y, v in d.set_index("year").sumR.items()}))
    for p in sorted(per, key=lambda p: -p["R"]):
        print(f"  {'KEEP' if p['kept'] else 'drop'} {p['mkt']:8s} n {p['n']:4d} R {p['R']:+.3f} t {p['t']:+.1f} | + years {p['pos']}/{p['years']} best {p['best_year']} {p['best_sumR']:+.1f}R | "
              f"last 12m {p['last12']:+.1f}R ({p['last12_n']}) | years up>15% {p['up_years']} R there {p['up_R']:+.2f} | drift {p['drift']:+.1%} ER {p['er']:.3f} ATR {p['atr']:.2f}% cost {p['cost']:.3f}")
    (HERE / "dropped_markets.json").write_text(json.dumps(dict(bins=bins, reg=reg, markets=per, panel=rows), indent=1, default=float))


if __name__ == "__main__":
    main()
