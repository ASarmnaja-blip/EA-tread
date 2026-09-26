"""Bar-by-bar walk with a FINE, unrestricted stop/target grid per period.

The operator asked for a version of the fixed 8,250-cell walk (Amendment 14)
that is not limited to five discrete stop values and five discrete target
values, with explicit permission to tune parameters to win each period's
market more. This builds that, within the six mechanical setup families
CLAUDE.md section 3 declares (the operator's own stated scope) - it widens HOW
FINELY each family's geometry is searched, not WHICH families exist.

WHAT THIS BUILDS ON: only verified primitives - core.resolve/core.atr,
mtf_engine.setup_signals (the six families) and mtf_engine.resolve_plane (the
fast stop/target-plane resolver, checked against core.resolve on 10,000 cases
with zero disagreements in test_mtf_engine.py). None of Codex's paused,
untested weekly_evolution_grid.py / compound_bar_replay.py is used or trusted.

THE GRID: stop in {0.50, 0.75, ..., 4.00} ATR (15 values), target in
{0.25, 0.50, ..., 5.00} R (20 values) = 300 combinations per (family,
timeframe) pair, x 6 families x 5 timeframes = 9,000 combinations - a finer,
not smaller, search than Amendment 14's 25 per family/timeframe. Market entry
only for this pass (the operator's phrasing centres on stop/target tuning;
entry-mode/expiry tuning is a separate, larger axis and is left out here,
stated explicitly rather than silently dropped).

TWO RESULTS ARE REPORTED FOR EVERY MONTH, side by side, because this project
has twice already measured the gap between them (Amendment 20: an
annually-reselected best-of-prior-year tool lost -46.277 R across three of
four forward years; Amendment 10: every CONFIRM winner from a 6,480-cell
search flipped sign on unseen data):

  1. IN-SAMPLE CEILING - the single best (family, timeframe, stop, target)
     for THAT month, chosen with full hindsight of that month's own outcomes.
     This is the "trace/guideline" the operator asked for: the sharpest
     description of what that month's market actually rewarded.
  2. WALK-FORWARD REALITY - the combination ranked best using ONLY the prior
     N months, applied mechanically into the next month with no look-ahead,
     exactly as Amendments 15/16 required. This is the honest forecast-style
     number for the same period.

Real Demo cost model throughout (spread + 0.140 commission + 0.033 slippage
round-turn; long swap 0.5493/night, short swap 0). Read-only against MT5/the
canonical file; no order-sending code anywhere in this module.
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import canonical_history as ch
import core
import data as D
import mtf_engine as E

DAY = 86400
STOPS = tuple(round(0.5 + 0.25 * i, 2) for i in range(15))     # 0.50 .. 4.00
TARGETS = tuple(round(0.25 + 0.25 * i, 2) for i in range(20))  # 0.25 .. 5.00
FAMILIES = E.SETUPS
TIMEFRAMES = E.TIMEFRAMES
MIN_TRADES_MONTH = 3
LOOKBACK_MONTHS = 3            # walk-forward selection window
EMBARGO_S = 24 * 3600 + E.TIME_STOP_M5 * 300   # matches the longest single
                                               # exit path at market entry
                                               # (no limit-entry expiry here)


def month_key(t: int) -> tuple[int, int]:
    d = datetime.fromtimestamp(t, timezone.utc)
    return d.year, d.month


def month_bounds(y: int, m: int) -> tuple[int, int]:
    lo = datetime(y, m, 1, tzinfo=timezone.utc)
    y2, m2 = (y, m + 1) if m < 12 else (y + 1, 1)
    hi = datetime(y2, m2, 1, tzinfo=timezone.utc)
    return int(lo.timestamp()), int(hi.timestamp())


def month_range(t0: int, t1: int):
    y, m = month_key(t0)
    out = []
    while True:
        lo, hi = month_bounds(y, m)
        if lo >= t1:
            break
        out.append((y, m, lo, min(hi, t1)))
        y, m = (y, m + 1) if m < 12 else (y + 1, 1)
    return out


def build_fills(b5: D.Bars, bs: D.Bars, nxt: np.ndarray, atr_s: np.ndarray,
                setup: str) -> list[tuple[int, int, float, float]]:
    """(entry_bar_k, direction, entry_price, atr) for every signal, market
    entry at the next bar's open - no limit/expiry variant in this pass."""
    ctx = core.Ctx(bs, nxt)
    sig = E.setup_signals(setup, ctx)
    out = []
    for (i, d) in sig:
        k0 = int(nxt[i])
        a = atr_s[i]
        if k0 < 0 or not np.isfinite(a) or a <= 0:
            continue
        out.append((k0, d, float(b5.o[k0]), float(a)))
    return out


def _rollover(t0: int, t1: int) -> int:
    if hasattr(E, "rollover_nights"):
        return E.rollover_nights(t0, t1)
    return _rollover_nights_fallback(t0, t1)


def planes_for_fills(b5: D.Bars, fills):
    """resolve_plane ONCE per fill, over the FULL stop/target grid at once -
    this is the whole point of resolve_plane: one forward pass (building the
    cumulative favourable/adverse-excursion arrays) answers every (stop,
    target) pair via cheap lookups inside it. Calling it once per (fill,
    stop, target) triple instead - as an earlier draft of this file did -
    would have repeated the expensive forward pass 300x for no reason."""
    out = []
    for (k0, d, entry, a) in fills:
        plane = E.resolve_plane(b5, k0, d, entry, a, STOPS, TARGETS,
                                E.TIME_STOP_M5)
        out.append((k0, d, entry, a, plane))
    return out


def trades_for_geometry(b5: D.Bars, fill_planes, stop_atr: float,
                        target_r: float):
    """One-position-at-a-time trade list for one fixed (stop, target), reusing
    the pre-computed plane per fill. Overlap filtering (busy_until) is still
    done PER (stop, target) here, since two different geometries close their
    positions on different bars."""
    out = []
    busy_until = -1
    for (k0, d, entry, a, plane) in fill_planes:
        if k0 <= busy_until:
            continue
        risk = stop_atr * a
        g, why, nb = plane[(stop_atr, target_r)]
        kx = min(k0 + nb, len(b5) - 1)
        sp = (float(b5.sp[k0]) if b5.sp is not None and np.isfinite(b5.sp[k0])
              and b5.sp[k0] > 0 else E.SPREAD_FALLBACK)
        cost = sp + E.COMMISSION_RT + 2 * E.SLIP_PER_FILL
        net = g - cost / risk
        if d > 0 and E.SWAP_LONG:
            nights = _rollover(int(b5.t[k0]), int(b5.t[kx]))
            net -= nights * E.SWAP_LONG / risk
        out.append((int(b5.t[k0]), net, int(b5.t[kx])))
        busy_until = k0 + nb
    return out


def _rollover_nights_fallback(t0: int, t1: int) -> int:
    h0 = (t0 // 3600) % 24
    cur = t0 - (t0 % 3600) + ((E.ROLLOVER_H - h0) % 24) * 3600
    n = 0
    while cur <= t1:
        n += 1
        cur += DAY
    return n


def main() -> int:
    print("=" * 108)
    print("FINE-GRID BAR-BY-BAR WALK — ไม่จำกัดที่กริดตายตัว 8,250 ช่อง")
    print("=" * 108)
    print(f"stop: {len(STOPS)} ค่า ({STOPS[0]}-{STOPS[-1]} ATR)   "
          f"target: {len(TARGETS)} ค่า ({TARGETS[0]}-{TARGETS[-1]} R)")
    print(f"รวม {len(STOPS)*len(TARGETS):,} คู่ต่อ (setup, timeframe) x "
          f"{len(FAMILIES)} setup x {len(TIMEFRAMES)} timeframe = "
          f"{len(STOPS)*len(TARGETS)*len(FAMILIES)*len(TIMEFRAMES):,} ค่ารวม")
    print("เข้าแบบตลาดเท่านั้นในรอบนี้ (ยังไม่รวมโหมด limit/expiry)")
    print("ต้นทุนจริงของโปรเจกต์: spread จริงต่อแท่ง + คอมมิชชั่น 0.140 + slippage 0.033\n")

    b5 = ch.load(Path("data/canonical_XAUUSD_M5.npz"))
    t0, t1 = int(b5.t[0]), int(b5.t[-1]) + b5.step

    # ------------------------------------------------- build every trade list
    print("สร้างไม้สำหรับทุก (setup, timeframe, stop, target)...")
    trades = {}   # (setup, tfname, stop, target) -> list[(t_in, net, t_out)]
    for tfname, mult in TIMEFRAMES:
        bs, nxt = E.resample(b5, mult)
        atr_s = core.atr(bs, E.ATR_N)
        for setup in FAMILIES:
            fills = build_fills(b5, bs, nxt, atr_s, setup)
            if len(fills) < 10:
                continue
            fill_planes = planes_for_fills(b5, fills)
            for st in STOPS:
                for tg in TARGETS:
                    tr = trades_for_geometry(b5, fill_planes, st, tg)
                    if len(tr) >= 10:
                        trades[(setup, tfname, st, tg)] = tr
        print(f"  {tfname}: สะสม {len(trades):,} ชุดที่มีไม้พอ")

    if not trades:
        print("ไม้ไม่พอเลย -> หยุด")
        return 0

    months = month_range(t0, t1)
    print(f"\nจำนวนเดือนทั้งหมด {len(months)}\n")

    # ------------------------------------------------- monthly means, cached
    print("จัดกลุ่มไม้ตามเดือนสำหรับทุกชุด...")
    monthly_mean = {}   # key -> {(y,m): (mean_net, n)}
    for key, tr in trades.items():
        by_month = {}
        for (t_in, net, _t_out) in tr:
            mk = month_key(t_in)
            by_month.setdefault(mk, []).append(net)
        monthly_mean[key] = {mk: (float(np.mean(v)), len(v))
                             for mk, v in by_month.items()}

    # ------------------------------------------------- part 1: in-sample ceiling
    print("\n" + "=" * 108)
    print("(1) เพดานมองย้อนหลัง — ค่าที่ดีที่สุดของ (setup,timeframe,stop,target) ในเดือนนั้นเอง")
    print("=" * 108)
    print(f"{'เดือน':10s}{'setup/timeframe ที่ดีที่สุด':30s}{'stop':>6s}{'target':>7s}"
          f"{'net R':>9s}{'ไม้':>6s}")
    print("-" * 90)
    ceiling_rows = []
    for (y, m, lo, hi) in months:
        best = None
        for key, mm in monthly_mean.items():
            v = mm.get((y, m))
            if v is None or v[1] < MIN_TRADES_MONTH:
                continue
            if best is None or v[0] > best[1][0]:
                best = (key, v)
        if best is None:
            print(f"{y}-{m:02d}    ไม้ไม่พอทุกชุด")
            continue
        (setup, tfname, st, tg), (mean_net, n) = best
        ceiling_rows.append((y, m, mean_net, n))
        print(f"{y}-{m:02d}    {setup+'/'+tfname:30s}{st:6.2f}{tg:7.2f}"
              f"{mean_net:9.4f}{n:6d}")

    ceil_vals = np.array([r[2] for r in ceiling_rows])
    n_trades_ceil = np.array([r[3] for r in ceiling_rows])
    print(f"\nเพดานมองย้อนหลังเฉลี่ยทุกเดือน: {ceil_vals.mean():+.4f} R  "
          f"(สูงสุด {ceil_vals.max():+.4f}  ต่ำสุด {ceil_vals.min():+.4f})")
    print(f"จำนวนไม้ของช่องที่ถูกเลือกเป็น 'ดีที่สุด': ค่ากลาง {np.median(n_trades_ceil):.0f}  "
          f"เฉลี่ย {n_trades_ceil.mean():.1f}  ({100*np.mean(n_trades_ceil<10):.0f}% ของเดือนมีไม้ต่ำกว่า 10)")
    print("คำเตือน: เกณฑ์ขั้นต่ำที่ใช้คือ 3 ไม้/เดือน ซึ่งต่ำมาก — ช่องที่มีไม้น้อย")
    print("มีโอกาสสูงที่จะติดอันดับ 'ดีที่สุด' เพราะความแปรปรวนสูง ไม่ใช่เพราะมีข้อมูลจริง")
    print("(นี่คือปัญหาเดียวกับที่ Amendment 16 ข้อ 9 เตือนไว้ว่าเป็น 'การล่าความแปรปรวน')")
    only_10 = np.array([r[2] for r in ceiling_rows if r[3] >= 10])
    if len(only_10):
        print(f"ถ้าบังคับขั้นต่ำ 10 ไม้/เดือน (เหลือ {len(only_10)} จาก {len(ceiling_rows)} เดือน): "
              f"เฉลี่ย {only_10.mean():+.4f} R  <- ตัวเลขนี้เชื่อถือได้มากกว่า")
    print("นี่คือ 'สิ่งที่ตลาดเดือนนั้นให้รางวัลมากที่สุด' ถ้ารู้คำตอบล่วงหน้า")
    print("ไม่ใช่สิ่งที่คาดว่าจะได้จริงในเดือนถัดไป — ดูข้อ (2) ต่อ")

    # ------------------------------------------------- part 2: walk-forward
    print("\n" + "=" * 108)
    print(f"(2) เดินไปข้างหน้าจริง — เลือกจาก {LOOKBACK_MONTHS} เดือนก่อน แล้วใช้กับเดือนถัดไปโดยไม่มองอนาคต")
    print("=" * 108)
    print(f"{'เดือน':10s}{'เลือกจาก':30s}{'stop':>6s}{'target':>7s}"
          f"{'net R เดือนก่อน':>16s}{'net R จริงเดือนนี้':>18s}{'ไม้':>6s}")
    print("-" * 108)
    fwd_rows = []
    for idx, (y, m, lo, hi) in enumerate(months):
        if idx < LOOKBACK_MONTHS:
            continue
        # embargo: only trust prior-month scores whose trades fully resolved
        # before this month's start (Amendment 16 correction 1's principle)
        prior_keys = [months[idx - k] for k in range(1, LOOKBACK_MONTHS + 1)]
        best = None
        for key, mm in monthly_mean.items():
            vals, ns = [], 0
            for (py, pm, _, _) in prior_keys:
                v = mm.get((py, pm))
                if v is not None:
                    vals.append(v[0] * v[1])
                    ns += v[1]
            if ns < MIN_TRADES_MONTH:
                continue
            score = sum(vals) / ns
            if best is None or score > best[1]:
                best = (key, score, ns)
        if best is None:
            continue
        (setup, tfname, st, tg), score, n_sel = best
        cur = monthly_mean[(setup, tfname, st, tg)].get((y, m))
        # POLICY RETURN, per Amendment 16 correction 8: a period where the
        # selected combo fires zero times contributes ZERO, because capital
        # sat idle - it is not silently dropped from the average. Dropping it
        # would survivor-bias the figure toward months where the (often
        # niche) selected combo happened to fire at all.
        if cur is None:
            fwd_rows.append((y, m, 0.0, 0))
            print(f"{y}-{m:02d}    {setup+'/'+tfname:30s}{st:6.2f}{tg:7.2f}"
                  f"{score:16.4f}{'0 (ไม้หมด)':>18s}")
            continue
        fwd_rows.append((y, m, cur[0], cur[1]))
        print(f"{y}-{m:02d}    {setup+'/'+tfname:30s}{st:6.2f}{tg:7.2f}"
              f"{score:16.4f}{cur[0]:18.4f}{cur[1]:6d}")

    fwd_vals = np.array([r[2] for r in fwd_rows])
    print(f"\nเดินหน้าจริงเฉลี่ยทุกเดือน: {fwd_vals.mean():+.4f} R  "
          f"บวก {100*np.mean(fwd_vals>0):.0f}% ของเดือน  "
          f"(สูงสุด {fwd_vals.max():+.4f}  ต่ำสุด {fwd_vals.min():+.4f})")

    print("\n" + "=" * 108)
    print("เทียบสองชั้น")
    print("=" * 108)
    print(f"  เพดานมองย้อนหลัง (รู้คำตอบล่วงหน้า)  เฉลี่ย {ceil_vals.mean():+.4f} R/เดือน")
    print(f"  เดินหน้าจริง (ไม่มองอนาคต)           เฉลี่ย {fwd_vals.mean():+.4f} R/เดือน")
    gap = ceil_vals.mean() - fwd_vals.mean()
    print(f"  ช่องว่าง = {gap:+.4f} R/เดือน  <- นี่คือราคาที่ต้องจ่ายสำหรับการไม่รู้อนาคต")
    if fwd_vals.mean() <= 0:
        print("\n  การเดินหน้าจริงไม่เป็นบวก -> การเลือกค่าที่ดีที่สุดของเดือนก่อน")
        print("  ไม่ถ่ายทอดไปเดือนถัดไป เหมือนที่ Amendment 20 (รายปี) และ Amendment 10")
        print("  (กริดคงที่ 6,480 ช่อง) เคยพบมาแล้ว")
    else:
        print("\n  การเดินหน้าจริงเป็นบวก — ยังต้องผ่านการทดสอบนัยสำคัญและ holdout")
        print("  ก่อนถือว่าเป็นหลักฐาน ไม่ใช่แค่ตัวเลขเฉลี่ยเดียว")

    print("\nสถานะคงเดิม: นี่คือการวิเคราะห์ ไม่ใช่การเลื่อนขั้นหรือคำสั่งเทรด NO TRADE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
