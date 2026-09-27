"""Amendment 28 — volatility-regime stand-aside on top of Amendment 24/26.

Pre-registered in docs/AMENDMENT_28_REGIME_STANDASIDE.md before this ran.
Reuses Amendment 26's causal chain and Amendment 24's friction-gated selector,
basket construction, execution and cost model completely unchanged. The only
addition: at each Weekend Rebuild cutoff, a trailing-year H1-ATR percentile
rank is computed causally (only bars strictly before the cutoff), and the
week is forced to NO TRADE when that percentile is below the frozen 0.40
threshold.

Read-only. No order-sending code. NOT BLIND: informed by the already-seen
Amendment 24/26 cost decomposition.
"""
from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import basket_gate as A24
import causal_chain as C
import core
import historical_regime_walkforward as hist
import mtf_engine as E

RECENT_H1_BARS = 480      # 20 trading days
HIST_H1_BARS = 8_760       # 365 days
THRESHOLD = 0.40


def build_regime_series(b5) -> tuple[np.ndarray, np.ndarray]:
    """H1 bar close-times and their (already-verified, causal) ATR-14."""
    bh1, _ = E.resample(b5, 12)   # 12 * M5(5min) = H1
    atr_h1 = core.atr(bh1, 14)
    return bh1.t, atr_h1


def regime_percentile_at(h1_t: np.ndarray, atr_h1: np.ndarray, cutoff: int
                         ) -> tuple[float | None, dict]:
    """Causal percentile rank of trailing-20-day ATR within the trailing year,
    using only H1 bars whose close is strictly before `cutoff`."""
    idx = int(np.searchsorted(h1_t, cutoff, side="left"))
    if idx < RECENT_H1_BARS:
        return None, {"reason": "insufficient_h1_history", "idx": idx}
    recent = atr_h1[max(0, idx - RECENT_H1_BARS):idx]
    hist_lo = max(0, idx - HIST_H1_BARS)
    hist_window = atr_h1[hist_lo:idx]
    recent = recent[np.isfinite(recent)]
    hist_window = hist_window[np.isfinite(hist_window)]
    if len(recent) < RECENT_H1_BARS // 2 or len(hist_window) < RECENT_H1_BARS:
        return None, {"reason": "insufficient_finite_atr"}
    recent_atr = float(np.median(recent))
    pct = float(np.mean(hist_window <= recent_atr))
    return pct, {"recent_atr": recent_atr, "hist_window_n": len(hist_window),
                "hist_start": int(h1_t[hist_lo]), "idx": idx}


def apply_standaside(decisions: list[C.A24.Decision], h1_t, atr_h1
                     ) -> tuple[list, list[dict]]:
    out = []
    log = []
    for d in decisions:
        pct, detail = regime_percentile_at(h1_t, atr_h1, d.cut)
        entry = {"cut": d.cut, "orig_members": len(d.members),
                 "orig_reason": d.reason, "percentile": pct, **detail}
        if pct is None or pct < THRESHOLD:
            entry["standaside"] = True
            out.append(replace(d, members=(), weights={}, scores={},
                               reason=f"regime_standaside(pct={pct})"))
        else:
            entry["standaside"] = False
            out.append(d)
        log.append(entry)
    return out, log


def run_variant(b5, pd, meta, streams, standaside: bool):
    last = int(b5.t[-1] + b5.step)
    first_policy = int(pd.boundaries[A24.MIN_HISTORY_WEEKS])
    decisions = A24.decisions_through(A24.Selector(pd, meta, "gate"),
                                      first_policy, last)
    log = []
    if standaside:
        h1_t, atr_h1 = build_regime_series(b5)
        decisions, log = apply_standaside(decisions, h1_t, atr_h1)
    opportunities = A24.opportunities_from_decisions(b5, streams, meta,
                                                     decisions, True)
    execution = A24.execute_opportunities(opportunities, True)
    path = A24.unit_path(b5, execution.admitted)
    return {"decisions": decisions, "execution": execution, "path": path,
            "log": log}


def collect(run, b5, meta):
    return {name: {cost: A24.window_metrics(b5, run["path"], run["execution"],
                                            meta, start, end, stress)
                   for cost, stress in (("BASE", False), ("COST_1P5X", True))}
            for name, start, end in C._windows(b5)}


def main() -> int:
    print("AMENDMENT_28_REGIME_STANDASIDE")
    print("research_only=true mt5_connection=false order_sending=false")
    b5 = hist.load_history()

    # ---- causality audit: the regime measure at a cutoff cannot see t>=cutoff
    h1_t, atr_h1 = build_regime_series(b5)
    test_cut = int(b5.t[len(b5) // 2])
    pct_full, _ = regime_percentile_at(h1_t, atr_h1, test_cut)
    b5_trunc_extra = b5  # same series; mutate the tail and recompute
    mutated_c = b5_trunc_extra.c.copy()
    tail_start = int(np.searchsorted(b5_trunc_extra.t, test_cut))
    mutated_c[tail_start:] = mutated_c[tail_start:] * 3.0 + 500.0
    from data import Bars
    b5_mut = Bars(b5.t, b5.o, b5.h, b5.l, mutated_c, b5.v, b5.step,
                 b5.symbol, b5.sp)
    h1_t_mut, atr_h1_mut = build_regime_series(b5_mut)
    pct_mut, _ = regime_percentile_at(h1_t_mut, atr_h1_mut, test_cut)
    audit_pass = (pct_full is not None and pct_mut is not None
                 and abs(pct_full - pct_mut) < 1e-9)
    print(f"AUDIT_FUTURE_MUTATION_INVARIANT={audit_pass} "
          f"pct_before={pct_full} pct_after_mutating_future={pct_mut}")
    if not audit_pass:
        print("SECTION_AUDIT=FAIL result_not_run=true")
        return 2

    streams, raw_meta, _ = A24.load_raw_cache(b5)
    pd = C._policy_data_causal_gate(b5, streams, raw_meta)
    print(f"policy_data_built cells={len(pd.tags)}")

    baseline = run_variant(b5, pd, raw_meta, streams, standaside=False)
    treated = run_variant(b5, pd, raw_meta, streams, standaside=True)

    base_m = collect(baseline, b5, raw_meta)
    treat_m = collect(treated, b5, raw_meta)

    def show(m, name):
        r = m[name]
        b = r["BASE"]; s = r["COST_1P5X"]
        print(f"  {name:20s} base net_R={b['net_R']:+9.3f}  "
              f"1.5x net_R={s['net_R']:+9.3f}  trades={b['trades']}  "
              f"active_weeks={b.get('active_week_pct', float('nan')):.1f}%")

    print("\n=== AMENDMENT 24 baseline (no stand-aside), causal chain ===")
    for name, _, _ in C._windows(b5):
        show(base_m, name)

    print("\n=== AMENDMENT 28 (with regime stand-aside) ===")
    for name, _, _ in C._windows(b5):
        show(treat_m, name)

    n_sa = sum(1 for e in treated["log"] if e["standaside"])
    n_total = len(treated["log"])
    print(f"\nstand-aside weeks: {n_sa}/{n_total} ({100*n_sa/max(n_total,1):.1f}%)")

    sa_by_window = {}
    for name, start, end in C._windows(b5):
        in_win = [e for e in treated["log"] if start <= e["cut"] < end]
        sa = sum(1 for e in in_win if e["standaside"])
        sa_by_window[name] = (sa, len(in_win))
        print(f"  {name:20s} stand-aside {sa}/{len(in_win)} "
              f"({100*sa/max(len(in_win),1):.1f}%)")

    print("\n=== Verdict per section 6 ===")
    for name in ("44_MONTH", "TRAILING_12_MONTH"):
        b, s = treat_m[name]["BASE"], treat_m[name]["COST_1P5X"]
        print(f"  {name}: base {b['net_R']:+.3f} R, 1.5x {s['net_R']:+.3f} R")
    verdict_44_stress = treat_m["44_MONTH"]["COST_1P5X"]["net_R"]
    verdict_12_base = treat_m["TRAILING_12_MONTH"]["BASE"]["net_R"]
    verdict_12_stress = treat_m["TRAILING_12_MONTH"]["COST_1P5X"]["net_R"]
    print(f"\n  44-month still negative at 1.5x cost: {verdict_44_stress < 0} "
          f"({verdict_44_stress:+.3f} R) -> mechanism did NOT fully work "
          f"if True")
    print(f"  trailing-12m turned negative at either cost: "
          f"{verdict_12_base < 0 or verdict_12_stress < 0} -> the fix broke "
          f"the working part if True")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
