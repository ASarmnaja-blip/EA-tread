#!/usr/bin/env python3
"""Every system we have built, in every version, over every window.

Systems (trade streams, all on one data set: metals hybrid H1, the 13 other
markets Dukascopy H1 bid, BTC Binance from 2017-08):
  A      G27K #1 on gold
  B      G27K #1 on gold, silver, BTC
  B16    G27K #1 on all 16 markets
  PM     each market's own best free-search pattern (gold, silver, BTC)
  POOL3  the best single pattern searched on gold, silver, BTC together
  ALL16  the best single pattern searched on all 16 markets, traded on all
         16; ALL16>3 the same pattern on gold, silver and BTC only
  W2     the forward-only walk-forward controller, round 2 (its own runs;
         only its native 10 and 5 year windows exist)
Versions (sizing on top of the same trades):
  normal  1% of balance per trade
  half    0.5%
  brake   1%, halved while balance DD >= 25% until it is back within 12.5%
  monitor 1% x the round-2 monitor layer: DD brake (15% -> x0.5, 25% -> x0.25,
          back to x1 under 7.5%), x0.5 after 8 trades in that market averaging
          below -0.3R, x0.5 when the ATR percentile at the signal > 0.95,
          x0.5 within -1h..+2h of a HIGH USD event, and no trade that would
          take open risk above 6%
  macro   1% x (1 + weekly macro score), normalised to a mean of 1 (gold,
          silver, BTC only; registered test failed, kept for completeness)
plus a monthly top-up ($100 + $100 a month) for normal, brake and monitor,
and a 10-year block-bootstrap Monte Carlo of each 17-year result.

Searched patterns (PM, POOL3, ALL16) were chosen on data before 2018 (BTC
before 2021 or 2024); their numbers before that are in-sample by construction.

Usage: python3 research/g27k_dev/suite.py --root <data-snapshot checkout>
"""
import argparse
import heapq
import json
import math
import pathlib
import pickle
import sys
import time

import numpy as np
import pandas as pd

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))
import dca as DC
import h4d1_pattern_search as P
import macro_portfolio as MP
import multi_market_search as MMS
import per_market_search as PMS
import walkforward_controller as W

END = "2026-10-01"
WINDOWS = {"17y": "2009-09-01", "10y": "2016-10-01", "5y": "2021-10-01", "3y": "2023-10-01"}
VERSIONS = ("normal", "half", "brake", "monitor", "macro")
TARGET = ("XAUUSD", "XAGUSD", "BTCUSD")
DAY = 86400


# ------------------------------------------------------------------ trade streams
def g27k_trades(mkts, H1, RP, G, K, ext):
    """G27K #1 with the G27K report's own fills (report768.sim_paths)."""
    K.START = W.ts(WINDOWS["17y"])
    out = []
    for m in mkts:
        Mk = K.prepare(m, H1[m], ext)
        X = G.features(G.frames(H1[m]), m, "H4")
        X["sec"] = 14400
        d = K.directions(Mk, "C8", "D3", "E1", "J1")
        idx = np.flatnonzero(d)
        vp = pd.Series(X["a14"]).rolling(250, min_periods=100).rank(pct=True).to_numpy()
        for tr in RP.sim_paths(X, m, idx, d[idx], "I1"):
            out.append(dict(mkt=m, t=int(tr["t"]), tx=int(tr["t_exit"]), R=float(tr["R"]), d=int(tr["d"]),
                            vp=float(vp[max(tr["e"] - 1, 0)]), sc=int(tr["t"])))
    return pd.DataFrame(out)


def pattern_trades(c, H1, mkts):
    """Full-history trades of one searched pattern, rebuilt from its definition
    on the given market set (cross-market features depend on that set)."""
    if "trades_all" in c:
        return c["trades_all"]
    E, feats, cats = P.build({m: H1[m] for m in mkts}, c["tf"])
    conds = [W.parse(n) for n in c["names"]]
    m = W.pmask(feats, cats, conds) & P.scope_mask(E, c["scope"]) & np.isfinite(E[f"R_{c['exit']}"])
    T = PMS.trades_of(E, m[:, None], dict(c, conds=[0]), feats, full=True)
    return T


def picks():
    """Top pattern per scope across all stages that exist."""
    out = {}
    for f, scopes in (("pms_hourly.pkl", ("XAUUSD", "XAGUSD", "BTCUSD", "pooled")),
                      ("pms_minute.pkl", ("XAUUSD", "XAGUSD", "BTCUSD", "pooled")), ("mms.pkl", ("pooled", "POOL3"))):
        p = PMS.CACHE / f
        if not p.exists():
            continue
        best = pickle.loads(p.read_bytes())["best"]
        for s in scopes:
            key = ("ALL16" if s == "pooled" else "POOL3m") if f == "mms.pkl" else ("POOL3" if s == "pooled" else s)
            c = best[s][0]
            if key not in out or c["t_disc"] > out[key]["t_disc"]:
                out[key] = c
    return out


# ------------------------------------------------------------------ sizing versions
def simulate(T, version, start, end=END, news=None, macro=None, deposits=False):
    """One account over [start, end): returns stats, monthly equity and per-trade risk."""
    s0, s1 = W.ts(start), W.ts(end)
    T = T[(T.t >= s0) & (T.t < s1)].sort_values(["t", "mkt"]).reset_index(drop=True)
    mult = np.ones(len(T))
    if version == "macro":
        mult = 1 + np.nan_to_num(np.array([macro(m, t) for m, t in zip(T.mkt, T.t)]))
        mult = mult / mult.mean() if len(mult) and mult.mean() > 0 else mult
    months = [W.ts(d) for d in pd.date_range(start, end, freq="MS", inclusive="left")] if deposits else []
    ev = sorted([(m, 0, -1) for m in months] + [(int(t), 1, i) for i, t in enumerate(T.t)])
    bal = 0.0 if deposits else 1.0
    nav, pk_nav, dd_nav, peak, dd = 1.0, 1.0, 0.0, bal, 0.0
    heap, open_risk, recent = [], {}, {}
    flows, ftimes, risk_of = [], [], np.zeros(len(T))
    braked, mb = False, 1.0
    pts = []

    def close(t):
        nonlocal bal, nav, pk_nav, dd_nav, peak, dd, braked, mb
        while heap and heap[0][0] <= t:
            tx, i, pnl = heapq.heappop(heap)
            nav *= (bal + pnl) / bal if bal > 0 else 1.0
            bal += pnl
            open_risk.pop(i, None)
            peak = max(peak, bal)
            pk_nav = max(pk_nav, nav)
            dd = max(dd, 1 - bal / peak) if peak > 0 else dd
            dd_nav = max(dd_nav, 1 - nav / pk_nav)
            recent.setdefault(T.mkt.iat[i], []).append(T.R.iat[i])
            now = 1 - nav / pk_nav
            braked = (now >= 0.25) or (braked and now > 0.125)
            mb = 0.25 if now >= 0.25 else 0.5 if now >= 0.15 else (1.0 if now < 0.075 else mb)
            pts.append((tx, bal))

    for t, kind, i in ev:
        close(t)
        if kind == 0:
            amt = DC.INITIAL + DC.MONTHLY if not flows else DC.MONTHLY
            bal += amt
            flows.append(amt)
            ftimes.append(t)
            peak = max(peak, bal)
            continue
        if bal <= 0:
            continue
        r = {"normal": 0.01, "half": 0.005, "brake": 0.005 if braked else 0.01, "macro": 0.01 * mult[i]}.get(version)
        if version == "monitor":
            r = 0.01 * mb
            rc = recent.get(T.mkt.iat[i], [])
            if len(rc) >= 8 and np.mean(rc[-8:]) < -0.3:
                r *= 0.5
            if T.vp.iat[i] > 0.95:
                r *= 0.5
            sc = int(T.sc.iat[i])
            j = np.searchsorted(news, sc - 3600)
            if j < len(news) and news[j] <= sc + 7200:
                r *= 0.5
            if sum(open_risk.values()) + r > 0.06 + 1e-12:
                continue
        risk_of[i] = r
        open_risk[i] = r
        heapq.heappush(heap, (int(T.tx.iat[i]), i, r * bal * T.R.iat[i]))
    close(2 ** 62)
    taken = risk_of > 0
    pnl_R = (T.R.to_numpy() * risk_of)[taken]
    yrs = (s1 - s0) / (365.25 * DAY)
    eq = pd.Series([b for _, b in pts], index=pd.to_datetime([x for x, _ in pts], unit="s")) if pts else pd.Series(dtype=float)
    st = dict(n=int(taken.sum()), final=float(bal), pf=float(pnl_R[pnl_R > 0].sum() / -pnl_R[pnl_R < 0].sum())
              if (pnl_R < 0).any() else None, avg_risk=float(risk_of[taken].mean()) if taken.any() else 0.0)
    if deposits:
        st.update(deposited=float(sum(flows)), irr=float(DC.irr(flows, ftimes, bal, s1)) if flows else None, dd=float(dd_nav))
    else:
        cagr = bal ** (1 / yrs) - 1 if bal > 0 else -1.0
        st.update(cagr=float(cagr), dd=float(dd), mar=float(cagr / dd) if dd > 0 else None)
        if len(eq):
            y = eq.resample("YE").last()
            yr = y / y.shift(1).fillna(1.0) - 1
            st.update(worst_year=float(yr.min()), worst_year_at=int(yr.idxmin().year), losing_years=int((yr < 0).sum()),
                      years=int(len(yr)))
    return st, eq, risk_of


def monte_carlo(eq, runs=4000, years=10, block=6, seed=7):
    me = eq.resample("ME").last().ffill()
    x = me.pct_change().dropna().to_numpy()
    if len(x) < 24:
        return None
    rng = np.random.default_rng(seed)
    nb = math.ceil(years * 12 / block)
    dds, fin = np.empty(runs), np.empty(runs)
    for k in range(runs):
        path = np.concatenate([x[s:s + block] for s in rng.integers(0, len(x) - block, nb)])[: years * 12]
        v = np.cumprod(1 + path)
        dds[k] = np.max(1 - v / np.maximum.accumulate(np.r_[1.0, v])[1:])
        fin[k] = v[-1]
    return dict(p_dd50=float((dds > 0.5).mean()), p_dd30=float((dds > 0.3).mean()), dd_median=float(np.median(dds)),
                cagr_median=float(np.median(fin) ** (1 / years) - 1))


# ------------------------------------------------------------------ main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    ap.add_argument("--only", default="", help="comma list of systems, for a partial run")
    ap.add_argument("--markets", default="", help="comma list overriding the 16 markets, for a quick check")
    ap.add_argument("--out", default="suite.json")
    a = ap.parse_args()
    if a.markets:
        MMS.MARKETS = tuple(a.markets.split(","))
    t0 = time.time()
    P.setup(a.root)
    G, K = P._M["G"], P._M["K"]
    sys.path.insert(0, str(pathlib.Path(a.root) / "research" / "grid768"))
    import report768 as RP
    W.SEC.update(P.TF_SEC)
    H1 = {m: MMS.load(m, G) for m in MMS.MARKETS}
    P._M["h1"] = H1
    ext = K.externals()
    news = W.news_times(a.root)
    weeks = pd.date_range(MP.FIRST, MP.LAST, freq="W-MON")
    S = MP.weekly_scores(MP.votes(a.root), weeks)
    wk = weeks.values.astype("datetime64[s]").astype(np.int64)

    def macro(m, t):
        if m not in S:
            return 0.0
        j = np.searchsorted(wk, t, side="right") - 1
        return float(S[m].iat[j]) if j >= 0 else 0.0

    streams, notes = {}, {}
    want = set(a.only.split(",")) if a.only else None
    if not want or want & {"A", "B", "B16"}:
        g16 = g27k_trades(MMS.MARKETS, H1, RP, G, K, ext)
        streams["A"] = g16[g16.mkt == "XAUUSD"]
        streams["B"] = g16[g16.mkt.isin(TARGET)]
        streams["B16"] = g16
        print(f"  G27K streams {time.time() - t0:.0f}s", flush=True)
    pk = picks()
    if (not want or "PM" in want) and all(m in pk for m in TARGET):
        streams["PM"] = pd.concat([pattern_trades(pk[m], H1, TARGET) for m in TARGET], ignore_index=True)
        notes["PM"] = {m: dict(tf=pk[m]["tf"], exit=pk[m]["exit"], names=pk[m]["names"]) for m in TARGET}
    if (not want or "POOL3" in want) and "POOL3" in pk:
        streams["POOL3"] = pattern_trades(pk["POOL3"], H1, TARGET)
        notes["POOL3"] = dict(tf=pk["POOL3"]["tf"], exit=pk["POOL3"]["exit"], names=pk["POOL3"]["names"])
    if (not want or "ALL16" in want) and "ALL16" in pk:
        T = pattern_trades(pk["ALL16"], H1, MMS.MARKETS)
        streams["ALL16"] = T
        streams["ALL16>3"] = T[T.mkt.isin(TARGET)]
        notes["ALL16"] = dict(tf=pk["ALL16"]["tf"], exit=pk["ALL16"]["exit"], names=pk["ALL16"]["names"])
    print(f"  streams: " + ", ".join(f"{k} {len(v)}" for k, v in streams.items()) + f"  {time.time() - t0:.0f}s", flush=True)

    res = dict(systems={}, dca={}, mc={}, notes=notes)
    for name, T in streams.items():
        res["systems"][name] = {}
        for v in VERSIONS:
            if v == "macro" and not set(T.mkt.unique()) <= set(TARGET):
                continue
            res["systems"][name][v] = {}
            for w, s in WINDOWS.items():
                st, eq, _ = simulate(T, v, s, news=news, macro=macro)
                res["systems"][name][v][w] = st
                if w == "17y" and v in ("normal", "brake", "monitor", "half"):
                    res["mc"].setdefault(name, {})[v] = monte_carlo(eq)
        res["dca"][name] = {v: {w: simulate(T, v, s, news=news, deposits=True)[0] for w, s in WINDOWS.items()}
                            for v in ("normal", "brake", "monitor")}
        r = res["systems"][name]["normal"]["17y"]
        print(f"  {name:8s} n {r['n']:5d} 17y CAGR {r['cagr']:+.1%} DD {r['dd']:.1%}  {time.time() - t0:.0f}s", flush=True)
    wf = json.loads((HERE.parent / "walkforward_10y.json").read_text())
    w2 = json.loads((HERE.parent / "walkforward_round2.json").read_text())
    res["W2"] = {"10y": {k: wf["controller"]["metrics"].get(k) for k in ("cagr", "equity_dd", "balance_dd", "pf", "trades", "final")}}
    m5 = w2["main"]["round2"]["metrics"]
    res["W2"]["5y"] = {k: m5.get(k) for k in ("cagr", "equity_dd", "balance_dd", "pf", "trades", "final")}
    res["W2"]["note"] = ("walk-forward round 2 (W2) and its own runs: gold, silver and BTC with MT5 BTC from 2021, "
                         "0.5% base risk with its built-in monitor; only its native 10 and 5 year windows exist")
    out = HERE / a.out
    out.write_text(json.dumps(res, indent=1, default=float))
    print(f"  saved {out.name}  {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
