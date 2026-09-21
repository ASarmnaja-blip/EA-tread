"""
Minute momentum, pre-registered before it was run.

WHERE THIS CAME FROM, STATED HONESTLY. It was not designed. It appeared as a
CONTROL in news_residual.py: the same-clock, non-event control returned
+0.854 $/oz at t = +2.63 for holding 15 minutes in the direction of the
previous minute, against a round turn of $0.460. That is the first
after-cost-positive number anywhere in this program, and it was found by
looking rather than by asking. Numbers found that way are usually noise, so
this file states the test before running it.

THE HYPOTHESIS, fixed now:

    On XAUUSD M1, the sign of one completed minute predicts the direction of
    the NEXT 15 minutes, entering at the close of the signal minute.

THE PREDICTION, fixed now. For this to survive it must show ALL of:

    1. net expectancy after $0.460 round turn > 0 on the DEVELOPMENT half
    2. the same sign on the HELD-OUT half, and net > 0 there too
    3. better than a permuted-sign control by more than the cost
    4. present in more than one hour-of-day bucket, not only the release hours
    5. the effect must not depend on event windows - it is tested with them
       EXCLUDED, since the control that produced it was non-event by design

If any of those fails, it is recorded as a failed candidate and not adjusted.
No parameter here will be changed after seeing a result. The horizon is 15
minutes because that is the horizon the control used; other horizons are
reported for information only and may not be used to rescue the hypothesis.

Windows do not overlap: sampling every bar would reuse the same minutes 15
times and inflate confidence by roughly the square root of that.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import calendar_feed
import data as D

COST = 0.460               # $/oz round turn: measured spread + assumed slippage
HORIZON = 15               # [DEF] declared, from the control that raised it
OTHER_HORIZONS = (5, 30, 60)   # information only
EVENT_EXCLUDE_MIN = 60     # [DEF] minutes either side of a USD HIGH release
SPLIT = 0.70               # [DEF] time-ordered
SEED = 20260921


def stats(x: np.ndarray) -> tuple[float, float, float]:
    n = len(x)
    if n < 30:
        return np.nan, np.nan, n
    se = x.std(ddof=1) / np.sqrt(n)
    return float(x.mean()), float(x.mean() / se), n


def run(b: D.Bars, mask: np.ndarray, h: int, start: int) -> np.ndarray:
    """Non-overlapping: one observation every h+1 minutes."""
    c = b.c
    idx = np.arange(start, len(b) - h - 2, h + 1)
    idx = idx[mask[idx]]
    sig = np.sign(c[idx + 1] - c[idx])
    res = c[idx + 1 + h] - c[idx + 1]
    ok = sig != 0
    return (sig[ok] * res[ok])


def main() -> int:
    b = D.load_csv("data/XAUUSD_M1.csv")
    t = pd.to_datetime(b.t, unit="s", utc=True)
    n = len(b)
    print("=" * 92)
    print("MINUTE MOMENTUM - ประกาศสมมติฐานไว้ก่อนแล้วจึงทดสอบ")
    print("=" * 92)
    print(f"M1 {n:,} แท่ง  {t[0]:%Y-%m-%d} ถึง {t[-1]:%Y-%m-%d}")

    keep = np.ones(n, bool)
    try:
        cal = calendar_feed.load_calendar("data/calendar.csv")
        rows = calendar_feed.build_events(cal, "USD", ("HIGH",))
        ev = np.array(sorted(r.epoch for r in rows if r.usable), dtype=np.int64)
        bt = b.t.astype(np.int64)
        nxt = np.searchsorted(ev, bt, "left")
        prv = nxt - 1
        to_n = np.where(nxt < len(ev), (ev[np.minimum(nxt, len(ev)-1)] - bt)/60, 1e9)
        since = np.where(prv >= 0, (bt - ev[np.maximum(prv, 0)])/60, 1e9)
        keep = ~((to_n <= EVENT_EXCLUDE_MIN) | (since <= EVENT_EXCLUDE_MIN))
        print(f"ตัดหน้าต่างข่าว +/-{EVENT_EXCLUDE_MIN} นาที ออก "
              f"({100*(1-keep.mean()):.1f}% ของแท่ง)")
    except Exception as e:
        print("ไม่มีปฏิทิน ใช้ทุกแท่ง:", e)

    cut = int(n * SPLIT)
    dev_mask = keep.copy(); dev_mask[cut:] = False
    ho_mask = keep.copy(); ho_mask[:cut] = False
    print(f"ช่วงพัฒนา ถึง {t[cut]:%Y-%m-%d} | holdout หลังจากนั้น")
    print(f"ต้นทุนไป-กลับ ${COST:.3f}/oz\n")

    print(f"{'ช่วง':>12s}{'n':>7s}{'ได้เฉลี่ย $/oz':>16s}{'t':>8s}"
          f"{'หักต้นทุน':>12s}{'ชนะ%':>8s}")
    res = {}
    for label, m, s0 in (("ช่วงพัฒนา", dev_mask, 0), ("holdout", ho_mask, cut)):
        x = run(b, m, HORIZON, s0)
        mu, tt, nn = stats(x)
        res[label] = (mu, tt, nn, x)
        print(f"{label:>12s}{nn:7d}{mu:16.4f}{tt:8.2f}{mu-COST:12.4f}"
              f"{100*(x>0).mean():8.1f}")

    rng = np.random.default_rng(SEED)
    xd = res["ช่วงพัฒนา"][3]
    perm = np.array([np.mean(rng.permutation(np.sign(xd)) * np.abs(xd))
                     for _ in range(300)])
    print(f"\nตัวควบคุมสุ่มเครื่องหมาย (ช่วงพัฒนา): {perm.mean():+.4f} $/oz "
          f"+/- {perm.std():.4f}")

    print(f"\nแยกตามชั่วโมง UTC (ช่วงพัฒนา, ถือ {HORIZON} นาที)")
    hh = t.hour.to_numpy()
    idx = np.arange(0, cut - HORIZON - 2, HORIZON + 1)
    idx = idx[dev_mask[idx]]
    sig = np.sign(b.c[idx + 1] - b.c[idx])
    pnl = sig * (b.c[idx + 1 + HORIZON] - b.c[idx + 1])
    ok = sig != 0
    dfh = pd.DataFrame({"h": hh[idx][ok], "p": pnl[ok]})
    g = dfh.groupby("h")["p"].agg(["count", "mean", "std"])
    g["t"] = g["mean"] / (g["std"] / np.sqrt(g["count"]))
    g["net"] = g["mean"] - COST
    pos = int((g["net"] > 0).sum())
    print(f"  ชั่วโมงที่หักต้นทุนแล้วยังบวก: {pos} จาก {len(g)}")
    for h_, r in g.sort_values("mean", ascending=False).head(6).iterrows():
        print(f"    {h_:02d}:00  n={int(r['count']):5d}  {r['mean']:+8.4f} $/oz  "
              f"t={r['t']:+5.2f}  หักต้นทุน {r['net']:+8.4f}")

    print(f"\nขอบเขตอื่นเพื่อข้อมูล (ห้ามใช้กู้สมมติฐาน)")
    for h in OTHER_HORIZONS:
        x = run(b, dev_mask, h, 0)
        mu, tt, nn = stats(x)
        print(f"  ถือ {h:2d} นาที: n={nn:6d} {mu:+8.4f} $/oz t={tt:+5.2f} "
              f"หักต้นทุน {mu-COST:+8.4f}")

    print("\n" + "=" * 92)
    d_mu, d_t, _, _ = res["ช่วงพัฒนา"]
    h_mu, h_t, _, _ = res["holdout"]
    checks = {
        "1 ช่วงพัฒนาหักต้นทุนแล้วเป็นบวก": d_mu - COST > 0,
        "2 holdout เครื่องหมายเดียวกันและหักต้นทุนแล้วบวก":
            (np.sign(d_mu) == np.sign(h_mu)) and (h_mu - COST > 0),
        "3 ชนะตัวควบคุมสุ่มเกินต้นทุน": d_mu - perm.mean() > COST,
        "4 บวกในหลายชั่วโมง ไม่ใช่เฉพาะชั่วโมงข่าว": pos >= 3,
    }
    for k, v in checks.items():
        print(f"  {'ผ่าน' if v else 'ไม่ผ่าน'}  {k}")
    print()
    if all(checks.values()):
        print("สมมติฐานรอด -> เลื่อนเป็น shadow challenger เพื่อทดสอบ forward")
    else:
        print("สมมติฐานตก -> บันทึกเป็น candidate ที่ล้มเหลว ห้ามปรับพารามิเตอร์แล้วลองใหม่")
        print("ตัวเลข +0.854 ที่เห็นใน control เมื่อกี้จึงเป็นผลของการมองหลังเห็นข้อมูล")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
