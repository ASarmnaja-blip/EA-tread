"""All M5 signals, restricted to the period M1 data actually covers, with
same-bar ties resolved using real 1-minute bars instead of the conservative
"assume own stop first" convention - then a clean before/after summary.

Scope: every M5-timeframe cell (6 families x 5 stops x 5 targets x 11 entry
modes = 1,650 cells), causal fill-time chain (Amendment 26), entries
restricted to >= M1's first bar (2023-11-20). For every trade whose M5-level
resolution was a genuine tie (stop and target both crossed within the same
M5 bar), the exact M5 bar's M1 sub-bars are checked to find which level was
actually touched first. Faithful to production: allow_entry_bar_target is
set from the stream's own recorded `at_open` flag, matching
mtf_engine.resolve_plane's real rule for intrabar limit fills.

Reports the SAME trades' net R twice: once under the original conservative
rule, once with ties corrected by M1 where resolvable. Read-only.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import basket_gate as A24
import data as D
import historical_regime_walkforward as hist
import mtf_engine as E

M1_PATH = "data/XAUUSD_M1.csv"


def first_cross(cum, level):
    idx = np.flatnonzero(cum >= level)
    return int(idx[0]) if len(idx) else len(cum)


def main() -> int:
    b5 = hist.load_history()
    streams, meta, _ = A24.load_raw_cache(b5)
    fee = E.COMMISSION_RT + 2.0 * E.SLIP_PER_FILL

    m1 = D.load_csv(M1_PATH)
    m1_t = m1.t.astype(np.int64)
    m1_start_t = int(m1.t[0])
    print(f"M1 coverage starts {__import__('datetime').datetime.fromtimestamp(m1_start_t, __import__('datetime').timezone.utc)}")

    m5_cells = [(tag, m) for tag, m in meta.items() if m["tf"] == "M5"]
    print(f"M5 cells: {len(m5_cells):,}")

    n_trades = n_ties = 0
    n_stop_first = n_target_first = n_still_tied = n_unresolvable_m1 = 0
    orig_net_sum = corr_net_sum = 0.0
    orig_wins = corr_wins = 0
    by_family_orig = {}
    by_family_corr = {}

    for tag, m in m5_cells:
        s = streams[m["stream"]]
        held_col = s["held"][:, int(m["plane"])]
        # causal, fill-time-ordered acceptance (Amendment 26)
        import causal_chain as C
        chosen, _ = C.causal_indices(s["entry_k"], s["order_k"], held_col)
        if not len(chosen):
            continue
        entry_k_all = s["entry_k"][chosen].astype(np.int64)
        keep = b5.t[entry_k_all] >= m1_start_t
        if not np.any(keep):
            continue
        idx = chosen[keep]
        st = float(m["stop"]); tg = float(m["target"])
        risk_all = st * s["atr"][idx]
        entries = s["entry"][idx]
        atrs = s["atr"][idx]
        directions = s["direction"][idx]
        at_opens = s["at_open"][idx]
        orig_gross_stored = s["gross"][idx, int(m["plane"])]

        fam = m["setup"]
        fo = by_family_orig.setdefault(fam, [0, 0.0])
        fc = by_family_corr.setdefault(fam, [0, 0.0])

        for j in range(len(idx)):
            k = int(entry_k_all[keep][j]); a = float(atrs[j]); e = float(entries[j])
            d = int(directions[j]); risk = float(risk_all[j])
            at_open = bool(at_opens[j])
            end = min(k + E.TIME_STOP_M5, len(b5))
            hi, lo = b5.h[k:end], b5.l[k:end]
            if d > 0:
                fav = (hi - e) / a
                adv = (e - lo) / a
                stop_price = e - st * a
                target_price = e + st * tg * a
            else:
                sp = np.maximum(b5.sp[k:end], E.SPREAD_FALLBACK)
                fav = (e - (lo + sp)) / a
                adv = ((hi + sp) - e) / a
                stop_price = e + st * a
                target_price = e - st * tg * a
            if not at_open and len(fav):
                fav = fav.copy(); fav[0] = -np.inf
            fav_c = np.maximum.accumulate(fav)
            adv_c = np.maximum.accumulate(adv)
            j_stop = first_cross(adv_c, st)
            j_tgt = first_cross(fav_c, st * tg)

            n_trades += 1
            orig_net = float(orig_gross_stored[j]) - fee / risk
            orig_net_sum += orig_net
            orig_wins += orig_net > 0
            fo[0] += 1; fo[1] += orig_net

            corr_net = orig_net  # default: unchanged unless a resolvable tie
            if j_stop < len(adv_c) and j_stop == j_tgt:
                n_ties += 1
                tie_bar_k = k + j_stop
                bar_t0 = int(b5.t[tie_bar_k]); bar_t1 = bar_t0 + 300
                i0 = int(np.searchsorted(m1_t, bar_t0))
                i1 = int(np.searchsorted(m1_t, bar_t1))
                if i1 - i0 >= 1:
                    hi1, lo1 = m1.h[i0:i1], m1.l[i0:i1]
                    if d > 0:
                        hit_s = np.flatnonzero(lo1 <= stop_price)
                        hit_t = np.flatnonzero(hi1 >= target_price)
                    else:
                        sp1 = np.maximum(m1.sp[i0:i1], E.SPREAD_FALLBACK)
                        hit_s = np.flatnonzero((hi1 + sp1) >= stop_price)
                        hit_t = np.flatnonzero((lo1 + sp1) <= target_price)
                    js1 = int(hit_s[0]) if len(hit_s) else 10**9
                    jt1 = int(hit_t[0]) if len(hit_t) else 10**9
                    if js1 == jt1:
                        n_still_tied += 1
                    elif js1 < jt1:
                        n_stop_first += 1
                    else:
                        n_target_first += 1
                        corr_net = float(tg) - fee / risk
                else:
                    n_unresolvable_m1 += 1
            corr_net_sum += corr_net
            corr_wins += corr_net > 0
            fc[0] += 1; fc[1] += corr_net

    print(f"\ntotal M5 trades in M1-covered window: {n_trades:,}")
    print(f"same-bar ties among them: {n_ties:,} ({100*n_ties/max(n_trades,1):.2f}%)")
    print(f"  of ties: stop truly first {n_stop_first:,}  "
          f"target truly first {n_target_first:,}  still tied@M1 {n_still_tied:,}  "
          f"no M1 bars found {n_unresolvable_m1:,}")

    print(f"\n{'':20s}{'net R (sum)':>14s}{'net R/trade':>13s}{'win%':>8s}")
    print(f"{'ORIGINAL (conservative)':20s}{orig_net_sum:14.2f}{orig_net_sum/n_trades:13.4f}"
          f"{100*orig_wins/n_trades:7.1f}%")
    print(f"{'M1-CORRECTED':20s}{corr_net_sum:14.2f}{corr_net_sum/n_trades:13.4f}"
          f"{100*corr_wins/n_trades:7.1f}%")
    print(f"{'difference':20s}{corr_net_sum-orig_net_sum:+14.2f}"
          f"{(corr_net_sum-orig_net_sum)/n_trades:+13.4f}")

    print(f"\nby family (net R/trade, original -> M1-corrected):")
    for fam in sorted(by_family_orig):
        no, so = by_family_orig[fam]
        nc, sc = by_family_corr[fam]
        print(f"  {fam:10s} n={no:7,d}  {so/no:+.4f} -> {sc/nc:+.4f}  "
              f"(delta {sc/nc - so/no:+.4f})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
