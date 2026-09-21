"""
Adaptive engine — measure the market first, then pick ONE tool for it.

Amendment 04 fixed the rules before this file existed:

    one champion, at most one shadow challenger, never the whole menu
    regime selects the tool from a fixed mechanism-based mapping
    no tool moves to another regime because it scored better there
    promotion needs a FORWARD shadow run, not a backtest

The mapping, declared and not fitted:

    STABLE_TREND     trend pullback      a pullback needs a trend to pull back in
    VOL_EXPANSION    breakout            a breakout needs expansion to carry it
    EVENT            news acceptance     a release is the only thing moving price
    BALANCED_RANGE   reversion to VWAP   reversion needs a balance to revert to
    anything else    NO TRADE

Windows follow CLAUDE.md section 5 and are fixed in advance:

    30-60 days  broad context
    10-20 days  the regime label
    3-5 days    strategy health, which decides champion against shadow
    session     entry, invalidation, expiry

COSTS ARE THE PART EARLIER ROUNDS GOT WRONG, so they are spelled out:

  spread     the live account charges a flat 260 points. The demo file's
             per-bar column belongs to a RAW account and is three times
             cheaper, so it is used only for its SHAPE - the hour-of-day
             profile - rescaled to the live level. That is a model, and it is
             labelled as one.
  slippage   never measured. Reported at three values so the reader can see
             how much of any conclusion rests on the assumption.
  swap       measured, 0.5493 per ounce per night, longs only, charged when a
             position is carried across 21:00 UTC.

Trades overlap in time, so treating them as independent understates the
interval. Every headline figure carries a block-bootstrap interval as well as
the naive one.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import core
import data as D

M15_PER_DAY = 96

# ------------------------------------------------------- declared constants
CONTEXT_D = 45            # [DEF] 30-60 day band, midpoint
REGIME_D = 15             # [DEF] 10-20 day band, midpoint
HEALTH_D = 4              # [DEF] 3-5 day band, midpoint
SPREAD_LIVE = 0.260       # measured on the account that will be traded
# 0.0165 is MEASURED, not assumed: ten demo round trips on 2026-09-21 gave a
# median entry slippage of exactly 0.0000 and a mean of +0.0273, with a mean
# of +0.0056 on the exit - 0.0329 for both sides, so 0.0165 per fill. Nine of
# the ten fills had zero slippage and one slipped 0.2730, which is the shape
# to expect: usually nothing, occasionally a lot.
#
# It is a DEMO figure and demo servers fill at the quote more readily than
# live ones, so it is a floor rather than an estimate. The larger values stay
# in the grid because the true number is somewhere between them.
SLIP_GRID = (0.0165, 0.05, 0.10, 0.20)
SWAP_LONG = 0.5493        # measured, per ounce per night, longs only
ROLLOVER_H = 21           # measured from where the bar count collapses

STOP_ATR = 1.5
TARGET_R = 2.0
TIME_STOP_M5 = 72
HOLDOUT_DAYS = 120
NEWS_WIN_MIN = 30         # [DEF] minutes either side that count as EVENT regime

TOOL_FOR_REGIME = {
    "STABLE_TREND": "pullback",
    "VOL_EXPANSION": "breakout",
    "EVENT": "news",
    "BALANCED_RANGE": "reversion",
}


# ------------------------------------------------------------- cost model
def hourly_spread_profile(b5: D.Bars) -> np.ndarray:
    """Hour-of-day multipliers taken from the demo file's SHAPE only.

    The level is wrong for the live account by a factor of three, but the
    shape - which hours widen - is a property of the market's clock rather
    than of the account type, so the profile is normalised to its own median
    and rescaled to the live level by the caller.
    """
    prof = np.ones(24)
    if b5.sp is None:
        return prof
    h = pd.to_datetime(b5.t, unit="s", utc=True).hour
    s = pd.Series(b5.sp, index=h)
    med = s[s > 0].median()
    if not np.isfinite(med) or med <= 0:
        return prof
    for hh in range(24):
        v = s[s.index == hh]
        v = v[v > 0]
        if len(v) > 50:
            prof[hh] = float(v.median() / med)
    return prof


def cost_series(b15: D.Bars, prof: np.ndarray, slip: float) -> np.ndarray:
    """Round-turn cost in PRICE units for a trade signalled on each M15 bar."""
    h = pd.to_datetime(b15.t, unit="s", utc=True).hour.to_numpy()
    return SPREAD_LIVE * prof[h] + 2.0 * slip


# ------------------------------------------------------------ regime layer
def build_regime(b15: D.Bars, news_epochs: np.ndarray | None) -> pd.DataFrame:
    c, h, l = b15.c, b15.h, b15.l
    atr = core.atr(b15, 14)
    t = pd.to_datetime(b15.t, unit="s", utc=True)
    n = len(b15)
    out = pd.DataFrame({"t": t, "atr": atr})

    logc = np.log(np.maximum(c, 1e-9))
    r1 = np.concatenate(([0.0], np.diff(logc)))

    # 10-20 day window: is the market walking somewhere, or milling about
    w = REGIME_D * M15_PER_DAY
    net = np.abs(c - pd.Series(c).shift(w).to_numpy())
    path = pd.Series(np.abs(r1) * np.maximum(c, 1e-9)).rolling(w).sum().to_numpy()
    with np.errstate(divide="ignore", invalid="ignore"):
        out["dir_eff"] = np.where(path > 0, net / path, np.nan)

    # expansion: current volatility against the same 10-20 day window
    atr_ref = pd.Series(atr).shift(w).rolling(w).mean().to_numpy()
    with np.errstate(divide="ignore", invalid="ignore"):
        out["expansion"] = atr / atr_ref

    # 30-60 day context: where volatility sits in its own longer history
    out["atr_pct"] = core.rolling_pct_rank(atr, CONTEXT_D * M15_PER_DAY)

    # stability of the regime itself - a trend that keeps changing its mind is
    # not a stable trend, whatever its efficiency reads
    out["stability"] = 1.0 - pd.Series(out["dir_eff"]).rolling(
        REGIME_D * M15_PER_DAY // 2).std().to_numpy()

    ev = np.zeros(n, bool)
    if news_epochs is not None and len(news_epochs):
        bt = b15.t.astype(np.int64)
        nxt = np.searchsorted(news_epochs, bt, "left")
        prv = nxt - 1
        to_next = np.where(nxt < len(news_epochs),
                           (news_epochs[np.minimum(nxt, len(news_epochs) - 1)] - bt) / 60, 1e9)
        since = np.where(prv >= 0, (bt - news_epochs[np.maximum(prv, 0)]) / 60, 1e9)
        ev = (to_next <= NEWS_WIN_MIN) | (since <= NEWS_WIN_MIN)
    out["event"] = ev

    de = out["dir_eff"].to_numpy()
    ex = out["expansion"].to_numpy()
    ap = out["atr_pct"].to_numpy()
    st = out["stability"].to_numpy()
    # thresholds are quantiles of the CONTEXT window, so they follow the
    # market rather than being numbers chosen to make a table look good
    de_hi = pd.Series(de).rolling(CONTEXT_D * M15_PER_DAY).quantile(0.70).to_numpy()
    de_lo = pd.Series(de).rolling(CONTEXT_D * M15_PER_DAY).quantile(0.30).to_numpy()
    ex_hi = pd.Series(ex).rolling(CONTEXT_D * M15_PER_DAY).quantile(0.80).to_numpy()

    regime = np.full(n, "UNDEFINED", dtype=object)
    with np.errstate(invalid="ignore"):
        regime = np.where(ev, "EVENT", regime)
        regime = np.where((regime == "UNDEFINED") & (ex >= ex_hi) & (ap >= 60),
                          "VOL_EXPANSION", regime)
        regime = np.where((regime == "UNDEFINED") & (de >= de_hi)
                          & (st >= np.nanmedian(st)), "STABLE_TREND", regime)
        regime = np.where((regime == "UNDEFINED") & (de <= de_lo) & (ap <= 60),
                          "BALANCED_RANGE", regime)
    out["regime"] = regime
    return out


# ------------------------------------------------------------------ tools
def tool_signals(name: str, b15: D.Bars, reg: pd.DataFrame,
                 allow: np.ndarray) -> list[tuple]:
    """Each tool fires ONLY on bars its own regime allows."""
    c, h, l = b15.c, b15.h, b15.l
    atr = reg["atr"].to_numpy()
    ema20 = core.ema(c, 20)
    ema50 = core.ema(c, 50)
    hh = core.rolling_max(h, 20)
    ll = core.rolling_min(l, 20)
    vwap, vsd = core.session_vwap(b15)
    warm = max(CONTEXT_D * M15_PER_DAY, 200)
    sig = []
    for i in range(warm, len(b15)):
        if not allow[i] or not np.isfinite(atr[i]) or atr[i] <= 0:
            continue
        a = atr[i]
        d = 0
        if name == "pullback":
            up = ema20[i] > ema50[i]
            if up and l[i] <= ema20[i] + 0.5 * a and c[i] > ema20[i]:
                d = 1
            elif (not up) and h[i] >= ema20[i] - 0.5 * a and c[i] < ema20[i]:
                d = -1
        elif name == "breakout":
            if np.isfinite(hh[i]) and c[i] > hh[i]:
                d = 1
            elif np.isfinite(ll[i]) and c[i] < ll[i]:
                d = -1
        elif name == "reversion":
            s = vsd[i]
            if s > 0:
                if c[i] > vwap[i] + 2 * s:
                    d = -1
                elif c[i] < vwap[i] - 2 * s:
                    d = 1
        elif name == "news":
            # price decides: take the side the first move after the release
            # chose, once it is large enough to mean anything
            if i >= 2:
                mv = (c[i] - c[i - 2]) / a
                if abs(mv) >= 0.5:
                    d = int(np.sign(mv))
        if d:
            sig.append((i, d, float(c[i] - d * STOP_ATR * a), "R", TARGET_R))
    return sig


# ------------------------------------------------------------ evaluation
def run_with_costs(c15: core.Ctx, sig, b5: D.Bars, nxt: np.ndarray,
                   costs: np.ndarray, slip: float,
                   swap: float | None = SWAP_LONG, out: dict | None = None):
    """core.run_signals charges one scalar cost; this charges the per-bar
    figure and then the swap, so the hour a trade opens in matters.

    `swap` is the overnight financing charge per unit per night, in the SAME
    price units as the series, for long positions only. It defaults to gold's
    measured 0.5493 per ounce. Passing gold's figure to another instrument is
    not a rounding error: it is divided by that instrument's risk, so on a
    GBPUSD stop of 0.0012 it charges 458 R per night and produced a mean of
    -65.95 R against a gross of +0.18. Swap is an interest-rate differential,
    not a volatility quantity, so unlike slippage it cannot be carried across
    instruments as a fraction of ATR. Where it has not been measured, pass
    None: nothing is charged and the caller must report it as NOT MEASURED.

    `out`, if given, receives diagnostics - including the share of trades held
    across a rollover, which is what an unmeasured swap would have hit.
    """
    trades = []
    accepted = []
    n_overnight = 0
    tot_nights = 0
    for (i, d, stop, tmode, tval) in sig:
        k = nxt[i]
        if k < 0:
            continue
        entry = b5.o[k]
        risk = abs(entry - stop)
        if risk <= 1e-9 or (d > 0 and stop >= entry) or (d < 0 and stop <= entry):
            continue
        target = entry + d * tval * risk
        px, why, nb = core.resolve(b5, k, d, entry, stop, target, TIME_STOP_M5)
        g = d * (px - entry) / risk
        cost = costs[i]
        net = g - cost / risk
        if d > 0:
            t0 = int(b5.t[k]); t1 = t0 + nb * b5.step
            h0 = (t0 // 3600) % 24
            cur = t0 - (t0 % 3600) + ((ROLLOVER_H - h0) % 24) * 3600
            nights = 0
            while cur <= t1:
                nights += 1
                cur += 86400
            if nights:
                n_overnight += 1
                tot_nights += nights
            if swap is not None:
                net -= nights * swap / risk
        trades.append(core.Trade(int(b5.t[k]), d, risk, g, net,
                                 c15.session[i], c15.regime[i], why, nb))
        accepted.append((i, d, stop, tmode, tval))
    if out is not None:
        out["n_overnight"] = n_overnight
        out["tot_nights"] = tot_nights
        out["swap_charged"] = swap
        out["overnight_share"] = (n_overnight / len(trades)) if trades else np.nan
    return trades, accepted


def clustered_stats(trades, block_hours: int = 24) -> dict:
    """Naive SE treats overlapping trades as independent. The block bootstrap
    keeps neighbours together, which is the honest interval here."""
    if len(trades) < 10:
        return dict(n=len(trades), E=np.nan, se=np.nan, lo=np.nan, hi=np.nan)
    x = np.array([t.net_R for t in trades])
    t0 = np.array([t.t for t in trades])
    per_block = max(2, int(len(x) / max(1, (t0[-1] - t0[0]) / (block_hours * 3600))))
    lo, hi = core.block_bootstrap_ci(x, block=per_block, draws=800,
                                     rng=np.random.default_rng(20260921))
    se = x.std(ddof=1) / np.sqrt(len(x))
    return dict(n=len(x), E=float(x.mean()), se=float(se), lo=lo, hi=hi,
                win=100.0 * float((x > 0).mean()), block=per_block)


def main() -> int:
    b5 = D.load_csv("data/XAUUSD_M5.csv")
    b15, _ = D.to_15m(b5)
    want = b15.t + 900
    pos = np.searchsorted(b5.t, want)
    nxt = np.where((pos < len(b5)) & (b5.t[np.minimum(pos, len(b5) - 1)] == want),
                   pos, -1)
    c15 = core.Ctx(b15, nxt)

    news_ep = None
    try:
        import calendar_feed
        cal = calendar_feed.load_calendar("data/calendar.csv")
        rows = calendar_feed.build_events(cal, "USD", ("HIGH",))
        news_ep = np.array(sorted(r.epoch for r in rows if r.usable), dtype=np.int64)
    except Exception as e:
        print("calendar unavailable:", e)

    t = pd.to_datetime(b15.t, unit="s", utc=True)
    print("=" * 100)
    print("ADAPTIVE ENGINE - วัดตลาดก่อน แล้วเลือกเครื่องมือเดียวให้สภาวะนั้น")
    print("=" * 100)
    print(f"M15 {len(b15):,} แท่ง {t[0]:%Y-%m-%d} ถึง {t[-1]:%Y-%m-%d} "
          f"= {(t[-1]-t[0]).days} วัน")

    reg = build_regime(b15, news_ep)
    print("\nสภาวะตลาดที่วัดได้ (หน้าต่าง regime 15 วัน, บริบท 45 วัน)")
    vc = reg["regime"].value_counts()
    for k, v in vc.items():
        tool = TOOL_FOR_REGIME.get(k, "NO TRADE")
        print(f"  {k:16s} {v:7,d} แท่ง ({100*v/len(reg):5.1f}%)  -> เครื่องมือ: {tool}")

    prof = hourly_spread_profile(b5)
    print(f"\nรูปทรง spread รายชั่วโมง (คูณกับระดับจริง ${SPREAD_LIVE:.3f})")
    print("  ชั่วโมงที่แพงสุด: " + ", ".join(
        f"{h:02d}:00 x{prof[h]:.2f}" for h in np.argsort(-prof)[:4]))
    print("  ชั่วโมงที่ถูกสุด: " + ", ".join(
        f"{h:02d}:00 x{prof[h]:.2f}" for h in np.argsort(prof)[:4]))

    cut = int(b15.t[-1]) - HOLDOUT_DAYS * 86400
    print(f"\nholdout {HOLDOUT_DAYS} วันสุดท้าย เริ่ม "
          f"{pd.to_datetime(cut, unit='s', utc=True):%Y-%m-%d} - ไม่ใช้เลือกอะไรทั้งสิ้น")

    print("\n" + "=" * 100)
    print("เครื่องมือแต่ละตัว ในสภาวะของตัวเองเท่านั้น")
    print("=" * 100)
    # Every slippage scenario is kept. An earlier version stored only the
    # 0.10 run and then printed its holdout beside a development figure
    # computed at the measured 0.0165 - two numbers from different cost
    # assumptions sitting in one table, which is how a comparison lies without
    # any single number being wrong. Development and holdout are now always
    # read from the SAME run.
    results: dict[tuple[str, float], dict] = {}
    for regime_name, tool in TOOL_FOR_REGIME.items():
        allow = (reg["regime"].to_numpy() == regime_name)
        sig = tool_signals(tool, b15, reg, allow)
        if not sig:
            print(f"\n{tool} ({regime_name}): ไม่มีสัญญาณเลย")
            continue
        print(f"\n{tool}  ใช้เฉพาะ {regime_name}   สัญญาณ {len(sig):,}")
        print(f"   {'slippage':>10s}{'n dev':>7s}{'ชนะ%':>7s}{'dev E':>10s}"
              f"{'dev CI':>22s}{'n ho':>6s}{'holdout E':>11s}")
        for slip in SLIP_GRID:
            costs = cost_series(b15, prof, slip)
            tr, acc = run_with_costs(c15, sig, b5, nxt, costs, slip)
            dev = [x for x in tr if x.t < cut]
            ho = [x for x in tr if x.t >= cut]
            s = clustered_stats(dev)
            hs = clustered_stats(ho)
            results[(tool, slip)] = dict(regime=regime_name, trades=tr,
                                         dev=s, ho=hs, slip=slip)
            if s["n"] < 30:
                print(f"   ${slip:9.4f}: ไม้ช่วงพัฒนา {s['n']} น้อยเกินไป")
                continue
            print(f"   ${slip:9.4f}{s['n']:7d}{s['win']:7.1f}{s['E']:10.4f}"
                  f"  [{s['lo']:+.4f},{s['hi']:+.4f}]{hs['n']:6d}"
                  f"{hs['E']:11.4f}")
            g = np.array([x.gross_R for x in dev])
            n_ = np.array([x.net_R for x in dev])
            if slip == SLIP_GRID[0]:
                print(f"      แยกต้นทุน: gross {g.mean():+.4f} R  "
                      f"ต้นทุนรวม {(g-n_).mean():.4f} R  net {n_.mean():+.4f} R")

    print("\n" + "=" * 100)
    print("CHAMPION / CHALLENGER")
    print("=" * 100)
    REF_SLIP = SLIP_GRID[0]     # the measured one; everything below uses it
    print(f"ทุกตัวเลขข้างล่างใช้ slippage ${REF_SLIP:.4f} (ค่าที่วัดได้) "
          f"ทั้งช่วงพัฒนาและ holdout จาก run เดียวกัน")
    ok = {k[0]: v for k, v in results.items()
          if k[1] == REF_SLIP and v["dev"]["n"] >= 30
          and np.isfinite(v["dev"]["E"])}
    if not ok:
        print("ไม่มีเครื่องมือไหนมีไม้พอจะจัดอันดับ -> NO TRADE")
        return 0
    order = sorted(ok.items(), key=lambda kv: kv[1]["dev"]["E"], reverse=True)
    print("จัดอันดับจากช่วงพัฒนาเท่านั้น (holdout ไม่มีส่วนร่วมในการเลือก):")
    for name, v in order:
        s = v["dev"]
        pos_ci = s["lo"] > 0
        print(f"  {name:10s} ({v['regime']:14s}) ได้ {s['E']:+.4f} R  "
              f"ช่วงเชื่อมั่น [{s['lo']:+.4f}, {s['hi']:+.4f}] "
              f"{'ทั้งช่วงเป็นบวก' if pos_ci else 'คร่อมศูนย์'}")

    champ_name, champ = order[0]
    chall_name = order[1][0] if len(order) > 1 else None
    print(f"\nผู้ท้าชิงอันดับ 1: {champ_name}  (อันดับ 2 เป็น shadow: {chall_name})")
    print("อนุญาตสูงสุด 1 champion + 1 shadow ตาม Amendment 04 ข้อ 4.1")

    s, hs = champ["dev"], champ["ho"]
    print(f"\n{champ_name} ที่ slippage ${REF_SLIP:.4f} เท่ากันทั้งสองช่วง")
    print(f"  ช่วงพัฒนา n={s['n']:5d}  ได้ {s['E']:+.4f} R  [{s['lo']:+.4f}, {s['hi']:+.4f}]")
    print(f"  holdout   n={hs['n']:5d}  ได้ {hs['E']:+.4f} R  "
          f"[{hs['lo']:+.4f}, {hs['hi']:+.4f}]   <- อ่านครั้งเดียว")
    print(f"\n  holdout ที่ทุกระดับต้นทุน (ดูว่าต้นทุนอธิบายการพลิกได้ไหม):")
    for slip in SLIP_GRID:
        r = results.get((champ_name, slip))
        if r and r["ho"]["n"] >= 10:
            print(f"    slippage ${slip:.4f}: dev {r['dev']['E']:+.4f} R  "
                  f"holdout {r['ho']['E']:+.4f} R  "
                  f"ต่าง {r['ho']['E']-r['dev']['E']:+.4f}")
    print("  ถ้าช่องว่างแทบไม่ขยับตามต้นทุน แปลว่าการพลิกไม่ได้มาจากต้นทุน")

    promoted = (np.isfinite(s["lo"]) and s["lo"] > 0
                and np.isfinite(hs["E"]) and hs["E"] > 0)
    print("\n" + "=" * 100)
    if promoted:
        print("ผ่านเกณฑ์ย้อนหลัง แต่ Amendment 04 ข้อ 4.4 กำหนดว่า")
        print("การเลื่อนเป็น champion ต้องผ่าน forward shadow ที่ยังไม่เคยมีอยู่")
        print("ตอนเขียนกฎ -> สถานะตอนนี้: SHADOW CHALLENGER, ยังไม่ใช่ champion")
    else:
        print("สรุป: NO TRADE")
        print("  ไม่มีเครื่องมือไหนที่ช่วงเชื่อมั่นแบบจับกลุ่มอยู่เหนือศูนย์ทั้งช่วง")
        print("  ทุกตัวยังเป็น shadow challenger ไม่มีตัวใดได้เป็น champion")
    print("ไม่มีการส่งคำสั่งใด ๆ และไม่มีฟังก์ชันส่งออเดอร์อยู่ในไฟล์นี้")

    out = Path("research/pilot/results"); out.mkdir(parents=True, exist_ok=True)
    reg[["t", "regime", "dir_eff", "expansion", "atr_pct", "stability"]] \
        .to_csv(out / "regime_timeline.csv", index=False)
    print(f"\nเส้นเวลาสภาวะตลาดบันทึกไว้ที่ {out / 'regime_timeline.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
