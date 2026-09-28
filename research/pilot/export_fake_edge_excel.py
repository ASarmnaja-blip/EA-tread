"""Export the Part 19/20 fake-edge findings (real expansion/M5 setup vs
unconditional random-entry baseline, trending window and flat window) to
one Excel file with Thai column headers. Read-only, reuses check_fake_edge.py
and check_fake_edge_flat.py's exact logic - no new numbers computed."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from rr_sweep_finance import load_long_entries, precompute_paths, first_cross, TIME_STOP
from check_fake_edge import dedupe_by_bar, eval_net_r
import basket_gate as A24
import core as C5
import data as D
import historical_regime_walkforward as hist
import mtf_engine as E

STOPS = (1.0, 1.5)
TARGETS = (1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0)
FLAT_START, FLAT_END = "2025-05-01", "2025-07-01"


def run_window(b5, streams, meta, fee, atr5, rng, win_start_idx, win_end_idx, usable_end,
              label):
    rows = []
    for st in STOPS:
        entry_k, atr, entries, at_open = load_long_entries(b5, streams, meta, st)
        n_real_raw = len(entry_k)
        keep = (entry_k >= win_start_idx) & (entry_k < win_end_idx) & (entry_k < usable_end)
        entry_k, atr, entries, at_open = entry_k[keep], atr[keep], entries[keep], at_open[keep]
        entry_k, atr, entries, at_open = dedupe_by_bar(entry_k, atr, entries, at_open)
        n_dedup = len(entry_k)
        if n_dedup == 0:
            continue

        rand_k = rng.choice(np.arange(win_start_idx, min(win_end_idx, usable_end)),
                            size=n_dedup, replace=False)
        rand_k = np.sort(rand_k)
        rand_atr = atr5[rand_k]
        rand_entries = b5.c[rand_k]
        rand_at_open = np.ones(n_dedup, dtype=bool)

        d = np.ones(n_dedup, np.int8)
        paths_real = precompute_paths(b5, entry_k, atr, entries, at_open, d, st)
        paths_rand = precompute_paths(b5, rand_k, rand_atr, rand_entries, rand_at_open, d, st)

        for tg in TARGETS:
            w_r, n_r = eval_net_r(b5, paths_real, st, tg, fee)
            w_x, n_x = eval_net_r(b5, paths_rand, st, tg, fee)
            rows.append({
                "ช่วง": label,
                "ATR หยุดขาดทุน": st,
                "RR (เป้า:ทุน)": f"1:{tg:g}",
                "จำนวนไม้ก่อน dedup": n_real_raw,
                "จำนวนไม้หลัง dedup (อิสระจริง)": n_dedup,
                "อัตราชนะ% (setup จริง)": round(w_r, 2),
                "กำไร/ไม้ เป็น R (setup จริง)": round(n_r, 4),
                "อัตราชนะ% (ไม้สุ่มล้วนๆ)": round(w_x, 2),
                "กำไร/ไม้ เป็น R (ไม้สุ่มล้วนๆ)": round(n_x, 4),
                "ส่วนต่าง จริง−สุ่ม (R)": round(n_r - n_x, 4),
            })
    return rows


def main() -> int:
    b5 = hist.load_history()
    streams, meta, _ = A24.load_raw_cache(b5)
    fee = E.COMMISSION_RT + 2.0 * E.SLIP_PER_FILL
    atr5 = C5.atr(b5, 14)
    usable_end = len(b5) - TIME_STOP
    t = pd.to_datetime(b5.t, unit="s", utc=True)

    m1 = D.load_csv("data/XAUUSD_M1.csv")
    m1_start_idx = int(np.searchsorted(b5.t.astype(np.int64), int(m1.t[0])))

    rng = np.random.default_rng(0)
    rows_trend = run_window(b5, streams, meta, fee, atr5, rng,
                            m1_start_idx, usable_end, usable_end,
                            "ช่วงเทรนด์ (2023-11 เป็นต้นไป, Part 19)")

    rng = np.random.default_rng(0)
    flat_start_idx = int(np.searchsorted(t.values, np.datetime64(FLAT_START)))
    flat_end_idx = int(np.searchsorted(t.values, np.datetime64(FLAT_END)))
    rows_flat = run_window(b5, streams, meta, fee, atr5, rng,
                           flat_start_idx, flat_end_idx, usable_end,
                           "ช่วงทองนิ่ง (พ.ค.-มิ.ย. 2025, Part 20)")

    df = pd.DataFrame(rows_trend + rows_flat)
    out_path = Path("data/fake_edge_check.xlsx")
    with pd.ExcelWriter(out_path, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="ทั้งหมด", index=False)
        df[df["ช่วง"].str.startswith("ช่วงเทรนด์")].to_excel(
            writer, sheet_name="ช่วงเทรนด์", index=False)
        df[df["ช่วง"].str.startswith("ช่วงทองนิ่ง")].to_excel(
            writer, sheet_name="ช่วงทองนิ่ง", index=False)
    print(f"wrote {out_path} ({len(df)} rows)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
