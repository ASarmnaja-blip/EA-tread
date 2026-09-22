"""Direction-neutral re-score of the 24 inverse candidates, per Amendment 08 s4.

Amendment 07's raw search found longs positive and shorts negative across five
unrelated families, and the drift audit then measured why: a random long at the
same geometry earns +0.0656 R and a random short -0.0507 R, a gap larger than
any family's own. Raw expectancy on this sample is mostly a reading of the bull
market.

This re-scores every one of the 24 on EXCESS over a stratified
direction-matched placebo, so the drift is inside the control and cancels.

WHAT THIS RUN IS. Amendment 08 section 6.4 records it in advance as an
EXPLORATORY DIAGNOSTIC and not a confirmatory test, because the decision to
score on excess was made after the raw outcome had been seen. No result here can
establish an edge on this sample. A confirmatory claim needs forward data that
does not exist yet.

All 24 are re-run. Screening down to the three raw losers first is forbidden by
Amendment 08 section 6.4, because that would let the first look choose the
family for the second.

THE PREDICTION, from Amendment 08 section 4: no candidate reaches -0.092 R in
excess terms. The largest raw loser, post_news_chase/short at -0.1003, sits
against a random short of -0.0507, an excess near -0.050 - about half.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import adaptive
import core
import data as D
import inverse_search as IS
import matched_control as MC

N_BONF = 48        # Amendment 08 section 6.4: 24 candidates, second look


def main() -> int:
    b5 = D.load_csv("data/XAUUSD_M5.csv")
    b15, _ = D.to_15m(b5)
    want = b15.t + 900
    pos = np.searchsorted(b5.t, want)
    nxt = np.where((pos < len(b5)) & (b5.t[np.minimum(pos, len(b5) - 1)] == want),
                   pos, -1)
    atr = core.atr(b15, IS.ATR_N)
    prof = adaptive.hourly_spread_profile(b5)
    cut = int(b15.t[-1]) - IS.HOLDOUT_DAYS * 86400
    hi_i = int(np.searchsorted(b15.t, cut))
    lo_i = IS.MEAN_N + IS.ATR_N + 2

    news_ep = None
    try:
        import calendar_feed
        cal = calendar_feed.load_calendar("data/calendar.csv")
        rows = calendar_feed.build_events(cal, "USD", ("HIGH",))
        news_ep = np.array(sorted(r.epoch for r in rows if r.usable),
                           dtype=np.int64)
    except Exception as e:
        print(f"ปฏิทินข่าวโหลดไม่ได้ ({e}) -> ชั้นข่าวจะเป็น 0 ทั้งหมด")

    st = MC.build_strata(b15, atr, prof, news_ep, lo_i, hi_i)
    zb = core.bonferroni_z(N_BONF)

    print("=" * 104)
    print("DIRECTION-NEUTRAL RE-SCORE ของ 24 candidate (Amendment 08 ข้อ 4)")
    print("=" * 104)
    print("นี่คือการวินิจฉัยเชิงสำรวจ ไม่ใช่การทดสอบยืนยัน ตาม Amendment 08 ข้อ 6.4")
    print("เพราะเราเลือกวิธีวัดนี้หลังเห็นผลดิบแล้ว ผลที่ออกมาจึงยืนยัน edge ไม่ได้")
    print(f"ชั้นที่จับคู่ได้ {len(st.pool)} ชั้น  วาง placebo {MC.DRAWS_PER_ENTRY} "
          f"ตัวต่อหนึ่งไม้  seed {MC.SEED}")
    print(f"เกณฑ์ Bonferroni ที่ N={N_BONF}: |t| >= {zb:.3f}  "
          f"(จะรายงาน maxT ควบคู่ด้วย)\n")

    pat = IS.patterns(b15, atr, news_ep)
    print(f"{'candidate':34s}{'ไม้':>6s}{'จับคู่ไม่ได้':>12s}{'ของเอง':>9s}"
          f"{'control':>9s}{'ส่วนต่าง':>10s}{'se':>8s}{'t':>7s}")
    print("-" * 104)

    results = {}
    for fam, sigs in pat.items():
        if not sigs:
            print(f"  {fam:32s}   ไม่มีสัญญาณ -> NOT ASSESSED")
            continue
        for dname, dsel in (("long", 1), ("short", -1)):
            for sname, hrs_ok in (("allhrs", None), ("ldn-ny", IS.LONDON_NY)):
                s = [(i, d) for (i, d) in sigs if d == dsel]
                if hrs_ok is not None:
                    s = [(i, d) for (i, d) in s
                         if hrs_ok[0] <= ((int(b15.t[i]) // 3600) % 24)
                         < hrs_ok[1]]
                tag = f"{fam}/{dname}/{sname}"
                r = MC.matched_excess(s, st, b5, nxt, atr, IS.STOP_ATR,
                                      IS.RR, IS.TIME_STOP_M5)
                if r["n"] < IS.MIN_TRADES:
                    print(f"  {tag:32s}{r['n']:6d}{r.get('unmatched',0):12d}"
                          f"   ไม้น้อยกว่า {IS.MIN_TRADES} -> ไม่ประเมิน")
                    continue
                results[tag] = r
                print(f"  {tag:32s}{r['n']:6d}{r['unmatched']:12d}"
                      f"{r['own']:9.4f}{r['control']:9.4f}{r['excess']:10.4f}"
                      f"{r['se']:8.4f}{r['t']:7.2f}")

    print("-" * 104)
    if not results:
        print("ไม่มี candidate ที่ประเมินได้")
        return 0

    mt = MC.maxt_permutation(results)
    print(f"\nmaxT permutation {mt['draws']} รอบ: ค่าวิกฤต |t| ที่ 95% = "
          f"{mt['crit']:.3f}")
    print("(สลับเครื่องหมายทีละวัน วันเดียวกันสลับพร้อมกันทุก candidate "
          "จึงรักษาความสัมพันธ์ระหว่างกันไว้)\n")

    # Every candidate's p value, both tails. The search was pointed at the
    # losing tail, but a family of 24 has two tails and hiding the other one
    # would be choosing which result to report after seeing it.
    print("ตารางเต็ม เรียงตามขนาด |t| ทั้งสองทาง:")
    for tag, r in sorted(results.items(), key=lambda kv: -abs(kv[1]["t"])):
        print(f"  {tag:34s} ส่วนต่าง {r['excess']:+.4f}  t {r['t']:+.2f}  "
              f"p(maxT) {mt['p'].get(tag, float('nan')):.4f}  "
              f"{'เกินค่าวิกฤต' if abs(r['t']) >= mt['crit'] else ''}")

    neg = sorted(results.items(), key=lambda kv: kv[1]["excess"])
    print("\nเรียงจากส่วนต่างติดลบที่สุด (ยิ่งลบยิ่งเป็นผู้แพ้จริงหลังหัก drift):")
    for tag, r in neg[:8]:
        p = mt["p"].get(tag, float("nan"))
        ok_mt = abs(r["t"]) >= mt["crit"]
        ok_bf = abs(r["t"]) >= zb
        print(f"  {tag:34s} ส่วนต่าง {r['excess']:+.4f}  t {r['t']:+.2f}  "
              f"p(maxT) {p:.3f}  maxT {'ผ่าน' if ok_mt else 'ไม่ผ่าน'}  "
              f"Bonf {'ผ่าน' if ok_bf else 'ไม่ผ่าน'}")

    worst = neg[0]
    print(f"\nส่วนต่างที่ติดลบที่สุดคือ {worst[0]} ที่ {worst[1]['excess']:+.4f} R")
    print(f"เกณฑ์ที่ประกาศไว้: ต้องถึง {IS.GROSS_MAX:+.4f} R")
    reached = [t for t, r in results.items() if r["excess"] <= IS.GROSS_MAX]
    print(f"candidate ที่ถึงเกณฑ์: {len(reached)}")
    passed = [t for t in reached if abs(results[t]["t"]) >= mt["crit"]]
    print(f"และผ่าน maxT ด้วย: {len(passed)}")

    print("\n" + "=" * 104)
    if not passed:
        print("ไม่มี candidate ที่ทั้งแพ้เกินเกณฑ์และมีนัยสำคัญหลังคุมความหลากหลาย")
        print("ตาม Amendment 08 ข้อ 6.6 บันทึกว่า: ปิดสำหรับ 24 candidate นี้")
        print("บนกลุ่มข้อมูลนี้ และแบบจำลองการส่งคำสั่งนี้ - ขอบเขตแค่นี้ ไม่กว้างกว่านี้")
        print("ห้ามลองนิยามการจับคู่ใหม่หลังเห็นผลนี้ (Amendment 08 ข้อ 6.4)")
    else:
        print(f"มี {len(passed)} candidate ที่ผ่านทั้งสองด่าน:")
        for t in passed:
            print(f"  {t}  ส่วนต่าง {results[t]['excess']:+.4f}")
        print("ขั้นต่อไปตาม Amendment 08 ข้อ 6.3 คือต้องพิสูจน์ว่าตัวกลับด้าน")
        print("มี net เป็นบวกหลังหักต้นทุนจริงต่อไม้ ซึ่งส่วนต่างติดลบไม่ได้รับประกัน")
    print("\nสถานะคงเดิม: NO TRADE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
