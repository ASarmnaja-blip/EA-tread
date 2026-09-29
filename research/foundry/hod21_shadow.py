"""Paper forward record of HOD21-SHADOW-1 (docs/FOUNDRY_SHADOW_PREREG.md Amendment 2).
Rule, frozen 2026-09-30: on the live Exness feed, at the open of every H1 bar opening at 21:00 UTC
(the hour before the daily break; it exists only in the northern winter) in a week the WPWB B0
forecast class is NORMAL or HIGH: paper long at the ask (bid open + recorded spread) + $0.10
slippage; stop 2 x ATR14 (Exness H1 bid, known at the open) checked on bid lows; otherwise exit at
the bid close of the 4th bar (00:00 UTC bar) - $0.10 slippage; swap $0.5493/oz/night (x3 Wednesday).
No order is ever sent. Each trade is recorded once (keyed by its bar time) after its exit bar has
closed (R12-5); a trade recorded more than 8 days after its exit is labelled LATE and not scored.
Exit = the bar opening at 00:00 UTC (Exness has no 22:00 bar in winter; R12-4)."""
from __future__ import annotations

import csv
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import engine as E  # noqa: E402

VERSION = "HOD21-SHADOW-1"
FORWARD = int(np.datetime64("2026-10-02T22:15:00", "s").astype(np.int64))
SWAP_USD, SLIP = 0.5493, 0.10
LOG = E.ROOT / "data" / "foundry" / "shadow" / "hod21_shadow_trades.csv"
FIELDS = ["bar_utc", "bar_epoch", "version", "week_class", "entry_ask", "stop", "exit_px", "exit_utc", "exit_kind",
          "gross_bp", "swap_bp", "net_bp", "stop_bp", "net_R", "recorded_utc"]


def main() -> int:
    os.chdir(E.ROOT)
    sys.path.insert(0, str(E.ROOT / "research" / "wpwb_weekly"))
    import bars as BR
    m = BR.market(BR.load_bars(frozen=False))
    t = np.asarray(m.t, np.int64); o, h, l, c = (np.asarray(getattr(m, a), float) for a in ("o", "h", "l", "c"))
    sp = np.asarray(m.sp_in, float)
    atr = E._atr(h, l, c, 14)
    H, D, cuts, cell = E.load_spliced()
    vol = np.array([x.split("/")[0] if x else "" for x in cell], object)
    done = set(pd.read_csv(LOG).bar_epoch.astype(int)) if LOG.exists() else set()
    new = []
    now = int(time.time())
    feed_end = int(t[-1]) + 3600
    hours = pd.to_datetime(t, unit="s").hour
    for i in np.flatnonzero((hours == 21) & (t > FORWARD)):
        if int(t[i]) in done or not np.isfinite(atr[i]):
            continue
        j0 = np.flatnonzero((t > t[i]) & (t <= t[i] + 4 * 3600) & (hours == 0))
        if not len(j0):
            continue                                          # no 00:00 bar within 4 h (weekend): no trade
        x = int(j0[0])
        if t[x] + 3600 > min(now, feed_end):
            continue                                          # exit bar not closed yet
        late = now - (t[x] + 3600) > 8 * 86400
        k = int(np.searchsorted(cuts, t[i], side="left") - 1)
        cls = vol[k] if 0 <= k < len(vol) else ""
        if cls not in ("NORMAL", "HIGH"):
            new.append(dict(bar_utc=str(pd.to_datetime(t[i], unit="s")), bar_epoch=int(t[i]), version=VERSION,
                            week_class=cls or "UNKNOWN", exit_kind="NO_TRADE"))
            continue
        ep = o[i] + sp[i] + SLIP
        stop = ep - 2 * atr[i]
        exit_px, kind, xi = c[x] - SLIP, "TIME", x
        for j in range(i, x + 1):
            if l[j] <= stop:
                exit_px = (min(o[j], stop) if j > i else stop) - SLIP; kind, xi = "STOP", j
                break
        if late:
            kind = "LATE_" + kind
        nights = 3 if pd.to_datetime(t[i], unit="s").dayofweek == 2 else 1
        swap_bp = SWAP_USD * nights / ep * 1e4
        gross = (exit_px / ep - 1) * 1e4
        stop_bp = 2 * atr[i] / ep * 1e4
        new.append(dict(bar_utc=str(pd.to_datetime(t[i], unit="s")), bar_epoch=int(t[i]), version=VERSION, week_class=cls,
                        entry_ask=ep, stop=stop, exit_px=exit_px, exit_utc=str(pd.to_datetime(t[xi], unit="s")), exit_kind=kind,
                        gross_bp=gross, swap_bp=swap_bp, net_bp=gross - swap_bp, stop_bp=stop_bp,
                        net_R=(gross - swap_bp) / stop_bp))
    if new:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        first = not LOG.exists()
        with open(LOG, "a", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=FIELDS, restval="")
            if first:
                w.writeheader()
            for r in new:
                r["recorded_utc"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
                w.writerow({k: r.get(k, "") for k in FIELDS})
    L = pd.read_csv(LOG) if LOG.exists() else pd.DataFrame()
    tr = L[L.exit_kind.isin(["TIME", "STOP"])] if len(L) else L          # LATE_* rows are not scored
    print(f"{VERSION}: {len(new)} new rows; forward trades {len(tr)}, mean net {tr.net_bp.mean() if len(tr) else float('nan'):+.2f} bp, "
          f"{tr.net_R.mean() if len(tr) else float('nan'):+.3f} R (descriptive)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
