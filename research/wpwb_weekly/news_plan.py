"""WPWB weekly news section — CLAUDE.md section 2 as a weekly plan.

(a) NEXT week: every USD HIGH release in the calendar with consensus,
    previous, and the hypothesis a surprise would set (or AMBIGUOUS).
(b) The fixed 8-scenario playbook (news.SCENARIOS). Under the current
    project verdict (NO TRADE: no directional edge confirmed; news
    acceptance/rejection failed in Part 25) every branch is a RECORD/STAND
    ASIDE instruction, never an entry.
(c) LAST week: each release classified by the existing newsdesk
    (news.assess) from M1 XAU and DXY reactions at 1/5/15/60 minutes.
Nothing here trades.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import bars as BR  # noqa: E402

sys.path.insert(0, str(BR.ROOT / "research" / "pilot"))
import calendar_feed  # noqa: E402
import news  # noqa: E402
import newsdesk  # noqa: E402

TH = 7 * 3600

SCENARIO_TH = {
    news.POS_CONFIRM: "ข่าวหนุนทอง + ราคายืนยัน",
    news.POS_REJECT: "ข่าวหนุนทอง + ราคาปฏิเสธ",
    news.NEG_CONFIRM: "ข่าวกดทอง + ราคายืนยัน",
    news.NEG_REJECT: "ข่าวกดทอง + ราคาปฏิเสธ",
    news.IN_LINE: "ออกใกล้ที่ตลาดคาด",
    news.CONFLICTING: "หลายข่าวพร้อมกันขัดกันเอง",
    news.SWEEP_BOTH: "กวาดสภาพคล่องสองด้าน",
    news.NO_TRADE: "สภาวะที่ไม่ควรเทรด",
}

# Fixed playbook. Changing it is a versioned amendment, never mid-week.
PLAYBOOK = [
    ("ก่อนข่าว (−15 นาที ถึง +1 นาที)",
     "ไม่เปิดสถานะใหม่; สถานะที่ถืออยู่ต้องมี SL อยู่แล้ว; ห้ามขยับ SL/ขนาดไม้ระหว่างถือเพื่อเลี่ยงการยอมรับว่าผิด (CLAUDE.md ข้อ 7)"),
    (SCENARIO_TH[news.POS_CONFIRM] + " / " + SCENARIO_TH[news.NEG_CONFIRM],
     "บันทึกเท่านั้น — การตามข่าวที่ราคายืนยันยังไม่มี edge ที่ผ่านการตรวจ (Part 25) จึงไม่เข้าไม้ตาม"),
    (SCENARIO_TH[news.POS_REJECT] + " / " + SCENARIO_TH[news.NEG_REJECT],
     "บันทึกเท่านั้น — ราคาปฏิเสธข่าวคือหลักฐานว่าตลาด price-in แล้ว แต่การเทรดสวนยังไม่มี edge ที่ผ่านการตรวจ"),
    (SCENARIO_TH[news.IN_LINE],
     "ข่าวไม่เปลี่ยนสมมติฐาน; กลับสู่กฎปกติหลัง 15 นาทีถ้า spread กลับสู่ปกติ"),
    (SCENARIO_TH[news.CONFLICTING], "ยืนดู 60 นาที; ไม่มีฝั่งที่อ่านได้"),
    (SCENARIO_TH[news.SWEEP_BOTH], "ยืนดู 60 นาที; ทั้งสองฝั่งถูกกวาด ไม่มีฝั่งที่อ่านได้"),
    (SCENARIO_TH[news.NO_TRADE],
     "ไม่เทรด — surprise คำนวณไม่ได้, spread เกินเกณฑ์, หรือปฏิกิริยาอยู่ในแถบ noise"),
    ("ทุกสถานการณ์ในสัปดาห์ที่พยากรณ์ว่าผันผวนสูง",
     "ใช้ตัวคูณขนาดไม้ vol_scale (≤ 1.0) — ลดความเสี่ยงได้อย่างเดียว ไม่เพิ่ม"),
]


def _sign_text(ev_name):
    s = calendar_feed.GOLD_SIGN.get(ev_name, "missing")
    if s is True:
        return "ออกสูงกว่าคาด → สมมติฐานกดทอง"
    if s is False:
        return "ออกสูงกว่าคาด → สมมติฐานหนุนทอง"
    if s is None:
        return "ไม่ตั้งสมมติฐานทิศ (ผลสองทาง หรือไม่ใช่ตัวขับทอง)"
    return "ไม่มีในตารางทิศ — ไม่ตั้งสมมติฐาน"


def next_week(cal, cut):
    """USD HIGH releases in [cut, cut + 1 week) and whether the calendar covers
    the whole week."""
    end = cut + BR.WEEK
    d = cal[(cal.currency == "USD") & (cal.importance == "HIGH")
            & (cal.epoch >= cut) & (cal.epoch < end)].copy()
    covered = int(cal.epoch.max()) >= end
    sig = calendar_feed.trailing_sigma(
        cal[(cal.currency == "USD") & (cal.importance == "HIGH")].reset_index(drop=True))
    hi = cal[(cal.currency == "USD") & (cal.importance == "HIGH")].reset_index(drop=True)
    hi["sigma"] = sig.values
    last_sigma = hi.dropna(subset=["sigma"]).groupby("event")["sigma"].last()
    rows = []
    for r in d.itertuples():
        rows.append({
            "เวลาไทย": pd.to_datetime(int(r.epoch) + TH, unit="s").strftime("%a %d %b %H:%M"),
            "ข่าว": r.event,
            "คาด (consensus)": r.forecast,
            "ครั้งก่อน": r.previous,
            "สมมติฐานถ้าออกผิดคาด": _sign_text(r.event),
            "มี sigma ย้อนหลัง": "มี" if r.event in last_sigma.index else "ไม่มี (จะเป็น NO_TRADE)",
        })
    return pd.DataFrame(rows), covered, int(cal.epoch.max())


def last_week(cal, cut_prev, cut):
    """Classify each USD HIGH release in [cut_prev, cut) with the newsdesk."""
    xau = BR.load_m1("XAUUSD")
    dxy = BR.load_m1("DXY")
    if xau is None or xau.t[-1] < cut - 3600:
        return None, "ไม่มีราคา M1 ครอบคลุมสัปดาห์ที่แล้ว — ต้องดึงข้อมูลใหม่"
    wk = cal[(cal.currency == "USD") & (cal.importance == "HIGH")
             & (cal.epoch >= cut_prev) & (cal.epoch < cut)]
    no_actual = sorted(set(wk[wk.actual.isna()].event))
    note = ("ok" if not no_actual else
            "ปฏิทินยังไม่มีค่า actual ของ: " + ", ".join(no_actual)
            + " — ต้องดัมป์ปฏิทินใหม่ (MT5 script CalendarDump) ข่าวเหล่านี้จึงยังจัดประเภทไม่ได้")
    pos = calendar_feed.positioning_series(cal)
    df = newsdesk.assess_all(cal, xau, dxy, pos)
    if df.empty:
        return df, note if no_actual else "ไม่มีข่าว USD HIGH ที่ประเมินได้ในสัปดาห์นี้"
    df = df[(df.epoch >= cut_prev) & (df.epoch < cut)].copy()
    if df.empty:
        return df, note if no_actual else "ไม่มีข่าว USD HIGH ที่ประเมินได้ในสัปดาห์นี้"
    df["เวลาไทย"] = pd.to_datetime(df.epoch + TH, unit="s").dt.strftime("%a %d %b %H:%M")
    df["สถานการณ์"] = df.scenario.map(SCENARIO_TH)
    return df, note


def positioning_line(cal, epoch):
    return calendar_feed.positioning_at(calendar_feed.positioning_series(cal), epoch)


def load_cal():
    return calendar_feed.load_calendar(str(BR.ROOT / "data" / "calendar.csv"))
