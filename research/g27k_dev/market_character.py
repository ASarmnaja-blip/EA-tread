#!/usr/bin/env python3
"""How the 16 original and the 28 fresh markets move, and which property goes
with G27K #1 working. 2012-01..2023-12 only (the stage-2 sealed period
2024-01..2026-09 is not read).

Per market: annualised volatility of daily returns, median D1 ATR in % of
price, annualised drift (log trend), trend persistence (20-day efficiency
ratio: net move / path length; and the 10-day variance ratio), cost as a
share of the G27K stop (round trip / 2 x H4 ATR20), and G27K #1 mean net R
per trade over the same years. Spearman correlation of each property with
the mean R across all 44 markets.

Usage: python3 research/g27k_dev/market_character.py --root <snap>
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

LO, HI = "2012-01-01", "2024-01-01"


def props(b, cost_bp):
    t = pd.to_datetime(np.asarray(b["t"], np.int64), unit="s")
    s = pd.DataFrame(dict(o=b["o"], h=b["h"], l=b["l"], c=b["c"]), index=t)
    s = s[(s.index >= LO) & (s.index < HI)]
    d = s.resample("D", offset="22h").agg(dict(o="first", h="max", l="min", c="last")).dropna()
    h4 = s.resample("4h", offset="22h").agg(dict(h="max", l="min", c="last")).dropna()
    r = np.log(d.c).diff().dropna()
    pc = d.c.shift(1)
    atr = pd.concat([d.h - d.l, (d.h - pc).abs(), (d.l - pc).abs()], axis=1).max(axis=1).rolling(20).mean()
    pc4 = h4.c.shift(1)
    atr4 = pd.concat([h4.h - h4.l, (h4.h - pc4).abs(), (h4.l - pc4).abs()], axis=1).max(axis=1).rolling(20).mean()
    yrs = (d.index[-1] - d.index[0]).days / 365.25
    er = (d.c.diff(20).abs() / d.c.diff().abs().rolling(20).sum()).median()
    r10 = np.log(d.c).diff(10).dropna()
    vr = r10.var() / (10 * r.var())
    return dict(vol=float(r.std() * np.sqrt(252)), atr_pct=float((atr / d.c).median() * 100),
                drift=float(np.log(d.c.iloc[-1] / d.c.iloc[0]) / yrs), er20=float(er), vr10=float(vr),
                cost_share=float(cost_bp / 1e4 / (2 * (atr4 / h4.c).median())))


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
    rows = []
    for grp, mkts in (("16 เดิม", MMS.MARKETS), ("28 ใหม่", FM.NEW)):
        for m in mkts:
            b = MMS.load(m, G) if grp == "16 เดิม" else L3.load(m, "2009-01-01", HI)
            T = FM.trades(m, b, RP, G, K, ext)
            T = T[(T.t >= W.ts(LO)) & (T.t < W.ts(HI))]
            pr = props(b, C.SPECS[m]["cost_rt_bp"])
            rows.append(dict(group=grp, mkt=m, n=len(T), R=float(T.R.mean()) if len(T) else np.nan, **pr))
            print(f"  {grp} {m:8s} R {rows[-1]['R']:+.3f}  vol {pr['vol']:.1%}  ATR {pr['atr_pct']:.2f}%  drift {pr['drift']:+.1%}/yr  "
                  f"ER20 {pr['er20']:.3f}  VR10 {pr['vr10']:.2f}  cost/stop {pr['cost_share']:.3f}", flush=True)
    D = pd.DataFrame(rows)
    cols = ["R", "vol", "atr_pct", "drift", "er20", "vr10", "cost_share"]
    print("\n  group medians")
    print(D.groupby("group")[cols].median().to_string(float_format=lambda x: f"{x:+.3f}"))
    corr = {c: float(D[["R", c]].corr("spearman").iloc[0, 1]) for c in cols[1:]}
    print("\n  Spearman correlation with G27K mean R (44 markets):", {k: round(v, 2) for k, v in corr.items()})
    (HERE / "market_character.json").write_text(json.dumps(dict(rows=rows, corr=corr), indent=1, default=float))


if __name__ == "__main__":
    main()
