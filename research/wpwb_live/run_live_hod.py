"""Single run of docs/WPWB_LIVE_PREREG.md: six frozen hour-of-day tools,
weekly walk-forward over the current era (2024-01 .. last complete week)."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
os.chdir(ROOT)
sys.path.insert(0, str(ROOT / "research" / "wpwb_search"))
import approaches as AP  # noqa: E402
import approaches2 as AP2  # noqa: E402
import common as C  # noqa: E402
import data as D  # noqa: E402
import evaluate as EV  # noqa: E402
import historical_regime_walkforward as hist  # noqa: E402

K = 6
P_MAX = 0.025 / K


def combined_bars():
    assert hist.CANONICAL_M5.exists()
    b5 = hist.load_history()
    f = np.load("data/fresh/XAUUSD_M5.npz")
    k = f["t"] > b5.t[-1]
    return D.Bars(np.r_[b5.t, f["t"][k]], np.r_[b5.o, f["o"][k]], np.r_[b5.h, f["h"][k]],
                  np.r_[b5.l, f["l"][k]], np.r_[b5.c, f["c"][k]], np.r_[b5.v, f["v"][k]],
                  300, "XAUUSD", np.r_[b5.sp, f["sp"][k]])


def runner(fam, m, cut, params):
    return AP.hod_week(m, cut, **params) if fam == "B" else AP2.hodm_week(m, cut, **params)


def main() -> int:
    b5 = combined_bars()
    m = C.Market(b5)
    last = int(m.t[-1]) + C.HOUR
    cuts = np.array([c for c in m.cuts if c >= C.DEV_END and c + C.WEEK <= last])
    print(f"current-era weeks: {len(cuts)} "
          f"({pd.to_datetime(cuts[0], unit='s').date()} .. "
          f"{pd.to_datetime(cuts[-1] + C.WEEK, unit='s').date()}); data to "
          f"{pd.to_datetime(m.t[-1], unit='s')}")
    eff = np.array([m.efficiency_at(int(c)) for c in cuts])
    lo_half = eff <= np.nanmedian(eff)
    years = pd.to_datetime(cuts, unit="s").year.to_numpy()

    variants = [("B", f"HOD W={W} T={T}", dict(W=W, T=T)) for W in (26, 52) for T in (2.0, 3.0)]
    variants += [("F", f"HODM W=52 T={T}", dict(W=52, T=T)) for T in (2.0, 3.0)]
    rows, yearly = [], []
    for fam, name, params in variants:
        sig = (lambda f, mm, c, p: AP.hod_tool(mm, c, p["W"], p["T"]))
        bad = EV.audit_lookahead(fam, params, m, cuts, sig=sig)
        s15 = EV.weekly_series(fam, params, m, cuts, 1.5, {}, runner=runner)
        s10 = EV.weekly_series(fam, params, m, cuts, 1.0, {}, runner=runner)
        r = EV.summarize("B", s15)
        halves = (float(s10["strat"][lo_half].mean()), float(s10["strat"][~lo_half].mean()))
        r.update(variant=name, audit_fail=len(bad), mean_week_bp_base=float(s10["strat"].mean()),
                 chop_half_base=halves[0], trend_half_base=halves[1])
        r["PASS"] = bool(len(bad) == 0 and r["mean_week_bp"] > 0 and r["mean_week_bp_base"] > 0
                         and r["max_p"] < P_MAX and r["active"] >= 0.5
                         and min(halves) >= 0)
        rows.append(r)
        for y in np.unique(years):
            mk = years == y
            yearly.append(dict(variant=name, year=int(y), weeks=int(mk.sum()),
                               base=float(s10["strat"][mk].mean()),
                               stress=float(s15["strat"][mk].mean()),
                               vs_rtime=float((s15["strat"] - s15["rtime"])[mk].mean()),
                               vs_long=float((s15["strat"] - s15["long"])[mk].mean())))
        print(f"{name:18s} audit_fail={len(bad)} active={r['active']:.2f} trades={r['trades']:5d} "
              f"wk_bp base={r['mean_week_bp_base']:+7.2f} 1.5x={r['mean_week_bp']:+7.2f} | "
              f"t long={r['vs_long_t']:+5.2f} rdir={r['vs_rdir_t']:+5.2f} rtime={r['vs_rtime_t']:+5.2f} "
              f"max_p={r['max_p']:.4f} | halves chop={halves[0]:+6.2f} trend={halves[1]:+6.2f} "
              f"{'PASS' if r['PASS'] else 'fail'}")
    pd.DataFrame(rows).to_csv("data/wpwb_live_hod.csv", index=False)
    yd = pd.DataFrame(yearly)
    yd.to_csv("data/wpwb_live_hod_yearly.csv", index=False)
    print("\nby year (bp/week; context only, not part of the pass rule):")
    print(yd.pivot(index="variant", columns="year", values="stress").round(1).to_string())
    print("\nstrategy minus RTIME by year (1.5x):")
    print(yd.pivot(index="variant", columns="year", values="vs_rtime").round(1).to_string())
    print(f"\nthreshold p < {P_MAX:.5f}; passes: {sum(r['PASS'] for r in rows)} of {K}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
