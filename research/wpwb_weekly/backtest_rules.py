"""What do the H2/H3/H4 rules actually do? (spec v3 evidence)

Same exposure as backtest_compound.py — hold gold for the whole week, long or
short, Demo90 costs, compounding, lots = 0.03/$10k x equity/10k x vol_scale
floored to 0.01 — with the frozen rules of riskrules.py switched on one at a
time and together.

Frozen rule actions (declared before running):
  H2 breaker  : at each H1 close from bar 20 of the week, if realised variance
                since the reopen exceeds 1.5x the forecast pace, HALVE the
                position at that close and do not increase it again this week.
  H3 weekend  : if the coming week is forecast HIGH/EXTREME, carry nothing
                across the cut (this weekly-hold test therefore skips the
                week); otherwise cap lots so a p99 adverse gap (175 bp) costs
                at most the per-trade budget.
  H4 news     : flatten from the H1 bar containing a tier-1 release until one
                bar after it, then re-enter at that bar's open.

Read the RISK columns (max DD, worst week, left tail). Return differences are
NOT evidence of an edge: flattening around news or skipping volatile weeks
changes exposure, and this is one gold path.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import bars as BR  # noqa: E402
import riskrules as RR  # noqa: E402
import vol as V  # noqa: E402

sys.path.insert(0, str(BR.ROOT / "research" / "pilot"))
import calendar_feed  # noqa: E402

ACCOUNT = 10_000.0
BASE_LOT_PER_10K = 0.03
RISK_BUDGET_FRAC = 0.01          # per-trade budget used by the H3 lot cap
OZ = 100.0
OUT = BR.WEEKLY_DIR / "backtest_rules.xlsx"
FIRST = int(np.datetime64("2022-07-01T22:15:00", "s").astype(np.int64))
SPREAD_BP = 2.6                  # Demo90 round-trip cost proxy for a re-entry, bp


def tier1_epochs(cal):
    d = cal[(cal.currency == "USD") & cal.event.isin(RR.TIER1)]
    return np.sort(d.epoch.unique().astype(np.int64))


def week_path(m, lo, hi, direction, lots0, forecast_rv, t1_eps, use_h2, use_h4):
    """Walk the week bar by bar; return (pnl_usd, halved_at, news_flats).

    Entry at the open of bar lo, exit at the close of bar hi-1. Costs are the
    frozen Demo90 model applied per executed leg."""
    entry = float(m.o[lo])
    usd_bp = entry * OZ / 1e4
    lots = lots0
    halved = False
    flats = 0
    pnl = 0.0
    pos_open_px = entry
    in_pos = True
    rv = 0.0
    for i in range(lo, hi):
        if i > lo:
            r = math.log(m.c[i] / m.c[i - 1]) * 1e4
            rv += r * r
        bar_has_t1 = bool(((t1_eps >= m.t[i]) & (t1_eps < m.t[i] + 3600)).any())
        # --- H4: flatten for the release bar, re-enter at the next bar's open
        if use_h4 and bar_has_t1 and in_pos:
            pnl += direction * (m.o[i] - pos_open_px) / entry * 1e4 * usd_bp * lots
            pnl -= SPREAD_BP * usd_bp * lots
            in_pos = False
            flats += 1
        elif use_h4 and not in_pos and not bar_has_t1:
            pos_open_px = float(m.o[i])
            pnl -= SPREAD_BP * usd_bp * lots
            in_pos = True
        # --- H2: halve once, at the close of the bar that trips the breaker
        if use_h2 and not halved and in_pos and RR.breaker_tripped(rv, i - lo + 1, forecast_rv):
            pnl += direction * (m.c[i] - pos_open_px) / entry * 1e4 * usd_bp * lots * 0.5
            lots *= 0.5
            pos_open_px = float(m.c[i])
            halved = True
    if in_pos:
        pnl += direction * (m.c[hi - 1] - pos_open_px) / entry * 1e4 * usd_bp * lots
    return pnl, halved, flats


def run(m, cuts, rv, f, med, t1_eps, direction, h2, h3, h4):
    eq = ACCOUNT
    peak = ACCOUNT
    rows = []
    for k, cut in enumerate(cuts):
        if cut < FIRST or not np.isfinite(f[k]) or not np.isfinite(med[k]):
            continue
        lo, hi = m.week_bars(int(cut))
        if hi <= lo:
            continue
        cls = V.label(f[k] / med[k])[1]
        scale = V.vol_scale(f[k])
        lots = RR.floor_lot(BASE_LOT_PER_10K * eq / ACCOUNT * scale)
        skipped = ""
        if h3 and not RR.weekend_hold_allowed(cls):
            lots, skipped = 0.0, "H3 skip"
        elif h3:
            cap = RR.weekend_max_lots(eq * RISK_BUDGET_FRAC, float(m.o[lo]))
            if cap < lots:
                lots, skipped = cap, "H3 cap"
        pnl, halved, flats = (0.0, False, 0)
        if lots >= RR.LOT_STEP:
            pnl, halved, flats = week_path(m, lo, hi, direction, lots, f[k], t1_eps, h2, h4)
        eq += pnl
        peak = max(peak, eq)
        rows.append(dict(cut=pd.Timestamp(int(cut), unit="s"), cls=cls, lots=lots,
                         pnl=pnl, equity=eq, dd=(eq - peak) / peak * 100,
                         halved=halved, flats=flats, note=skipped))
        if eq <= 0:
            break
    return pd.DataFrame(rows)


def summary(df, name):
    p = df.pnl.to_numpy()
    return {"กฎที่ใช้": name, "ทุนสุดท้าย ($)": round(df.equity.iloc[-1]),
            "max DD (%)": round(df.dd.min(), 1),
            "สัปดาห์แย่สุด ($)": round(p.min()),
            "ท้ายซ้าย 1% ($)": round(np.percentile(p, 1)),
            "SD รายสัปดาห์ ($)": round(p.std(ddof=1)),
            "สัปดาห์ที่เทรด": int((df.lots >= RR.LOT_STEP).sum()),
            "ตัวตัดทำงาน": int(df.halved.sum()),
            "ปิดก่อนข่าว (ครั้ง)": int(df.flats.sum()),
            "ข้ามสัปดาห์ (H3)": int((df.note == "H3 skip").sum())}


def main() -> int:
    m = BR.market(BR.load_bars(frozen=False))
    cuts = BR.cuts_between(m, BR.FIRST_CUT, 10 ** 12)
    rv, _, _, _ = V.weekly_rv(m.t, m.c, m.h, m.l, cuts)
    f = V.ewma_forecast(rv)
    med = V.past_median52(rv)
    cal = calendar_feed.load_calendar(str(BR.ROOT / "data" / "calendar.csv"))
    t1 = tier1_epochs(cal)
    print(f"tier-1 releases in the calendar: {len(t1)} "
          f"({pd.Timestamp(int(t1[0]), unit='s').date()} .. {pd.Timestamp(int(t1[-1]), unit='s').date()})")
    combos = [("ไม่มีกฎ (ฐาน)", 0, 0, 0), ("H2 ตัวตัดกลางสัปดาห์", 1, 0, 0),
              ("H3 gap สุดสัปดาห์", 0, 1, 0), ("H4 ข่าวใหญ่", 0, 0, 1),
              ("H2+H3+H4 ครบ", 1, 1, 1)]
    out, paths = [], {}
    for side, dname in ((1, "ซื้อ"), (-1, "ขาย")):
        for name, h2, h3, h4 in combos:
            df = run(m, cuts, rv, f, med, t1, side, h2, h3, h4)
            s = summary(df, f"{dname} · {name}")
            out.append(s)
            paths[(dname, name)] = df
    res = pd.DataFrame(out)
    with pd.ExcelWriter(OUT) as xw:
        res.to_excel(xw, sheet_name="สรุป", index=False)
        for (d, n), df in paths.items():
            if "ครบ" in n or "ฐาน" in n:
                df.to_excel(xw, sheet_name=f"{d} {n}"[:30], index=False)
    pd.set_option("display.width", 250)
    print(res.to_string(index=False))
    print(f"\nsaved {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
