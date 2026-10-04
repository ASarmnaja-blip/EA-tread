"""Handoff section 3.3: check the MT5 EA against the research engine trade by trade.

Reads the EA's tester log (Common\\Files\\tester_g27k_log.csv) and handoff_expected_trades_h4_00utc.json, pairs trades by market
and signal bar, and reports how often the entry bar and the exit bar agree. The handoff's bar is 95 % for both; prices differ a
little because the tester uses the broker's history and the research used Candle Lab / MT5 / Dukascopy / Binance data.

The EA starts flat on the first test day, while the research may already hold a trade then, so the first trade per market is also
reported separately as a warm-up effect.

Usage: python research/g27k_dev/compare_ea_trades.py [--log <tester log>] [--from 2023-01-01 --to 2026-09-30]
"""
import argparse
import json
import pathlib
import re

import pandas as pd

HERE = pathlib.Path(__file__).resolve().parent
COMMON = pathlib.Path.home() / "AppData" / "Roaming" / "MetaQuotes" / "Terminal" / "Common" / "Files"
H4 = pd.Timedelta(hours=4)


def h4_floor(t):
    return t.floor("4h")


def load_ea(path, symbol_map):
    L = pd.read_csv(path)
    L["time"] = pd.to_datetime(L["time"], format="%Y.%m.%d %H:%M:%S")
    L["market"] = L["symbol"].map(lambda s: symbol_map.get(s, s) if isinstance(s, str) else s)
    trades = []
    for m, g in L[L.market.notna()].groupby("market"):
        open_t = None
        for r in g.sort_values("time").itertuples():
            if r.event == "ENTRY":
                open_t = dict(market=m, signal_bar=pd.to_datetime(r.signal_bar, format="%Y.%m.%d %H:%M"), entry_time=r.time,
                              entry_bar=h4_floor(r.time), fill=r.fill, bar_open=None, stop=r.stop, atr=r.atr20, lots=r.lots,
                              risk_pct=r.risk_pct, slippage=r.slippage, delay_s=r.delay_s, exit_bar=pd.NaT, exit_reason=None,
                              exit_price=None, r_gross=None)
                note = str(r.note)
                mo = re.search(r"bar open ([0-9.]+)", note)
                open_t["bar_open"] = float(mo.group(1)) if mo else None
                trades.append(open_t)
            elif r.event.startswith("EXIT_") and r.event != "EXIT_FAIL" and open_t is not None:
                note = str(r.note)
                mb = re.search(r"exit bar ([0-9.]+ [0-9:]+)", note)
                open_t["exit_bar"] = pd.to_datetime(mb.group(1), format="%Y.%m.%d %H:%M") if mb else h4_floor(r.time)
                open_t["exit_reason"] = {"EXIT_STOP": "stop", "EXIT_CHANNEL": "channel"}.get(r.event, r.event.lower())
                open_t["exit_price"] = r.exit_price
                open_t["r_gross"] = r.r_gross
                open_t = None
    skips = L[L.event.astype(str).str.startswith("SKIP_")].groupby(["market", "event"]).size()
    return pd.DataFrame(trades), skips, L


def load_expected(path, t0, t1):
    E = pd.DataFrame(json.loads(pathlib.Path(path).read_text(encoding="utf-8"))["trades"])
    for c in ("signal_bar_first_h1_utc", "entry_time_utc", "exit_time_utc"):
        E[c] = pd.to_datetime(E[c])
    E = E[(E.entry_time_utc >= t0) & (E.entry_time_utc <= t1)].copy()
    # the research labels an H4 bar by its first H1 bar (22:00 or 23:00 when metals reopen on Sunday); MT5 labels it by the
    # 4-hour boundary (20:00), so put both on the 00 UTC 4-hour grid before pairing
    E["signal_bar"] = E.signal_bar_first_h1_utc.map(h4_floor)
    E["exit_bar"] = E.exit_time_utc.map(h4_floor)
    return E


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--log", default=str(COMMON / "tester_g27k_log.csv"))
    ap.add_argument("--expected", default=str(HERE / "handoff_expected_trades_h4_00utc.json"))
    ap.add_argument("--from", dest="t0", default="2023-01-01")
    ap.add_argument("--to", dest="t1", default="2026-09-30")
    ap.add_argument("--map", default="", help="broker=research symbol pairs, e.g. XAUUSDc=XAUUSD,XAGUSDc=XAGUSD")
    a = ap.parse_args()
    smap = dict(p.split("=") for p in a.map.split(",") if "=" in p)
    t0, t1 = pd.Timestamp(a.t0), pd.Timestamp(a.t1) + pd.Timedelta(days=1)
    X, skips, L = load_ea(a.log, smap)
    E = load_expected(a.expected, t0, t1)
    print(f"EA log {a.log}: {len(L)} rows, {len(X)} trades | expected trades in window: {len(E)}")
    if X.empty:
        print("no EA trades in the log")
        return
    X = X[(X.entry_time >= t0) & (X.entry_time <= t1)]
    rows = []
    for m in sorted(set(E.market) | set(X.market)):
        e, x = E[E.market == m].sort_values("signal_bar"), X[X.market == m].sort_values("signal_bar")
        j = e.merge(x, on="signal_bar", how="outer", suffixes=("_exp", "_ea"), indicator="side")
        both = j[j.side == "both"]
        first_sig = min(e.signal_bar.min() if len(e) else t1, x.signal_bar.min() if len(x) else t1)
        warm = both.signal_bar == first_sig
        exit_ok = both.exit_bar_exp == both.exit_bar_ea
        closed = both.exit_bar_ea.notna()
        rows.append(dict(market=m, expected=len(e), ea=len(x), matched=len(both), only_expected=int((j.side == "left_only").sum()),
                         only_ea=int((j.side == "right_only").sum()), entry_match=len(both) / max(len(e), 1),
                         exit_match=float(exit_ok[closed].mean()) if closed.any() else float("nan"),
                         reason_match=float((both.exit_reason_exp == both.exit_reason_ea)[closed].mean()) if closed.any() else float("nan"),
                         entry_bp=float(((both.fill.astype(float) - both.entry_price) / both.entry_price * 1e4).median()) if len(both) else float("nan"),
                         atr_ratio=float((both.atr.astype(float) / both.atr20_sma_at_signal).median()) if len(both) else float("nan"),
                         warmup_pairs=int(warm.sum()), exits_compared=int(closed.sum()), exits_matched=int((exit_ok & closed).sum())))
        miss = j[j.side != "both"][["signal_bar", "side"]]
        if len(miss):
            print(f"  {m}: unmatched signal bars -> " + ", ".join(f"{r.signal_bar:%Y-%m-%d %H:%M} ({'research only' if r.side == 'left_only' else 'EA only'})"
                                                         for r in miss.head(12).itertuples()) + (" ..." if len(miss) > 12 else ""))
        bad = both[closed & ~exit_ok]
        if len(bad):
            print(f"  {m}: exit bar differs on {len(bad)} -> " + ", ".join(
                f"{r.signal_bar:%Y-%m-%d} exp {r.exit_bar_exp:%m-%d %H} {r.exit_reason_exp} / ea {r.exit_bar_ea:%m-%d %H} {r.exit_reason_ea}"
                for r in bad.head(8).itertuples()))
    R = pd.DataFrame(rows)
    tot_e, tot_m = R.expected.sum(), R.matched.sum()
    print("\n" + R.round(3).to_string(index=False))
    print(f"\nall markets: entry bars matched {tot_m} of {tot_e} expected = {tot_m / max(tot_e, 1):.1%}"
          f" (EA-only trades {R.only_ea.sum()}); exit bars matched {R.exits_matched.sum()} of {R.exits_compared.sum()} closed pairs"
          f" = {R.exits_matched.sum() / max(R.exits_compared.sum(), 1):.1%}; handoff bar 95 % for both")
    if not skips.empty:
        print("\nEA skips by reason:\n" + skips.to_string())


if __name__ == "__main__":
    main()
