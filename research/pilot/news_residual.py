"""
Does the first minute after a release predict what happens AFTERWARDS?

newsdesk.py reported that the first-minute move points where the hour ends.
A peer review found the flaw and it is real: that statistic conditions on the
sign of the 0-to-60 minute return and then reports the 0-to-1 minute return,
but the first minute is PART of the hour it is being compared against. The
number is a part-whole dependence, not a prediction.

The tradable question is whether the first minute predicts the RESIDUAL:

    E[ sign(r_0:1) x r_1:15 ]   and   E[ sign(r_0:1) x r_1:60 ]

with entry at the end of minute one - which is when a trader could actually
act - and measured against two controls:

    permuted sign   the same returns with the signal's sign shuffled
    same-clock      the same minutes of day on days with no release

This file also settles a cheap question raised in the same review. VWAP
reversion measured -0.1146 R net in a balanced range, reliably negative, and
the obvious temptation is to invert it. The algebra says otherwise:

    E_inverse_net = -E_gross - c

so inverting only pays when the original net is worse than -2c. The
reconstruction below shows whether that holds or whether the negative number
is simply friction.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import calendar_feed
import core
import data as D

COST_ROUND_TURN = 0.460        # $0.260 spread + 2 x $0.10 slippage, per oz
HORIZONS = (5, 15, 60)         # minutes measured AFTER the first minute
SEED = 20260921


def move(b: D.Bars, i0: int, i1: int) -> float:
    if i0 < 0 or i1 >= len(b) or i1 <= i0:
        return np.nan
    return float(b.c[i1] - b.c[i0])


def main() -> int:
    xau = D.load_csv("data/XAUUSD_M1.csv")
    cal = calendar_feed.load_calendar("data/calendar.csv")
    rows = calendar_feed.build_events(cal, "USD", ("HIGH",))
    usable = sorted({r.epoch for r in rows if r.usable})

    print("=" * 94)
    print("นาทีแรกหลังข่าว ทำนาย 'ส่วนที่เหลือ' ได้ไหม")
    print("=" * 94)
    print("แก้จากรอบก่อนที่วัดผิด: เดิมเทียบนาทีแรกกับ 60 นาทีซึ่งมีนาทีแรกอยู่ข้างใน")
    print("คราวนี้เข้าไม้ตอนจบนาทีแรก แล้ววัดเฉพาะสิ่งที่เกิดหลังจากนั้น\n")

    recs = []
    for ep in usable:
        i0 = int(np.searchsorted(xau.t, ep))
        if i0 < 100 or i0 + 70 >= len(xau):
            continue
        if abs(int(xau.t[i0]) - ep) > 120:      # release must land on a bar
            continue
        first = move(xau, i0, i0 + 1)           # the minute of the print
        if not np.isfinite(first) or first == 0:
            continue
        rec = dict(epoch=ep, first=first, sign=np.sign(first))
        for h in HORIZONS:
            rec[f"res_{h}"] = move(xau, i0 + 1, i0 + 1 + h)
        recs.append(rec)
    df = pd.DataFrame(recs).dropna()
    print(f"อีเวนต์ที่วัดได้ {len(df):,} ครั้ง")
    if len(df) < 30:
        print("น้อยเกินกว่าจะสรุป")
        return 0

    rng = np.random.default_rng(SEED)
    print(f"\n{'ถือต่อ':>8s}{'n':>6s}{'ได้เฉลี่ย $/oz':>16s}{'t':>8s}"
          f"{'หักต้นทุน':>12s}{'ชนะ%':>8s}{'สุ่มเครื่องหมาย':>16s}")
    for h in HORIZONS:
        pnl = (df["sign"] * df[f"res_{h}"]).to_numpy()
        se = pnl.std(ddof=1) / np.sqrt(len(pnl))
        # permuted-sign control: same returns, signal's sign shuffled
        perm = np.array([np.mean(rng.permutation(df["sign"].to_numpy())
                                 * df[f"res_{h}"].to_numpy())
                         for _ in range(400)])
        print(f"{h:6d}น{len(pnl):6d}{pnl.mean():16.4f}{pnl.mean()/se:8.2f}"
              f"{pnl.mean()-COST_ROUND_TURN:12.4f}{100*(pnl>0).mean():8.1f}"
              f"{perm.mean():16.4f}")

    # same-clock control on days without a release
    ev_days = {pd.Timestamp(e, unit="s", tz="UTC").date() for e in usable}
    t_all = pd.to_datetime(xau.t, unit="s", utc=True)
    ctrl = []
    for ep in usable:
        ts = pd.Timestamp(ep, unit="s", tz="UTC")
        for back in range(1, 15):
            d = ts - pd.Timedelta(days=back)
            if d.date() in ev_days:
                continue
            j = int(np.searchsorted(xau.t, int(d.timestamp())))
            if j < 100 or j + 70 >= len(xau):
                continue
            f = move(xau, j, j + 1)
            if not np.isfinite(f) or f == 0:
                continue
            ctrl.append(dict(sign=np.sign(f),
                             **{f"res_{h}": move(xau, j + 1, j + 1 + h)
                                for h in HORIZONS}))
            break
    c = pd.DataFrame(ctrl).dropna()
    print(f"\nตัวควบคุมเวลาเดียวกันในวันที่ไม่มีข่าว ({len(c):,} ครั้ง)")
    for h in HORIZONS:
        p = (c["sign"] * c[f"res_{h}"]).to_numpy()
        se = p.std(ddof=1) / np.sqrt(len(p))
        print(f"  ถือต่อ {h:2d} นาที: ได้เฉลี่ย {p.mean():+.4f} $/oz  t={p.mean()/se:+.2f}")
    print("  หมายเหตุสำคัญ: ตัวเลขบวกในบรรทัดข้างบนนี้ถูกทดสอบแล้วและตกไปแล้ว")
    print("  ดู minute_momentum.py - บน 41,615 ตัวอย่างที่ไม่ทับกัน เหลือ +0.008 $/oz")
    print("  ต่อต้นทุน 0.460 และไม่มีชั่วโมงไหนใน 24 ชั่วโมงที่เป็นบวก")
    print("  มันคือเสียงรบกวนของตัวอย่าง 466 ครั้ง ห้ามหยิบไปอ้างอีก")

    print(f"\nต้นทุนไป-กลับที่ต้องจ่าย: ${COST_ROUND_TURN:.3f}/oz")
    best = max(HORIZONS, key=lambda h: (df["sign"] * df[f"res_{h}"]).mean())
    b = (df["sign"] * df[f"res_{best}"]).to_numpy()
    print(f"ดีที่สุดคือถือต่อ {best} นาที ได้ {b.mean():+.4f} $/oz "
          f"-> หลังต้นทุน {b.mean()-COST_ROUND_TURN:+.4f} $/oz")

    # ---------------------------------------------------------------- VWAP
    print("\n" + "=" * 94)
    print("กลับข้าง VWAP reversion คุ้มไหม - ตรวจด้วยพีชคณิตก่อนเสียเวลา backtest")
    print("=" * 94)
    E_net = -0.1146
    for c_R in (0.0717, 0.1010):
        E_gross = E_net + c_R
        inv_net = -E_gross - c_R
        print(f"  ถ้าต้นทุน {c_R:.4f} R: gross เดิม {E_gross:+.4f} R "
              f"-> กลับข้างแล้วได้ {inv_net:+.4f} R "
              f"{'คุ้ม' if inv_net > 0 else 'ยังขาดทุน'}")
    print("  เงื่อนไขที่จะคุ้มคือ net เดิมต้องแย่กว่า -2 เท่าของต้นทุน")
    print(f"  net เดิม {E_net:+.4f} R เทียบกับเกณฑ์ -0.1434 ถึง -0.2020 R")
    print("  -> ความติดลบของมันคือค่าธรรมเนียม ไม่ใช่สัญญาณกลับทาง ปิดประเด็นนี้ได้")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
