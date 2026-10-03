#!/usr/bin/env python3
"""Worst outcomes of the final system (G27K #1 on gold, silver, BTC, JP225, 1%, 25% brake) since Sep 2011, and how
often a 10-year block-bootstrap Monte Carlo (brake applied on each path) reaches them.

Usage: run from a data-snapshot checkout: python3 research/g27k_dev/worst_case.py
"""
import sys, json, math, itertools
sys.path[:0] = ["/home/user/EA-tread/research/g27k_dev", "/home/user/EA-tread/research"]
import numpy as np, pandas as pd
import h4d1_pattern_search as P, multi_market_search as MMS, suite as SU, walkforward_controller as W
P.setup(".")
G, K = P._M["G"], P._M["K"]
sys.path.insert(0, "research/grid768")
import report768 as RP
M4 = ("XAUUSD", "XAGUSD", "BTCUSD", "JP225")
H1 = {m: MMS.load(m, G) for m in M4}
T = SU.g27k_trades(M4, H1, RP, G, K, K.externals())
news = W.news_times(".")
S = "2011-09-01"
out = {}
for v in ("brake", "normal"):
    st, eq, risk = SU.simulate(T, v, S, news=news)
    e = pd.concat([pd.Series([1.0], index=[pd.Timestamp(S)]), eq]); e = e.groupby(level=0).last()
    dd = 1 - e / e.cummax()
    tr = dd.idxmax(); pk = e[:tr].idxmax()
    rec = e[tr:][e[tr:] >= e[pk]]
    uw, longest, start = 0, 0, None
    peak = e.iloc[0]; s_uw = e.index[0]; best_uw = (0, None, None)
    for t, x in e.items():
        if x >= peak:
            span = (t - s_uw).days
            if span > best_uw[0]: best_uw = (span, s_uw, t)
            peak, s_uw = x, t
    span = (e.index[-1] - s_uw).days
    if span > best_uw[0]: best_uw = (span, s_uw, None)
    m = e.resample("ME").last().ffill()
    mr = m.pct_change().dropna()
    yr = e.resample("YE").last(); yr = (yr / yr.shift(1).fillna(1.0) - 1)
    r12 = (m / m.shift(12) - 1).dropna()
    Tt = T.loc[risk.index].assign(rf=risk.values).sort_values("t")
    Tt = Tt[Tt.rf > 0]
    loss_pct = (Tt.R * Tt.rf)
    streak = max((len(list(g)) for k, g in itertools.groupby(Tt.R > 0) if not k), default=0)
    neg_months = max((len(list(g)) for k, g in itertools.groupby(mr > 0) if not k), default=0)
    out[v] = dict(max_dd=float(dd.max()), peak=str(pk.date()), trough=str(tr.date()), recovered=str(rec.index[0].date()) if len(rec) else None,
                  longest_underwater_years=round(best_uw[0] / 365.25, 2), uw_from=str(best_uw[1].date()), uw_to=str(best_uw[2].date()) if best_uw[2] is not None else None,
                  worst_year=float(yr.min()), worst_year_at=int(yr.idxmin().year), worst_12m=float(r12.min()), worst_12m_end=str(r12.idxmin().date()),
                  worst_month=float(mr.min()), worst_month_at=str(mr.idxmin().date()), worst_trade_R=float(Tt.R.min()),
                  worst_trade_pct=float(loss_pct.min()), worst_trade=Tt.loc[Tt.R.idxmin(), ["mkt"]].iloc[0], worst_trade_t=str(pd.Timestamp(int(Tt.loc[Tt.R.idxmin(), "t"]), unit="s").date()),
                  losing_streak=int(streak), losing_months_in_row=int(neg_months), cagr=st["cagr"], trades=int(len(Tt)), win=float((Tt.R > 0).mean()))
    print(v, json.dumps(out[v], default=str))
# Monte Carlo on 1% monthly returns with the brake applied on each path
st, eq, _ = SU.simulate(T, "normal", S, news=news)
x = pd.concat([pd.Series([1.0], index=[pd.Timestamp(S)]), eq]).resample("ME").last().ffill().pct_change().dropna().to_numpy()
rng = np.random.default_rng(7); runs, years, block = 20000, 10, 6; nb = math.ceil(years * 12 / block)
res = {v: dict(dd=[], uw=[], cagr=[], losing_year=[], worst_year=[]) for v in ("brake", "normal")}
for _ in range(runs):
    path = np.concatenate([x[s:s + block] for s in rng.integers(0, len(x) - block, nb)])[: years * 12]
    for v in ("brake", "normal"):
        val, pk, mdd, mult, uw, best_uw, yrs = 1.0, 1.0, 0.0, 1.0, 0, 0, []
        y0 = 1.0
        for i, r in enumerate(path):
            if v == "brake":
                now = 1 - val / pk
                mult = 0.5 if (mult == 1.0 and now >= 0.25) else 1.0 if (mult < 1.0 and now <= 0.125) else mult
            val *= 1 + r * mult
            if val >= pk: pk, uw = val, 0
            else: uw += 1
            best_uw = max(best_uw, uw); mdd = max(mdd, 1 - val / pk)
            if i % 12 == 11: yrs.append(val / y0 - 1); y0 = val
        d = res[v]; d["dd"].append(mdd); d["uw"].append(best_uw / 12); d["cagr"].append(val ** (1 / years) - 1)
        d["losing_year"].append(min(yrs) < 0); d["worst_year"].append(min(yrs))
mc = {}
for v, d in res.items():
    dd, uw, cg, wy = map(np.array, (d["dd"], d["uw"], d["cagr"], d["worst_year"]))
    h = out[v]
    mc[v] = dict(dd_p50=float(np.median(dd)), dd_p90=float(np.quantile(dd, .9)), dd_p95=float(np.quantile(dd, .95)), dd_p99=float(np.quantile(dd, .99)),
                 p_dd_ge_hist=float((dd >= h["max_dd"]).mean()), p_dd30=float((dd > .3).mean()), p_dd40=float((dd > .4).mean()), p_dd50=float((dd > .5).mean()),
                 p_uw_ge_hist=float((uw >= h["longest_underwater_years"]).mean()), uw_p50=float(np.median(uw)), uw_p95=float(np.quantile(uw, .95)),
                 p_losing_year=float(np.mean(d["losing_year"])), worst_year_p5=float(np.quantile(wy, .05)), p_10y_loss=float((cg < 0).mean()),
                 cagr_p5=float(np.quantile(cg, .05)), cagr_p50=float(np.median(cg)))
    print("MC", v, json.dumps({k: round(x_, 3) for k, x_ in mc[v].items()}))
# losing streak odds: iid trades with the historical win rate and trade count per 10 years
w = out["brake"]["win"]; n10 = int(out["brake"]["trades"] / 15.08 * 10)
sims = rng.random((20000, n10)) > w
def longest(row):
    best = cur = 0
    for z in row:
        cur = cur + 1 if z else 0
        best = max(best, cur)
    return best
ls = np.array([longest(r) for r in sims[:5000]])
print("streak", dict(trades_per_10y=n10, p_ge_16=float((ls >= 16).mean()), p_ge_20=float((ls >= 20).mean()), median=float(np.median(ls)), p95=float(np.quantile(ls, .95))))
json.dump(dict(history=out, mc=mc), open("/home/user/EA-tread/research/g27k_dev/worst_case.json", "w"), indent=1, default=str)
