"""Backtest of the WPWB weekly risk report (vol_scale) — what it does to risk.

The report never chooses direction, so it is tested on the plainest exposure:
hold gold for the whole week (first H1 bar open -> last H1 bar close), LONG
and SHORT, with Demo90 costs (spread, commission, slippage, long swap). Each
is run at a fixed 0.10 lot and at 0.10 x vol_scale (rounded DOWN to the 0.01
lot step). Account $10,000. vol_scale uses the EWMA forecast made BEFORE each
week. Honest limits: B_REF was computed on this same history (level only);
lambda 0.75 was not tuned by Claude; scaling shrinks gains and losses alike —
it is not an edge, and LONG's profit is gold's 2022-2026 trend.

Output: data/wpwb_weekly/backtest_risk.xlsx, backtest_risk.png (Thai).
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib import font_manager  # noqa: E402

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import bars as BR  # noqa: E402
import vol as V  # noqa: E402

for f in ("Leelawadee UI", "Tahoma", "Segoe UI"):
    if any(f == x.name for x in font_manager.fontManager.ttflist):
        plt.rcParams["font.family"] = f
        break

ACCOUNT = 10_000.0
BASE_LOT = 0.10
LOT_STEP = 0.01
OZ_PER_LOT = 100.0
FIRST_SCORED = int(np.datetime64("2022-07-01T22:15:00", "s").astype(np.int64))
OUT_X = BR.WEEKLY_DIR / "backtest_risk.xlsx"
OUT_P = BR.WEEKLY_DIR / "backtest_risk.png"


def stats(pnl, hi_mask):
    eq = ACCOUNT + np.cumsum(pnl)
    peak = np.maximum.accumulate(np.r_[ACCOUNT, eq])[1:]
    dd = eq - peak
    return {
        "กำไรรวม ($)": round(pnl.sum(), 0),
        "ขาดทุนสะสมสูงสุด max DD ($)": round(dd.min(), 0),
        "สัปดาห์แย่สุด ($)": round(pnl.min(), 0),
        "สัปดาห์ดีสุด ($)": round(pnl.max(), 0),
        "ความแกว่งรายสัปดาห์ SD ($)": round(pnl.std(ddof=1), 0),
        "กำไร ÷ max DD": round(pnl.sum() / -dd.min(), 2) if dd.min() < 0 else np.nan,
        "ขาดทุนรวมในสัปดาห์ผันผวน ($)": round(pnl[hi_mask & (pnl < 0)].sum(), 0),
        "SD ในสัปดาห์ผันผวน ($)": round(pnl[hi_mask].std(ddof=1), 0),
    }, eq, dd


def main() -> int:
    m = BR.market(BR.load_bars(frozen=False))
    cuts = BR.cuts_between(m, BR.FIRST_CUT, 10 ** 12)
    rv, _, _, _ = V.weekly_rv(m.t, m.c, m.h, m.l, cuts)
    f = V.ewma_forecast(rv)
    med = V.past_median52(rv)
    rows = []
    for k, cut in enumerate(cuts):
        if cut < FIRST_SCORED or not np.isfinite(f[k]) or not np.isfinite(med[k]):
            continue
        lo, hi = m.week_bars(int(cut))
        if hi <= lo:
            continue
        s = V.vol_scale(f[k])
        lot_s = math.floor(BASE_LOT * s / LOT_STEP + 1e-9) * LOT_STEP
        entry = float(m.o[lo])
        usd_per_bp = entry * OZ_PER_LOT / 1e4
        bp_l = float(m.pnl_bp([lo], [hi - 1], [1])[0])
        bp_s = float(m.pnl_bp([lo], [hi - 1], [-1])[0])
        rows.append({
            "cut": int(cut), "week": pd.to_datetime(int(cut) + 7 * 3600, unit="s"),
            "real": V.label(rv[k] / med[k])[1], "fc": V.label(f[k] / med[k])[1],
            "vol_scale": s, "lot_scaled": round(lot_s, 2), "entry": entry,
            "long_fixed": bp_l * usd_per_bp * BASE_LOT, "long_scaled": bp_l * usd_per_bp * lot_s,
            "short_fixed": bp_s * usd_per_bp * BASE_LOT, "short_scaled": bp_s * usd_per_bp * lot_s,
        })
    df = pd.DataFrame(rows)
    hi_mask = df.real.isin(["HIGH", "EXTREME"]).to_numpy()
    table, curves = [], {}
    for side, th in (("long", "ถือซื้อทั้งสัปดาห์"), ("short", "ถือขายทั้งสัปดาห์")):
        for mode, thm in (("fixed", "ไม้คงที่ 0.10 lot"), ("scaled", "ไม้ × vol_scale")):
            st, eq, dd = stats(df[f"{side}_{mode}"].to_numpy(), hi_mask)
            table.append({"แบบ": f"{th} · {thm}", **st})
            curves[(side, mode)] = (eq, dd)
    tab = pd.DataFrame(table)

    fig, ax = plt.subplots(4, 1, figsize=(13, 15), sharex=True,
                           gridspec_kw=dict(height_ratios=[1.4, 1.6, 1.6, 1.1]))
    w = df.week
    for a in ax:
        for x, h in zip(w, hi_mask):
            if h:
                a.axvspan(x, x + pd.Timedelta(days=7), color="#ffcc80", alpha=0.35, lw=0)
    real = np.sqrt([rv[list(cuts).index(c)] for c in df.cut])
    fc = np.sqrt([f[list(cuts).index(c)] for c in df.cut])
    ax[0].plot(w, real, color="#444", lw=1.2, label="ความผันผวนจริง (bp)")
    ax[0].plot(w, fc, color="#1f77b4", lw=1.6, label="พยากรณ์ก่อนเริ่มสัปดาห์ (EWMA)")
    ax[0].axhline(math.sqrt(V.B_REF), color="k", ls=":", lw=0.8)
    ax[0].set_ylabel("ความผันผวนรายสัปดาห์ (bp)")
    ax[0].set_title("WPWB รายงานความเสี่ยง — backtest 2022-07 ถึง 2026-09 · แถบส้ม = สัปดาห์ผันผวนสูงขึ้นไป")
    ax[0].legend(loc="upper left")
    for i, (side, th) in enumerate((("long", "ถือซื้อทั้งสัปดาห์"), ("short", "ถือขายทั้งสัปดาห์")), start=1):
        for mode, lab, c in (("fixed", "ไม้คงที่ 0.10 lot", "#999999"), ("scaled", "ไม้ × vol_scale", "#d62728")):
            ax[i].plot(w, curves[(side, mode)][0], color=c, lw=2, label=lab)
        ax[i].axhline(ACCOUNT, color="k", ls=":", lw=0.8)
        ax[i].set_ylabel(r"ทุน \$ (เริ่ม \$10,000)")
        ax[i].set_title(f"{th} (ต้นทุนจริง รวม swap) — ทิศทางไม่ได้มาจากระบบ ใช้เพื่อดูผลต่อความเสี่ยงเท่านั้น", fontsize=10)
        ax[i].legend(loc="upper left")
    ax[3].plot(w, df.vol_scale, color="#2ca02c", lw=1.8, label="vol_scale")
    ax[3].set_ylim(0.4, 1.05)
    ax[3].set_ylabel("ตัวคูณขนาดไม้")
    ax[3].legend(loc="lower left")
    fig.tight_layout()
    fig.savefig(OUT_P, dpi=110)

    out = df.copy()
    out["week"] = out.week.dt.strftime("%Y-%m-%d")
    out = out.rename(columns={"week": "เริ่มสัปดาห์ (ไทย)", "real": "ระดับจริง", "fc": "ระดับที่พยากรณ์",
                              "lot_scaled": "lot หลังปรับ", "entry": "ราคาเข้า",
                              "long_fixed": "ซื้อ ไม้คงที่ ($)", "long_scaled": "ซื้อ ปรับไม้ ($)",
                              "short_fixed": "ขาย ไม้คงที่ ($)", "short_scaled": "ขาย ปรับไม้ ($)"}).drop(columns="cut")
    with pd.ExcelWriter(OUT_X) as xw:
        tab.to_excel(xw, sheet_name="สรุป", index=False)
        out.round(2).to_excel(xw, sheet_name="รายสัปดาห์", index=False)
    pd.set_option("display.width", 250)
    print(f"weeks {len(df)} ({df.week.iloc[0]:%Y-%m-%d} .. {df.week.iloc[-1]:%Y-%m-%d}); volatile {hi_mask.sum()}")
    print(f"mean vol_scale {df.vol_scale.mean():.2f}; lot distribution {df.lot_scaled.value_counts().sort_index().to_dict()}")
    print(tab.to_string(index=False))
    print(f"saved {OUT_X} and {OUT_P}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
