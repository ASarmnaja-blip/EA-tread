"""Task 4 of MT5_TASKS.md: the M30 sleeve EA against the research trades.

Pairs the EA's tester log with trades_M30.csv.gz on market and signal bar, and reports how often the entry bar and the exit bar
agree, gross R either side, and - the point of the exercise - the cost the tester actually charged against the R_spread + R_swap
the research modelled. The research priced gold and silver off Dukascopy, BTC and ETH off Binance and USDJPY off histdata, so
prices differ a little by construction; the entry and exit BARS are what must line up.

Usage: python compare_m30.py [--from 2023-01-01] [--to 2026-09-30]
"""
from __future__ import annotations

import argparse
import pathlib
import re

import numpy as np
import pandas as pd

HERE = pathlib.Path(__file__).resolve().parent
HANDOFF = HERE.parent
COMMON = pathlib.Path.home() / "AppData" / "Roaming" / "MetaQuotes" / "Terminal" / "Common" / "Files"
M30 = pd.Timedelta(minutes=30)


def load_ea(path):
    # the note is free text and last; the first tester log let a comma through, so split on the first N-1 commas only
    raw = pathlib.Path(path).read_text(encoding="utf-8", errors="replace").splitlines()
    head = raw[0].split(",")
    rows = [r.split(",", len(head) - 1) for r in raw[1:] if r.strip()]
    L = pd.DataFrame([r for r in rows if len(r) == len(head)], columns=head)
    for c in L.columns:
        if c not in ("time", "event", "symbol", "dir", "signal_bar", "note"):
            L[c] = pd.to_numeric(L[c], errors="coerce")
    L["time"] = pd.to_datetime(L["time"], format="%Y.%m.%d %H:%M:%S")
    trades, cur = [], {}
    for r in L[L.symbol.notna()].sort_values("time").itertuples():
        m = r.symbol
        if r.event == "ENTRY":
            cur[m] = dict(market=m, direction=1 if r.dir == "long" else -1,
                          signal_bar=pd.to_datetime(r.signal_bar, format="%Y.%m.%d %H:%M"),
                          entry_time=r.time, fill=float(r.fill), stop=float(r.stop), tp=float(r.tp),
                          atr20=float(r.atr20), lots=float(r.lots), risk_pct=float(r.risk_pct),
                          slippage=float(r.slippage) if pd.notna(r.slippage) else np.nan,
                          margin=float(r.margin) if pd.notna(r.margin) else np.nan,
                          brk55=float(r.brk55), atr_ratio=float(r.atr_ratio))
            mo = re.search(r"risk ([0-9.]+) of target", str(r.note))
            cur[m]["risk_money"] = float(mo.group(1)) if mo else np.nan
        elif str(r.event).startswith("EXIT_") and r.event != "EXIT_FAIL" and m in cur:
            t = cur.pop(m)
            t["exit_time"] = r.time
            t["exit_bar"] = r.time.floor("30min")
            t["exit_reason"] = {"EXIT_STOP": "stop", "EXIT_TP": "tp", "EXIT_TIME": "time"}.get(r.event, r.event.lower())
            t["exit_price"] = float(r.exit_price)
            t["r_gross_ea"] = float(r.r_gross)
            t["money"] = float(r.money)
            t["bars_held"] = float(r.bars_held)
            t["net_R_ea"] = t["money"] / t["risk_money"] if t["risk_money"] else np.nan
            trades.append(t)
    skips = L[L.event.astype(str).str.startswith("SKIP_")].groupby(["symbol", "event"]).size()
    return pd.DataFrame(trades), skips, L


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--log", default=str(COMMON / "tester_g27k_m30_log.csv"))
    ap.add_argument("--from", dest="t0", default="2023-01-01")
    ap.add_argument("--to", dest="t1", default="2026-09-30")
    a = ap.parse_args()
    t0, t1 = pd.Timestamp(a.t0), pd.Timestamp(a.t1) + pd.Timedelta(days=1)
    X, skips, L = load_ea(a.log)
    E = pd.read_csv(HANDOFF / "trades_M30.csv.gz")
    for c in ("entry_time_utc", "exit_time_utc"):
        E[c] = pd.to_datetime(E[c])
    E = E[(E.entry_time_utc >= t0) & (E.entry_time_utc <= t1)].copy()
    E["signal_bar"] = (E.entry_time_utc - M30).dt.floor("30min")      # research enters at the open of the bar after the signal
    E["exit_bar"] = E.exit_time_utc.dt.floor("30min")
    # the research file records no exit reason, so infer it from where the exit landed relative to the stop and the 2R target
    d = E.direction
    stop_px = E.entry_price - d * E.stop_distance
    tp_px = E.entry_price + d * 2.0 * E.stop_distance
    tol = E.stop_distance * 0.02
    E["exit_reason"] = np.where((E.exit_price - stop_px).abs() <= tol, "stop",
                       np.where((E.exit_price - tp_px).abs() <= tol, "tp", "time"))
    X = X[(X.entry_time >= t0) & (X.entry_time <= t1)]
    print(f"EA log: {len(L):,} rows, {len(X)} trades | research trades in window: {len(E)}")
    rows = []
    for m in sorted(set(E.market) | set(X.market)):
        e, x = E[E.market == m], X[X.market == m]
        j = e.merge(x, on=["market", "signal_bar"], how="outer", suffixes=("_exp", "_ea"), indicator="side")
        both = j[j.side == "both"]
        closed = both.exit_bar_ea.notna() & both.exit_bar_exp.notna()
        exit_ok = both.exit_bar_exp == both.exit_bar_ea
        dir_ok = both.direction_exp == both.direction_ea
        rows.append(dict(market=m, research=len(e), ea=len(x), matched=len(both),
                         only_research=int((j.side == "left_only").sum()), only_ea=int((j.side == "right_only").sum()),
                         entry_match=len(both) / max(len(e), 1),
                         dir_match=float(dir_ok.mean()) if len(both) else np.nan,
                         exit_match=float(exit_ok[closed].mean()) if closed.any() else np.nan,
                         reason_match=float((both.exit_reason_exp == both.exit_reason_ea)[closed].mean()) if closed.any() else np.nan,
                         exits_compared=int(closed.sum()), exits_matched=int((exit_ok & closed).sum()),
                         R_gross_exp=float(e.R_gross.sum()), R_gross_ea=float(x.r_gross_ea.sum()),
                         cost_exp=float((e.R_spread + e.R_swap).sum()), cost_ea=float((x.r_gross_ea - x.net_R_ea).sum()),
                         n_exp=len(e), n_ea=len(x)))
    R = pd.DataFrame(rows)
    print("\n== bars matched")
    print(R[["market", "research", "ea", "matched", "only_research", "only_ea", "entry_match", "dir_match", "exit_match", "reason_match"]].round(3).to_string(index=False))
    tm, te = R.matched.sum(), R.research.sum()
    print(f"\nall markets: entry bars matched {tm} of {te} = {tm/max(te,1):.1%} | exit bars {R.exits_matched.sum()} of {R.exits_compared.sum()}"
          f" = {R.exits_matched.sum()/max(R.exits_compared.sum(),1):.1%}   (handoff bar for G27K was 95 %)")
    print("\n== R before costs, and the cost each side charged (the point of task 4)")
    print(f"  {'market':8s} {'n res':>6s} {'n EA':>6s} {'gross res':>10s} {'gross EA':>9s} {'cost res':>9s} {'cost EA':>8s} "
          f"{'cost/trade res':>15s} {'cost/trade EA':>14s} {'EA dearer by':>13s}")
    for r in R.itertuples():
        cr, ce = r.cost_exp / max(r.n_exp, 1), r.cost_ea / max(r.n_ea, 1)
        print(f"  {r.market:8s} {r.n_exp:>6d} {r.n_ea:>6d} {r.R_gross_exp:>+10.1f} {r.R_gross_ea:>+9.1f} {r.cost_exp:>9.1f} "
              f"{r.cost_ea:>8.1f} {cr:>15.4f} {ce:>14.4f} {ce - cr:>+13.4f}")
    cr = R.cost_exp.sum() / max(R.n_exp.sum(), 1); ce = R.cost_ea.sum() / max(R.n_ea.sum(), 1)
    print(f"  {'total':8s} {R.n_exp.sum():>6d} {R.n_ea.sum():>6d} {R.R_gross_exp.sum():>+10.1f} {R.R_gross_ea.sum():>+9.1f} "
          f"{R.cost_exp.sum():>9.1f} {R.cost_ea.sum():>8.1f} {cr:>15.4f} {ce:>14.4f} {ce - cr:>+13.4f}")
    print(f"\n  mean net R per trade: research {(E.R).mean():+.4f} ({len(E)}) | EA {X.net_R_ea.mean():+.4f} ({len(X)})")
    print(f"  the sleeve's edge is about +0.16R, so a cost gap much above that would sink it")
    if not skips.empty:
        print("\n== EA skips\n" + skips.to_string())


if __name__ == "__main__":
    main()
