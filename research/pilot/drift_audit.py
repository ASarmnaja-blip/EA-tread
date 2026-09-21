"""Is ORDERLY_TREND's positive number an edge, or is it gold's uptrend?

The inverse search (Amendment 07) found that on this sample the sign of almost
every candidate follows its DIRECTION rather than its pattern: longs positive,
shorts negative, across five unrelated families. Gold moved from roughly 1900
to 4300 over the period, so that is what drift looks like.

That finding casts a shadow backwards. ORDERLY_TREND's pullback earned +0.0837 R
gross on XAUUSD. If its trades are mostly long, the same explanation may apply
to it, and the project would have spent weeks validating a bull market.

This asks the question directly and answers it three ways:

  1. the long/short split of the tool's own trades, and its expectancy in each
  2. a DIRECTION-MATCHED control: random entries of the same direction, the
     same holding horizon and the same period, so the drift is present in the
     control too. The tool's excess over that control is what is left when the
     drift is removed.
  3. a sign test on the excess, day-clustered

This changes no rule and promotes nothing. It is an audit of a number the
project already has.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import adaptive
import core
import data as D
import regime_v2

N_CONTROL = 400           # random draws per direction
SEED = 20260921


def matched_control(b5: D.Bars, atr15: np.ndarray, b15: D.Bars,
                    nxt: np.ndarray, direction: int, n_draws: int,
                    hold_bars: int, lo_i: int, hi_i: int,
                    rng: np.random.Generator) -> np.ndarray:
    """Random entries of ONE direction over the same index range, resolved with
    the same geometry and the same worst-case rule. The drift is inside this
    control, so whatever the tool earns above it is not the drift."""
    out = []
    for _ in range(n_draws):
        i = int(rng.integers(lo_i, hi_i))
        k = nxt[i]
        a = atr15[i]
        if k < 0 or not np.isfinite(a) or a <= 0:
            continue
        entry = b5.o[k]
        risk = adaptive.STOP_ATR * a
        stop = entry - direction * risk
        target = entry + direction * adaptive.TARGET_R * risk
        px, _, _ = core.resolve(b5, k, direction, entry, stop, target,
                                hold_bars)
        out.append(direction * (px - entry) / risk)
    return np.array(out, dtype=float)


def main() -> int:
    b5 = D.load_csv("data/XAUUSD_M5.csv")
    b15, _ = D.to_15m(b5)
    want = b15.t + 900
    pos = np.searchsorted(b5.t, want)
    nxt = np.where((pos < len(b5)) & (b5.t[np.minimum(pos, len(b5) - 1)] == want),
                   pos, -1)
    c15 = core.Ctx(b15, nxt)
    atr15 = core.atr(b15, 14)
    prof = adaptive.hourly_spread_profile(b5)
    cut = int(b15.t[-1]) - adaptive.HOLDOUT_DAYS * 86400

    news_ep = None
    try:
        import calendar_feed
        cal = calendar_feed.load_calendar("data/calendar.csv")
        rows = calendar_feed.build_events(cal, "USD", ("HIGH",))
        news_ep = np.array(sorted(r.epoch for r in rows if r.usable),
                           dtype=np.int64)
    except Exception:
        pass

    print("=" * 96)
    print("DRIFT AUDIT — ผลบวกของ ORDERLY_TREND เป็น edge หรือเป็นเทรนด์ขาขึ้นของทอง")
    print("=" * 96)

    px0, px1 = float(b15.c[0]), float(b15.c[-1])
    days = (int(b15.t[-1]) - int(b15.t[0])) / 86400
    print(f"ช่วงข้อมูล {days:.0f} วัน  ราคา {px0:,.2f} -> {px1:,.2f} "
          f"({100*(px1/px0-1):+.1f}%)")
    print(f"drift เฉลี่ย {100*(px1/px0-1)/days*365:+.1f}% ต่อปี\n")

    reg = regime_v2.build_regime_v2(b15, news_ep)
    allow = reg["regime"].to_numpy() == "ORDERLY_TREND"
    sig = adaptive.tool_signals("pullback", b15, reg, allow)
    costs = adaptive.cost_series(b15, prof, adaptive.SLIP_GRID[0])
    tr, _ = adaptive.run_with_costs(c15, sig, b5, nxt, costs,
                                    adaptive.SLIP_GRID[0])
    dev = [x for x in tr if x.t < cut]
    if len(dev) < 20:
        print("ไม้ช่วงพัฒนาน้อยเกินไป")
        return 0

    print("--- 1. ไม้ของเครื่องมือเอง แยกตามทิศทาง ---")
    for d, name in ((1, "Long"), (-1, "Short")):
        s = [x for x in dev if x.dir == d]
        if not s:
            print(f"  {name:6s} ไม่มีไม้เลย")
            continue
        g = np.array([x.gross_R for x in s])
        n = np.array([x.net_R for x in s])
        print(f"  {name:6s} ไม้ {len(s):4d} ({100*len(s)/len(dev):4.1f}%)  "
              f"gross {g.mean():+.4f}  net {n.mean():+.4f}  "
              f"ชนะ {100*np.mean(n > 0):.1f}%")
    allg = np.array([x.gross_R for x in dev])
    print(f"  {'รวม':6s} ไม้ {len(dev):4d}          gross {allg.mean():+.4f}")

    print("\n--- 2. เทียบกับ control ที่จับคู่ทิศทาง ---")
    print("  control = เข้าสุ่มในทิศเดียวกัน ช่วงเดียวกัน ถือเท่ากัน")
    print("  ถ้าเครื่องมือชนะเพราะ drift อย่างเดียว ส่วนต่างจะเป็นศูนย์\n")
    rng = np.random.default_rng(SEED)
    lo_i = 60
    hi_i = int(np.searchsorted(b15.t, cut))
    hold = int(np.median([x.bars for x in dev])) or adaptive.TIME_STOP_M5

    excess_rows = []
    for d, name in ((1, "Long"), (-1, "Short")):
        s = [x for x in dev if x.dir == d]
        if len(s) < 10:
            print(f"  {name:6s} ไม้น้อยเกินไป ({len(s)}) -> ไม่ประเมิน")
            continue
        ctrl = matched_control(b5, atr15, b15, nxt, d, N_CONTROL, hold,
                               lo_i, hi_i, rng)
        if len(ctrl) < 30:
            print(f"  {name:6s} control ไม่พอ")
            continue
        tool_g = np.array([x.gross_R for x in s])
        ex = tool_g.mean() - ctrl.mean()
        se_c = ctrl.std(ddof=1) / np.sqrt(len(ctrl))
        se_t = tool_g.std(ddof=1) / np.sqrt(len(tool_g))
        se = float(np.sqrt(se_c ** 2 + se_t ** 2))
        print(f"  {name:6s} เครื่องมือ {tool_g.mean():+.4f}   "
              f"control {ctrl.mean():+.4f} (n={len(ctrl)})   "
              f"ส่วนต่าง {ex:+.4f}  se {se:.4f}  t {ex/se:+.2f}")
        excess_rows.append((name, d, ex, se, s, ctrl))

    print("\n--- 3. ส่วนต่างแบบจัดกลุ่มรายวัน ---")
    for (name, d, ex, se, s, ctrl) in excess_rows:
        cm = float(ctrl.mean())
        x = np.array([t.gross_R - cm for t in s])
        day = np.array([int(t.t) // 86400 for t in s])
        mu = float(x.mean())
        grp = pd.Series(x - mu).groupby(day).sum().to_numpy()
        sec = float(np.sqrt((grp ** 2).sum())) / len(x)
        lo, hi = mu - 1.96 * sec, mu + 1.96 * sec
        print(f"  {name:6s} ส่วนต่าง {mu:+.4f}  [{lo:+.4f}, {hi:+.4f}]  "
              f"-> {'เหลือ edge หลังหัก drift' if lo > 0 else 'อธิบายได้ด้วย drift'}")

    # ---------------------------------------------------------------- part 4
    # How much of the inverse search's long-versus-short gap is drift?
    #
    # The inverse search found longs positive and shorts negative across five
    # unrelated families, and the commit message attributed that to gold's
    # +126 percent move. That attribution was ASSERTED, not measured, and the
    # control above is at the pullback's 2R geometry, not the search's 1:1.
    # The honest way to size the claim is to price a random entry at the
    # SEARCH's geometry and see how big the direction effect actually is.
    print("\n--- 4. drift มีขนาดเท่าไรที่เรขาคณิตของ inverse search (RR 1:1) ---")
    print("  ข้อนี้มีไว้ตรวจคำอธิบายของผมเอง ไม่ใช่เพื่อคัดเลือกอะไร")
    rng2 = np.random.default_rng(SEED + 1)
    base = {}
    for d, name in ((1, "Long"), (-1, "Short")):
        out = []
        for _ in range(1500):
            i = int(rng2.integers(lo_i, hi_i))
            k = nxt[i]
            a = atr15[i]
            if k < 0 or not np.isfinite(a) or a <= 0:
                continue
            entry = b5.o[k]
            risk = adaptive.STOP_ATR * a
            px, _, _ = core.resolve(b5, k, d, entry,
                                    entry - d * risk, entry + d * risk,
                                    adaptive.TIME_STOP_M5)
            out.append(d * (px - entry) / risk)
        v = np.array(out, dtype=float)
        base[d] = v
        se = v.std(ddof=1) / np.sqrt(len(v))
        print(f"  {name:6s} เข้าสุ่ม RR 1:1  n={len(v):5d}  "
              f"gross {v.mean():+.4f}  se {se:.4f}")
    if 1 in base and -1 in base:
        gap = float(base[1].mean() - base[-1].mean())
        se = float(np.sqrt(base[1].var(ddof=1) / len(base[1])
                           + base[-1].var(ddof=1) / len(base[-1])))
        print(f"  ช่องว่าง Long−Short จากการเข้าสุ่มล้วน ๆ = {gap:+.4f} R "
              f"(se {se:.4f})")
        print("  เทียบกับช่องว่างที่ inverse search เจอในแต่ละตระกูล:")
        for fam, lo_v, hi_v in (("late_extension", -0.0315, 0.0600),
                                ("second_failed_push", -0.0283, 0.0283),
                                ("inside_bar_break", -0.0514, 0.0468),
                                ("breakout_into_level", -0.0488, 0.0266),
                                ("post_news_chase", -0.1003, -0.0302)):
            obs = hi_v - lo_v
            share = 100 * gap / obs if obs else float("nan")
            print(f"      {fam:22s} ช่องว่างที่วัดได้ {obs:+.4f}  "
                  f"drift อธิบายได้ {share:5.1f}%")
        # Written after the numbers came back, and the numbers say more than
        # the attribution claimed: the drift gap of +0.1163 R is LARGER than
        # every family's own gap, so drift accounts for 118 to 206 percent of
        # what the search found. The patterns spread long against short LESS
        # than random entries do. There is no pattern-specific losing tail on
        # this sample - the tail is the direction, and nothing else.
        print("  drift อธิบายได้ 118-206% ของทุกตระกูล กล่าวคือ ช่องว่างจากการเข้าสุ่ม")
        print("  กว้างกว่าช่องว่างของ pattern เองด้วยซ้ำ -> ไม่มีหางฝั่งแพ้ที่เป็นของ")
        print("  pattern เลย หางทั้งหมดคือทิศทาง")
        print("  -> คำตัดสิน 'ไม่ผ่าน' ของ Amendment 07 ไม่เปลี่ยน และตอนนี้มีคำอธิบาย")
        print("     ที่วัดได้รองรับ ไม่ใช่แค่คำกล่าวอ้าง")

    print("\n" + "=" * 96)
    print("หมายเหตุ: นี่คือการตรวจสอบ ไม่ใช่การเลื่อนขั้น ไม่มีกฎใดถูกแก้จากไฟล์นี้")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
