"""G27K-F EA (G27K_Trend.mq5 1.10) against the research: the Fed rule times, then the trades.

1. Fed rule times: the EA writes the times it computed from the FRED DGS2 csv to Common\\Files\\tester_g27k_fed_times.txt; they are
   compared with news_shock.fed_shocks() run here on the same file (its code copied line for line below).
2. Trades: the EA's tester log against trades_F.csv.gz for gold, silver, BTC and ETH, paired on market and entry bar (H4). Reports
   entry and exit bars, the Fed-rule exits, the trades the EA dropped by the Fed rule, and R either side. The research's R_gross
   column belongs to the original exit on Fed-rule exits, so its gross R here is R + R_spread + R_swap.

Trades are paired on the H4 bar each side entered in, as bucket numbers (time - start hour) // 4 h, so the comparison holds for the
22:00 UTC bars of every research report (the default) and for 00:00 UTC bars alike.

Usage: python compare_f.py [--from 2019-01-01] [--to 2026-09-30] [--dgs2 <csv>] [--h4start 22]
"""
from __future__ import annotations

import argparse
import pathlib
import re

import numpy as np
import pandas as pd
from pandas.tseries.holiday import USFederalHolidayCalendar

HERE = pathlib.Path(__file__).resolve().parent
HANDOFF = HERE.parent
COMMON = pathlib.Path.home() / "AppData" / "Roaming" / "MetaQuotes" / "Terminal" / "Common" / "Files"
SNAP_DGS2 = pathlib.Path.home() / "Documents" / "G27K-snap" / "data" / "macro" / "fred" / "DGS2.csv"
M4 = ["XAUUSD", "XAGUSD", "BTCUSD", "ETHUSD"]
H4 = pd.Timedelta(hours=4)
START_HOUR = 22


def bucket(t):
    """H4 bucket number as g768.frames groups H1 bars: (time - start hour) // 4 h."""
    sec = (pd.to_datetime(t) - pd.Timestamp("1970-01-01")) // pd.Timedelta("1s")
    return (sec - START_HOUR * 3600) // 14400


def fed_shocks(path):
    """news_shock.fed_shocks, with the file path as the argument."""
    d = pd.read_csv(path)
    d = d[pd.to_numeric(d.DGS2, errors="coerce").notna()]
    v = pd.Series(d.DGS2.astype(float).to_numpy(), index=pd.to_datetime(d.observation_date))
    ch = v.diff()
    sd = ch.rolling(250, min_periods=120).std().shift(1)
    days = ch[ch >= 2 * sd].index
    nb = pd.offsets.CustomBusinessDay(calendar=USFederalHolidayCalendar())
    pub = [(t + nb).tz_localize("UTC") + pd.Timedelta(hours=22) for t in days]
    return np.array(sorted(int(x.timestamp()) for x in pub))


def load_ea(path):
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
            sb = pd.to_datetime(r.signal_bar, format="%Y.%m.%d %H:%M")
            cur[m] = dict(market=m, signal_bar=sb, entry_time=r.time, fill=num(r.fill), stop=num(r.stop), atr20=num(r.atr20))
            mo = re.search(r"risk ([0-9.]+) of target", str(r.note))
            cur[m]["risk_money"] = float(mo.group(1)) if mo else np.nan
        elif str(r.event).startswith("EXIT_") and r.event not in ("EXIT_FAIL", "EXIT_WAIT") and m in cur:   # a wait is not an exit
            t = cur.pop(m)
            t["exit_time"] = r.time
            t["exit_time_ea"] = r.time
            t["exit_reason"] = {"EXIT_STOP": "stop", "EXIT_CHANNEL": "channel", "EXIT_FED": "fed"}.get(r.event, r.event.lower())
            t["r_gross_ea"] = num(r.r_gross)
            t["net_R_ea"] = num(r.money) / t["risk_money"] if t["risk_money"] else np.nan
            trades.append(t)
    return pd.DataFrame(trades), L


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="t0", default="2019-01-01")
    ap.add_argument("--to", dest="t1", default="2026-09-30")
    ap.add_argument("--dgs2", default=str(SNAP_DGS2))
    ap.add_argument("--h4start", type=int, default=22)
    a = ap.parse_args()
    global START_HOUR
    START_HOUR = a.h4start
    t0, t1 = pd.Timestamp(a.t0), pd.Timestamp(a.t1) + pd.Timedelta(days=1)

    # ---- 1. Fed rule times
    res = fed_shocks(a.dgs2)
    ea_txt = [x for x in (COMMON / "tester_g27k_fed_times.txt").read_text(encoding="utf-8", errors="replace").splitlines() if x.strip()]
    ea = np.array(sorted(int(pd.Timestamp(x.replace(".", "-"), tz="UTC").timestamp()) for x in ea_txt))
    only_r, only_e = np.setdiff1d(res, ea), np.setdiff1d(ea, res)
    fmt = lambda xs: [str(pd.Timestamp(int(x), unit="s")) for x in xs[:10]]
    print(f"== Fed rule times: research {len(res)} | EA {len(ea)} | identical {len(np.intersect1d(res, ea))}"
          f" | only research {len(only_r)} {fmt(only_r)} | only EA {len(only_e)} {fmt(only_e)}")
    win = res[(res >= t0.tz_localize('UTC').timestamp()) & (res < t1.tz_localize('UTC').timestamp())]
    print(f"   in the test window {a.t0}..{a.t1}: {len(win)} rule times")

    # ---- 2. trades
    E = pd.read_csv(HANDOFF / "trades_F.csv.gz")
    for c in ("entry_time_utc", "exit_time_utc"):
        E[c] = pd.to_datetime(E[c])
    E = E[E.market.isin(M4) & (E.entry_time_utc >= t0) & (E.entry_time_utc <= t1)].copy()
    E["entry_bar"] = bucket(E.entry_time_utc)
    E["exit_bar"] = bucket(E.exit_time_utc)
    E["gross_eff"] = E.R + E.R_spread + E.R_swap
    E["fed_exit"] = E.fed_exit.astype(bool)
    X, L = load_ea(COMMON / "tester_g27k_log.csv")
    X = X[(X.entry_time >= t0) & (X.entry_time <= t1)].copy()
    X["entry_bar"] = bucket(X.entry_time)
    X["exit_bar"] = bucket(X.exit_time_ea)
    rows = []
    for m in M4:
        e, x = E[E.market == m], X[X.market == m]
        j = e.merge(x, on=["market", "entry_bar"], how="outer", suffixes=("_exp", "_ea"), indicator="side")
        both = j[j.side == "both"]
        closed = both.exit_bar_exp.notna() & both.exit_bar_ea.notna()
        fed_r, fed_e = both.fed_exit, both.exit_reason == "fed"
        rows.append(dict(market=m, research=len(e), ea=len(x), matched=len(both), entry_match=len(both) / max(len(e), 1),
                         exit_match=float((both.exit_bar_exp == both.exit_bar_ea)[closed].mean()) if closed.any() else np.nan,
                         fed_res=int(e.fed_exit.sum()), fed_ea=int((x.exit_reason == "fed").sum()), fed_both=int((fed_r & fed_e).sum()),
                         gross_res=float(both.gross_eff.mean()), gross_ea=float(both.r_gross_ea.mean()),
                         net_res=float(both.R.mean()), net_ea=float(both.net_R_ea.mean()),
                         n_exit=int(closed.sum()), n_exit_ok=int(((both.exit_bar_exp == both.exit_bar_ea) & closed).sum())))
        miss = j[j.side == "left_only"].sort_values("entry_bar").head(3)
        extra = j[j.side == "right_only"].sort_values("entry_bar").head(3)
        if len(miss) or len(extra):
            print(f"   {m}: research-only entries {[str(t) for t in miss.entry_time_utc]} | EA-only {[str(t) for t in extra.entry_time]}")
    R = pd.DataFrame(rows)
    print("\n== G27K-F trades, " + a.t0 + " .. " + a.t1)
    print(R[["market", "research", "ea", "matched", "entry_match", "exit_match", "fed_res", "fed_ea", "fed_both",
             "gross_res", "gross_ea", "net_res", "net_ea"]].round(3).to_string(index=False))
    w = lambda c: float((R[c] * R.matched).sum() / max(R.matched.sum(), 1))
    print(f"  all: entry bars {R.matched.sum()} of {R.research.sum()} = {R.matched.sum() / max(R.research.sum(), 1):.1%} | exit bars "
          f"{R.n_exit_ok.sum()} of {R.n_exit.sum()} = {R.n_exit_ok.sum() / max(R.n_exit.sum(), 1):.1%} | Fed exits research "
          f"{R.fed_res.sum()} EA {R.fed_ea.sum()} both {R.fed_both.sum()} | matched gross R research {w('gross_res'):+.3f} EA "
          f"{w('gross_ea'):+.3f} | net R research {w('net_res'):+.3f} EA {w('net_ea'):+.3f}")
    print(f"  every trade: net R research {E.R.mean():+.4f} ({len(E)}) | EA {X.net_R_ea.mean():+.4f} ({len(X)})")
    ev = L.event.astype(str)
    print("  EA events: " + ", ".join(f"{k} {v}" for k, v in ev[ev.str.startswith(("SKIP_", "SHADOW", "EXIT_FED", "FED"))].value_counts().items()))


if __name__ == "__main__":
    main()
