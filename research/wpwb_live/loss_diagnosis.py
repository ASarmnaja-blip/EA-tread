"""EXPLORATORY loss diagnosis for WPWB (hindsight view, labelled as such).

For every week, the traces that were readable BEFORE it started (at the
Weekend Rebuild) and the intraweek path. Question: which traces separate
losing weeks from winning weeks, and does that hold across eras (2021-07..
2023-12 vs 2024-01..2026-09)? Findings here only nominate rules; rules are
then frozen and tested separately against random week-skipping.
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
sys.path.insert(0, str(ROOT / "research" / "wpwb_search"))
sys.path.insert(0, str(ROOT / "research" / "wpwb_live"))
sys.path.insert(0, str(ROOT / "research" / "pilot"))
import cftc_legacy  # noqa: E402
import common as C  # noqa: E402
from backtest_report import TIER1, load_events  # noqa: E402
from run_live_hod import combined_bars  # noqa: E402
from run_round3 import sigma_at  # noqa: E402


def build(m):
    last = int(m.t[-1]) + C.HOUR
    cuts = np.array([c for c in m.cuts if c + C.WEEK <= last])
    dxy = np.load("data/fresh/DXY_M5.npz")
    cf = cftc_legacy.load()
    cf["avail_s"] = ((cf.available - pd.Timestamp("1970-01-01", tz="UTC"))
                     // pd.Timedelta(seconds=1)).astype("int64")
    ev = load_events()
    wk_close = {}
    for c in cuts:
        kb = m.last_bar_before(int(c))
        wk_close[int(c)] = m.c[kb] if kb >= 0 else np.nan
    rows = []
    for cut in cuts:
        cut = int(cut)
        lo, hi = m.week_bars(cut)
        if hi <= lo or cut - 26 * C.WEEK < cuts[0]:
            continue
        sig = sigma_at(m, cut, 13); sig4 = sigma_at(m, cut - 4 * C.WEEK, 13)
        closes = np.array([wk_close.get(cut - j * C.WEEK, np.nan) for j in range(0, 27)])
        px = closes[0]
        wsig = sig * np.sqrt(5) if np.isfinite(sig) else np.nan
        sma20 = np.nanmean(closes[:20])
        a = np.searchsorted(dxy["t"], cut - 4 * C.WEEK); b = np.searchsorted(dxy["t"], cut) - 1
        dxy4 = (dxy["c"][b] / dxy["c"][a] - 1) * 100 if (b > a and a > 0) else np.nan
        cfr = cf[cf.avail_s < cut + 86400]
        cf_rank = float(cfr.pct_rank.iloc[-1]) if len(cfr) else np.nan
        cf_chg = float(cfr.chg.iloc[-1]) if len(cfr) else np.nan
        nxt = ev[(ev.ts >= cut) & (ev.ts < cut + C.WEEK)]
        # outcome and intraweek path (Bid path, long)
        entry = m.o[lo] + m.sp_in[lo]
        lows = m.l[lo:hi]; closes_w = m.c[lo:hi]
        mae = (lows.min() - entry) / entry / wsig if np.isfinite(wsig) else np.nan
        # Wednesday check: return from week open to the last bar before Wed 21:00 UTC
        wed = cut + 5 * 86400 - 75 * 60                     # Fri 22:15 + 5d - 1h15 = Wed 21:00
        assert pd.to_datetime(wed, unit="s").weekday() == 2
        kw = int(np.searchsorted(m.t, wed)) - 1
        ret_to_wed = (m.c[kw] / m.o[lo] - 1) if lo < kw < hi else np.nan
        ret_rest = (m.c[hi - 1] / m.c[kw] - 1) if lo < kw < hi - 1 else np.nan
        long_bp = float(m.pnl_bp([lo], [hi - 1], [1], 1.0)[0])
        rows.append(dict(
            cut=cut, date=pd.to_datetime(cut, unit="s").date(), era="new" if cut >= C.DEV_END else "old",
            long_bp=long_bp, long_usd=long_bp / 1e4 * m.o[lo],
            sigma=sig, vol_trend=sig / sig4 if (np.isfinite(sig4) and sig4 > 0) else np.nan,
            ret_1w=np.log(closes[0] / closes[1]), ret_4w=np.log(closes[0] / closes[4]),
            ret_13w=np.log(closes[0] / closes[13]),
            ext_z=(px - sma20) / (px * wsig) if np.isfinite(wsig) else np.nan,
            off_high=px / np.nanmax(closes[:26]) - 1,
            dxy_4w=dxy4, cftc_rank=cf_rank, cftc_chg=cf_chg,
            fomc_next=int((nxt.event == "Fed Interest Rate Decision").any()),
            tier1_next=int(len(nxt)),
            eff20=m.efficiency_at(cut),
            mae_wsig=mae, ret_to_wed=ret_to_wed, ret_thu_fri=ret_rest))
    return pd.DataFrame(rows)


def main() -> int:
    m = C.Market(combined_bars())
    df = build(m)
    df.to_csv("data/wpwb_loss_diagnosis.csv", index=False)
    feats = ["sigma", "vol_trend", "ret_1w", "ret_4w", "ret_13w", "ext_z", "off_high",
             "dxy_4w", "cftc_rank", "cftc_chg", "fomc_next", "tier1_next", "eff20"]
    print(f"weeks: old era {int((df.era == 'old').sum())}, new era {int((df.era == 'new').sum())}\n")
    print("Spearman rho of each pre-week trace with the NEXT week's long P&L (bp):")
    print(f"{'trace':12s}{'old era':>18s}{'new era':>18s}   losing vs winning weeks (new era, median)")
    for f in feats:
        line = f"{f:12s}"
        for e in ("old", "new"):
            x = df[df.era == e][[f, "long_bp"]].dropna()
            if len(x) < 30 or x[f].nunique() < 3:
                line += f"{'n/a':>18s}"
                continue
            r, p = stats.spearmanr(x[f], x.long_bp)
            line += f"{r:+10.2f} (p={p:.2f})"
        n = df[df.era == "new"]
        lo_med = n[n.long_bp < 0][f].median(); hi_med = n[n.long_bp > 0][f].median()
        print(f"{line}   {lo_med:+.3f} vs {hi_med:+.3f}")

    n = df[df.era == "new"]
    print("\nFOMC weeks, both eras:")
    for e in ("old", "new"):
        x = df[df.era == e]
        a, b = x[x.fomc_next == 1].long_bp, x[x.fomc_next == 0].long_bp
        print(f"  {e}: FOMC weeks n={len(a)} mean {a.mean():+.0f} bp vs {b.mean():+.0f} bp other "
              f"(Mann-Whitney p={stats.mannwhitneyu(a, b).pvalue:.2f})")

    print("\nintraweek: does Mon-Wed predict Thu-Fri? (Spearman)")
    for e in ("old", "new"):
        x = df[df.era == e][["ret_to_wed", "ret_thu_fri"]].dropna()
        r, p = stats.spearmanr(x.ret_to_wed, x.ret_thu_fri)
        print(f"  {e}: rho {r:+.2f} (p={p:.2f}), n={len(x)}")

    print("\nintraweek stop-loss view (new era): a stop at k x weekly sigma below entry")
    for k in (0.5, 0.75, 1.0, 1.5):
        hit = n.mae_wsig <= -k
        print(f"  k={k:4.2f}: hit in {hit.mean():.0%} of weeks; of those, finished the week "
              f"ABOVE the stop level in {(n[hit].long_bp / 1e4 > -k * n[hit].sigma * np.sqrt(5)).mean():.0%} "
              f"(would have been stopped out needlessly); losing weeks hit: "
              f"{(hit & (n.long_bp < 0)).sum()}/{(n.long_bp < 0).sum()}")

    print("\n15 worst new-era weeks with their pre-week traces:")
    cols = ["date", "long_usd", "sigma", "vol_trend", "ret_4w", "ext_z", "dxy_4w",
            "cftc_rank", "fomc_next", "mae_wsig"]
    print(n.nsmallest(15, "long_bp")[cols].round(3).to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
