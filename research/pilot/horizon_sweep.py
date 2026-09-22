"""The holding-horizon sweep, implementing Amendment 11.

TIME_STOP_M5 = 72 has sat under every result this project has produced. It was
chosen once and never varied, so every conclusion here - including four recorded
closures - describes what happens when a position is abandoned after six hours,
not the setups themselves.

This sweeps 12, 24, 48, 72, 144, 288 and 576 M5 bars and answers three questions
that were written down, with their directions, before the code ran:

  P1  Is horizon mismatch real? Predicted: the Spearman correlation between
      slack = log2(horizon / tool lookback) and matched excess is POSITIVE.
      One test.
  P2  Is Amendment 10's "nothing beyond chance" conditional on 72? Both global
      statistics recomputed at all seven horizons, Bonferroni for 7.
  P3  Does a matched horizon explain watchlist W2? Predicted: the excess of
      rsi:40/short and emax:50-200/long moves TOWARD ZERO at 144 and 576. If it
      does they are RETIRED from the watchlist, because horizon mismatch is a
      non-invertible cause.

RR stays 1:1 and the stop stays 1.5 ATR throughout. One variable moves at a time.

This file may not name a new candidate. Anything that looks good at a new horizon
is the extreme of 240 x 7 = 1,680 cells, and Amendment 11 section 5 declares no
CONFIRM stage for it.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import adaptive
import core
import data as D
import matched_control as MC
import tools_wide as TW
import wide_engine as WE
import wide_search as WS

HORIZONS = (12, 24, 48, 72, 144, 288, 576)      # Amendment 11 section 3
INCUMBENT = 72
W2 = {"rsi:40/short": 144, "emax:50-200/long": 576}   # matched horizons
DRAWS = 1000


# Tools whose parameter is NOT a lookback period, and which therefore cannot
# contribute to P1. Caught before any P1 number existed: `round:10` means a $10
# price step, `candle:2` a wick-to-body ratio, `psar:0.02` an acceleration
# factor. Reading those as periods would have put nonsense values of `slack` on
# the x-axis of the one test this amendment stakes its mechanism on.
NO_PERIOD = ("round", "candle", "psar")


def lookback_m5(tag: str) -> float | None:
    """The period in the tool's own name, in M5 bars, or None if it has none.

    A tool named `emax:50-200` looks back 200 M15 bars; the signal it emits is a
    statement about a move on that scale. Multiplying by three puts it in the
    same units as the time stop, which is what makes `slack` comparable across
    tools with different natural speeds.

    Where a name carries two numbers the larger is taken, because that is the
    slower component and the one that sets the scale: `macd:12-26` speaks to 26
    bars, not 12. Known understatements, accepted and not corrected because
    correcting them individually would be a free parameter: `ribbon` and `ultosc`
    are labelled by their middle span, and `fractal` by its half-window.
    """
    body = tag.split("/")[0]
    if ":" not in body:
        return None
    name, param = body.split(":", 1)
    if name in NO_PERIOD:
        return None
    nums = [float(x) for x in re.findall(r"\d+(?:\.\d+)?", param)]
    if not nums:
        return None
    return max(nums) * 3.0


def spearman(x: np.ndarray, y: np.ndarray) -> float:
    def rk(v):
        o = np.argsort(v, kind="mergesort")
        r = np.empty(len(v), float)
        r[o] = np.arange(len(v), dtype=float)
        return r
    a, b = rk(x), rk(y)
    a -= a.mean()
    b -= b.mean()
    d = np.sqrt((a * a).sum() * (b * b).sum())
    return float((a * b).sum() / d) if d > 0 else 0.0


def main() -> int:
    b5 = D.load_csv("data/XAUUSD_M5.csv")
    b15, _ = D.to_15m(b5)
    n = len(b15)
    want = b15.t + 900
    pos = np.searchsorted(b5.t, want)
    nxt = np.where((pos < len(b5)) & (b5.t[np.minimum(pos, len(b5) - 1)] == want),
                   pos, -1)
    atr = core.atr(b15, WS.ATR_N)
    prof = adaptive.hourly_spread_profile(b5)

    t0 = int(b15.t[0])
    i_sel_hi = int(np.searchsorted(b15.t, t0 + WS.SELECT_DAYS * 86400))

    news_ep = None
    try:
        import calendar_feed
        cal = calendar_feed.load_calendar("data/calendar.csv")
        rows = calendar_feed.build_events(cal, "USD", ("HIGH",))
        news_ep = np.array(sorted(r.epoch for r in rows if r.usable),
                           dtype=np.int64)
    except Exception as e:
        print(f"ปฏิทินข่าวโหลดไม่ได้ ({e})")

    print("=" * 108)
    print("HOLDING-HORIZON SWEEP (Amendment 11)")
    print("=" * 108)
    print(f"เวลาถือสูงสุดที่ทดสอบ (แท่ง M5): {HORIZONS}")
    print(f"= ชั่วโมง: {tuple(h/12 for h in HORIZONS)}")
    print(f"ค่าที่ใช้มาตลอดทั้งโปรเจกต์คือ {INCUMBENT} แท่ง = 6 ชั่วโมง")
    print("RR คงที่ 1:1 และ stop คงที่ 1.5 ATR ขยับตัวแปรทีละตัว\n")

    tools = TW.build(b15)
    cand, _pairs = WS.candidates(tools, n)
    st = MC.build_strata(b15, atr, prof, news_ep, WS.WARMUP, i_sel_hi)
    print(f"ชั้น A {len(cand)} candidate   ชั้นที่จับคู่ได้ {len(st.pool)}\n")

    rows = []                 # (tag, horizon, excess, t, se, n, slack)
    per_h = {}
    print(f"{'เวลาถือ':>10s}{'ชม.':>6s}{'ประเมินได้':>11s}{'ไม้กลาง':>9s}"
          f"{'ส่วนต่างกลาง':>14s}{'max|t|':>9s}{'วิกฤต':>8s}{'p(maxT)':>10s}"
          f"{'p(BJ)':>9s}")
    for H in HORIZONS:
        pre = WE.precompute(b5, b15, nxt, atr, WS.STOP_ATR, WS.RR, H,
                            WS.SPREAD_FALLBACK, WS.COMMISSION_RT,
                            WS.SLIP_PER_FILL, WS.SWAP_LONG)
        WE.attach_control(pre, st.key, st.pool, min_pool=WS.MIN_POOL)
        scored = {}
        for tag, ents in cand.items():
            r = WE.score(ents, pre, WS.WARMUP, i_sel_hi)
            if r is None or r["n"] < WS.MIN_TRADES_SELECT:
                continue
            if len(set(r["days"].tolist())) < WS.MIN_DAYS_SELECT:
                continue
            scored[tag] = r
        if len(scored) < 10:
            print(f"{H:10d}{H/12:6.0f}{len(scored):11d}   ประเมินได้น้อยเกินไป")
            continue
        fp = WE.family_permutation(scored, draws=DRAWS)
        per_h[H] = (scored, fp)
        nm, mu, tv = fp["names"], fp["mu"], fp["t"]
        ns = [scored[k]["n"] for k in nm]
        print(f"{H:10d}{H/12:6.0f}{len(scored):11d}{int(np.median(ns)):9d}"
              f"{np.median(mu):14.5f}{np.abs(tv).max():9.3f}{fp['crit']:8.3f}"
              f"{fp['p_fwer'].min():10.4f}{fp['p_bj']:9.4f}")
        for j, k in enumerate(nm):
            lb = lookback_m5(k)
            if lb:
                rows.append((k, H, float(mu[j]), float(tv[j]),
                             float(fp["se"][j]), scored[k]["n"],
                             float(np.log2(H / lb))))

    # ------------------------------------------------------------------ P2
    zb = core.bonferroni_z(len(per_h))
    alpha = 0.05 / max(1, len(per_h))
    print("\n" + "=" * 108)
    print(f"P2 — ผลสรุป 'ไม่มีอะไรเกินความบังเอิญ' ขึ้นกับเลข 72 หรือไม่")
    print("=" * 108)
    print(f"ทดสอบ {len(per_h)} เวลาถือ -> Bonferroni ที่ alpha {alpha:.4f}")
    hit = []
    for H, (sc, fp) in per_h.items():
        s_ok = fp["p_fwer"].min() < alpha
        b_ok = fp["p_bj"] < alpha
        print(f"  {H:4d} แท่ง ({H/12:4.0f} ชม.)  max|t| p={fp['p_fwer'].min():.4f}"
              f"{' <- มีนัยสำคัญ' if s_ok else '':14s}"
              f"  Berk-Jones p={fp['p_bj']:.4f}"
              f"{' <- มีนัยสำคัญ' if b_ok else ''}")
        if s_ok or b_ok:
            hit.append(H)
    if not hit:
        print("\nไม่มีเวลาถือใดที่ให้สัญญาณระดับตระกูล")
        print("-> คำปิดของ Amendment 10 แข็งขึ้นจาก 'ไม่มีอะไรที่ 6 ชั่วโมง'")
        print("   เป็น 'ไม่มีอะไรที่เวลาถือใดเลยตั้งแต่ 1 ชั่วโมงถึง 48 ชั่วโมง'")
        print("   ซึ่งเป็นคำกล่าวที่กว้างกว่าเดิมมาก")
    else:
        print(f"\nมีสัญญาณที่เวลาถือ {hit} -> ทุกข้อสรุปก่อนหน้านี้เป็นจริงเฉพาะที่ 72")
        print("นั่นคือผลลัพธ์ ไม่ใช่ใบอนุญาตให้ไปไล่ตาม candidate ในช่องนั้น")
        print("(Amendment 11 ข้อ 5: ห้ามตั้งชื่อ candidate ใหม่จากไฟล์นี้)")

    # ------------------------------------------------------------------ P1
    print("\n" + "=" * 108)
    print("P1 — สมมติฐาน 'ความยาวคลื่นไม่ตรงกัน' ทำนายว่าความสัมพันธ์เป็นบวก")
    print("=" * 108)
    if len(rows) < 50:
        print("ข้อมูลน้อยเกินไป -> NOT ASSESSED")
    else:
        tags = np.array([r[0] for r in rows])
        Hs = np.array([r[1] for r in rows], float)
        ex = np.array([r[2] for r in rows], float)
        slack = np.array([r[6] for r in rows], float)
        rho = spearman(slack, ex)
        print(f"จำนวนช่อง {len(rows):,}  slack จาก {slack.min():+.2f} ถึง "
              f"{slack.max():+.2f}")
        print(f"Spearman rho ระหว่าง slack กับ ส่วนต่าง = {rho:+.4f}")
        print("(slack < 0 = ปิดไม้ก่อนที่เครื่องมือจะมองย้อนหลังครบรอบของมันเอง)")
        # permutation: shuffle slack WITHIN horizon, so the correlation is judged
        # against the same clustering rather than against a free-for-all
        rng = np.random.default_rng(20260922)
        null = np.empty(2000)
        for i in range(2000):
            s2 = slack.copy()
            for H in np.unique(Hs):
                m = Hs == H
                s2[m] = rng.permutation(s2[m])
            null[i] = spearman(s2, ex)
        p_one = (np.sum(null >= rho) + 1.0) / (len(null) + 1.0)
        print(f"สลับ slack ภายในเวลาถือเดียวกัน 2,000 รอบ: "
              f"ค่ากลาง {np.median(null):+.4f}  p ด้านเดียว = {p_one:.4f}")

        # A SECOND, more conservative null, because the first one is too narrow.
        # Each tool contributes seven cells - one per horizon - so 1,505 cells
        # are not 1,505 independent observations; the effective count is closer
        # to the 233 tools. Shuffling slack within a horizon breaks the horizon
        # clustering but leaves each tool's block of seven intact in the
        # observed data while scrambling it in the null, which flatters the
        # result. This null instead permutes the LOOKBACK LABEL across tools,
        # keeping every tool's seven-cell profile whole, so the test asks
        # whether a tool's OWN lookback predicts its horizon profile.
        uniq_tags = sorted(set(tags.tolist()))
        lb_of = {t: lookback_m5(t) for t in uniq_tags}
        idx_of = {t: np.nonzero(tags == t)[0] for t in uniq_tags}
        null2 = np.empty(2000)
        lbs = np.array([lb_of[t] for t in uniq_tags], float)
        for i in range(2000):
            perm = rng.permutation(lbs)
            s3 = np.empty_like(slack)
            for j, t in enumerate(uniq_tags):
                ii = idx_of[t]
                s3[ii] = np.log2(Hs[ii] / perm[j])
            null2[i] = spearman(s3, ex)
        p_two = (np.sum(null2 >= rho) + 1.0) / (len(null2) + 1.0)
        print(f"สลับ 'รอบมองย้อน' ข้ามเครื่องมือ (คุมการซ้ำของเครื่องมือเดียวกัน) "
              f"2,000 รอบ:")
        print(f"   ค่ากลาง {np.median(null2):+.4f}  p ด้านเดียว = {p_two:.4f}"
              f"  <- ตัวนี้เข้มกว่าและเป็นตัวตัดสิน")
        print(f"   หมายเหตุ: rho = {rho:+.4f} อธิบายความแปรปรวนได้เพียงราว "
              f"{100*rho**2:.1f}% เป็นผลที่จริงแต่เล็ก")
        p_one = max(p_one, p_two)
        if rho > 0 and p_one < 0.05:
            print("\n-> P1 ผ่าน ทิศทางตรงตามที่ทำนายไว้")
            print("   ความยาวคลื่นไม่ตรงกันเป็นคำอธิบายที่มีหลักฐานรองรับ")
        elif rho > 0:
            print("\n-> ทิศทางถูก แต่ไม่มีนัยสำคัญ -> ยังไม่ยืนยัน")
        else:
            print("\n-> P1 ไม่ผ่าน เครื่องหมายกลับทิศจากที่ทำนาย")
            print("   ตาม Amendment 11 ข้อ 6 ให้ถอนคำอธิบาย 'ความยาวคลื่นไม่ตรงกัน'")
            print("   ออกจากบันทึกของ Amendment 09")
        # the same relationship restricted to the slow tools that motivated it
        slow = slack < 0
        if slow.sum() > 30:
            print(f"\nเฉพาะช่องที่ slack < 0 ({int(slow.sum()):,} ช่อง): "
                  f"rho = {spearman(slack[slow], ex[slow]):+.4f}")

    # ------------------------------------------------------------------ P3
    print("\n" + "=" * 108)
    print("P3 — ทดสอบเพื่อ 'ปลดระวาง' watchlist W2 ไม่ใช่เพื่อเลื่อนขั้น")
    print("=" * 108)
    z3 = core.bonferroni_z(2)
    print(f"ทำนายไว้ล่วงหน้า: ที่เวลาถือที่ตรงกับรอบมองย้อนของมัน ส่วนต่างจะขยับเข้าหาศูนย์")
    print(f"ถ้าเป็นจริง = การแพ้มาจากความยาวคลื่น ซึ่งกลับด้านไม่ได้ -> ปลดออกจาก watchlist\n")
    for tag, Hm in W2.items():
        lb = lookback_m5(tag)
        print(f"{tag}   รอบมองย้อน {lb:.0f} แท่ง M5   เวลาถือที่ตรงกัน {Hm}")
        line = []
        for H in HORIZONS:
            if H not in per_h:
                continue
            sc, fp = per_h[H]
            if tag not in sc:
                line.append(f"{H}:ไม้น้อย")
                continue
            j = fp["names"].index(tag)
            line.append(f"{H}:{fp['mu'][j]:+.4f}(n={sc[tag]['n']},t={fp['t'][j]:+.2f})")
        print("   ส่วนต่างตามเวลาถือ: " + "  ".join(line))
        got = [(H, per_h[H][1]) for H in (INCUMBENT, Hm)
               if H in per_h and tag in per_h[H][0]]
        if len(got) == 2:
            (_, f0), (_, f1) = got
            e0 = f0["mu"][f0["names"].index(tag)]
            e1 = f1["mu"][f1["names"].index(tag)]
            # A bare `abs(e1) < abs(e0)` reported "moved toward zero" for a
            # change of 0.0006 on a value of 0.24, which is rounding noise
            # dressed as evidence. The prediction was that the excess moves
            # toward zero, so it needs a threshold: a reduction of at least 30%
            # to count as partial, 50% to count as explained.
            ratio = abs(e1) / abs(e0) if e0 else float("nan")
            print(f"   ที่ {INCUMBENT} = {e0:+.4f}   ที่ {Hm} = {e1:+.4f}   "
                  f"เหลือ {100*ratio:.1f}% ของขนาดเดิม")
            if ratio <= 0.50:
                print("   -> ส่วนต่างหายไปกว่าครึ่ง อ่านว่าการแพ้มาจากความยาวคลื่น")
                print("      -> ปลดออกจาก watchlist ตาม Amendment 11 ข้อ 4 (P3)")
            elif ratio <= 0.70:
                print("   -> ลดลงอย่างมีความหมายแต่ไม่ถึงครึ่ง ยังสรุปไม่ได้")
            else:
                print("   -> ไม่ลด (เปลี่ยนแปลงในระดับปัดเศษ)")
                print("      -> P3 ไม่ผ่านสำหรับตัวนี้ ความยาวคลื่นไม่ใช่คำอธิบาย")
                print("      -> คงอยู่ใน watchlist และต้องแก้บันทึกกลไกที่แนบไว้")
            prof_e = [per_h[H][1]["mu"][per_h[H][1]["names"].index(tag)]
                      for H in HORIZONS if H in per_h and tag in per_h[H][0]]
            if len(prof_e) >= 5:
                print(f"   ช่วงของส่วนต่างทั้ง 7 เวลาถือ: {min(prof_e):+.4f} ถึง "
                      f"{max(prof_e):+.4f}  -> "
                      f"{'แทบไม่ขึ้นกับเวลาถือ' if max(prof_e)-min(prof_e) < 0.10 else 'ขึ้นกับเวลาถือ'}")
        print()

    print("=" * 108)
    print("ไฟล์นี้ไม่ตั้งชื่อ candidate ใหม่ และไม่เปลี่ยนเวลาถือของเครื่องมือใด")
    print("ตาม Amendment 11 ข้อ 5  HOLDOUT 120 วันไม่ถูกอ่านในไฟล์นี้")
    print("\nสถานะคงเดิม: NO TRADE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
