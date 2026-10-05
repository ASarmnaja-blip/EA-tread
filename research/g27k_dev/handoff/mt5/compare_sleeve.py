"""A sleeve EA (G27K_M30 or G27K_H1, Include/G27K/G27K_Sleeve.mqh) against the research trades.

Pairs the EA's tester log with trades_<book>.csv.gz on market and signal bar, and reports how often the entry bar, the exit bar and
the exit reason agree, and R before and after costs either side. Prices differ a little by construction (the research priced gold and
silver off Dukascopy mid, BTC and ETH off Binance), so the bars and the R per trade are what must line up. --before compares an
older log too, to show what a change to the EA did.

Usage: python compare_sleeve.py --book M30|H1 [--log <tester log>] [--before <older log>] [--from 2023-01-01] [--to 2026-09-30]
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
TF = {"M30": pd.Timedelta(minutes=30), "H1": pd.Timedelta(hours=1)}
M4 = ["XAUUSD", "XAGUSD", "BTCUSD", "ETHUSD"]


def load_ea(path, bar):
    # the note is free text and last; split on the first N-1 commas only
    raw = pathlib.Path(path).read_text(encoding="utf-8", errors="replace").splitlines()
    head = raw[0].split(",")
    rows = [r.split(",", len(head) - 1) for r in raw[1:] if r.strip()]
    L = pd.DataFrame([r for r in rows if len(r) == len(head)], columns=head)
    L["time"] = pd.to_datetime(L["time"], format="%Y.%m.%d %H:%M:%S")
    num = lambda v: float(v) if v not in ("", None) else np.nan
    trades, cur = [], {}
    for r in L[L.symbol != ""].sort_values("time", kind="mergesort").itertuples():
        m = r.symbol
        if r.event == "ENTRY":
            cur[m] = dict(market=m, direction=1 if r.dir == "long" else -1,
                          signal_bar=pd.to_datetime(r.signal_bar, format="%Y.%m.%d %H:%M"), entry_time=r.time,
                          fill=num(r.fill), stop=num(r.stop), atr20=num(r.atr20))
            mo = re.search(r"risk ([0-9.]+) of target", str(r.note))
            cur[m]["risk_money"] = float(mo.group(1)) if mo else np.nan
        elif str(r.event).startswith("EXIT_") and r.event not in ("EXIT_FAIL", "EXIT_WAIT") and m in cur:   # a wait is not an exit
            t = cur.pop(m)
            t["exit_time"] = r.time
            t["exit_bar"] = r.time.floor(bar)
            t["exit_reason"] = {"EXIT_STOP": "stop", "EXIT_TP": "tp", "EXIT_TIME": "time"}.get(r.event, r.event.lower())
            t["r_gross_ea"] = num(r.r_gross)
            t["net_R_ea"] = num(r.money) / t["risk_money"] if t["risk_money"] else np.nan
            trades.append(t)
    return pd.DataFrame(trades), L


def research(book, t0, t1, bar):
    E = pd.read_csv(HANDOFF / f"trades_{book}.csv.gz")
    for c in ("entry_time_utc", "exit_time_utc"):
        E[c] = pd.to_datetime(E[c])
    E = E[E.market.isin(M4) & (E.entry_time_utc >= t0) & (E.entry_time_utc <= t1)].copy()
    E["signal_bar"] = (E.entry_time_utc - TF[book]).dt.floor(bar)        # entry is the open of the bar after the signal
    E["exit_bar"] = E.exit_time_utc.dt.floor(bar)
    d, tol = E.direction, E.stop_distance * 0.02
    E["exit_reason"] = np.where((E.exit_price - (E.entry_price - d * E.stop_distance)).abs() <= tol, "stop",
                       np.where((E.exit_price - (E.entry_price + d * 2.0 * E.stop_distance)).abs() <= tol, "tp", "time"))
    return E


def compare(E, X, label):
    rows = []
    for m in M4:
        e, x = E[E.market == m], X[X.market == m]
        j = e.merge(x, on=["market", "signal_bar"], how="outer", suffixes=("_exp", "_ea"), indicator="side")
        both = j[j.side == "both"]
        closed = both.exit_bar_ea.notna() & both.exit_bar_exp.notna()
        rows.append(dict(market=m, research=len(e), ea=len(x), matched=len(both), entry_match=len(both) / max(len(e), 1),
                         dir_match=float((both.direction_exp == both.direction_ea).mean()) if len(both) else np.nan,
                         exit_match=float((both.exit_bar_exp == both.exit_bar_ea)[closed].mean()) if closed.any() else np.nan,
                         reason_match=float((both.exit_reason_exp == both.exit_reason_ea)[closed].mean()) if closed.any() else np.nan,
                         gross_res=float(both.R_gross.mean()), gross_ea=float(both.r_gross_ea.mean()),
                         net_res=float(both.R.mean()), net_ea=float(both.net_R_ea.mean()),
                         all_net_res=float(e.R.mean()), all_net_ea=float(x.net_R_ea.mean()),
                         n_matched=len(both), n_exits=int(closed.sum()),
                         n_exit_ok=int(((both.exit_bar_exp == both.exit_bar_ea) & closed).sum())))
    R = pd.DataFrame(rows)
    tm, te = R.matched.sum(), R.research.sum()
    print(f"\n== {label}")
    print(R[["market", "research", "ea", "matched", "entry_match", "dir_match", "exit_match", "reason_match",
             "gross_res", "gross_ea", "net_res", "net_ea"]].round(3).to_string(index=False))
    w = lambda c: float((R[c] * R.n_matched).sum() / max(R.n_matched.sum(), 1))
    print(f"  all: entry bars {tm} of {te} = {tm / max(te, 1):.1%} | exit bars {R.n_exit_ok.sum()} of {R.n_exits.sum()} = "
          f"{R.n_exit_ok.sum() / max(R.n_exits.sum(), 1):.1%} | matched gross R research {w('gross_res'):+.3f} EA {w('gross_ea'):+.3f}"
          f" | matched net R research {w('net_res'):+.3f} EA {w('net_ea'):+.3f}")
    print(f"  every trade: net R research {E.R.mean():+.4f} ({len(E)}) | EA {X.net_R_ea.mean():+.4f} ({len(X)})")
    return R


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--book", required=True, choices=list(TF))
    ap.add_argument("--log", default="")
    ap.add_argument("--before", default="")
    ap.add_argument("--from", dest="t0", default="2023-01-01")
    ap.add_argument("--to", dest="t1", default="2026-09-30")
    a = ap.parse_args()
    bar = {"M30": "30min", "H1": "1h"}[a.book]
    t0, t1 = pd.Timestamp(a.t0), pd.Timestamp(a.t1) + pd.Timedelta(days=1)
    E = research(a.book, t0, t1, bar)
    log = a.log or str(COMMON / f"tester_g27k_{a.book.lower()}_log.csv")
    for label, path in (("before", a.before), ("EA", log)):
        if not path:
            continue
        X, L = load_ea(path, bar)
        X = X[(X.entry_time >= t0) & (X.entry_time <= t1)]
        compare(E, X, f"{label}: {pathlib.Path(path).name}")
        sk = L[L.event.astype(str).str.startswith("SKIP_")].groupby("event").size()
        print("  skips: " + ", ".join(f"{k} {v}" for k, v in sk.items()))


if __name__ == "__main__":
    main()
