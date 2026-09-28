"""Readable trace or repeated luck? (user question, 2026-09-28)

1. Pre-week traces: do winning and losing weeks differ BEFORE they start?
2. In-week traces: what actually happened in winning vs losing weeks?
3. FOMC rule: sign counts, leave-best/worst-week-out, pooled permutation,
   and the selection penalty for having looked at ~15 candidate traces.
4. VOLMAN: leave-top-weeks-out.
5. How good does the best of 15 random rules look? (the 'lucky streak' base rate)
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

ROOT = Path(__file__).resolve().parents[2]
os.chdir(ROOT)

PRE = ["sigma", "vol_trend", "ret_1w", "ret_4w", "ret_13w", "ext_z", "off_high",
       "dxy_4w", "cftc_rank", "cftc_chg", "tier1_next", "eff20"]
TH = {"sigma": "ความผันผวน", "vol_trend": "ความผันผวนเพิ่ม/ลด", "ret_1w": "ทอง 1 สัปดาห์ก่อน",
      "ret_4w": "ทอง 4 สัปดาห์ก่อน", "ret_13w": "ทอง 13 สัปดาห์ก่อน", "ext_z": "ห่างจากค่าเฉลี่ย 20 สัปดาห์",
      "off_high": "ห่างจากจุดสูงสุด 26 สัปดาห์", "dxy_4w": "DXY 4 สัปดาห์ก่อน",
      "cftc_rank": "CFTC สถานะกองทุน (อันดับ)", "cftc_chg": "CFTC เปลี่ยนแปลง",
      "tier1_next": "จำนวนข่าวใหญ่สัปดาห์หน้า", "eff20": "ความเป็นเทรนด์ 20 วัน"}


def maxdd(x):
    eq = np.cumsum(x)
    return float((eq - np.maximum.accumulate(np.r_[0.0, eq])[1:]).min())


def main() -> int:
    d = pd.read_csv("data/wpwb_loss_diagnosis.csv")
    d = d[d.cut >= 1640995200].copy()                    # calendar starts 2022-01-01
    w = pd.read_csv("data/wpwb_backtest_weekly.csv")[["cut", "dxy_pct", "week_range_usd",
                                                     "events", "VOLMAN_usd", "LONG_usd"]]
    d = d.merge(w, on="cut", how="left")
    d["win"] = d.long_bp > 0
    rng = np.random.default_rng(7)

    print("== 1. BEFORE the week (readable at the Weekend Rebuild): winning vs losing weeks")
    print(f"   weeks {len(d)} (2022-01..2026-09); winning {int(d.win.sum())}, losing {int((~d.win).sum())}")
    sig = 0
    for f in PRE:
        x = d[[f, "win"]].dropna()
        a, b = x[x.win][f], x[~x.win][f]
        p = stats.mannwhitneyu(a, b).pvalue
        sig += p < 0.05
        print(f"   {TH[f]:32s} win median {a.median():+9.3f} | lose median {b.median():+9.3f} | p={p:.2f}")
    print(f"   -> {sig} of {len(PRE)} traces differ at p<0.05; expected by pure chance: {0.05 * len(PRE):.1f}")

    n = d[d.era == "new"]
    print("\n== 2. DURING the week (visible only as it happens), 2024-01..2026-09")
    for lab, mk in (("winning weeks", n.win), ("losing weeks", ~n.win)):
        x = n[mk]
        print(f"   {lab:14s} n={len(x):3d}  DXY same week median {x.dxy_pct.median():+.2f}%  "
              f"DXY up in {(x.dxy_pct > 0).mean():.0%}  gold range median ${x.week_range_usd.median():.0f}")
    r, p = stats.spearmanr(n.dxy_pct, n.long_bp)
    print(f"   same-week DXY vs gold: rho {r:+.2f} (p={p:.4f}) - strong, but only knowable after the fact")

    print("\n== 3. FOMC rule: readable trace or a few lucky weeks?")
    fom = d.fomc_next == 1
    for era in ("old", "new"):
        x = d[d.era == era]; f = x.fomc_next == 1
        print(f"   {era}: FOMC weeks {int(f.sum())}, losing {int((~x[f].win).sum())} "
              f"({(~x[f].win).mean():.0%}) vs other weeks losing {(~x[~f].win).mean():.0%}; "
              f"mean {x[f].long_bp.mean():+.0f} bp vs {x[~f].long_bp.mean():+.0f} bp; "
              f"median {x[f].long_bp.median():+.0f} vs {x[~f].long_bp.median():+.0f}")
    obs = d[fom].long_bp.mean() - d[~fom].long_bp.mean()
    perm = []
    for _ in range(20000):
        lab = np.zeros(len(d), bool)
        for era in ("old", "new"):
            idx = np.flatnonzero(d.era.to_numpy() == era)
            k = int(d.fomc_next.to_numpy()[idx].sum())
            lab[rng.choice(idx, k, replace=False)] = True
        perm.append(d.long_bp[lab].mean() - d.long_bp[~lab].mean())
    p_pool = float((np.array(perm) <= obs).mean())
    print(f"   pooled 2022-2026: FOMC minus other = {obs:+.0f} bp/week; permutation p = {p_pool:.3f}")
    print(f"   selection penalty: ~15 candidate traces examined -> adjusted p ~ "
          f"{min(1, 15 * p_pool):.2f} (Bonferroni)")
    worst = d[fom].long_bp.idxmin()
    d2 = d.drop(index=worst)
    f2 = d2.fomc_next == 1
    print(f"   drop the single worst FOMC week ({d.loc[worst, 'date']}, {d.loc[worst, 'long_bp']:+.0f} bp): "
          f"FOMC minus other = {d2[f2].long_bp.mean() - d2[~f2].long_bp.mean():+.0f} bp; "
          f"Mann-Whitney p = {stats.mannwhitneyu(d2[f2].long_bp, d2[~f2].long_bp).pvalue:.2f}")
    # gain of the skip rule on VOLMAN $ (new era) without that week, vs random skipping
    ne = n.reset_index(drop=True)
    v = ne.VOLMAN_usd.to_numpy(); fm = (ne.fomc_next == 1).to_numpy()
    keep = ne.date.astype(str) != "2026-03-13"
    v2, fm2 = v[keep], fm[keep]
    gain = -v2[fm2].sum()
    rs = [-v2[rng.choice(len(v2), fm2.sum(), replace=False)].sum() for _ in range(20000)]
    print(f"   new era WITHOUT 2026-03-13: skip-FOMC gain ${gain:+.0f}; beats random skipping in "
          f"{(np.array(rs) < gain).mean():.0%} of draws (was 96% with it)")

    print("\n== 4. VOLMAN: how many weeks carry its edge over plain LONG?")
    ex = (ne.VOLMAN_usd - ne.LONG_usd * (ne.VOLMAN_usd.abs().sum() / ne.LONG_usd.abs().sum())).to_numpy()
    raw = (ne.VOLMAN_usd - ne.LONG_usd).to_numpy()
    order = np.argsort(-raw)
    print(f"   VOLMAN minus LONG total ${raw.sum():+.0f}; best 1 week ${raw[order[0]]:+.0f}, "
          f"best 3 ${raw[order[:3]].sum():+.0f}; without the best 3 weeks: ${raw[order[3:]].sum():+.0f}")

    print("\n== 5. Base rate of a 'lucky streak': best of 15 RANDOM skip rules (22 weeks each)")
    L = ne.VOLMAN_usd.to_numpy()
    best = []
    for _ in range(4000):
        gains = [-L[rng.choice(len(L), 22, replace=False)].sum() for _ in range(15)]
        best.append(max(gains))
    best = np.array(best)
    print(f"   typical best-of-15 random gain ${np.median(best):+.0f}; skip-FOMC gain $377 is beaten by the "
          f"best random rule in {(best >= 377).mean():.0%} of trials")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
