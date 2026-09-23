"""Walk-forward over the Amendment 14 grid, with Amendment 16's eleven corrections.

THE QUESTION. Not "does rule X have an edge" but:

    does ranking 8,250 cells on the last 60 days predict which of them work over
    the next 10 days?

That is what an adaptive engine actually does, and it is the question CLAUDE.md
section 1 asks. The earlier searches fitted the OLDEST two years and withheld the
newest, so they answered "did this work in 2023-2024" instead.

THE ELEVEN CORRECTIONS, all from Codex's pre-run review, which refused to run the
first version of this design:

  1  an 84-hour RESOLUTION EMBARGO. The longest forward path one signal needs is an
     H4 limit with 15-bar expiry (60 h) plus the 24-hour time stop. A trade counts
     toward selection only if its EXIT resolves before the cutoff, not merely if
     its signal did. Purged counts are reported.
  2  the holdout is truncated by 20 days + 84 hours, so no signal, pending order,
     exit or decay horizon can reach it.
  3  bucket edges frozen from the selection window (the ATR tercile already uses a
     trailing per-bar percentile, which is sound; the spread bucket is the one that
     leaked and is now frozen).
  4  ONE OBSERVATION PER ROLL, with common sign flips over contiguous SIX-ROLL
     blocks, because adjacent rolls share 50 of their 60 selection days.
  5  equal-weight TOP-5 / CENTRAL-5 / BOTTOM-5 cell means. Trades are NOT pooled
     across cells - pooling lets the busiest cell dominate.
  6  primary statistic D_r = mean(Top5 fwd) - mean(Bottom5 fwd); U_r and L_r
     against the central five with a JOINT max-statistic adjustment.
  7  duplicate cells collapsed by trade signature INSIDE each roll, since 8,250
     definitions is not 8,250 realised strategies in a 60-day window.
  8  a cell-roll with no forward trade contributes ZERO (policy return), decided in
     advance; per-trade edge is secondary and conditional on firing.
  9  the selection trade-count distribution of all three groups is reported,
     because a 15-trade floor on a raw mean selects for variance.
 10  the decay curve uses the same six-roll blocks, not day flips.
 11  W1-scale rarity is NOT ASSESSED and says so whatever the result.

And Amendment 16 section 15: D_r is a difference between two groups on the same
roll in the same market, so drift cancels in the subtraction and no placebo is
needed for the primary. The MDE is printed FIRST, above the numbers.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import core
import data as D
import mtf_engine as E

DAY = 86400
SEL_DAYS = 60
FWD_DAYS = 10
STEP_DAYS = 10
HOLDOUT_DAYS = 120
EMBARGO_S = 84 * 3600                     # correction 1
DECAY_DAYS = (1, 3, 5, 10, 20)
BUFFER_S = 20 * DAY + EMBARGO_S           # correction 2
MIN_TRADES_SEL = 15
MIN_DAYS_SEL = 8
K = 5
BLOCK_ROLLS = 6                           # correction 4
DRAWS = 4000
SEED = 20260922


# ------------------------------------------------------------------ precompute
def build_universe(b5: D.Bars, t_end: int):
    """Every cell's complete trade list, once. Returns {tag: arrays}.

    Signals are computed per (setup, timeframe); fills per (setup, timeframe,
    entry mode); and resolve_plane answers the whole 25-cell (stop, target) plane
    from one forward pass per fill. Without that the run is tens of millions of
    Python-level bar steps.
    """
    out = {}
    meta = {}
    for (tfname, mult) in E.TIMEFRAMES:
        bs, nxt = E.resample(b5, mult)
        keep = bs.t <= t_end
        atr_s = core.atr(bs, E.ATR_N)
        ctx = core.Ctx(bs, nxt)
        for setup in E.SETUPS:
            sig = [(i, d) for (i, d) in E.setup_signals(setup, ctx)
                   if keep[i]]
            if not sig:
                continue
            for (off, exp) in E.ENTRY_MODES:
                fills = []
                for (i, d) in sig:
                    k0 = int(nxt[i])
                    a = atr_s[i]
                    if k0 < 0 or not np.isfinite(a) or a <= 0:
                        continue
                    if exp == 0:
                        k, entry = k0, float(b5.o[k0])
                    else:
                        lim = float(bs.c[i]) - d * off * float(a)
                        got = E.entry_fill(b5, k0, d, lim, exp * mult)
                        if got is None:
                            continue
                        k, entry = got
                    fills.append((k, d, entry, float(a)))
                if len(fills) < MIN_TRADES_SEL:
                    continue
                planes = []
                for (k, d, entry, a) in fills:
                    planes.append(E.resolve_plane(b5, k, d, entry, a, E.STOPS,
                                                  E.TARGETS, E.TIME_STOP_M5))
                for st in E.STOPS:
                    for tg in E.TARGETS:
                        tag = (f"{setup}/{tfname}/s{st:g}/t{tg:g}"
                               f"/o{off:g}e{exp}")
                        t_in, t_out, net, sigk = [], [], [], []
                        risks, directions, dollars = [], [], []
                        entries, exit_indices = [], []
                        busy = -1
                        for j, (k, d, entry, a) in enumerate(fills):
                            if k <= busy:
                                continue
                            g, why, nb = planes[j][(st, tg)]
                            risk = st * a
                            kx = min(k + nb, len(b5) - 1)
                            sp = (float(b5.sp[k]) if b5.sp is not None
                                  and np.isfinite(b5.sp[k]) and b5.sp[k] > 0
                                  else E.SPREAD_FALLBACK)
                            cost = sp + E.COMMISSION_RT + 2 * E.SLIP_PER_FILL
                            nt = g - cost / risk
                            if d > 0 and E.SWAP_LONG:
                                t0 = int(b5.t[k])
                                # Use the actual exit timestamp.  `nb * 300`
                                # silently skips weekend rollover charges.
                                t1 = int(b5.t[kx])
                                nights = E.rollover_nights(t0, t1)
                                nt -= nights * E.SWAP_LONG / risk
                            t_in.append(int(b5.t[k]))
                            t_out.append(int(b5.t[kx]))
                            net.append(nt)
                            sigk.append(k)
                            risks.append(risk)
                            directions.append(d)
                            # XAUUSD contract size is 100 oz and the Demo
                            # minimum is 0.01 lot, hence one price unit is
                            # one USD.  Keeping this alongside R lets later
                            # portfolio audits report the actual minimum-lot
                            # finance result without reconstructing fills.
                            dollars.append(nt * risk)
                            entries.append(entry)
                            exit_indices.append(kx)
                            busy = k + nb
                        if len(t_in) >= MIN_TRADES_SEL:
                            out[tag] = dict(
                                t_in=np.array(t_in, np.int64),
                                t_out=np.array(t_out, np.int64),
                                net=np.array(net, float),
                                sigk=np.array(sigk, np.int64),
                                risk=np.array(risks, float),
                                direction=np.array(directions, np.int8),
                                dollars=np.array(dollars, float),
                                entry=np.array(entries, float),
                                exit_k=np.array(exit_indices, np.int64))
                            meta[tag] = dict(setup=setup, tf=tfname, stop=st,
                                             target=tg, off=off, exp=exp)
    return out, meta


# ------------------------------------------------------------------ one roll
def roll_scores(uni: dict, sel_lo: int, sel_hi: int, fwd_hi: int):
    """Selection score, forward score and trade signature for every cell.

    Correction 1: a trade counts toward SELECTION only if `t_out < sel_hi`, so
    nothing that resolves after the cutoff can influence the ranking.
    """
    sel, fwd, n_sel, d_sel, sig = {}, {}, {}, {}, {}
    purged = 0
    for tag, a in uni.items():
        m_sig = (a["t_in"] >= sel_lo) & (a["t_in"] < sel_hi)
        if not m_sig.any():
            continue
        m_res = m_sig & (a["t_out"] < sel_hi)
        purged += int(m_sig.sum() - m_res.sum())
        if m_res.sum() < MIN_TRADES_SEL:
            continue
        days = np.unique(a["t_in"][m_res] // DAY)
        if len(days) < MIN_DAYS_SEL:
            continue
        sel[tag] = float(a["net"][m_res].mean())
        n_sel[tag] = int(m_res.sum())
        d_sel[tag] = len(days)
        # correction 7: the realised trade set inside this window is the identity
        sig[tag] = a["sigk"][m_res].tobytes()
        mf = (a["t_in"] >= sel_hi) & (a["t_in"] < fwd_hi)
        # correction 8: no forward trade contributes ZERO, not missing
        fwd[tag] = float(a["net"][mf].mean()) if mf.any() else 0.0
    return sel, fwd, n_sel, d_sel, sig, purged


def pick_groups(sel: dict, sig: dict):
    """Rank, collapsing duplicate realised trade sets to one representative."""
    seen, uniq = set(), []
    for tag in sorted(sel, key=lambda t: -sel[t]):
        if sig[tag] in seen:
            continue
        seen.add(sig[tag])
        uniq.append(tag)
    dup = len(sel) - len(uniq)
    if len(uniq) < 3 * K:
        return None, None, None, dup, len(uniq)
    mid = len(uniq) // 2
    return (uniq[:K], uniq[mid - K // 2: mid - K // 2 + K], uniq[-K:], dup,
            len(uniq))


# ------------------------------------------------------- block permutation
def block_flip_p(x: np.ndarray, block: int, draws: int, seed: int,
                 one_sided: bool = True):
    """Sign-flip permutation on contiguous blocks of rolls (correction 4)."""
    rng = np.random.default_rng(seed)
    n = len(x)
    nb = int(np.ceil(n / block))
    obs = float(x.mean())
    null = np.empty(draws)
    for j in range(draws):
        f = np.repeat(rng.choice([-1.0, 1.0], size=nb), block)[:n]
        null[j] = float((x * f).mean())
    if one_sided:
        p = (np.sum(null >= obs) + 1.0) / (draws + 1.0)
    else:
        p = (np.sum(np.abs(null) >= abs(obs)) + 1.0) / (draws + 1.0)
    return obs, float(p), null


def main() -> int:
    b5 = D.load_csv("data/XAUUSD_M5.csv")
    t_last = int(b5.t[-1])
    hold_lo = t_last - HOLDOUT_DAYS * DAY
    t_end = hold_lo - BUFFER_S                     # correction 2
    t0 = int(b5.t[0])

    print("=" * 100)
    print("WALK-FORWARD (Amendment 15 + 16) — ทดสอบว่า 'การเลือกจากอดีตล่าสุด' ใช้ได้ไหม")
    print("=" * 100)
    print(f"เลือกจาก {SEL_DAYS} วันล่าสุด -> วัดผล {FWD_DAYS} วันถัดไป -> "
          f"เลื่อนทีละ {STEP_DAYS} วัน")
    print(f"ตัดข้อมูลท้ายทิ้ง {BUFFER_S/DAY:.1f} วัน (= 20 วัน + 84 ชม.) "
          f"เพื่อไม่ให้แตะ holdout เลย")
    print(f"ห้ามนับไม้ที่ยังไม่ปิดก่อนเส้นแบ่ง (embargo 84 ชม.)")
    print(f"หนึ่งค่าต่อรอบ สลับเครื่องหมายเป็นก้อนละ {BLOCK_ROLLS} รอบ\n")

    print("สร้างชุดไม้ของทุกช่องล่วงหน้า (ทำครั้งเดียว)...")
    uni, meta = build_universe(b5, t_end)
    print(f"  ช่องที่มีไม้พอ {len(uni):,} จาก {E.n_cells():,} ที่ประกาศไว้")
    if len(uni) < 3 * K:
        print("น้อยเกินไป -> หยุด")
        return 0

    rolls = []
    s = t0 + SEL_DAYS * DAY
    while s + FWD_DAYS * DAY <= t_end:
        rolls.append(s)
        s += STEP_DAYS * DAY
    print(f"  จำนวนรอบ {len(rolls)}  -> ก้อนอิสระราว "
          f"{int(np.ceil(len(rolls)/BLOCK_ROLLS))} ก้อน\n")

    Dv, Uv, Lv = [], [], []
    ntop, nmid, nbot, dups, purges, nocell = [], [], [], [], [], 0
    decay = {h: [] for h in DECAY_DAYS}
    for s in rolls:
        sel, fwd, n_sel, d_sel, sig, purged = roll_scores(
            uni, s - SEL_DAYS * DAY, s, s + FWD_DAYS * DAY)
        purges.append(purged)
        if len(sel) < 3 * K:
            nocell += 1
            continue
        top, mid, bot, dup, nu = pick_groups(sel, sig)
        if top is None:
            nocell += 1
            continue
        dups.append(dup)
        ft = float(np.mean([fwd[t] for t in top]))
        fm = float(np.mean([fwd[t] for t in mid]))
        fb = float(np.mean([fwd[t] for t in bot]))
        Dv.append(ft - fb)
        Uv.append(ft - fm)
        Lv.append(fb - fm)
        ntop.append(np.mean([n_sel[t] for t in top]))
        nmid.append(np.mean([n_sel[t] for t in mid]))
        nbot.append(np.mean([n_sel[t] for t in bot]))
        for h in DECAY_DAYS:
            hi = s + h * DAY
            vt = [float(uni[t]["net"][(uni[t]["t_in"] >= s)
                                     & (uni[t]["t_in"] < hi)].mean())
                  if ((uni[t]["t_in"] >= s) & (uni[t]["t_in"] < hi)).any()
                  else 0.0 for t in top]
            vb = [float(uni[t]["net"][(uni[t]["t_in"] >= s)
                                     & (uni[t]["t_in"] < hi)].mean())
                  if ((uni[t]["t_in"] >= s) & (uni[t]["t_in"] < hi)).any()
                  else 0.0 for t in bot]
            decay[h].append(float(np.mean(vt) - np.mean(vb)))

    Dv = np.array(Dv); Uv = np.array(Uv); Lv = np.array(Lv)
    print(f"รอบที่ใช้ได้ {len(Dv)}  รอบที่ไม่มีช่องผ่านด่าน {nocell}")
    print(f"ไม้ที่ถูกตัดเพราะยังไม่ปิดก่อนเส้นแบ่ง (embargo): "
          f"รวม {sum(purges):,}  เฉลี่ยต่อรอบ {np.mean(purges):.0f}")
    print(f"ช่องที่ยุบเพราะให้ไม้เหมือนกันเป๊ะ: เฉลี่ยต่อรอบ {np.mean(dups):.0f}")
    if len(Dv) < 8:
        print("\nรอบน้อยเกินกว่าจะอนุมานอะไรได้ -> NOT ASSESSED")
        return 0

    # ------------------------------------------------ the MDE comes FIRST
    print("\n" + "=" * 100)
    print("พลังการตรวจจับ — อ่านก่อนดูผล (Amendment 16 ข้อ 15.2)")
    print("=" * 100)
    nblk = int(np.ceil(len(Dv) / BLOCK_ROLLS))
    se_blk = float(Dv.std(ddof=1) / np.sqrt(nblk))
    print(f"รอบ {len(Dv)}  ก้อนอิสระ {nblk}  sd ต่อรอบ {Dv.std(ddof=1):.4f} R")
    print(f"ความคลาดเคลื่อนระดับก้อน {se_blk:.4f} R")
    print(f"effect ที่ต้องมีเพื่อพลัง 80% (ทางเดียว) = {(1.645+0.84)*se_blk:.4f} R")
    print("ถ้าเลขนี้สูงกว่าค่าที่เป็นไปได้จริง ผลลบไม่ได้แปลว่าอันดับถ่ายทอดไม่ได้")
    print("มันแปลว่าข้อมูลเท่านี้ตอบคำถามนี้ไม่ได้ — สองอย่างนี้ต่างกัน")

    print("\n" + "=" * 100)
    print("สถิติหลัก: อันดับจาก 60 วันล่าสุด ทำนาย 10 วันถัดไปได้หรือไม่")
    print("=" * 100)
    obsD, pD, _ = block_flip_p(Dv, BLOCK_ROLLS, DRAWS, SEED)
    print(f"D = ผลของ Top5 − ผลของ Bottom5  ต่อรอบ")
    print(f"  ค่าเฉลี่ย {obsD:+.4f} R   ค่ากลาง {np.median(Dv):+.4f}   "
          f"รอบที่เป็นบวก {100*np.mean(Dv>0):.0f}%")
    print(f"  p ด้านเดียว (สลับก้อนละ {BLOCK_ROLLS} รอบ, {DRAWS:,} ครั้ง) = {pD:.4f}")
    print(f"  -> {'อันดับถ่ายทอดได้' if pD < 0.05 else 'ไม่มีหลักฐานว่าอันดับถ่ายทอดได้'}")

    print("\nสองหางแยกกัน เทียบกับช่องกลาง 5 ช่อง (ปรับร่วมกันแบบ max-statistic)")
    obsU, pU, nU = block_flip_p(Uv, BLOCK_ROLLS, DRAWS, SEED + 1, one_sided=False)
    obsL, pL, nL = block_flip_p(Lv, BLOCK_ROLLS, DRAWS, SEED + 2, one_sided=False)
    mx = np.maximum(np.abs(nU), np.abs(nL))
    pj_U = (np.sum(mx >= abs(obsU)) + 1.0) / (DRAWS + 1.0)
    pj_L = (np.sum(mx >= abs(obsL)) + 1.0) / (DRAWS + 1.0)
    print(f"  หางชนะ  U = Top5 − Mid5     {obsU:+.4f} R   p เดี่ยว {pU:.4f}   "
          f"p ร่วม {pj_U:.4f}")
    print(f"  หางแพ้  L = Bottom5 − Mid5  {obsL:+.4f} R   p เดี่ยว {pL:.4f}   "
          f"p ร่วม {pj_L:.4f}")

    print("\nจำนวนไม้ในหน้าต่างเลือก (ข้อ 9 — ถ้าหางกองที่ขั้นต่ำ = เราวัดความแปรปรวน)")
    print(f"  Top5 {np.mean(ntop):.1f}   Mid5 {np.mean(nmid):.1f}   "
          f"Bottom5 {np.mean(nbot):.1f}   ขั้นต่ำที่กำหนด {MIN_TRADES_SEL}")
    # The meaningful comparison is TAILS AGAINST THE MIDDLE, not tails against the
    # floor. The first version tested `mean(ntop) < MIN_TRADES_SEL * 1.5`, which
    # reported "not clustered" at 28 trades against a 15-trade floor while the
    # middle sat at 136 - a 4.8x gap that is exactly the variance-selection
    # signature correction 9 was written to catch. Fixed here; the earlier reading
    # of this line in data/walk_forward_run.txt was wrong and the commit says so.
    r_top = np.mean(nmid) / max(np.mean(ntop), 1e-9)
    r_bot = np.mean(nmid) / max(np.mean(nbot), 1e-9)
    print(f"  ค่ากลางมีไม้มากกว่าหางชนะ {r_top:.1f} เท่า และมากกว่าหางแพ้ "
          f"{r_bot:.1f} เท่า")
    if r_top >= 2.0 or r_bot >= 2.0:
        print("  -> หางถูกครองโดยช่องที่มีไม้น้อย = ความแปรปรวนสูง")
        print("     บันทึกตามข้อ 9 ว่าการทดลองนี้วัด 'การล่าความแปรปรวน'")
        print("     ไม่ใช่ 'การเลือก edge' ตัวคัดเลือกแบบ shrinkage จะดีกว่า")
        print("     และต้องมี amendment ของตัวเอง ห้ามเปลี่ยนย้อนหลัง")
    else:
        print("  -> หางมีไม้ใกล้เคียงค่ากลาง ไม่ใช่การล่าความแปรปรวน")

    # What sample WOULD answer the question, given the measured noise. This is the
    # most useful number the run produces.
    for target in (0.05, 0.10, 0.26):
        need_se = target / (1.645 + 0.84)
        need_blk = (Dv.std(ddof=1) / need_se) ** 2
        need_rolls = need_blk * BLOCK_ROLLS
        print(f"  เพื่อจับ effect {target:.2f} R ต้องมีก้อนอิสระ {need_blk:,.0f} "
              f"= ราว {need_rolls*STEP_DAYS/365:,.0f} ปี")

    print("\nเส้นโค้งการเสื่อม (ก้อนละ 6 รอบเหมือนกัน ตามข้อ 10)")
    print("  ระยะ (วัน) " + "".join(f"{h:>10d}" for h in DECAY_DAYS))
    print("  D เฉลี่ย   " + "".join(
        f"{np.mean(decay[h]):+10.4f}" for h in DECAY_DAYS))
    ps = []
    for h in DECAY_DAYS:
        _, ph, _ = block_flip_p(np.array(decay[h]), BLOCK_ROLLS, 1000, SEED + h)
        ps.append(ph)
    print("  p          " + "".join(f"{p:10.4f}" for p in ps))

    print("\n" + "=" * 100)
    print("NOT ASSESSED: การเลือก setup ที่เกิดน้อยแบบ W1 ระบุไม่ได้จากหน้าต่าง 60 วัน")
    print("(W1 เกิดราว 4 ครั้งต่อ 60 วัน ไม่เคยผ่านด่าน 15 ไม้) — Amendment 16 ข้อ 11")
    print("ค่าสัมบูรณ์ 'มี edge จริงไหม' ต้องใช้คู่เทียบ ซึ่งไม่ได้สร้างในรอบนี้")
    print("-> NOT ASSESSED ตาม Amendment 16 ข้อ 15.1")
    print("\nสถานะคงเดิม: NO TRADE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
