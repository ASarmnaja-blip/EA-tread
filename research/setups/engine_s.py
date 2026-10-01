"""Shared engine for docs/plans/P01..P15 (rules in docs/plans/P00_COMMON.md): bars, fractal swings, an order simulator (market or limit
entry, stop first inside a bar, fixed take-profit or the uncapped Chandelier exit, the creator's early-cut rule on closes), matched random
controls, weekly-cluster bootstrap p, Holm, and the pass rule."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path[:0] = [str(ROOT / "research" / "bundle")]
import common as C  # noqa: E402

L = C.L
OUT = ROOT / "data" / "setups"; OUT.mkdir(parents=True, exist_ok=True)
MARKETS = tuple(m for m in C.ORIG8 + C.NEW8 if m != "USDINR")
CUTS = L.cut_grid(C.ts("2026-10-02"))
_BARS = {}


def bars(mkt, tf):
    key = (mkt, tf)
    if key not in _BARS:
        if mkt == "GOLD_DUKAS":
            import y1_htf_system as Y
            B = Y.early_bars(tf)
        else:
            B = C.bars(mkt, tf)
        B.a22 = L.atr(B.h, B.l, B.c, 22)
        _BARS[key] = B
    return _BARS[key]


def drop_cache():
    _BARS.clear()


def sym_of(mkt):
    return "XAUUSD" if mkt == "GOLD_DUKAS" else mkt


def samples(mkt, t):
    t = np.asarray(t)
    if mkt == "GOLD_DUKAS":
        return {"DEV": t < C.ts("2016-01-01"), "CHECK": t >= C.ts("2016-01-01")}
    if mkt == "XAUUSD":
        return {"DEV": (t >= C.ts("2009-01-01")) & (t < C.ts("2016-01-01")), "CHECK": t >= C.ts("2016-01-01")}
    return {"ALL": np.ones(len(t), bool)}


# ------------------------------------------------------------------ swings
def fractals(B, k=2):
    """Pivot flags: swing high at j if h[j] > max of the k bars before and >= max of the k bars after (mirror for lows). A pivot is known at
    bar j + k (confirmation index)."""
    h = pd.Series(B.h); l = pd.Series(B.l)
    left_h = h.shift(1).rolling(k).max(); right_h = h[::-1].shift(1).rolling(k).max()[::-1]
    left_l = l.shift(1).rolling(k).min(); right_l = l[::-1].shift(1).rolling(k).min()[::-1]
    sh = ((h > left_h) & (h >= right_h)).to_numpy()
    sl = ((l < left_l) & (l <= right_l)).to_numpy()
    return sh, sl


def swing_table(B, k=2):
    """Confirmed swings in confirmation order: DataFrame with conf (bar where it becomes known), piv (pivot bar), kind (+1 high / -1 low), val."""
    sh, sl = fractals(B, k)
    ih = np.flatnonzero(sh); il = np.flatnonzero(sl)
    S = pd.DataFrame(dict(piv=np.r_[ih, il], kind=np.r_[np.ones(len(ih), int), -np.ones(len(il), int)], val=np.r_[B.h[ih], B.l[il]]))
    S["conf"] = S.piv + k
    S = S[S.conf < len(B.c)].sort_values(["conf", "piv"]).reset_index(drop=True)
    return S


# ------------------------------------------------------------------ simulator
def simulate(B, sym, O, mode):
    """O: DataFrame with s, d, kind ('mkt' / 'lmt'), lmt, valid_to, sl, tp (NaN = none), cut (close level that exits against d; NaN = none).
    mode 'tp' uses tp; 'unc' ignores tp and exits on a close beyond best -/+ 3 x ATR22. Returns one row per filled trade."""
    n = len(B.c); o, h, l, c, A = B.o, B.h, B.l, B.c, B.a22
    rows = []
    s_ = O.s.to_numpy(np.int64); d_ = O.d.to_numpy(np.int64); kind = O.kind.to_numpy(); lmt = O.lmt.to_numpy(float)
    vt = O.valid_to.to_numpy(np.int64); sl_ = O.sl.to_numpy(float); tp_ = O.tp.to_numpy(float); cut_ = O["cut"].to_numpy(float)
    can_ = O["cancel"].to_numpy(float) if "cancel" in O else np.full(len(O), np.nan)
    trail_lo = getattr(B, "trail_lo", None); trail_hi = getattr(B, "trail_hi", None)
    for i in range(len(O)):
        s, d, sl = s_[i], d_[i], sl_[i]
        tp = tp_[i] if mode == "tp" else np.nan
        if s + 1 >= n or not np.isfinite(sl):
            continue
        if kind[i] == "mkt":
            e = s + 1; ep = o[e]
            if d * (ep - sl) <= 0 or (np.isfinite(tp) and d * (tp - ep) <= 0):
                continue
            first = e; fill_bar_checked = False
        else:
            j1 = min(vt[i], n - 1); e = None
            for j in range(s + 1, j1 + 1):
                if np.isfinite(can_[i]) and ((d > 0 and h[j] >= can_[i] and l[j] > lmt[i]) or (d < 0 and l[j] <= can_[i] and h[j] < lmt[i])):
                    break                                                    # cancel level traded before the limit: cancelled
                if (d > 0 and l[j] <= lmt[i]) or (d < 0 and h[j] >= lmt[i]):
                    e = j; ep = min(o[j], lmt[i]) if d > 0 else max(o[j], lmt[i]); break
            if e is None or d * (ep - sl) <= 0:
                continue
            first = e; fill_bar_checked = True
        risk = abs(ep - sl)
        x = None; px = None; j0 = first; W = 64; best = ep
        while x is None:
            j1 = min(n, j0 + W)
            seg_l, seg_h, seg_c = l[j0:j1], h[j0:j1], c[j0:j1]
            st = (seg_l <= sl) if d > 0 else (seg_h >= sl)
            if np.isfinite(tp):
                tg = (seg_h >= tp) if d > 0 else (seg_l <= tp)
                if fill_bar_checked and j0 == first:
                    tg = tg.copy(); tg[0] = False                         # no target inside the bar that filled the limit
            else:
                tg = np.zeros(len(st), bool)
            ce = np.zeros(len(st), bool)
            if np.isfinite(cut_[i]):
                ce |= (seg_c < cut_[i]) if d > 0 else (seg_c > cut_[i])
            if mode == "struct":                                          # close beyond the latest confirmed swing (P15 exit B)
                lv = trail_lo[j0:j1] if d > 0 else trail_hi[j0:j1]
                with np.errstate(invalid="ignore"):
                    ce |= (seg_c < lv) if d > 0 else (seg_c > lv)
            if mode == "unc":
                ext = seg_h if d > 0 else seg_l
                bst = np.maximum.accumulate(np.r_[best, ext])[1:] if d > 0 else np.minimum.accumulate(np.r_[best, ext])[1:]
                with np.errstate(invalid="ignore"):
                    ce |= (seg_c < bst - 3 * A[j0:j1]) if d > 0 else (seg_c > bst + 3 * A[j0:j1])
            ks = int(np.argmax(st)) if st.any() else 10 ** 9
            kt = int(np.argmax(tg)) if tg.any() else 10 ** 9
            kc = int(np.argmax(ce)) if ce.any() else 10 ** 9
            k = min(ks, kt, kc)
            if k < 10 ** 9:
                j = j0 + k
                if ks == k:
                    px = sl if (j == first or d * (o[j] - sl) > 0) else o[j]; x = j
                elif kt == k:
                    px = tp if (j == first or d * (tp - o[j]) > 0) else o[j]; x = j
                else:
                    if j + 1 < n:
                        px = o[j + 1]; x = j + 1
                    else:
                        px = c[n - 1]; x = n - 1
            elif j1 >= n:
                px = c[n - 1]; x = n - 1
            else:
                if mode == "unc":
                    best = bst[-1]
                j0 = j1; W *= 4
        rows.append((i, s, e, x, d, ep, px, risk))
    if not rows:
        return pd.DataFrame(columns=["oi", "s", "e", "x", "d", "ep", "px", "risk", "t", "t_exit", "gR", "R"])
    T = pd.DataFrame(rows, columns=["oi", "s", "e", "x", "d", "ep", "px", "risk"])
    T["t"] = B.t[T.e.to_numpy()]; T["t_exit"] = B.t[T.x.to_numpy()]
    T["gR"] = T.d * (T.px - T.ep) / T.risk
    sw = C.swap_bp(sym, T.t.to_numpy(), T.t_exit.to_numpy(), T.d.to_numpy())
    T["R"] = T.gR - (C.cost_rt_bp(sym) + sw) / (T.risk / T.ep * 1e4)
    return T


# ------------------------------------------------------------------ control
def control(B, sym, O, T, mode, mask_bars=None, tod=False, draws=20, cap=2000, seed=0):
    """Matched random entries: same direction, stop and target distances in ATR14 multiples of the real signal bar, market entry at a random
    bar (inside mask_bars when given; same time of day when tod)."""
    if not len(T):
        return np.nan
    rng = np.random.default_rng(seed)
    n = len(B.c); A = B.atr
    Ot = O.iloc[T.oi.to_numpy()]
    a_s = A[Ot.s.to_numpy()]
    ksl = np.abs(T.ep.to_numpy() - Ot.sl.to_numpy()) / a_s
    ktp = np.abs(Ot.tp.to_numpy() - T.ep.to_numpy()) / a_s
    dd = T.d.to_numpy()
    if isinstance(mask_bars, dict):
        pools = {k: np.flatnonzero(v) for k, v in mask_bars.items()}
    else:
        pools = {k: (np.flatnonzero(mask_bars) if mask_bars is not None else np.arange(30, n - 2)) for k in (1, -1)}
    pools = {k: v[(v > 30) & (v < n - 2)] for k, v in pools.items()}
    pool = np.unique(np.r_[pools[1], pools[-1]])
    if tod:
        sec = B.t % 86400
    means = []
    for _ in range(draws):
        m = min(len(T), cap)
        pick = rng.integers(0, len(T), m)
        if tod:
            day = rng.choice(np.unique(B.t[pool] // 86400), m)
            want = day * 86400 + sec[Ot.s.to_numpy()[pick]]
            r = np.searchsorted(B.t, want)
            r = r[(r < n - 2) & (B.t[np.minimum(r, n - 1)] == want)]
            pick = pick[: len(r)]
        else:
            r = np.array([rng.choice(pools[int(x)]) if len(pools[int(x)]) else rng.choice(pool) for x in dd[pick]], np.int64)
        a = A[r]; ep = B.o[np.minimum(r + 1, n - 1)]
        sl = ep - dd[pick] * ksl[pick] * a
        tp = ep + dd[pick] * ktp[pick] * a
        Oc = pd.DataFrame(dict(s=r, d=dd[pick], kind="mkt", lmt=np.nan, valid_to=r, sl=sl, tp=tp, cut=np.nan))
        ok = np.isfinite(a) & np.isfinite(sl)
        Tc = simulate(B, sym, Oc[ok].reset_index(drop=True), mode)
        if len(Tc):
            means.append(Tc.R.mean())
    return float(np.mean(means)) if means else np.nan


# ------------------------------------------------------------------ statistics
def boot_p(R, t, K=1000, seed=7):
    R = np.asarray(R, float); t = np.asarray(t)
    if len(R) < 10:
        return np.nan
    w = np.searchsorted(CUTS, t, side="right") - 1
    uw, inv = np.unique(w, return_inverse=True)
    S = np.bincount(inv, R); N = np.bincount(inv); mu = S.sum() / N.sum()
    rng = np.random.default_rng(seed); idx = rng.integers(0, len(uw), (K, len(uw)))
    bm = (S - mu * N)[idx].sum(1) / N[idx].sum(1)
    return float((bm >= mu).mean())


def holm(p):
    p = np.asarray(p, float); m = np.isfinite(p).sum(); out = np.full(len(p), np.nan); run = 0.0
    for r, i in enumerate(np.argsort(np.where(np.isfinite(p), p, np.inf))):
        if np.isfinite(p[i]):
            run = max(run, min(1.0, (m - r) * p[i])); out[i] = run
    return out


def summarize(plan, tf, variant, mode, mkt, sample, T, ctl, years):
    R = T.R.to_numpy() if len(T) else np.zeros(0)
    win = R > 0
    return dict(plan=plan, tf=tf, variant=variant, exit=mode, mkt=mkt, sample=sample, n=len(R), per_year=len(R) / max(years, 0.1),
                win=float(win.mean()) if len(R) else np.nan, avg_win=float(R[win].mean()) if win.any() else np.nan,
                avg_loss=float(R[~win].mean()) if (~win).any() else np.nan, R=float(R.mean()) if len(R) else np.nan,
                gR=float(T.gR.mean()) if len(T) else np.nan, ctl_R=ctl, excess=(float(R.mean()) - ctl) if len(R) and np.isfinite(ctl) else np.nan,
                p_net=boot_p(R, T.t) if len(R) else np.nan,
                p_excess=boot_p(R - ctl, T.t) if len(R) and np.isfinite(ctl) else np.nan)


def verdict(D):
    """Pass rule of P00 per plan x tf x variant x exit."""
    g = D[(D.mkt == "XAUUSD") & (D["sample"] == "CHECK")].copy()
    g["p_max"] = np.fmax(g.p_net.to_numpy(float), g.p_excess.to_numpy(float))
    out = []
    for plan, gp in g.groupby("plan"):
        gp = gp.copy(); gp["p_holm"] = holm(gp.p_max.to_numpy())
        for r in gp.itertuples():
            key = (D.plan == plan) & (D.tf == r.tf) & (D.variant == r.variant) & (D.exit == r.exit)
            dev = D[key & (D.mkt == "XAUUSD") & (D["sample"] == "DEV")]
            sv = D[key & (D.mkt == "XAGUSD")]
            ot = D[key & D.mkt.isin(MARKETS) & (D.n >= 30)]
            share = float((ot.R > 0).mean()) if len(ot) >= 5 else np.nan
            ok = (r.R > 0 and r.excess > 0 and r.p_holm < 0.05 and len(dev) and dev.R.iloc[0] > 0 and len(sv) and sv.R.iloc[0] > 0
                  and (np.isnan(share) or share >= 0.6))
            out.append(dict(plan=plan, tf=r.tf, variant=r.variant, exit=r.exit, n_check=r.n, R_check=r.R, win_check=r.win, excess=r.excess,
                            p_holm=r.p_holm, R_dev=dev.R.iloc[0] if len(dev) else np.nan, R_silver=sv.R.iloc[0] if len(sv) else np.nan,
                            win_silver=sv.win.iloc[0] if len(sv) else np.nan, markets=len(ot), share_markets_pos=share,
                            median_market_R=float(ot.R.median()) if len(ot) else np.nan, PASS=bool(ok)))
    return pd.DataFrame(out)


def run_plan(plan, gen, tfs, markets, modes=("tp", "unc"), tod=False, mask_fn=None, log=print):
    """gen(B, mkt, tf) -> dict variant -> orders DataFrame. Every (tf, variant, mode, market, sample) is summarized."""
    rows = []
    for tf in tfs:
        for mkt in markets:
            try:
                B = bars(mkt, tf)
            except (FileNotFoundError, KeyError, ValueError):
                continue
            try:
                Vs = gen(B, mkt, tf)
            except (FileNotFoundError, KeyError, ValueError) as ex:
                log(f"  {plan} {mkt} {tf}: skipped ({ex})"); continue
            for variant, O in Vs.items():
                if O is None or not len(O):
                    continue
                O = O.reset_index(drop=True)
                for mode in modes:
                    T = simulate(B, sym_of(mkt), O, mode)
                    if not len(T):
                        continue
                    for sname, m in samples(mkt, T.t.to_numpy()).items():
                        TT = T[m].reset_index(drop=True)
                        if len(TT) < 5:
                            continue
                        mb = mask_fn(B) if mask_fn else None
                        ctl = control(B, sym_of(mkt), O, TT, mode, mask_bars=mb, tod=tod)
                        yrs = (TT.t.max() - TT.t.min()) / (365.25 * 86400) if len(TT) > 1 else 0.1
                        rows.append(summarize(plan, tf, variant, mode, mkt, sname, TT, ctl, yrs))
            log(f"  {plan} {mkt} {tf} done")
        drop_cache()
    return pd.DataFrame(rows)


def orders(s, d, sl, tp, kind="mkt", lmt=None, valid_to=None, cut=None, cancel=None):
    s = np.asarray(s, np.int64)
    k = len(s)
    return pd.DataFrame(dict(s=s, d=np.asarray(d, np.int64), kind=kind, lmt=np.full(k, np.nan) if lmt is None else np.asarray(lmt, float),
                             valid_to=s if valid_to is None else np.asarray(valid_to, np.int64), sl=np.asarray(sl, float), tp=np.asarray(tp, float),
                             cut=np.full(k, np.nan) if cut is None else np.asarray(cut, float),
                             cancel=np.full(k, np.nan) if cancel is None else np.asarray(cancel, float)))
