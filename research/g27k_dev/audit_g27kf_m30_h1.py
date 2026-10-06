#!/usr/bin/env python3
"""Audit of G27K-F + M30 sleeve + H1 sleeve (the report_g27kf_m30.py --h1
system): checks that the numbers in the report can be trusted and how they
could fail live.

  1. independent re-implementation: 40 random sleeve trades (20 M30, 20 H1)
     rebuilt from raw M1 with pandas only (bars, ATR, signal, entry, stop,
     2R target walked minute by minute, out at the next bar's open if
     neither is hit by the close of the 30th bar) against the engine
  2. clock: sleeve entries on Saturday for metals / FX (should be none),
     trades spanning data gaps of more than 3 days
  3. Fed rule: shocks whose next business day is a US federal holiday (H.15
     then comes a day later than the rule assumes)
  4. the account at 1% + brake, Standard and Cent: peak open risk, peak
     notional / balance (margin), same market and direction held by two or
     three books at once
  5. costs: modelled cost per trade by book and market, the extra cost per
     trade that wipes each book out, and the sleeves at the spreads seen on
     the Exness Cent screenshot of 4-5 Oct 2026 (market closed)
  6. concentration: share of each book's R from its best 1% of trades and
     from 2023-10..2026-09

Usage: python3 research/g27k_dev/audit_g27kf_m30_h1.py --root <snap>
"""
import argparse
import json
import pathlib
import sys

import numpy as np
import pandas as pd
from pandas.tseries.holiday import USFederalHolidayCalendar

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))
import h1_sleeve as HS
import h4d1_pattern_search as P
import m30_new_markets as NM
import news_shock as NS
import report_g27kf_m30 as RG
import suite as SU

START, END = "2011-09-01", "2026-10-01"
MK5 = ("XAUUSD", "XAGUSD", "BTCUSD", "ETHUSD", "USDJPY")
# Exness Cent screenshot, 4-5 Oct 2026 (weekend close): spread in bp of price, round trip = spread + 1 bp as in the model
SHOT_BP = {"XAUUSD": 0.26 / 4140.3 * 1e4, "XAGUSD": 0.03 / 60.37 * 1e4, "USDJPY": 0.026 / 157.83 * 1e4, "ETHUSD": 1.00 / 2704.0 * 1e4, "BTCUSD": 10.0 / 85360.0 * 1e4}


def sleeve(spec, h1):
    E, feats, cats = P.build(h1, spec["tf"])
    ex = spec["exit"]
    k = P.no_overlap(E, HS.mask(E, feats, cats, spec), ex)
    T = HS.trades(E, k, spec)
    T["ep"] = E[f"ep_{ex}"][T.i]
    T["rk"] = E[f"rk_{ex}"][T.i]
    T["stop_pct"] = T.rk / T.ep
    T["s"] = E["s"][T.i]
    return T, E


def independent(T, h1, tf, spec, n, rng):
    """Rebuild n random trades from raw M1 with pandas only."""
    sec = P.TF_SEC[tf]
    out = []
    for _, r in T.sample(n, random_state=rng).iterrows():
        b = h1[r.mkt]
        m1 = pd.DataFrame(dict(o=b["o"], h=b["h"], l=b["l"], c=b["c"]), index=pd.to_datetime(b["t"], unit="s"))
        sig_close = pd.Timestamp(int(r.t), unit="s")
        w = m1[(m1.index >= sig_close - pd.Timedelta(days=40)) & (m1.index < sig_close + pd.Timedelta(days=30))]
        bars = w.resample(f"{sec}s", label="left", closed="left").agg(dict(o="first", h="max", l="min", c="last")).dropna()
        pc = bars.c.shift(1)
        tr = pd.concat([bars.h - bars.l, (bars.h - pc).abs(), (bars.l - pc).abs()], axis=1).max(axis=1)
        a20 = tr.rolling(20).mean()
        sb = bars.index[bars.index < sig_close][-1]                         # the signal bar: last bar opening before its close
        e = bars.index[bars.index >= sig_close][0]                          # the entry bar
        ep = bars.o[e]
        risk = 2 * a20[sb]
        d = int(r.d)
        stop, tp = ep - d * risk, ep + d * 2 * risk
        px = tx = None
        pos = bars.index.get_loc(e)
        t_out = bars.index[pos + 30] if pos + 30 < len(bars) else None     # not out by the close of the 30th bar: exit at the next bar's open
        for t, row in w[w.index >= e].iterrows():
            if t_out is not None and t >= t_out:
                px, tx = bars.o[t_out], t_out
                break
            if (d > 0 and row.l <= stop) or (d < 0 and row.h >= stop):
                px, tx = (stop if d * (row.o - stop) > 0 or t == e else row.o), t
                break
            if (d > 0 and row.h >= tp) or (d < 0 and row.l <= tp):
                px, tx = (tp if d * (tp - row.o) > 0 or t == e else row.o), t
                break
        g = d * (px - ep) / risk if px is not None else np.nan
        out.append(dict(mkt=r.mkt, tf=tf, entry=str(e), engine_ep=float(r.ep), ind_ep=float(ep), engine_risk=float(r.rk), ind_risk=float(risk),
                        engine_exit=str(pd.Timestamp(int(r.tx), unit="s")), ind_exit=str(tx), engine_gross=float(r.gross), ind_gross=float(g),
                        match=bool(abs(ep - r.ep) < 1e-6 * ep and abs(risk - r.rk) < 1e-6 * ep and tx is not None and int(tx.timestamp()) == int(r.tx)
                                   and abs(g - r.gross) < 1e-6)))
    return out


def held(rows):
    """Peak open risk, peak notional / balance, and same market + direction stacking, from sized rows."""
    ev = []
    for r in rows:
        ev.append((r["t"], 1, r))
        ev.append((r["t_exit"], 0, r))
    ev.sort(key=lambda x: (x[0], x[1]))
    open_, peak_risk, peak_notional, stack, when = {}, 0.0, 0.0, {}, {}
    for t, kind, r in ev:
        key = id(r)
        if kind == 0:
            open_.pop(key, None)
            continue
        open_[key] = r
        rs = sum(x["risk_frac"] for x in open_.values())
        nt = sum(x["risk_frac"] / x["stop_pct"] for x in open_.values() if x.get("stop_pct"))
        if rs > peak_risk:
            peak_risk, when["risk"] = rs, t
        if nt > peak_notional:
            peak_notional, when["notional"] = nt, t
        base = RG.BASE(r["mkt"]) if "_" in r["mkt"] else r["mkt"]
        same = {RG.BOOK(x["mkt"]) if "_" in x["mkt"] else "G27K-F" for x in open_.values()
                if (RG.BASE(x["mkt"]) if "_" in x["mkt"] else x["mkt"]) == base and x["d"] == r["d"]}
        stack[len(same)] = stack.get(len(same), 0) + 1
    return dict(peak_open_risk=peak_risk, at_risk=str(pd.Timestamp(when.get("risk", 0), unit="s").date()), peak_notional_x=peak_notional,
                at_notional=str(pd.Timestamp(when.get("notional", 0), unit="s").date()), entries_by_books_holding_same_market_and_side=stack)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    ap.add_argument("--only-independent", action="store_true")
    a = ap.parse_args()
    out = {}
    h1 = NM.prepare(a.root, MK5)
    C = P._M["C"]
    C.SPECS.update(NS.FM.specs(C))
    hspec = HS.spec_of(HS.pick())
    M30, _ = sleeve(RG.M30_SPEC, h1)
    H1S, _ = sleeve(hspec, h1)
    print(f"  sleeves rebuilt: M30 {len(M30)} trades {M30.R.mean():+.3f}R, H1 {len(H1S)} trades {H1S.R.mean():+.3f}R", flush=True)
    # 1 independent re-implementation
    rng = 7
    ind = independent(M30, h1, "M30", RG.M30_SPEC, 20, rng) + independent(H1S, h1, "H1", hspec, 20, rng)
    out["independent"] = ind
    print(f"  1. independent rebuild: {sum(x['match'] for x in ind)}/{len(ind)} trades match the engine exactly", flush=True)
    for x in ind:
        if not x["match"]:
            print(f"     mismatch {x}", flush=True)
    if a.only_independent:
        return
    # 2 clock and gaps
    clk = {}
    for nm, T in (("M30", M30), ("H1", H1S)):
        ent = pd.to_datetime(T.t, unit="s")
        sat = int(((ent.dt.dayofweek == 5) & ~T.mkt.isin(["BTCUSD", "ETHUSD"])).sum())
        gaps = 0
        for m in MK5:
            tt = h1[m]["t"]
            big = np.flatnonzero(np.diff(tt) > 3 * 86400)
            gs, ge = tt[big], tt[big + 1]
            x = T[T.mkt == m]
            for s0, s1 in zip(gs, ge):
                gaps += int(((x.t <= s0) & (x.tx >= s1)).sum())
        clk[nm] = dict(saturday_entries_non_crypto=sat, trades_spanning_gap_over_3d=gaps,
                       entry_hour_share={int(h): float(v) for h, v in ent.dt.hour.value_counts(normalize=True).sort_index().items()})
        print(f"  2. {nm}: Saturday entries outside crypto {sat}, trades spanning a data gap > 3 days {gaps}", flush=True)
    out["clock"] = clk
    # 3 Fed rule holidays
    sh = NS.fed_shocks(a.root)
    hol = USFederalHolidayCalendar().holidays("2009-01-01", "2026-12-31")
    pub_days = pd.to_datetime(sh, unit="s").normalize()
    late = int(pub_days.isin(hol).sum())
    out["fed_holiday_lookahead"] = dict(shocks=len(sh), on_us_holiday=late, dates=[str(d.date()) for d in pub_days[pub_days.isin(hol)]])
    print(f"  3. Fed shocks {len(sh)}: {late} have their assumed publication day on a US federal holiday", flush=True)
    # 4 account holding, 5 costs, 6 concentration use the G27K-F rows
    G, K = P._M["G"], P._M["K"]
    sys.path.insert(0, str(pathlib.Path(a.root) / "research" / "grid768"))
    import report768 as RP
    Hh = {m: (NS.MMS.load(m, G) if m in NS.MMS.MARKETS else NS.L3.load(m, "2009-01-01", END)) for m in NS.RF.STD}
    NS.RSD.START = START
    G.START = NS.W.ts(START)
    raw = [{k: v for k, v in r.items() if k != "X"} for r in NS.RSD.g27k_rows(NS.RF.STD, Hh, RP, G, K, K.externals()) if NS.W.ts(START) <= r["t"] < NS.W.ts(END)]
    gf = NS.apply(raw, NS.fed_shocks(a.root), Hh, True)
    news = NS.W.news_times(a.root)

    def rows_of(T, book):
        return [dict(mkt=f"{m}_{book}", t=int(t), t_exit=int(tx), R=float(R), d=int(d), stop_pct=float(sp)) for m, t, tx, R, d, sp in
                zip(T.mkt, T.t, T.tx, T.R, T.d, T.stop_pct)]
    acc = {}
    for acct, ms in (("Cent", NS.RF.CENT), ("Standard", NS.RF.STD)):
        rr = [dict(r) for r in gf if r["mkt"] in ms] + rows_of(M30[M30.mkt.isin(ms)], "M30") + rows_of(H1S[H1S.mkt.isin(ms)], "H1")
        rr.sort(key=lambda r: (r["t"], r["mkt"]))
        scale = {m: 0.5 for m in {r["mkt"] for r in rr} if "_" in m}
        RG.START = START
        sized = RG.sized(rr, "brake", news, scale)
        acc[acct] = held(sized)
        x = acc[acct]
        print(f"  4. {acct} 1% + brake: peak open risk {x['peak_open_risk']:.1%} ({x['at_risk']}), peak notional {x['peak_notional_x']:.0f}x balance "
              f"({x['at_notional']}), entries by number of books on the same market and side {x['entries_by_books_holding_same_market_and_side']}", flush=True)
    out["account"] = acc
    gfd = pd.DataFrame(dict(mkt=[r["mkt"] for r in gf], t=[r["t"] for r in gf], R=[r["R"] for r in gf], stop_pct=[r.get("stop_pct", np.nan) for r in gf]))
    cost = {}
    for nm, T in (("G27K-F", gfd), ("M30", M30), ("H1", H1S)):
        per = {}
        for m in sorted(T.mkt.unique()):
            x = T[T.mkt == m]
            spec = C.SPECS[m]
            mod = spec["cost_rt_bp"] / 1e4 / x.stop_pct
            shot = (SHOT_BP.get(m, np.nan) + 1.0) / 1e4 / x.stop_pct if m in SHOT_BP else mod
            per[m] = dict(n=int(len(x)), R=float(x.R.mean()), cost_R=float(mod.mean()), stop_pct=float(x.stop_pct.median()),
                          R_at_screenshot_spread=float((x.R + mod - np.maximum(mod, shot)).mean()))
        allR = T.R.to_numpy()
        top = np.sort(allR)[::-1][: max(1, len(allR) // 100)]
        recent = T[T.t >= NS.W.ts("2023-10-01")].R.sum() / T.R.sum()
        cost[nm] = dict(per_market=per, breakeven_extra_R=float(allR.mean()), top1pct_share=float(top.sum() / allR.sum()), last3y_share=float(recent))
        print(f"  5/6. {nm}: mean {allR.mean():+.3f}R (= extra cost per trade that wipes it out), best 1% of trades = {top.sum() / allR.sum():.0%} of all R, "
              f"2023-10..2026-09 = {recent:.0%} of all R", flush=True)
        for m, v in per.items():
            print(f"        {m}: n {v['n']} R {v['R']:+.3f} model cost {v['cost_R']:.3f}R, median stop {v['stop_pct']:.2%} of price, "
                  f"R at screenshot spreads {v['R_at_screenshot_spread']:+.3f}", flush=True)
    out["cost"] = cost
    (HERE / "audit_g27kf_m30_h1.json").write_text(json.dumps(out, indent=1, default=float))


if __name__ == "__main__":
    main()
