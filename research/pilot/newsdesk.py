"""
News desk — the release sets a hypothesis, the price decides it.

engine2 reduced the calendar to a column of epochs and threw away everything
that made it a calendar. This module keeps all of it and runs the eight-
situation decision layer in news.py the way CLAUDE.md section 2 specifies:

    actual against forecast, standardised by that series' own history
    previous, and whether it was revised
    a hypothesis formed BEFORE the reaction is looked at
    the reaction of XAUUSD and of DXY at 1, 5, 15 and 60 minutes
    acceptance, rejection, conflict between simultaneous releases,
        and the sweep of both pre-event extremes
    CFTC positioning as it stood before the release

US yields are NOT ASSESSED and reported as such: this account carries 314
symbols and none of them is a bond or a yield - the only US* matches are
USTEC, which is the Nasdaq. Narrative is NOT ASSESSED for the same reason,
there being no feed for it. Neither is estimated, because an invented number
here would be the fabrication CLAUDE.md section 8 forbids.

Nothing in this file trades. It classifies and it measures.
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
import news

HORIZONS_MIN = (1, 5, 15, 60)
PRE_BARS_M1 = 30          # [DEF] pre-event window whose extremes a sweep must take
ATR_BARS_M1 = 60          # [DEF] the volatility unit for reaction size

NOT_ASSESSED_YIELDS = ("NOT ASSESSED: no bond or yield symbol on this account "
                       "(314 symbols; the only US* matches are the Nasdaq)")
NOT_ASSESSED_NARRATIVE = ("NOT ASSESSED: no narrative or sentiment feed exists "
                          "in this project")


def _atr_at(b: D.Bars, i: int, n: int = ATR_BARS_M1) -> float:
    lo = max(0, i - n)
    if i - lo < 5:
        return float("nan")
    h, l, c = b.h[lo:i], b.l[lo:i], b.c[lo:i]
    pc = np.concatenate(([c[0]], c[:-1]))
    tr = np.maximum(h - l, np.maximum(np.abs(h - pc), np.abs(l - pc)))
    return float(tr.mean())


def reaction_of(b: D.Bars, t_event: int, atr: float) -> news.Reaction:
    """Signed move at each horizon in ATR units, measured only after the bell."""
    return news.measure_reaction(t_event, b.t, b.h, b.l, b.c, atr, HORIZONS_MIN)


def assess_all(cal: pd.DataFrame, xau: D.Bars, dxy: D.Bars | None,
               pos: pd.DataFrame | None) -> pd.DataFrame:
    rows = calendar_feed.build_events(cal, "USD", ("HIGH",))
    usable = [r for r in rows if r.usable]

    # group simultaneous releases: the mandate requires CONFLICTING to be a
    # possible verdict, and it can only arise when two releases share a minute
    by_time: dict[int, list] = {}
    for r in usable:
        by_time.setdefault(r.epoch, []).append(r)

    out = []
    for ep in sorted(by_time):
        grp = by_time[ep]
        i = int(np.searchsorted(xau.t, ep))
        if i <= ATR_BARS_M1 or i >= len(xau) - 1:
            continue
        atr = _atr_at(xau, i)
        if not np.isfinite(atr) or atr <= 0:
            continue

        evs = [news.Event(t=r.epoch, name=r.name, importance=r.importance,
                          actual=r.actual, consensus=r.consensus,
                          previous=r.previous,
                          previous_revised=r.previous_revised, sigma=r.sigma,
                          higher_is_gold_negative=bool(r.higher_is_gold_negative))
               for r in grp]

        rx = reaction_of(xau, ep, atr)
        a = news.assess(evs, rx)

        rx_dxy = None
        if dxy is not None:
            j = int(np.searchsorted(dxy.t, ep))
            if ATR_BARS_M1 < j < len(dxy) - 1:
                atr_d = _atr_at(dxy, j)
                if np.isfinite(atr_d) and atr_d > 0:
                    rx_dxy = reaction_of(dxy, ep, atr_d)

        rec = dict(
            epoch=ep, n_releases=len(grp),
            events="; ".join(sorted(r.name for r in grp)),
            scenario=a.scenario, reason=a.reason,
            surprise_z=a.surprise_z, revision=a.revision,
            hypothesis_dir=a.hypothesis_dir, confirmed=a.confirmed,
            tradeable=a.tradeable,
            priced_in=a.priced_in,
            positioning=(calendar_feed.positioning_at(pos, ep)
                         if pos is not None and len(pos) else a.positioning),
            yields=NOT_ASSESSED_YIELDS,
            narrative=NOT_ASSESSED_NARRATIVE,
            swept_high=rx.swept_high, swept_low=rx.swept_low,
        )
        for h in HORIZONS_MIN:
            rec[f"xau_{h}m"] = rx.by_horizon.get(h, np.nan)
            rec[f"dxy_{h}m"] = (rx_dxy.by_horizon.get(h, np.nan)
                                if rx_dxy else np.nan)
        out.append(rec)
    return pd.DataFrame(out)


def main() -> int:
    cal = calendar_feed.load_calendar("data/calendar.csv")
    pos = calendar_feed.positioning_series(cal)
    # M1 where it reaches, because a 1-minute reaction cannot be read off M5
    xau = D.load_csv("data/XAUUSD_M1.csv")
    # DXY must be M1 here. An earlier version loaded DXY_M5 and then asked it
    # for a ONE-MINUTE reaction, which five-minute bars cannot resolve: every
    # dxy_1m figure was a five-minute move wearing a one-minute label. The
    # correlation at one minute moved from -0.808 to -0.892 once this was
    # fixed, on 438 events instead of 137.
    dxy, dxy_note = None, "ไม่มี"
    for path, note in (("data/DXY_M1.csv", "M1"),
                       ("data/DXY_M5.csv", "M5 - ปฏิกิริยา 1 นาทีแยกไม่ได้")):
        try:
            dxy = D.load_csv(path)
            dxy_note = note
            break
        except Exception:
            continue

    t = pd.to_datetime(xau.t, unit="s", utc=True)
    print("=" * 98)
    print("NEWS DESK - ข่าวตั้งสมมติฐาน ราคาตัดสิน")
    print("=" * 98)
    print(f"ราคา M1 {len(xau):,} แท่ง {t[0]:%Y-%m-%d} ถึง {t[-1]:%Y-%m-%d}")
    print(f"DXY {dxy_note} | "
          f"US yields: ไม่มีบนบัญชีนี้ -> NOT ASSESSED")

    df = assess_all(cal, xau, dxy, pos)
    if df.empty:
        print("ไม่มีอีเวนต์ที่ประเมินได้ในช่วงที่ราคาครอบคลุม")
        return 0

    print(f"\nอีเวนต์ที่ประเมินได้ {len(df):,} ครั้ง "
          f"(USD HIGH ที่คำนวณ surprise ได้ และอยู่ในช่วงที่มีราคา M1)")
    print(f"  ที่มีหลายข่าวออกพร้อมกัน: {int((df.n_releases > 1).sum()):,} ครั้ง")
    print(f"  ที่ previous ถูกแก้ไข   : {int(df.revision.notna().sum()):,} ครั้ง")

    print("\nผลการจัดเข้า 8 สถานการณ์ตาม CLAUDE.md ข้อ 2")
    names = {
        "POSITIVE_CONFIRMED": "ข่าวหนุนทอง + ราคายืนยัน",
        "POSITIVE_REJECTED": "ข่าวหนุนทอง + ราคาปฏิเสธ",
        "NEGATIVE_CONFIRMED": "ข่าวกดทอง + ราคายืนยัน",
        "NEGATIVE_REJECTED": "ข่าวกดทอง + ราคาปฏิเสธ",
        "IN_LINE": "ออกใกล้ที่ตลาดคาด",
        "CONFLICTING": "ข่าวพร้อมกันขัดกันเอง",
        "SWEPT_BOTH_SIDES": "กวาดสภาพคล่องสองด้าน",
        "NO_TRADE": "สภาวะที่ไม่ควรเทรด",
    }
    vc = df.scenario.value_counts()
    for k in news.SCENARIOS:
        n = int(vc.get(k, 0))
        print(f"  {names[k]:32s} {n:5d}  ({100*n/len(df):5.1f}%)")

    print("\nราคาทำอะไรต่อหลังแต่ละสถานการณ์ (หน่วย ATR ของ M1, + คือขึ้น)")
    print(f"  {'สถานการณ์':32s}{'n':>5s}{'1 นาที':>9s}{'5 นาที':>9s}"
          f"{'15 นาที':>9s}{'60 นาที':>9s}{'DXY 60น':>9s}")
    for k in news.SCENARIOS:
        g = df[df.scenario == k]
        if len(g) < 5:
            continue
        print(f"  {names[k]:32s}{len(g):5d}"
              + "".join(f"{g[f'xau_{h}m'].mean():9.3f}" for h in HORIZONS_MIN)
              + f"{g['dxy_60m'].mean():9.3f}")

    print("\nทองกับดอลลาร์เดินสวนทางกันจริงไหม (ควรเป็นลบ)")
    for h in HORIZONS_MIN:
        a, b = df[f"xau_{h}m"], df[f"dxy_{h}m"]
        m = a.notna() & b.notna()
        if m.sum() > 20:
            print(f"  ที่ {h:2d} นาที: correlation {np.corrcoef(a[m], b[m])[0,1]:+.3f} "
                  f"จาก {int(m.sum())} ครั้ง")

    print("\n" + "!" * 98)
    print("อ่านตารางข้างบนอย่างไรไม่ให้หลอกตัวเอง")
    print("!" * 98)
    print("คอลัมน์ 60 นาที เป็นวงกลม - news.assess ใช้การเคลื่อนไหวที่ 60 นาที")
    print("เป็นตัวตัดสินว่าเป็น CONFIRMED หรือ REJECTED ดังนั้นการที่ CONFIRMED")
    print("มีค่า 60 นาทีสูง เป็นผลจากนิยาม ไม่ใช่การค้นพบ")
    print()
    print("คอลัมน์ที่อ่านได้จริงคือ 1 นาที เพราะมันไม่ได้ถูกใช้จัดประเภท:")
    for k, lab in (("POSITIVE_CONFIRMED", "หนุนทอง+ยืนยัน"),
                   ("NEGATIVE_CONFIRMED", "กดทอง+ยืนยัน")):
        g = df[df.scenario == k]
        if len(g) >= 5:
            print(f"  {lab:18s} นาทีแรก {g['xau_1m'].mean():+6.2f} ATR "
                  f"-> จบชั่วโมงที่ {g['xau_60m'].mean():+6.2f} ATR  (n={len(g)})")
    print("  ทิศทางในนาทีแรกชี้ทางที่ชั่วโมงนั้นจะจบ - นี่คือข้อความที่ไม่เป็นวงกลม")
    print("  แต่การจะใช้มันต้องเข้าไม้ในนาทีแรกของข่าว ซึ่งเป็นจังหวะที่ spread")
    print("  กว้างที่สุดและ slippage แพงที่สุด ต้นทุนตรงนั้นยังไม่เคยวัด")

    trad = df[df.tradeable]
    print(f"\nอีเวนต์ที่ news.py บอกว่าอ่านออก (tradeable): {len(trad):,} "
          f"({100*len(trad)/len(df):.1f}%)")
    print("  หมายเหตุ: tradeable แปลว่าอ่านสถานการณ์ออก ไม่ได้แปลว่ามี edge")
    print(f"\nขนาดตัวอย่างคือข้อจำกัดหลัก: {len(df)} อีเวนต์ แบ่งเป็น 8 กลุ่ม")
    print("  เหลือกลุ่มละ 6-53 ครั้ง ซึ่งน้อยเกินกว่าจะสรุปอะไรได้")
    print("  ปฏิทินที่ดัมป์ไว้เริ่มที่ 2025-04-01 แต่ราคา M1 ย้อนถึง 2023-11")
    print("  -> ดัมป์ปฏิทินใหม่โดยตั้ง InpFrom เป็น 2022 จะได้อีเวนต์เพิ่มราว 3 เท่า")

    print("\nสิ่งที่ยังประเมินไม่ได้ และจะไม่เดา")
    print(f"  priced_in   : {df.priced_in.iloc[0]}")
    print(f"  US yields   : {NOT_ASSESSED_YIELDS}")
    print(f"  narrative   : {NOT_ASSESSED_NARRATIVE}")
    print(f"  positioning : ประเมินได้ -> {df.positioning.iloc[-1]}")

    out = Path("research/pilot/results"); out.mkdir(parents=True, exist_ok=True)
    df.to_csv(out / "news_assessments.csv", index=False)
    print(f"\nบันทึกไว้ที่ {out / 'news_assessments.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
