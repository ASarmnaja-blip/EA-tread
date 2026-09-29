"""Historical replay of the Outlook shadow log (DEVELOPMENT, not evidence).
Re-runs the frozen OUTLOOK-V2.0 models week by week on 2003-2026 Dukascopy H1 +
the pinned GVZ file, writing one row per week in the shadow-log style plus the
realised outcome, and a chart. Every forecast uses only data before its cut, but
the model was chosen after seeing this history (Part 52), so the replay cannot
confirm anything; only the forward shadow log can."""
from __future__ import annotations

import math
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
import outlook_dev as O  # noqa: E402

OUT_CSV = ROOT / "data" / "wpwb_weekly" / "outlook_replay_2013_2026.csv"
OUT_PNG = ROOT / "data" / "wpwb_weekly" / "outlook_replay_2013_2026.png"
MODELS = ("B0", "HAR", "MVOL")


def main() -> int:
    os.chdir(ROOT)
    h, t, cuts, *_ = O.load()
    rv, F, mu, _ = O.run_models(h, t, cuts)
    ens = O.ensembles(rv, {m: mu[m] for m in ("B0", "HAR", "MVOL")})
    mk = O.med52(rv)
    lv = np.log(rv)
    date = pd.to_datetime(cuts, unit="s")
    rows = []
    for k in range(len(cuts)):
        if not all(ens[m][k] is not None for m in MODELS) or not np.isfinite(lv[k]) or not np.isfinite(mk[k]):
            continue
        prev = rv[k - 1] / mk[k - 1] if np.isfinite(mk[k - 1]) else np.nan
        cur = int(O.cls(np.array([prev]))[0]); real = int(O.cls(np.array([rv[k] / mk[k]]))[0])
        r = dict(week_start=date[k].strftime("%Y-%m-%d"), current_class=cur, realised_vol_bp=math.sqrt(rv[k]),
                 realised_class=real)
        lm = math.log(mk[k])
        for m in MODELS:
            e = ens[m][k]
            p_hi = float(np.mean(e >= lm + math.log(1.5)))
            r.update({f"{m}_vol_bp": math.sqrt(np.mean(np.exp(e))),
                      f"{m}_lo10_bp": math.exp(np.quantile(e, .1) / 2), f"{m}_hi90_bp": math.exp(np.quantile(e, .9) / 2),
                      f"{m}_p_high": p_hi, f"{m}_crps": O.crps(e, lv[k])})
        rows.append(r)
    R = pd.DataFrame(rows)
    R.to_csv(OUT_CSV, index=False)
    R["d"] = pd.to_datetime(R.week_start)
    print(f"{len(R)} weeks {R.week_start.iloc[0]}..{R.week_start.iloc[-1]} -> {OUT_CSV.name}")
    for y, g in R.groupby(R.d.dt.year):
        print(f"  {y}: weeks {len(g):3d}  mean realised vol {g.realised_vol_bp.mean():5.0f} bp  "
              f"CRPS B0 {g.B0_crps.mean():.3f}  MVOL {g.MVOL_crps.mean():.3f}  "
              f"MVOL better in {100 * (g.MVOL_crps < g.B0_crps).mean():3.0f}% of weeks")
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(3, 1, figsize=(13, 10), sharex=True, gridspec_kw=dict(height_ratios=[3, 1.2, 1.5]))
    ax[0].fill_between(R.d, R.MVOL_lo10_bp, R.MVOL_hi90_bp, color="tab:blue", alpha=.15, label="MVOL 10-90% range")
    ax[0].plot(R.d, R.realised_vol_bp, color="black", lw=.8, label="realised weekly vol")
    ax[0].plot(R.d, R.B0_vol_bp, color="tab:orange", lw=1, label="B0 = EWMA (used today)")
    ax[0].plot(R.d, R.MVOL_vol_bp, color="tab:blue", lw=1, label="MVOL = HAR + GVZ")
    ax[0].set_ylabel("bp per week"); ax[0].legend(loc="upper left", fontsize=8)
    ax[0].set_title("WPWB Outlook replay 2013-2026 (DEVELOPMENT, forecasts made before each week; not evidence)")
    ax[1].plot(R.d, R.MVOL_p_high, color="tab:blue", lw=.8, label="MVOL P(next week HIGH/EXTREME)")
    hi = R.realised_class >= 2
    ax[1].scatter(R.d[hi], np.full(hi.sum(), 1.02), s=4, color="red", label="week was HIGH/EXTREME")
    ax[1].set_ylim(0, 1.08); ax[1].legend(loc="upper left", fontsize=8)
    ax[2].plot(R.d, (R.B0_crps - R.MVOL_crps).cumsum(), color="tab:green")
    ax[2].axhline(0, color="grey", lw=.5)
    ax[2].axvspan(pd.Timestamp("2019-01-01"), pd.Timestamp("2021-07-01"), color="grey", alpha=.15)
    ax[2].set_ylabel("cumulative CRPS gain\nMVOL over B0"); ax[2].text(pd.Timestamp("2019-02-01"), ax[2].get_ylim()[1] * .8, "pseudo-holdout", fontsize=8)
    fig.tight_layout(); fig.savefig(OUT_PNG, dpi=110)
    print(f"chart -> {OUT_PNG.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
