"""expansion/M5, stop ATR in (0.75, 1.0, 1.5), target R in
1/1.5/2/2.5/3/4/5/6/7/8/9/10, LONG (real) vs SHORT (flipped, same entries) -
every value, step by step, then converted to dollar finance.

Because targets go far beyond the declared grid's 3R cap, the time stop is
extended from 24h (288 M5 bars) to 30 calendar days (8,640 M5 bars) so a
distant target has a real chance to resolve; how often it still expires
unresolved is reported explicitly, not hidden.

Same-bar ties are resolved with real M1 data on the M1-covered subset
(2023-11-20 onward), exactly as Parts 13-17. Finance uses XAUUSD's minimum
0.01 lot (1 oz; contract 100 oz), so $1 of P&L = 1.0 price-unit move.
Read-only.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import basket_gate as A24
import causal_chain as C
import data as D
import historical_regime_walkforward as hist
import mtf_engine as E

STOPS = (0.75, 1.0, 1.5)
TARGETS = (1.0, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0)
TIME_STOP = 30 * 288          # 30 calendar days of M5 bars
VALUE_PER_PRICE_UNIT_001LOT = 1.0   # XAUUSD: 100 oz/lot * 0.01 lot = 1 oz


def first_cross(cum, level):
    idx = np.flatnonzero(cum >= level)
    return int(idx[0]) if len(idx) else len(cum)


def load_long_entries(b5, streams, meta, st):
    parts = []
    for tag, m in meta.items():
        if m["setup"] != "expansion" or m["tf"] != "M5" or float(m["stop"]) != st \
                or float(m["target"]) != 1.0:
            continue
        s = streams[m["stream"]]
        held = s["held"][:, int(m["plane"])]
        chosen, _ = C.causal_indices(s["entry_k"], s["order_k"], held)
        if not len(chosen):
            continue
        d = s["direction"][chosen]
        keep = d > 0
        if not np.any(keep):
            continue
        idx = chosen[keep]
        parts.append((s["entry_k"][idx].astype(np.int64), s["atr"][idx],
                     s["entry"][idx], s["at_open"][idx]))
    entry_k = np.concatenate([p[0] for p in parts])
    atr = np.concatenate([p[1] for p in parts])
    entries = np.concatenate([p[2] for p in parts])
    at_open = np.concatenate([p[3] for p in parts])
    return entry_k, atr, entries, at_open


def precompute_paths(b5, entry_k, atr, entries, at_open, direction, st):
    """fav_c/adv_c/j_stop (target-independent) computed ONCE per (stop,
    direction) - the expensive part - reused for every target ratio."""
    n_total = len(entry_k)
    out = []
    for i in range(n_total):
        k = int(entry_k[i]); a = float(atr[i]); e = float(entries[i])
        ao = bool(at_open[i]); d = int(direction[i])
        end = min(k + TIME_STOP, len(b5))
        hi, lo = b5.h[k:end], b5.l[k:end]
        if d > 0:
            fav = (hi - e) / a; adv = (e - lo) / a
        else:
            sp = np.maximum(b5.sp[k:end], E.SPREAD_FALLBACK)
            fav = (e - (lo + sp)) / a; adv = ((hi + sp) - e) / a
        if not ao and len(fav):
            fav = fav.copy(); fav[0] = -np.inf
        fav_c = np.maximum.accumulate(fav)
        adv_c = np.maximum.accumulate(adv)
        j_stop = first_cross(adv_c, st)
        last_c = float(b5.c[end - 1] if d > 0 else b5.c[end - 1] + E.SPREAD_FALLBACK)
        out.append((k, a, e, d, end, fav_c, adv_c, j_stop, last_c))
    return out


def eval_cell(b5, m1, m1_t, m1_start_t, paths, st, tg, fee):
    n_total = len(paths)
    full_wins = full_net = full_dollars = full_timeexp = 0.0
    m1_orig_wins = m1_orig_net = 0.0
    m1_corr_wins = m1_corr_net = m1_corr_dollars = 0.0
    n_m1 = 0
    for (k, a, e, d, end, fav_c, adv_c, j_stop, last_c) in paths:
        risk = st * a
        if d > 0:
            stop_price = e - st * a; target_price = e + st * tg * a
        else:
            stop_price = e + st * a; target_price = e - st * tg * a
        j_tgt = first_cross(fav_c, st * tg)

        timed_out = False
        if j_stop < len(adv_c) and j_stop <= j_tgt:
            gross = -1.0
        elif j_tgt < len(fav_c):
            gross = float(tg)
        else:
            timed_out = True
            gross = d * (last_c - e) / risk
        net = gross - fee / risk
        dollars = net * risk * VALUE_PER_PRICE_UNIT_001LOT
        full_wins += net > 0
        full_net += net
        full_dollars += dollars
        full_timeexp += timed_out

        if b5.t[k] < m1_start_t:
            continue
        n_m1 += 1
        m1_orig_wins += net > 0
        m1_orig_net += net
        corr_net = net
        if j_stop < len(adv_c) and j_stop == j_tgt:
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
                if js1 > jt1:
                    corr_net = float(tg) - fee / risk
        m1_corr_wins += corr_net > 0
        m1_corr_net += corr_net
        m1_corr_dollars += corr_net * risk * VALUE_PER_PRICE_UNIT_001LOT

    return dict(n=n_total, full_win=100*full_wins/n_total, full_net=full_net/n_total,
               full_dollars=full_dollars, full_timeexp=100*full_timeexp/n_total,
               n_m1=n_m1,
               m1_orig_win=100*m1_orig_wins/max(n_m1,1), m1_orig_net=m1_orig_net/max(n_m1,1),
               m1_corr_win=100*m1_corr_wins/max(n_m1,1), m1_corr_net=m1_corr_net/max(n_m1,1),
               m1_corr_dollars=m1_corr_dollars)


def main() -> int:
    b5 = hist.load_history()
    streams, meta, _ = A24.load_raw_cache(b5)
    fee = E.COMMISSION_RT + 2.0 * E.SLIP_PER_FILL
    m1 = D.load_csv("data/XAUUSD_M1.csv")
    m1_t = m1.t.astype(np.int64)
    m1_start_t = int(m1.t[0])

    print(f"time stop extended to {TIME_STOP:,} M5 bars (30 calendar days)")
    print(f"$1 finance unit = 1.0 XAUUSD price-unit move at 0.01 lot\n")

    excel_rows = []
    for st in STOPS:
        entry_k, atr, entries, at_open = load_long_entries(b5, streams, meta, st)
        n = len(entry_k)
        print(f"\n{'='*100}\nSTOP = {st} ATR  ({n:,} real signals)\n{'='*100}")
        hdr = (f"{'RR':>7s}{'side':>6s}{'n_M1':>7s}"
              f"{'win%_M1fix':>11s}{'net/tr_M1fix':>13s}{'timeexp%':>9s}  |"
              f"{'$_full':>12s}{'$_M1fix':>12s}")
        print(hdr)
        for label, d_arr in (("LONG", np.ones(n, np.int8)),
                             ("SHORT*", -np.ones(n, np.int8))):
            # the expensive part - once per (stop, side), reused for every RR
            paths = precompute_paths(b5, entry_k, atr, entries, at_open, d_arr, st)
            for tg in TARGETS:
                r = eval_cell(b5, m1, m1_t, m1_start_t, paths, st, tg, fee)
                print(f"1:{tg:<5.1f}{label:>6s}{r['n_m1']:7,d}"
                      f"{r['m1_corr_win']:10.1f}%{r['m1_corr_net']:13.4f}"
                      f"{r['full_timeexp']:8.1f}%  |"
                      f"{r['full_dollars']:12,.2f}{r['m1_corr_dollars']:12,.2f}")
                side_th = "ซื้อ (จริง)" if label == "LONG" else "ขาย (กลับด้าน จำลอง)*"
                excel_rows.append({
                    "ATR หยุดขาดทุน": st, "RR (เป้า:ทุน)": f"1:{tg:g}",
                    "ทิศทาง": side_th,
                    "จำนวนไม้ทั้งหมด": r["n"], "จำนวนไม้ (ช่วงมี M1)": r["n_m1"],
                    "อัตราชนะ% (ทั้งช่วง)": round(r["full_win"], 2),
                    "กำไร/ไม้ เป็น R (ทั้งช่วง)": round(r["full_net"], 4),
                    "%หมดเวลา (ทั้งช่วง)": round(r["full_timeexp"], 2),
                    "กำไรรวม$ (ทั้งช่วง)": round(r["full_dollars"], 2),
                    "อัตราชนะ% (M1 ก่อนแก้)": round(r["m1_orig_win"], 2),
                    "กำไร/ไม้ เป็น R (M1 ก่อนแก้)": round(r["m1_orig_net"], 4),
                    "อัตราชนะ% (M1 แก้ไขแล้ว)": round(r["m1_corr_win"], 2),
                    "กำไร/ไม้ เป็น R (M1 แก้ไขแล้ว)": round(r["m1_corr_net"], 4),
                    "กำไรรวม$ (M1 แก้ไขแล้ว)": round(r["m1_corr_dollars"], 2),
                })
    print("\ncolumns: RR = target:stop ratio. n_M1 = trades inside M1 coverage.")
    print("win%_M1fix/net_M1fix = M1-corrected, on the M1-covered subset only.")
    print("timeexp% = share of the FULL-period trades that hit the 30-day time")
    print("  stop without reaching either level - if this is large, the target")
    print("  is too far for even 30 days and the number below it is unreliable.")
    print("$_full = summed dollar P&L, full period, conservative tie-break,")
    print("  0.01 lot every trade. $_M1fix = summed dollar P&L, M1-covered")
    print("  subset only, ties corrected with real M1 data.")

    import pandas as pd
    df = pd.DataFrame(excel_rows)
    out_path = Path("data/rr_sweep_finance.xlsx")
    with pd.ExcelWriter(out_path, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="ทั้งหมด", index=False)
        for st in STOPS:
            df[df["ATR หยุดขาดทุน"] == st].to_excel(
                writer, sheet_name=f"stop_{st}", index=False)
    print(f"\nExcel written: {out_path}  ({len(df)} rows)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
