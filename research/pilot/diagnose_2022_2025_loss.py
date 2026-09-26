"""Why did the 44-month window (2022-01-01 to 2025-09-21) lose money while the
trailing 12 months turned the whole run profitable?

The operator asked a specific, answerable question: is the loss because the
strategy scope genuinely cannot read that market, or because gold simply was not
rallying the way it is now?

This does NOT reuse weekly_evolution_grid.py or compound_bar_replay.py, which are
Codex's uncommitted, untested work and are exactly the code whose result is under
question. It uses only `core.resolve` (verified against a mutation trap in
test_mtf_engine.py) and `core.atr`, computing three independent things per era:

  1. what the market itself did - price change, volatility relative to price,
     and directional efficiency (net move / total path length), the same shape
     of measure used throughout this project's regime work
  2. a random-entry drift baseline, long and short, at the project's simplest
     shared geometry (1.5 ATR stop, 1:1 target, worst-case resolution) - exactly
     the method drift_audit.py used earlier in this project to separate "the
     instrument drifted" from "the tool has information"
  3. where possible, the actual weekly-selected trades' own long/short mix in
     the losing window, read directly from the cached universe (read-only,
     Codex's data, not modified)
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import canonical_history as ch
import core
import data as D

STOP_ATR = 1.5
RR = 1.0
TIME_STOP_M5 = 72
ATR_N = 14
DAY = 86400
SEED = 20260926

ERAS = [
    ("2022", "2022-01-01", "2023-01-01"),
    ("2023", "2023-01-01", "2024-01-01"),
    ("2024", "2024-01-01", "2025-01-01"),
    ("2025 Jan-Sep (in losing window)", "2025-01-01", "2025-09-21"),
    ("LOSING WINDOW full: 2022-01-01..2025-09-21", "2022-01-01", "2025-09-21"),
    ("CURRENT/trailing 12mo: 2025-09-21..2026-09-21", "2025-09-21", "2026-09-21"),
]


def epoch(s: str) -> int:
    import datetime as dt
    y, m, d = (int(x) for x in s.split("-"))
    return int(dt.datetime(y, m, d, tzinfo=dt.timezone.utc).timestamp())


def market_character(b15, atr15, lo_i, hi_i):
    """What the market itself did in [lo_i, hi_i): return, vol/price,
    directional efficiency at three horizons (1 day, 1 week, 1 month, in M15
    bars), and the share of days that were net up vs down."""
    c = b15.c[lo_i:hi_i]
    if len(c) < 50:
        return None
    px0, px1 = float(c[0]), float(c[-1])
    ret_pct = 100.0 * (px1 / px0 - 1.0)
    a = atr15[lo_i:hi_i]
    a = a[np.isfinite(a) & (a > 0)]
    vol_over_price = float(np.median(a)) / float(np.median(c)) if len(a) else float("nan")

    logc = np.log(np.maximum(c, 1e-9))
    r1 = np.diff(logc)
    path_total = float(np.sum(np.abs(r1)))
    net_total = float(abs(logc[-1] - logc[0]))
    eff_full = net_total / path_total if path_total > 0 else float("nan")

    # weekly directional efficiency, averaged (M15 bars per week ~ 4*24*7=672)
    week = 672
    effs = []
    for i in range(0, len(logc) - week, week):
        seg = logc[i:i + week]
        p = float(np.sum(np.abs(np.diff(seg))))
        n = float(abs(seg[-1] - seg[0]))
        if p > 0:
            effs.append(n / p)
    weekly_eff = float(np.mean(effs)) if effs else float("nan")

    return dict(ret_pct=ret_pct, vol_over_price=vol_over_price,
               eff_full_period=eff_full, weekly_eff_mean=weekly_eff,
               n_weeks=len(effs))


def random_drift(b5, nxt, atr15, lo_i, hi_i, n_draws=3000, seed=SEED):
    """Random-entry gross R, long and short, at the project's shared simple
    geometry, worst-case resolved. This is drift_audit.py's method, rerun per
    era rather than assumed."""
    rng = np.random.default_rng(seed)
    idx = np.arange(lo_i, min(hi_i, len(atr15) - 1))
    idx = idx[np.isfinite(atr15[idx]) & (atr15[idx] > 0)]
    if len(idx) < 50:
        return dict(long=float("nan"), short=float("nan"), n=0)
    out = {}
    for d, name in ((1, "long"), (-1, "short")):
        picks = rng.choice(idx, size=min(n_draws, len(idx)), replace=True)
        vals = []
        for i in picks:
            k = int(nxt[i])
            a = atr15[i]
            if k < 0 or not np.isfinite(a) or a <= 0:
                continue
            entry = b5.o[k]
            risk = STOP_ATR * float(a)
            px, _, _ = core.resolve(b5, k, d, entry, entry - d * risk,
                                    entry + d * RR * risk, TIME_STOP_M5)
            vals.append(d * (px - entry) / risk)
        out[name] = float(np.mean(vals)) if vals else float("nan")
    out["n"] = len(idx)
    out["long_minus_short"] = out["long"] - out["short"]
    return out


def main() -> int:
    print("=" * 100)
    print("ทำไม 44 เดือน (ม.ค.2022 - ก.ย.2025) ขาดทุน แต่รวม 12 เดือนล่าสุดแล้วกลับเป็นบวกมหาศาล")
    print("=" * 100)
    print("ใช้เฉพาะ core.resolve/core.atr ที่ผ่านการทดสอบ mutation-trap แล้ว ไม่พึ่งโค้ดของ Codex")
    print()

    b5 = ch.load(Path("data/canonical_XAUUSD_M5.npz"))
    b15, _ = D.to_15m(b5)
    want = b15.t + 900
    pos = np.searchsorted(b5.t, want)
    nxt = np.where((pos < len(b5)) & (b5.t[np.minimum(pos, len(b5) - 1)] == want),
                   pos, -1)
    atr15 = core.atr(b15, ATR_N)

    print(f"{'ช่วง':45s}{'ผลตอบแทน':>10s}{'ATR/ราคา':>10s}{'ประสิทธิภาพ':>12s}"
          f"{'สุ่ม Long':>11s}{'สุ่ม Short':>11s}{'ช่องว่าง':>10s}")
    print(f"{'':45s}{'ทั้งช่วง':>10s}{'(ผันผวน)':>10s}{'ทิศทาง':>12s}"
          f"{'(gross R)':>11s}{'(gross R)':>11s}{'L-S':>10s}")
    print("-" * 100)

    results = {}
    for name, s0, s1 in ERAS:
        lo, hi = epoch(s0), epoch(s1)
        lo_i = int(np.searchsorted(b15.t, lo))
        hi_i = int(np.searchsorted(b15.t, hi))
        mc = market_character(b15, atr15, lo_i, hi_i)
        rd = random_drift(b5, nxt, atr15, lo_i, hi_i)
        results[name] = (mc, rd)
        if mc is None:
            print(f"{name:45s}  ข้อมูลไม่พอ")
            continue
        print(f"{name:45s}{mc['ret_pct']:+9.1f}%{100*mc['vol_over_price']:9.3f}%"
              f"{mc['weekly_eff_mean']:12.3f}{rd['long']:11.4f}{rd['short']:11.4f}"
              f"{rd['long_minus_short']:10.4f}")

    print()
    print("คำอธิบายศัพท์:")
    print("  ผลตอบแทนทั้งช่วง = ราคาทองเปลี่ยนไปกี่ % ตลอดช่วงนั้น (ไม่ใช่ต่อปี)")
    print("  ATR/ราคา = ความผันผวนเฉลี่ยต่อแท่ง M15 คิดเป็น % ของราคา ยิ่งสูงคือแท่งสวิงมากกว่า")
    print("  ประสิทธิภาพทิศทาง = ระยะทางที่ราคาเดินสุทธิ หารด้วยระยะทางที่ราคาเดินจริงทั้งหมด")
    print("                      ราย 1 สัปดาห์ แล้วเฉลี่ย ถ้า =1 คือราคาเดินตรงทางเดียวไม่มีสวนเลย")
    print("                      ถ้า ~0 คือแกว่งไปแกว่งมาแต่ไปไม่ถึงไหน (ตลาด choppy/range)")
    print("  สุ่ม Long/Short = เข้าไม้แบบสุ่มล้วน ๆ (ไม่มีสัญญาณ) ที่ stop 1.5 ATR target 1:1")
    print("                    วัดผลก่อนหักต้นทุน (gross R) ถ้าค่าไม่เท่ากันแปลว่ามี drift")
    print("  ช่องว่าง L-S = สุ่ม Long ลบ สุ่ม Short ยิ่งบวกมากคือตลาดเอื้อฝั่งซื้อมากเท่านั้น")

    print("\n" + "=" * 100)
    print("อ่านผล")
    print("=" * 100)
    loss = results.get(ERAS[4][0])
    cur = results.get(ERAS[5][0])
    if loss[0] and cur[0]:
        print(f"\n1) ราคาทองใน 44 เดือนที่ขาดทุน: {loss[0]['ret_pct']:+.1f}%  "
              f"เทียบกับ 12 เดือนปัจจุบัน: {cur[0]['ret_pct']:+.1f}%")
        if loss[0]['ret_pct'] > 0:
            print("   -> ทองขึ้นทั้งสองช่วง ไม่ใช่ว่าช่วงที่ขาดทุนราคาทองนิ่งหรือลง")
        print(f"\n2) ประสิทธิภาพทิศทาง (ราคาเดินตรงทางแค่ไหน): "
              f"44 เดือน = {loss[0]['weekly_eff_mean']:.3f}  "
              f"12 เดือนปัจจุบัน = {cur[0]['weekly_eff_mean']:.3f}")
        d = cur[0]['weekly_eff_mean'] - loss[0]['weekly_eff_mean']
        print(f"   ต่างกัน {d:+.3f}  "
              f"({'ตอนนี้เดินตรงทางกว่ามาก' if d > 0.03 else 'ใกล้เคียงกัน'})")
        print(f"\n3) ช่องว่าง Long-Short จากการเข้าสุ่ม (วัด drift ล้วน ๆ): "
              f"44 เดือน = {loss[1]['long_minus_short']:+.4f} R  "
              f"12 เดือนปัจจุบัน = {cur[1]['long_minus_short']:+.4f} R")
        r = (cur[1]['long_minus_short'] / loss[1]['long_minus_short']
             if loss[1]['long_minus_short'] else float('nan'))
        print(f"   ตอนนี้ drift หนุนฝั่ง Long มากกว่าช่วง 44 เดือนถึง {r:.1f} เท่า"
              if np.isfinite(r) else "")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
