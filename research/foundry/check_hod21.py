"""Audit of the Track B full pass HOD_21L (long at the 21:00 UTC open, hold 4 h, stop 2 ATR,
NOTCALM weeks): broker hours, spreads, swap, adjacent hours, per-year results, and the same
rule simulated on the live Exness H1 feed with Exness's recorded spreads. Read-only."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path[:0] = [str(HERE), str(ROOT / "research" / "wpwb_weekly")]
import engine as E  # noqa: E402
import families as F  # noqa: E402

SWAP_USD = 0.5493            # measured Exness long swap, $/oz/night (triple on Wednesday)


def main():
    import bars as BR
    m = BR.market(BR.load_bars(frozen=False))
    t = np.asarray(m.t, np.int64); idx = pd.to_datetime(t, unit="s")
    sp = np.asarray(m.sp_in, float)
    print("Exness H1 bars per UTC hour:", pd.Series(idx.hour).value_counts().sort_index().to_dict())
    print("Exness median spread $ by hour:", pd.Series(sp).groupby(idx.hour).median().round(3).to_dict())
    d = pd.DataFrame(dict(h=idx.hour, m=idx.month))
    print("Exness 21:00 bars by month:", d[d.h == 21].groupby("m").size().to_dict())

    H, D, cuts, cell = E.load()
    cb = np.where(H.week >= 0, cell[np.clip(H.week, 0, len(cell) - 1)], "")
    date = pd.to_datetime(H.t, unit="s")
    print("\nDukascopy H1 bars at 21:00 by month:", pd.Series(date.month[H.hour == 21]).value_counts().sort_index().to_dict())
    rows = []
    for h in range(18, 25):
        hh = h % 24
        sp_ = [s for s in F.hod(H) if s.name == f"HOD_{hh:02d}L"][0]
        g, ex = E.simulate(H, sp_.ent, sp_.dirs, sp_.stop, sp_.tgt, sp_.last)
        vol = np.array([c.split("/")[0] if c else "" for c in cb[sp_.ent]])
        mk = np.isin(vol, ["NORMAL", "HIGH"])
        sbp = sp_.stop / H.o[sp_.ent] * 1e4
        # swap: charged if the hold crosses 21:00 UTC (conservative: every trade entered 18-24h crossing it)
        cross = (H.hour[sp_.ent] <= 21) & (H.hour[ex] >= 22) | (H.hour[sp_.ent] >= 21) & (H.hour[ex] < H.hour[sp_.ent])
        wed = H.dow[sp_.ent] == 2
        swap_bp = np.where(cross, SWAP_USD * np.where(wed, 3, 1) / H.o[sp_.ent] * 1e4, 0.0)
        for per, (a, b) in {"2015-20": ("2015", "2021"), "2021-23": ("2021", "2024"), "2024-26": ("2024", "2027")}.items():
            mm = mk & (date[sp_.ent] >= a) & (date[sp_.ent] < b)
            net = g[mm] - E.COST_BP
            net_sw = net - swap_bp[mm]
            wk = H.t[sp_.ent][mm] // E.WEEK
            rows.append(dict(hour=hh, period=per, n=int(mm.sum()), net_bp=net.mean(), net_R=(net / sbp[mm]).mean(),
                             t_R=E.cluster_t(net / sbp[mm], wk), swap_bp=swap_bp[mm].mean(),
                             net_after_swap_R=(net_sw / sbp[mm]).mean(), t_after_swap=E.cluster_t(net_sw / sbp[mm], wk)))
    pd.set_option("display.width", 220)
    print("\nlong at hour h, hold 4 h, NOTCALM, Dukascopy mid, 2 bp cost; swap = current Exness long swap applied")
    print(pd.DataFrame(rows).round(3).to_string(index=False))

    # per-year for hour 21
    sp_ = [s for s in F.hod(H) if s.name == "HOD_21L"][0]
    g, ex = E.simulate(H, sp_.ent, sp_.dirs, sp_.stop, sp_.tgt, sp_.last)
    vol = np.array([c.split("/")[0] if c else "" for c in cb[sp_.ent]])
    mk = np.isin(vol, ["NORMAL", "HIGH"])
    sbp = sp_.stop / H.o[sp_.ent] * 1e4
    y = date[sp_.ent].year
    yr = pd.DataFrame(dict(y=y[mk], R=((g - E.COST_BP) / sbp)[mk])).groupby("y").R.agg(["mean", "count"])
    print("\nHOD_21L NOTCALM net R by year:"); print(yr.round(3).T.to_string())

    # Exness replication: long at the Exness 21:00 bar open (bid + spread = ask), exit at the bid close 4 bars later
    ex_rows = []
    h21 = np.flatnonzero(idx.hour == 21)
    h21 = h21[h21 + 3 < len(t)]
    ok = (t[h21 + 3] - t[h21]) <= 6 * 3600
    h21 = h21[ok]
    o = np.asarray(m.o, float); c = np.asarray(m.c, float)
    entry = o[h21] + sp[h21]; exitp = c[h21 + 3]
    gross = (exitp / entry - 1) * 1e4 - 0.10 * 2 / entry * 1e4          # + $0.10 slippage per fill
    swap = SWAP_USD * np.where(pd.to_datetime(t[h21], unit="s").dayofweek == 2, 3, 1) / entry * 1e4
    yy = pd.to_datetime(t[h21], unit="s").year
    print("\nExness live-feed replication (ask entry at 21:00 open, bid exit at 00:00 close, no stop, all weeks):")
    print(pd.DataFrame(dict(y=yy, net=gross, net_swap=gross - swap)).groupby("y").agg(n=("net", "size"), net_bp=("net", "mean"),
                                                                                     net_after_swap_bp=("net_swap", "mean")).round(2).to_string())
    print("all:", round(gross.mean(), 2), "bp; after swap", round((gross - swap).mean(), 2), "bp; n", len(gross))


if __name__ == "__main__":
    main()
