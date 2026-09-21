"""Search for patterns that lose reliably at RR 1:1, implementing Amendment 07.

THE IDEA. Every search in this repository so far looked for patterns that win.
This one looks for patterns that lose reliably, on the reasoning that a mirror
of a reliable loser is a reliable winner. The project already holds one
instance: UNSTABLE_HIGH_VOL at -0.069 R gross, whose inversion Amendment 06
section 10 computed as +0.031 R and rejected as too small to trade. The method
is therefore not speculative. What failed was magnitude.

THE MIRROR IS RUN, NOT NEGATED. Inverted gross is NOT minus original gross, and
the difference is the whole reason this search can lie. At RR 1:1 the stop and
the target are equidistant, so a bar covering both says nothing about which was
reached first. core.resolve tests the stop before the target, so such a bar is
booked as a loss - and when the mirror is run as its own strategy, with its stop
where the original's target was, that same bar is booked as a loss again. Both
sides lose it. The inversion recovers nothing from ambiguity, which is exactly
what Amendment 07 section 4 requires. Negating the original's number instead
would hand the mirror every ambiguous bar as a win and manufacture profit out of
information nobody has.

THE THRESHOLD. Cost is paid again by the mirror, so it does not cancel:

    original net = g - c        inverted net = -g - c

With commission measured at $7.00 per lot per side on XAUUSD (0.140/oz round
turn), spread 0.090 and slippage 0.033, c = 0.263/oz = 0.042 R against an
R of 1.5 ATR ~ 6.30. A +0.05 R minimum worthwhile edge therefore needs

    g <= -0.092 R

and a candidate that loses less than that is recorded, not inverted.

MULTIPLICITY. The minimum of N noisy estimates is exactly as optimistic as the
maximum. N = 24 is fixed by Amendment 07 section 6 and counted before any
result is read; significance is judged at the family-wise level, two-sided.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import core
import data as D

# ------------------------------------------------------------------ geometry
STOP_ATR = 1.5
RR = 1.0                       # Amendment 07 section 3, the operator's choice
TIME_STOP_M5 = 72
HOLDOUT_DAYS = 120
ATR_N = 14
MEAN_N = 20

# ------------------------------------------------------------------ costs
# All measured on the account in use (Exness-MT5Trial7, demo, trade_mode=0).
SPREAD_FALLBACK = 0.090        # live tick sampling, tools/measure_spreads.py
COMMISSION_RT = 0.140          # $7.00/lot/side -> 0.07/oz/side -> 0.14 round turn
SLIP_PER_FILL = 0.0165         # measured floor, demo
COST_MULTIPLIERS = (1.0, 1.5, 3.0, 7.0)

# ------------------------------------------------------------------ thresholds
GROSS_MAX = -0.092             # Amendment 07 section 2, fixed before any result
AMBIG_MAX = 0.15               # Amendment 07 section 4
MIN_TRADES = 30
N_TESTS = 24                   # Amendment 07 section 6, counted in advance
LONDON_NY = (7, 20)            # UTC hours, inclusive start, exclusive end


# =============================================================== the family
# Six mechanical patterns. Each is here because there is a nameable reason a
# participant would be systematically on the wrong side of it: all six are
# late, crowded or reactive entries. Amendment 07 section 6 requires the
# mechanism to be stated before the number is read, so each carries one.

MECHANISMS = {
    "late_extension": "entering with the trend after it has already travelled "
                      "two ATR from its mean is buying from whoever is taking "
                      "profit into that extension",
    "breakout_into_level": "a breakout whose target sits inside the prior day's "
                           "high or low is running into resting liquidity that "
                           "is waiting to fill it",
    "second_failed_push": "a second attempt that clears the old extreme by "
                          "almost nothing is the point where the participants "
                          "who needed the break have already acted",
    "gap_continuation": "chasing an opening gap assumes the gap is information "
                        "when it is often a thin-book print that fills back",
    "post_news_chase": "the first five-minute move after a release is the most "
                       "crowded entry of the day and the one with the widest "
                       "spread, so the marginal entrant pays the most",
    "inside_bar_break": "a break out of a contraction is the entry the largest "
                        "number of chart readers are watching simultaneously",
}


def _atr(b: D.Bars, n: int = ATR_N) -> np.ndarray:
    return core.atr(b, n)


def _prior_day_levels(b: D.Bars) -> tuple[np.ndarray, np.ndarray]:
    """Previous calendar day's high and low, aligned to each bar. Uses only
    days strictly before the bar's own day, so nothing looks ahead."""
    day = b.t // 86400
    df = pd.DataFrame({"day": day, "h": b.h, "l": b.l})
    g = df.groupby("day").agg(dh=("h", "max"), dl=("l", "min"))
    g["ph"] = g["dh"].shift(1)
    g["pl"] = g["dl"].shift(1)
    m = df["day"].map(g["ph"]).to_numpy(), df["day"].map(g["pl"]).to_numpy()
    return m


def patterns(b15: D.Bars, atr: np.ndarray,
             news_ep: np.ndarray | None) -> dict[str, list[tuple[int, int]]]:
    """Every family returns (bar index, direction) pairs. Direction is the
    pattern's OWN direction - the one a participant following it would take.
    Nothing is inverted here; inversion happens at evaluation."""
    n = len(b15)
    c, h, l, o = b15.c, b15.h, b15.l, b15.o
    out: dict[str, list[tuple[int, int]]] = {k: [] for k in MECHANISMS}

    mean20 = pd.Series(c).rolling(MEAN_N).mean().to_numpy()
    hh20 = pd.Series(h).rolling(MEAN_N).max().shift(1).to_numpy()
    ll20 = pd.Series(l).rolling(MEAN_N).min().shift(1).to_numpy()
    rng = h - l
    rng_mean = pd.Series(rng).rolling(MEAN_N).mean().shift(1).to_numpy()
    ph, pl = _prior_day_levels(b15)
    prev_c = np.concatenate(([c[0]], c[:-1]))

    # a new 20-bar extreme was already made within the last 10 bars
    new_hi = np.zeros(n, bool)
    new_lo = np.zeros(n, bool)
    with np.errstate(invalid="ignore"):
        new_hi = h > hh20
        new_lo = l < ll20
    recent_hi = pd.Series(new_hi.astype(float)).rolling(10).sum() \
        .shift(1).to_numpy()
    recent_lo = pd.Series(new_lo.astype(float)).rolling(10).sum() \
        .shift(1).to_numpy()

    news_set = None
    if news_ep is not None and len(news_ep):
        # a bar is a post-news bar when a release landed inside the PREVIOUS
        # M15 bar, so the "first five-minute move" has already happened and is
        # observable at this bar's open
        bt = b15.t.astype(np.int64)
        idx = np.searchsorted(news_ep, bt, "left") - 1
        since = np.where(idx >= 0, bt - news_ep[np.maximum(idx, 0)], 10 ** 9)
        news_set = (since > 0) & (since <= 900)

    for i in range(MEAN_N + ATR_N + 2, n - 1):
        a = atr[i]
        if not np.isfinite(a) or a <= 0:
            continue

        # 1. late extension: already two ATR from the mean, enter with it
        if np.isfinite(mean20[i]):
            ext = (c[i] - mean20[i]) / a
            if abs(ext) >= 2.0:
                out["late_extension"].append((i, 1 if ext > 0 else -1))

        # 2. breakout of the 20-bar range whose target lands on prior-day level
        if np.isfinite(hh20[i]) and c[i] > hh20[i] and np.isfinite(ph[i]):
            if abs((c[i] + STOP_ATR * a) - ph[i]) <= 0.5 * a:
                out["breakout_into_level"].append((i, 1))
        if np.isfinite(ll20[i]) and c[i] < ll20[i] and np.isfinite(pl[i]):
            if abs((c[i] - STOP_ATR * a) - pl[i]) <= 0.5 * a:
                out["breakout_into_level"].append((i, -1))

        # 3. second push that clears the old extreme by almost nothing
        if new_hi[i] and (recent_hi[i] or 0) >= 1 and np.isfinite(hh20[i]):
            if (h[i] - hh20[i]) < 0.25 * a:
                out["second_failed_push"].append((i, 1))
        if new_lo[i] and (recent_lo[i] or 0) >= 1 and np.isfinite(ll20[i]):
            if (ll20[i] - l[i]) < 0.25 * a:
                out["second_failed_push"].append((i, -1))

        # 4. gap continuation
        gap = o[i] - prev_c[i]
        if abs(gap) >= 0.5 * a:
            out["gap_continuation"].append((i, 1 if gap > 0 else -1))

        # 5. post-news chase, in the direction of the first move
        if news_set is not None and news_set[i]:
            move = c[i - 1] - o[i - 1]
            if move != 0:
                out["post_news_chase"].append((i, 1 if move > 0 else -1))

        # 6. inside-bar break after a contraction
        if (i >= 2 and np.isfinite(rng_mean[i])
                and h[i - 1] <= h[i - 2] and l[i - 1] >= l[i - 2]
                and rng[i - 1] <= 0.7 * rng_mean[i]):
            if c[i] > h[i - 1]:
                out["inside_bar_break"].append((i, 1))
            elif c[i] < l[i - 1]:
                out["inside_bar_break"].append((i, -1))

    return out


# =========================================================== evaluation
class Res:
    __slots__ = ("n", "gross", "net", "se", "ambig", "days", "trades",
                 "by_q", "by_sess")

    def __init__(self, n, gross, net, se, ambig, days, trades, by_q, by_sess):
        self.n, self.gross, self.net, self.se = n, gross, net, se
        self.ambig, self.days, self.trades = ambig, days, trades
        self.by_q, self.by_sess = by_q, by_sess


def evaluate(sig, b15: D.Bars, b5: D.Bars, nxt: np.ndarray, atr: np.ndarray,
             invert: bool, mult: float, spread: np.ndarray | None,
             t_lo: int | None = None, t_hi: int | None = None) -> Res | None:
    """Run the candidate as its own strategy. `invert` flips the direction and
    the mirror is then resolved by the same worst-case rule, so an ambiguous
    bar is a loss for the original AND for the mirror."""
    rows = []
    ambig = 0
    busy_until = -1
    for (i, d0) in sig:
        k = nxt[i]
        if k < 0 or k <= busy_until:
            continue
        t0 = int(b5.t[k])
        if t_lo is not None and t0 < t_lo:
            continue
        if t_hi is not None and t0 >= t_hi:
            continue
        d = -d0 if invert else d0
        a = atr[i]
        entry = b5.o[k]
        risk = STOP_ATR * a
        stop = entry - d * risk
        target = entry + d * RR * risk
        px, why, nb = core.resolve(b5, k, d, entry, stop, target, TIME_STOP_M5)
        kx = min(k + nb, len(b5) - 1)
        # was the exit bar one that covered BOTH levels? then which came first
        # is unknown, and this bar is a loss for this direction and for its
        # mirror alike
        if b5.l[kx] <= min(stop, target) and b5.h[kx] >= max(stop, target):
            ambig += 1
        g = d * (px - entry) / risk
        sp = (float(spread[k]) if spread is not None
              and np.isfinite(spread[k]) and spread[k] > 0 else SPREAD_FALLBACK)
        c_abs = mult * (sp + COMMISSION_RT + 2.0 * SLIP_PER_FILL)
        rows.append((t0, g, g - c_abs / risk, (int(b5.t[k]) // 3600) % 24))
        busy_until = k + nb

    if len(rows) < 3:
        return None
    arr = np.array([(r[1], r[2]) for r in rows], dtype=float)
    ts = np.array([r[0] for r in rows], dtype=np.int64)
    hrs = np.array([r[3] for r in rows], dtype=int)
    net = arr[:, 1]
    day = ts // 86400
    mu = float(net.mean())
    resid = net - mu
    grp = pd.Series(resid).groupby(day).sum().to_numpy()
    se = float(np.sqrt((grp ** 2).sum())) / len(net)

    q = pd.to_datetime(ts, unit="s", utc=True).tz_localize(None).to_period("Q")
    by_q = pd.Series(net).groupby(np.asarray(q.astype(str))).mean().to_dict()
    sess = np.where(hrs < LONDON_NY[0], "asia",
                    np.where(hrs < 13, "london", "ny"))
    by_sess = pd.Series(net).groupby(sess).mean().to_dict()

    return Res(len(net), float(arr[:, 0].mean()), mu, se, ambig / len(net),
               len(grp), rows, by_q, by_sess)


def circular_control(sig, b15, b5, nxt, atr, invert, spread, cut, shifts=40):
    """Amendment 07 section 7.6. Shift the signal indices around the series and
    re-run. A real pattern dies under the shift; a period effect survives it."""
    n = len(b15)
    outs = []
    rng = np.random.default_rng(20260921)
    for _ in range(shifts):
        s = int(rng.integers(MEAN_N + ATR_N + 5, n - 5))
        moved = [((i + s) % n, d) for (i, d) in sig]
        moved = [(i, d) for (i, d) in moved
                 if MEAN_N + ATR_N + 2 <= i < n - 1]
        r = evaluate(moved, b15, b5, nxt, atr, invert, 1.0, spread,
                     t_hi=cut)
        if r is not None:
            outs.append(r.net)
    return np.array(outs, dtype=float)


def main() -> int:
    b5 = D.load_csv("data/XAUUSD_M5.csv")
    b15, _ = D.to_15m(b5)
    want = b15.t + 900
    pos = np.searchsorted(b5.t, want)
    nxt = np.where((pos < len(b5)) & (b5.t[np.minimum(pos, len(b5) - 1)] == want),
                   pos, -1)
    atr = _atr(b15)
    cut = int(b15.t[-1]) - HOLDOUT_DAYS * 86400

    news_ep = None
    try:
        import calendar_feed
        cal = calendar_feed.load_calendar("data/calendar.csv")
        rows = calendar_feed.build_events(cal, "USD", ("HIGH",))
        news_ep = np.array(sorted(r.epoch for r in rows if r.usable),
                           dtype=np.int64)
    except Exception as e:
        print(f"ปฏิทินข่าวโหลดไม่ได้ ({e}) -> post_news_chase = NOT ASSESSED")

    z = core.bonferroni_z(N_TESTS)
    print("=" * 100)
    print("INVERSE SEARCH (Amendment 07) — หา pattern ที่แพ้สม่ำเสมอ แล้วรันตัวกลับด้านจริง")
    print("=" * 100)
    print(f"RR 1:1  stop {STOP_ATR} ATR  ต้นทุนวัดได้ spread {SPREAD_FALLBACK:.3f}"
          f" + คอมมิชชั่น {COMMISSION_RT:.3f} + slippage "
          f"{2*SLIP_PER_FILL:.3f} = {SPREAD_FALLBACK+COMMISSION_RT+2*SLIP_PER_FILL:.3f}/oz")
    print(f"เกณฑ์ที่ประกาศไว้ล่วงหน้า: ต้องแพ้ดิบเกิน {GROSS_MAX:+.3f} R, "
          f"ความกำกวมต่ำกว่า {AMBIG_MAX:.0%}, z แบบ family-wise ที่ N={N_TESTS} = {z:.3f}")
    print("ตัวกลับด้านถูก 'รัน' ไม่ใช่เอาผลเดิมมาใส่ลบ แท่งกำกวมจึงแพ้ทั้งสองฝั่ง\n")

    pat = patterns(b15, atr, news_ep)
    sp = b5.sp

    print(f"{'candidate':34s}{'ไม้':>6s}{'gross':>9s}{'net':>9s}{'se':>8s}"
          f"{'กำกวม':>8s}{'mirror gross':>14s}{'mirror net':>12s}")
    print("-" * 100)

    found = []
    tested = 0
    for fam, sigs in pat.items():
        if not sigs:
            print(f"  {fam:32s}   ไม่มีสัญญาณ -> NOT ASSESSED")
            continue
        for dname, dsel in (("long", 1), ("short", -1)):
            for sname, hrs_ok in (("allhrs", None), ("ldn-ny", LONDON_NY)):
                s = [(i, d) for (i, d) in sigs if d == dsel]
                if hrs_ok is not None:
                    s = [(i, d) for (i, d) in s
                         if hrs_ok[0] <= ((int(b15.t[i]) // 3600) % 24) < hrs_ok[1]]
                tag = f"{fam}/{dname}/{sname}"
                tested += 1
                orig = evaluate(s, b15, b5, nxt, atr, False, 1.0, sp, t_hi=cut)
                if orig is None or orig.n < MIN_TRADES:
                    nn = 0 if orig is None else orig.n
                    print(f"  {tag:32s}{nn:6d}   ไม้น้อยกว่า {MIN_TRADES} -> ไม่ประเมิน")
                    continue
                mir = evaluate(s, b15, b5, nxt, atr, True, 1.0, sp, t_hi=cut)
                print(f"  {tag:32s}{orig.n:6d}{orig.gross:9.4f}{orig.net:9.4f}"
                      f"{orig.se:8.4f}{100*orig.ambig:7.1f}%"
                      f"{mir.gross:14.4f}{mir.net:12.4f}")
                if orig.gross <= GROSS_MAX:
                    found.append((tag, fam, s, orig, mir))

    print("-" * 100)
    print(f"ประเมินไปทั้งหมด {tested} แบบ (ประกาศไว้ N={N_TESTS})\n")

    if not found:
        print("ไม่มี candidate ใดแพ้ดิบถึงเกณฑ์ที่ประกาศไว้")
        print(f"หางฝั่งแพ้บนสินค้านี้ไม่ลึกพอจะกลับด้านได้ (ต้องแพ้เกิน {GROSS_MAX:+.3f} R)")
        print("ตาม Amendment 07 ข้อ 9 ปิดเส้นทางนี้ ห้ามลดเกณฑ์เพื่อรับตัวที่เกือบถึง")
        print("\nสถานะคงเดิม: NO TRADE")
        return 0

    print("=" * 100)
    print(f"candidate ที่แพ้ดิบถึงเกณฑ์: {len(found)} ตัว — ตรวจเงื่อนไขที่เหลือ")
    print("=" * 100)
    for (tag, fam, s, orig, mir) in found:
        print(f"\n{tag}")
        print(f"  กลไกที่ประกาศไว้ก่อนอ่านตัวเลข: {MECHANISMS[fam]}")
        print(f"  ของเดิม   ไม้ {orig.n}  gross {orig.gross:+.4f}  net {orig.net:+.4f}"
              f"  se {orig.se:.4f}  t {orig.net/orig.se:+.2f}")
        print(f"  ตัวกลับด้าน        gross {mir.gross:+.4f}  net {mir.net:+.4f}"
              f"  se {mir.se:.4f}  t {mir.net/mir.se:+.2f}")
        ok_sig = abs(mir.net / mir.se) >= z if mir.se > 0 else False
        ok_amb = orig.ambig < AMBIG_MAX
        print(f"  ความกำกวม {100*orig.ambig:.1f}% -> "
              f"{'ผ่าน' if ok_amb else 'ไม่ผ่าน NOT ASSESSABLE'}")
        print(f"  นัยสำคัญแบบ family-wise (ต้อง |t| >= {z:.3f}) -> "
              f"{'ผ่าน' if ok_sig else 'ไม่ผ่าน'}")
        print(f"  แยกตามไตรมาส: " + "  ".join(
            f"{k} {v:+.3f}" for k, v in sorted(mir.by_q.items())))
        print(f"  แยกตาม session: " + "  ".join(
            f"{k} {v:+.3f}" for k, v in sorted(mir.by_sess.items())))
        pos_q = sum(1 for v in mir.by_q.values() if v > 0)
        pos_s = sum(1 for v in mir.by_sess.values() if v > 0)
        print(f"  กระจายตัว: ไตรมาสที่บวก {pos_q}/{len(mir.by_q)}  "
              f"session ที่บวก {pos_s}/{len(mir.by_sess)} -> "
              f"{'ผ่าน' if pos_q >= 3 and pos_s >= 2 else 'ไม่ผ่าน กระจุกตัว'}")

        ctrl = circular_control(s, b15, b5, nxt, atr, True, sp, cut)
        if len(ctrl) > 5:
            beat = float(np.mean(ctrl >= mir.net))
            print(f"  control แบบเลื่อนวน {len(ctrl)} รอบ: ค่ากลาง "
                  f"{np.median(ctrl):+.4f}  สัดส่วนที่ชนะของจริง {100*beat:.0f}%"
                  f" -> {'ผ่าน' if beat < 0.05 else 'ไม่ผ่าน เป็นผลของช่วงเวลา'}")

        print("  ต้นทุนหลายระดับ (ของตัวกลับด้าน):")
        for m in COST_MULTIPLIERS:
            r = evaluate(s, b15, b5, nxt, atr, True, m, sp, t_hi=cut)
            print(f"      {m:.1f}x  net {r.net:+.4f}  t {r.net/r.se:+.2f}")

    print("\n" + "=" * 100)
    print("ไม่ว่าผลจะเป็นอย่างไร Amendment 07 ข้อ 8 กำหนดว่า candidate ที่ผ่าน")
    print("เป็นได้เพียง shadow challenger ตัวกลับด้านไม่ได้รับการยกเว้นจาก forward shadow")
    print("มันคือคำกล่าวอ้างเรื่องอนาคตแบบเดียวกัน แค่พูดจากอีกฝั่ง -> วันนี้ NO TRADE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
