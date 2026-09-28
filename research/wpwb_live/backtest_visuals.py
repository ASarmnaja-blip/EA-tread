"""Chart + Thai Excel for the WPWB current-era backtest (reads the CSVs
written by backtest_report.py)."""
from __future__ import annotations

import os
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib import font_manager  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
os.chdir(ROOT)

for f in ("Leelawadee UI", "Tahoma", "Segoe UI"):
    if any(f == x.name for x in font_manager.fontManager.ttflist):
        plt.rcParams["font.family"] = f
        break


def main() -> int:
    df = pd.read_csv("data/wpwb_backtest_weekly.csv", parse_dates=["week_start"])
    hi_cut = df.sigma_daily_pct_at_rebuild.quantile(2 / 3)

    fig, (a1, a2, a3) = plt.subplots(3, 1, figsize=(13, 11), sharex=True,
                                     gridspec_kw=dict(height_ratios=[2.2, 1.3, 1.2]))
    for col, lab, c in (("LONG_equity", "LONG (ถือทองทั้งสัปดาห์)", "#888888"),
                        ("VOLMAN_equity", "VOLMAN (ปรับขนาดตามความผันผวน)", "#1f77b4"),
                        ("TSM26_equity", "TSM26 (ตามเทรนด์ 26 สัปดาห์)", "#d62728")):
        a1.plot(df.week_start, df[col], label=lab, color=c, lw=2)
    a1.axhline(1000, color="k", lw=0.8, ls=":")
    a1.axhline(0, color="red", lw=1, ls="--")
    a1.text(df.week_start.iloc[1], 30, r"เงินหมดบัญชี \$0", color="red", fontsize=9)
    a1.set_ylabel(r"ทุน \$ (เริ่ม \$1,000, 0.01 lot)")
    a1.set_title("WPWB backtest ยุคปัจจุบัน 2024-01 ถึง 2026-09 (ต้นทุนจริง: spread+ค่าคอม+slippage+swap)")
    a1.legend(loc="upper left")
    for _, r in df[df.sigma_daily_pct_at_rebuild >= hi_cut].iterrows():
        for ax in (a1, a2, a3):
            ax.axvspan(r.week_start, r.week_start + pd.Timedelta(days=7), color="orange",
                       alpha=0.12, lw=0)
    a2.plot(df.week_start, df.gold_close, color="goldenrod", lw=1.8)
    a2.set_ylabel(r"ราคาทอง \$")
    a2.set_title("แถบส้ม = สัปดาห์ที่ความผันผวนตอน Weekend Rebuild อยู่กลุ่มสูงสุด 1/3", fontsize=10)
    colors = np.where(df.LONG_usd >= 0, "#2ca02c", "#d62728")
    a3.bar(df.week_start, df.LONG_usd, width=5, color=colors)
    a3.set_ylabel(r"กำไร/ขาดทุน LONG \$/สัปดาห์")
    a3.axhline(0, color="k", lw=0.6)
    fig.tight_layout()
    Path("data").mkdir(exist_ok=True)
    fig.savefig("data/wpwb_backtest_equity.png", dpi=120)

    th = {"week_start": "สัปดาห์เริ่ม", "gold_open": "ทองเปิด", "gold_close": "ทองปิด",
          "gold_move_usd": "ทองเปลี่ยน $", "gold_move_pct": "ทองเปลี่ยน %",
          "week_range_usd": "กรอบสัปดาห์ $", "sigma_daily_pct_at_rebuild": "ความผันผวนรายวัน % (ตอน Rebuild)",
          "volman_size": "ขนาด VOLMAN (เท่า)", "tsm26_dir": "ทิศ TSM26 (+1 ซื้อ/-1 ขาย)",
          "dxy_pct": "DXY เปลี่ยน %", "efficiency_week": "ความเป็นเทรนด์ของสัปดาห์ (0-1)",
          "events": "ข่าวสำคัญ (hot=สูงกว่าคาด cool=ต่ำกว่าคาด)",
          "LONG_usd": "LONG กำไร $", "VOLMAN_usd": "VOLMAN กำไร $", "TSM26_usd": "TSM26 กำไร $",
          "LONG_equity": "LONG ทุนสะสม $", "VOLMAN_equity": "VOLMAN ทุนสะสม $",
          "TSM26_equity": "TSM26 ทุนสะสม $", "month": "เดือน"}
    w = df.drop(columns=["cut"]).rename(columns=th)
    w["สัปดาห์เริ่ม"] = w["สัปดาห์เริ่ม"].dt.date
    q = df.assign(q=df.week_start.dt.to_period("Q").astype(str)).groupby("q").agg(
        ทองเปลี่ยน_pct=("gold_move_pct", "sum"), DXY_pct=("dxy_pct", "sum"),
        ความผันผวนเฉลี่ย=("sigma_daily_pct_at_rebuild", "mean"),
        สัปดาห์ทองขึ้น=("gold_move_usd", lambda x: round((x > 0).mean(), 2)),
        LONG=("LONG_usd", "sum"), VOLMAN=("VOLMAN_usd", "sum"), TSM26=("TSM26_usd", "sum")
    ).round(2).reset_index().rename(columns={"q": "ไตรมาส"})
    terc = pd.qcut(df.sigma_daily_pct_at_rebuild, 3, labels=["ต่ำ", "กลาง", "สูง"])
    v = df.groupby(terc, observed=True).agg(
        จำนวนสัปดาห์=("LONG_usd", "size"), ทองเฉลี่ย_ต่อสัปดาห์=("gold_move_usd", "mean"),
        สัปดาห์แย่สุด=("gold_move_usd", "min"), ขนาด_VOLMAN_เฉลี่ย=("volman_size", "mean"),
        LONG_รวม=("LONG_usd", "sum"), VOLMAN_รวม=("VOLMAN_usd", "sum")).round(1).reset_index()
    v = v.rename(columns={"sigma_daily_pct_at_rebuild": "ความผันผวนตอน Rebuild"})
    with pd.ExcelWriter("data/wpwb_backtest.xlsx", engine="openpyxl") as xw:
        q.to_excel(xw, sheet_name="รายไตรมาส", index=False)
        v.to_excel(xw, sheet_name="ตามความผันผวน", index=False)
        w.nlargest(15, "LONG กำไร $").to_excel(xw, sheet_name="15 สัปดาห์กำไรสุด", index=False)
        w.nsmallest(15, "LONG กำไร $").to_excel(xw, sheet_name="15 สัปดาห์ขาดทุนสุด", index=False)
        w.to_excel(xw, sheet_name="รายสัปดาห์ทั้งหมด", index=False)
    print("wrote data/wpwb_backtest_equity.png and data/wpwb_backtest.xlsx; font:",
          plt.rcParams["font.family"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
