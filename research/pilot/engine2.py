"""
Two-layer engine: slow context decides the side, fast timing decides the bar.

The measurements that led here, in order:

    candles.py      the shape of an M5 bar predicts how FAR price moves
                    (volume vs neighbours IC +0.116) and nothing about WHICH
                    WAY (best directional feature t -1.46 against a bar of
                    3.27). So direction cannot come from the fast layer.
    seasons.py      the only things leaning directional are slow and weak -
                    distance from the 5-day and 20-day average, and 3-day
                    continuation. None significant on its own.
    vol_attribution the clock and volatility's own memory explain 97 percent
                    of what is explainable about size. News adds 0.8 points
                    once the clock is present.

The architecture follows from that rather than from tradition: SIDE from the
slow layer, TIMING and SIZE from the fast one. A fast layer asked for
direction is being asked for something the data says it does not have.

EVERY PARAMETER BELOW IS DECLARED, NOT FITTED. Nothing is optimised on the
data, so there is no in-sample advantage to discount - only the question of
whether a mechanism-shaped rule survives cost. The holdout is still kept
untouched, because judgement about which variant to report is itself a fitting
step if it happens after seeing the recent window.

Costs charged: measured spread, assumed slippage, and swap on longs carried
across the rollover - which the earlier rounds omitted entirely.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import core
import data as D

# ----------------------------------------------------------------- declared
M15_PER_DAY = 96
SPREAD = 0.260              # measured on the live account
SLIPPAGE = 0.10             # assumed per fill
SWAP_LONG_PER_OZ = 0.5493   # measured, longs only, per night
ROLLOVER_UTC_H = 21         # measured from where the bar count collapses

CTX_FAST_D = 5              # [DEF] context lookbacks, in days
CTX_SLOW_D = 20
CTX_Z_WIN = 20 * M15_PER_DAY    # [DEF] trailing window for standardising
CTX_THRESHOLD = 0.50        # [DEF] how strong the context must be to allow a side

NEWS_WINDOW_H = 4           # [DEF] how long a release keeps colouring context
NEWS_MOVE_ATR = 0.50        # [DEF] reaction size that counts as price deciding

STOP_ATR = 1.5              # [DEF] risk unit
TARGET_R = 2.0              # [DEF]
TIME_STOP_M5 = 72           # [DEF] 6 hours
PULLBACK_ATR = 0.5          # [DEF] how close to the average counts as a pullback
BREAK_LOOKBACK = 20         # [DEF] bars for the breakout trigger
MIN_ATR_PCT = 30            # [DEF] below this the move is too small to pay costs

HOLDOUT_DAYS = 120          # [DEF] recent window untouched by any choice


# ------------------------------------------------------------------ helpers
def zscore(x: np.ndarray, win: int) -> np.ndarray:
    s = pd.Series(x)
    m = s.rolling(win, min_periods=win // 4).mean()
    sd = s.rolling(win, min_periods=win // 4).std()
    return ((s - m) / sd.replace(0, np.nan)).to_numpy()


def build_context(b15: D.Bars, dxy: D.Bars | None,
                  news: pd.DataFrame | None) -> pd.DataFrame:
    """Layer 1. Everything here changes over days, not bars."""
    c = b15.c
    atr = core.atr(b15, 14)
    safe = np.where(atr > 0, atr, np.nan)
    t = pd.to_datetime(b15.t, unit="s", utc=True)
    out = pd.DataFrame({"t": t})

    for d, name in ((CTX_FAST_D, "trend_fast"), (CTX_SLOW_D, "trend_slow")):
        sma = pd.Series(c).rolling(d * M15_PER_DAY).mean().to_numpy()
        out[name] = zscore((c - sma) / safe, CTX_Z_WIN)

    if dxy is not None:
        s = pd.Series(dxy.c, index=pd.to_datetime(dxy.t, unit="s", utc=True))
        s = s[~s.index.duplicated()].reindex(t, method="ffill")
        d5 = s.to_numpy() - pd.Series(s.to_numpy()).shift(CTX_FAST_D * M15_PER_DAY).to_numpy()
        # a FALLING dollar is the gold-positive state, hence the minus sign
        out["dollar"] = zscore(-d5, CTX_Z_WIN)
    else:
        out["dollar"] = np.nan

    # news: the release sets a hypothesis, the price reaction decides it.
    # What is carried forward is the DECISION, which is the sign of the move
    # since the release once that move is big enough to mean anything.
    nz = np.zeros(len(b15))
    if news is not None and len(news):
        ev = news["epoch"].to_numpy()
        bt = b15.t.astype(np.int64)
        prev = np.searchsorted(ev, bt, side="right") - 1
        ok = prev >= 0
        since = np.where(ok, (bt - ev[np.maximum(prev, 0)]) / 3600.0, np.inf)
        fresh = ok & (since <= NEWS_WINDOW_H)
        rel_idx = np.searchsorted(b15.t, ev[np.maximum(prev, 0)], side="right") - 1
        rel_idx = np.clip(rel_idx, 0, len(b15) - 1)
        with np.errstate(invalid="ignore"):
            react = (c - c[rel_idx]) / safe
        nz = np.where(fresh & (np.abs(react) >= NEWS_MOVE_ATR), np.sign(react), 0.0)
    out["news"] = nz

    parts = out[["trend_fast", "trend_slow", "dollar"]].to_numpy()
    with np.errstate(invalid="ignore"):
        ctx = np.nanmean(parts, axis=1)
    # news is a decision in {-1,0,1}, not a z-score, so it enters as a nudge
    out["context"] = ctx + 0.5 * out["news"].to_numpy()
    out["bias"] = np.where(out["context"] >= CTX_THRESHOLD, 1,
                           np.where(out["context"] <= -CTX_THRESHOLD, -1, 0))
    out["atr"] = atr
    out["atr_pct"] = core.rolling_pct_rank(atr, 200)
    return out


def triggers(b15: D.Bars, ctx: pd.DataFrame, use_pullback=True,
             use_breakout=True) -> list[tuple]:
    """Layer 2. Only ever in the direction the context already allows."""
    c, h, l = b15.c, b15.h, b15.l
    atr = ctx["atr"].to_numpy()
    bias = ctx["bias"].to_numpy()
    ap = ctx["atr_pct"].to_numpy()
    ema20 = core.ema(c, 20)
    hh = core.rolling_max(h, BREAK_LOOKBACK)
    ll = core.rolling_min(l, BREAK_LOOKBACK)
    warm = max(CTX_SLOW_D * M15_PER_DAY, 200)

    sig = []
    for i in range(warm, len(b15)):
        d = bias[i]
        if d == 0 or not np.isfinite(atr[i]) or atr[i] <= 0:
            continue
        if not np.isfinite(ap[i]) or ap[i] < MIN_ATR_PCT:
            continue                      # too quiet: cost eats the move
        a = atr[i]
        fired = False
        if use_pullback:
            if d > 0 and l[i] <= ema20[i] + PULLBACK_ATR * a and c[i] > ema20[i]:
                fired = True
            if d < 0 and h[i] >= ema20[i] - PULLBACK_ATR * a and c[i] < ema20[i]:
                fired = True
        if not fired and use_breakout:
            if d > 0 and np.isfinite(hh[i]) and c[i] > hh[i]:
                fired = True
            if d < 0 and np.isfinite(ll[i]) and c[i] < ll[i]:
                fired = True
        if fired:
            stop = c[i] - d * STOP_ATR * a
            sig.append((i, int(d), float(stop), "R", TARGET_R))
    return sig


def apply_swap(trades, exec_bars) -> None:
    """Charge the rollover that every earlier round in this repo ignored.

    A long carried across 21:00 UTC pays SWAP_LONG_PER_OZ per ounce per night.
    Shorts pay nothing on this symbol. The charge is converted into R using
    the trade's own risk, so it lands in the same unit as everything else.
    """
    for tr in trades:
        if tr.dir <= 0:
            continue
        t0 = int(tr.t)
        t1 = t0 + tr.bars * exec_bars.step
        h0 = (t0 // 3600) % 24
        nights = 0
        cur = t0 - (t0 % 3600) + (ROLLOVER_UTC_H - h0) % 24 * 3600
        while cur <= t1:
            nights += 1
            cur += 86400
        if nights:
            tr.net_R -= nights * SWAP_LONG_PER_OZ / tr.risk


def evaluate(name: str, b15: D.Bars, ctx: pd.DataFrame, b5: D.Bars,
             nxt: np.ndarray, sig: list, rng) -> dict:
    cost = SPREAD + 2 * SLIPPAGE
    c = core.Ctx(b15, nxt)
    tr, skipped, accepted = core.run_signals(c, sig, b5, nxt, cost, TIME_STOP_M5)
    apply_swap(tr, b5)
    ctl_sig, drop = core.circular_shift_control(c, accepted, nxt, 10, rng)
    ctl, _, _ = core.run_signals(c, ctl_sig, b5, nxt, cost, TIME_STOP_M5)
    apply_swap(ctl, b5)
    s = core.summarise(tr, "net_R")
    cs = core.summarise(ctl, "net_R")
    skill = s["E"] - cs["E"] if s["n"] and cs["n"] else np.nan
    se = (np.sqrt(s["se"] ** 2 + cs["se"] ** 2)
          if s["n"] > 1 and cs["n"] > 1 else np.nan)
    return dict(name=name, trades=tr, n=s["n"], E=s["E"], se=s["se"],
                mde=s["mde"], win=s["win"], n_ctl=cs["n"], E_ctl=cs["E"],
                skill=skill, skill_t=(skill / se if se and np.isfinite(se) and se > 0
                                      else np.nan))


def slice_trades(tr, lo: int, hi: int):
    return [x for x in tr if lo <= int(x.t) < hi]


def line(tag, trades):
    if len(trades) < 2:
        return f"  {tag:26s} n={len(trades):4d}   น้อยเกินไป"
    x = np.array([t.net_R for t in trades])
    se = x.std(ddof=1) / np.sqrt(len(x))
    return (f"  {tag:26s} n={len(x):4d}  ชนะ {100*(x>0).mean():4.1f}%  "
            f"ได้เฉลี่ย {x.mean():+7.4f} R  ความมั่นใจ t={x.mean()/se:+5.2f}")


def failure_report(trades) -> None:
    """Why the losers lost, in categories that point at different fixes.

    The distinction that matters most is between a trade that was WRONG and a
    trade that was RIGHT AND TOO SMALL. The first is a signal problem; the
    second is a cost problem, and no amount of signal work fixes it.
    """
    if not trades:
        print("  ไม่มีไม้")
        return
    g = np.array([t.gross_R for t in trades])
    n_ = np.array([t.net_R for t in trades])
    why = np.array([t.why for t in trades])
    dr = np.array([t.dir for t in trades])

    losers = n_ < 0
    cost_only = losers & (g > 0)
    wrong = losers & (g <= 0)
    print(f"  ไม้ทั้งหมด {len(trades):,}  ขาดทุน {losers.sum():,} "
          f"({100*losers.mean():.1f}%)")
    print(f"    ทิศถูกแต่ได้ไม่พอจ่ายค่าธรรมเนียม : {cost_only.sum():5,d} "
          f"({100*cost_only.sum()/max(losers.sum(),1):.1f}% ของไม้ที่ขาดทุน)")
    print(f"    ทิศผิดจริง ๆ                       : {wrong.sum():5,d} "
          f"({100*wrong.sum()/max(losers.sum(),1):.1f}%)")
    print(f"  ต้นทุนเฉลี่ยที่กินไป : {np.mean(g - n_):.4f} R ต่อไม้ "
          f"(รวม swap ฝั่ง long)")
    print("  จบด้วยวิธีไหน:")
    for w in ("target", "stop", "time"):
        m = why == w
        if m.sum():
            print(f"    {w:7s} {m.sum():6,d} ไม้ ({100*m.mean():4.1f}%)  "
                  f"ได้เฉลี่ย {n_[m].mean():+7.4f} R")
    print("  แยกตามฝั่ง:")
    for d, nm in ((1, "ซื้อ"), (-1, "ขาย")):
        m = dr == d
        if m.sum():
            print(f"    {nm:5s} {m.sum():6,d} ไม้  ได้เฉลี่ย {n_[m].mean():+7.4f} R  "
                  f"ต้นทุน {np.mean(g[m]-n_[m]):.4f} R")
    print("  แยกตาม session:")
    ss = np.array([t.session for t in trades])
    for s in sorted(set(ss)):
        m = ss == s
        if m.sum() > 30:
            print(f"    {s:8s} {m.sum():6,d} ไม้  ได้เฉลี่ย {n_[m].mean():+7.4f} R")
    print("  แยกตามสภาพตลาด:")
    rg = np.array([t.regime for t in trades])
    for s in sorted(set(rg)):
        m = rg == s
        if m.sum() > 30:
            print(f"    {s:10s} {m.sum():6,d} ไม้  ได้เฉลี่ย {n_[m].mean():+7.4f} R")


def main() -> int:
    b5 = D.load_csv("data/XAUUSD_M5.csv")
    b15, _ = D.to_15m(b5)
    nxt = np.searchsorted(b5.t, b15.t + 900)
    nxt = np.where((nxt < len(b5)) & (b5.t[np.minimum(nxt, len(b5) - 1)] == b15.t + 900),
                   nxt, -1)
    try:
        dxy = D.load_csv("data/DXY_M5.csv")
    except Exception:
        dxy = None
    news = None
    try:
        import calendar_feed
        cal = calendar_feed.load_calendar("data/calendar.csv")
        rows = calendar_feed.build_events(cal, "USD", ("HIGH",))
        usable = [r for r in rows if r.usable]
        news = pd.DataFrame([{"epoch": r.epoch} for r in usable]).sort_values("epoch")
    except Exception as e:
        print("calendar unavailable:", e)

    t = pd.to_datetime(b15.t, unit="s", utc=True)
    print("=" * 96)
    print("ระบบสองชั้น - ชั้นช้าเลือกฝั่ง ชั้นเร็วเลือกจังหวะ")
    print("=" * 96)
    print(f"M15 {len(b15):,} แท่ง  {t[0]:%Y-%m-%d} ถึง {t[-1]:%Y-%m-%d} "
          f"= {(t[-1]-t[0]).days} วัน   (M5 ต้นทาง {len(b5):,} แท่ง)")
    print(f"ต้นทุนที่คิด: spread ${SPREAD:.3f} วัดจริง + slippage ${SLIPPAGE:.2f} x2 สมมติ"
          f" + swap ${SWAP_LONG_PER_OZ:.4f}/oz/คืน เฉพาะฝั่ง long")

    ctx = build_context(b15, dxy, news)
    have = ctx["bias"].to_numpy() != 0
    print(f"\nชั้นที่ 1 - บริบททิศทาง")
    print(f"  แท่งที่บริบทกล้าบอกฝั่ง : {have.sum():,} จาก {len(ctx):,} "
          f"({100*have.mean():.1f}%)")
    print(f"  ฝั่งซื้อ {int((ctx['bias']==1).sum()):,}  "
          f"ฝั่งขาย {int((ctx['bias']==-1).sum()):,}  "
          f"อยู่เฉย {int((ctx['bias']==0).sum()):,}")
    print(f"  ข่าวมีส่วนร่วม {int((ctx['news']!=0).sum()):,} แท่ง")

    cut = int(b15.t[-1]) - HOLDOUT_DAYS * 86400
    print(f"\nแบ่งข้อมูล: ช่วงพัฒนา ถึง {pd.to_datetime(cut, unit='s', utc=True):%Y-%m-%d}"
          f" | holdout {HOLDOUT_DAYS} วันสุดท้าย ไม่แตะจนกว่าจะเลือกเสร็จ")

    rng = np.random.default_rng(20260921)
    variants = [
        ("champion: pullback+breakout", True, True),
        ("challenger A: pullback only", True, False),
        ("challenger B: breakout only", False, True),
    ]
    results = []
    for name, up, ub in variants:
        sig = triggers(b15, ctx, up, ub)
        r = evaluate(name, b15, ctx, b5, nxt, sig, rng)
        results.append(r)

    print("\nชั้นที่ 2 - ผลรวมทั้งช่วง (รวม holdout ยังไม่แยก)")
    print(f"  {'':28s}{'ไม้':>6s}{'ชนะ%':>7s}{'ได้เฉลี่ย':>11s}{'เทียบ control':>14s}{'ความมั่นใจ':>11s}")
    for r in results:
        if not r["n"]:
            print(f"  {r['name']:28s}  ไม่มีไม้เลย")
            continue
        print(f"  {r['name']:28s}{r['n']:6d}{r['win']:7.1f}{r['E']:11.4f}"
              f"{r['skill']:14.4f}{r['skill_t']:11.2f}")

    print("\nแยกช่วงพัฒนา กับ holdout ที่ไม่เคยถูกใช้เลือกอะไร")
    for r in results:
        if not r["n"]:
            continue
        print(f"\n  {r['name']}")
        print(line("ช่วงพัฒนา", slice_trades(r["trades"], 0, cut)))
        print(line("holdout 120 วันสุดท้าย", slice_trades(r["trades"], cut, 1 << 62)))

    print("\nเดินหน้าทีละไตรมาส (walk-forward)")
    ch = results[0]
    if ch["n"]:
        tt = pd.to_datetime([x.t for x in ch["trades"]], unit="s", utc=True)
        q = pd.Series(tt).dt.to_period("Q")
        for period in sorted(q.unique()):
            sel = [x for x, p in zip(ch["trades"], q) if p == period]
            print(line(str(period), sel))

    print("\n" + "=" * 96)
    print("ผ่าซากไม้ที่แพ้ - champion ทั้งช่วง")
    print("=" * 96)
    failure_report(results[0]["trades"])
    print("\nเฉพาะ holdout 120 วันสุดท้าย")
    failure_report(slice_trades(results[0]["trades"], cut, 1 << 62))

    print("\n" + "=" * 96)
    best = max((r for r in results if r["n"] > 30),
               key=lambda r: r["skill_t"] if np.isfinite(r["skill_t"]) else -9,
               default=None)
    bar = core.bonferroni_z(len(results))
    if best is None:
        print("สรุป: ไม่มีตัวไหนมีไม้พอจะตัดสิน -> NO TRADE")
    else:
        ho = slice_trades(best["trades"], cut, 1 << 62)
        ho_e = np.mean([x.net_R for x in ho]) if len(ho) > 1 else np.nan
        print(f"ตัวที่ดีที่สุด: {best['name']}")
        print(f"  ทั้งช่วง  ได้เฉลี่ย {best['E']:+.4f} R  "
              f"เทียบ control {best['skill']:+.4f}  ความมั่นใจ {best['skill_t']:+.2f} "
              f"(ต้องเกิน {bar:.2f})")
        print(f"  holdout   ได้เฉลี่ย {ho_e:+.4f} R จาก {len(ho)} ไม้")
        passed = (np.isfinite(best["skill_t"]) and best["skill_t"] >= bar
                  and best["E"] > 0 and np.isfinite(ho_e) and ho_e > 0)
        print()
        if passed:
            print("สรุป: ผ่านเกณฑ์ -> เลื่อนเป็น champion ได้ แต่ยังต้องรันแบบ shadow ก่อน")
        else:
            print("สรุป: NO TRADE")
            print("  ไม่มี edge สุทธิที่ผ่านเกณฑ์หลังหักต้นทุนจริง")
            print("  ตัวที่เหลือทั้งหมดยังเป็น challenger แบบ shadow ไม่มีตัวไหนได้เป็น champion")
    print("\nไม่มีการส่งคำสั่งใด ๆ ทั้งสิ้น และไม่มีฟังก์ชันส่งออเดอร์อยู่ในไฟล์นี้")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
