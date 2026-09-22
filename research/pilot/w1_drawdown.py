"""Drawdown arithmetic for W1, at a stated risk per trade.

The operator asked: at 1 % risk per trade, what drawdown should be expected, and
what risk per trade corresponds to a 30-40 % drawdown?

This computes it rather than asserting it, by Monte Carlo over the ACTUAL 76 net-R
outcomes rather than an assumed win/loss pattern, so time-stop exits and the real
spread of results are carried through.

THREE SCENARIOS, and the third is the one that matters most.

  A  point estimate. The edge is exactly the +0.2573 R measured.
  B  edge uncertainty. The measured edge has a day-clustered standard error of
     0.109, so a 95 % interval runs roughly +0.04 to +0.47 R. Each simulated
     path draws its own true edge from that uncertainty. This is the honest
     version, because sizing on a point estimate pretends the estimate is exact.
  C  NO EDGE. W1's expectancy is zero - the pass was luck. This is not
     pessimism, it is the live possibility: W1 has passed a cost test and
     nothing else, its forward shadow has produced zero events so far, and the
     slippage figure in the hour it actually trades has never been measured. The
     drawdown under C is what the operator is actually risking today.

SIZING is fixed-fractional and compounding: risk a constant PERCENTAGE of current
equity, so losses shrink the next bet. That is the standard and the least
dangerous of the common schemes. No Martingale, no averaging, no grid - those are
prohibited by CLAUDE.md section 8 and they are what turn a drawdown into a
wipeout.

NOTHING HERE IS A RECOMMENDATION TO TRADE. W1 is not a confirmed edge. These are
the consequences of a sizing choice IF the strategy behaves as measured, and under
scenario C, if it does not.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import core
import data as D
import w1_cost_test as W

PATHS = 20000
SEED = 20260922
RISKS = (0.005, 0.01, 0.02, 0.03, 0.05, 0.075, 0.10)
HORIZONS = (25, 76, 125, 250)      # trades: ~1yr, ~3yr, ~5yr, ~10yr at 25/yr
SE_EDGE = 0.109                    # day-clustered se of the measured expectancy


def max_dd(equity: np.ndarray) -> np.ndarray:
    """Largest peak-to-trough fall of each path, as a fraction."""
    peak = np.maximum.accumulate(equity, axis=1)
    return (1.0 - equity / peak).max(axis=1)


def simulate(returns: np.ndarray, risk: float, n_trades: int, paths: int,
             rng, shift: float = 0.0) -> np.ndarray:
    """Fixed-fractional compounding. `shift` moves the mean of the sampled
    returns, which is how scenarios B and C are produced from the same
    empirical shape."""
    draw = rng.choice(returns, size=(paths, n_trades), replace=True) + shift
    eq = np.cumprod(1.0 + risk * draw, axis=1)
    eq = np.concatenate([np.ones((paths, 1)), eq], axis=1)
    return eq


def report(name: str, returns: np.ndarray, rng, shift_fn=None):
    print("\n" + "=" * 96)
    print(name)
    print("=" * 96)
    print(f"{'เสี่ยง/ไม้':>10s}" + "".join(f"{f'{h} ไม้':>13s}" for h in HORIZONS)
          + f"{'โอกาส DD>30%':>14s}{'>40%':>9s}{'>50%':>9s}")
    for risk in RISKS:
        cells, p30, p40, p50 = [], None, None, None
        for h in HORIZONS:
            sh = shift_fn(rng, 1) if shift_fn else 0.0
            if shift_fn:
                # a separate true edge per path
                shifts = shift_fn(rng, PATHS)[:, None]
                draw = rng.choice(returns, size=(PATHS, h), replace=True) + shifts
                eq = np.cumprod(1.0 + risk * draw, axis=1)
                eq = np.concatenate([np.ones((PATHS, 1)), eq], axis=1)
            else:
                eq = simulate(returns, risk, h, PATHS, rng)
            dd = max_dd(eq)
            cells.append(f"{100*np.median(dd):5.1f}/{100*np.percentile(dd,95):5.1f}")
            if h == HORIZONS[2]:
                p30 = float(np.mean(dd > 0.30))
                p40 = float(np.mean(dd > 0.40))
                p50 = float(np.mean(dd > 0.50))
        print(f"{100*risk:9.1f}%" + "".join(f"{c:>13s}" for c in cells)
              + f"{100*p30:13.1f}%{100*p40:8.1f}%{100*p50:8.1f}%")
    print("  ตัวเลขในช่องคือ 'DD กลาง / DD ที่แย่ 1 ใน 20' หน่วยเปอร์เซ็นต์")
    print(f"  คอลัมน์โอกาสคิดที่ {HORIZONS[2]} ไม้ (ประมาณ 5 ปี ที่ 25 ไม้/ปี)")


def solve_risk(returns, rng, target_dd: float, n_trades: int, shift_fn=None,
               quantile: float = 0.95) -> float:
    """The risk per trade whose `quantile` max drawdown equals the target."""
    lo, hi = 0.001, 0.50
    for _ in range(40):
        mid = 0.5 * (lo + hi)
        if shift_fn:
            shifts = shift_fn(rng, 4000)[:, None]
            draw = rng.choice(returns, size=(4000, n_trades), replace=True) + shifts
        else:
            draw = rng.choice(returns, size=(4000, n_trades), replace=True)
        eq = np.cumprod(1.0 + mid * draw, axis=1)
        eq = np.concatenate([np.ones((4000, 1)), eq], axis=1)
        d = float(np.percentile(max_dd(eq), 100 * quantile))
        if d < target_dd:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def main() -> int:
    b5 = D.load_csv("data/XAUUSD_M5.csv")
    b15, _ = D.to_15m(b5)
    want = b15.t + 900
    pos = np.searchsorted(b5.t, want)
    nxt = np.where((pos < len(b5)) & (b5.t[np.minimum(pos, len(b5) - 1)] == want),
                   pos, -1)
    atr = core.atr(b15, W.ATR_N)
    cut = int(b15.t[-1]) - W.HOLDOUT_DAYS * 86400
    i_hi = int(np.searchsorted(b15.t, cut))
    sig = W.w1_signals(b15, atr, W.WARMUP, i_hi)
    rows = W.evaluate(sig, b5, b15, nxt, atr, 1.0)
    r = np.array([x["net"] for x in rows], float)

    print("=" * 96)
    print("W1 — DRAWDOWN ที่ระดับความเสี่ยงต่อไม้ต่าง ๆ")
    print("=" * 96)
    print(f"ใช้ผลจริง {len(r)} ไม้  ค่าเฉลี่ย {r.mean():+.4f} R  "
          f"sd {r.std(ddof=1):.4f}  ชนะ {100*np.mean(r>0):.0f}%")
    print(f"ความคลาดเคลื่อนของค่าเฉลี่ย (จัดกลุ่มรายวัน) = {SE_EDGE:.3f} R")
    print(f"ช่วงความเชื่อมั่น 95% ของ edge จริง: "
          f"{r.mean()-1.96*SE_EDGE:+.3f} ถึง {r.mean()+1.96*SE_EDGE:+.3f} R")
    print(f"เกิดประมาณ 25 ครั้ง/ปี  จำลอง {PATHS:,} เส้นทาง")
    print("การคิดขนาดไม้: เสี่ยงเป็นเปอร์เซ็นต์คงที่ของทุนปัจจุบัน (ทบต้น)")
    print("ไม่มีมาติงเกล ไม่มีถัวเฉลี่ย ไม่มีกริด")

    rng = np.random.default_rng(SEED)

    report("ฉาก A — สมมติว่า edge เท่ากับที่วัดได้พอดี (+0.2573 R)", r, rng)

    def shift_B(g, n):
        return g.normal(0.0, SE_EDGE, size=n)

    report("ฉาก B — ยอมรับว่า edge ไม่แน่นอน (แต่ละเส้นทางสุ่ม edge จริงของตัวเอง)",
           r, rng, shift_fn=shift_B)

    def shift_C(g, n):
        return np.full(n, -r.mean())

    report("ฉาก C — สมมติว่า W1 ไม่มี edge เลย (ค่าคาดหวัง = 0) <- ความเสี่ยงจริงวันนี้",
           r, rng, shift_fn=shift_C)

    print("\n" + "=" * 96)
    print("ตอบคำถามตรง ๆ")
    print("=" * 96)
    n5 = HORIZONS[2]
    print(f"\n[1] ที่ความเสี่ยงไม้ละ 1% ในช่วง {n5} ไม้ (~5 ปี):")
    for nm, sf in (("A ถ้า edge จริงเท่าที่วัด", None),
                   ("B ถ้ายอมรับความไม่แน่นอน", shift_B),
                   ("C ถ้าไม่มี edge เลย", shift_C)):
        if sf:
            shifts = sf(rng, PATHS)[:, None]
            draw = rng.choice(r, size=(PATHS, n5), replace=True) + shifts
        else:
            draw = rng.choice(r, size=(PATHS, n5), replace=True)
        eq = np.cumprod(1.0 + 0.01 * draw, axis=1)
        eq = np.concatenate([np.ones((PATHS, 1)), eq], axis=1)
        dd = max_dd(eq)
        fin = eq[:, -1] - 1.0
        print(f"    {nm:28s} DD กลาง {100*np.median(dd):5.1f}%   "
              f"แย่ 1/20 {100*np.percentile(dd,95):5.1f}%   "
              f"แย่ 1/100 {100*np.percentile(dd,99):5.1f}%   "
              f"ผลตอบแทนกลาง {100*np.median(fin):+6.1f}%")

    print(f"\n[2] ถ้าอยากให้ DD ที่แย่ 1 ใน 20 อยู่ที่ 30% และ 40% "
          f"ต้องเสี่ยงไม้ละเท่าไหร่ (ช่วง {n5} ไม้):")
    print(f"    {'ฉาก':32s}{'เพื่อ DD 30%':>16s}{'เพื่อ DD 40%':>16s}")
    for nm, sf in (("A edge จริงเท่าที่วัด", None),
                   ("B ยอมรับความไม่แน่นอน", shift_B),
                   ("C ไม่มี edge เลย", shift_C)):
        a = solve_risk(r, rng, 0.30, n5, shift_fn=sf)
        b = solve_risk(r, rng, 0.40, n5, shift_fn=sf)
        print(f"    {nm:32s}{100*a:15.1f}%{100*b:15.1f}%")

    print("\n" + "=" * 96)
    print("อ่านตัวเลขเหล่านี้อย่างไร")
    print("=" * 96)
    print("1. ฉาก C คือสิ่งที่คุณกำลังเสี่ยงอยู่จริง ณ วันนี้ ไม่ใช่ฉาก A")
    print("   W1 ผ่านแค่การทดสอบต้นทุน ยังไม่มีหลักฐานเดินหน้าแม้แต่เหตุการณ์เดียว")
    print("   และ slippage ในชั่วโมงที่มันเทรดจริงยังไม่เคยวัด")
    print("2. ขนาดไม้ที่ทำให้ DD ไปถึง 30-40% คือขนาดที่ 'ถ้าเราคิดผิด")
    print("   พอร์ตหายไปหนึ่งในสาม' ไม่ใช่ขนาดที่ควรเริ่ม")
    print("3. เกิดแค่ปีละ 25 ครั้ง ดังนั้น 5 ปีคือ 125 ไม้ การจะรู้ว่าคิดถูกหรือผิด")
    print("   ต้องใช้เวลาหลายปี และ DD จะมาถึงก่อนคำตอบ")
    print("4. ตัวเลขทั้งหมดนี้ไม่ใช่คำแนะนำให้เทรด และไม่ใช่การรับประกันอะไร")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
