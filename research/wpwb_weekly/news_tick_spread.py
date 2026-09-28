"""Tick-level XAUUSD spread and price jump around USD HIGH releases (READ-ONLY
MT5 copy_ticks_range). Bar spreads hide spikes; ticks do not. For each
release in the tick history: median spread in the 30 min before, max spread
from -1 to +5 min, and the largest 1-minute mid move after the release, in $
and in bp. Also the Sunday reopen and the 21:00 UTC rollover for contrast.
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import bars as BR  # noqa: E402

sys.path.insert(0, str(BR.ROOT / "research" / "pilot"))
import calendar_feed  # noqa: E402

OUT = BR.WEEKLY_DIR / "news_tick_spread.csv"


def main() -> int:
    import MetaTrader5 as mt5
    if not mt5.initialize():
        print("MT5 init failed", mt5.last_error()); return 2
    acc = mt5.account_info()
    print(f"{acc.server} trade_mode {acc.trade_mode} (read-only ticks)")
    cal = calendar_feed.load_calendar(str(BR.ROOT / "data" / "calendar.csv"))
    ev = cal[(cal.currency == "USD") & (cal.importance == "HIGH")].groupby("epoch").event.apply(
        lambda s: "; ".join(sorted(set(s)))).reset_index().rename(columns={"event": "events"})
    now = datetime.now(timezone.utc)
    rows = []
    for r in ev.itertuples():
        t = datetime.fromtimestamp(int(r.epoch), timezone.utc)
        if t > now - timedelta(hours=1) or t < now - timedelta(days=400):
            continue
        tk = mt5.copy_ticks_range("XAUUSD", t - timedelta(minutes=30), t + timedelta(minutes=5), mt5.COPY_TICKS_INFO)
        if tk is None or len(tk) < 50:
            continue
        ts = tk["time_msc"] / 1000.0
        sp = tk["ask"] - tk["bid"]
        mid = (tk["ask"] + tk["bid"]) / 2
        pre = ts < r.epoch - 60
        win = (ts >= r.epoch - 60) & (ts <= r.epoch + 300)
        post = (ts >= r.epoch) & (ts <= r.epoch + 60)
        if pre.sum() < 20 or win.sum() < 5 or post.sum() < 2:
            continue
        m0 = mid[pre][-1]
        rows.append(dict(time=t.strftime("%Y-%m-%d %H:%M"), events=r.events, price=m0,
                         spread_pre_median=float(np.median(sp[pre])), spread_max_window=float(sp[win].max()),
                         jump_1m_usd=float(np.max(np.abs(mid[post] - m0))),
                         jump_1m_bp=float(np.max(np.abs(mid[post] - m0)) / m0 * 1e4),
                         ticks=int(win.sum())))
    mt5.shutdown()
    df = pd.DataFrame(rows)
    df.to_csv(OUT, index=False)
    if df.empty:
        print("no tick history around releases"); return 0
    df["spread_ratio"] = df.spread_max_window / df.spread_pre_median
    print(f"releases with ticks: {len(df)} ({df.time.min()} .. {df.time.max()})")
    print(f"pre-release median spread ${df.spread_pre_median.median():.3f}; "
          f"max spread -1..+5 min: median ${df.spread_max_window.median():.3f}, p90 ${df.spread_max_window.quantile(.9):.3f}, "
          f"max ${df.spread_max_window.max():.3f} (x{df.spread_ratio.max():.0f} of normal)")
    print(f"largest move within 1 min: median {df.jump_1m_bp.median():.1f} bp (${df.jump_1m_usd.median():.2f}), "
          f"p90 {df.jump_1m_bp.quantile(.9):.1f} bp, max {df.jump_1m_bp.max():.1f} bp (${df.jump_1m_usd.max():.2f})")
    print(df.sort_values("jump_1m_bp", ascending=False).head(8)[["time", "events", "spread_max_window", "jump_1m_usd", "jump_1m_bp"]].to_string(index=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
