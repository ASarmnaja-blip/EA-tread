"""
Why does the pullback flip sign between development and holdout?

At a matched cost the tool earns +0.0853 R on the development period and
-0.1359 R on the last 120 days. A peer review set out the order to test this
in, and the order matters: three explanations are all still live and they
demand different responses.

    cost            a cheaper or dearer round turn moved the answer
    composition     the market's mix of states changed, so the SAME rule met
                    different conditions
    decay           the rule met the same conditions and stopped working

Cost is already eliminated upstream: the development-minus-holdout gap is
-0.221, -0.212, -0.199 and -0.173 R at slippage 0.0165, 0.05, 0.10 and 0.20.
It barely moves. What follows separates the other two.

  1. GROSS, before any cost. If gross flips too, cost is confirmed innocent.
  2. Feature distributions on both sides, so a composition shift is visible
     rather than assumed.
  3. Importance reweighting: re-weight development trades so their feature mix
     matches the holdout's. If the reweighted development figure turns
     negative, the market changed. If it stays positive while the holdout is
     negative, the rule decayed.

No parameter is tuned here and nothing is selected. This is a post-mortem on a
candidate that is already frozen as SHADOW / NO TRADE.
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

TOOL = "pullback"
REGIME = "STABLE_TREND"
SLIP = adaptive.SLIP_GRID[0]


def describe(tag: str, tr: list) -> dict:
    g = np.array([x.gross_R for x in tr])
    n = np.array([x.net_R for x in tr])
    d = np.array([x.dir for x in tr])
    r = np.array([x.risk for x in tr])
    b = np.array([x.bars for x in tr])
    why = np.array([x.why for x in tr])
    out = dict(tag=tag, n=len(tr), gross=g.mean(), net=n.mean(),
               long_share=100 * (d > 0).mean(), risk=np.median(r),
               bars=np.median(b),
               target=100 * (why == "target").mean(),
               stop=100 * (why == "stop").mean(),
               time=100 * (why == "time").mean())
    return out


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
    except Exception:
        pass

    reg = adaptive.build_regime(b15, news_ep)
    allow = reg["regime"].to_numpy() == REGIME
    sig = adaptive.tool_signals(TOOL, b15, reg, allow)
    prof = adaptive.hourly_spread_profile(b5)
    costs = adaptive.cost_series(b15, prof, SLIP)
    tr, acc = adaptive.run_with_costs(c15, sig, b5, nxt, costs, SLIP)
    cut = int(b15.t[-1]) - adaptive.HOLDOUT_DAYS * 86400

    dev = [x for x in tr if x.t < cut]
    ho = [x for x in tr if x.t >= cut]
    print("=" * 96)
    print(f"ทำไม {TOOL} ถึงพลิกเครื่องหมาย - แยกสาเหตุตามลำดับ")
    print("=" * 96)
    print(f"ไม้ทั้งหมด {len(tr):,}  ช่วงพัฒนา {len(dev):,}  holdout {len(ho):,}")

    print("\n--- ขั้นที่ 1: ดู GROSS ก่อนหักต้นทุน ---")
    a, b = describe("ช่วงพัฒนา", dev), describe("holdout", ho)
    print(f"  {'':12s}{'n':>6s}{'gross':>10s}{'net':>10s}{'ซื้อ%':>8s}"
          f"{'risk$':>8s}{'แท่ง':>7s}{'เป้า%':>7s}{'stop%':>7s}{'เวลา%':>7s}")
    for x in (a, b):
        print(f"  {x['tag']:12s}{x['n']:6d}{x['gross']:10.4f}{x['net']:10.4f}"
              f"{x['long_share']:8.1f}{x['risk']:8.2f}{x['bars']:7.0f}"
              f"{x['target']:7.1f}{x['stop']:7.1f}{x['time']:7.1f}")
    print(f"\n  gross ต่างกัน {b['gross']-a['gross']:+.4f} R  "
          f"net ต่างกัน {b['net']-a['net']:+.4f} R")
    if np.sign(a["gross"]) != np.sign(b["gross"]):
        print("  -> gross พลิกด้วย ยืนยันว่าต้นทุนไม่ใช่สาเหตุ")
    else:
        print("  -> gross ไม่พลิก สาเหตุอาจอยู่ที่ต้นทุน")

    print("\n--- ขั้นที่ 2: สภาพตลาดตอนเข้าไม้ ต่างกันไหม ---")
    idx = {int(b5.t[nxt[i]]): i for (i, *_r) in acc if nxt[i] >= 0}
    feats = ["dir_eff", "expansion", "atr_pct", "stability", "atr"]
    rows = []
    for tag, group in (("ช่วงพัฒนา", dev), ("holdout", ho)):
        ii = [idx[int(x.t)] for x in group if int(x.t) in idx]
        rec = dict(tag=tag, n=len(ii))
        for f in feats:
            rec[f] = float(np.nanmedian(reg[f].to_numpy()[ii])) if ii else np.nan
        sess = pd.Series([c15.session[i] for i in ii]).value_counts(normalize=True)
        rec["NY%"] = 100 * sess.get("NY", 0.0)
        rec["LONDON%"] = 100 * sess.get("LONDON", 0.0)
        rows.append(rec)
    df = pd.DataFrame(rows)
    print(df.to_string(index=False, float_format=lambda v: f"{v:9.4f}"))
    print("\n  ความต่างเป็นสัดส่วน:")
    for f in feats + ["NY%", "LONDON%"]:
        x, y = df[f].iloc[0], df[f].iloc[1]
        if np.isfinite(x) and np.isfinite(y) and x != 0:
            print(f"    {f:12s} {x:9.4f} -> {y:9.4f}   ({100*(y-x)/abs(x):+6.1f}%)")

    print("\n--- ขั้นที่ 3: ถ่วงน้ำหนักช่วงพัฒนาให้เหมือน holdout ---")
    print("  ถ้าถ่วงแล้วกลายเป็นลบ = ตลาดเปลี่ยน | ถ้ายังบวก = กฎเสื่อม")
    ii_dev = [idx[int(x.t)] for x in dev if int(x.t) in idx]
    ii_ho = [idx[int(x.t)] for x in ho if int(x.t) in idx]
    # Reweighting on a PERCENTILE cannot correct a LEVEL shift, because the
    # percentile is constructed to be blind to the level. Median ATR went from
    # 3.26 to 7.56 - it more than doubled - while its percentile FELL from 40
    # to 30. So the percentile version below answers a different question than
    # the one the data is asking, and the absolute version after it is the one
    # that matters.
    if len(ii_dev) > 50 and len(ii_ho) > 20:
        key = "atr_pct"
        bins = np.array([0, 20, 40, 60, 80, 101])
        dv = np.digitize(reg[key].to_numpy()[ii_dev], bins) - 1
        hv = np.digitize(reg[key].to_numpy()[ii_ho], bins) - 1
        wd = pd.Series(dv).value_counts(normalize=True)
        wh = pd.Series(hv).value_counts(normalize=True)
        w = np.array([wh.get(k, 0.0) / wd.get(k, 1e-9) for k in dv])
        gross = np.array([x.gross_R for x in dev if int(x.t) in idx])
        net = np.array([x.net_R for x in dev if int(x.t) in idx])
        print(f"  สัดส่วน {key} ช่วงพัฒนา: "
              + ", ".join(f"{k}:{100*v:.0f}%" for k, v in sorted(wd.items())))
        print(f"  สัดส่วน {key} holdout  : "
              + ", ".join(f"{k}:{100*v:.0f}%" for k, v in sorted(wh.items())))
        print(f"  ช่วงพัฒนาเดิม        gross {gross.mean():+.4f}  net {net.mean():+.4f}")
        print(f"  ถ่วงน้ำหนักใหม่แล้ว   gross {np.average(gross, weights=w):+.4f}"
              f"  net {np.average(net, weights=w):+.4f}")
        print(f"  holdout จริง          gross {b['gross']:+.4f}  net {b['net']:+.4f}")
        rw = np.average(net, weights=w)
        if rw < 0:
            print("\n  -> ถ่วงแล้วติดลบ: ส่วนผสมของสภาพตลาดคือคำอธิบายหลัก")
        elif b["net"] < 0:
            print("\n  -> ถ่วงแล้วยังบวกแต่ holdout ติดลบ: กฎเสื่อมหรือกลไกไม่เสถียร")

    print("\n--- ขั้นที่ 3ข: ถ่วงด้วย ATR สัมบูรณ์ และเทียบเฉพาะไม้ที่ผันผวนพอกัน ---")
    if len(ii_dev) > 50 and len(ii_ho) > 20:
        atr_all = reg["atr"].to_numpy()
        ad, ah = atr_all[ii_dev], atr_all[ii_ho]
        edges = np.array([0, 3, 5, 7, 9, 1e9])
        dbin = np.digitize(ad, edges) - 1
        hbin = np.digitize(ah, edges) - 1
        wd = pd.Series(dbin).value_counts(normalize=True)
        wh = pd.Series(hbin).value_counts(normalize=True)
        lab = {0: "<3", 1: "3-5", 2: "5-7", 3: "7-9", 4: ">9"}
        print("  สัดส่วนไม้ตามระดับ ATR จริง:")
        print("    ช่วงพัฒนา: " + ", ".join(
            f"{lab[k]}:{100*v:.0f}%" for k, v in sorted(wd.items())))
        print("    holdout  : " + ", ".join(
            f"{lab[k]}:{100*v:.0f}%" for k, v in sorted(wh.items())))
        gd = np.array([x.gross_R for x in dev if int(x.t) in idx])
        nd = np.array([x.net_R for x in dev if int(x.t) in idx])
        w2 = np.array([wh.get(k, 0.0) / wd.get(k, 1e-9) for k in dbin])
        if w2.sum() > 0:
            print(f"  ช่วงพัฒนาถ่วงด้วย ATR จริง: gross "
                  f"{np.average(gd, weights=w2):+.4f}  "
                  f"net {np.average(nd, weights=w2):+.4f}")
        print("\n  เทียบเฉพาะไม้ที่ ATR สูงพอ ๆ กัน (>= 5):")
        for tag, ii, group in (("ช่วงพัฒนา", ii_dev, dev), ("holdout", ii_ho, ho)):
            g2 = [x for x, i in zip([y for y in group if int(y.t) in idx], ii)
                  if atr_all[i] >= 5.0]
            if len(g2) >= 20:
                gg = np.array([x.gross_R for x in g2])
                nn = np.array([x.net_R for x in g2])
                se = nn.std(ddof=1) / np.sqrt(len(nn))
                print(f"    {tag:10s} n={len(g2):4d}  gross {gg.mean():+.4f}  "
                      f"net {nn.mean():+.4f}  se {se:.4f}")
            else:
                print(f"    {tag:10s} n={len(g2)} น้อยเกินไป")

    print("\n--- ขั้นที่ 4: ความต่างนี้ใหญ่เกินความบังเอิญไหม ---")
    g1 = np.array([x.net_R for x in dev])
    g2 = np.array([x.net_R for x in ho])
    rng = np.random.default_rng(20260921)
    diffs = []
    for _ in range(2000):
        s1 = rng.choice(g1, size=len(g1), replace=True)
        s2 = rng.choice(g2, size=len(g2), replace=True)
        diffs.append(s2.mean() - s1.mean())
    diffs = np.array(diffs)
    lo, hi = np.percentile(diffs, [2.5, 97.5])
    print(f"  ความต่าง holdout − พัฒนา = {g2.mean()-g1.mean():+.4f} R")
    print(f"  ช่วงเชื่อมั่น 95% จาก bootstrap [{lo:+.4f}, {hi:+.4f}]")
    print(f"  ครอบคลุมศูนย์ไหม: {'ใช่ - อาจเป็นความบังเอิญ' if lo <= 0 <= hi else 'ไม่ - ความต่างนี้ของจริง'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
