"""The deliberately-bad-tool inversion search, implementing Amendment 09.

Search 150 configurations of the tools retail traders actually use for the ones
that lose most reliably, then test whether mirroring them pays.

THE THREE CAUSES OF A LOSS, and which one mirrors (Amendment 09 section 1):

  cost      does not mirror - the mirror pays it too, both sides lose
  drift     does not mirror - the mirror reduces to being long gold
  anti-timing information   mirrors, and it is the only one that does

So candidates are ranked on EXCESS over a stratified direction-matched placebo,
never on raw expectancy. The control removes the drift, and cost cancels out of
the excess because the placebo pays it too. What is left is the only invertible
quantity. That is also why a negative excess is NOT sufficient: cost having
cancelled from the ranking, it has to be charged back explicitly before asking
whether a mirror is tradeable, which is condition 2 on CONFIRM below.

THE THREE-WAY SPLIT (Amendment 09 section 5) is what makes "tune it to be as bad
as possible" legitimate. Selecting the worst of 150 and testing its mirror on
the same data is the same error as selecting the best and reporting its
backtest:

  SELECT   first 730 days   all 150 scored, the search for the worst happens here
  CONFIRM  next ~245 days   untouched by selection; only the K=5 worst carry
                            forward, and the mirror is judged here
  HOLDOUT  last 120 days    spent already per Amendment 05, not touched here

N = 150 and K = 5 were both counted before any result was read.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import adaptive
import core
import data as D
import junk_tools
import matched_control as MC

# ---------------------------------------------------------------- geometry
STOP_ATR = 1.5
RR = 1.0                      # the operator's choice, same as Amendment 07
TIME_STOP_M5 = 72
ATR_N = 14
WARMUP = 220                  # the slowest tool is a 200-period EMA

# ---------------------------------------------------------------- costs
# Measured on this account; see docs/AMENDMENT_08 section 2.
SPREAD_FALLBACK = 0.090
COMMISSION_RT = 0.140
SLIP_PER_FILL = 0.0165
SWAP_LONG = 0.5493
ROLLOVER_H = 21
COST_MULTIPLIERS = (1.0, 1.5, 3.0, 7.0)

# ---------------------------------------------------------------- protocol
SELECT_DAYS = 730             # Amendment 09 section 5, fixed in advance
HOLDOUT_DAYS = 120
K_CARRY = 5                   # likewise
MIN_TRADES_SELECT = 40
MIN_TRADES_CONFIRM = 50
MIN_NET = 0.05                # the minimum worthwhile edge, unchanged
AMBIG_MAX = 0.15


def mirror_net(entries, b5: D.Bars, nxt: np.ndarray, atr: np.ndarray,
               t_lo: int, t_hi: int, mult: float = 1.0) -> dict:
    """Net expectancy per trade of the MIRROR, with every measured cost charged
    per trade rather than as an average.

    Amendment 08 section 6.3 replaced the single averaged threshold with this,
    because risk distances vary trade by trade and an average cost over an
    average R is not the cost any individual trade paid.
    """
    rows, ambig = [], 0
    busy_until = -1
    for (i, d0) in entries:
        k = int(nxt[i])
        if k < 0 or k <= busy_until:
            continue
        t0 = int(b5.t[k])
        if t0 < t_lo or t0 >= t_hi:
            continue
        a = atr[i]
        if not np.isfinite(a) or a <= 0:
            continue
        d = -d0                                   # the mirror
        entry = b5.o[k]
        risk = STOP_ATR * float(a)
        stop, target = entry - d * risk, entry + d * RR * risk
        px, _, nb = core.resolve(b5, k, d, entry, stop, target, TIME_STOP_M5)
        kx = min(k + nb, len(b5) - 1)
        if b5.l[kx] <= min(stop, target) and b5.h[kx] >= max(stop, target):
            ambig += 1
        g = d * (px - entry) / risk
        sp = (float(b5.sp[k]) if b5.sp is not None and np.isfinite(b5.sp[k])
              and b5.sp[k] > 0 else SPREAD_FALLBACK)
        cost = mult * (sp + COMMISSION_RT + 2.0 * SLIP_PER_FILL)
        net = g - cost / risk
        if d > 0:                                 # gold charges longs only
            t1 = t0 + nb * b5.step
            h0 = (t0 // 3600) % 24
            cur = t0 - (t0 % 3600) + ((ROLLOVER_H - h0) % 24) * 3600
            nights = 0
            while cur <= t1:
                nights += 1
                cur += 86400
            net -= nights * SWAP_LONG / risk
        rows.append((t0 // 86400, g, net))
        busy_until = k + nb
    if len(rows) < 3:
        return dict(n=len(rows))
    import pandas as pd
    net = np.array([r[2] for r in rows])
    day = np.array([r[0] for r in rows], dtype=np.int64)
    mu = float(net.mean())
    grp = pd.Series(net - mu).groupby(day).sum().to_numpy()
    se = float(np.sqrt((grp ** 2).sum())) / len(net)
    return dict(n=len(net), net=mu, se=se, gross=float(np.mean([r[1] for r in rows])),
                t=(mu / se if se > 0 else np.nan), ambig=ambig / len(net),
                days=len(grp))


def candidates(tools: dict, b15: D.Bars) -> dict:
    """The 150 configurations of Amendment 09 section 4, built without looking
    at any outcome."""
    out: dict[str, list] = {}
    n = len(b15)
    idx = np.arange(n)

    # 60 single-tool candidates: 10 tools x 3 settings x 2 directions
    for name, t in tools.items():
        for dname, fire, d in (("long", t.fire_long, 1),
                               ("short", t.fire_short, -1)):
            sel = idx[fire & (idx >= WARMUP) & (idx < n - 1)]
            out[f"{name}/{dname}"] = [(int(i), d) for i in sel]

    # 90 contradiction pairs: A fires in direction d while B's state is -d.
    # The mechanism, stated in Amendment 09 section 2 before any number was
    # read: this fires where the most chart readers are looking at one bar and
    # reaching opposite conclusions, which is where stops pile up on both sides.
    defs = junk_tools.DEFAULTS
    for ai in range(len(defs)):
        for bi in range(ai + 1, len(defs)):
            A, B = tools[defs[ai]], tools[defs[bi]]
            sa = defs[ai].split(":")[0]
            sb = defs[bi].split(":")[0]
            for dname, fire, d in (("long", A.fire_long, 1),
                                   ("short", A.fire_short, -1)):
                m = fire & (B.state == -d) & (idx >= WARMUP) & (idx < n - 1)
                out[f"{sa}+not{sb}/{dname}"] = [(int(i), d) for i in idx[m]]
    return out


def main() -> int:
    b5 = D.load_csv("data/XAUUSD_M5.csv")
    b15, _ = D.to_15m(b5)
    want = b15.t + 900
    pos = np.searchsorted(b5.t, want)
    nxt = np.where((pos < len(b5)) & (b5.t[np.minimum(pos, len(b5) - 1)] == want),
                   pos, -1)
    atr = core.atr(b15, ATR_N)
    prof = adaptive.hourly_spread_profile(b5)

    t0 = int(b15.t[0])
    sel_hi = t0 + SELECT_DAYS * 86400
    hold_lo = int(b15.t[-1]) - HOLDOUT_DAYS * 86400
    i_sel_lo = WARMUP
    i_sel_hi = int(np.searchsorted(b15.t, sel_hi))
    i_con_hi = int(np.searchsorted(b15.t, hold_lo))

    news_ep = None
    try:
        import calendar_feed
        cal = calendar_feed.load_calendar("data/calendar.csv")
        rows = calendar_feed.build_events(cal, "USD", ("HIGH",))
        news_ep = np.array(sorted(r.epoch for r in rows if r.usable),
                           dtype=np.int64)
    except Exception as e:
        print(f"ปฏิทินข่าวโหลดไม่ได้ ({e}) -> ชั้นข่าวเป็น 0 ทั้งหมด")

    print("=" * 108)
    print("JUNK-TOOL INVERSION SEARCH (Amendment 09)")
    print("=" * 108)
    print(f"SELECT  วันที่ 0-{SELECT_DAYS}  แท่ง {i_sel_lo:,}-{i_sel_hi:,}"
          f"   <- ค้นหาตัวที่แย่ที่สุดที่นี่")
    print(f"CONFIRM วันที่ {SELECT_DAYS}-{(hold_lo-t0)//86400}  "
          f"แท่ง {i_sel_hi:,}-{i_con_hi:,}   <- ยังไม่ถูกแตะโดยการคัดเลือก")
    print(f"HOLDOUT {HOLDOUT_DAYS} วันสุดท้าย  ไม่แตะในไฟล์นี้เลย")
    print(f"ต้นทุนที่วัดได้ spread {SPREAD_FALLBACK:.3f} + คอม {COMMISSION_RT:.3f}"
          f" + slip {2*SLIP_PER_FILL:.3f} = "
          f"{SPREAD_FALLBACK+COMMISSION_RT+2*SLIP_PER_FILL:.3f}/oz")
    print("จัดอันดับด้วย 'ส่วนต่างจาก placebo ที่จับคู่ทิศทาง' ไม่ใช่กำไรดิบ")
    print("เพราะกำไรดิบบนกราฟนี้คือการอ่านตลาดกระทิง ไม่ใช่การอ่าน pattern\n")

    tools = junk_tools.build(b15)
    cand = candidates(tools, b15)
    print(f"สร้าง candidate ได้ {len(cand)} แบบ (ประกาศไว้ N=150)")

    st = MC.build_strata(b15, atr, prof, news_ep, i_sel_lo, i_sel_hi)
    runner = MC.make_runner(b5, nxt, atr, STOP_ATR, RR, TIME_STOP_M5)
    print(f"ชั้นที่จับคู่ได้บน SELECT: {len(st.pool)} ชั้น\n")

    print("--- ขั้น SELECT: ให้คะแนนทั้ง 150 แบบ ---")
    res = {}
    skipped = 0
    for tag, ents in cand.items():
        e = [(i, d) for (i, d) in ents if i_sel_lo <= i < i_sel_hi]
        if len(e) < MIN_TRADES_SELECT:
            skipped += 1
            continue
        r = MC.matched_excess(e, st, b5, nxt, atr, STOP_ATR, RR, TIME_STOP_M5,
                              runner=runner)
        if r["n"] >= MIN_TRADES_SELECT:
            res[tag] = r
        else:
            skipped += 1
    print(f"ประเมินได้ {len(res)} แบบ  ข้ามเพราะไม้น้อยกว่า "
          f"{MIN_TRADES_SELECT}: {skipped}")

    if len(res) < 2:
        print("ประเมินได้น้อยเกินไป -> ปิดการค้นหา")
        return 0

    zb = core.bonferroni_z(len(cand))
    mt = MC.maxt_permutation(res, draws=1000)
    print(f"\nmaxT permutation {mt['draws']} รอบ ข้าม {len(res)} candidate: "
          f"ค่าวิกฤต |t| ที่ 95% = {mt['crit']:.3f}")
    print(f"Bonferroni ที่ N={len(cand)}: |t| >= {zb:.3f}")

    ex = np.array([r["excess"] for r in res.values()])
    print(f"\nการกระจายของส่วนต่างทั้งหมด: ค่ากลาง {np.median(ex):+.4f}  "
          f"sd {ex.std(ddof=1):.4f}  ต่ำสุด {ex.min():+.4f}  สูงสุด {ex.max():+.4f}")
    print("ถ้าส่วนต่างเป็นเพียงเสียงรบกวน ค่ากลางควรอยู่แถวศูนย์และไม่มีใครโดดออกมา")

    order = sorted(res.items(), key=lambda kv: kv[1]["excess"])
    print(f"\n{'candidate':28s}{'ไม้':>6s}{'ของเอง':>9s}{'control':>9s}"
          f"{'ส่วนต่าง':>10s}{'se':>8s}{'t':>7s}{'p(maxT)':>10s}")
    print("-" * 108)
    for tag, r in order[:12]:
        print(f"  {tag:26s}{r['n']:6d}{r['own']:9.4f}{r['control']:9.4f}"
              f"{r['excess']:10.4f}{r['se']:8.4f}{r['t']:7.2f}"
              f"{mt['p'].get(tag, float('nan')):10.4f}")
    print("  ... (ฝั่งที่เป็นบวกที่สุด เพื่อไม่ให้รายงานแค่หางเดียว)")
    for tag, r in order[-4:]:
        print(f"  {tag:26s}{r['n']:6d}{r['own']:9.4f}{r['control']:9.4f}"
              f"{r['excess']:10.4f}{r['se']:8.4f}{r['t']:7.2f}"
              f"{mt['p'].get(tag, float('nan')):10.4f}")
    print("-" * 108)

    carry = [t for t, _ in order[:K_CARRY]]
    print(f"\nส่งต่อไป CONFIRM จำนวน K={K_CARRY} ตัวที่ส่วนต่างติดลบที่สุด "
          f"(กำหนดไว้ล่วงหน้า ห้ามเพิ่มหลังเห็นผล):")
    for t in carry:
        print(f"  {t:28s} ส่วนต่าง {res[t]['excess']:+.4f}  t {res[t]['t']:+.2f}"
              f"  p(maxT) {mt['p'].get(t, float('nan')):.4f}")

    print("\n--- ขั้น CONFIRM: ช่วงที่ยังไม่ถูกแตะโดยการคัดเลือก ---")
    st_c = MC.build_strata(b15, atr, prof, news_ep, i_sel_hi, i_con_hi)
    zc = core.bonferroni_z(K_CARRY)
    print(f"ชั้นที่จับคู่ได้บน CONFIRM: {len(st_c.pool)}  "
          f"Bonferroni ที่ N={K_CARRY}: |t| >= {zc:.3f}\n")

    passed = []
    for tag in carry:
        e = [(i, d) for (i, d) in cand[tag] if i_sel_hi <= i < i_con_hi]
        rc = MC.matched_excess(e, st_c, b5, nxt, atr, STOP_ATR, RR,
                               TIME_STOP_M5, runner=runner)
        mn = mirror_net([(i, d) for (i, d) in cand[tag]], b5, nxt, atr,
                        int(b15.t[i_sel_hi]), int(b15.t[i_con_hi]))
        print(f"{tag}")
        if rc.get("n", 0) < 3 or mn.get("n", 0) < 3:
            print("   ไม้บน CONFIRM น้อยเกินไป -> ประเมินไม่ได้\n")
            continue
        sign_ok = rc["excess"] < 0
        n_ok = mn["n"] >= MIN_TRADES_CONFIRM
        net_ok = mn.get("net", -9) >= MIN_NET
        amb_ok = mn["ambig"] < AMBIG_MAX
        sig_ok = abs(mn.get("t", 0)) >= zc
        print(f"   1 ส่วนต่างยังติดลบ: {rc['excess']:+.4f} (SELECT "
              f"{res[tag]['excess']:+.4f})  -> {'ผ่าน' if sign_ok else 'ไม่ผ่าน พลิกเครื่องหมาย'}")
        print(f"   2 net ของตัวกลับด้าน: {mn['net']:+.4f} R  "
              f"(ดิบ {mn['gross']:+.4f})  ต้องถึง {MIN_NET:+.3f} -> "
              f"{'ผ่าน' if net_ok else 'ไม่ผ่าน'}")
        print(f"   3 จำนวนไม้ {mn['n']} ต้องถึง {MIN_TRADES_CONFIRM} -> "
              f"{'ผ่าน' if n_ok else 'ไม่ผ่าน'}")
        print(f"   4 ความกำกวม {100*mn['ambig']:.1f}% -> "
              f"{'ผ่าน' if amb_ok else 'ไม่ผ่าน'}")
        print(f"   5 นัยสำคัญ |t|={abs(mn.get('t',0)):.2f} ต้องถึง {zc:.3f} -> "
              f"{'ผ่าน' if sig_ok else 'ไม่ผ่าน'}")
        line = []
        for m in COST_MULTIPLIERS:
            r2 = mirror_net([(i, d) for (i, d) in cand[tag]], b5, nxt, atr,
                            int(b15.t[i_sel_hi]), int(b15.t[i_con_hi]), mult=m)
            line.append(f"{m:.1f}x {r2.get('net', float('nan')):+.4f}")
        print("   6 ต้นทุนหลายระดับ: " + "  ".join(line))
        if all((sign_ok, net_ok, n_ok, amb_ok, sig_ok)):
            passed.append(tag)
        print()

    print("=" * 108)
    if not passed:
        print("ไม่มี configuration ใดผ่านครบทุกเงื่อนไขของ Amendment 09 ข้อ 6")
        print("บันทึกตามข้อ 8: ปิดสำหรับ 150 configuration นี้ สินค้านี้ กลุ่มข้อมูลนี้")
        print("และแบบจำลองการส่งคำสั่งนี้ - ขอบเขตแค่นี้ ไม่กว้างกว่านี้")
        print("ห้ามเพิ่มเครื่องมือ ขยายกริด เพิ่ม K ขยับเส้นแบ่ง หรือลดเกณฑ์เพราะผลนี้")
    else:
        print(f"มี {len(passed)} configuration ที่ผ่านครบ:")
        for t in passed:
            print(f"  {t}")
        print("ตาม Amendment 09 ข้อ 6 นี่ทำให้มันเป็นได้แค่ shadow challenger")
        print("ต้องมี forward evidence ที่ยังไม่มีอยู่ก่อนจึงจะเลื่อนขั้นได้")
    print("\nสถานะคงเดิม: NO TRADE ไม่มีคำสั่งเงินจริง ไม่มีสถานะเปิด")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
