"""The geometry-neutral path diagnostic, implementing Amendment 13.

Every search in this project fixed the stop at 1.5 ATR and the target at 1:1. A
setup with real directional information at the WRONG barrier distance leaves
exactly the same pass/fail record as a setup with no information at all - both
look like noise - and five closures rest on that record.

So instead of another barrier sweep, the path itself is measured, in ATR units,
with no barrier chosen:

    r(h)     signed progress at horizon h
    MFE(h)   how far it went the right way before h
    MAE(h)   how far it went the wrong way before h
    P(fav|X) whether a favourable move of X ATR arrives before an adverse one

Each against the same stratified direction-matched placebo, with the focal bar's
whole calendar day removed from the control pool, so the drift is inside the
control and cancels.

INFERENCE: one simultaneous permutation band across all horizons, because the
horizons are nested and eight separate tests would be eight readings of one
quantity. The statistic is the maximum |t| over the curve - a curve is
significant as a curve or not at all.

FIVE SUBJECTS, counted in advance, Bonferroni at 5. No subject may be added
after a result is seen, and this file may not name a new candidate or change any
geometry.
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
import matched_control as MC
import regime_v2
import tools_wide as TW
import w1_cost_test as W1
import wide_search as WS

HORIZONS = (3, 6, 12, 24, 48, 72, 144, 288)          # M5 bars, 15 min to 24 h
BARRIERS = (0.5, 1.0, 1.5, 2.0, 3.0)                 # in ATR, for P(favourable)
DRAWS = 2000
SEED = 20260922
N_SUBJECTS = 5
MIN_POOL = 30
WARMUP = 260
HOLDOUT_DAYS = 120


def path_matrix(b5: D.Bars, nxt: np.ndarray, atr: np.ndarray, entries,
                no_overlap: bool = True):
    """For each accepted entry, the whole path in ATR units.

    Returns r, mfe, mae as (n_entries, n_horizons), plus first-touch outcomes per
    barrier size, the bar index and the calendar day.

    `no_overlap` enforces one position at a time over the LONGEST horizon, which
    is right for a candidate: it cannot open a second trade while the first is
    still inside the window being measured.

    It must be FALSE for the placebo pool. Each placebo is a standalone control
    for one entry, so overlap between placebos is not a quantity that means
    anything - and applying the candidate's rule to the pool cut it from ~46,000
    eligible bars to 642, which left every stratum below the minimum pool size
    and produced "no control available" for every subject.
    """
    H = np.array(HORIZONS)
    hmax = int(H.max())
    R, MFE, MAE, FIRST, days, idx = [], [], [], [], [], []
    busy_until = -1
    for (i, d) in entries:
        k = int(nxt[i])
        a = atr[i]
        if k < 0 or not np.isfinite(a) or a <= 0:
            continue
        if k + hmax >= len(b5):
            continue
        if no_overlap:
            if i <= busy_until:
                continue
            busy_until = i + hmax // 3       # in M15 units
        entry = b5.o[k]
        fwd_h = b5.h[k:k + hmax + 1]
        fwd_l = b5.l[k:k + hmax + 1]
        fwd_c = b5.c[k:k + hmax + 1]
        up = (fwd_h - entry) / a
        dn = (entry - fwd_l) / a
        fav = up if d > 0 else dn            # favourable excursion in ATR
        adv = dn if d > 0 else up            # adverse excursion in ATR
        R.append([d * (fwd_c[h] - entry) / a for h in HORIZONS])
        MFE.append([float(np.max(fav[1:h + 1])) for h in HORIZONS])
        MAE.append([float(np.max(adv[1:h + 1])) for h in HORIZONS])
        # which barrier is touched first, per barrier size. A bar that spans both
        # is charged as ADVERSE, the same worst-case rule core.resolve uses, so a
        # favourable reading can never come from intrabar ambiguity.
        row = []
        for X in BARRIERS:
            hit = 0.0
            for j in range(1, hmax + 1):
                a_hit = adv[j] >= X
                f_hit = fav[j] >= X
                if a_hit:
                    hit = 0.0
                    break
                if f_hit:
                    hit = 1.0
                    break
            row.append(hit)
        FIRST.append(row)
        days.append(int(b5.t[k]) // 86400)
        idx.append(i)
    if not R:
        return None
    return dict(r=np.array(R), mfe=np.array(MFE), mae=np.array(MAE),
                first=np.array(FIRST), days=np.array(days, np.int64),
                idx=np.array(idx))


def control_curves(pm_pool: dict, key: np.ndarray, pool: dict, day: np.ndarray):
    """Leave-one-day-out stratum means of every path quantity, per stratum and
    per day, built from the pooled placebo paths."""
    out = {}
    for name in ("r", "mfe", "mae", "first"):
        M = pm_pool[name]
        out[name] = {}
        for s, members in pool.items():
            sel = np.nonzero(np.isin(pm_pool["idx"], members))[0]
            if len(sel) < MIN_POOL + 1:
                continue
            vals = M[sel]
            dd = day[pm_pool["idx"][sel]]
            tot = vals.sum(axis=0)
            cnt = float(len(sel))
            per_day = {}
            for u in np.unique(dd):
                m = dd == u
                rem_n = cnt - m.sum()
                if rem_n >= MIN_POOL:
                    per_day[int(u)] = (tot - vals[m].sum(axis=0)) / rem_n
            out[name][s] = per_day
    return out


def excess_curve(pm: dict, ctl: dict, key: np.ndarray, name: str):
    """Per-entry excess of a path quantity over its matched control."""
    M = pm[name]
    rows, dys = [], []
    for j, i in enumerate(pm["idx"]):
        s = int(key[i])
        d = int(pm["days"][j])
        tbl = ctl[name].get(s)
        if tbl is None:
            continue
        c = tbl.get(d)
        if c is None:
            continue
        rows.append(M[j] - c)
        dys.append(d)
    if len(rows) < 10:
        return None
    return np.array(rows), np.array(dys, np.int64)


def curve_t(E: np.ndarray, days: np.ndarray):
    """Day-clustered t at each column, with the G/(G-1) correction."""
    uniq = {d: j for j, d in enumerate(sorted(set(days.tolist())))}
    ix = np.array([uniq[int(d)] for d in days])
    nd = len(uniq)
    n = len(E)
    mu = E.mean(axis=0)
    ts = np.empty(E.shape[1])
    for c in range(E.shape[1]):
        sums = np.bincount(ix, weights=E[:, c] - mu[c], minlength=nd)
        g = int((np.bincount(ix, minlength=nd) > 0).sum())
        corr = g / (g - 1) if g > 1 else 1.0
        se = np.sqrt(corr * (sums ** 2).sum()) / n
        ts[c] = mu[c] / se if se > 0 else 0.0
    return mu, ts, ix, nd


def curve_permutation(E: np.ndarray, ix: np.ndarray, nd: int, draws=DRAWS,
                      seed=SEED):
    """One band for the whole curve: the null of max|t| across columns, built by
    flipping the sign of whole days, the same flip applied to every column."""
    rng = np.random.default_rng(seed)
    n = len(E)
    cnts = np.bincount(ix, minlength=nd).astype(float)
    g = int((cnts > 0).sum())
    corr = g / (g - 1) if g > 1 else 1.0
    S = np.zeros((nd, E.shape[1]))
    np.add.at(S, ix, E)
    nulls = np.empty(draws)
    for j in range(draws):
        f = rng.choice([-1.0, 1.0], size=nd)
        Sf = S * f[:, None]
        mu = Sf.sum(axis=0) / n
        resid = Sf - cnts[:, None] * mu[None, :]
        se = np.sqrt(corr * (resid ** 2).sum(axis=0)) / n
        with np.errstate(divide="ignore", invalid="ignore"):
            nulls[j] = np.nanmax(np.abs(np.where(se > 0, mu / se, 0.0)))
    return nulls


def report_subject(name: str, entries, pm_pool, ctl, key, b5, nxt, atr, zb):
    print("\n" + "=" * 104)
    print(f"{name}")
    print("=" * 104)
    pm = path_matrix(b5, nxt, atr, entries)
    if pm is None or len(pm["idx"]) < 20:
        got = 0 if pm is None else len(pm["idx"])
        print(f"  ไม้ที่วัดเส้นทางได้ {got} -> น้อยเกินไป NOT ASSESSED")
        return None
    print(f"  ไม้ {len(pm['idx'])}  วัน {len(set(pm['days'].tolist()))}")
    verdict = {}
    for q, label in (("r", "ความคืบหน้าสุทธิ r(h)"),
                     ("mfe", "ไปทางถูกไกลสุด MFE(h)"),
                     ("mae", "ไปทางผิดไกลสุด MAE(h)")):
        got = excess_curve(pm, ctl, key, q)
        if got is None:
            print(f"  {label}: จับคู่ไม่ได้")
            continue
        E, dys = got
        mu, ts, ix, nd = curve_t(E, dys)
        nulls = curve_permutation(E, ix, nd)
        obs = float(np.nanmax(np.abs(ts)))
        p = float((np.sum(nulls >= obs) + 1.0) / (len(nulls) + 1.0))
        crit = float(np.percentile(nulls, 95))
        verdict[q] = dict(mu=mu, t=ts, p=p, crit=crit, obs=obs)
        print(f"\n  {label}  (หน่วย ATR, ส่วนต่างจากคู่เทียบ)")
        print("    ระยะ (แท่ง M5) " + "".join(f"{h:>9d}" for h in HORIZONS))
        print("    ส่วนต่าง        " + "".join(f"{v:+9.4f}" for v in mu))
        print("    t               " + "".join(f"{v:+9.2f}" for v in ts))
        print(f"    max|t| {obs:.3f}  ค่าวิกฤตจากการสลับ {crit:.3f}  p = {p:.4f}"
              f"  Bonferroni ที่ N={N_SUBJECTS}: ต้อง p < {0.05/N_SUBJECTS:.4f}"
              f"  -> {'มีนัยสำคัญ' if p < 0.05/N_SUBJECTS else 'ไม่มีนัยสำคัญ'}")

    got = excess_curve(pm, ctl, key, "first")
    if got is not None:
        E, dys = got
        mu, ts, ix, nd = curve_t(E, dys)
        print(f"\n  โอกาสที่ราคาไปถึงฝั่งกำไรก่อนฝั่งขาดทุน (ส่วนต่างจากคู่เทียบ)")
        print("    ขนาดกรอบ (ATR) " + "".join(f"{x:>9.1f}" for x in BARRIERS))
        print("    ส่วนต่าง        " + "".join(f"{v:+9.4f}" for v in mu))
        print("    t               " + "".join(f"{v:+9.2f}" for v in ts))
        verdict["first"] = dict(mu=mu, t=ts)
        own = pm["first"].mean(axis=0)
        print("    ของตัวเองดิบ    " + "".join(f"{v:9.3f}" for v in own))
    return verdict


def main() -> int:
    b5 = D.load_csv("data/XAUUSD_M5.csv")
    b15, _ = D.to_15m(b5)
    n = len(b15)
    want = b15.t + 900
    pos = np.searchsorted(b5.t, want)
    nxt = np.where((pos < len(b5)) & (b5.t[np.minimum(pos, len(b5) - 1)] == want),
                   pos, -1)
    atr = core.atr(b15, 14)
    prof = adaptive.hourly_spread_profile(b5)
    cut = int(b15.t[-1]) - HOLDOUT_DAYS * 86400
    i_hi = int(np.searchsorted(b15.t, cut))

    print("=" * 104)
    print("PATH DIAGNOSTIC (Amendment 13) — วัดเส้นทางราคา ไม่ผูกกับ stop/target ใด")
    print("=" * 104)
    print(f"ระยะที่วัด (แท่ง M5): {HORIZONS}  = 15 นาที ถึง 24 ชั่วโมง")
    print(f"ขนาดกรอบที่ทดสอบ (ATR): {BARRIERS}")
    print(f"ทดสอบ {N_SUBJECTS} เรื่อง นับไว้ก่อนรัน  Bonferroni ต้อง p < "
          f"{0.05/N_SUBJECTS:.4f}")
    print("ทุกอย่างวัดเป็นหน่วย ATR จึงไม่ขึ้นกับการเลือก stop")
    print("แท่งที่แตะทั้งสองฝั่งถูกนับเป็นฝั่งขาดทุน ตามกฎเดิม\n")

    st = MC.build_strata(b15, atr, prof, None, WARMUP, i_hi)
    print(f"ชั้นที่จับคู่ได้ {len(st.pool)}")

    # the placebo pool: every eligible bar, both directions, so a control exists
    # for each subject's own side
    print("คำนวณเส้นทางของคู่เทียบทุกแท่ง (ทำครั้งเดียว)...")
    day_of_bar = np.zeros(n, np.int64)
    ok_bar = nxt >= 0
    day_of_bar[ok_bar] = b5.t[nxt[ok_bar]].astype(np.int64) // 86400
    pool_idx = (np.concatenate([m for m in st.pool.values()]) if st.pool
                else np.array([], np.int64))
    pool_sorted = sorted(set(int(x) for x in pool_idx.tolist()))
    ctl_by_dir = {}
    for d in (1, -1):
        ents = [(i, d) for i in pool_sorted]
        pmp = path_matrix(b5, nxt, atr, ents, no_overlap=False)
        if pmp is None:
            continue
        ctl_by_dir[d] = (pmp, control_curves(pmp, st.key, st.pool, day_of_bar))
        print(f"  คู่เทียบฝั่ง {'Long ' if d > 0 else 'Short'} "
              f"{len(pmp['idx']):,} แท่ง")

    zb = core.bonferroni_z(N_SUBJECTS)
    tools = TW.build(b15)
    cand, _ = WS.candidates(tools, n)

    subjects = []
    subjects.append(("1/5  W1 gap_continuation/short (ตัวที่ยังมีชีวิต)",
                     W1.w1_signals(b15, atr, WARMUP, i_hi), -1))
    subjects.append(("2/5  W2a rsi:40/short (watchlist)",
                     [(i, d) for (i, d) in cand.get("rsi:40/short", [])
                      if WARMUP <= i < i_hi], -1))
    subjects.append(("3/5  W2b emax:50-200/long (watchlist)",
                     [(i, d) for (i, d) in cand.get("emax:50-200/long", [])
                      if WARMUP <= i < i_hi], 1))

    news_ep = None
    try:
        import calendar_feed
        cal = calendar_feed.load_calendar("data/calendar.csv")
        rws = calendar_feed.build_events(cal, "USD", ("HIGH",))
        news_ep = np.array(sorted(r.epoch for r in rws if r.usable), np.int64)
    except Exception:
        pass
    reg = regime_v2.build_regime_v2(b15, news_ep)
    allow = reg["regime"].to_numpy() == "ORDERLY_TREND"
    ot = adaptive.tool_signals("pullback", b15, reg, allow)
    subjects.append(("4/5  ORDERLY_TREND v2 pullback (ตระกูลที่ปิดแล้วที่แข็งที่สุด)",
                     [(i, d) for (i, d, *_rest) in ot if WARMUP <= i < i_hi], None))

    pooled = []
    for tag, ents in cand.items():
        pooled.extend([(i, d) for (i, d) in ents if WARMUP <= i < i_hi])
    # one entry per bar-direction, so the pool is not weighted by how many tools
    # happened to fire on the same bar
    pooled = sorted(set(pooled))
    subjects.append((f"5/5  ชั้น A รวมทุกตัว ({len(pooled):,} จุดเข้าที่ไม่ซ้ำ)",
                     pooled, None))

    results = {}
    for (name, ents, fixed_d) in subjects:
        if not ents:
            print(f"\n{name}\n  ไม่มีสัญญาณ -> NOT ASSESSED")
            continue
        d0 = fixed_d if fixed_d is not None else ents[0][1]
        pmp, ctl = ctl_by_dir.get(d0, (None, None))
        if ctl is None:
            # mixed-direction subject: score each side against its own control
            mixed = {}
            for d in (1, -1):
                sub = [(i, dd) for (i, dd) in ents if dd == d]
                if len(sub) < 20 or d not in ctl_by_dir:
                    continue
                mixed[d] = report_subject(f"{name}  [ฝั่ง {'Long' if d>0 else 'Short'}]",
                                          sub, ctl_by_dir[d][0], ctl_by_dir[d][1],
                                          st.key, b5, nxt, atr, zb)
            results[name] = mixed
            continue
        results[name] = report_subject(name, ents, pmp, ctl, st.key, b5, nxt,
                                       atr, zb)

    print("\n" + "=" * 104)
    print("อ่านผลตามตารางที่ประกาศไว้ใน Amendment 13 ข้อ 6")
    print("=" * 104)
    alpha = 0.05 / N_SUBJECTS
    any_sig = False
    for name, v in results.items():
        if not v:
            continue
        flat = []
        for q in ("r", "mfe", "mae"):
            d = v.get(q) if isinstance(v, dict) and q in v else None
            if d:
                flat.append((q, d["p"], d["obs"]))
        if not flat:
            continue
        sig = [q for (q, p, o) in flat if p < alpha]
        if sig:
            any_sig = True
        print(f"\n{name}")
        for (q, p, o) in flat:
            lbl = dict(r="ความคืบหน้าสุทธิ", mfe="ไปทางถูก", mae="ไปทางผิด")[q]
            print(f"   {lbl:16s} max|t| {o:5.2f}  p {p:.4f}  "
                  f"{'<- มีนัยสำคัญ' if p < alpha else ''}")
    if not any_sig:
        print("\nไม่มีเรื่องใดที่เส้นทางราคาต่างจากคู่เทียบอย่างมีนัยสำคัญ")
        print("ตามตารางข้อ 6 อ่านว่า: ไม่มีโครงสร้างในเส้นทางที่จะใช้ประโยชน์ได้")
        print("-> คำปิดทั้งห้าเรื่องแข็งขึ้น และเรขาคณิตของกรอบ (stop/target)")
        print("   ถูกตัดออกจากรายการคำอธิบายที่เป็นไปได้")
        print("-> RR และระยะ stop ปิดเป็น 'ช่องว่างที่ตรวจแล้ว' ไม่ใช่ 'ยังไม่ตรวจ'")
    else:
        print("\nมีเรื่องที่เส้นทางต่างจากคู่เทียบ -> ต้องอ่านตามตารางข้อ 6")
        print("ว่าเป็นแบบ 'stop แคบเกินไป' หรือ 'สัญญาณสั้น' หรือ 'ต้องมี trailing'")
        print("และตาม Amendment 13 ข้อ 7 ห้ามแก้เรขาคณิตในไฟล์นี้")
        print("ต้องเปิด amendment ใหม่ที่มีช่วงข้อมูลที่ยังไม่ถูกแตะของตัวเอง")

    print("\nไฟล์นี้ไม่ตั้งชื่อ candidate ใหม่ ไม่แก้เรขาคณิต ไม่อ่าน holdout")
    print("สถานะคงเดิม: NO TRADE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
