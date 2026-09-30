"""Layer-0 feature library for the five-layer sieve (docs/SIEVE_PREREG.md).
build(B, cuts, ext) -> (DataFrame of features known at the close of bar t, dict of kind -> names).
Time features describe the ENTRY bar t+1 (known in advance). Read-only research."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "research" / "foundry"), str(ROOT / "research" / "pilot"), str(ROOT / "research" / "wpwb_weekly")]
import engine as E  # noqa: E402
import vol as V  # noqa: E402

_ZOO_SRC = (ROOT / "research" / "foundry" / "indicator_zoo.py").read_text(encoding="utf-8")
_ZOO_SRC = _ZOO_SRC[: _ZOO_SRC.index("rng = np.random.default_rng(7)")]
_ZOO_SRC = _ZOO_SRC.replace("H, D, cuts, cell = E.load()\n", "").replace(
    "o, h, l, c, v = (pd.Series(x) for x in (H.o, H.h, H.l, H.c, H.v))\n", "")


def zoo_signals(B):
    ns = {"__file__": str(ROOT / "research" / "foundry" / "indicator_zoo.py"), "__name__": "zoo_defs", "E": E, "np": np, "pd": pd}
    exec(compile(_ZOO_SRC, "zoo_defs", "exec"), ns)
    ns.update(H=B, o=pd.Series(B.o), h=pd.Series(B.h), l=pd.Series(B.l), c=pd.Series(B.c), v=pd.Series(B.v))
    return ns["signals"]()


def _rsi(x, n):
    d = x.diff(); up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean(); dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    return 100 - 100 / (1 + up / dn)


def _atr(h, l, c, n):            # ATR including bar t (known at its close)
    pc = c.shift(1)
    tr = pd.concat([h - l, (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1)
    return tr.rolling(n, min_periods=n).mean()


def wpwb_week_state(t, c, h, l, cuts):
    """Per cut k: EWMA forecast / 52-week median RV, 13-week trend z, log forecast (as in engine.regimes)."""
    rv_raw, _, ret, nb = V.weekly_rv(t, c, h, l, cuts)
    rv = V.mask_invalid(rv_raw, nb)
    f = V.ewma_forecast(rv)
    lr = np.log1p(np.where(np.isfinite(rv), ret, np.nan) / 1e4)
    ratio = np.full(len(cuts), np.nan); z = np.full(len(cuts), np.nan)
    for k in range(53, len(cuts)):
        w = rv[k - 52:k]
        if np.isfinite(w).sum() >= 40 and np.isfinite(f[k]):
            ratio[k] = f[k] / np.nanmedian(w)
        z[k] = E.trend_z(lr, rv, k - 1)
    return ratio, z, np.log(f)


def build(B, cuts, cell, ext=None):
    t = np.asarray(B.t, np.int64); n = len(t); step = int(B.step)
    o, h, l, c, v = (pd.Series(np.asarray(x, float)) for x in (B.o, B.h, B.l, B.c, B.v))
    a14 = _atr(h, l, c, 14); A = a14.replace(0, np.nan)
    F, kinds = {}, {"cont": [], "event": [], "time": [], "ext": []}

    def put(name, x, kind="cont"):
        F[name] = np.asarray(x, float); kinds[kind].append(name)

    # ---------------- indicator states
    r14 = _rsi(c, 14); put("rsi14", r14); put("rsi2", _rsi(c, 2))
    lo14, hi14 = l.rolling(14).min(), h.rolling(14).max()
    put("stoch_k", 100 * (c - lo14) / (hi14 - lo14)); put("willr", -100 * (hi14 - c) / (hi14 - lo14))
    tp = (h + l + c) / 3; md = tp.rolling(20).apply(lambda x: np.mean(np.abs(x - x.mean())), raw=True)
    put("cci20", (tp - tp.rolling(20).mean()) / (0.015 * md)); put("roc10", c.pct_change(10) * 1e4)
    macd = c.ewm(span=12, adjust=False).mean() - c.ewm(span=26, adjust=False).mean()
    put("macd_hist", (macd - macd.ewm(span=9, adjust=False).mean()) / A)
    for p in (20, 50, 200):
        put(f"c_sma{p}", (c - c.rolling(p).mean()) / A)
    s20 = c.rolling(20).mean(); put("sma20_slope", (s20 - s20.shift(5)) / A)
    put("ema9_21", (c.ewm(span=9, adjust=False).mean() - c.ewm(span=21, adjust=False).mean()) / A)
    sd20 = c.rolling(20).std(); put("bb_pctb", (c - (s20 - 2 * sd20)) / (4 * sd20))
    bw = 4 * sd20 / s20; put("bb_width_ratio", bw / bw.rolling(120).median())
    a20 = _atr(h, l, c, 20); put("keltner_pos", (c - c.ewm(span=20, adjust=False).mean()) / a20)
    for p in (20, 55):
        hh, ll = h.rolling(p).max(), l.rolling(p).min(); put(f"donch{p}_pos", (c - ll) / (hh - ll))
    up_m, dn_m = h.diff(), -l.diff()
    pdm = pd.Series(np.where((up_m > dn_m) & (up_m > 0), up_m, 0.0)); ndm = pd.Series(np.where((dn_m > up_m) & (dn_m > 0), dn_m, 0.0))
    pdi = 100 * pdm.ewm(alpha=1 / 14, adjust=False).mean() / A; ndi = 100 * ndm.ewm(alpha=1 / 14, adjust=False).mean() / A
    put("adx14", (100 * (pdi - ndi).abs() / (pdi + ndi)).ewm(alpha=1 / 14, adjust=False).mean()); put("di_diff", pdi - ndi)
    ar_up = 100 * h.rolling(26).apply(np.argmax, raw=True) / 25; ar_dn = 100 * l.rolling(26).apply(np.argmin, raw=True) / 25
    put("aroon_osc", ar_up - ar_dn)
    ten = (h.rolling(9).max() + l.rolling(9).min()) / 2; kij = (h.rolling(26).max() + l.rolling(26).min()) / 2
    put("tk_diff", (ten - kij) / A)
    spa = ((ten + kij) / 2).shift(26); spb = ((h.rolling(52).max() + l.rolling(52).min()) / 2).shift(26)
    put("cloud_pos", (c - (spa + spb) / 2) / A)
    day = (t - 22 * 3600) // 86400
    pv = (tp * v).groupby(day).cumsum(); vv = v.groupby(day).cumsum(); put("vwap_dist", (c - pv / vv) / A)
    obv = (np.sign(c.diff()).fillna(0) * v).cumsum(); put("obv_z", (obv - obv.rolling(20).mean()) / obv.rolling(20).std())
    rng_ = (h - l).replace(0, np.nan)
    put("body_frac", (c - o) / rng_); put("upper_wick", (h - np.maximum(o, c)) / rng_); put("lower_wick", (np.minimum(o, c) - l) / rng_)
    put("range_atr", (h - l) / A.shift(1))
    zs = zoo_signals(B)
    for nm in ("ParabolicSAR_flip", "Supertrend_10_3_flip", "HeikinAshi_color_change"):
        pass
    # side states from flips: +1 after a long flip until a short flip
    for nm, lab in (("ParabolicSAR_flip", "psar_side"), ("Supertrend_10_3_flip", "supertrend_side"), ("HeikinAshi_color_change", "ha_side")):
        sl, ss = zs[nm]; s = pd.Series(np.where(sl, 1.0, np.where(ss, -1.0, np.nan))).ffill()
        put(lab, s)
    # ---------------- indicator events (the 31 zoo signals)
    for nm, (sl, ss) in zs.items():
        put(f"ev_{nm}", np.where(sl, 1.0, np.where(ss, -1.0, 0.0)), "event")
    # ---------------- quant
    lc = np.log(c)
    for k in (1, 4, 24, 120, 480):
        put(f"ret{k}", (c - c.shift(k)) / A)
    for p in (20, 100):
        put(f"z{p}", (c - c.rolling(p).mean()) / c.rolling(p).std())
    d1 = lc.diff()
    put("eff_ratio24", (c - c.shift(24)).abs() / c.diff().abs().rolling(24).sum())
    put("autocorr24", d1.rolling(24).corr(d1.shift(1)))
    put("var_ratio", (lc - lc.shift(4)).rolling(96).var() / (4 * d1.rolling(96).var()))
    yr = int(round(365.25 * 86400 / step * 5 / 7))
    put("dist_52w_high", (c - h.rolling(yr, min_periods=yr // 2).max()) / A)
    put("dist_52w_low", (c - l.rolling(yr, min_periods=yr // 2).min()) / A)
    put("rv_ratio", d1.rolling(24).std() / d1.rolling(240).std())
    put("atr_pctile", a14.rolling(yr, min_periods=yr // 2).rank(pct=True))
    put("vol_z", (v - v.rolling(20).median()) / v.rolling(20).std())
    # ---------------- daily / weekly levels (completed periods only)
    g = pd.DataFrame(dict(day=day, h=h, l=l, c=c, o=o))
    dd = g.groupby("day").agg(h=("h", "max"), l=("l", "min"), c=("c", "last"), o=("o", "first"))
    prev = dd.shift(1)
    pdh, pdl, pdc = (prev[x].reindex(day).to_numpy() for x in ("h", "l", "c"))
    put("pd_range_pos", (c - pdl) / (pdh - pdl)); put("c_pdh", (c - pdh) / A); put("c_pdl", (c - pdl) / A)
    P = (pdh + pdl + pdc) / 3
    put("c_pivot", (c - P) / A); put("c_r1", (c - (2 * P - pdl)) / A); put("c_s1", (c - (2 * P - pdh)) / A)
    rng_d = dd.h - dd.l
    nr7 = (rng_d <= rng_d.rolling(7).min()).shift(1); inside = ((dd.h < dd.h.shift(1)) & (dd.l > dd.l.shift(1))).shift(1)
    put("nr7_prevday", nr7.reindex(day).astype(float).to_numpy()); put("inside_prevday", inside.reindex(day).astype(float).to_numpy())
    wk = np.searchsorted(cuts, t, side="left") - 1
    gw = pd.DataFrame(dict(wk=wk, h=h, l=l)).groupby("wk").agg(h=("h", "max"), l=("l", "min")).shift(1)
    pwh, pwl = gw.h.reindex(wk).to_numpy(), gw.l.reindex(wk).to_numpy()
    put("pw_range_pos", (c - pwl) / (pwh - pwl))
    for unit in (10, 50, 100):
        put(f"round{unit}", (c - np.round(c / unit) * unit) / A)
    put("bar_gap", (o - c.shift(1)) / A.shift(1))
    first_of_day = pd.Series(day).diff().fillna(1).to_numpy() != 0
    dgap = pd.Series(np.where(first_of_day, (o - c.shift(1)) / A.shift(1), np.nan)).groupby(day).ffill()
    put("daily_gap", dgap)
    wknd = np.r_[True, np.diff(t) > 24 * 3600]
    wgap = pd.Series(np.where(wknd, (o - c.shift(1)) / A.shift(1), np.nan)).groupby(wk).ffill()
    put("weekly_gap", wgap)
    # ---------------- SMC (loops, causal)
    H_, L_, C_ = h.to_numpy(), l.to_numpy(), c.to_numpy(); At = A.to_numpy()
    bull_n = np.zeros(n); bear_n = np.zeros(n); bull_d = np.full(n, np.nan); bear_d = np.full(n, np.nan)
    bulls, bears = [], []                    # (created bar, lower edge, upper edge)
    for i in range(2, n):
        if L_[i] > H_[i - 2]:
            bulls.append((i, H_[i - 2], L_[i]))
        if H_[i] < L_[i - 2]:
            bears.append((i, H_[i], L_[i - 2]))
        bulls = [z for z in bulls if L_[i] > z[1] and i - z[0] <= 20]        # filled once price trades to the lower edge
        bears = [z for z in bears if H_[i] < z[2] and i - z[0] <= 20]
        bull_n[i], bear_n[i] = len(bulls), len(bears)
        if bulls:
            bull_d[i] = min(C_[i] - z[2] for z in bulls) / At[i]
        if bears:
            bear_d[i] = min(z[1] - C_[i] for z in bears) / At[i]
    put("fvg_bull_n", bull_n); put("fvg_bear_n", bear_n); put("fvg_bull_dist", bull_d); put("fvg_bear_dist", bear_d)
    state = np.zeros(n); choch = np.zeros(n); sh = sl_ = np.nan; st = 0.0
    for i in range(4, n):
        j = i - 2                                # fractal centred at j is confirmed at i
        if H_[j] >= H_[j - 2:j + 3].max():
            sh = H_[j]
        if L_[j] <= L_[j - 2:j + 3].min():
            sl_ = L_[j]
        new = st
        if np.isfinite(sh) and C_[i] > sh:
            new = 1.0
        elif np.isfinite(sl_) and C_[i] < sl_:
            new = -1.0
        if new != st and st != 0:
            choch[i] = new
        st = new; state[i] = st
    put("structure_state", state); put("ev_choch", choch, "event")
    sweep_pd = np.where((h > pdh) & (c < pdh), -1.0, np.where((l < pdl) & (c > pdl), 1.0, 0.0))
    put("ev_sweep_prevday", sweep_pd, "event")
    m20h, m20l = h.rolling(20).max().shift(1), l.rolling(20).min().shift(1)
    put("ev_sweep20", np.where((h > m20h) & (c < m20h), -1.0, np.where((l < m20l) & (c > m20l), 1.0, 0.0)), "event")
    big = ((h - l) > 2 * A.shift(1)).to_numpy()
    last_big = pd.Series(np.where(big, np.arange(n), np.nan)).ffill().to_numpy()
    put("bars_since_expansion", np.minimum(np.arange(n) - last_big, 500))
    # ---------------- WPWB weekly state (known at the cut)
    ratio, z13, lf = ext["wpwb"] if ext and "wpwb" in ext else wpwb_week_state(t, np.asarray(c), np.asarray(h), np.asarray(l), cuts)
    wkc = np.clip(wk, 0, len(cuts) - 1)
    put("wpwb_vol_ratio", np.where(wk >= 0, ratio[wkc], np.nan)); put("wpwb_trend_z", np.where(wk >= 0, z13[wkc], np.nan))
    put("wpwb_log_f", np.where(wk >= 0, lf[wkc], np.nan))
    # ---------------- time of the ENTRY bar (t+1), DST-aware
    tn = np.r_[t[1:], t[-1] + step]
    u = pd.to_datetime(tn, unit="s", utc=True)
    lon = u.tz_convert("Europe/London"); ny = u.tz_convert("America/New_York")
    for hr in range(24):
        put(f"hour{hr:02d}", (u.hour == hr).astype(float), "time")
    for dw in range(5):
        put(f"dow{dw}", (u.dayofweek == dw).astype(float), "time")
    for mo in range(1, 13):
        put(f"month{mo:02d}", (u.month == mo).astype(float), "time")

    def contains(local, hh, mm):
        start = local.hour * 60 + local.minute
        return ((start <= hh * 60 + mm) & (hh * 60 + mm < start + step // 60)).astype(float)
    put("fix_am_bar", contains(lon, 10, 30), "time"); put("fix_pm_bar", contains(lon, 15, 0), "time")
    put("ny_open_bar", contains(ny, 9, 30), "time")
    put("after_weekend", np.r_[np.diff(t) > 24 * 3600, False].astype(float), "time")
    tday = pd.Series(((tn + 2 * 3600) // 86400))
    dates = pd.to_datetime(tday.to_numpy() * 86400, unit="s")
    ym = dates.year * 12 + dates.month
    uniq = pd.DataFrame(dict(d=tday, ym=ym)).drop_duplicates("d")
    uniq["rank_fwd"] = uniq.groupby("ym").cumcount(); uniq["rank_bwd"] = uniq.iloc[::-1].groupby("ym").cumcount().iloc[::-1]
    mp = uniq.set_index("d")
    put("turn_of_month", ((mp.rank_bwd.reindex(tday).to_numpy() == 0) | (mp.rank_fwd.reindex(tday).to_numpy() <= 1)).astype(float), "time")
    # ---------------- externals (NaN outside coverage)
    if ext:
        for nm, ser in ext.get("daily", {}).items():           # value of the latest date strictly before the trading day
            s = ser.dropna(); ds = s.index.values.astype("datetime64[D]").astype(np.int64)
            td = ((t + 2 * 3600) // 86400)
            j = np.searchsorted(ds, td, side="left") - 1
            put(nm, np.where(j >= 0, s.to_numpy()[np.clip(j, 0, None)], np.nan), "ext")
        for nm, (rel_t, vals) in ext.get("released", {}).items():   # value known after its release time
            j = np.searchsorted(rel_t, t + step, side="right") - 1        # released by the close of bar t
            put(nm, np.where(j >= 0, vals[np.clip(j, 0, None)], np.nan), "ext")
        if "news" in ext:
            et, sz = ext["news"]
            j = np.searchsorted(et, t + step, side="right") - 1
            since = np.where(j >= 0, (t + step - et[np.clip(j, 0, None)]) / 3600.0, np.nan)
            put("news_hours_since", np.minimum(since, 168), "ext")
            put("news_surprise_24h", np.where((since <= 24) & (j >= 0), sz[np.clip(j, 0, None)], 0.0), "ext")
            k = np.searchsorted(et, tn, side="left")
            nxt = np.where(k < len(et), et[np.clip(k, 0, len(et) - 1)] - tn, np.inf)
            put("news_next24", (nxt <= 24 * 3600).astype(float), "ext")
        for nm, arr in ext.get("aligned", {}).items():
            put(nm, arr, "ext")
    df = pd.DataFrame(F).astype("float32")
    df = df.replace([np.inf, -np.inf], np.nan)
    return df, kinds
