"""Chart + remaining-loss table for R2 (VOLMAN, stand aside in FOMC weeks)."""
from __future__ import annotations

import os
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
os.chdir(ROOT)
plt.rcParams["font.family"] = "Leelawadee UI"


def dd(x):
    eq = 1000 + np.cumsum(x)
    return float((eq - np.maximum.accumulate(np.r_[1000.0, eq])[1:]).min())


def main() -> int:
    df = pd.read_csv("data/wpwb_backtest_weekly.csv", parse_dates=["week_start"])
    fomc = df.events.fillna("").str.split().apply(lambda xs: "FOMC" in xs)
    df["R2_usd"] = np.where(fomc, 0.0, df.VOLMAN_usd)
    print(f"{'':22s}{'net $':>9s}{'max DD $':>10s}{'worst wk':>10s}{'losing wks':>12s}{'traded':>8s}")
    for col, lab in (("LONG_usd", "LONG"), ("VOLMAN_usd", "VOLMAN"), ("R2_usd", "VOLMAN + skip FOMC")):
        x = df[col]; tr = x != 0
        print(f"{lab:22s}{x.sum():+9.0f}{dd(x):+10.0f}{x.min():+10.0f}{int((x < 0).sum()):12d}{int(tr.sum()):8d}")
    q = df.assign(q=df.week_start.dt.to_period("Q").astype(str)).groupby("q")[
        ["LONG_usd", "VOLMAN_usd", "R2_usd"]].sum().round(0)
    print("\nby quarter:"); print(q.to_string())
    print("\nFOMC weeks that were skipped (what R2 avoided / gave up):")
    f = df[fomc][["week_start", "gold_move_usd", "dxy_pct", "VOLMAN_usd"]]
    print(f.to_string(index=False))
    print(f"  skipped total: {f.VOLMAN_usd.sum():+.0f}$ (losses avoided {f.VOLMAN_usd[f.VOLMAN_usd < 0].sum():+.0f}$, "
          f"gains given up {f.VOLMAN_usd[f.VOLMAN_usd > 0].sum():+.0f}$)")
    print("\n8 worst weeks still left under R2:")
    cols = ["week_start", "gold_move_usd", "gold_move_pct", "dxy_pct", "sigma_daily_pct_at_rebuild",
            "volman_size", "events", "R2_usd"]
    print(df.nsmallest(8, "R2_usd")[cols].to_string(index=False))

    fig, ax = plt.subplots(figsize=(13, 6))
    for col, lab, c in (("LONG_usd", "LONG (ถือทองทั้งสัปดาห์)", "#888888"),
                        ("VOLMAN_usd", "VOLMAN (ปรับขนาดตามความผันผวน)", "#1f77b4"),
                        ("R2_usd", "VOLMAN + ไม่ถือในสัปดาห์ FOMC", "#2ca02c")):
        ax.plot(df.week_start, 1000 + df[col].cumsum(), label=lab, color=c, lw=2.2)
    for d in df.week_start[fomc]:
        ax.axvline(d + pd.Timedelta(days=3), color="purple", alpha=0.18, lw=3)
    ax.axhline(1000, color="k", lw=0.8, ls=":")
    ax.set_ylabel(r"ทุน \$ (เริ่ม \$1,000, 0.01 lot)")
    ax.set_title("WPWB 2024-01 ถึง 2026-09: ผลของการไม่ถือไม้ในสัปดาห์ FOMC (เส้นม่วง = สัปดาห์ FOMC)")
    ax.legend(loc="upper left")
    fig.tight_layout()
    fig.savefig("data/wpwb_r2_equity.png", dpi=120)
    df.to_csv("data/wpwb_backtest_weekly_r2.csv", index=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
