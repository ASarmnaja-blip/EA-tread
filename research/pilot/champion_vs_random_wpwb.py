"""Does WPWB's ACTUAL weekly-selected champion beat a genuine unconditional
random-entry baseline - not just the median-ranked cell from the same pool
(Part 24's built-in control)?

User's question: Part 24 only showed champion vs median-of-the-same-8250-
cell-pool (+0.0042R, 49.7% of weeks - a coin flip). But the median cell is
still drawn from the same pool, so if the WHOLE pool shares some drift-
driven effect, the median would share it too and understate how little
skill the selector has. A truly independent, unconditional random-entry
baseline (Parts 19/22/24's methodology, no relation to the setup grid at
all) is the stronger, more decisive test. This script builds exactly that,
matched week-by-week to whatever stop/target/timeframe WPWB's real
selector actually chose, using the exact same production resolution
function (mtf_engine.resolve_plane) and cost model (mtf_engine.COMMISSION_RT
/ SLIP_PER_FILL / SWAP_LONG / rollover_nights) that walk_forward.py's
build_universe uses - not a reimplementation. Read-only, no MT5, no order.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import core
import current_edge_backtest as bt
import historical_regime_walkforward as hist
import mtf_engine as E
import walk_forward as wf
from weekly_evolution_grid import (DAY, SELECT_DAYS, FORWARD_DAYS,
                                   _week_boundary, _score_universe,
                                   _unique_ranking, _forward)

TF_MULT = dict(E.TIMEFRAMES)  # {"M5":1, "M15":3, "M30":6, "H1":12, "H4":48}
rng = np.random.default_rng(0)


def build_atr_aligned(b5, mult: int) -> np.ndarray:
    bs, _ = E.resample(b5, mult)
    atr_s = core.atr(bs, E.ATR_N)
    aligned = np.full(len(b5), np.nan)
    for i in range(len(bs)):
        k0 = int(np.searchsorted(b5.t, int(bs.t[i])))
        k1 = min(k0 + mult, len(b5))
        aligned[k0:k1] = atr_s[i]
    valid = ~np.isnan(aligned)
    if not valid.any():
        return np.zeros(len(b5))
    idx = np.where(valid, np.arange(len(aligned)), -1)
    np.maximum.accumulate(idx, out=idx)
    idx[idx < 0] = np.flatnonzero(valid)[0]
    return aligned[idx]


def random_matched_trades(b5, atr_cache: dict, mult: int, stop: float, target: float,
                          lo_idx: int, hi_idx: int, n: int) -> list[float]:
    if mult not in atr_cache:
        atr_cache[mult] = build_atr_aligned(b5, mult)
    atr_arr = atr_cache[mult]
    time_stop = E.TIME_STOP_M5 * mult
    hi_idx = min(hi_idx, len(b5) - time_stop - 1)
    if hi_idx <= lo_idx:
        return []
    ks = rng.choice(np.arange(lo_idx, hi_idx), size=n, replace=True)
    dirs = rng.choice([-1, 1], size=n)
    out = []
    for k, d in zip(ks, dirs):
        a = float(atr_arr[k])
        if not np.isfinite(a) or a <= 0:
            continue
        sp = E.spread_at(b5, k)
        entry = float(b5.o[k] + (sp if d > 0 else 0.0))
        planes = E.resolve_plane(b5, k, d, entry, a, (stop,), (target,),
                                 time_stop, allow_entry_bar_target=True)
        if (stop, target) not in planes:
            continue
        g, why, nb = planes[(stop, target)]
        risk = stop * a
        cost = E.COMMISSION_RT + 2.0 * E.SLIP_PER_FILL
        nt = g - cost / risk
        if d > 0 and E.SWAP_LONG:
            t0 = int(b5.t[k]); t1 = int(b5.t[min(k + nb, len(b5) - 1)])
            nt -= E.rollover_nights(t0, t1) * E.SWAP_LONG / risk
        out.append(nt)
    return out


def main() -> int:
    b5 = hist.load_history()
    last = int(b5.t[-1] + b5.step)
    first = int(b5.t[0])
    print("building fixed 8,250-cell universe once (same as Part 24)...")
    uni, meta = wf.build_universe(b5, last)
    print(f"eligible_cells={len(uni):,}\n")

    atr_cache: dict = {}
    cut = _week_boundary(first)
    if cut <= first + SELECT_DAYS * DAY:
        cut += 7 * DAY
    while cut < first + SELECT_DAYS * DAY:
        cut += 7 * DAY

    champ_net, mid_net, rand_champ_net, rand_mid_net = [], [], [], []
    rolls = idle = 0
    while cut < last:
        end = min(cut + FORWARD_DAYS * DAY, last)
        scores, signature, _ = _score_universe(uni, cut - SELECT_DAYS * DAY, cut)
        rolls += 1
        ranked, _ = _unique_ranking(scores, signature)
        if not ranked:
            idle += 1
            cut += 7 * DAY
            continue
        chosen = ranked[0]
        middle = ranked[len(ranked) // 2]
        chosen_vals = _forward(uni[chosen], cut, end)
        middle_vals = _forward(uni[middle], cut, end)
        champ_net.extend(chosen_vals)
        mid_net.extend(middle_vals)

        lo_idx = int(np.searchsorted(b5.t, cut))
        hi_idx = int(np.searchsorted(b5.t, end))

        m = meta[chosen]
        mult = TF_MULT[m["tf"]]
        n = max(len(chosen_vals), 1)
        rand_champ_net.extend(random_matched_trades(
            b5, atr_cache, mult, m["stop"], m["target"], lo_idx, hi_idx, n))

        mm = meta[middle]
        mult_m = TF_MULT[mm["tf"]]
        n_m = max(len(middle_vals), 1)
        rand_mid_net.extend(random_matched_trades(
            b5, atr_cache, mult_m, mm["stop"], mm["target"], lo_idx, hi_idx, n_m))

        cut += 7 * DAY

    print(f"rolls={rolls} idle={idle}\n")

    def show(label, vals):
        m = bt._metrics(vals)
        if not m:
            print(f"[{label}] no trades")
            return None
        print(f"[{label}] trades={m['trades']} net_R={m['net_R']:+.3f} "
              f"mean_R={m['mean_R']:+.4f} win={m['win_pct']:.1f}% "
              f"PF={m['profit_factor']:.3f}")
        return m

    mc = show("champion (top-ranked cell), real forward trades", champ_net)
    mmid = show("median-ranked cell, real forward trades", mid_net)
    mr = show("random baseline matched to CHAMPION's stop/target/tf each week", rand_champ_net)
    mrm = show("random baseline matched to MEDIAN cell's stop/target/tf each week", rand_mid_net)

    print()
    if mc and mr:
        print(f"champion  - its own matched random  = {mc['mean_R']-mr['mean_R']:+.4f}R/trade")
    if mmid and mrm:
        print(f"median    - its own matched random  = {mmid['mean_R']-mrm['mean_R']:+.4f}R/trade")
    if mc and mmid:
        print(f"champion  - median (within-pool)    = {mc['mean_R']-mmid['mean_R']:+.4f}R/trade")
    print()
    print("Reading: if 'champion - its matched random' and 'median - its matched")
    print("random' are SIMILAR, then beating random is a property of being ANY")
    print("member of this setup grid (consistent with Parts 19/22's drift-artifact")
    print("finding), not of the LCB-based selection step. Only if champion's edge")
    print("over random clearly EXCEEDS median's edge over random does the weekly")
    print("selection mechanism itself look like it adds value beyond grid membership.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
