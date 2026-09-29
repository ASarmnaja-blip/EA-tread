"""Regime atlas (Part 1, descriptive) and prequential trace accuracy (Part 2).
See docs/REGIME_MAP_PREREG.md v2 (+ Amendment 1) and docs/REGIME_TRACE_DICTIONARY.md.
Read-only.  Usage:
  python research/pilot/regime_atlas.py --smoke    counts only on whatever is cached
  python research/pilot/regime_atlas.py            full run (requires complete cache)
Index convention: cuts[k] is the START of week k = (cuts[k], cuts[k]+7d]. At the
cut C = cuts[k] the just-completed week is p = k-1 (W_t) and the target is k."""
from __future__ import annotations

import math
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import rankdata

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "research" / "history"))
sys.path.insert(0, str(ROOT / "research" / "wpwb_weekly"))
sys.path.insert(0, str(HERE))
from build_all_tf import load_kind  # noqa: E402
import vol as V  # noqa: E402
from plan_b_daily import daily_from_h1  # noqa: E402

SMOKE = "--smoke" in sys.argv
WEEK = 7 * 86400
FIRST_CUT = int(np.datetime64("2003-05-09T22:15:00", "s").astype(np.int64))
PRIOR = 10.0
MIN_EV = 30
TRAIL = 260
BLOCK = 26
B_REPS = 2000
N_SYN = 40
RNG = np.random.default_rng(20260929)
OUT = ROOT / "data" / "regime_atlas.xlsx"
TARGETS = ("V-change", "V-on", "V-off", "D-counterweek", "D-state-change", "Next-sign")
CATEGORICAL = ("month", "week_of_month", "qend_flag", "lag_short")
STATE = {0: "LOW", 1: "MID", 2: "HIGH"}
ERAS = {"2003-2008": ("2003", "2009"), "2009-2014": ("2009", "2015"),
        "2015-2020": ("2015", "2021"), "2021-2026": ("2021", "2027")}


# ------------------------------------------------------------------ data
def load():
    h = load_kind("hour")
    t = h.index.astype("datetime64[s]").astype(np.int64).to_numpy()
    big = int((np.diff(t) > 8 * 86400).sum())
    end = int(t[-1]) + 3600
    cuts = np.arange(FIRST_CUT, end - WEEK + 1, WEEK, dtype=np.int64)
    c, hi, lo = (h[k].to_numpy(float) for k in ("c", "h", "l"))
    rv_raw, rng, ret, nbar = V.weekly_rv(t, c, hi, lo, cuts)
    rv = V.mask_invalid(rv_raw, nbar)
    ret = np.where(np.isfinite(rv), ret, np.nan)
    rng = np.where(np.isfinite(rv), rng, np.nan)
    return h, t, cuts, rv, rng, ret, nbar, big


# ------------------------------------------------------------------ causal states and targets
def causal_edges(sig):
    """q[k] = terciles of sigma over weeks p-52..p-1 (p = k-1), >= 40 valid."""
    n = len(sig)
    q = np.full((n, 2), np.nan)
    for k in range(54, n):
        w = sig[k - 53:k - 1]
        if np.isfinite(w).sum() >= 40:
            q[k] = np.nanquantile(w, [1 / 3, 2 / 3])
    return q


def band(x, q):
    if not (np.isfinite(x) and np.isfinite(q).all()):
        return np.nan
    return 2.0 if x >= q[1] else (0.0 if x < q[0] else 1.0)


def trend_z(lr, rv, end, L=13):
    """z of the L-week log return ending at week `end` (inclusive); NaN unless all valid."""
    s = end - L + 1
    if s < 0:
        return np.nan
    w, v = lr[s:end + 1], rv[s:end + 1]
    if not (np.isfinite(w).all() and np.isfinite(v).all()):
        return np.nan
    return w.sum() * 1e4 / math.sqrt(v.sum())


def tstate(z):
    if not np.isfinite(z):
        return np.nan
    return 2.0 if z >= 0.5 else (0.0 if z <= -0.5 else 1.0)


def targets(sig, rv, ret):
    n = len(sig)
    lr = np.log1p(ret / 1e4)
    q = causal_edges(sig)
    Y = {k: np.full(n, np.nan) for k in TARGETS}
    cur = np.full(n, np.nan)
    nxt = np.full(n, np.nan)
    for k in range(54, n):
        p = k - 1
        sc, sn = band(sig[p], q[k]), band(sig[k], q[k])
        cur[k], nxt[k] = sc, sn
        if np.isfinite(sc) and np.isfinite(sn):
            Y["V-change"][k] = float(sn != sc)
            if sc in (0.0, 1.0):
                Y["V-on"][k] = float(sn == 2.0)
            else:
                Y["V-off"][k] = float(sn != 2.0)
        w, v = lr[p - 3:p + 1], rv[p - 3:p + 1]
        if np.isfinite(w).all() and np.isfinite(v).all() and np.isfinite(ret[k]) and ret[k] != 0:
            r4 = w.sum() * 1e4
            if r4 != 0 and abs(r4) >= 0.5 * math.sqrt(v.sum()):
                Y["D-counterweek"][k] = float(np.sign(ret[k]) != np.sign(r4))
        a, b = tstate(trend_z(lr, rv, p)), tstate(trend_z(lr, rv, k))
        if np.isfinite(a) and np.isfinite(b):
            Y["D-state-change"][k] = float(a != b)
        if np.isfinite(ret[k]) and ret[k] != 0:
            Y["Next-sign"][k] = float(ret[k] > 0)
    return Y, cur, nxt, q


# ------------------------------------------------------------------ traces (dictionary v2)
def traces(h, t, cuts, rv, rng, ret, sig, nbar):
    n = len(cuts)
    lr = np.log1p(ret / 1e4)
    close_t = t + 3600
    c_h, hi_h, lo_h = (h[k].to_numpy(float) for k in ("c", "h", "l"))
    r1 = np.r_[np.nan, np.diff(np.log(c_h))]
    f = V.ewma_forecast(rv)
    day = daily_from_h1()
    dclose = day.c.to_numpy(float)
    dend = (day.index + pd.Timedelta(days=1, hours=22)).astype("datetime64[s]").astype(np.int64).to_numpy()
    g = pd.read_csv(ROOT / "data" / "external" / "GVZ_History.csv")
    g["d"] = pd.to_datetime(g.DATE, format="%m/%d/%Y")
    gs = g.set_index("d").GVZ.astype(float)
    gd = gs.index.astype("datetime64[s]").astype(np.int64).to_numpy(); gv = gs.to_numpy()
    names = ("sig_ratio", "sig4_26", "ewma_ratio", "range_exp", "accel", "gvz_lvl", "gvz_chg", "gvz_prem",
             "r4z", "r13z", "r26z", "dist_ma50", "dist_ma200", "dist_hi52", "dist_lo52", "streak", "up_share8",
             "month", "week_of_month", "qend_flag", "lag_short")
    T = {k: np.full(n, np.nan) for k in names}
    s = np.sign(ret)
    for k in range(54, n):
        cut = int(cuts[k]); p = k - 1
        d = pd.Timestamp(cut, unit="s")
        T["month"][k] = d.month
        T["week_of_month"][k] = (d.day - 1) // 7 + 1
        T["qend_flag"][k] = float(d.month in (3, 6, 9, 12) and d.day >= 22)
        if not np.isfinite(sig[p]):
            continue
        T["lag_short"][k] = float(nbar[p] < 100)
        w52 = sig[p - 52:p]
        if np.isfinite(w52).sum() >= 40:
            med52 = np.nanmedian(w52)
            T["sig_ratio"][k] = sig[p] / med52
            if np.isfinite(f[k]):
                T["ewma_ratio"][k] = math.sqrt(f[k]) / med52
        w4, w26 = sig[p - 3:p + 1], sig[p - 25:p + 1]
        if np.isfinite(w4).sum() >= 3 and np.isfinite(w26).sum() >= 20:
            T["sig4_26"][k] = np.nanmean(w4) / np.nanmean(w26)
        T["range_exp"][k] = rng[p] / sig[p]
        use = (close_t > cut - WEEK) & (close_t <= cut)
        late = use & (close_t > cut - 2 * 86400)
        v_all = np.nansum(r1[use] ** 2)
        if v_all > 0:
            T["accel"][k] = (np.nansum(r1[late] ** 2) / v_all) / 0.4
        thu = cut - 86400
        j = np.searchsorted(gd, thu, side="right") - 1
        if j > 260 and gd[j] > cut - 6 * 86400:
            T["gvz_lvl"][k] = gv[j] / np.median(gv[j - 260:j])
            j0 = np.searchsorted(gd, thu - 7 * 86400, side="right") - 1
            if j0 >= 0 and gd[j0] > thu - 13 * 86400:
                T["gvz_chg"][k] = gv[j] / gv[j0] - 1
            T["gvz_prem"][k] = (gv[j] / 100) ** 2 / 52 * 1e8 / rv[p]
        for L, nm in ((4, "r4z"), (13, "r13z"), (26, "r26z")):
            w = lr[p - L + 1:p + 1]
            if len(w) == L and np.isfinite(w).all():
                T[nm][k] = w.sum() / (np.mean(sig[p - L + 1:p + 1]) / 1e4 * math.sqrt(L))
        pos = np.searchsorted(close_t, cut, side="right") - 1
        c_now = c_h[pos]
        s13 = sig[p - 12:p + 1]
        if np.isfinite(s13).sum() >= 10:
            m13 = np.nanmean(s13) / 1e4
            dc = dclose[dend <= cut]
            for L, nm in ((50, "dist_ma50"), (200, "dist_ma200")):
                if len(dc) >= L:
                    T[nm][k] = math.log(c_now / dc[-L:].mean()) / m13
            lo_i = np.searchsorted(close_t, cut - 52 * WEEK, side="right")
            if pos - lo_i > 1000:
                T["dist_hi52"][k] = math.log(c_now / hi_h[lo_i:pos + 1].max()) / m13
                T["dist_lo52"][k] = math.log(c_now / lo_h[lo_i:pos + 1].min()) / m13
        st, sg = 0, s[p]
        for q_ in range(p, max(p - 40, -1), -1):
            if np.isfinite(s[q_]) and s[q_] == sg and sg != 0:
                st += 1
            else:
                break
        T["streak"][k] = st * sg if sg else 0.0
        w8 = s[p - 7:p + 1]
        if np.isfinite(w8).sum() >= 6:
            T["up_share8"][k] = np.nanmean(w8 > 0)
    return T


# ------------------------------------------------------------------ prequential model
def prequential(x, y, categorical, window=None):
    """Prediction for each week k from past risk-set weeks j < k (outcome of j known at cuts[j+1] <= cuts[k])."""
    n = len(x)
    ok = np.isfinite(x) & np.isfinite(y)
    pred = np.full(n, np.nan); base = np.full(n, np.nan)
    idx = np.flatnonzero(ok)
    for k in idx:
        lo = 0 if window is None else k - window
        past = idx[(idx < k) & (idx >= lo)]
        if len(past) == 0:
            continue
        ys = y[past]
        ev = ys.sum()
        if ev < MIN_EV or len(ys) - ev < MIN_EV:
            continue
        b = ys.mean()
        xs = x[past]
        if categorical:
            sel = xs == x[k]
        else:
            e = np.quantile(xs, [1 / 3, 2 / 3])
            bk = np.searchsorted(e, x[k], side="right")
            sel = np.searchsorted(e, xs, side="right") == bk
        pred[k] = (ys[sel].sum() + PRIOR * b) / (sel.sum() + PRIOR)
        base[k] = b
    return pred, base


def alarms(pred):
    a = np.zeros(len(pred), bool)
    hist = []
    for k in np.flatnonzero(np.isfinite(pred)):
        if len(hist) >= 50 and pred[k] > np.quantile(hist, 0.8):
            a[k] = True
        hist.append(pred[k])
    return a


def auc(p, y):
    y = y.astype(bool)
    npos, nneg = y.sum(), (~y).sum()
    if npos < 5 or nneg < 5:
        return np.nan
    r = rankdata(p)
    return float((r[y].sum() - npos * (npos + 1) / 2) / (npos * nneg))


def metrics(pred, base, y, alarm, sel, boot=True):
    m = sel & np.isfinite(pred) & np.isfinite(y)
    k = np.flatnonzero(m)
    if len(k) == 0:
        return None
    yy, pp, bb, aa = y[k], pred[k], base[k], alarm[k]
    ev, ne = int(yy.sum()), int(len(yy) - yy.sum())
    if ev < 20 or ne < 20:
        return dict(weeks=len(k), events=ev, printed=False)
    bm, bs = (pp - yy) ** 2, (bb - yy) ** 2
    skill = 1 - bm.sum() / bs.sum()
    tp = int((aa & (yy == 1)).sum()); fp = int((aa & (yy == 0)).sum())
    fn = int((~aa & (yy == 1)).sum()); tn = int((~aa & (yy == 0)).sum())
    br = yy.mean()
    prec = tp / (tp + fp) if tp + fp else np.nan
    out = dict(weeks=len(k), events=ev, printed=True, base_rate=br, brier_skill=skill, AUC=auc(pp, yy),
               alarms=tp + fp, alarm_prevalence=(tp + fp) / len(k), TP=tp, FP=fp, FN=fn, TN=tn,
               precision=prec, lift=prec / br if np.isfinite(prec) and br > 0 else np.nan,
               sensitivity=tp / (tp + fn) if tp + fn else np.nan, FPR=fp / (fp + tn) if fp + tn else np.nan,
               FDR=fp / (tp + fp) if tp + fp else np.nan)
    if boot:
        # moving blocks over the calendar positions of the scored weeks
        pos = k - k.min()
        span = pos.max() + 1
        nb = int(math.ceil(span / BLOCK))
        starts = RNG.integers(0, max(span - BLOCK, 1), (B_REPS, nb))
        order = np.argsort(pos)
        pos_sorted = pos[order]
        sk, lf = np.empty(B_REPS), np.empty(B_REPS)
        cbm = np.r_[0, np.cumsum(bm[order])]; cbs = np.r_[0, np.cumsum(bs[order])]
        cy = np.r_[0, np.cumsum(yy[order])]; cn = np.arange(len(yy) + 1)
        tp_ = np.r_[0, np.cumsum((aa & (yy == 1))[order])]; al_ = np.r_[0, np.cumsum(aa[order])]
        for r in range(B_REPS):
            a_ = np.searchsorted(pos_sorted, starts[r]); b_ = np.searchsorted(pos_sorted, starts[r] + BLOCK)
            sbm = (cbm[b_] - cbm[a_]).sum(); sbs = (cbs[b_] - cbs[a_]).sum()
            sy = (cy[b_] - cy[a_]).sum(); sn = (cn[b_] - cn[a_]).sum()
            stp = (tp_[b_] - tp_[a_]).sum(); sal = (al_[b_] - al_[a_]).sum()
            sk[r] = 1 - sbm / sbs if sbs > 0 else np.nan
            lf[r] = (stp / sal) / (sy / sn) if sal > 0 and sy > 0 else np.nan
        out.update(skill_lo=float(np.nanpercentile(sk, 2.5)), skill_hi=float(np.nanpercentile(sk, 97.5)),
                   lift_lo=float(np.nanpercentile(lf, 2.5)), lift_hi=float(np.nanpercentile(lf, 97.5)))
    return out


def rolling_skill(pred, base, y, years):
    rows = {}
    for y0 in range(2008, 2023):
        m = np.isfinite(pred) & np.isfinite(y) & (years >= y0) & (years < y0 + 5)
        if m.sum() and y[m].sum() >= 20 and (1 - y[m]).sum() >= 20:
            rows[f"{y0}-{y0 + 4}"] = 1 - ((pred[m] - y[m]) ** 2).sum() / ((base[m] - y[m]) ** 2).sum()
    return rows


# ------------------------------------------------------------------ Part 1 (descriptive)
def part1(cuts, sig, ret, rv):
    date = pd.to_datetime(cuts, unit="s")
    lr = np.log1p(ret / 1e4)
    q1, q2 = np.nanquantile(sig, [1 / 3, 2 / 3])
    lvl = np.where(~np.isfinite(sig), np.nan, np.where(sig < q1, 0, np.where(sig >= q2, 2, 1)))
    dist = []
    for L in range(3):
        s = sig[lvl == L]
        dist.append({"band": STATE[L], "weeks": len(s), **{f"p{int(q * 100)}": np.quantile(s, q)
                                                          for q in (0.05, 0.25, 0.5, 0.75, 0.95)}})
    sens = []
    for nb in (3, 4, 5):
        e = np.nanquantile(sig, np.linspace(0, 1, nb + 1)[1:-1])
        sens.append({"bands": nb, "edges_bp": ", ".join(f"{v:.0f}" for v in e)})
    # spells (gaps break spells; first and last spells are censored)
    spells = []
    k = 0
    n = len(lvl)
    while k < n:
        if not np.isfinite(lvl[k]):
            k += 1; continue
        j = k
        while j + 1 < n and lvl[j + 1] == lvl[k]:
            j += 1
        cens = (k == 0) or (j == n - 1) or not np.isfinite(lvl[k - 1]) or (j + 1 < n and not np.isfinite(lvl[j + 1]))
        spells.append((int(lvl[k]), j - k + 1, cens))
        k = j + 1
    sp = pd.DataFrame(spells, columns=["band", "len", "censored"])
    spell_tab = []
    for L in range(3):
        s = sp[(sp.band == L) & ~sp.censored].len
        spell_tab.append({"band": STATE[L], "completed spells": len(s), "censored": int(((sp.band == L) & sp.censored).sum()),
                          "median weeks": s.median(), "p25": s.quantile(.25), "p75": s.quantile(.75), "max": s.max()})
    # transitions with block-bootstrap intervals
    a, b = lvl[:-1], lvl[1:]
    ok = np.isfinite(a) & np.isfinite(b)
    idx = np.flatnonzero(ok)
    M = np.zeros((3, 3))
    for i in idx:
        M[int(a[i]), int(b[i])] += 1
    P = M / M.sum(1, keepdims=True)
    boots = []
    nblk = int(math.ceil(len(a) / BLOCK))
    for _ in range(1000):
        st = RNG.integers(0, len(a) - BLOCK, nblk)
        sel = np.concatenate([np.arange(s0, s0 + BLOCK) for s0 in st])
        sel = sel[ok[sel]]
        Mb = np.zeros((3, 3))
        np.add.at(Mb, (a[sel].astype(int), b[sel].astype(int)), 1)
        boots.append(Mb / np.maximum(Mb.sum(1, keepdims=True), 1))
    boots = np.array(boots)
    lo, hi = np.percentile(boots, 2.5, 0), np.percentile(boots, 97.5, 0)
    trans = pd.DataFrame([[f"{P[i, j]:.2f} [{lo[i, j]:.2f}, {hi[i, j]:.2f}]" for j in range(3)] for i in range(3)],
                         index=[f"from {STATE[i]}" for i in range(3)], columns=[f"to {STATE[j]}" for j in range(3)])
    era = []
    for e, (y0, y1) in ERAS.items():
        m = (date >= y0) & (date < y1) & np.isfinite(lvl)
        if m.sum():
            era.append({"era": e, "weeks": int(m.sum()), "LOW": (lvl[m] == 0).mean(), "MID": (lvl[m] == 1).mean(),
                        "HIGH": (lvl[m] == 2).mean(), "median sigma bp": np.median(sig[m])})
    return (q1, q2), pd.DataFrame(dist), pd.DataFrame(sens), pd.DataFrame(spell_tab), trans, pd.DataFrame(era)


# ------------------------------------------------------------------ main
def run_pairs(T, Y, cur, years, windows=(None, TRAIL), boot=True):
    rows, roll = [], []
    for tn, y in Y.items():
        for name, x in T.items():
            cat = name in CATEGORICAL
            for w in windows:
                pred, base = prequential(x, y, cat, w)
                al = alarms(pred)
                wl = "expanding" if w is None else f"trailing {w}"
                strata = {"all": np.ones(len(x), bool)}
                if tn == "V-on":
                    strata.update({"state LOW": cur == 0, "state MID": cur == 1})
                elif tn != "V-off":
                    strata.update({f"state {STATE[s_]}": cur == s_ for s_ in range(3)})
                for sn, sel in strata.items():
                    m = metrics(pred, base, y, al, sel, boot=boot and sn == "all")
                    if m is None:
                        continue
                    rows.append(dict(target=tn, trace=name, window=wl, stratum=sn, **m))
                if w is None:
                    roll.append(dict(target=tn, trace=name, **rolling_skill(pred, base, y, years)))
    return pd.DataFrame(rows), pd.DataFrame(roll)


def self_check(template, Y, cur, years):
    n = len(template)
    hits = total = 0
    for _ in range(N_SYN):
        z = np.zeros(n); e = RNG.normal(size=n)
        for i in range(1, n):
            z[i] = 0.9 * z[i - 1] + e[i]
        z[~np.isfinite(template)] = np.nan
        R, _ = run_pairs({"syn": z}, Y, cur, years, windows=(None,), boot=True)
        R = R[(R.stratum == "all") & R.printed.astype(bool)]
        hits += int((R.skill_lo > 0).sum()); total += len(R)
    return hits, total


def main() -> int:
    os.chdir(ROOT)
    h, t, cuts, rv, rng, ret, nbar, big = load()
    sig = np.sqrt(rv)
    years = pd.to_datetime(cuts, unit="s").year.to_numpy()
    print(f"{'SMOKE ' if SMOKE else ''}H1 bars {len(t):,} {pd.to_datetime(t[0], unit='s'):%Y-%m-%d}.."
          f"{pd.to_datetime(t[-1], unit='s'):%Y-%m-%d}; weeks {len(cuts)}; valid {int(np.isfinite(sig).sum())}; big gaps {big}")
    if not SMOKE:
        assert big == 0 and pd.to_datetime(t[-1], unit="s") >= pd.Timestamp("2026-09-01"), "cache incomplete: run later"
    Y, cur, nxt, q = targets(sig, rv, ret)
    T = traces(h, t, cuts, rv, rng, ret, sig, nbar)
    cnt = []
    for tn, y in Y.items():
        for name, x in T.items():
            ok = np.isfinite(x) & np.isfinite(y)
            first = pd.to_datetime(cuts[np.flatnonzero(ok)[0]], unit="s").date() if ok.any() else None
            cnt.append(dict(target=tn, trace=name, risk_weeks=int(ok.sum()), events=int(np.nansum(y[ok])), first_week=first))
    C = pd.DataFrame(cnt)
    tc = pd.crosstab(pd.Series(cur).map(STATE), pd.Series(nxt).map(STATE))
    pd.set_option("display.width", 240); pd.set_option("display.max_columns", 40)
    print("\ncount table (per target: risk weeks and events for the trace with the most data)")
    print(C.sort_values("risk_weeks").groupby("target").tail(1).to_string(index=False))
    print("\ncausal 3x3 next-state counts (rows: state at the cut, columns: next week, same edges)")
    print(tc.to_string())
    if SMOKE:
        print("smoke: counts only, no accuracy figure computed")
        return 0
    hits, total = self_check(T["sig_ratio"], Y, cur, years)
    print(f"\nself-check: {hits}/{total} synthetic intervals with lower bound > 0 ({hits / max(total, 1):.1%}; must be <= 5%)")
    assert hits / max(total, 1) <= 0.05, "self-check failed"
    (q1, q2), dist, sens, spells, trans, era = part1(cuts, sig, ret, rv)
    print(f"\nPART 1 (full-sample, descriptive) bands: LOW < {q1:.0f} <= MID < {q2:.0f} <= HIGH (bp/week)")
    print(dist.round(1).to_string(index=False)); print(sens.to_string(index=False))
    print(spells.to_string(index=False)); print(trans.to_string()); print(era.round(3).to_string(index=False))
    R, RL = run_pairs(T, Y, cur, years)
    pos = R[(R.stratum == "all") & R.printed.astype(bool) & (R.skill_lo > 0)]
    print(f"\nPART 2: {len(R[R.stratum == 'all'])} pair-window results; positive-skill intervals (lower > 0): {len(pos)}")
    cols = ["target", "trace", "window", "weeks", "events", "base_rate", "brier_skill", "skill_lo", "skill_hi",
            "AUC", "alarms", "precision", "lift", "lift_lo", "lift_hi", "sensitivity", "FPR"]
    print(pos[cols].round(3).to_string(index=False) if len(pos) else "none")
    best = (R[(R.stratum == "all") & R.printed.astype(bool) & (R.window == "expanding")]
            .sort_values("brier_skill", ascending=False).groupby("target").head(3))
    print("\nbest 3 per target by skill (expanding window)")
    print(best[cols].round(3).to_string(index=False))
    with pd.ExcelWriter(OUT) as xw:
        C.to_excel(xw, sheet_name="counts", index=False)
        tc.to_excel(xw, sheet_name="causal transitions")
        dist.to_excel(xw, sheet_name="P1 bands", index=False); sens.to_excel(xw, sheet_name="P1 sensitivity", index=False)
        spells.to_excel(xw, sheet_name="P1 spells", index=False); trans.to_excel(xw, sheet_name="P1 transitions")
        era.to_excel(xw, sheet_name="P1 eras", index=False)
        R.to_excel(xw, sheet_name="P2 all pairs", index=False); RL.to_excel(xw, sheet_name="P2 rolling 5y", index=False)
    print(f"\nsaved {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
