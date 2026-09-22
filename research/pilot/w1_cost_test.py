"""W1's cost test, implementing Amendment 12.

W1 is `gap_continuation/short`: on M15, a gap down of at least 0.5 ATR fires a
short, entered at the next M5 open, 1.5 ATR stop, 1.5 ATR target, 72-bar time
stop. It is the only observation in this project that ever cleared a family-wise
threshold - excess +0.3483 R over a stratum-matched placebo on n=75, t +3.18,
p(maxT) 0.0330 - and no cost has ever been charged to it.

THE PRIMARY OUTPUT IS NOT THE NET EXPECTANCY. Gold gaps where the book is
thinnest: the Sunday open, the 21:00 UTC rollover, and data holes. Those are the
widest spreads of the week. The project's cost model uses a MEDIAN spread of
0.090, so the first question is whether W1's own entry bars carry anything like
that. If they carry five times it, the +0.2934 R gross was being charged a cost it
never paid, and the answer is arithmetic rather than a matter of judgement.

The second question decides whether n=75 means anything: if the 75 entries fall
on very few distinct weeks, they are closer to 75 observations of one recurring
event than to 75 independent trades, and the discovery t of +3.18 was overstated
by dependence.

Surviving is a PREREQUISITE, not confirmation. The discovery p-value is not
reused here; it belongs to the search that found it.
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
import matched_control as MC
import wide_engine as WE

# ---- the rule, frozen by Amendment 12 section 1. Nothing here may move. ----
GAP_ATR = 0.5
STOP_ATR = 1.5
RR = 1.0
TIME_STOP_M5 = 72
ATR_N = 14
WARMUP = 60

# ---- the measured cost model, Amendment 08 ----
SPREAD_FALLBACK = 0.090
COMMISSION_RT = 0.140
SLIP_PER_FILL = 0.0165
SWAP_SHORT = 0.0                # measured: a short pays no financing on XAUUSD
COST_MULTIPLIERS = (1.0, 1.5, 3.0, 7.0)

# ---- pass criteria, Amendment 12 section 4 ----
MIN_NET = 0.05
MIN_TRADES = 50
MIN_DAYS = 30
HOLDOUT_DAYS = 120


def w1_signals(b15: D.Bars, atr: np.ndarray, lo_i: int, hi_i: int):
    """Down-gap of at least 0.5 ATR -> short. Identical to the definition that
    produced the discovery, re-derived here rather than imported so the rule is
    visible in the file that tests it."""
    prev_c = np.concatenate(([b15.c[0]], b15.c[:-1]))
    gap = b15.o - prev_c
    out = []
    for i in range(max(lo_i, WARMUP), min(hi_i, len(b15) - 1)):
        a = atr[i]
        if not np.isfinite(a) or a <= 0:
            continue
        if gap[i] <= -GAP_ATR * a:
            out.append((i, -1))
    return out


def evaluate(sig, b5, b15, nxt, atr, mult: float):
    """Net per trade with the measured per-bar spread AT THE ENTRY BAR."""
    rows = []
    busy_until = -1
    for (i, d) in sig:
        k = int(nxt[i])
        if k < 0 or k <= busy_until:
            continue
        a = atr[i]
        if not np.isfinite(a) or a <= 0:
            continue
        entry = b5.o[k]
        risk = STOP_ATR * float(a)
        stop, target = entry - d * risk, entry + d * RR * risk
        px, why, nb = core.resolve(b5, k, d, entry, stop, target, TIME_STOP_M5)
        g = d * (px - entry) / risk
        sp = (float(b5.sp[k]) if b5.sp is not None and np.isfinite(b5.sp[k])
              and b5.sp[k] > 0 else SPREAD_FALLBACK)
        cost = mult * (sp + COMMISSION_RT + 2.0 * SLIP_PER_FILL)
        rows.append(dict(t=int(b5.t[k]), g=g, net=g - cost / risk, sp=sp,
                         risk=risk, why=why, nb=nb, atr=float(a)))
        busy_until = k + nb
    return rows


def clustered(vals, days):
    v = np.asarray(vals, float)
    dd = np.asarray(days, np.int64)
    mu = float(v.mean())
    grp = pd.Series(v - mu).groupby(dd).sum().to_numpy()
    g = len(grp)
    corr = g / (g - 1) if g > 1 else 1.0
    se = float(np.sqrt(corr * (grp ** 2).sum())) / len(v)
    return mu, se, g, mu - 1.96 * se, mu + 1.96 * se


def main() -> int:
    b5 = D.load_csv("data/XAUUSD_M5.csv")
    b15, _ = D.to_15m(b5)
    n = len(b15)
    want = b15.t + 900
    pos = np.searchsorted(b5.t, want)
    nxt = np.where((pos < len(b5)) & (b5.t[np.minimum(pos, len(b5) - 1)] == want),
                   pos, -1)
    atr = core.atr(b15, ATR_N)
    prof = adaptive.hourly_spread_profile(b5)
    cut = int(b15.t[-1]) - HOLDOUT_DAYS * 86400
    i_dev_hi = int(np.searchsorted(b15.t, cut))

    print("=" * 100)
    print("W1 COST TEST (Amendment 12) — gap_continuation/short")
    print("=" * 100)
    print("กฎที่แช่แข็งไว้: ช่องว่างราคาลงอย่างน้อย 0.5 ATR -> Short")
    print("stop 1.5 ATR  target 1.5 ATR (RR 1:1)  ถือไม่เกิน 72 แท่ง M5")
    print("ไม่มีพารามิเตอร์ใดขยับได้ในไฟล์นี้\n")

    sig = w1_signals(b15, atr, WARMUP, i_dev_hi)
    rows = evaluate(sig, b5, b15, nxt, atr, 1.0)
    if len(rows) < 10:
        print(f"ไม้น้อยเกินไป ({len(rows)}) -> ประเมินไม่ได้")
        return 0

    sp = np.array([r["sp"] for r in rows])
    ts = np.array([r["t"] for r in rows], np.int64)
    hrs = (ts // 3600) % 24
    dows = ((ts // 86400) + 4) % 7          # 0=Mon ... 6=Sun for epoch days
    days = ts // 86400
    weeks = ts // (7 * 86400)

    # --------------------------------------------------- 1. the spread question
    all_sp = b5.sp[np.isfinite(b5.sp) & (b5.sp > 0)] if b5.sp is not None else None
    print("=" * 100)
    print("ข้อ 1 — spread ตอนที่ W1 เข้าไม้ เทียบกับ spread ทั่วไป")
    print("=" * 100)
    print("นี่คือผลลัพธ์หลักของการทดสอบนี้ ไม่ใช่กำไรขาดทุน")
    qs = (10, 50, 75, 90, 99)
    print(f"\n{'':22s}" + "".join(f"{f'p{q}':>10s}" for q in qs) + f"{'เฉลี่ย':>10s}")
    print(f"{'ตอน W1 เข้าไม้':22s}"
          + "".join(f"{np.percentile(sp, q):10.4f}" for q in qs)
          + f"{sp.mean():10.4f}")
    if all_sp is not None and len(all_sp):
        print(f"{'ทุกแท่งในกราฟ':22s}"
              + "".join(f"{np.percentile(all_sp, q):10.4f}" for q in qs)
              + f"{all_sp.mean():10.4f}")
        ratio = float(np.median(sp) / np.median(all_sp))
        print(f"\nอัตราส่วนค่ากลาง: {ratio:.2f}x  "
              f"(W1 {np.median(sp):.4f} เทียบทั่วไป {np.median(all_sp):.4f})")
        print(f"แบบจำลองต้นทุนใช้ค่ากลาง {SPREAD_FALLBACK:.3f} — "
              f"{'สูงกว่าที่ W1 เจอจริง' if SPREAD_FALLBACK > np.median(sp) else 'ต่ำกว่าที่ W1 เจอจริง'}")
        if ratio > 2.0:
            print("-> spread ตอน W1 เข้าไม้กว้างกว่าปกติอย่างมีนัย ตามที่กลัวไว้")
        else:
            print("-> spread ตอน W1 เข้าไม้ไม่ได้กว้างกว่าปกติมาก ข้อกังวลนี้ตกไป")
    sp_over_risk = sp / np.array([r["risk"] for r in rows])
    print(f"spread คิดเป็นสัดส่วนของ R: ค่ากลาง {np.median(sp_over_risk):.4f}  "
          f"สูงสุด {sp_over_risk.max():.4f}")

    # ------------------------------------------- 2. are the 75 independent?
    print("\n" + "=" * 100)
    print("ข้อ 2 — ไม้ 75 ไม้นี้เป็นเหตุการณ์อิสระกันจริงหรือไม่")
    print("=" * 100)
    dow_names = ("จ", "อ", "พ", "พฤ", "ศ", "ส", "อา")
    print(f"ไม้ทั้งหมด {len(rows)}   วันที่ต่างกัน {len(set(days.tolist()))}   "
          f"สัปดาห์ที่ต่างกัน {len(set(weeks.tolist()))}")
    vc = pd.Series(dows).value_counts().sort_index()
    print("แยกตามวันในสัปดาห์: " + "  ".join(
        f"{dow_names[int(k)]} {v}" for k, v in vc.items()))
    vh = pd.Series(hrs).value_counts().sort_index()
    print("แยกตามชั่วโมง UTC:  " + "  ".join(f"{int(k):02d}:{v}" for k, v in vh.items()))
    step15 = 900
    prev_t = np.array([int(b15.t[i]) for (i, _) in
                       [(i, d) for (i, d) in sig
                        if int(nxt[i]) >= 0]][:len(rows)], np.int64)
    after_break = int(np.sum(np.diff(np.sort(prev_t)) > 4 * 3600))
    print(f"ไม้ที่อยู่หลังช่องว่างเวลายาวกว่า 4 ชั่วโมง (เปิดสัปดาห์/หลัง rollover): "
          f"ประมาณ {after_break} จาก {len(rows)}")
    top_hour = int(vh.idxmax())
    print(f"ชั่วโมงที่กระจุกที่สุดคือ {top_hour:02d}:00 UTC มี {int(vh.max())} ไม้ "
          f"({100*int(vh.max())/len(rows):.0f}%)")
    if len(set(weeks.tolist())) < 0.5 * len(rows):
        print("-> ไม้กระจุกอยู่ในไม่กี่สัปดาห์ ค่า t ที่ค้นพบสูงเกินจริงจากการพึ่งพากัน")
    else:
        print("-> กระจายอยู่หลายสัปดาห์พอสมควร")

    # --------------------------------------------------- 3. the cost test
    print("\n" + "=" * 100)
    print("ข้อ 3 — คิดค่าใช้จ่ายจริงแล้วเหลืออะไร")
    print("=" * 100)
    print("ต้นทุนต่อรอบ = spread ของแท่งนั้นจริง + คอมมิชชั่น 0.140 + slippage 0.033")
    print("Short ทองไม่เสียค่าถือข้ามคืน (วัดได้ว่าเป็นศูนย์)\n")
    gross = float(np.mean([r["g"] for r in rows]))
    print(f"{'ตัวคูณต้นทุน':>14s}{'net R':>10s}{'se':>9s}{'t':>7s}"
          f"{'ขอบล่าง 95%':>14s}{'ผ่าน +0.05?':>13s}")
    res = {}
    for m in COST_MULTIPLIERS:
        rr = evaluate(sig, b5, b15, nxt, atr, m)
        nets = [x["net"] for x in rr]
        dys = [x["t"] // 86400 for x in rr]
        mu, se, g, lo, hi = clustered(nets, dys)
        res[m] = (mu, se, lo, g)
        print(f"{m:14.1f}{mu:10.4f}{se:9.4f}{mu/se if se>0 else float('nan'):7.2f}"
              f"{lo:14.4f}{'ผ่าน' if mu >= MIN_NET else 'ไม่ผ่าน':>13s}")
    print(f"\nกำไรดิบก่อนหักอะไรเลย {gross:+.4f} R")
    print(f"ต้นทุนกินไป {gross - res[1.0][0]:.4f} R ที่ 1x")

    # ------------------------------- 4. matched excess under the corrected control
    print("\n" + "=" * 100)
    print("ข้อ 4 — ส่วนต่างจากคู่เทียบ เมื่อใช้คู่เทียบที่ตัดวันนั้นออก")
    print("=" * 100)
    st = MC.build_strata(b15, atr, prof, None, WARMUP, i_dev_hi)
    pre = WE.precompute(b5, b15, nxt, atr, STOP_ATR, RR, TIME_STOP_M5,
                        SPREAD_FALLBACK, COMMISSION_RT, SLIP_PER_FILL,
                        0.0, SWAP_SHORT)
    WE.attach_control(pre, st.key, st.pool, min_pool=30)
    sc = WE.score(sig, pre, WARMUP, i_dev_hi)
    if sc is None:
        print("จับคู่ไม่ได้ -> NOT ASSESSED")
        ex_ok = False
        ex_mu = float("nan")
    else:
        uniq = {d: j for j, d in enumerate(sorted(set(sc["days"].tolist())))}
        ix = np.asarray([uniq[int(d)] for d in sc["days"]])
        ex_mu, ex_se, ex_t = WE.day_t(sc["excess"], ix, len(uniq))
        print(f"ไม้ที่จับคู่ได้ {sc['n']}  จับคู่ไม่ได้ {sc['unmatched']}")
        print(f"ส่วนต่าง {ex_mu:+.4f} R  se {ex_se:.4f}  t {ex_t:+.2f}")
        print(f"เทียบกับตอนค้นพบที่ +0.3483 (คู่เทียบแบบสุ่ม 20 ตัว ไม่ตัดวัน)")
        ex_ok = ex_mu > 0
        print(f"-> {'ยังเป็นบวก' if ex_ok else 'กลับเป็นลบ คู่เทียบเดิมปนเปื้อน'}")

    # --------------------------------------------------- verdict
    mu1, se1, lo1, g1 = res[1.0]
    mu15 = res[1.5][0]
    checks = {
        f"1 net ที่ 1x >= +0.05 (ได้ {mu1:+.4f})": mu1 >= MIN_NET,
        f"2 net ที่ 1.5x >= +0.05 (ได้ {mu15:+.4f})": mu15 >= MIN_NET,
        f"3 ไม้ >= {MIN_TRADES} (ได้ {len(rows)})": len(rows) >= MIN_TRADES,
        f"4 วันที่มีไม้ >= {MIN_DAYS} (ได้ {g1})": g1 >= MIN_DAYS,
        f"5 ขอบล่าง 95% เหนือศูนย์ (ได้ {lo1:+.4f})": lo1 > 0,
        f"6 ส่วนต่างยังเป็นบวก (ได้ {ex_mu:+.4f})": bool(ex_ok),
    }
    print("\n" + "=" * 100)
    print("ตรวจตามเกณฑ์ที่ประกาศไว้ใน Amendment 12 ข้อ 4")
    print("=" * 100)
    for k, v in checks.items():
        print(f"  {'ผ่าน  ' if v else 'ไม่ผ่าน'} {k}")
    ok = all(checks.values())

    # ------------------------------- the holdout, as a caveated secondary only
    print("\n" + "=" * 100)
    print("ช่วง holdout 120 วัน — เป็นการตรวจประกอบ ไม่ใช่การยืนยัน")
    print("=" * 100)
    print("Amendment 05 ใช้ช่วงนี้วินิจฉัยความล้มเหลวของ ORDERLY_TREND ไปแล้ว")
    print("จึงไม่ใช่ข้อมูลสะอาด และคาดไว้ล่วงหน้าว่าจะมีแค่ 8-10 เหตุการณ์\n")
    sh = w1_signals(b15, atr, i_dev_hi, len(b15) - 1)
    rh = evaluate(sh, b5, b15, nxt, atr, 1.0)
    if len(rh) < 3:
        print(f"เหตุการณ์ {len(rh)} ครั้ง -> น้อยเกินกว่าจะพูดอะไรได้ NOT ASSESSED")
    else:
        nets = [x["net"] for x in rh]
        print(f"เหตุการณ์ {len(rh)} ครั้ง  net เฉลี่ย {np.mean(nets):+.4f} R  "
              f"ดิบ {np.mean([x['g'] for x in rh]):+.4f}  "
              f"ชนะ {100*np.mean(np.array(nets) > 0):.0f}%")
        print(f"spread ตอนเข้า: ค่ากลาง {np.median([x['sp'] for x in rh]):.4f}")
        print("-> อ่านได้แค่ว่า 'สอดคล้อง' หรือ 'ไม่สอดคล้อง' ห้ามเรียกว่ายืนยัน")

    print("\n" + "=" * 100)
    if ok:
        print("W1 ผ่านการทดสอบต้นทุน -> เป็นเงื่อนไขเบื้องต้นที่ผ่าน ยังไม่ใช่การยืนยัน")
        print("ขั้นต่อไปตาม Amendment 12 ข้อ 6 คือ forward shadow 26 สัปดาห์")
        print("หรือ 30 เหตุการณ์ แล้วแต่อะไรมาทีหลัง หยุดก่อนไม่ได้ ยืดไม่ได้")
    else:
        print("W1 ไม่ผ่านการทดสอบต้นทุน -> บันทึกว่าตายใน watchlist")
        print("ตาม Amendment 12 ข้อ 7 ห้ามขยับเกณฑ์ช่องว่างราคา stop target เวลาถือ")
        print("และห้ามตัดไม้ที่ spread แย่ออกหลังเห็นผลแล้ว")
        print("ขั้นต่อไปคือตัววินิจฉัยเส้นทางที่เป็นกลางต่อเรขาคณิต ไม่ใช่การกู้ W1")
    print("\nสถานะคงเดิม: NO TRADE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
