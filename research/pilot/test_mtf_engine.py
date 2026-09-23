"""Verification suite for mtf_engine, required by Amendment 14 section 6.

The operator's condition was that the work be checked for errors BEFORE it is
handed over to be run. Eight checks, each on data whose correct answer is known by
construction rather than by comparison with another run of the same code.

Check 1 is the one that matters most: a deliberately mutated engine that peeks one
bar into the future must be CAUGHT. A test suite that only confirms the code agrees
with itself proves nothing.

Run:  python research/pilot/test_mtf_engine.py
Exit code 0 means every check passed and the search may be handed over.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import core
import data as D
import matched_control as MC
import mtf_engine as E
import wide_engine as WE

FAILS: list[str] = []
PASSES: list[str] = []


def ok(name: str, cond: bool, detail: str = ""):
    (PASSES if cond else FAILS).append(f"{name}  {detail}".rstrip())
    print(f"  {'ผ่าน  ' if cond else 'ไม่ผ่าน'} {name}"
          + (f"   {detail}" if detail else ""))


def synth_bars(n: int, step: int = 300, t0: int = 1_700_000_000,
               seed: int = 7) -> D.Bars:
    """A synthetic M5 series on an exact grid, with a known shape."""
    rng = np.random.default_rng(seed)
    t0 -= t0 % (48 * step)                 # align so every H4 block is whole
    t = t0 + np.arange(n, dtype=np.int64) * step
    c = 100.0 + np.cumsum(rng.normal(0, 0.1, n))
    o = np.concatenate(([100.0], c[:-1]))
    h = np.maximum(o, c) + np.abs(rng.normal(0, 0.05, n))
    l = np.minimum(o, c) - np.abs(rng.normal(0, 0.05, n))
    v = rng.integers(1, 100, n).astype(float)
    sp = np.full(n, 0.03)
    return D.Bars(t, o, h, l, c, v, step, "SYNTH", sp)


# ---------------------------------------------------------------- 1. look-ahead
def test_no_lookahead():
    print("\n[1] ไม่มีการมองอนาคต (look-ahead)")
    b5 = synth_bars(4000)
    bs, nxt = E.resample(b5, 3)

    # the honest property: the execution bar must START at or after the signal
    # bar's CLOSE. Not one second before.
    span = bs.step
    bad = 0
    for i in range(len(bs)):
        k = int(nxt[i])
        if k < 0:
            continue
        if int(b5.t[k]) < int(bs.t[i]) + span:
            bad += 1
    ok("1a execution bar starts at or after the signal bar closes",
       bad == 0, f"ละเมิด {bad} จาก {len(bs)} แท่ง")

    # the mutation: point the execution index one M5 bar EARLIER, which is a
    # 5-minute peek. It must change a measurable outcome, otherwise the test is
    # not sensitive enough to catch the real bug it is guarding against.
    mutated = np.where(nxt > 0, nxt - 1, nxt)
    atr_s = core.atr(bs, E.ATR_N)
    sig = [(i, 1) for i in range(250, len(bs) - 5, 7)]
    good = E.run_cell(bs, nxt, atr_s, sig, b5, 1.5, 1.0, (0.0, 0), 3)
    peek = E.run_cell(bs, mutated, atr_s, sig, b5, 1.5, 1.0, (0.0, 0), 3)
    g1 = np.mean([r["g"] for r in good["rows"]]) if good["rows"] else np.nan
    g2 = np.mean([r["g"] for r in peek["rows"]]) if peek["rows"] else np.nan
    ok("1b a one-bar peek changes the result, so the test is sensitive",
       np.isfinite(g1) and np.isfinite(g2) and abs(g1 - g2) > 1e-9,
       f"ปกติ {g1:+.5f} vs มองอนาคต {g2:+.5f}")

    # and the peeking index must itself violate 1a, i.e. the check above would
    # have caught the mutation
    bad_m = sum(1 for i in range(len(bs))
                if int(mutated[i]) > 0
                and int(b5.t[int(mutated[i])]) < int(bs.t[i]) + span)
    ok("1c the look-ahead check CATCHES the mutated engine",
       bad_m > 0, f"ตรวจพบการละเมิด {bad_m} จุดในเวอร์ชันที่ถูกดัดแปลง")


# ---------------------------------------------------------------- 2. resampling
def test_resample():
    print("\n[2] การรวมแท่งข้ามไทม์เฟรมถูกต้อง")
    n = 48 * 60
    b5 = synth_bars(n)
    for (name, mult) in E.TIMEFRAMES:
        bs, nxt = E.resample(b5, mult)
        if mult == 1:
            ok(f"2.{name} ส่งคืนชุดเดิม", len(bs) == len(b5))
            continue
        # brute-force the first 20 output bars from the M5 source
        errs = 0
        for j in range(min(20, len(bs))):
            t0 = int(bs.t[j])
            m = (b5.t >= t0) & (b5.t < t0 + mult * 300)
            if m.sum() != mult:
                errs += 1
                continue
            if (abs(bs.o[j] - b5.o[m][0]) > 1e-12
                    or abs(bs.c[j] - b5.c[m][-1]) > 1e-12
                    or abs(bs.h[j] - b5.h[m].max()) > 1e-12
                    or abs(bs.l[j] - b5.l[m].min()) > 1e-12
                    or abs(bs.v[j] - b5.v[m].sum()) > 1e-9):
                errs += 1
        aligned = all(int(x) % (mult * 300) == 0 for x in bs.t)
        ok(f"2.{name} open/high/low/close/volume และขอบแท่งถูกต้อง",
           errs == 0 and aligned,
           f"แท่ง {len(bs):,}  ผิด {errs}  ขอบตรง {aligned}")

    # a gap must not be bridged: delete one M5 bar and the block containing it
    # must disappear rather than be built from two bars
    b5b = synth_bars(600)
    keep = np.ones(len(b5b), bool)
    keep[10] = False                      # kill a bar inside the 4th M15 block
    b5c = D.Bars(b5b.t[keep], b5b.o[keep], b5b.h[keep], b5b.l[keep],
                 b5b.c[keep], b5b.v[keep], 300, "SYNTH", b5b.sp[keep])
    bs_full, _ = E.resample(b5b, 3)
    bs_gap, _ = E.resample(b5c, 3)
    ok("2.gap แท่งที่ข้อมูลไม่ครบถูกทิ้ง ไม่ถูกสร้างขึ้นจากแท่งที่เหลือ",
       len(bs_gap) == len(bs_full) - 1,
       f"เต็ม {len(bs_full)} -> มีรูโหว่ {len(bs_gap)}")


# ------------------------------------------------------- 3. limit fill / expiry
def test_limit_expiry():
    print("\n[3] คำสั่ง limit และอายุของจุดเข้า")
    t = 1_700_000_000 + np.arange(10, dtype=np.int64) * 300
    # a long limit at 100. Price stays above it until bar 4, touches on bar 4.
    lo = np.array([101, 101, 101, 101, 99.5, 101, 101, 101, 101, 101.0])
    hi = lo + 1.0
    o = lo + 0.5
    c = lo + 0.5
    b = D.Bars(t, o, hi, lo, c, np.ones(10), 300, "S", np.full(10, 0.03))

    ok("3a limit ที่ราคาแตะ -> ได้ราคา limit",
       E.entry_fill(b, 0, 1, 100.0, 6) == (4, 100.0),
       f"ได้ {E.entry_fill(b, 0, 1, 100.0, 6)}")
    ok("3b หน้าต่างสั้นกว่าที่ราคาจะแตะ -> ไม่มีการเข้าไม้",
       E.entry_fill(b, 0, 1, 100.0, 4) is None)
    ok("3c แตะที่แท่งสุดท้ายของหน้าต่างพอดี -> ยังนับ",
       E.entry_fill(b, 0, 1, 100.0, 5) == (4, 100.0))
    ok("3d ราคาที่ไม่เคยแตะเลย -> ไม่มีการเข้าไม้",
       E.entry_fill(b, 0, 1, 50.0, 10) is None)
    # a gap through the limit must fill at the open, not at the limit
    o2 = o.copy(); o2[0] = 99.0
    lo2 = lo.copy(); lo2[0] = 98.5
    b2 = D.Bars(t, o2, hi, lo2, c, np.ones(10), 300, "S", np.full(10, 0.03))
    ok("3e ถ้าเปิดทะลุ limit ไปแล้ว -> ได้ราคาเปิด ไม่ใช่ราคา limit",
       E.entry_fill(b2, 0, 1, 100.0, 6) == (0, 99.09),
       f"ได้ {E.entry_fill(b2, 0, 1, 100.0, 6)}")
    # short side mirrors
    ok("3f ฝั่ง short ทำงานกลับด้านถูกต้อง",
       E.entry_fill(b, 0, -1, 101.5, 6) == (0, 101.5),
       f"ได้ {E.entry_fill(b, 0, -1, 101.5, 6)}")

    # A pending order may survive a session break. A later gap through the
    # limit receives the later open, not the stale limit price.
    o3 = o.copy(); o3[4] = 99.0
    lo3 = lo.copy(); lo3[4] = 98.5
    b3 = D.Bars(t, o3, hi, lo3, c, np.ones(10), 300, "S", np.full(10, 0.03))
    ok("3g gap ผ่าน limit ในแท่งถัดไป -> ใช้ราคาเปิดของแท่งนั้น",
       E.entry_fill(b3, 0, 1, 100.0, 6) == (4, 99.09),
       f"ได้ {E.entry_fill(b3, 0, 1, 100.0, 6)}")

    # expiry must reduce the trade count and raise the expiry rate monotonically
    b5 = synth_bars(6000)
    bs, nxt = E.resample(b5, 3)
    atr_s = core.atr(bs, E.ATR_N)
    sig = [(i, 1) for i in range(250, len(bs) - 20, 5)]
    counts, rates = [], []
    for ex in (5, 8, 10, 12, 15):
        res = E.run_cell(bs, nxt, atr_s, sig, b5, 1.5, 1.0, (0.50, ex), 3)
        counts.append(len(res["rows"]))
        rates.append(res["expiry_rate"])
    ok("3h อายุยาวขึ้น -> สัดส่วนที่หมดอายุลดลงแบบไม่สลับทาง",
       all(rates[i] >= rates[i + 1] - 1e-12 for i in range(len(rates) - 1)),
       "สัดส่วนหมดอายุ " + " ".join(f"{100*x:.0f}%" for x in rates))
    mk = E.run_cell(bs, nxt, atr_s, sig, b5, 1.5, 1.0, (0.0, 0), 3)
    ok("3i การเข้าแบบตลาดไม่มีการหมดอายุเลย",
       mk["n_expired"] == 0 and len(mk["rows"]) >= max(counts),
       f"ไม้แบบตลาด {len(mk['rows'])} vs แบบ limit สูงสุด {max(counts)}")


# -------------------------------------------------------- 4. worst-case intrabar
def test_worst_case():
    print("\n[4] แท่งที่แตะทั้งสองฝั่งต้องนับเป็นการขาดทุน")
    t = 1_700_000_000 + np.arange(5, dtype=np.int64) * 300
    # entry 100, stop 99, target 101; bar 1 spans 98.5 to 101.5 - both are inside
    o = np.array([100.0, 100.0, 100, 100, 100])
    hi = np.array([100.2, 101.5, 100, 100, 100])
    lo = np.array([99.8, 98.5, 100, 100, 100])
    c = np.array([100.0, 100.0, 100, 100, 100])
    b = D.Bars(t, o, hi, lo, c, np.ones(5), 300, "S", np.full(5, 0.03))
    px_l, why_l, _ = core.resolve(b, 0, 1, 100.0, 99.0, 101.0, 5)
    px_s, why_s, _ = core.resolve(b, 0, -1, 100.0, 101.0, 99.0, 5)
    ok("4a ฝั่ง long ได้ผลเป็น stop", why_l == "stop", f"ได้ {why_l} ที่ {px_l}")
    ok("4b ฝั่ง short ก็ได้ผลเป็น stop ด้วย (ทั้งสองฝั่งแพ้)",
       why_s == "stop", f"ได้ {why_s} ที่ {px_s}")
    ok("4c จึงกลับด้านแล้วไม่ได้กำไรจากความกำกวม",
       why_l == "stop" and why_s == "stop")

    # The high can precede a long limit fill at 100. With OHLC alone its order
    # is unknowable, so an intrabar fill must not inherit that high as a TP.
    hi2 = np.array([101.5, 100.2, 100.2, 100.2, 100.2])
    lo2 = np.array([99.5, 99.8, 99.8, 99.8, 99.8])
    b2 = D.Bars(t, o, hi2, lo2, c, np.ones(5), 300, "S", np.full(5, 0.03))
    normal = E.resolve_plane(b2, 0, 1, 100.0, 1.0, (1.0,), (1.0,), 5)
    conservative = E.resolve_plane(
        b2, 0, 1, 100.0, 1.0, (1.0,), (1.0,), 5,
        allow_entry_bar_target=False)
    ok("4d limit ที่เข้าในแท่ง ห้ามใช้ high ก่อนเข้าเป็น TP",
       normal[(1.0, 1.0)][1] == "target"
       and conservative[(1.0, 1.0)][1] != "target")


# ---------------------------------------------------------------- 5. costs
def test_costs():
    print("\n[5] ต้นทุนถูกคิดต่อไม้และเพิ่มตามตัวคูณ")
    b5 = synth_bars(6000)
    bs, nxt = E.resample(b5, 3)
    atr_s = core.atr(bs, E.ATR_N)
    sig = [(i, 1) for i in range(250, len(bs) - 20, 5)]
    nets = []
    for m in (1.0, 1.5, 3.0, 7.0):
        res = E.run_cell(bs, nxt, atr_s, sig, b5, 1.5, 1.0, (0.0, 0), 3, cost_mult=m)
        nets.append(np.mean([r["net"] for r in res["rows"]]))
    ok("5a net ลดลงเมื่อต้นทุนเพิ่ม (ไม่สลับทาง)",
       all(nets[i] > nets[i + 1] for i in range(len(nets) - 1)),
       " ".join(f"{x:+.4f}" for x in nets))

    r1 = E.run_cell(bs, nxt, atr_s, sig, b5, 1.5, 1.0, (0.0, 0), 3, cost_mult=1.0)
    row = r1["rows"][0]
    expect = E.COMMISSION_RT + 2 * E.SLIP_PER_FILL
    # Spread is embedded in the Ask path; this difference is explicit fees.
    charged = row["g"] - row["net"]
    ok("5b หักคอมมิชชั่นและ slippage โดย spread อยู่ใน Ask แล้ว",
       charged >= expect / row["risk"] - 1e-12,
       f"หักไป {charged:.5f} R, ขั้นต่ำที่ควรหัก {expect/row['risk']:.5f} R")

    # a short pays no financing on this instrument; a long does
    sigS = [(i, -1) for i in range(250, len(bs) - 20, 5)]
    rs = E.run_cell(bs, nxt, atr_s, sigS, b5, 1.5, 1.0, (0.0, 0), 3)
    ok("5c ฝั่ง short ไม่เสียค่าถือข้ามคืน (วัดได้ว่าเป็นศูนย์)",
       E.SWAP_SHORT == 0.0 and len(rs["rows"]) > 0)


# ------------------------------------------------- 6. leave-one-day-out control
def test_loo_control():
    print("\n[6] คู่เทียบตัดวันของไม้นั้นออกจริง")
    b5 = synth_bars(20000)
    bs, nxt = E.resample(b5, 3)
    atr_s = core.atr(bs, E.ATR_N)
    pre = WE.precompute(b5, bs, nxt, atr_s, 1.5, 1.0, 288,
                        E.SPREAD_FALLBACK, E.COMMISSION_RT, E.SLIP_PER_FILL,
                        0.0, 0.0)
    st = MC.build_strata(bs, atr_s, None, None, 250, len(bs) - 5)
    if not st.pool:
        ok("6 สร้างชั้นไม่ได้บนข้อมูลสังเคราะห์", False, "ข้ามการตรวจ")
        return
    WE.attach_control(pre, st.key, st.pool, min_pool=5)
    s = next(iter(st.pool))
    members = st.pool[s]
    g = pre.G[1][members]
    fin = np.isfinite(g)
    mem, vals = members[fin], g[fin]
    day = pre.day[mem]
    d0 = int(day[0])
    manual = float(vals[day != d0].mean())
    got = float(pre.ctl[1][mem[0]])
    ok("6a ค่ากลางของคู่เทียบ = ค่ากลางของชั้นที่ตัดวันนั้นออก",
       abs(manual - got) < 1e-9, f"คำนวณมือ {manual:+.6f} vs โค้ด {got:+.6f}")
    full = float(vals.mean())
    ok("6b และต่างจากค่ากลางที่ไม่ตัดวัน (ไม่ใช่การตัดหลอก ๆ)",
       abs(full - got) > 1e-12, f"ไม่ตัดวัน {full:+.6f} vs ตัดวัน {got:+.6f}")


# --------------------------------------------- 7. permutation reduction is exact
def test_permutation_exact():
    print("\n[7] การลดรูปของ permutation เท่ากับการคำนวณตรงเป๊ะ")
    rng = np.random.default_rng(11)
    n, nd = 400, 60
    e = rng.normal(0, 1, n)
    ix = rng.integers(0, nd, n)
    flip = rng.choice([-1.0, 1.0], size=nd)

    # direct, per trade
    e2 = e * flip[ix]
    mu_d = e2.mean()
    sums = np.bincount(ix, weights=e2 - mu_d, minlength=nd)
    cnts = np.bincount(ix, minlength=nd)
    g = int((cnts > 0).sum())
    corr = g / (g - 1)
    se_d = np.sqrt(corr * (sums ** 2).sum()) / n

    # reduced, per day sums only
    S = np.bincount(ix, weights=e, minlength=nd)
    N = cnts.astype(float)
    Sf = S * flip
    mu_r = Sf.sum() / n
    resid = Sf - N * mu_r
    se_r = np.sqrt(corr * (resid ** 2).sum()) / n

    ok("7a ค่าเฉลี่ยตรงกัน", abs(mu_d - mu_r) < 1e-12,
       f"{mu_d:+.12f} vs {mu_r:+.12f}")
    ok("7b ค่าความคลาดเคลื่อนตรงกัน", abs(se_d - se_r) < 1e-12,
       f"{se_d:.12f} vs {se_r:.12f}")
    ok("7c จึงย่อเป็นการคูณเมทริกซ์ได้โดยไม่เสียความถูกต้อง",
       abs(mu_d - mu_r) < 1e-12 and abs(se_d - se_r) < 1e-12)


# ---------------------------------------------------------------- 8. grid size
def test_grid():
    print("\n[8] ขนาดกริดตรงกับที่ประกาศไว้")
    built = list(E.cells())
    tags = {c["tag"] for c in built}
    ok("8a จำนวนช่องเท่ากับ 8,250 ตามที่ประกาศ (แก้จาก 4,500 ใน 6a)",
       len(built) == 8250, f"สร้างได้ {len(built):,}")
    ok("8b n_cells() ตรงกับจำนวนที่สร้างจริง", E.n_cells() == len(built),
       f"{E.n_cells():,} vs {len(built):,}")
    ok("8c ไม่มีชื่อช่องซ้ำกัน", len(tags) == len(built),
       f"ชื่อไม่ซ้ำ {len(tags):,}")
    ok("8d มีการเข้าแบบตลาดและแบบ limit ทั้ง 5 อายุ",
       sorted({c["expiry"] for c in built}) == [0, 5, 8, 10, 12, 15])
    ok("8e มีระยะ limit ทั้งสองค่าที่วัดแล้วว่าทำให้อายุมีผลจริง",
       sorted({c["offset"] for c in built}) == [0.0, 0.5, 1.0],
       f"ระยะที่มี {sorted({c['offset'] for c in built})}")


def test_rollover_clock():
    print("\n[10] rollover ใช้เวลาจริง ไม่ใช้จำนวนแท่ง")
    day = 2_000_000_000 - (2_000_000_000 % 86400)
    before = day + 20 * 3600 + 55 * 60
    after = day + 21 * 3600 + 5 * 60
    monday = day + 3 * 86400 + 22 * 3600
    ok("10a เข้าก่อน 21:00 แล้วถือผ่าน 21:00 นับหนึ่งคืน",
       E.rollover_nights(before, day + 21 * 3600 + 5 * 60) == 1)
    ok("10b เข้าหลัง 21:00 ไม่นับ rollover ที่ผ่านไปแล้ว",
       E.rollover_nights(after, day + 22 * 3600) == 0)
    ok("10c ช่วงข้าม weekend นับจาก timestamp จริง",
       E.rollover_nights(before, monday) == 4)


def main() -> int:
    print("=" * 92)
    print("ตรวจสอบเครื่องยนต์ก่อนส่งมอบ (Amendment 14 ข้อ 6)")
    print("=" * 92)
    for fn in (test_no_lookahead, test_resample, test_limit_expiry,
               test_worst_case, test_costs, test_loo_control,
               test_permutation_exact, test_grid, test_fast_resolver,
               test_rollover_clock):
        try:
            fn()
        except Exception as exc:  # a crash is a failure, not a skip
            FAILS.append(f"{fn.__name__} ล้มด้วยข้อผิดพลาด: {exc}")
            print(f"  ไม่ผ่าน {fn.__name__} ล้มด้วยข้อผิดพลาด: {exc}")

    print("\n" + "=" * 92)
    print(f"ผ่าน {len(PASSES)}   ไม่ผ่าน {len(FAILS)}")
    if FAILS:
        print("\nรายการที่ไม่ผ่าน:")
        for f in FAILS:
            print(f"  - {f}")
        print("\nAmendment 14 ข้อ 6: ถ้ามีข้อใดไม่ผ่าน ห้ามรันการค้นหา")
        print("ให้รายงานความล้มเหลวแทน")
        return 1
    print("\nผ่านทั้งหมด -> ส่งมอบให้ Codex รันได้")
    return 0




# ------------------------------------------- 9. the fast resolver equals core
def test_fast_resolver():
    print("\n[9] ตัวคำนวณเร็วให้ผลตรงกับ core.resolve เป๊ะ")
    b5 = synth_bars(20000, seed=3)
    rng = np.random.default_rng(5)
    bad_g = bad_w = checked = 0
    worst = 0.0
    for _ in range(400):
        k = int(rng.integers(100, len(b5) - E.TIME_STOP_M5 - 2))
        d = int(rng.choice([1, -1]))
        entry = float(b5.o[k] + (E.spread_at(b5, k) if d > 0 else 0.0))
        a = float(abs(rng.normal(0.4, 0.15))) + 0.05
        plane = E.resolve_plane(b5, k, d, entry, a, E.STOPS, E.TARGETS,
                               E.TIME_STOP_M5)
        if d > 0:
            ref_bars = b5
        else:
            spreads = np.maximum(b5.sp, E.SPREAD_FALLBACK)
            ref_bars = D.Bars(b5.t, b5.o + spreads, b5.h + spreads,
                              b5.l + spreads, b5.c + spreads, b5.v,
                              b5.step, b5.symbol, b5.sp)
        for st in E.STOPS:
            risk = st * a
            for tg in E.TARGETS:
                px, why, nb = core.resolve(ref_bars, k, d, entry,
                                           entry - d * risk,
                                           entry + d * tg * risk,
                                           E.TIME_STOP_M5)
                g_ref = d * (px - entry) / risk
                g_fast, why_fast, _ = plane[(st, tg)]
                checked += 1
                if why != why_fast:
                    bad_w += 1
                if abs(g_ref - g_fast) > 1e-9:
                    bad_g += 1
                    worst = max(worst, abs(g_ref - g_fast))
    ok("9a เหตุผลการออกตรงกันทุกกรณี", bad_w == 0,
       f"ตรวจ {checked:,} กรณี  ต่าง {bad_w}")
    ok("9b ผลกำไรดิบตรงกันทุกกรณี", bad_g == 0,
       f"ตรวจ {checked:,} กรณี  ต่าง {bad_g}  ส่วนต่างสูงสุด {worst:.2e}")


if __name__ == "__main__":
    raise SystemExit(main())
