"""
Current signal and shadow logger — what the engine says about right now.

Emits the full schema CLAUDE.md section 6 requires, including the fields that
usually get quietly dropped: what the market has probably priced in, the news
that could break the premise, the invalidation level, the expiry, and the
reason for NO TRADE when there is one. A NO TRADE with no reason is not a
conclusion, it is a missing answer (ENGINE_PROTOCOL section 11).

Confidence is calibrated from measured results, never asserted. When the tool
a regime selects has a negative measured expectancy, the confidence field says
so instead of producing a number that looks reassuring.

Re-evaluation follows CLAUDE.md section 4: every bar for entry and
invalidation, every ~4 hours or on a session change for the regime, and around
a release. Drift is checked on every run against the frozen Research Watch
baseline.

THIS FILE CANNOT TRADE. It imports no order function. It appends a row to a
shadow log and prints a report.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import adaptive
import core
import data as D

SHADOW_LOG = Path("research/pilot/results/shadow_log.csv")
REGIME_REFRESH_H = 4          # [DEF] CLAUDE.md section 4
SESSIONS = {"ASIA": (22, 7), "LONDON": (7, 13), "OVERLAP": (13, 16),
            "NY": (16, 21), "BREAK": (21, 22)}

# Baselines frozen by Amendment 04 / measured by adaptive.py on the
# development period at the $0.10 slippage assumption. Drift is measured
# against these and they are not updated from a run's own results.
BASELINE = {
    "pullback":  dict(regime="STABLE_TREND",   E=+0.0351, win=39.9, n=1337),
    "breakout":  dict(regime="VOL_EXPANSION",  E=-0.0233, win=38.6, n=1514),
    "reversion": dict(regime="BALANCED_RANGE", E=-0.1146, win=34.7, n=1662),
    "news":      dict(regime="EVENT",          E=-0.1829, win=30.1, n=276),
}


def session_of(h: int) -> str:
    for name, (a, b) in SESSIONS.items():
        if a <= b:
            if a <= h < b:
                return name
        elif h >= a or h < b:
            return name
    return "OTHER"


def fetch_live(symbol="XAUUSD", bars=40000):
    # 40,000 M5 bars is about 139 calendar days. The context window is 45
    # TRADING days of M15, which is 4,320 M15 bars = 12,960 M5 bars, and the
    # rolling quantiles need a full window before they return anything. A
    # first version pulled 4,000 bars and every regime input came back NaN,
    # which the engine then reported as UNDEFINED - a data shortage wearing
    # the costume of an unreadable market.
    """Pull the most recent M5 bars straight from the terminal, so 'current'
    means current. Read-only: copy_rates_from_pos and symbol_info_tick."""
    try:
        import MetaTrader5 as mt5
    except Exception:
        return None, None, None
    if not mt5.initialize():
        return None, None, None
    try:
        mt5.symbol_select(symbol, True)
        r = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M5, 0, bars)
        if r is None or not len(r):
            return None, None, None
        info = mt5.symbol_info(symbol)
        tick = mt5.symbol_info_tick(symbol)
        b = D.Bars(r["time"], r["open"], r["high"], r["low"], r["close"],
                   r["tick_volume"], 300, symbol,
                   r["spread"] * info.point if "spread" in r.dtype.names else None)
        spec = dict(spread_now=info.spread * info.point, bid=tick.bid,
                    ask=tick.ask, digits=info.digits,
                    contract=info.trade_contract_size,
                    server_time=int(tick.time))
        return b, spec, mt5.account_info().server
    finally:
        mt5.shutdown()


def build_signal() -> dict:
    live, spec, server = fetch_live()
    if live is not None and len(live) > 1000:
        b5, source = live, f"MT5 สด ({server})"
    else:
        b5, spec, source = D.load_csv("data/XAUUSD_M5.csv"), None, "ไฟล์ CSV"

    b15, _ = D.to_15m(b5)
    want = b15.t + 900
    pos = np.searchsorted(b5.t, want)
    nxt = np.where((pos < len(b5)) & (b5.t[np.minimum(pos, len(b5) - 1)] == want),
                   pos, -1)

    news_ep = None
    next_news_min = None
    try:
        import calendar_feed
        cal = calendar_feed.load_calendar("data/calendar.csv")
        rows = calendar_feed.build_events(cal, "USD", ("HIGH",))
        news_ep = np.array(sorted(r.epoch for r in rows if r.usable), dtype=np.int64)
        now = int(b15.t[-1])
        fut = news_ep[news_ep > now]
        if len(fut):
            next_news_min = (int(fut[0]) - now) / 60.0
        posdf = calendar_feed.positioning_series(cal)
        positioning = calendar_feed.positioning_at(posdf, now)
    except Exception as e:
        positioning = f"NOT ASSESSED: {e}"

    reg = adaptive.build_regime(b15, news_ep)
    i = len(b15) - 1
    regime = str(reg["regime"].iloc[i])
    tool = adaptive.TOOL_FOR_REGIME.get(regime)
    atr = float(reg["atr"].iloc[i])
    stability = float(reg["stability"].iloc[i])
    t_now = pd.to_datetime(int(b15.t[i]), unit="s", utc=True)
    sess = session_of(t_now.hour)

    prof = adaptive.hourly_spread_profile(b5)
    spread_model = adaptive.SPREAD_LIVE * prof[t_now.hour]
    cost_R = (spread_model + 2 * 0.10) / (adaptive.STOP_ATR * atr) if atr > 0 else np.nan

    out = dict(
        generated_utc=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        bar_time_utc=str(t_now), source=source, symbol="XAUUSD",
        timeframe="M15 signal / M5 execution",
        session=sess, regime=regime, stability=round(stability, 4),
        atr_m15=round(atr, 3),
        spread_model=round(spread_model, 4),
        spread_now=(round(spec["spread_now"], 4) if spec else None),
        cost_R=round(float(cost_R), 4) if np.isfinite(cost_R) else None,
        tool=tool or "NONE",
        direction="NEUTRAL", entry=None, stop=None, target=None,
        risk_R=1.0, expiry_bars_m5=adaptive.TIME_STOP_M5,
        confidence="NOT ASSESSED",
        priced_in="NOT ASSESSED: no consensus-distribution feed",
        positioning=positioning,
        yields="NOT ASSESSED: no bond or yield symbol on this account",
        narrative="NOT ASSESSED: no narrative feed in this project",
        news_risk=(f"ข่าว USD HIGH ถัดไปอีก {next_news_min:.0f} นาที"
                   if next_news_min is not None else "ไม่มีข่าวที่ประเมินได้ข้างหน้า"),
        decision="NO_TRADE", reason="", evidence="", invalidation="",
    )

    # A market that cannot be classified and a window that has not filled are
    # different answers, and collapsing them would let a data shortage be
    # reported as a reading of the market.
    inputs = {"dir_eff": reg["dir_eff"].iloc[i],
              "expansion": reg["expansion"].iloc[i],
              "atr_pct": reg["atr_pct"].iloc[i],
              "stability": stability}
    missing = [k for k, v in inputs.items() if not np.isfinite(v)]
    if missing:
        out["regime"] = "INSUFFICIENT_DATA"
        out["decision"] = "NO_TRADE"
        out["tool"] = "NONE"
        out["reason"] = (f"ยังสรุปสภาวะตลาดไม่ได้เพราะหน้าต่างข้อมูลยังไม่เต็ม: "
                         f"{', '.join(missing)} ยังคำนวณไม่ได้ "
                         f"(มีแท่ง M15 {len(b15):,} แท่ง ต้องการอย่างน้อย "
                         f"{adaptive.CONTEXT_D * adaptive.M15_PER_DAY:,}) "
                         f"- นี่คือข้อมูลไม่พอ ไม่ใช่ตลาดอ่านไม่ออก")
        out["evidence"] = "; ".join(f"{k}={v}" for k, v in inputs.items())
        return out

    if tool is None:
        out["reason"] = (f"สภาวะตลาดอ่านได้เป็น {regime} ซึ่งไม่มีเครื่องมือไหน"
                         f"ถูกประกาศให้ใช้ -> ยืนดู")
        out["evidence"] = (f"dir_eff={inputs['dir_eff']:.3f} "
                           f"expansion={inputs['expansion']:.3f} "
                           f"atr_pct={inputs['atr_pct']:.0f} "
                           f"stability={stability:.3f}")
        return out

    base = BASELINE.get(tool, {})
    allow = np.zeros(len(b15), bool)
    allow[i] = True
    sig = adaptive.tool_signals(tool, b15, reg, allow)

    out["evidence"] = (f"regime={regime} (dir_eff={reg['dir_eff'].iloc[i]:.3f}, "
                       f"expansion={reg['expansion'].iloc[i]:.3f}, "
                       f"atr_pct={reg['atr_pct'].iloc[i]:.0f}, "
                       f"stability={stability:.3f}); "
                       f"เครื่องมือที่สภาวะนี้อนุญาต: {tool}")

    if base and base.get("E", 0) <= 0:
        out["confidence"] = (f"ไม่มี - {tool} วัดได้ {base['E']:+.4f} R ต่อไม้ "
                             f"ในสภาวะ {base['regime']} จาก {base['n']} ไม้ "
                             f"(ติดลบ)")
    elif base:
        out["confidence"] = (f"สอบเทียบจาก {base['n']} ไม้: ชนะ {base['win']:.1f}% "
                             f"ได้เฉลี่ย {base['E']:+.4f} R - ช่วงเชื่อมั่นยังคร่อมศูนย์")

    if not sig:
        out["reason"] = (f"สภาวะคือ {regime} เครื่องมือที่อนุญาตคือ {tool} "
                         f"แต่เงื่อนไขเข้าของมันไม่เกิดบนแท่งนี้")
        return out

    _, d, stop, _, tval = sig[0]
    entry = float(b5.c[-1])
    risk = abs(entry - stop)
    out.update(direction=("LONG" if d > 0 else "SHORT"),
               entry=round(entry, 3), stop=round(float(stop), 3),
               target=round(entry + d * tval * risk, 3),
               invalidation=f"ปิดไม้ทันทีถ้าราคาแตะ {stop:.3f} "
                            f"หรือสภาวะเปลี่ยนออกจาก {regime}")

    # Amendment 04 section 4.4: nothing is promoted on history alone
    out["decision"] = "NO_TRADE"
    out["reason"] = (
        f"เครื่องมือ {tool} ให้สัญญาณ {out['direction']} จริงบนแท่งนี้ "
        f"แต่ยังไม่ถูกเลื่อนเป็น champion - Amendment 04 ข้อ 4.4 กำหนดว่า"
        f"ต้องผ่าน forward shadow ก่อน และผลวัดย้อนหลังของมัน"
        f"{'ติดลบ' if base.get('E', 0) <= 0 else 'ยังคร่อมศูนย์'} "
        f"-> บันทึกเป็น shadow ไม่ส่งคำสั่ง")
    return out


def drift_check() -> list[str]:
    """Compare what the shadow log has seen lately against the frozen
    baseline. Reported, never used to change a parameter."""
    notes = []
    if not SHADOW_LOG.exists():
        return ["ยังไม่มีประวัติ shadow log - เริ่มนับจากรอบนี้"]
    df = pd.read_csv(SHADOW_LOG)
    if len(df) < 20:
        return [f"shadow log มี {len(df)} แถว ยังน้อยเกินกว่าจะตรวจ drift"]
    recent = df.tail(200)
    for tool, base in BASELINE.items():
        g = recent[recent.tool == tool]
        if len(g) < 10:
            continue
        share = 100.0 * len(g) / len(recent)
        notes.append(f"{tool}: ถูกเลือก {share:.0f}% ของรอบล่าสุด "
                     f"(baseline regime {base['regime']})")
    rg = recent.regime.value_counts(normalize=True) * 100
    notes.append("สัดส่วนสภาวะล่าสุด: " +
                 ", ".join(f"{k} {v:.0f}%" for k, v in rg.head(4).items()))
    return notes


def main() -> int:
    s = build_signal()
    print("=" * 96)
    print("CURRENT SIGNAL - XAUUSD")
    print("=" * 96)
    order = [
        ("เวลาแท่งล่าสุด (UTC)", "bar_time_utc"), ("แหล่งข้อมูล", "source"),
        ("Session", "session"), ("สภาวะตลาด (Regime)", "regime"),
        ("ความเสถียรของสภาวะ", "stability"),
        ("เครื่องมือที่สภาวะนี้อนุญาต", "tool"),
        ("ทิศทาง", "direction"), ("Entry", "entry"), ("Stop", "stop"),
        ("Target", "target"), ("ความเสี่ยง", "risk_R"),
        ("อายุสัญญาณ (แท่ง M5)", "expiry_bars_m5"),
        ("Confidence", "confidence"), ("ATR M15", "atr_m15"),
        ("spread ที่ใช้คิด", "spread_model"), ("spread ตอนนี้", "spread_now"),
        ("ต้นทุนคิดเป็น R", "cost_R"),
        ("สิ่งที่ตลาด price in แล้ว", "priced_in"),
        ("สถานะนักเก็งกำไร", "positioning"),
        ("US yields", "yields"), ("Narrative", "narrative"),
        ("ความเสี่ยงจากข่าว", "news_risk"),
        ("เงื่อนไขยกเลิก", "invalidation"),
        ("หลักฐาน", "evidence"),
        ("คำตัดสิน", "decision"), ("เหตุผล", "reason"),
    ]
    for label, key in order:
        v = s.get(key)
        if v in (None, ""):
            v = "-"
        print(f"  {label:28s}: {v}")

    print("\n" + "-" * 96)
    print("DRIFT CHECK")
    for n in drift_check():
        print("  " + n)

    SHADOW_LOG.parent.mkdir(parents=True, exist_ok=True)
    row = pd.DataFrame([s])
    header = not SHADOW_LOG.exists()
    row.to_csv(SHADOW_LOG, mode="a", header=header, index=False,
               encoding="utf-8")
    print(f"\nบันทึกลง shadow log แล้ว: {SHADOW_LOG}")
    print("ไฟล์นี้ไม่มีฟังก์ชันส่งคำสั่งใด ๆ และไม่เคยเรียก order_send")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
