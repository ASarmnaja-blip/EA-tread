"""The wide two-tailed search: every entry tool, stacked, tuned, both tails.

The operator asked for every entry tool there is including the unpopular ones,
stacked together, parameters swept across the grid, and BOTH tails reported -
the losers to mirror and the winners to look at.

    240 single candidates    40 tools x 3 parameter settings x 2 directions
  3,120 stacked pairs        C(40,2)=780 pairs x 2 directions x 2 stack modes
  -----
  3,360 total, counted before a single number was read

THE HONEST PROBLEM AT THIS SCALE, stated up front. Searching 3,360
configurations for the extremes and then reporting the extremes is a
data-mining machine. Three things are done about it, and none of them is a
caveat bolted on afterwards:

  1. THE GLOBAL TEST COMES FIRST. Before any individual candidate is named, the
     observed distribution of t statistics is compared against the permutation
     null for the whole family. The question "does this family contain more
     extreme values than chance produces" has a defensible answer. The question
     "which one is real" mostly does not, at this N.
  2. THE THREE-WAY SPLIT. Selection happens on SELECT only. A pre-fixed K from
     EACH tail carries to CONFIRM, a slice untouched by the selection. HOLDOUT
     is not read at all.
  3. BOTH TAILS FACE THE SAME GAUNTLET. A winner is not promoted for being
     large; it has to survive CONFIRM exactly as a mirrored loser does. That is
     the only way reporting the winning tail does not turn into a candidate
     generator.

WHAT A LARGE NUMBER HERE IS WORTH. With 3,360 tests the largest |t| in the
family is expected to be around 4 even when nothing is real. A candidate that
does not clear the permutation maxT critical value has not been shown to be
anything, however large its expectancy looks.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import adaptive
import core
import data as D
import matched_control as MC
import tools_wide as TW
import wide_engine as WE

# ---------------------------------------------------------------- geometry
STOP_ATR = 1.5
RR = 1.0
TIME_STOP_M5 = 72
ATR_N = 14
WARMUP = 260                   # the slowest tool is a 200-period EMA

# ------------------------------------------------- measured costs, Amendment 08
SPREAD_FALLBACK = 0.090
COMMISSION_RT = 0.140
SLIP_PER_FILL = 0.0165
SWAP_LONG = 0.5493
COST_MULTIPLIERS = (1.0, 1.5, 3.0, 7.0)

# ---------------------------------------------------------------- protocol
SELECT_DAYS = 730
HOLDOUT_DAYS = 120
K_PER_TAIL = 5
MIN_TRADES_SELECT = 40
MIN_DAYS_SELECT = 20           # Amendment 10 section 3: 50 trades on 6 days
MIN_TRADES_CONFIRM = 50        # do not support day-cluster inference
MIN_DAYS_CONFIRM = 20
MIN_POOL = 30
MIN_NET = 0.05
DRAWS = 1000
MANIFEST = Path("data/wide_search_manifest.json")


def candidates(tools: dict, n: int) -> tuple[dict, dict]:
    """Returns (tier A singles, tier B stacked pairs).

    Amendment 10 section 11.2 gives the tiers different rights. Tier A may name
    a candidate and reach CONFIRM. Tier B is an anonymous global diagnostic and
    may never do either, because no mechanistic hypothesis about any specific
    pair was declared before the pair results existed.
    """
    out: dict[str, list] = {}
    pairs: dict[str, list] = {}
    idx = np.arange(n)
    base = (idx >= WARMUP) & (idx < n - 1)

    for name, t in tools.items():
        for dname, fire, d in (("long", t.fire_long, 1),
                               ("short", t.fire_short, -1)):
            sel = idx[fire & base]
            out[f"{name}/{dname}"] = [(int(i), d) for i in sel]

    # Pairs. The stack is ANCHORED on whichever tool fires, so "A fires while B
    # agrees" and "B fires while A agrees" are different candidates and both
    # anchors must be counted. The first draft of Amendment 10 used one anchor
    # and reported N = 3,360 when the real count is 6,480; Codex caught it.
    defs = TW.DEFAULTS
    for ai in range(len(defs)):
        for bi in range(ai + 1, len(defs)):
            for (anchor, other) in ((defs[ai], defs[bi]), (defs[bi], defs[ai])):
                A, B = tools[anchor], tools[other]
                sa, sb = anchor.split(":")[0], other.split(":")[0]
                for dname, fire, d in (("long", A.fire_long, 1),
                                       ("short", A.fire_short, -1)):
                    m = fire & (B.state == d) & base
                    pairs[f"{sa}&{sb}/{dname}"] = [(int(i), d) for i in idx[m]]
                    m = fire & (B.state == -d) & base
                    pairs[f"{sa}!{sb}/{dname}"] = [(int(i), d) for i in idx[m]]
    return out, pairs


def main() -> int:
    b5 = D.load_csv("data/XAUUSD_M5.csv")
    b15, _ = D.to_15m(b5)
    n = len(b15)
    want = b15.t + 900
    pos = np.searchsorted(b5.t, want)
    nxt = np.where((pos < len(b5)) & (b5.t[np.minimum(pos, len(b5) - 1)] == want),
                   pos, -1)
    atr = core.atr(b15, ATR_N)
    prof = adaptive.hourly_spread_profile(b5)

    t0 = int(b15.t[0])
    i_sel_hi = int(np.searchsorted(b15.t, t0 + SELECT_DAYS * 86400))
    hold_lo = int(b15.t[-1]) - HOLDOUT_DAYS * 86400
    i_con_hi = int(np.searchsorted(b15.t, hold_lo))

    news_ep = None
    try:
        import calendar_feed
        cal = calendar_feed.load_calendar("data/calendar.csv")
        rows = calendar_feed.build_events(cal, "USD", ("HIGH",))
        news_ep = np.array(sorted(r.epoch for r in rows if r.usable),
                           dtype=np.int64)
    except Exception as e:
        print(f"ปฏิทินข่าวโหลดไม่ได้ ({e}) -> ชั้นข่าวเป็น 0")

    print("=" * 112)
    print("WIDE TWO-TAILED SEARCH — เครื่องมือเข้าทุกตัวที่มี ซ้อนกัน จูนค่า ดูทั้งสองหาง")
    print("=" * 112)
    print(f"SELECT  แท่ง {WARMUP:,}-{i_sel_hi:,}   ({SELECT_DAYS} วันแรก) "
          f"<- ค้นหาที่นี่เท่านั้น")
    print(f"CONFIRM แท่ง {i_sel_hi:,}-{i_con_hi:,}   <- ไม่ถูกแตะโดยการคัดเลือก")
    print(f"HOLDOUT {HOLDOUT_DAYS} วันสุดท้าย  ไม่อ่านในไฟล์นี้")
    print("คู่เทียบ = ค่ากลางของชั้นทั้งชั้น (ทิศ ไตรมาส session ATR ข่าว สเปรด)")
    print("ทั้งสองหางต้องผ่านด่านเดียวกัน หางชนะไม่ได้สิทธิ์พิเศษเพราะตัวเลขใหญ่\n")

    print("สร้างเครื่องมือ...")
    tools = TW.build(b15)
    cand, pairs = candidates(tools, n)
    print(f"  เครื่องมือ {len(tools)} configuration จาก {len(TW.DEFAULTS)} ตัว")
    print(f"  ชั้น A (ตัวเดี่ยว) {len(cand):,} แบบ   <- ตั้งชื่อและส่งต่อได้")
    print(f"  ชั้น B (คู่ซ้อน)  {len(pairs):,} แบบ   <- ตรวจระดับตระกูลเท่านั้น "
          f"ห้ามตั้งชื่อหรือส่งต่อ")
    print(f"  รวม {len(cand)+len(pairs):,} (ประกาศไว้ก่อนรัน = 6,480)")

    print("คำนวณผลลัพธ์ต่อแท่งล่วงหน้า (ทำครั้งเดียว ใช้ทุก candidate)...")
    pre = WE.precompute(b5, b15, nxt, atr, STOP_ATR, RR, TIME_STOP_M5,
                        SPREAD_FALLBACK, COMMISSION_RT, SLIP_PER_FILL,
                        SWAP_LONG)
    print(f"  ใช้ได้ {int(pre.ok.sum()):,} แท่ง จาก {n:,}")

    st = MC.build_strata(b15, atr, prof, news_ep, WARMUP, i_sel_hi)
    WE.attach_control(pre, st.key, st.pool, min_pool=MIN_POOL)
    print(f"  ชั้นที่จับคู่ได้บน SELECT {len(st.pool)} ชั้น")
    print("  คู่เทียบตัดวันของไม้นั้นทั้งวันออก (leave-one-day-out)\n")

    print("--- ขั้น SELECT: จัดอันดับและทดสอบระดับตระกูล ไม่อ้างตัวใดตัวหนึ่ง ---")
    scored = {}
    thin = thin_d = 0
    for tag, ents in cand.items():
        r = WE.score(ents, pre, WARMUP, i_sel_hi)
        if r is None or r["n"] < MIN_TRADES_SELECT:
            thin += 1
            continue
        if len(set(r["days"].tolist())) < MIN_DAYS_SELECT:
            thin_d += 1
            continue
        scored[tag] = r
    print(f"ประเมินได้ {len(scored):,} แบบ  ข้ามเพราะไม้ < {MIN_TRADES_SELECT}: "
          f"{thin:,}  ข้ามเพราะวันที่มีไม้ < {MIN_DAYS_SELECT}: {thin_d:,}")
    if len(scored) < 10:
        print("น้อยเกินไป -> หยุด")
        return 0

    fp = WE.family_permutation(scored, draws=DRAWS)
    names, tv, q = fp["names"], fp["t"], fp["q"]
    mu, se_v = fp["mu"], fp["se"]

    # ------------------------------------------------ the power table, first
    # Amendment 10 section 5 requires this BEFORE the search is interpreted. If
    # the detectable effect is far above anything plausible, that is the finding.
    print("\n" + "=" * 112)
    print("ตารางพลังการตรวจจับ — อ่านก่อนดูผล")
    print("=" * 112)
    crit = fp["crit"]
    print(f"ค่าวิกฤต maxT ที่ 95% = |t| {crit:.3f}")
    print(f"{'เปอร์เซ็นไทล์ se':>18s}{'se':>10s}{'effect ที่ต้องมีเพื่อพลัง 80%':>32s}")
    for pct in (25, 50, 75):
        s = float(np.nanpercentile(se_v, pct))
        print(f"{pct:>17d}%{s:10.4f}{(crit + 0.84) * s:>32.4f}")
    plaus = 0.10
    frac = float(np.mean((crit + 0.84) * se_v <= plaus))
    print(f"\nสัดส่วน candidate ที่มีพลังพอจะจับ effect ขนาด {plaus:.2f} R ได้: "
          f"{100*frac:.1f}%")
    print("ถ้าตัวเลขนี้ต่ำ แปลว่ากลุ่มข้อมูลนี้รองรับการชี้ตัวรายตัวไม่ได้")
    print("นั่นคือเหตุผลที่ SELECT ทำได้แค่จัดอันดับ และภาระสถิติย้ายไป CONFIRM")

    print("\n" + "=" * 112)
    print("ด่านแรก: ทั้งตระกูลมีอะไรเกินความบังเอิญหรือไม่ (ถามก่อนจะถามว่าตัวไหน)")
    print("=" * 112)
    a = np.abs(tv)
    print(f"candidate {len(names):,} ตัว  สลับเครื่องหมายรายวัน {fp['draws']:,} รอบ "
          f"บน {fp['ndays']} วัน")
    print(f"ค่าวิกฤต maxT ที่ 95%: |t| = {fp['crit']:.3f}   "
          f"|t| สูงสุดที่วัดได้: {a.max():.3f}")
    n_fwer = int((fp["p_fwer"] < 0.05).sum())
    n_marg = int((fp["p_marg"] < 0.05).sum())
    exp_marg = 0.05 * len(names)
    print(f"ผ่านแบบคุมทั้งตระกูล (maxT p<0.05): {n_fwer}")
    print(f"ผ่านแบบไม่คุม (p<0.05): {n_marg}  เทียบกับที่ความบังเอิญให้ "
          f"{exp_marg:.0f}  อัตราส่วน {n_marg/max(exp_marg,1e-9):.2f}x")
    print(f"Berk-Jones (สัญญาณกระจายทั่วตระกูล) = {fp['bj']:.3f}  "
          f"p จากการสลับ = {fp['p_bj']:.4f}")
    print(f"FDR แบบ BH (รายงานเชิงพรรณนาเท่านั้น ไม่ใช่การคุมอย่างเป็นทางการ): "
          f"q<0.10 ได้ {int((q < 0.10).sum())}   q<0.20 ได้ {int((q < 0.20).sum())}")
    print(f"ค่ากลางของส่วนต่างทั้งตระกูล {np.median(mu):+.5f} R  "
          f"sd {mu.std(ddof=1):.5f}")
    print("\nควอนไทล์ของส่วนต่าง (R): " + "  ".join(
        f"p{p}={np.nanpercentile(mu, p):+.4f}" for p in (1, 5, 25, 50, 75, 95, 99)))
    print("ควอนไทล์ของ t:            " + "  ".join(
        f"p{p}={np.nanpercentile(tv, p):+.2f}" for p in (1, 5, 25, 50, 75, 95, 99)))

    sparse_ok = fp["p_fwer"].min() < 0.05
    distr_ok = fp["p_bj"] < 0.05
    print(f"\nสถิติหลักสองตัวที่ประกาศไว้ล่วงหน้า:")
    print(f"  max|t| (สัญญาณเดี่ยว)      p = {fp['p_fwer'].min():.4f}  -> "
          f"{'มีนัยสำคัญ' if sparse_ok else 'ไม่มีนัยสำคัญ'}")
    print(f"  Berk-Jones (สัญญาณกระจาย)  p = {fp['p_bj']:.4f}  -> "
          f"{'มีนัยสำคัญ' if distr_ok else 'ไม่มีนัยสำคัญ'}")
    if not sparse_ok and not distr_ok:
        print("\nอ่านว่า: ชั้น A ไม่มีอะไรเกินความบังเอิญ ทั้งแบบเดี่ยวและแบบกระจาย")
        print("ตาม Amendment 10 ข้อ 10 ห้ามตั้งชื่อหรือไล่ตาม candidate ใด")
        print("ไม่ว่า t ของมันจะใหญ่แค่ไหน  ด่าน CONFIRM ยังรันต่อเพื่อบันทึก")
    else:
        print("\nอ่านว่า: มีสัญญาณระดับตระกูล ต้องไปดูด่าน CONFIRM")

    # ---------------------------------------------- blinded shortlist, tier A
    ordr = np.argsort(tv)
    lose = [names[j] for j in ordr[:K_PER_TAIL]]
    win = [names[j] for j in ordr[::-1][:K_PER_TAIL]]
    blind = {}
    for r, k in enumerate(lose, 1):
        blind[f"L{r}"] = k
    for r, k in enumerate(win, 1):
        blind[f"W{r}"] = k

    print("\n" + "=" * 112)
    print(f"รายชื่อย่อ K={K_PER_TAIL} จากแต่ละหาง — ปิดชื่อไว้ตาม Amendment 10 ข้อ 6")
    print("=" * 112)
    print("ชื่อจริงจะเปิดเผยเฉพาะตัวที่ผ่าน CONFIRM เท่านั้น เพื่อไม่ให้หางชนะ")
    print("กลายเป็นเครื่องผลิต candidate จากการมองตัวเลขที่ใหญ่ที่สุดใน 6,480 ตัว\n")
    print(f"{'รหัส':6s}{'ไม้':>7s}{'วัน':>6s}{'ส่วนต่าง':>11s}{'se':>9s}{'t':>8s}"
          f"{'p':>9s}{'p(maxT)':>10s}")
    for bid, k in blind.items():
        j = names.index(k)
        print(f"  {bid:4s}{scored[k]['n']:7d}{int(fp['gcl'][j]):6d}{mu[j]:11.4f}"
              f"{se_v[j]:9.4f}{tv[j]:8.2f}{fp['p_marg'][j]:9.4f}"
              f"{fp['p_fwer'][j]:10.4f}")

    import hashlib
    import json
    src = Path(__file__).read_bytes() + Path("research/pilot/tools_wide.py").read_bytes()
    manifest = dict(
        written="2026-09-22", n_tier_a=len(cand), n_tier_b=len(pairs),
        code_sha256=hashlib.sha256(src).hexdigest(),
        select_days=SELECT_DAYS, holdout_days=HOLDOUT_DAYS,
        k_per_tail=K_PER_TAIL, draws=DRAWS,
        maxt_crit=fp["crit"], p_maxt_min=float(fp["p_fwer"].min()),
        berk_jones=fp["bj"], p_berk_jones=fp["p_bj"],
        ids={bid: dict(candidate=k, n=scored[k]["n"],
                       excess=float(mu[names.index(k)]),
                       t=float(tv[names.index(k)])) for bid, k in blind.items()})
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"\nแช่แข็ง manifest (รหัส -> ชื่อจริง + hash ของโค้ด) ไว้ที่ {MANIFEST}")
    print(f"code sha256 {manifest['code_sha256'][:16]}...")

    # ------------------------------------- tier B: anonymous global diagnostic
    print("\n" + "=" * 112)
    print("ชั้น B: คู่ซ้อน — ตรวจระดับตระกูลแบบไม่มีชื่อเท่านั้น")
    print("=" * 112)
    print("Amendment 10 ข้อ 11.2: ไม่มีการประกาศสมมติฐานเชิงกลไกของคู่ใดไว้ก่อน")
    print("จึงห้ามตั้งชื่อ ห้ามทำรายชื่อย่อ ห้ามส่งต่อ ไม่ว่าผลจะเป็นอย่างไร\n")
    sc_b = {}
    tb = tb_d = 0
    for tag, ents in pairs.items():
        r = WE.score(ents, pre, WARMUP, i_sel_hi)
        if r is None or r["n"] < MIN_TRADES_SELECT:
            tb += 1
            continue
        if len(set(r["days"].tolist())) < MIN_DAYS_SELECT:
            tb_d += 1
            continue
        sc_b[tag] = r
    print(f"ประเมินได้ {len(sc_b):,} คู่  ข้ามเพราะไม้น้อย {tb:,}  "
          f"ข้ามเพราะวันน้อย {tb_d:,}")
    if len(sc_b) >= 10:
        fb = WE.family_permutation(sc_b, draws=DRAWS)
        mb, tb_v = fb["mu"], fb["t"]
        print(f"ค่าวิกฤต maxT {fb['crit']:.3f}   |t| สูงสุด {np.abs(tb_v).max():.3f}")
        print(f"max|t| p = {fb['p_fwer'].min():.4f}   "
              f"Berk-Jones {fb['bj']:.3f} p = {fb['p_bj']:.4f}")
        print(f"ผ่านแบบไม่คุม p<0.05: {int((fb['p_marg']<0.05).sum())}  "
              f"เทียบความบังเอิญ {0.05*len(mb):.0f}  "
              f"อัตราส่วน {(fb['p_marg']<0.05).sum()/max(0.05*len(mb),1e-9):.2f}x")
        print("ควอนไทล์ของส่วนต่าง (R): " + "  ".join(
            f"p{p}={np.nanpercentile(mb, p):+.4f}"
            for p in (1, 5, 25, 50, 75, 95, 99)))
        print(f"ค่ากลาง {np.median(mb):+.5f} R  sd {mb.std(ddof=1):.5f}")
        b_sparse = fb["p_fwer"].min() < 0.05
        b_distr = fb["p_bj"] < 0.05
        if not b_sparse and not b_distr:
            print("\nอ่านว่า: การซ้อนเครื่องมือ 6,240 แบบ ไม่ให้อะไรเกินความบังเอิญ")
            print("ทั้งแบบเห็นความเห็นพ้องและแบบเห็นความขัดแย้ง")
        else:
            print("\nอ่านว่า: มีสัญญาณระดับตระกูลในชั้น B -> ขั้นต่อไปคือ amendment ใหม่")
            print("ที่ประกาศสมมติฐานเชิงกลไกของคู่ล่วงหน้า ไม่ใช่หยิบตัวเด่นจากรอบนี้")
    else:
        print("ประเมินได้น้อยเกินไป -> NOT ASSESSED")

    print("\n" + "=" * 112)
    print(f"ขั้น CONFIRM: ส่ง K={K_PER_TAIL} จากแต่ละหาง (กำหนดล่วงหน้า)")
    print("=" * 112)
    st_c = MC.build_strata(b15, atr, prof, news_ep, i_sel_hi, i_con_hi)
    pre_cache = {}
    for m in COST_MULTIPLIERS:
        p2 = WE.precompute(b5, b15, nxt, atr, STOP_ATR, RR, TIME_STOP_M5,
                           SPREAD_FALLBACK, COMMISSION_RT, SLIP_PER_FILL,
                           SWAP_LONG, cost_mult=m)
        WE.attach_control(p2, st_c.key, st_c.pool, min_pool=MIN_POOL)
        pre_cache[m] = p2
    pre_c = pre_cache[1.0]
    print(f"ชั้นบน CONFIRM {len(st_c.pool)} ชั้น")

    # Step-down maxT across exactly the 2K frozen hypotheses, per Amendment 10
    # section 7. A raw threshold would ignore that ten correlated hypotheses are
    # being tested at once; single-step maxT would over-penalise the ones ranked
    # below the top. The null is rebuilt on the CONFIRM slice, not reused.
    order_ids = list(blind)
    conf_scores = {}
    for bid in order_ids:
        r = WE.score(cand[blind[bid]], pre_c, i_sel_hi, i_con_hi)
        if r is not None and r["n"] >= 3:
            conf_scores[bid] = r
    adj = {}
    if len(conf_scores) >= 2:
        fc = WE.family_permutation(conf_scores, draws=DRAWS)
        adjv = WE.stepdown_maxt(fc["t"], fc["nullmat"])
        adj = {k: float(adjv[i]) for i, k in enumerate(fc["names"])}
        print(f"step-down maxT บน {len(conf_scores)} สมมติฐานที่แช่แข็งไว้ "
              f"({DRAWS:,} รอบ)\n")

    passed = []
    for tail, group, invert in (("แพ้ -> ทดสอบตัวกลับด้าน", "L", True),
                                ("ชนะ -> ทดสอบตัวมันเอง", "W", False)):
        print(f"### หาง{tail}")
        for bid in [b for b in blind if b.startswith(group)]:
            tag = blind[bid]
            j = names.index(tag)
            rc = conf_scores.get(bid)
            nt = WE.net_of(cand[tag], pre_c, i_sel_hi, i_con_hi, invert=invert)
            print(f"{bid}   (SELECT ส่วนต่าง {mu[j]:+.4f}  t {tv[j]:+.2f})")
            if rc is None or nt is None:
                print("   ไม้บน CONFIRM น้อยเกินไป -> ประเมินไม่ได้\n")
                continue
            uniq = {d: i for i, d in enumerate(sorted(set(rc["days"].tolist())))}
            ix = np.asarray([uniq[int(d)] for d in rc["days"]])
            cmu, cse, ct = WE.day_t(rc["excess"], ix, len(uniq))
            sign_ok = (cmu < 0) if invert else (cmu > 0)
            n_ok = nt["n"] >= MIN_TRADES_CONFIRM
            d_ok = nt["days"] >= MIN_DAYS_CONFIRM
            net_ok = nt["net"] >= MIN_NET
            pa = adj.get(bid, 1.0)
            sig_ok = pa < 0.05
            print(f"   1 ส่วนต่างบน CONFIRM {cmu:+.4f} (ต้อง"
                  f"{'ติดลบ' if invert else 'เป็นบวก'}) -> "
                  f"{'ผ่าน' if sign_ok else 'ไม่ผ่าน พลิกเครื่องหมาย'}")
            print(f"   2 net ที่จะเทรดจริง {nt['net']:+.4f} R ต้องถึง "
                  f"{MIN_NET:+.3f} -> {'ผ่าน' if net_ok else 'ไม่ผ่าน'}")
            print(f"   3 ไม้ {nt['n']} ต้องถึง {MIN_TRADES_CONFIRM} -> "
                  f"{'ผ่าน' if n_ok else 'ไม่ผ่าน'}   วัน {nt['days']} ต้องถึง "
                  f"{MIN_DAYS_CONFIRM} -> {'ผ่าน' if d_ok else 'ไม่ผ่าน'}")
            print(f"   4 step-down maxT p = {pa:.4f} ต้อง < 0.05 -> "
                  f"{'ผ่าน' if sig_ok else 'ไม่ผ่าน'}")
            line = []
            for m in COST_MULTIPLIERS:
                r2 = WE.net_of(cand[tag], pre_cache[m], i_sel_hi, i_con_hi,
                               invert=invert)
                line.append(f"{m:.1f}x {r2['net']:+.4f}" if r2 else f"{m:.1f}x -")
            print("   5 ต้นทุน: " + "  ".join(line))
            if all((sign_ok, net_ok, n_ok, d_ok, sig_ok)):
                passed.append(bid)
            print()

    print("=" * 112)
    if not passed:
        print("ไม่มี candidate ใดจากหางไหนผ่านครบทุกเงื่อนไข")
        print("ชื่อจริงของทั้งสิบตัวยังคงปิดอยู่ตาม Amendment 10 ข้อ 6")
        print("(บันทึกไว้ใน manifest ที่แช่แข็งแล้ว ตรวจย้อนหลังได้)")
        print(f"บันทึก: ปิดสำหรับ {len(cand)+len(pairs):,} configuration นี้ บนทอง")
        print("บนกลุ่มข้อมูลนี้ และแบบจำลองการส่งคำสั่งนี้ - ขอบเขตแค่นี้")
        print("ห้ามเพิ่มเครื่องมือ ขยายกริด เพิ่ม K หรือลดเกณฑ์เพราะผลนี้")
    else:
        print(f"ผ่านครบ {len(passed)} ตัว -> เปิดชื่อได้ตาม Amendment 10 ข้อ 6:")
        for bid in passed:
            print(f"  {bid} = {blind[bid]}")
        print("ขั้นต่อไปคือ HOLDOUT 120 วัน ซึ่งเปิดได้เฉพาะตัวที่ผ่าน CONFIRM")
        print("และผ่านแล้วก็ได้แค่สถานะ forward shadow ไม่ใช่คำสั่งจริง")
    print("\nสถานะคงเดิม: NO TRADE ไม่มีคำสั่งเงินจริง ไม่มีสถานะเปิด")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
