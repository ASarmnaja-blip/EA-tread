"""Are signals that fire while the same cell's previous trade is still open
systematically worse? Claude, reviewing Amendment 24.

The finding it tests: Amendment 23's paired replay on Amendment 24's engine
took 2,820 trades that the old continuous cache had skipped. Those trades
averaged -0.37 R gross and won 18.3% of the time, against +0.15 R and 33.5%
for the 9,906 trades both engines share. The old per-cell busy chain skipped
every signal that fired while that cell's previous (possibly hypothetical)
trade was still open. If such "re-signals" are structurally bad across the
whole universe, the old chain was a real filter, not a fidelity defect. It is
causal, because whether the earlier trade is still open is known at the time,
and it can be run live by tracking a shadow position for each cell.

For every one of the 8,250 cells, over the whole canonical history, this
script walks the raw fills (Codex's Amendment 24 raw cache, full-hash
verified) with the one-position chain. It labels each fill:

  FREE       - no earlier trade of that cell is open; the chain takes it
  RE_SAME    - an earlier trade is open, and this signal is the same direction
  RE_OPPOSE  - an earlier trade is open, and this signal is the opposite way

It reports gross geometric R (spread is inside the Bid/Ask geometry) and net
R after commission and slippage. Swap is left out, which is stated here
rather than hidden. Results are by label, family, timeframe and period.
Read-only.
"""
from __future__ import annotations

import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import basket_gate as G
import historical_regime_walkforward as hist
import mtf_engine as E

SPLIT = int(datetime(2025, 9, 21, tzinfo=timezone.utc).timestamp())
START = int(datetime(2022, 1, 1, tzinfo=timezone.utc).timestamp())


def main() -> int:
    b5 = hist.load_history()
    streams, meta, _ = G.load_raw_cache(b5)
    fee = E.COMMISSION_RT + 2.0 * E.SLIP_PER_FILL
    plane_keys = tuple((st, tg) for st in E.STOPS for tg in E.TARGETS)

    # acc[(label, group)] = [n, sum_gross, sum_net, wins]
    acc = defaultdict(lambda: np.zeros(4))

    def add(label, group, g, n):
        a = acc[(label, group)]
        a[0] += 1; a[1] += g; a[2] += n; a[3] += n > 0

    by_stream = defaultdict(list)
    for tag, m in meta.items():
        by_stream[m["stream"]].append(m)

    for key, s in streams.items():
        # Signal order, exactly as the old cache's chain walked it; Codex's
        # reproduction audit shows this raw order reproduces that cache.
        ek = s["entry_k"].astype(np.int64)
        dirs = s["direction"]
        atr = s["atr"]
        gross_all = s["gross"]
        held_all = s["held"].astype(np.int64)
        t_in = b5.t[ek]
        for m in by_stream[key]:
            p = int(m["plane"])
            risk = float(m["stop"]) * atr
            gross = gross_all[:, p]
            held = held_all[:, p]
            net = gross - fee / risk
            fam, tf = m["setup"], m["tf"]
            busy_until, busy_dir = -1, 0
            for q in range(len(ek)):
                k = ek[q]
                if k <= busy_until:
                    label = "RE_SAME" if dirs[q] == busy_dir else "RE_OPPOSE"
                else:
                    label = "FREE"
                    busy_until = k + held[q]
                    busy_dir = dirs[q]
                period = ("44m" if START <= t_in[q] < SPLIT else
                          "12m" if t_in[q] >= SPLIT else "2021")
                g, n = float(gross[q]), float(net[q])
                add(label, "ALL", g, n)
                add(label, "period:" + period, g, n)
                add(label, "family:" + fam, g, n)
                add(label, "tf:" + tf, g, n)

    def show(group):
        cells = [(lab, acc[(lab, group)]) for lab in ("FREE", "RE_SAME", "RE_OPPOSE")]
        parts = []
        for lab, a in cells:
            if a[0]:
                parts.append(f"{lab:9s} n={int(a[0]):>10,d} gross {a[1]/a[0]:+.4f} "
                             f"net {a[2]/a[0]:+.4f} win {100*a[3]/a[0]:5.1f}%")
        print(f"{group:18s} | " + " | ".join(parts))

    print("Per-signal means over all 8,250 cells (unweighted, whole history).")
    print("FREE = the cell's chain is flat; RE_* = an earlier trade is still open.\n")
    for grp in ["ALL", "period:2021", "period:44m", "period:12m"]:
        show(grp)
    print()
    for fam in E.SETUPS:
        show("family:" + fam)
    print()
    for tf, _ in E.TIMEFRAMES:
        show("tf:" + tf)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
