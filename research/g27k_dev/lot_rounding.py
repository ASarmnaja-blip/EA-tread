"""Ledger id g27k_lot_rounding_nearest: what the broker's lot step does to the written 1 % rule.

The research sized every position with unrounded fractional lots. A live account can only trade whole lot steps, so the realised risk
differs. This replays the handoff trade list (entries, stops, exits and R unchanged) through an account that sizes in real lots using the
Exness contract specs read on 2026-10-03, under three sizing modes:
  fractional  what the research assumed (no rounding)            - baseline
  floor       the written rule ("round down to the lot step")
  nearest     the registered change (round half up)
The 25 % brake, the 1 % / 0.5 % risk and the overlapping-position accounting follow docs/HANDOFF_G27K_FINAL.md section 1.

Usage: python3 research/g27k_dev/lot_rounding.py [--specs <account check json>] [--start 2011-09-01] [--balance 10000]
"""
from __future__ import annotations

import argparse
import heapq
import json
import math
import pathlib

import numpy as np
import pandas as pd

HERE = pathlib.Path(__file__).resolve().parent
BRAKE_ON, BRAKE_OFF, BRAKE_MULT = 0.25, 0.125, 0.5


def load_specs(path):
    d = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    return {s["base"]: s for s in d["symbols"] if s.get("found")}, d


def size(risk_money, risk_per_lot, spec, mode):
    """Lots the broker would actually accept, and whether the minimum lot forced more risk than intended."""
    want = risk_money / risk_per_lot
    step, lo, hi = spec["vol_step"], spec["vol_min"], 200.0
    if mode == "fractional":
        return want, False
    n = want / step
    k = math.floor(n) if mode == "floor" else math.floor(n + 0.5)      # round half up
    lot = round(k * step, 8)
    forced = lot < lo
    return min(max(lot, lo), hi), forced


def run(T, specs, mode, start_bal=10_000.0, brake=True):
    bal = peak = start_bal
    heap = []; pts = []; risks = []; forced = 0; braked = 0; mult = 1.0
    for r in T.itertuples():
        while heap and heap[0][0] <= r.t:
            _, p = heapq.heappop(heap)
            bal += p; peak = max(peak, bal); pts.append((heap_t := _, bal))
        if brake:
            dd_now = 1 - bal / peak
            if mult == 1.0 and dd_now >= BRAKE_ON:
                mult = BRAKE_MULT
            elif mult < 1.0 and dd_now <= BRAKE_OFF:
                mult = 1.0
        braked += mult < 1.0
        risk_money = 0.01 * mult * bal
        lot, f = size(risk_money, r.risk_per_lot, specs[r.market], mode)
        forced += f
        actual = lot * r.risk_per_lot
        risks.append(actual / bal if bal > 0 else 0.0)
        heapq.heappush(heap, (r.tx, actual * r.R_net))
    while heap:
        tx, p = heapq.heappop(heap)
        bal += p; peak = max(peak, bal); pts.append((tx, bal))
    eq = pd.Series([b for _, b in pts], index=pd.to_datetime([t for t, _ in pts], unit="s")).sort_index()
    run_peak = eq.cummax()
    dd = float((1 - eq / run_peak).max())
    yrs = (T.tx.max() - T.t.min()) / (365.25 * 86400)
    cagr = (bal / start_bal) ** (1 / yrs) - 1 if bal > 0 else -1.0
    return dict(mode=mode, n=len(T), final=float(bal), cagr=float(cagr), dd=dd, years=float(yrs),
                avg_risk=float(np.mean(risks)), med_risk=float(np.median(risks)), max_risk=float(np.max(risks)),
                min_lot_forced=int(forced), share_braked=float(braked / max(len(T), 1))), eq


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--specs", default=str(HERE.parents[1] / ".." / "EA-tread" / "data" / "g27k_account_check.json"))
    ap.add_argument("--trades", default=str(HERE / "handoff_expected_trades_h4_00utc.json"))
    ap.add_argument("--start", default="2011-09-01")
    ap.add_argument("--balance", type=float, default=10_000.0)
    a = ap.parse_args()

    specs, meta = load_specs(a.specs)
    raw = json.loads(pathlib.Path(a.trades).read_text(encoding="utf-8"))["trades"]
    T = pd.DataFrame(raw)
    # astype("int64") follows the column's datetime resolution (microseconds here), so force seconds first
    T["t"] = pd.to_datetime(T.entry_time_utc).astype("datetime64[s]").astype("int64")
    T["tx"] = pd.to_datetime(T.exit_time_utc).astype("datetime64[s]").astype("int64")
    T["sl_dist"] = (T.entry_price - T.stop_price).abs()
    T["risk_per_lot"] = [ (d / specs[m]["tick_size"]) * specs[m]["tick_value"] for d, m in zip(T.sl_dist, T.market) ]
    T = T.sort_values("t").reset_index(drop=True)
    print(f"specs from {meta['server']} ({meta['account_type']}, read {meta['checked_utc'][:19]}), start balance {a.balance:,.0f} "
          f"{meta['currency']}")
    print("  " + " | ".join(f"{m}: min {s['vol_min']:g} step {s['vol_step']:g}" for m, s in specs.items()))
    print(f"  JP225 is quoted in JPY: its tick value uses the USDJPY rate of the spec read, not the rate of each historical trade\n")

    for label, sub in (("full file 2009-09..2026-09", T), (f"from {a.start} (matches the handoff headline)",
                                                           T[T.entry_time_utc >= a.start])):
        print(f"== {label}: {len(sub)} trades")
        base = None
        for mode in ("fractional", "floor", "nearest"):
            res, _ = run(sub, specs, mode, a.balance)
            if base is None:
                base = res
            print(f"   {mode:11s} CAGR {res['cagr']:>6.1%} | DD {res['dd']:>5.1%} | final {res['final']:>12,.0f}"
                  f" | realised risk avg {res['avg_risk']:>5.2%} med {res['med_risk']:>5.2%} max {res['max_risk']:>5.2%}"
                  f" | min-lot forced {res['min_lot_forced']:>4d} | braked {res['share_braked']:>4.0%}"
                  f" | vs fractional CAGR {res['cagr'] - base['cagr']:+.1%}")
        print()
    for m in specs:
        sub = T[T.market == m]
        print(f"   {m:7s} {len(sub):>4d} trades | mean SL {sub.sl_dist.mean():>10,.4g} | mean risk per lot "
              f"${sub.risk_per_lot.mean():>10,.0f} | E(R_net) {sub.R_net.mean():+.3f}")


if __name__ == "__main__":
    main()
