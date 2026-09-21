"""
Cross-asset replication of ORDERLY_TREND, implementing Amendment 06.

The rule is frozen and identical everywhere. What differs per asset is only
what must: its spread, its ATR, its session clock. Every threshold is a 45-day
trailing percentile computed INSIDE that asset, so nothing leaks between them.

Evidence is combined on the EFFECT ESTIMATES with a random-effects model, not
by stacking orders into one row count. Gold, silver, the majors and an index
move on shared macro events, so pooled rows would count one shock several
times and report a confidence nobody earned.

SLIPPAGE ACROSS ASSETS. Amendment 06 fixes the measured floor at 0.0165 per
fill, which is a dollar figure for gold and meaningless for EURUSD. It is
transferred as a constant fraction of each asset's own volatility:

    slip_per_fill = (0.0165 / 4.705) * ATR_asset = 0.003507 * ATR_asset

4.705 being XAUUSD's median M5 ATR when the slippage was measured. This keeps
the slippage term a fixed share of R everywhere instead of a fixed number of
price units, which would be absurd on a 1.08 quote. The spread is each
asset's own measured per-bar figure and is not transferred at all.

All six assets are reported. None may be dropped after its result is seen.
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
import regime_v2

UNIVERSE = [("XAUUSD", "metals"), ("XAGUSD", "metals"),
            ("EURUSD", "FX"), ("GBPUSD", "FX"), ("USDJPY", "FX"),
            ("US500", "index")]
SLIP_PER_ATR = 0.0165 / 4.705          # measured on XAU, carried as a ratio
COST_MULTIPLIERS = (1.0, 1.5, 3.0, 7.0)
MIN_TRADES = 20                         # below this an asset is reported, not used


def day_clustered(trades) -> tuple[float, float, int, int]:
    """Mean and a standard error that treats one calendar day as one
    observation. Orders opened inside the same session on the same macro
    event are not independent, and a naive SE would say they are."""
    if len(trades) < 3:
        return np.nan, np.nan, len(trades), 0
    x = np.array([t.net_R for t in trades])
    day = np.array([int(t.t) // 86400 for t in trades])
    mu = float(x.mean())
    resid = x - mu
    g = pd.Series(resid).groupby(day).sum().to_numpy()
    n = len(x)
    se = float(np.sqrt((g ** 2).sum())) / n if n else np.nan
    return mu, se, n, len(g)


def random_effects(mus: np.ndarray, ses: np.ndarray):
    """DerSimonian-Laird. Lets the true effect differ by asset rather than
    assuming one number fits all, which is the honest model when the markets
    are not the same market."""
    ok = np.isfinite(mus) & np.isfinite(ses) & (ses > 0)
    y, s = mus[ok], ses[ok]
    if len(y) < 2:
        return dict(pooled=np.nan, se=np.nan, tau2=np.nan, k=len(y),
                    weights=np.array([]))
    w = 1.0 / s ** 2
    fixed = float((w * y).sum() / w.sum())
    Q = float((w * (y - fixed) ** 2).sum())
    c = float(w.sum() - (w ** 2).sum() / w.sum())
    tau2 = max(0.0, (Q - (len(y) - 1)) / c) if c > 0 else 0.0
    wr = 1.0 / (s ** 2 + tau2)
    pooled = float((wr * y).sum() / wr.sum())
    se = float(np.sqrt(1.0 / wr.sum()))
    return dict(pooled=pooled, se=se, tau2=tau2, k=len(y),
                weights=wr / wr.sum(), Q=Q)


def run_asset(sym: str, mult: float) -> dict | None:
    try:
        b5 = D.load_csv(f"data/{sym}_M5.csv")
    except Exception as e:
        print(f"  {sym}: โหลดไม่ได้ {e}")
        return None
    b15, _ = D.to_15m(b5)
    if len(b15) < 5000:
        print(f"  {sym}: แท่ง M15 น้อยเกินไป ({len(b15)})")
        return None
    want = b15.t + 900
    pos = np.searchsorted(b5.t, want)
    nxt = np.where((pos < len(b5)) & (b5.t[np.minimum(pos, len(b5) - 1)] == want),
                   pos, -1)
    c15 = core.Ctx(b15, nxt)

    # the asset's own spread has to be known BEFORE the regime is built,
    # because the cost gate inside it divides by that asset's ATR
    if b5.sp is not None and np.isfinite(b5.sp).any():
        sp_med = float(np.nanmedian(b5.sp[np.isfinite(b5.sp) & (b5.sp > 0)]))
    else:
        sp_med = np.nan
    if not np.isfinite(sp_med) or sp_med <= 0:
        # no spread column: fall back to the symbol's own median range/50,
        # flagged so it cannot be mistaken for a measurement
        sp_med = float(np.nanmedian(b15.h - b15.l)) / 50.0
        measured = False
    else:
        measured = True

    # no calendar is used for ANY asset here, including XAU, so the rule is
    # identical everywhere as Amendment 06 section 4 requires
    reg = regime_v2.build_regime_v2(b15, None, spread=sp_med)
    allow = reg["regime"].to_numpy() == "ORDERLY_TREND"
    # kept whether or not signals appear: an asset with zero signals has to be
    # explainable, and "which state did its bars fall into instead" is the only
    # thing that distinguishes a market that is never orderly from a bug
    comp = (reg["regime"].value_counts() / len(reg)).to_dict()
    sig = adaptive.tool_signals("pullback", b15, reg, allow)
    if not sig:
        return dict(sym=sym, n=0, n_sig=0, mu=np.nan, se=np.nan,
                    spread=sp_med, measured=measured, comp=comp,
                    n_orderly=int(allow.sum()), bars=len(b15))
    atr = reg["atr"].to_numpy()
    costs = mult * (sp_med + 2.0 * SLIP_PER_ATR * atr)

    # SWAP. Measured for XAUUSD only: -0.5493 per ounce per night on longs.
    # It is NOT transferred to the other five. Unlike slippage, swap is an
    # interest-rate differential and has no fixed relation to volatility, so
    # scaling it by ATR would be an invented number, and the standing rule is
    # to report NOT MEASURED rather than guess. The consequence is stated
    # plainly in the output: XAU carries a financing charge the other five do
    # not, so the other five are OPTIMISTIC by an unknown amount, and the
    # share of their trades held across a rollover is printed so the size of
    # the omission is visible instead of hidden.
    swap = adaptive.SWAP_LONG if sym == "XAUUSD" else None
    diag: dict = {}
    tr, _ = adaptive.run_with_costs(c15, sig, b5, nxt, costs, 0.0,
                                    swap=swap, out=diag)
    mu, se, n, ndays = day_clustered(tr)
    gross = float(np.mean([t.gross_R for t in tr])) if tr else np.nan
    return dict(sym=sym, n=n, days=ndays, mu=mu, se=se, gross=gross,
                n_sig=len(sig), spread=sp_med, measured=measured,
                atr=float(np.nanmedian(atr)), comp=comp,
                n_orderly=int(allow.sum()), bars=len(b15),
                swap=swap, on_share=diag.get("overnight_share", np.nan))


def main() -> int:
    print("=" * 98)
    print("CROSS-ASSET REPLICATION ของ ORDERLY_TREND (Amendment 06)")
    print("=" * 98)
    print("กฎเดียวกันทุกสินค้า threshold คำนวณภายในสินค้านั้นเอง")
    print("รวมหลักฐานที่ระดับ effect ไม่ใช่เอาออเดอร์มาต่อกัน\n")

    table = {}
    for mult in COST_MULTIPLIERS:
        rows = []
        print(f"--- ต้นทุน {mult:.1f}x ---")
        print(f"  {'สินค้า':9s}{'กลุ่ม':8s}{'สัญญาณ':>8s}{'ไม้':>6s}{'วัน':>6s}"
              f"{'gross':>9s}{'net R':>9s}{'se':>8s}{'t':>7s}")
        for sym, grp in UNIVERSE:
            r = run_asset(sym, mult)
            if r is None:
                continue
            r["group"] = grp
            rows.append(r)
            if r["n"] < 3:
                print(f"  {sym:9s}{grp:8s}{r.get('n_sig',0):8d}{r['n']:6d}"
                      f"{'':>6s}{'':>9s}   ไม้น้อยเกินไป")
                continue
            t = r["mu"] / r["se"] if r["se"] and r["se"] > 0 else np.nan
            print(f"  {sym:9s}{grp:8s}{r['n_sig']:8d}{r['n']:6d}{r['days']:6d}"
                  f"{r['gross']:9.4f}{r['mu']:9.4f}{r['se']:8.4f}{t:7.2f}")
        table[mult] = rows

        if mult == COST_MULTIPLIERS[0]:
            print("\n  สัดส่วนสภาวะของแต่ละสินค้า (ORDERLY_TREND คือสภาวะเดียวที่ได้เทรด)")
            for r in rows:
                c = r.get("comp") or {}
                top = "  ".join(f"{k} {100*v:.0f}%" for k, v in
                                sorted(c.items(), key=lambda x: -x[1])[:5])
                print(f"      {r['sym']:9s} แท่ง {r.get('bars',0):6,d} "
                      f"orderly {r.get('n_orderly',0):5,d}  {top}")
            print("\n  swap (ค่าถือข้ามคืน) และสัดส่วนไม้ที่ถือข้ามคืน")
            for r in rows:
                s = r.get("swap")
                lab = f"วัดได้ {s:.4f}/คืน" if s is not None else "NOT MEASURED (คิด 0)"
                on = r.get("on_share")
                on_s = f"{100*on:.0f}%" if on is not None and np.isfinite(on) else "-"
                print(f"      {r['sym']:9s} {lab:26s} ไม้ที่ถือข้ามคืน {on_s}")
            print("      => สินค้าที่ยังไม่ได้วัด swap ถูกคิดต้นทุนต่ำกว่าความจริง"
                  " ผลของมันจึงดีเกินจริงอยู่บ้าง")

        use = [r for r in rows if r["n"] >= MIN_TRADES and np.isfinite(r["se"])]
        if len(use) < 2:
            print("  รวมไม่ได้ สินค้าที่มีไม้พอ < 2\n")
            continue
        mus = np.array([r["mu"] for r in use])
        ses = np.array([r["se"] for r in use])
        re_ = random_effects(mus, ses)
        lo = re_["pooled"] - 1.96 * re_["se"]
        hi = re_["pooled"] + 1.96 * re_["se"]
        pos = sum(1 for r in use if r["mu"] > 0)
        wmax = float(re_["weights"].max()) if len(re_["weights"]) else np.nan
        print(f"  รวมแบบ random-effects: {re_['pooled']:+.4f} R  "
              f"[{lo:+.4f}, {hi:+.4f}]  tau2={re_['tau2']:.5f}  k={re_['k']}")
        print(f"  บวก {pos}/{len(use)} สินค้า | น้ำหนักสูงสุดของสินค้าเดียว "
              f"{100*wmax:.0f}%")
        if mult == 1.0:
            for r, w in zip(use, re_["weights"]):
                print(f"      {r['sym']:9s} น้ำหนัก {100*w:5.1f}%  "
                      f"spread {'วัดได้' if r['measured'] else 'ประมาณ'} "
                      f"{r['spread']:.5f}")
            print("\n  leave-one-asset-out:")
            for j, r in enumerate(use):
                keep = [i for i in range(len(use)) if i != j]
                sub = random_effects(mus[keep], ses[keep])
                print(f"      ตัด {r['sym']:9s} ออก -> {sub['pooled']:+.4f} R "
                      f"[{sub['pooled']-1.96*sub['se']:+.4f}, "
                      f"{sub['pooled']+1.96*sub['se']:+.4f}]")
        print()

    print("=" * 98)
    print("ตรวจตามเกณฑ์ที่ประกาศไว้ใน Amendment 06 ข้อ 7")
    print("=" * 98)
    base = [r for r in table[1.0] if r["n"] >= MIN_TRADES and np.isfinite(r["se"])]
    if len(base) < 2:
        print("  ไม่ผ่าน: มีสินค้าที่มีไม้พอน้อยกว่า 2 -> กลไกยังทดสอบไม่ได้")
        print("\nสถานะคงเดิม: ORDERLY_TREND เป็น rare shadow candidate, NO TRADE")
        return 0
    mus = np.array([r["mu"] for r in base]); ses = np.array([r["se"] for r in base])
    re_ = random_effects(mus, ses)
    lo = re_["pooled"] - 1.96 * re_["se"]
    pos = sum(1 for r in base if r["mu"] > 0)
    wmax = float(re_["weights"].max())
    loo_ok = all(random_effects(np.delete(mus, j), np.delete(ses, j))["pooled"] > 0
                 for j in range(len(base)))
    xau = next((r for r in base if r["sym"] == "XAUUSD"), None)
    r15 = [r for r in table[1.5] if r["n"] >= MIN_TRADES and np.isfinite(r["se"])]
    p15 = random_effects(np.array([r["mu"] for r in r15]),
                         np.array([r["se"] for r in r15]))["pooled"] if len(r15) > 1 else np.nan

    checks = {
        "1 ขอบล่างของช่วงรวมอยู่เหนือศูนย์": lo > 0,
        f"2 บวกอย่างน้อย 4 จาก 6 (ได้ {pos}/{len(base)})": pos >= 4,
        "3 leave-one-out ทุกชุดยังบวก": loo_ok,
        f"4 ไม่มีสินค้าไหนน้ำหนักเกิน 35% (สูงสุด {100*wmax:.0f}%)": wmax <= 0.35,
        "5 ต้นทุน 1.5x ยังไม่พลิกเครื่องหมาย": np.isfinite(p15) and p15 > 0,
        "7 XAU เป็นบวก": xau is not None and xau["mu"] > 0,
    }
    for k, v in checks.items():
        print(f"  {'ผ่าน  ' if v else 'ไม่ผ่าน'} {k}")
    print()
    if all(checks.values()):
        print("ผ่านการทดสอบซ้ำข้ามสินค้า -> กลไกมีอยู่จริงในหลายตลาด")
        print("แต่ Amendment 06 ข้อ 2 ระบุว่านี่คือใบอนุญาตให้ทำต่อ ไม่ใช่ใบอนุญาตให้เทรด")
        print("XAU ยังต้องมี forward evidence ของตัวเอง -> วันนี้ NO TRADE")
    else:
        print("ไม่ผ่านการทดสอบซ้ำ -> บันทึกเป็น failed replication")
        print("ตาม Amendment 06 ข้อ 9 ห้ามปรับ ORDERLY_TREND เพราะผลนี้")
        print("สถานะคงเดิม: rare shadow candidate, NO TRADE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
