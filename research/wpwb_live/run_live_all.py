"""WPWB-live Amendment 1: the other 34 frozen tools, once, on the current era.
Bonferroni over all 40 tools (0.025/40)."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
os.chdir(ROOT)
sys.path.insert(0, str(ROOT / "research" / "wpwb_search"))
sys.path.insert(0, str(ROOT / "research" / "wpwb_live"))
import approaches as AP  # noqa: E402
import approaches2 as AP2  # noqa: E402
import common as C  # noqa: E402
import evaluate as EV  # noqa: E402
from run_dev import FLOOR as FLOOR1  # noqa: E402
from run_live_hod import combined_bars  # noqa: E402
from run_round2 import meta_choose  # noqa: E402
from run_round3 import tsmi_week, volman_series  # noqa: E402

P_MAX = 0.025 / 40


def judge(name, fam, s15, s10, floor, controls, halves_mask, audit_fail):
    r = EV.summarize(fam, s15, controls=controls)
    ch = float(s10["strat"][halves_mask].mean()); tr = float(s10["strat"][~halves_mask].mean())
    r.update(variant=name, audit_fail=audit_fail, mean_week_bp_base=float(s10["strat"].mean()),
             chop_half_base=ch, trend_half_base=tr, floor=floor)
    r["PASS"] = bool(audit_fail == 0 and r["mean_week_bp"] > 0 and r["mean_week_bp_base"] > 0
                     and r["max_p"] < P_MAX and r["active"] >= floor and min(ch, tr) >= 0)
    ts = " ".join(f"{c}={r[f'vs_{c}_t']:+5.2f}" for c in controls)
    print(f"{name:28s} audit={audit_fail} act={r['active']:.2f} n={r['trades']:5d} "
          f"base={r['mean_week_bp_base']:+7.2f} 1.5x={r['mean_week_bp']:+7.2f} | t {ts} "
          f"| p={r['max_p']:.4f} | chop={ch:+6.2f} trend={tr:+6.2f} {'PASS' if r['PASS'] else 'fail'}",
          flush=True)
    return r


def main() -> int:
    m = C.Market(combined_bars())
    last = int(m.t[-1]) + C.HOUR
    all_cuts = np.array([c for c in m.cuts if c + C.WEEK <= last])
    cuts = all_cuts[all_cuts >= C.DEV_END]
    warm = all_cuts[(all_cuts < C.DEV_END)][-26:]
    print(f"current-era weeks {len(cuts)}; META warm-up weeks {len(warm)}")
    eff = np.array([m.efficiency_at(int(c)) for c in cuts])
    chop = eff <= np.nanmedian(eff)
    effc: dict = {}
    rows = []

    # round 1 (minus HOD, already run)
    for fam, name, params in AP.variants():
        if fam == "B":
            continue
        bad = len(EV.audit_lookahead(fam, params, m, cuts))
        s15 = EV.weekly_series(fam, params, m, cuts, 1.5, effc)
        s10 = EV.weekly_series(fam, params, m, cuts, 1.0, effc)
        rows.append(judge(name, fam, s15, s10, FLOOR1[fam], EV.controls_for(fam), chop, bad))

    # round 2: sessions, daily reversal
    for fam, name, params in AP2.variants2():
        if fam == "F":
            continue
        sig = lambda f, mm, c, p: AP2.tool_signature2(f, mm, c, p)  # noqa: E731
        bad = len(EV.audit_lookahead(fam, params, m, cuts, sig=sig))
        s15 = EV.weekly_series(fam, params, m, cuts, 1.5, effc, runner=AP2.run_week2)
        s10 = EV.weekly_series(fam, params, m, cuts, 1.0, effc, runner=AP2.run_week2)
        rows.append(judge(name, fam, s15, s10, 0.5, EV.controls_for(fam), chop, bad))

    # round 2: META over the round-1 menu, with 26 warm-up weeks for selection only
    menu = AP.variants()
    wc = np.r_[warm, cuts]
    base = np.vstack([EV.weekly_series(f, p, m, wc, 1.0, effc)["strat"] for f, _, p in menu])
    ser15 = [EV.weekly_series(f, p, m, wc, 1.5, effc) for f, _, p in menu]
    s10all = base
    nw = len(warm)
    for hl in (3, 8):
        n = len(cuts)
        s15 = dict(strat=np.zeros(n), long=np.zeros(n), rdir=np.zeros(n),
                   rtool=np.zeros(n), ntr=np.zeros(n, int))
        s10 = dict(strat=np.zeros(n))
        for w in range(n):
            j = meta_choose(base, nw + w, hl)
            if j < 0:
                continue
            s15["strat"][w] = ser15[j]["strat"][nw + w]
            s15["long"][w] = ser15[j]["long"][nw + w]
            s15["rdir"][w] = ser15[j]["rdir"][nw + w]
            s15["rtool"][w] = np.mean([s["strat"][nw + w] for s in ser15])
            s15["ntr"][w] = ser15[j]["ntr"][nw + w]
            s10["strat"][w] = s10all[j, nw + w]
        rows.append(judge(f"META hl={hl}", "M", s15, s10, 0.5, ("long", "rdir", "rtool"),
                          chop, 0))

    # round 3
    for L in (8, 13):
        sig = lambda f, mm, c, p: AP.tsm_tool(mm, c, p["L"])  # noqa: E731
        bad = len(EV.audit_lookahead("K", dict(L=L), m, cuts, sig=sig))
        s15 = EV.weekly_series("K", dict(L=L), m, cuts, 1.5, {}, runner=tsmi_week)
        s10 = EV.weekly_series("K", dict(L=L), m, cuts, 1.0, {}, runner=tsmi_week)
        rows.append(judge(f"TSMI L={L}", "K", s15, s10, 0.5, ("long", "rdir"), chop, bad))
    sigc: dict = {}
    for hl in (4, 13):
        s15, _ = volman_series(m, cuts, hl, 1.5, sigc)
        s10, _ = volman_series(m, cuts, hl, 1.0, sigc)
        rows.append(judge(f"VOLMAN hl={hl}", "I", s15, s10, 0.5, ("longmatch", "rdir"), chop, 0))
    for z in (3.0, 4.0):
        for H in (2, 6):
            p = dict(z=z, H=H, gated=False)
            bad = len(EV.audit_lookahead("D-ungated", p, m, cuts))
            s15 = EV.weekly_series("D-ungated", p, m, cuts, 1.5, effc)
            s10 = EV.weekly_series("D-ungated", p, m, cuts, 1.0, effc)
            rows.append(judge(f"CHOPREV-X z={z} H={H}", "D-ungated", s15, s10, 0.25,
                              EV.controls_for("D-ungated"), chop, bad))

    df = pd.DataFrame(rows)
    df.to_csv("data/wpwb_live_all.csv", index=False)
    print(f"\ntools run: {len(df)} (+6 HOD-family earlier = 40); threshold p < {P_MAX:.6f}; "
          f"passes: {int(df.PASS.sum())}")
    top = df.sort_values("min_t", ascending=False).head(5)
    print("\nstrongest five by min t across controls (for the record):")
    for _, r in top.iterrows():
        print(f"  {r['variant']:28s} min_t={r['min_t']:+.2f} max_p={r['max_p']:.4f} "
              f"base={r['mean_week_bp_base']:+.2f} bp/wk")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
