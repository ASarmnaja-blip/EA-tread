"""
Does gold have a monsoon?

Wind has a direction because something slow sits underneath it - land and sea
heating on a seasonal cycle - and that slow thing lasts for months. The
candle-anatomy round found that the shape of a bar predicts how FAR price
moves and nothing about WHICH WAY. The question this module asks is whether
some slower state predicts the way.

A season, to count here, has to be three things at once:

    slow        it persists long enough to still be there when you act
    visible now you can read it today, not only in hindsight
    directional it says up or down, not merely big or small

Five candidates are tested, each against the SIGNED forward move:

    1 the trend itself   does the past move predict the next one
    2 distance from a moving average
    3 the dollar's own trend  a falling DXY is gold's tailwind
    4 speculative positioning  CFTC net longs, level and change
    5 the calendar  month, weekday, hour

OVERLAP IS THE TRAP HERE. Two windows that share bars share their answer, so
sampling every bar and counting them as independent inflates confidence
enormously - a 5-day horizon sampled every 5 minutes reports 1,440 times more
evidence than it has. Every test below samples NON-OVERLAPPING windows and
reports how few observations that leaves.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import core
import data as D

BARS_PER_DAY = 288                      # M5 bars in 24h
HORIZONS = {                            # [DEF] name -> bars
    "1 hour": 12,
    "4 hours": 48,
    "1 day": BARS_PER_DAY,
    "3 days": 3 * BARS_PER_DAY,
}
COST_R = 0.0717                         # measured round turn, in R
STOP_ATR = 1.5


def fwd_R(b: D.Bars, k: int) -> np.ndarray:
    atr = core.atr(b, 14)
    risk = STOP_ATR * atr
    f = pd.Series(b.c).shift(-k).to_numpy() - b.c
    with np.errstate(divide="ignore", invalid="ignore"):
        return f / np.where(risk > 0, risk, np.nan)


def past_R(b: D.Bars, k: int) -> np.ndarray:
    atr = core.atr(b, 14)
    risk = STOP_ATR * atr
    p = b.c - pd.Series(b.c).shift(k).to_numpy()
    with np.errstate(divide="ignore", invalid="ignore"):
        return p / np.where(risk > 0, risk, np.nan)


def report(title: str, sig: np.ndarray, fwd: np.ndarray, k: int,
           start: int) -> dict | None:
    """Trade the SIGN of `sig`, hold k bars, non-overlapping windows only."""
    idx = np.arange(start, len(sig) - k, k)          # non-overlapping
    s, f = sig[idx], fwd[idx]
    m = np.isfinite(s) & np.isfinite(f) & (s != 0)
    s, f = np.sign(s[m]), f[m]
    n = len(s)
    if n < 25:
        print(f"  {title:44s} n={n:4d}   too few non-overlapping windows")
        return None
    pnl = s * f
    hit = 100.0 * (pnl > 0).mean()
    mean = pnl.mean()
    se = pnl.std(ddof=1) / np.sqrt(n)
    net = mean - COST_R
    print(f"  {title:44s} n={n:4d}  ถูกทาง {hit:5.1f}%  "
          f"ได้ {mean:+7.4f} R  หักค่าธรรมเนียม {net:+7.4f} R  "
          f"ความมั่นใจ t={mean/se:+5.2f}")
    return dict(title=title, n=n, hit=hit, mean=mean, net=net, t=mean / se)


def main() -> int:
    b = D.load_csv("data/XAUUSD_M5.csv")
    n = len(b)
    print("=" * 100)
    print("มีฤดูกาลในทองไหม - ทดสอบสิ่งที่เปลี่ยนช้าว่าบอกทิศทางได้หรือไม่")
    print("=" * 100)
    t = pd.to_datetime(b.t, unit="s", utc=True)
    print(f"ข้อมูล {n:,} แท่ง M5  {t[0]:%Y-%m-%d} ถึง {t[-1]:%Y-%m-%d}  "
          f"= {(t[-1]-t[0]).days} วัน")
    print("ทุกการทดสอบใช้หน้าต่างที่ไม่ทับกัน จึงมีจำนวนตัวอย่างน้อยกว่าที่คิด\n")

    results = []

    # ---------------------------------------------------------- 1 the trend
    print("1) แนวโน้มตัวมันเอง - ที่ผ่านมาขึ้น แล้วต่อไปจะขึ้นไหม")
    for name, k in HORIZONS.items():
        p = past_R(b, k)
        f = fwd_R(b, k)
        r = report(f"มองย้อน {name} แล้วถือต่ออีก {name}", p, f, k, k)
        if r:
            results.append(r)

    # ------------------------------------------- 2 distance from an average
    print("\n2) ราคาอยู่เหนือหรือใต้เส้นค่าเฉลี่ย")
    atr = core.atr(b, 14)
    for days, k in ((1, 48), (5, BARS_PER_DAY), (20, BARS_PER_DAY)):
        win = days * BARS_PER_DAY
        sma = pd.Series(b.c).rolling(win).mean().to_numpy()
        with np.errstate(invalid="ignore"):
            dist = (b.c - sma) / np.where(atr > 0, atr, np.nan)
        f = fwd_R(b, k)
        hold = [nm for nm, v in HORIZONS.items() if v == k][0]
        r = report(f"เหนือ/ใต้ค่าเฉลี่ย {days} วัน แล้วถือ {hold}", dist, f, k, win)
        if r:
            results.append(r)

    # ------------------------------------------------------ 3 the dollar
    print("\n3) ทิศทางของดอลลาร์ (DXY) - ดอลลาร์อ่อน ทองควรแข็ง")
    try:
        dxy = D.load_csv("data/DXY_M5.csv")
        s = pd.Series(dxy.c, index=pd.to_datetime(dxy.t, unit="s", utc=True))
        s = s[~s.index.duplicated()].reindex(t, method="ffill")
        d = s.to_numpy()
        for days, k in ((1, BARS_PER_DAY), (5, BARS_PER_DAY)):
            win = days * BARS_PER_DAY
            chg = d - pd.Series(d).shift(win).to_numpy()
            f = fwd_R(b, k)
            # a FALLING dollar is the gold-positive state, hence the minus
            r = report(f"ดอลลาร์เปลี่ยนแปลงใน {days} วัน (กลับทิศ) ถือ 1 วัน",
                       -chg, f, k, win)
            if r:
                results.append(r)
    except Exception as e:
        print("   DXY ใช้ไม่ได้:", e)

    # -------------------------------------------------- 4 positioning
    print("\n4) สถานะนักเก็งกำไร (CFTC) - คนถือ long เยอะไปแล้วหรือยัง")
    try:
        import calendar_feed
        cal = calendar_feed.load_calendar("data/calendar.csv")
        pos = calendar_feed.positioning_series(cal).dropna(subset=["actual"])
        ps = pd.Series(pos["actual"].to_numpy(),
                       index=pd.to_datetime(pos["epoch"], unit="s", utc=True))
        ps = ps[~ps.index.duplicated()].reindex(t, method="ffill")
        lvl = ps.to_numpy()
        pct = pd.Series(lvl).rolling(52 * 5 * BARS_PER_DAY, min_periods=20 * BARS_PER_DAY) \
            .rank(pct=True).to_numpy()
        chg4 = lvl - pd.Series(lvl).shift(20 * BARS_PER_DAY).to_numpy()
        k = BARS_PER_DAY
        f = fwd_R(b, k)
        r = report("long แออัด (สวนทาง) ถือ 1 วัน", -(pct - 0.5), f, k, 20 * BARS_PER_DAY)
        if r:
            results.append(r)
        r = report("สถานะกำลังเพิ่มขึ้น (ตามทาง) ถือ 1 วัน", chg4, f, k, 20 * BARS_PER_DAY)
        if r:
            results.append(r)
    except Exception as e:
        print("   CFTC ใช้ไม่ได้:", e)

    # ---------------------------------------------------------- 5 calendar
    print("\n5) ปฏิทิน - เดือน วัน ชั่วโมง")
    f1 = fwd_R(b, BARS_PER_DAY)
    df = pd.DataFrame({"t": t, "f": f1})
    df["dow"] = df.t.dt.dayofweek
    df["month"] = df.t.dt.month
    idx = np.arange(0, n - BARS_PER_DAY, BARS_PER_DAY)
    d = df.iloc[idx].dropna(subset=["f"])
    print(f"   ตัวอย่างรายวันที่ไม่ทับกัน: {len(d)} วัน")
    g = d.groupby("dow")["f"].agg(["count", "mean", "std"])
    g["t"] = g["mean"] / (g["std"] / np.sqrt(g["count"]))
    names = {0: "จันทร์", 1: "อังคาร", 2: "พุธ", 3: "พฤหัส", 4: "ศุกร์", 6: "อาทิตย์"}
    print("   วันในสัปดาห์:")
    for i, row in g.iterrows():
        print(f"     {names.get(i, str(i)):8s} n={int(row['count']):3d}  "
              f"เฉลี่ย {row['mean']:+7.4f} R  t={row['t']:+5.2f}")
    mo = d.groupby("month")["f"].agg(["count", "mean"])
    print(f"   เดือน: มีข้อมูลแค่ {len(mo)} เดือน และแต่ละเดือนเกิดขึ้น "
          f"{mo['count'].min()}-{mo['count'].max()} วัน")
    print("     -> ฤดูกาลรายเดือนทดสอบไม่ได้ด้วยข้อมูล 17 เดือน ต้องใช้อย่างน้อย 10 ปี")

    # ---------------------------------------------------------- summary
    print("\n" + "=" * 100)
    print("สรุป - เรียงตามความมั่นใจ")
    print("=" * 100)
    if results:
        rs = pd.DataFrame(results).sort_values("t", key=abs, ascending=False)
        bar = core.bonferroni_z(len(results))
        print(f"ทดสอบ {len(results)} อย่าง -> เกณฑ์ความมั่นใจ t ต้องเกิน {bar:.2f}")
        for _, q in rs.iterrows():
            ok = "ผ่าน" if abs(q.t) >= bar else ""
            print(f"  t={q.t:+6.2f}  หักต้นทุน {q.net:+7.4f} R  n={int(q.n):4d}  "
                  f"{q.title}  {ok}")
        best = rs.iloc[0]
        print(f"\nดีที่สุด: {best['title']}")
        print(f"  ถูกทาง {best['hit']:.1f}% | ได้ {best['mean']:+.4f} R | "
              f"หักค่าธรรมเนียมแล้ว {best['net']:+.4f} R")

    print("\n" + "!" * 100)
    print("คำเตือนเรื่องหน่วย R ที่ต้องอ่านก่อนเชื่อตัวเลขข้างบน")
    print("!" * 100)
    print("R ในทุกบรรทัดคือ 1.5 เท่าของ ATR บนกราฟ 5 นาที ซึ่งเป็นระยะ stop ที่สั้นมาก")
    print("การถือ 1-3 วันโดยใช้ stop ขนาดนั้น จะโดนเขี่ยออกก่อนถึงเป้าเกือบแน่นอน")
    print("ตัวเลขอย่าง +3.0 R จึงไม่ได้แปลว่าเทรดแล้วได้ 3 เท่าของความเสี่ยง")
    print("มันแปลว่า ราคาเคลื่อนไปไกลเท่ากับ 3 เท่าของ stop สั้น ๆ อันนั้น")
    print("ถ้าจะถือ 3 วันจริง stop ต้องกว้างตามความผันผวน 3 วัน ซึ่งจะทำให้ R ใหญ่ขึ้นมาก")
    print("และตัวเลขทั้งหมดหดลงตามสัดส่วน - เทียบกับผลระยะสั้นตรง ๆ ไม่ได้")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
