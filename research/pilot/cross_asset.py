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

# The measured cost model, built read-only from the broker by
# tools/build_cost_model.py. Loaded rather than hardcoded so the numbers in the
# code are always the ones that were actually measured.
def _load_cost_model() -> dict:
    import json
    p = Path("data/cost_model.json")
    if not p.exists():
        print("เตือน: ไม่พบ data/cost_model.json -> ต้นทุนจะถูกประมาณ ไม่ใช่วัด")
        print("      รัน tools/build_cost_model.py ก่อนเพื่อให้ผลเชื่อถือได้")
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


COST_MODEL = _load_cost_model()


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


def _paule_mandel(y: np.ndarray, s: np.ndarray, iters: int = 200) -> float:
    """tau2 by Paule-Mandel: the value at which the weighted residual sum of
    squares equals its own degrees of freedom.

    Replaces DerSimonian-Laird, which Amendment 08 section 6.1 records as the
    wrong estimator at k = 4: tau2 is unstable there and DL can understate
    heterogeneity, and six instruments sharing USD and macro shocks are not
    independent studies. PM solves the estimating equation directly instead of
    using DL's one-step moment approximation.
    """
    k = len(y)
    if k < 2:
        return 0.0
    lo, hi = 0.0, max(1e-12, float(np.var(y, ddof=1)) * 10.0 + 1.0)

    def F(t2):
        w = 1.0 / (s ** 2 + t2)
        mu = (w * y).sum() / w.sum()
        return float((w * (y - mu) ** 2).sum()) - (k - 1)

    if F(0.0) <= 0:
        return 0.0
    for _ in range(iters):
        mid = 0.5 * (lo + hi)
        if F(mid) > 0:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def random_effects(mus: np.ndarray, ses: np.ndarray, hk: bool = True):
    """Random-effects pooling with Paule-Mandel tau2 and a Hartung-Knapp
    interval, per Amendment 08 section 6.1.

    HK replaces the normal critical value with a t quantile on k-1 degrees of
    freedom and rescales the variance by the observed weighted dispersion, which
    is what makes it usable at k = 4. It carries the standard safeguard: when
    its scale factor falls below 1 it would REPORT A NARROWER INTERVAL than the
    uncorrected one, which is the opposite of the point, so the factor is
    floored at 1.
    """
    ok = np.isfinite(mus) & np.isfinite(ses) & (ses > 0)
    y, s = mus[ok], ses[ok]
    k = len(y)
    if k < 2:
        return dict(pooled=np.nan, se=np.nan, tau2=np.nan, k=k,
                    weights=np.array([]), lo=np.nan, hi=np.nan,
                    pi_lo=np.nan, pi_hi=np.nan, hk_scale=np.nan)
    tau2 = _paule_mandel(y, s)
    wr = 1.0 / (s ** 2 + tau2)
    pooled = float((wr * y).sum() / wr.sum())
    se_re = float(np.sqrt(1.0 / wr.sum()))
    Q = float((1.0 / s ** 2 * (y - (y / s ** 2).sum() / (1 / s ** 2).sum()) ** 2).sum())

    if hk:
        scale = float((wr * (y - pooled) ** 2).sum() / (k - 1))
        scale = max(1.0, scale)          # the safeguard; never narrow the CI
        se = se_re * np.sqrt(scale)
        crit = _t_quantile(k - 1)
    else:
        scale, se, crit = 1.0, se_re, 1.96
    lo, hi = pooled - crit * se, pooled + crit * se
    # prediction interval: where a NEW asset's true effect would be expected,
    # which is the quantity that matters for "does the mechanism exist"
    se_pi = float(np.sqrt(se ** 2 + tau2))
    return dict(pooled=pooled, se=se, se_re=se_re, tau2=tau2, k=k,
                weights=wr / wr.sum(), Q=Q, lo=lo, hi=hi, crit=crit,
                hk_scale=scale, pi_lo=pooled - crit * se_pi,
                pi_hi=pooled + crit * se_pi)


def _t_quantile(df: int, p: float = 0.975) -> float:
    """Two-sided 95 % t quantile. Small table plus a normal tail, because
    scipy is not a dependency of this pilot."""
    tbl = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447,
           7: 2.365, 8: 2.306, 9: 2.262, 10: 2.228, 12: 2.179, 15: 2.131,
           20: 2.086, 30: 2.042, 60: 2.000}
    if df in tbl:
        return tbl[df]
    keys = sorted(tbl)
    if df < keys[0]:
        return tbl[keys[0]]
    if df > keys[-1]:
        return 1.96
    for a, b in zip(keys, keys[1:]):
        if a < df < b:
            f = (df - a) / (b - a)
            return tbl[a] + f * (tbl[b] - tbl[a])
    return 1.96


def synchronised_day_bootstrap(per_asset: dict[str, list], n_draws: int = 2000,
                               seed: int = 20260922) -> dict:
    """Resample CALENDAR DAYS and keep every asset's trades from a selected day
    together, per Amendment 08 section 6.2.

    Clustering each instrument by its own days, which is what the first run did,
    says nothing about one macro release moving all six at once. This is the
    dependence that matters: if a CPI print drives gold, silver and the majors
    on the same afternoon, those are one observation about the mechanism, not
    six. tau2 and the pooled estimate are recomputed INSIDE every draw, so the
    heterogeneity is resampled too rather than held fixed.

    `per_asset` maps a symbol to a list of (day, net_R) pairs.
    """
    rng = np.random.default_rng(seed)
    days = sorted({d for rows in per_asset.values() for (d, _) in rows})
    if len(days) < 20:
        return dict(lo=np.nan, hi=np.nan, n=0, days=len(days))
    idx: dict[int, dict[str, list[float]]] = {d: {} for d in days}
    for sym, rows in per_asset.items():
        for (d, x) in rows:
            idx[d].setdefault(sym, []).append(x)
    darr = np.array(days)
    pooled = []
    for _ in range(n_draws):
        pick = rng.choice(darr, size=len(darr), replace=True)
        acc: dict[str, list[float]] = {}
        for d in pick:
            for sym, xs in idx[int(d)].items():
                acc.setdefault(sym, []).extend(xs)
        mus, ses = [], []
        for sym, xs in acc.items():
            if len(xs) < MIN_TRADES:
                continue
            a = np.asarray(xs, dtype=float)
            mus.append(float(a.mean()))
            ses.append(float(a.std(ddof=1) / np.sqrt(len(a))))
        if len(mus) < 2:
            continue
        r = random_effects(np.array(mus), np.array(ses), hk=False)
        if np.isfinite(r["pooled"]):
            pooled.append(r["pooled"])
    if len(pooled) < 100:
        return dict(lo=np.nan, hi=np.nan, n=len(pooled), days=len(days))
    p = np.array(pooled)
    return dict(lo=float(np.percentile(p, 2.5)),
                hi=float(np.percentile(p, 97.5)),
                med=float(np.median(p)), n=len(p), days=len(days),
                share_positive=float(np.mean(p > 0)))


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

    # the asset's own cost has to be known BEFORE the regime is built, because
    # the cost gate inside it divides by that asset's ATR
    #
    # The first run estimated the spread from the export's per-bar column while
    # DROPPING every bar whose spread was zero. On this account 94.1 percent of
    # EURUSD bars and 92.2 percent of USDJPY bars record zero, and a live
    # measurement confirms the zeros are REAL - it is a commission account that
    # genuinely quotes those pairs at zero spread. Dropping them left the median
    # of the widest few percent, which is what classified 99 percent of EURUSD's
    # bars TOO_EXPENSIVE and produced zero signals. The cost now comes from the
    # measured model instead, and commission is charged - it never was before,
    # anywhere, and on a zero-spread pair it is the entire cost.
    cm = COST_MODEL.get(sym)
    if cm:
        sp_med = float(cm["spread_live"]) + float(cm["commission_price_round_turn"])
        swap = (float(-cm["swap_long_price_per_night"]),
                float(-cm["swap_short_price_per_night"]))
        measured = True
    else:
        sp_med = float(np.nanmedian(b15.h - b15.l)) / 50.0
        swap = None
        measured = False

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

    # SWAP is now measured for all six, read-only from symbol_info, so the
    # NOT MEASURED caveat the first run carried is removed rather than papered
    # over. It never needed transferring across instruments: it is an
    # interest-rate differential, and the broker publishes it. GBPUSD charges
    # both sides, which is why it is passed as a (long, short) pair.
    diag: dict = {}
    tr, _ = adaptive.run_with_costs(c15, sig, b5, nxt, costs, 0.0,
                                    swap=swap, out=diag)
    mu, se, n, ndays = day_clustered(tr)
    gross = float(np.mean([t.gross_R for t in tr])) if tr else np.nan
    return dict(sym=sym, n=n, days=ndays, mu=mu, se=se, gross=gross,
                n_sig=len(sig), spread=sp_med, measured=measured,
                atr=float(np.nanmedian(atr)), comp=comp,
                n_orderly=int(allow.sum()), bars=len(b15),
                swap=swap, on_share=diag.get("overnight_share", np.nan),
                rows=[(int(t.t) // 86400, float(t.net_R)) for t in tr])


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
                if s is None:
                    lab = "NOT MEASURED (คิด 0)"
                elif isinstance(s, (tuple, list)):
                    lab = f"วัดได้ L {s[0]:.6f} / S {s[1]:.6f}"
                else:
                    lab = f"วัดได้ {s:.6f}/คืน"
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
        lo, hi = re_["lo"], re_["hi"]
        pos = sum(1 for r in use if r["mu"] > 0)
        wmax = float(re_["weights"].max()) if len(re_["weights"]) else np.nan
        print(f"  รวมแบบ random-effects (Paule-Mandel + Hartung-Knapp):")
        print(f"      {re_['pooled']:+.4f} R  ช่วงความเชื่อมั่น "
              f"[{lo:+.4f}, {hi:+.4f}]  tau2={re_['tau2']:.5f}  k={re_['k']}  "
              f"ตัวคูณ HK {re_['hk_scale']:.2f}  t({re_['k']-1}) {re_['crit']:.3f}")
        print(f"      ช่วงทำนายสินค้าตัวใหม่ [{re_['pi_lo']:+.4f}, "
              f"{re_['pi_hi']:+.4f}]  <- ตัวนี้ตอบว่ากลไกมีจริงหรือไม่")
        print(f"  บวก {pos}/{len(use)} สินค้า | น้ำหนักสูงสุดของสินค้าเดียว "
              f"{100*wmax:.0f}%")
        if mult == 1.0:
            print("  จำนวนวันที่เป็นกลุ่มอิสระของแต่ละสินค้า: " + "  ".join(
                f"{r['sym']} {r['days']}" for r in use))
            boot = synchronised_day_bootstrap(
                {r["sym"]: r["rows"] for r in use})
            if np.isfinite(boot.get("lo", np.nan)):
                print(f"  bootstrap สุ่มวันพร้อมกันทุกสินค้า "
                      f"({boot['n']} รอบ จาก {boot['days']} วัน):")
                print(f"      ค่ากลาง {boot['med']:+.4f} R  "
                      f"[{boot['lo']:+.4f}, {boot['hi']:+.4f}]  "
                      f"รอบที่เป็นบวก {100*boot['share_positive']:.0f}%")
                print("      นี่คือช่วงที่นับว่าข่าวหนึ่งตัวขยับทุกสินค้าพร้อมกัน"
                      " = หนึ่งข้อสังเกต")
            xag = next((r for r in use if r["sym"] == "XAGUSD"), None)
            if xag and xag["rows"]:
                by_day: dict[int, list[float]] = {}
                for (d, x) in xag["rows"]:
                    by_day.setdefault(d, []).append(x)
                worst_lo, worst_hi, worst_d = np.inf, -np.inf, None
                for d in by_day:
                    kept = [x for (dd, x) in xag["rows"] if dd != d]
                    if len(kept) < 5:
                        continue
                    m = float(np.mean(kept))
                    if m < worst_lo:
                        worst_lo, worst_d = m, d
                    worst_hi = max(worst_hi, m)
                print(f"  XAGUSD ตัดออกทีละวัน: ค่าเฉลี่ยแกว่งอยู่ระหว่าง "
                      f"{worst_lo:+.4f} ถึง {worst_hi:+.4f} R "
                      f"(เดิม {xag['mu']:+.4f})")
            for r, w in zip(use, re_["weights"]):
                print(f"      {r['sym']:9s} น้ำหนัก {100*w:5.1f}%  "
                      f"spread {'วัดได้' if r['measured'] else 'ประมาณ'} "
                      f"{r['spread']:.5f}")
            print("\n  leave-one-asset-out:")
            for j, r in enumerate(use):
                keep = [i for i in range(len(use)) if i != j]
                sub = random_effects(mus[keep], ses[keep])
                print(f"      ตัด {r['sym']:9s} ออก -> {sub['pooled']:+.4f} R "
                      f"[{sub['lo']:+.4f}, {sub['hi']:+.4f}]")
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
    lo = re_["lo"]
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
