"""Claude's review of Amendment 24's state-fidelity swing (+62 R -> -251 R).

Amendment 23's original run, over the 44-month window, made +62.070 R. The same
Amendment 23 policy on Amendment 24's state-correct engine made -251.037 R.
Codex attributes the swing entirely to the busy-state change. This script
tests that by matching the two trade lists trade by trade.

  OLD = Amendment 23 admitted orders, rebuilt with basket_dd's own functions
  NEW = the PAIRED_A23 per-trade ledger in data/basket_gate_run.txt (UTF-16)

The 44-month window runs 2022-01-01 to 2025-09-21, by exit time. Trades are
matched on (tag, entry minute). The script reports the weighted net R of
matched, old-only and new-only trades. It then breaks the new-only trades
down by weekday and hour, and by whether the entry bar is the first bar after
a market gap of more than 2 hours.

Read-only. No order path.
"""
from __future__ import annotations

import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import basket_dd as B

RAW = Path("data/basket_gate_run.txt")


def minute(t: int) -> str:
    return datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%d %H:%M")


def parse_new():
    text = RAW.read_bytes().decode("utf-16")
    rows = []
    for line in text.splitlines():
        if not line.startswith("PAIRED_A23,"):
            continue
        p = line.split(",")
        rows.append(dict(tag=p[1], entry=p[2].replace(" UTC", ""),
                         exit=p[3].replace(" UTC", ""), w=float(p[4]),
                         gross=float(p[9]), net=float(p[10])))
    return rows


def main() -> int:
    b5 = B.hist.load_history()
    uni, meta = B.audit.load_universe(b5)
    wd = B.WeeklyData.build(b5, uni)
    sel = B.Selector(wd, uni, meta)
    first = int(wd.boundaries[B.MIN_HISTORY_WEEKS])
    last = int(b5.t[-1] + b5.step)
    old_rows = B.admit_orders(B.orders_from_decisions(
        b5, uni, B.decisions_through(sel, first, last))).admitted

    lo, hi = minute(B.REPORT_START), minute(B.REPORT_SPLIT)
    old = {}
    for r in old_rows:
        x = minute(r.exit_t)
        if lo <= x < hi:
            old[(r.tag, minute(r.entry_t))] = r.net_r * r.weight
    new = {}
    for r in parse_new():
        if lo <= r["exit"] < hi:
            new[(r["tag"], r["entry"])] = r["net"] * r["w"]

    both = old.keys() & new.keys()
    only_old = old.keys() - new.keys()
    only_new = new.keys() - old.keys()
    s = lambda d, ks: sum(d[k] for k in ks)
    print(f"44-month  OLD total {sum(old.values()):+.3f} R over {len(old)} trades")
    print(f"44-month  NEW total {sum(new.values()):+.3f} R over {len(new)} trades")
    print(f"  matched   {len(both):6d}  OLD {s(old, both):+9.3f}  NEW {s(new, both):+9.3f}")
    print(f"  OLD only  {len(only_old):6d}  {s(old, only_old):+9.3f} R")
    print(f"  NEW only  {len(only_new):6d}  {s(new, only_new):+9.3f} R")

    # timing of NEW-only trades
    t_index = {minute(int(t)): i for i, t in enumerate(b5.t)}
    gap_first = np.r_[True, np.diff(b5.t) > 2 * 3600]
    by_dow, by_gap = defaultdict(lambda: [0, 0.0]), defaultdict(lambda: [0, 0.0])
    for k in only_new:
        e = datetime.strptime(k[1], "%Y-%m-%d %H:%M")
        by_dow[e.strftime("%a")][0] += 1
        by_dow[e.strftime("%a")][1] += new[k]
        i = t_index.get(k[1])
        g = "first bar after gap" if (i is not None and gap_first[i]) else (
            "bar not in data" if i is None else "normal bar")
        by_gap[g][0] += 1
        by_gap[g][1] += new[k]
    print("\nNEW-only trades by entry weekday (UTC):")
    for d in ("Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"):
        if d in by_dow:
            n, v = by_dow[d]
            print(f"  {d}  {n:6d}  {v:+9.3f} R   mean {v/n:+.4f}")
    print("\nNEW-only trades by entry bar type:")
    for g, (n, v) in by_gap.items():
        print(f"  {g:22s}  {n:6d}  {v:+9.3f} R   mean {v/n:+.4f}")
    print("\nShape of trades in the 44-month window (unweighted, per trade):")
    new44 = [r for r in parse_new() if lo <= r["exit"] < hi]
    shape_report(set(old.keys()), new44)
    return 0


def shape_report(old_keys_44, new_rows):
    """Duration and loss shape of NEW-only trades versus matched trades."""
    def stats(rows, label):
        dur = np.array([(datetime.strptime(r["exit"], "%Y-%m-%d %H:%M")
                         - datetime.strptime(r["entry"], "%Y-%m-%d %H:%M")
                         ).total_seconds() / 60 for r in rows])
        net = np.array([r["net"] for r in rows])
        gross = np.array([r["gross"] for r in rows])
        print(f"  {label:10s} n={len(rows):5d}  unweighted net {net.mean():+.4f}  "
              f"gross {gross.mean():+.4f}  win {100*np.mean(net>0):5.1f}%  "
              f"same-bar exit {100*np.mean(dur==0):5.1f}%  "
              f"median minutes {np.median(dur):6.0f}  "
              f"gross<=-0.9R {100*np.mean(gross<=-0.9):5.1f}%")
    matched = [r for r in new_rows if (r["tag"], r["entry"]) in old_keys_44]
    only = [r for r in new_rows if (r["tag"], r["entry"]) not in old_keys_44]
    stats(matched, "matched")
    stats(only, "NEW only")


if __name__ == "__main__":
    raise SystemExit(main())
