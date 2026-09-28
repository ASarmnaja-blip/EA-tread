"""Cheap check before building anything new: within the already-tested
0.5R-3.0R target range, does profitability improve as target R grows?

The operator's idea: find trades with a stop wide enough that cost can't eat
it, at a reward so large that one win pays for many losses. Before building a
whole new extended-time-stop system to test very large targets (5R, 10R, 20R
- which the current 24-hour time stop cannot resolve; price would rarely
reach them before being cut off), check whether the trend even points that
way within data already computed. Uses the causal chain (Amendment 26),
grouped by target R only, marginalizing over stop/family/timeframe/period -
on both XAUUSD and GBPUSD's already-built raw caches. Read-only.
"""
from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import basket_gate as A24
import canonical_history as ch
import causal_chain as C
import historical_regime_walkforward as hist
import mtf_engine as E


def check(b5, streams, meta, label):
    fee = E.COMMISSION_RT + 2.0 * E.SLIP_PER_FILL
    by_target = defaultdict(lambda: [0, 0.0, 0.0, 0])  # n, gross, net, wins
    by_stop_target = defaultdict(lambda: [0, 0.0])      # n, net  (win-rate needed check)
    for tag, m in meta.items():
        s = streams[m["stream"]]
        held = s["held"][:, int(m["plane"])]
        chosen, _ = C.causal_indices(s["entry_k"], s["order_k"], held)
        if not len(chosen):
            continue
        risk = float(m["stop"]) * s["atr"][chosen]
        gross = s["gross"][chosen, int(m["plane"])]
        net = gross - fee / risk
        tgt = float(m["target"])
        a = by_target[tgt]
        a[0] += len(chosen); a[1] += float(gross.sum()); a[2] += float(net.sum())
        a[3] += int(np.sum(net > 0))
        b = by_stop_target[(float(m["stop"]), tgt)]
        b[0] += len(chosen); b[1] += float(net.sum())

    print(f"\n=== {label}: net R grouped by TARGET only (marginal over stop/family/tf) ===")
    print(f"{'target R':>9s}{'trades':>10s}{'gross/tr':>10s}{'net/tr':>9s}{'win%':>7s}")
    for tgt in sorted(by_target):
        n, g, net, w = by_target[tgt]
        print(f"{tgt:9.2f}{n:10,d}{g/n:10.4f}{net/n:9.4f}{100*w/n:7.1f}%")

    print(f"\n=== {label}: net R per trade by (stop, target) — is a corner winning? ===")
    print(f"{'stop':>6s}{'target':>7s}{'trades':>9s}{'net/tr':>9s}")
    for (st, tg) in sorted(by_stop_target):
        n, net = by_stop_target[(st, tg)]
        if n >= 30:
            print(f"{st:6.2f}{tg:7.2f}{n:9,d}{net/n:9.4f}")
    return by_target


def main() -> int:
    print("checking XAUUSD...")
    b5x = hist.load_history()
    sx, mx, _ = A24.load_raw_cache(b5x)
    check(b5x, sx, mx, "XAUUSD (causal chain)")

    print("\nchecking GBPUSD...")
    b5g = ch.load(Path("data/canonical_GBPUSD_M5.npz"))
    E.SPREAD_FALLBACK = 0.00001
    E.COMMISSION_RT = 5e-05
    sg, mg, _ = A24.load_raw_cache(b5g)
    check(b5g, sg, mg, "GBPUSD (causal chain, spread~0, commission 5e-5)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
