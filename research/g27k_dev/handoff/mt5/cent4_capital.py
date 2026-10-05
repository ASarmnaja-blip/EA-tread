"""Minimum capital for G27K-F + M30 + H1 on the Cent account without USDJPY (gold, silver, BTC, ETH), no brake.

Risk per trade as a share of balance at entry: G27K-F 1 %, the M30 and H1 sleeves 0.5 % each, never reduced (no brake).
The broker sizes in lots: nearest step, never below the minimum lot (operator's choices "ปัดใกล้เคียง" and "ก"). A small account
therefore takes more risk than the rule on any trade whose correct size is under the minimum lot. This script finds the balance
at which that stops mattering.

1. What the minimum lot risks today, per book and market: stop width from the last 12 months of trades (median and 90th
   percentile, as % of price) at today's price, on the Cent contract. Balance needed = minimum-lot risk / target risk.
2. Replay of the last three years of trades at today's price level (each trade keeps its own stop as % of price), real Cent
   lots, from several starting balances, against the same trades sized exactly. Counts trades forced over the target risk,
   tracks margin, and compares growth and drawdown with exact sizing.
3. The 15-year account at $100,000 under each cost version, with and without the brake, as a check against the research.

Usage: python cent4_capital.py
"""
from __future__ import annotations

import heapq
import json
import math
from datetime import datetime, timezone

import numpy as np
import pandas as pd

import cent4_costs as CC

SPEC = {   # Cent contracts measured 2026-10-05 (cent_symbols.csv / cent_margin.csv): units per lot, minimum, step, leverage granted
    "XAUUSD": dict(sym="XAUUSDc", contract=1.0, vmin=0.01, vstep=0.01, leverage=2000),
    "XAGUSD": dict(sym="XAGUSDc", contract=50.0, vmin=0.01, vstep=0.01, leverage=2000),
    "BTCUSD": dict(sym="BTCUSDc", contract=0.01, vmin=0.01, vstep=0.01, leverage=400),
    "ETHUSD": dict(sym="ETHUSDc", contract=0.01, vmin=0.10, vstep=0.01, leverage=400),
}
RISK = {"F": 0.01, "M30": 0.005, "H1": 0.005}
START, END = "2011-09-01", "2026-10-01"
RECENT = "2025-10-01"          # stop widths "today": the last 12 months of entries
REPLAY = "2023-10-01"          # replay window: the last three years
BALANCES_USD = [100, 130, 150, 200, 300, 500, 1000]
STATIC_USD = [50, 75, 100, 110, 120, 130, 140, 150, 175, 200, 250, 300, 400, 500, 750, 1000]


def live_prices():
    """Mid prices now from the terminal (the demo's XAUUSD etc. quote the same as the Cent symbols)."""
    import MetaTrader5 as mt5
    mt5.initialize(path=r"C:\Program Files\MetaTrader 5\terminal64.exe") or mt5.initialize()
    out, when = {}, None
    for m in SPEC:
        mt5.symbol_select(m, True)
        t = mt5.symbol_info_tick(m)
        out[m] = (t.bid + t.ask) / 2
        when = max(when or 0, t.time)
    mt5.shutdown()
    return out, datetime.fromtimestamp(when, tz=timezone.utc)


def lots(want_usc, risk_per_lot_usc, s):
    lot = math.floor(want_usc / risk_per_lot_usc / s["vstep"] + 0.5) * s["vstep"]
    return max(round(lot, 2), s["vmin"])


def account(D, rcol, start=100_000.0, t0=START, t1=END, brake=False, sized=None, px=None):
    """Compounding account over trades entered in [t0, t1). sized=None: exact fractions of balance (the research's way);
    sized='cent': real Cent lots at today's price level. Returns stats, per-trade sizing records ('cent' only) and the
    balance after every close."""
    s0, s1 = CC.ts(pd.Series([t0])).iat[0], CC.ts(pd.Series([t1])).iat[0]
    X = D[(D.t >= s0) & (D.t < s1)]
    bal = peak = start
    heap, recs, pts = [], [], [(s0, start)]
    braked = False
    open_m = 0.0; peak_m = 0.0; min_lvl = np.inf; npos = 0; max_pos = 0
    for r in X.itertuples():
        while heap and heap[0][0] <= r.t:
            tx, _, pnl, m = heapq.heappop(heap)
            bal += pnl; open_m -= m; npos -= 1
            peak = max(peak, bal); pts.append((tx, bal))
            now = 1 - bal / peak
            braked = (now >= 0.25) or (braked and now > 0.125)
        if bal <= 0:
            continue
        target = RISK[r.book] * (0.5 if (brake and braked) else 1.0)
        R = getattr(r, rcol)
        if sized == "cent":
            s = SPEC[r.market]
            rpl = r.stop_pct * px[r.market] * s["contract"]                  # USD lost per lot at the stop (Cent: 1 lot XAUUSDc = 1 oz, P&L in USC = USD x 100)
            lot = lots(target * bal, rpl, s)
            risk_money = lot * rpl
            margin = lot * s["contract"] * px[r.market] / s["leverage"]
            recs.append(dict(t=r.t, book=r.book, market=r.market, bal=bal, target=target, actual=risk_money / bal, lot=lot,
                             at_min=lot <= s["vmin"] + 1e-9))
        else:
            risk_money, margin = target * bal, 0.0
        open_m += margin; npos += 1; max_pos = max(max_pos, npos)
        if open_m > 0:
            peak_m = max(peak_m, open_m / bal); min_lvl = min(min_lvl, bal / open_m)
        heapq.heappush(heap, (r.tx, r.Index, risk_money * R, margin))
    while heap:
        tx, _, pnl, m = heapq.heappop(heap)
        bal += pnl; peak = max(peak, bal); pts.append((tx, bal))
    eq = pd.Series([b for _, b in pts], index=pd.to_datetime([t for t, _ in pts], unit="s")).sort_index()
    dd = float((1 - eq / eq.cummax()).max())
    yrs = (s1 - s0) / (365.25 * 86400)
    cagr = (bal / start) ** (1 / yrs) - 1 if bal > 0 else -1.0
    out = dict(final=bal, cagr=cagr, dd=dd, mar=cagr / dd if dd > 0 else np.nan, n=len(X), peak_margin=peak_m,
               min_margin_level=min_lvl, max_positions=max_pos)
    return out, pd.DataFrame(recs), eq


def main():
    T = CC.load()
    D = CC.versions(T)
    px, when = live_prices()
    res = dict(prices=px, prices_at=str(when), versions=CC.VERSIONS)
    print(f"prices now ({when:%Y-%m-%d %H:%M} UTC): " + "  ".join(f"{m} {p:,.2f}" for m, p in px.items()))

    # ---------- 0. R per trade by book and market under each version
    print("\n== R per trade, 4 markets, 2011-09..2026-09")
    rp = {}
    for (b, m), g in D.groupby(["book", "market"]):
        rp[f"{m}_{b}"] = dict(n=len(g), **{v: float(g[f"R_{v}"].mean()) for v in CC.VERSIONS},
                              spread={v: float(g[f"R_spread_{v}"].mean()) for v in CC.VERSIONS},
                              swap={v: float(g[f"R_swap_{v}"].mean()) for v in CC.VERSIONS}, gross=float(g.R_gross.mean()))
        print(f"  {b:4s} {m:7s} n {len(g):4d}  gross {g.R_gross.mean():+.3f}  " + "  ".join(f"{v} {g[f'R_{v}'].mean():+.3f}" for v in CC.VERSIONS))
    for b, g in D.groupby("book"):
        print(f"  {b:4s} all     n {len(g):4d}  gross {g.R_gross.mean():+.3f}  " + "  ".join(f"{v} {g[f'R_{v}'].mean():+.3f}" for v in CC.VERSIONS))
    res["r_per_trade"] = rp

    # ---------- 1. what the minimum lot risks today
    print(f"\n== minimum lot at today's prices, stop width from entries {RECENT}..2026-09 (median / 90th pct), target risk F 1 %, sleeves 0.5 %")
    rec = D[D.t >= CC.ts(pd.Series([RECENT])).iat[0]]
    need = []
    for b in ("F", "M30", "H1"):
        for m, s in SPEC.items():
            g = rec[(rec.book == b) & (rec.market == m)]
            if not len(g):
                continue
            row = dict(book=b, market=m, n=len(g), min_lot=s["vmin"])
            for q, lab in ((0.5, "med"), (0.9, "p90")):
                sp = float(g.stop_pct.quantile(q))
                risk_usd = s["vmin"] * s["contract"] * sp * px[m]            # USD lost at the stop with the minimum lot
                row[f"stop_{lab}"] = sp
                row[f"minlot_risk_{lab}"] = risk_usd
                row[f"need_{lab}"] = risk_usd / RISK[b]
            row["stop_max"] = float(g.stop_pct.max())
            row["need_max"] = s["vmin"] * s["contract"] * row["stop_max"] * px[m] / RISK[b]
            need.append(row)
            print(f"  {b:4s} {m:7s} n {len(g):3d}  stop med {row['stop_med']:.2%} p90 {row['stop_p90']:.2%}  min lot {s['vmin']:.2f} "
                  f"risks ${row['minlot_risk_med']:.2f} / ${row['minlot_risk_p90']:.2f}  -> balance needed ${row['need_med']:,.0f} / ${row['need_p90']:,.0f}"
                  f"  (widest stop ${row['need_max']:,.0f})")
    N = pd.DataFrame(need)
    bm, bp = N.loc[N.need_med.idxmax()], N.loc[N.need_p90.idxmax()]
    print(f"  binding: median stop {bm.book} {bm.market} ${bm.need_med:,.0f} | 90th pct {bp.book} {bp.market} ${bp.need_p90:,.0f}")
    res["need"] = need

    # ---------- 2a. a fixed balance against the last 12 months of trades (no growth: the account as it would stand on day one)
    print(f"\n== fixed balance vs every trade entered {RECENT}..2026-09 at today's prices: actual risk / target after rounding to Cent lots")
    s_rec = rec.copy()
    s_rec["rpl"] = [r.stop_pct * px[r.market] * SPEC[r.market]["contract"] for r in s_rec.itertuples()]
    s_rec["target"] = s_rec.book.map(RISK)
    static = []
    for usd in STATIC_USD:
        lot = np.array([lots(tg * usd, rpl, SPEC[m]) for tg, rpl, m in zip(s_rec.target, s_rec.rpl, s_rec.market)])
        ratio = lot * s_rec.rpl.to_numpy() / (s_rec.target.to_numpy() * usd)
        k = int(np.argmax(ratio))
        by = {f"{b} {m}": float(r_.max()) for (b, m), r_ in pd.Series(ratio, index=s_rec.index).groupby([s_rec.book, s_rec.market])}
        static.append(dict(start=usd, n=len(ratio), over1=float((ratio > 1.0 + 1e-9).mean()), over125=float((ratio > 1.25).mean()),
                           over15=float((ratio > 1.5).mean()), over2=float((ratio > 2.0).mean()), max_ratio=float(ratio.max()),
                           worst=f"{s_rec.book.iat[k]} {s_rec.market.iat[k]}", by=by))
        print(f"  ${usd:>5,}: over target {static[-1]['over1']:5.1%} | >1.25x {static[-1]['over125']:5.1%} | >1.5x {static[-1]['over15']:5.1%}"
              f" | >2x {static[-1]['over2']:5.1%} | largest {ratio.max():4.2f}x ({static[-1]['worst']})")
    res["static"] = static

    # ---------- 2b. replays at today's price level: the last 12 months (today's volatility) and the last three years
    rows = []
    for t0, lab in ((RECENT, "12m"), (REPLAY, "3y")):
        print(f"\n== replay {t0}..2026-09 at today's price level, real-cost version, no brake: real Cent lots vs exact sizing")
        for usd in BALANCES_USD:
            exact, _, _ = account(D, "R_real", start=usd, t0=t0)
            cent, L, _ = account(D, "R_real", start=usd, t0=t0, sized="cent", px=px)
            over = L.actual > 1.5 * L.target
            first = L[L.t < L.t.min() + 91 * 86400]
            row = dict(window=lab, start=usd, n=len(L), over15=int(over.sum()), over15_share=float(over.mean()),
                       over15_first_q=float((first.actual > 1.5 * first.target).mean()),
                       at_min=float(L.at_min.mean()), max_actual=float(L.actual.max()), mean_ratio=float((L.actual / L.target).mean()),
                       worst_market=(L.loc[L.actual.idxmax(), "book"] + " " + L.loc[L.actual.idxmax(), "market"]),
                       final=cent["final"], cagr=cent["cagr"], dd=cent["dd"], exact_final=exact["final"], exact_cagr=exact["cagr"], exact_dd=exact["dd"],
                       peak_margin=cent["peak_margin"], min_margin_level=cent["min_margin_level"], max_positions=cent["max_positions"])
            rows.append(row)
            print(f"  start ${usd:>5,}: {len(L)} trades | over 1.5x target {row['over15']:4d} ({row['over15_share']:5.1%}; first 3 months {row['over15_first_q']:5.1%})"
                  f" | at min lot {row['at_min']:5.1%} | largest actual risk {row['max_actual']:5.2%} ({row['worst_market']})"
                  f" | return {cent['final'] / usd - 1:+.0%} DD {cent['dd']:.1%} vs exact {exact['final'] / usd - 1:+.0%} DD {exact['dd']:.1%}"
                  f" | peak margin {cent['peak_margin']:.2%} of balance, max {cent['max_positions']} open")
    res["replay"] = rows

    # ---------- 3. the 15-year account, $100,000, each version, with and without the brake
    print("\n== 15 years 2011-09..2026-09, $100,000, exact sizing")
    acc = {}
    for v in CC.VERSIONS:
        for brake in (False, True):
            a, _, _ = account(D, f"R_{v}", brake=brake)
            h1, _, _ = account(D, f"R_{v}", brake=brake, t1="2019-01-01")
            h2, _, _ = account(D, f"R_{v}", brake=brake, t0="2019-01-01")
            acc[f"{v}{'_brake' if brake else ''}"] = dict(a, mar_2011_18=h1["mar"], mar_2019_26=h2["mar"])
            print(f"  {v:6s} {'brake' if brake else 'no brake':8s} CAGR {a['cagr']:+.1%} DD {a['dd']:.1%} MAR {a['mar']:.2f} | "
                  f"MAR 2011-18 {h1['mar']:+.2f} 2019-26 {h2['mar']:+.2f} | {a['n']} trades | final ${a['final']:,.0f}")
    res["accounts"] = acc
    (CC.HERE / "cent4_capital.json").write_text(json.dumps(res, indent=1, default=float), encoding="utf-8")
    print(f"\nwritten {CC.HERE / 'cent4_capital.json'}")


if __name__ == "__main__":
    main()
