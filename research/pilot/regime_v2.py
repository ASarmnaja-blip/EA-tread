"""
Scale-aware regime (v2), implementing Amendment 05 exactly as declared.

v1 asked whether the market was trending. v2 asks whether it is trending in a
way a pullback can survive, which is a different question: a trend built from
gaps and one built from a steady path look identical to a percentile of ATR.

Nothing here is tuned. Every threshold is the 70th or 30th percentile of a
45-day trailing window computed from prior bars, as Amendment 05 section 3
fixed before this file existed, and the one absolute number - the 8 percent
cost-over-ATR gate - is a mechanism choice stated there too.

The run reports v1 and v2 side by side. v1 is a frozen CONTROL that may never
be promoted; v2 is the single challenger. That was declared in advance so the
comparison cannot become a selection.
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

M15_PER_DAY = adaptive.M15_PER_DAY
CTX = adaptive.CONTEXT_D * M15_PER_DAY      # 45 days, the threshold window
HORIZONS = (M15_PER_DAY, 16, 4)             # 1 day, 4 hours, 1 hour
COST_OVER_ATR_MAX = 0.08                    # [DEF] Amendment 05 section 3
SLIP = adaptive.SLIP_GRID[0]


def build_regime_v2(b15: D.Bars, news_ep: np.ndarray | None,
                    spread: float | None = None) -> pd.DataFrame:
    """`spread` is the asset's own, in its own price units.

    It defaults to gold's for backward compatibility, and passing the wrong
    one is not a small error: the cost gate is (spread + slippage) / ATR, so
    charging gold's $0.260 against EURUSD's ATR of 0.0005 gives a ratio of 520
    against a limit of 0.08, and every single bar is classified TOO_EXPENSIVE.
    That is how the first cross-asset run produced zero signals on four of six
    assets and looked like a finding instead of a bug.
    """
    c, h, l, o = b15.c, b15.h, b15.l, b15.o
    n = len(b15)
    atr = core.atr(b15, 14)
    t = pd.to_datetime(b15.t, unit="s", utc=True)
    out = pd.DataFrame({"t": t, "atr": atr})

    safe_c = np.where(c > 0, c, np.nan)
    out["atr_rel"] = atr / safe_c                    # proportional volatility

    rng = h - l
    prev_c = np.concatenate(([c[0]], c[:-1]))
    out["jump_share"] = np.abs(o - prev_c) / np.where(rng > 0, rng, np.nan)

    logc = np.log(np.maximum(c, 1e-9))
    r1 = np.concatenate(([0.0], np.diff(logc)))
    rv = pd.Series(r1).rolling(4).std()
    out["vol_of_vol"] = (rv.rolling(M15_PER_DAY).std()
                         / rv.rolling(M15_PER_DAY).mean()).to_numpy()

    # directional efficiency and slope sign at three horizons
    signs = []
    for k in HORIZONS:
        back = pd.Series(c).shift(k).to_numpy()
        net = c - back
        path = pd.Series(np.abs(r1) * safe_c).rolling(k).sum().to_numpy()
        with np.errstate(divide="ignore", invalid="ignore"):
            out[f"eff_{k}"] = np.where(path > 0, np.abs(net) / path, np.nan)
        signs.append(np.sign(net))
    s = np.vstack(signs)
    out["slope_agree"] = ((s[0] == s[1]) & (s[1] == s[2]) & (s[0] != 0))
    out["slope_dir"] = s[0]

    sp = adaptive.SPREAD_LIVE if spread is None else float(spread)
    slip = SLIP if spread is None else 0.003507 * np.nanmedian(atr)
    with np.errstate(divide="ignore", invalid="ignore"):
        out["cost_over_atr"] = (sp + 2 * slip) / np.where(atr > 0, atr, np.nan)

    def q(col, p):
        return pd.Series(out[col]).rolling(CTX, min_periods=CTX // 3) \
            .quantile(p).to_numpy()

    hi_eff = [out[f"eff_{k}"].to_numpy() >= q(f"eff_{k}", 0.70) for k in HORIZONS]
    lo_eff = out[f"eff_{HORIZONS[0]}"].to_numpy() <= q(f"eff_{HORIZONS[0]}", 0.30)
    n_hi = np.sum(np.vstack([x.astype(int) for x in hi_eff]), axis=0)
    jump_hi = out["jump_share"].to_numpy() >= q("jump_share", 0.70)
    jump_lo = out["jump_share"].to_numpy() <= q("jump_share", 0.30)
    vov_hi = out["vol_of_vol"].to_numpy() >= q("vol_of_vol", 0.70)
    vov_lo = out["vol_of_vol"].to_numpy() <= q("vol_of_vol", 0.30)
    atr_hi = out["atr_rel"].to_numpy() >= q("atr_rel", 0.70)

    ev = np.zeros(n, bool)
    if news_ep is not None and len(news_ep):
        bt = b15.t.astype(np.int64)
        nx = np.searchsorted(news_ep, bt, "left")
        pv = nx - 1
        to_n = np.where(nx < len(news_ep),
                        (news_ep[np.minimum(nx, len(news_ep) - 1)] - bt) / 60, 1e9)
        since = np.where(pv >= 0, (bt - news_ep[np.maximum(pv, 0)]) / 60, 1e9)
        ev = (to_n <= 30) | (since <= 30)

    directional = (n_hi >= 2) & out["slope_agree"].to_numpy()
    regime = np.full(n, "UNDEFINED", dtype=object)
    with np.errstate(invalid="ignore"):
        regime = np.where(ev, "EVENT", regime)
        regime = np.where((regime == "UNDEFINED") & directional
                          & (jump_hi | vov_hi), "SHOCK_TREND", regime)
        regime = np.where((regime == "UNDEFINED") & directional
                          & jump_lo & vov_lo, "ORDERLY_TREND", regime)
        regime = np.where((regime == "UNDEFINED") & atr_hi & lo_eff,
                          "UNSTABLE_HIGH_VOL", regime)
        regime = np.where((regime == "UNDEFINED") & lo_eff & ~atr_hi,
                          "BALANCED_RANGE", regime)
    # the cost gate applies to every state: a move that cannot pay is not taken
    too_dear = out["cost_over_atr"].to_numpy() > COST_OVER_ATR_MAX
    out["too_dear"] = too_dear
    out["regime"] = np.where(too_dear & (regime != "EVENT"), "TOO_EXPENSIVE",
                             regime)
    return out


def evaluate(tag: str, b15, reg, allow, b5, nxt, c15, prof, cut):
    sig = adaptive.tool_signals("pullback", b15, reg, allow)
    if not sig:
        print(f"  {tag}: ไม่มีสัญญาณ")
        return None
    costs = adaptive.cost_series(b15, prof, SLIP)
    tr, _ = adaptive.run_with_costs(c15, sig, b5, nxt, costs, SLIP)
    dev = [x for x in tr if x.t < cut]
    ho = [x for x in tr if x.t >= cut]
    d, hsl = adaptive.clustered_stats(dev), adaptive.clustered_stats(ho)
    if d["n"] < 30:
        print(f"  {tag}: ไม้ช่วงพัฒนา {d['n']} น้อยเกินไป")
        return None
    gd = np.mean([x.gross_R for x in dev])
    gh = np.mean([x.gross_R for x in ho]) if len(ho) > 1 else np.nan
    print(f"  {tag:22s} สัญญาณ {len(sig):5,d}")
    print(f"      ช่วงพัฒนา n={d['n']:5d} gross {gd:+.4f} net {d['E']:+.4f} "
          f"[{d['lo']:+.4f},{d['hi']:+.4f}] ชนะ {d['win']:.1f}%")
    print(f"      holdout   n={hsl['n']:5d} gross {gh:+.4f} net {hsl['E']:+.4f} "
          f"[{hsl['lo']:+.4f},{hsl['hi']:+.4f}]")
    return dict(tag=tag, dev=d, ho=hsl, gross_dev=gd, gross_ho=gh, n_sig=len(sig))


def main() -> int:
    b5 = D.load_csv("data/XAUUSD_M5.csv")
    b15, _ = D.to_15m(b5)
    want = b15.t + 900
    pos = np.searchsorted(b5.t, want)
    nxt = np.where((pos < len(b5)) & (b5.t[np.minimum(pos, len(b5) - 1)] == want),
                   pos, -1)
    c15 = core.Ctx(b15, nxt)
    prof = adaptive.hourly_spread_profile(b5)
    cut = int(b15.t[-1]) - adaptive.HOLDOUT_DAYS * 86400

    news_ep = None
    try:
        import calendar_feed
        cal = calendar_feed.load_calendar("data/calendar.csv")
        rows = calendar_feed.build_events(cal, "USD", ("HIGH",))
        news_ep = np.array(sorted(r.epoch for r in rows if r.usable), dtype=np.int64)
    except Exception:
        pass

    print("=" * 96)
    print("REGIME v2 (Amendment 05) เทียบกับ v1 ที่เป็นตัวควบคุมแช่แข็ง")
    print("=" * 96)

    r1 = adaptive.build_regime(b15, news_ep)
    r2 = build_regime_v2(b15, news_ep)

    print("\nสัดส่วนเวลาในแต่ละสภาวะ")
    for name, reg in (("v1", r1), ("v2", r2)):
        vc = reg["regime"].value_counts()
        print(f"  {name}: " + "  ".join(
            f"{k} {100*v/len(reg):.1f}%" for k, v in vc.head(6).items()))

    print(f"\nด่านต้นทุน: แท่งที่ต้นทุนเกิน {COST_OVER_ATR_MAX:.0%} ของ ATR "
          f"= {100*r2['too_dear'].mean():.1f}% ของทั้งหมด")

    print("\n--- pullback ---")
    res = []
    a = evaluate("v1 STABLE_TREND (ควบคุม)", b15, r1,
                 r1["regime"].to_numpy() == "STABLE_TREND", b5, nxt, c15, prof, cut)
    b = evaluate("v2 ORDERLY_TREND (ท้าชิง)", b15, r2,
                 r2["regime"].to_numpy() == "ORDERLY_TREND", b5, nxt, c15, prof, cut)
    for x in (a, b):
        if x:
            res.append(x)

    print("\n--- สภาวะที่ v2 แยกออกมาใหม่ (ยังไม่มีเครื่องมือประกาศให้ใช้) ---")
    for state in ("SHOCK_TREND", "UNSTABLE_HIGH_VOL"):
        m = r2["regime"].to_numpy() == state
        if m.sum() > 500:
            evaluate(f"{state} (ข้อมูลเท่านั้น)", b15, r2, m, b5, nxt, c15, prof, cut)

    print("\n" + "=" * 96)
    if b is None:
        print("v2 ยังไม่มีไม้พอจะประเมิน -> NO TRADE")
    else:
        flip_v1 = (a["ho"]["E"] - a["dev"]["E"]) if a else np.nan
        flip_v2 = b["ho"]["E"] - b["dev"]["E"]
        print(f"ช่องว่าง holdout − พัฒนา:  v1 {flip_v1:+.4f} R   v2 {flip_v2:+.4f} R")
        if np.isfinite(flip_v1) and abs(flip_v2) < abs(flip_v1):
            print("  v2 พลิกน้อยกว่า -> นิยามสภาวะช่วยได้บางส่วน")
        else:
            print("  v2 ไม่ได้พลิกน้อยกว่า -> นิยามสภาวะไม่ใช่คำอธิบาย")
        print("\nไม่ว่าผลเป็นอย่างไร Amendment 05 ข้อ 4 กำหนดว่า v2 เลื่อนขั้นได้")
        print("ก็ต่อเมื่อผ่าน forward shadow ที่ยังไม่มีอยู่ -> วันนี้ NO TRADE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
