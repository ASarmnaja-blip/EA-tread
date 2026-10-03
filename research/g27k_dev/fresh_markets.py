#!/usr/bin/env python3
"""G27K #1, unchanged, on 28 markets it has never run on (ledger g27k_fresh_markets).

Costs as registered: round trip = max(2 bp, median Dukascopy spread + 1 bp);
swap per night assumed (FX 1.0 bp both sides; indices and commodities 2.0 bp
long, 1.0 bp short; ETH = the BTC broker spec). Admission per market: mean net
R > 0 with t > 2, positive in both halves of its own data range, and still
positive with the assumed swap doubled. Then S5 + every admitted market
against S5 (brake 25%).

Usage: python3 research/g27k_dev/fresh_markets.py --root <data-snapshot checkout>
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
import h4d1_pattern_search as P
import multi_market_search as MMS
import suite as SU
import walkforward_controller as W

FX = ["GBPUSD", "USDCAD", "NZDUSD", "USDSEK", "EURJPY", "GBPJPY", "AUDJPY", "CADJPY", "CHFJPY", "NZDJPY", "EURGBP",
      "EURAUD", "EURCAD", "EURCHF", "GBPAUD", "GBPCHF", "AUDCAD", "AUDNZD"]
IDX = ["UK100", "FRA40", "AUS200", "HK50", "STOXX50"]
COM = ["UKOIL", "XPTUSD", "XPDUSD", "XNGUSD"]
NEW = FX + IDX + COM + ["ETHUSD"]
S5 = ("XAUUSD", "XAGUSD", "BTCUSD", "JP225", "USDJPY")
S4U = ("XAUUSD", "XAGUSD", "BTCUSD", "USDJPY")
# Exness Standard Cent instrument list (help centre, 2026-10-03): every FX pair here except USDSEK, UKOIL, ETHUSD (MT5)
CENT = [m for m in FX if m != "USDSEK"] + ["UKOIL", "ETHUSD"]
PSTART, MID, END = "2011-09-01", "2018-01-01", "2026-10-01"


REAL = {}


def specs(C, real_xpt=False):
    for k in ("XPTUSD", "BTCUSD"):
        REAL.setdefault(k, dict(C.SPECS[k]))
    sp = {**json.loads((HERE / "fresh_spreads_fx.json").read_text()), **json.loads((HERE / "fresh_spreads_other.json").read_text())}
    out = {}
    for m in NEW:
        if m == "ETHUSD":
            out[m] = dict(REAL["BTCUSD"])
            continue
        if m == "XPTUSD" and real_xpt:
            out[m] = dict(REAL["XPTUSD"])
            continue
        fx = m in FX
        s = sp.get(m, np.nan)
        out[m] = dict(swap_mode=1, swap_long=0.0, swap_short=0.0, rollover3=5 if m in IDX else 3, contract=1.0, currency_profit="USD",
                      price=1.0, median_spread_bp=float(s), cost_rt_bp=float(max(2.0, s + 1.0)) if np.isfinite(s) else 4.0,
                      swap_long_bp=1.0 if fx else 2.0, swap_short_bp=1.0)
    return out


def trades(m, H1m, RP, G, K, ext):
    K.START = W.ts("2009-09-01")
    Mk = K.prepare(m, H1m, ext)
    X = G.features(G.frames(H1m), m, "H4")
    X["sec"] = 14400
    d = K.directions(Mk, "C8", "D3", "E1", "J1")
    idx = np.flatnonzero(d)
    vp = pd.Series(X["a14"]).rolling(250, min_periods=100).rank(pct=True).to_numpy()
    return pd.DataFrame([dict(mkt=m, t=int(r["t"]), tx=int(r["t_exit"]), R=float(r["R"]), R_swap=float(r["R_swap"]), d=int(r["d"]),
                              vp=float(vp[max(r["e"] - 1, 0)]), sc=int(r["t"])) for r in RP.sim_paths(X, m, idx, d[idx], "I1")])


def tstat(x):
    x = np.asarray(x, float)
    return float(x.mean() / x.std(ddof=1) * np.sqrt(len(x))) if len(x) > 2 else float("nan")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    a = ap.parse_args()
    P.setup(a.root)
    G, K, C = P._M["G"], P._M["K"], P._M["C"]
    sys.path.insert(0, str(pathlib.Path(a.root) / "research" / "grid768"))
    import report768 as RP
    ext = K.externals()
    news = W.news_times(a.root)
    C.SPECS.update(specs(C))
    H1 = {m: MMS.load(m, G) for m in NEW + list(S5)}
    T = {m: trades(m, H1[m], RP, G, K, ext) for m in NEW}
    res = {"markets": {}, "specs": {m: C.SPECS[m] for m in NEW}}
    end = W.ts(END)
    for m in NEW:
        x = T[m]
        if not len(x):
            continue
        t0 = int(H1[m]["t"][0])
        mid = t0 + (end - t0) // 2
        h1, h2 = x[x.t < mid], x[x.t >= mid]
        r = dict(n=len(x), first=str(pd.Timestamp(t0, unit="s").date()), mean=float(x.R.mean()), t=tstat(x.R),
                 win=float((x.R > 0).mean()), mean_h1=float(h1.R.mean()), mean_h2=float(h2.R.mean()),
                 mean_swap2=float((x.R - x.R_swap).mean()), mean_swap0=float((x.R + x.R_swap).mean()),
                 cost_rt_bp=C.SPECS[m]["cost_rt_bp"])
        r["admit"] = bool(r["mean"] > 0 and r["t"] > 2.0 and r["mean_h1"] > 0 and r["mean_h2"] > 0 and r["mean_swap2"] > 0)
        res["markets"][m] = r
    for m, r in res["markets"].items():
        r["account"] = "cent" if m in CENT else "standard"
    for grp, label in (("cent", "CENT (also on Standard)"), ("standard", "STANDARD ONLY")):
        print(f"  --- {label}")
        print(f"  {'market':8s} {'from':10s} {'n':>4s} {'mean R':>7s} {'t':>6s} {'half1':>7s} {'half2':>7s} {'swap x2':>7s} {'cost bp':>7s}")
        for m, r in sorted(((k, v) for k, v in res["markets"].items() if v["account"] == grp), key=lambda kv: -kv[1]["mean"]):
            print(f"  {m:8s} {r['first']:10s} {r['n']:4d} {r['mean']:+7.3f} {r['t']:+6.2f} {r['mean_h1']:+7.3f} {r['mean_h2']:+7.3f} "
                  f"{r['mean_swap2']:+7.3f} {r['cost_rt_bp']:7.2f}" + ("  ADMIT" if r["admit"] else ""))
    pos = sum(r["mean"] > 0 for r in res["markets"].values())
    res["positive"] = pos
    res["admitted"] = [m for m, r in res["markets"].items() if r["admit"]]
    res["admitted_cent"] = [m for m in res["admitted"] if m in CENT]
    print(f"  positive {pos}/{len(res['markets'])} (16-market base rate 7/16) · admitted: {res['admitted']} · on cent: {res['admitted_cent']}")

    # XPTUSD at the real Exness broker spec (fidelity check, reported only)
    C.SPECS["XPTUSD"] = specs(C, real_xpt=True)["XPTUSD"]
    xp = trades("XPTUSD", H1["XPTUSD"], RP, G, K, ext)
    res["xptusd_real_spec"] = dict(n=len(xp), mean=float(xp.R.mean()), t=tstat(xp.R))
    print(f"  XPTUSD at the real Exness spec (spread {C.SPECS['XPTUSD']['median_spread_bp']:.1f} bp): mean {xp.R.mean():+.3f}R t {tstat(xp.R):+.2f}")
    C.SPECS["XPTUSD"] = specs(C)["XPTUSD"]

    # correlations: monthly R with S5 and with the JPY theme
    g = SU.g27k_trades(S5, H1, RP, G, K, ext)
    mon = lambda d: pd.Series(d.R.to_numpy(), index=pd.to_datetime(d.tx, unit="s")).resample("ME").sum()
    s5m, jpy = mon(g[g.t >= W.ts(PSTART)]), mon(g[g.mkt.isin(["USDJPY", "JP225"]) & (g.t >= W.ts(PSTART))])

    def cor(a_, b_):
        i = a_.index.union(b_.index)
        return float(np.corrcoef(a_.reindex(i, fill_value=0), b_.reindex(i, fill_value=0))[0, 1])
    for m, r in res["markets"].items():
        x = mon(T[m][T[m].t >= W.ts(PSTART)])
        r["corr_S5"], r["corr_JPY"] = cor(x, s5m), cor(x, jpy)

    cols = ["mkt", "t", "tx", "R", "vp", "sc"]
    res["portfolio"] = {}
    pos_all = [m for m, r in res["markets"].items() if r["mean"] > 0]
    # (name, base set, added markets)
    cands = [("CENT: S4U", S4U, [])]
    if res["admitted_cent"]:
        cands.append(("CENT: S4U+admitted cent", S4U, res["admitted_cent"]))
    cands += [("STANDARD: S5", S5, [])]
    if res["admitted"]:
        cands.append(("STANDARD: S5+admitted", S5, res["admitted"]))
    cands.append(("STANDARD: S5+all positive (hindsight, info)", S5, pos_all))
    for name, bset, add in cands:
        TT = pd.concat([g[g.mkt.isin(bset)][cols]] + [T[m][cols] for m in add], ignore_index=True)
        st, eq, _ = SU.simulate(TT, "brake", PSTART, END, news=news)
        a1, _, _ = SU.simulate(TT, "brake", PSTART, MID, news=news)
        a2, _, _ = SU.simulate(TT, "brake", MID, END, news=news)
        st.update(mar_h1=a1["mar"], mar_h2=a2["mar"], mc=SU.monte_carlo(eq), markets=list(bset) + add)
        res["portfolio"][name] = st
        print(f"  {name:44s} CAGR {st['cagr']:+6.1%}  DD {st['dd']:5.1%}  MAR {st['mar']:.2f}  halves {a1['mar']:+.2f}/{a2['mar']:+.2f}  "
              f"worst yr {st['worst_year']:+.0%}  n {st['n']}  MC P(DD>50%) {st['mc']['p_dd50']:.1%}", flush=True)
    for m in res["admitted"]:
        r = res["markets"][m]
        print(f"  {m}: corr with S5 {r['corr_S5']:+.2f}, with USDJPY+JP225 {r['corr_JPY']:+.2f}")
    P_ = res["portfolio"]
    for new, old, key in (("STANDARD: S5+admitted", "STANDARD: S5", "portfolio_pass"),
                          ("CENT: S4U+admitted cent", "CENT: S4U", "portfolio_pass_cent")):
        if new in P_:
            res[key] = bool(P_[new]["mar_h1"] > P_[old]["mar_h1"] and P_[new]["mar_h2"] > P_[old]["mar_h2"])
            print(f"  {key} (MAR better in both halves): {res[key]}")
    (HERE / "fresh_markets.json").write_text(json.dumps(res, indent=1, default=float))


if __name__ == "__main__":
    main()
