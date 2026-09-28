"""DEV phase of the WPWB edge search. Never evaluates a HOLDOUT week.

Order: (1) pipeline sanity (oracle must pass, coin-flip must fail, a leaky
tool must be caught by the audit); (2) look-ahead audit per variant;
(3) all 20 variants on DEV; (4) eligibility per prereg s.6 + amendment 1.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import approaches as AP  # noqa: E402
import common as C  # noqa: E402
import evaluate as EV  # noqa: E402
import historical_regime_walkforward as hist  # noqa: E402

FLOOR = {"A": 0.5, "B": 0.5, "C": 0.5, "D": 0.5, "D-ungated": 0.25, "E": 0.25}


def dev_cuts(m):
    cuts = np.array([c for c in m.cuts if c >= C.DEV_START and c + C.WEEK <= C.DEV_END])
    assert cuts.max() + C.WEEK <= C.DEV_END, "DEV touched HOLDOUT"
    return cuts


def pipeline_sanity(m, cuts):
    """The machinery must find a planted edge and must not find a fake one."""
    orig_run, orig_tool = AP.run_week, AP.tool_signature
    rng = np.random.default_rng(3)
    coin = {int(c): int(rng.choice([-1, 1])) for c in cuts}

    def oracle_week(fam, mm, cut, params, eff):
        lo, hi = mm.week_bars(cut)
        if hi <= lo:
            return [], []
        d = 1 if mm.c[hi - 1] > mm.o[lo] else -1
        if fam == "COIN":
            d = coin[cut]
        return [(lo, hi - 1, d)], []

    AP.run_week = oracle_week
    try:
        o = EV.summarize("A", EV.weekly_series("ORACLE", {}, m, cuts, 1.5, {}))
        n = EV.summarize("A", EV.weekly_series("COIN", {}, m, cuts, 1.5, {}))
    finally:
        AP.run_week = orig_run

    def leaky_tool(fam, mm, cut, params, eff):
        lo, hi = mm.week_bars(cut)
        return int(np.sign(mm.c[hi - 1] - mm.o[lo])) if hi > lo else 0

    AP.tool_signature = leaky_tool
    try:
        caught = EV.audit_lookahead("A", {}, m, cuts)
    finally:
        AP.tool_signature = orig_tool
    ok = (o["max_p"] < C.DEV_P_MAX and n["max_p"] >= C.DEV_P_MAX and len(caught) > 0)
    print(f"pipeline sanity: oracle max_p={o['max_p']:.4f} (must be < {C.DEV_P_MAX}), "
          f"coin max_p={n['max_p']:.4f} (must be >= {C.DEV_P_MAX}), "
          f"leaky tool caught at {len(caught)}/25 cuts -> {'OK' if ok else 'FAILED'}")
    return ok


def load_canonical():
    """Pin cwd to the repo root and refuse anything but the frozen snapshot."""
    import os
    os.chdir(Path(__file__).resolve().parents[2])
    assert hist.CANONICAL_M5.exists(), "canonical snapshot missing - refusing to run"
    return C.Market(hist.load_history())


def main() -> int:
    m = load_canonical()
    cuts = dev_cuts(m)
    print(f"DEV weeks: {len(cuts)}  ({pd.to_datetime(cuts[0], unit='s').date()} .. "
          f"{pd.to_datetime(cuts[-1] + C.WEEK, unit='s').date()})\n")
    if not pipeline_sanity(m, cuts):
        print("ABORT: pipeline sanity failed")
        return 2

    eff_cache: dict = {}
    rows = []
    for fam, name, params in AP.variants():
        bad = EV.audit_lookahead(fam, params, m, cuts)
        s15 = EV.weekly_series(fam, params, m, cuts, 1.5, eff_cache)
        s10 = EV.weekly_series(fam, params, m, cuts, 1.0, eff_cache)
        r = EV.summarize(fam, s15)
        r.update(family=fam, variant=name, audit_fail=len(bad),
                 mean_week_bp_base=float(s10["strat"].mean()))
        r["eligible"] = bool(len(bad) == 0 and r["mean_week_bp"] > 0
                             and r["max_p"] < C.DEV_P_MAX
                             and r["active"] >= FLOOR[fam])
        rows.append(r)
        print(f"{name:32s} audit_fail={len(bad)} active={r['active']:.2f} "
              f"trades={r['trades']:5d} wk_bp(1.5x)={r['mean_week_bp']:+8.2f} "
              f"base={r['mean_week_bp_base']:+8.2f} min_t={r['min_t']:+6.2f} "
              f"max_p={r['max_p']:.4f} {'ELIGIBLE' if r['eligible'] else ''}")

    df = pd.DataFrame(rows)
    Path("data").mkdir(exist_ok=True)
    df.to_csv("data/wpwb_search_dev.csv", index=False)
    elig = df[df.eligible].sort_values("min_t", ascending=False)
    fin = elig.groupby("family", sort=False).head(1).head(3)
    print(f"\nvariants evaluated on DEV: {len(df)}; eligible: {len(elig)}; "
          f"finalists: {len(fin)}")
    for _, r in fin.iterrows():
        print(f"  FINALIST {r['variant']}  min_t={r['min_t']:+.2f} max_p={r['max_p']:.4f}")
    Path("data/wpwb_search_finalists.json").write_text(json.dumps(
        [dict(family=r["family"], variant=r["variant"]) for _, r in fin.iterrows()],
        indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
