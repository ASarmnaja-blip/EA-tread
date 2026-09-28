"""Read-only adversarial checks for the WPWB risk report and DD backtests.

This script deliberately writes no artifacts.  It checks the historical
reference-risk look-ahead, minimum-lot quantisation, direction-path
assumptions, continuous-versus-rounded sizing, and Friday-cut readiness.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
WEEKLY = HERE.parent
sys.path.insert(0, str(WEEKLY))

import backtest_compound as BC  # noqa: E402
import bars as BR  # noqa: E402
import vol as V  # noqa: E402


def continuous_sim(bp, mae, entry, scale, base):
    """BC.simulate without the 0.01-lot floor/round-down discontinuities."""
    n_p, n_w = bp.shape
    eq = np.full(n_p, BC.ACCOUNT)
    out = np.empty((n_p, n_w))
    for w in range(n_w):
        lots = base * eq / BC.ACCOUNT * scale[w]
        usd_bp = entry[w] * BC.OZ / 1e4
        blow = eq + lots * usd_bp * mae[:, w] <= 0
        eq = np.where(blow, 0.0, eq + lots * usd_bp * bp[:, w])
        out[:, w] = eq
    return out


def direction_paths(rng, n_paths, n_weeks, same_probability=0.5, p_long=0.5):
    """Stationary binary direction paths; 0.5 persistence is iid."""
    if same_probability == 0.5:
        return np.where(rng.random((n_paths, n_weeks)) < p_long, 1, -1)
    d = np.empty((n_paths, n_weeks), dtype=np.int8)
    d[:, 0] = np.where(rng.random(n_paths) < p_long, 1, -1)
    for w in range(1, n_weeks):
        keep = rng.random(n_paths) < same_probability
        # Symmetric transition keeps a 50/50 stationary distribution.
        d[:, w] = np.where(keep, d[:, w - 1], -d[:, w - 1])
    return d


def dd_row(label, eq):
    dd = BC.dd_pct(eq)
    return (label, float(np.median(dd)), float(np.percentile(dd, 5)),
            float(np.mean(dd <= -45)), float(np.mean(eq[:, -1] == 0)))


def simulate_directions(df, scale, base, d, continuous=False):
    long_bp = df.bp_l.to_numpy()
    short_bp = df.bp_s.to_numpy()
    long_mae = df.mae_l.to_numpy()
    short_mae = df.mae_s.to_numpy()
    bp = np.where(d > 0, long_bp, short_bp)
    mae = np.where(d > 0, long_mae, short_mae)
    entry = df.entry.to_numpy()
    if continuous:
        return continuous_sim(bp, mae, entry, scale, base)
    return BC.simulate(bp, mae, entry, scale, base)[0]


def reference_scales():
    """Return full-sample and pre-backtest B_REF scales for scored weeks."""
    m = BR.market(BR.load_bars(frozen=False))
    cuts = BR.cuts_between(m, BR.FIRST_CUT, 10**12)
    rv, _, _, _ = V.weekly_rv(m.t, m.c, m.h, m.l, cuts)
    f = V.ewma_forecast(rv)
    scored = cuts >= BC.FIRST
    pre = rv[cuts < BC.FIRST]
    pre52 = float(np.median(pre[-52:]))
    full = np.array([V.vol_scale(x, V.B_REF) for x in f[scored]])
    causal = np.array([V.vol_scale(x, pre52) for x in f[scored]])
    return pre52, full, causal


def cut_readiness():
    """Gap from the last available H1 close to each Friday 22:15 cut."""
    m = BR.market(BR.load_bars(frozen=True))
    cuts = m.cuts[(m.cuts >= BR.FIRST_CUT) & (m.cuts <= BR.FREEZE_LAST_CUT + BR.WEEK)]
    gaps = []
    for cut in cuts:
        i = np.searchsorted(m.t, cut) - 1
        gaps.append(int(cut - (m.t[i] + 3600)))
    return np.asarray(gaps)


def main():
    df = BC.weeks()
    n = len(df)
    scale = df.s.to_numpy()
    pre52, full_scale, causal_scale = reference_scales()
    assert len(full_scale) == n and np.allclose(full_scale, scale)

    print("FIXED-LOT BACKTEST REPRODUCTION")
    fixed_rows = []
    for side in ("l", "s"):
        for mode in ("fixed", "scaled"):
            lots = (np.full(n, .10) if mode == "fixed" else
                    np.floor(.10 * scale / BC.STEP + 1e-9) * BC.STEP)
            pnl = df[f"bp_{side}"].to_numpy() * (df.entry.to_numpy() * BC.OZ / 1e4) * lots
            eq = BC.ACCOUNT + np.cumsum(pnl)
            peak = np.maximum.accumulate(np.r_[BC.ACCOUNT, eq])[1:]
            fixed_rows.append((side, mode, pnl.sum(), (eq - peak).min(), pnl.min(),
                               pnl.std(ddof=1), eq[-1]))
    print(pd.DataFrame(fixed_rows, columns=["side", "mode", "total $", "max DD $",
                                            "worst week $", "weekly SD $", "final equity $"])
          .round(1).to_string(index=False))
    print("Negative final equity is allowed by this fixed-lot calculation; it is an "
          "exposure stress, not a feasible account path.")

    print("\nREFERENCE RISK UNIT")
    print(f"published full-sample B_REF={V.B_REF:.1f} bp^2")
    print(f"median of 52 weeks known before backtest={pre52:.1f} bp^2")
    print(f"mean scale full-sample={full_scale.mean():.3f}; pre-period={causal_scale.mean():.3f}")
    print(f"weeks with changed rounded 0.03-lot order="
          f"{np.mean(np.floor(.03*full_scale/.01) != np.floor(.03*causal_scale/.01)):.1%}")

    print("\nLOT QUANTISATION AT $10,000, BASE 0.03")
    intended = .03 * scale
    rounded = np.floor(intended / BC.STEP + 1e-9) * BC.STEP
    q = pd.DataFrame({"scale": scale, "intended": intended, "rounded": rounded})
    print(q.groupby("rounded").agg(weeks=("scale", "size"),
                                    min_intended=("intended", "min"),
                                    max_intended=("intended", "max")).to_string())
    print(f"mean rounded/intended={np.mean(rounded/intended):.3f}; "
          f"min={np.min(rounded/intended):.3f}")
    threshold = BC.STEP * BC.ACCOUNT / (.03 * scale)
    print(f"equity below which trading silently stops: median ${np.median(threshold):.0f}, "
          f"range ${threshold.min():.0f}-${threshold.max():.0f}")

    rng = np.random.default_rng(20260928)
    rows = []
    iid = direction_paths(rng, 20_000, n)
    rows.append(dd_row("iid, rounded", simulate_directions(df, scale, .03, iid)))
    rows.append(dd_row("iid, continuous lots", simulate_directions(df, scale, .03, iid, True)))
    for persistence in (0.60, 0.75, 0.90):
        d = direction_paths(rng, 20_000, n, persistence)
        rows.append(dd_row(f"Markov P(same)={persistence:.2f}",
                           simulate_directions(df, scale, .03, d)))
    for p_long in (0.25, 0.75):
        d = direction_paths(rng, 20_000, n, p_long=p_long)
        rows.append(dd_row(f"iid P(long)={p_long:.2f}",
                           simulate_directions(df, scale, .03, d)))
    out = pd.DataFrame(rows, columns=["path design", "median DD %", "worst-5% DD %",
                                      "P(DD>=45%)", "P(model wipeout)"])
    print("\nDIRECTION-DESIGN SENSITIVITY, BASE 0.03")
    print(out.round(4).to_string(index=False))

    # Same iid draws under the historical full-sample reference versus a
    # reference available before the reported 2022-2026 backtest began.
    e_full = simulate_directions(df, full_scale, .03, iid)
    e_pre = simulate_directions(df, causal_scale, .03, iid)
    print("\nB_REF SENSITIVITY ON SAME IID PATHS")
    print(pd.DataFrame([dd_row("full-sample B_REF", e_full),
                        dd_row("pre-period B_REF", e_pre)],
                       columns=out.columns).round(4).to_string(index=False))

    gaps = cut_readiness()
    print("\nFRIDAY CUT READINESS")
    print(f"cuts checked={len(gaps)}; last H1 close is before cut on {(gaps > 0).mean():.1%}; "
          f"median gap={np.median(gaps)/60:.0f} min; max gap={gaps.max()/3600:.1f} h")
    print("cuts_between/main currently require last_H1_start+1h >= cut; a Saturday run "
          "fails when the scheduled Friday close precedes 22:15 UTC.")


if __name__ == "__main__":
    main()
