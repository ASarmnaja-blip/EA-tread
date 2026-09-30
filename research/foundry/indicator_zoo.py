"""Indicator zoo with 1:1 exits (operator request 2026-09-30: "every tool, every indicator", not tuned
to win). Classic indicators on H1 with textbook parameters; every signal is traded two ways, FOLLOW
(as the textbook reads it) and FADE (the opposite); exits 1:1 with stop = target = k ATR, k {1, 2},
max hold {24, 72} h, one position at a time; entry at the next bar's open; 2 bp cost and swap.
Each result is compared with RANDOM entries using the same k, hold and direction mix (the no-edge
baseline, which also carries the simulator's conservative intrabar rules). By era 2003-26.
Writes data/foundry/indicator_zoo.csv and data/foundry/indicator_zoo.png. Descriptive only."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import engine as E  # noqa: E402
from families import nonoverlap  # noqa: E402

H, D, cuts, cell = E.load()
o, h, l, c, v = (pd.Series(x) for x in (H.o, H.h, H.l, H.c, H.v))
ERAS = {"2003-08": ("2003", "2009"), "2009-14": ("2009", "2015"), "2015-20": ("2015", "2021"), "2021-26": ("2021", "2027")}


def cross_up(a, b):
    a, b = pd.Series(a), pd.Series(b)
    return ((a > b) & (a.shift(1) <= b.shift(1))).to_numpy()


def cross_dn(a, b):
    a, b = pd.Series(a), pd.Series(b)
    return ((a < b) & (a.shift(1) >= b.shift(1))).to_numpy()


def rsi(x, n):
    d = x.diff(); up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean(); dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    return 100 - 100 / (1 + up / dn)


def atr_s(n):
    pc = c.shift(1)
    tr = pd.concat([h - l, (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / n, adjust=False).mean()


def signals():
    """{name: (long_signal_bool, short_signal_bool)} - the textbook reading, evaluated on bar close."""
    S = {}
    for f, s_ in ((10, 30), (20, 50), (50, 200)):
        a, b = c.rolling(f).mean(), c.rolling(s_).mean()
        S[f"SMA_cross_{f}_{s_}"] = (cross_up(a, b), cross_dn(a, b))
    for f, s_ in ((9, 21), (12, 26)):
        a, b = c.ewm(span=f, adjust=False).mean(), c.ewm(span=s_, adjust=False).mean()
        S[f"EMA_cross_{f}_{s_}"] = (cross_up(a, b), cross_dn(a, b))
    macd = c.ewm(span=12, adjust=False).mean() - c.ewm(span=26, adjust=False).mean(); sig = macd.ewm(span=9, adjust=False).mean()
    S["MACD_signal_cross"] = (cross_up(macd, sig), cross_dn(macd, sig))
    S["MACD_zero_cross"] = (cross_up(macd, 0 * macd), cross_dn(macd, 0 * macd))
    r14 = rsi(c, 14)
    S["RSI14_30_70_exit"] = (cross_up(r14, 30 + 0 * r14), cross_dn(r14, 70 + 0 * r14))      # leaves oversold / overbought
    S["RSI14_cross_50"] = (cross_up(r14, 50 + 0 * r14), cross_dn(r14, 50 + 0 * r14))
    r2 = rsi(c, 2)
    S["RSI2_10_90"] = ((r2 < 10).to_numpy() & (r2.shift(1) >= 10).to_numpy(), (r2 > 90).to_numpy() & (r2.shift(1) <= 90).to_numpy())
    lo14, hi14 = l.rolling(14).min(), h.rolling(14).max()
    k_ = 100 * (c - lo14) / (hi14 - lo14); d_ = k_.rolling(3).mean()
    S["Stoch_14_3_OBOS"] = (cross_up(k_, d_) & (k_ < 20).to_numpy(), cross_dn(k_, d_) & (k_ > 80).to_numpy())
    tp = (h + l + c) / 3; cci = (tp - tp.rolling(20).mean()) / (0.015 * tp.rolling(20).apply(lambda x: np.mean(np.abs(x - x.mean())), raw=True))
    S["CCI20_cross_100"] = (cross_up(cci, 100 + 0 * cci), cross_dn(cci, -100 + 0 * cci))
    wr = -100 * (hi14 - c) / (hi14 - lo14)
    S["WilliamsR_exit_OBOS"] = (cross_up(wr, -80 + 0 * wr), cross_dn(wr, -20 + 0 * wr))
    roc = c.pct_change(10)
    S["ROC10_zero_cross"] = (cross_up(roc, 0 * roc), cross_dn(roc, 0 * roc))
    ar_up = 100 * h.rolling(26).apply(np.argmax, raw=True) / 25; ar_dn = 100 * l.rolling(26).apply(np.argmin, raw=True) / 25
    S["Aroon25_cross"] = (cross_up(ar_up, ar_dn), cross_dn(ar_up, ar_dn))
    m20, s20 = c.rolling(20).mean(), c.rolling(20).std()
    S["BB_breakout_20_2"] = (cross_up(c, m20 + 2 * s20), cross_dn(c, m20 - 2 * s20))
    S["BB_reentry_20_2"] = (cross_up(c, m20 - 2 * s20), cross_dn(c, m20 + 2 * s20))            # back inside: reversal reading
    at = atr_s(20); em = c.ewm(span=20, adjust=False).mean()
    S["Keltner_breakout_20_2"] = (cross_up(c, em + 2 * at), cross_dn(c, em - 2 * at))
    S["Donchian20_breakout"] = ((c > h.rolling(20).max().shift(1)).to_numpy(), (c < l.rolling(20).min().shift(1)).to_numpy())
    S["Donchian55_breakout"] = ((c > h.rolling(55).max().shift(1)).to_numpy(), (c < l.rolling(55).min().shift(1)).to_numpy())
    up_m, dn_m = h.diff(), -l.diff()
    pdm = pd.Series(np.where((up_m > dn_m) & (up_m > 0), up_m, 0.0)); ndm = pd.Series(np.where((dn_m > up_m) & (dn_m > 0), dn_m, 0.0))
    a14 = atr_s(14); pdi = 100 * pdm.ewm(alpha=1 / 14, adjust=False).mean() / a14; ndi = 100 * ndm.ewm(alpha=1 / 14, adjust=False).mean() / a14
    adx = (100 * (pdi - ndi).abs() / (pdi + ndi)).ewm(alpha=1 / 14, adjust=False).mean()
    S["ADX25_DI_cross"] = (cross_up(pdi, ndi) & (adx > 25).to_numpy(), cross_dn(pdi, ndi) & (adx > 25).to_numpy())
    # Parabolic SAR (0.02, 0.2)
    n = len(c); sar = np.zeros(n); bull = np.ones(n, bool); af = 0.02; ep = H.h[0]; sar[0] = H.l[0]
    for i in range(1, n):
        sar[i] = sar[i - 1] + af * (ep - sar[i - 1]); bull[i] = bull[i - 1]
        if bull[i]:
            if H.l[i] < sar[i]:
                bull[i] = False; sar[i] = ep; ep = H.l[i]; af = 0.02
            elif H.h[i] > ep:
                ep = H.h[i]; af = min(af + 0.02, 0.2)
        else:
            if H.h[i] > sar[i]:
                bull[i] = True; sar[i] = ep; ep = H.h[i]; af = 0.02
            elif H.l[i] < ep:
                ep = H.l[i]; af = min(af + 0.02, 0.2)
    bs = pd.Series(bull)
    S["ParabolicSAR_flip"] = ((bs & ~bs.shift(1, fill_value=True)).to_numpy(), (~bs & bs.shift(1, fill_value=False)).to_numpy())
    # Supertrend (10, 3)
    a10 = atr_s(10).to_numpy(); hl2 = ((h + l) / 2).to_numpy(); ub = hl2 + 3 * a10; lb = hl2 - 3 * a10
    st_up = np.ones(n, bool); fub, flb = ub.copy(), lb.copy()
    for i in range(1, n):
        fub[i] = ub[i] if (ub[i] < fub[i - 1] or H.c[i - 1] > fub[i - 1]) else fub[i - 1]
        flb[i] = lb[i] if (lb[i] > flb[i - 1] or H.c[i - 1] < flb[i - 1]) else flb[i - 1]
        st_up[i] = (H.c[i] > fub[i - 1]) if not st_up[i - 1] else not (H.c[i] < flb[i - 1])
    su = pd.Series(st_up)
    S["Supertrend_10_3_flip"] = ((su & ~su.shift(1, fill_value=True)).to_numpy(), (~su & su.shift(1, fill_value=False)).to_numpy())
    ten = (h.rolling(9).max() + l.rolling(9).min()) / 2; kij = (h.rolling(26).max() + l.rolling(26).min()) / 2
    S["Ichimoku_TK_cross"] = (cross_up(ten, kij), cross_dn(ten, kij))
    spa = ((ten + kij) / 2).shift(26); spb = ((h.rolling(52).max() + l.rolling(52).min()) / 2).shift(26)
    top, bot = np.maximum(spa, spb), np.minimum(spa, spb)
    S["Ichimoku_cloud_break"] = (cross_up(c, top), cross_dn(c, bot))
    day = (H.t - 22 * 3600) // 86400
    pv = (tp * v).groupby(day).cumsum(); vv = v.groupby(day).cumsum(); vwap = pv / vv
    S["VWAP_daily_cross"] = (cross_up(c, vwap), cross_dn(c, vwap))
    obv = (np.sign(c.diff()).fillna(0) * v).cumsum(); ob_ma = obv.rolling(20).mean()
    S["OBV_SMA20_cross"] = (cross_up(obv, ob_ma), cross_dn(obv, ob_ma))
    hac = (o + h + l + c) / 4; hao = hac.copy()
    hao_arr = hao.to_numpy().copy(); hac_arr = hac.to_numpy(); oo = H.o
    hao_arr[0] = (oo[0] + H.c[0]) / 2
    for i in range(1, n):
        hao_arr[i] = (hao_arr[i - 1] + hac_arr[i - 1]) / 2
    green = pd.Series(hac_arr > hao_arr)
    S["HeikinAshi_color_change"] = ((green & ~green.shift(1, fill_value=True)).to_numpy(), (~green & green.shift(1, fill_value=False)).to_numpy())
    po, pcl = o.shift(1), c.shift(1)
    S["Engulfing"] = (((c > o) & (pcl < po) & (c >= po) & (o <= pcl)).to_numpy(), ((c < o) & (pcl > po) & (c <= po) & (o >= pcl)).to_numpy())
    body = (c - o).abs(); rngb = h - l
    lw = np.minimum(o, c) - l; uw = h - np.maximum(o, c)
    S["PinBar"] = (((lw > 2 * body) & (lw > 0.6 * rngb)).to_numpy(), ((uw > 2 * body) & (uw > 0.6 * rngb)).to_numpy())
    inside = (h < h.shift(1)) & (l > l.shift(1))
    ins = inside.shift(1, fill_value=False)
    S["InsideBar_break"] = ((ins & (c > h.shift(1))).to_numpy(), (ins & (c < l.shift(1))).to_numpy())
    return S


def trades(sig_long, sig_short, k, hold, fade):
    idx_l = np.flatnonzero(sig_long[:-1]); idx_s = np.flatnonzero(sig_short[:-1])
    ent = np.r_[idx_l, idx_s] + 1
    d = np.r_[np.ones(len(idx_l)), -np.ones(len(idx_s))] * (-1 if fade else 1)
    o_ = np.argsort(ent, kind="stable"); ent, d = ent[o_], d[o_]
    ok = np.isfinite(H.atr[ent]) & (ent < len(H.t) - 80)
    ent, d = ent[ok], d[ok]
    last = np.searchsorted(H.t, H.t[ent] + (hold - 1) * 3600, side="right") - 1
    keep = nonoverlap(ent, last); ent, d, last = ent[keep], d[keep], last[keep]
    a = H.atr[ent]
    g, ex = E.simulate(H, ent, d, k * a, k * a, last)
    g = g - E.swap_bp(H, ent, ex, d)
    R = (g - E.COST_BP) / (k * a / H.o[ent] * 1e4)
    return ent, d, R


rng = np.random.default_rng(7)
pool = np.flatnonzero(np.isfinite(H.atr) & (np.arange(len(H.t)) < len(H.t) - 80))
base = {}
for k in (1, 2):
    for hold in (24, 72):
        ent = np.sort(rng.choice(pool, 30000, replace=False)); d = np.where(rng.random(len(ent)) < .5, 1.0, -1.0)
        last = np.searchsorted(H.t, H.t[ent] + (hold - 1) * 3600, side="right") - 1
        a = H.atr[ent]; g, ex = E.simulate(H, ent, d, k * a, k * a, last); g = g - E.swap_bp(H, ent, ex, d)
        R = (g - E.COST_BP) / (k * a / H.o[ent] * 1e4)
        dt = pd.to_datetime(H.t[ent], unit="s")
        base[(k, hold)] = {e: float(R[(dt >= a0) & (dt < a1)].mean()) for e, (a0, a1) in ERAS.items()} | {"ALL": float(R.mean())}

rows = []
for name, (sl, ss) in signals().items():
    for fade in (False, True):
        for k in (1, 2):
            for hold in (24, 72):
                ent, d, R = trades(sl, ss, k, hold, fade)
                if len(ent) < 50:
                    continue
                dt = pd.to_datetime(H.t[ent], unit="s")
                r = dict(indicator=name, mode="FADE" if fade else "FOLLOW", k_atr=k, hold_h=hold, n=len(ent),
                         long_share=float((d > 0).mean()), win_rate=float((R > -E.COST_BP / 1e9).mean()),
                         net_R=float(R.mean()), t=E.cluster_t(R, H.t[ent] // E.WEEK), random_R=base[(k, hold)]["ALL"])
                r["excess_R"] = r["net_R"] - r["random_R"]
                for e, (a0, a1) in ERAS.items():
                    m = (dt >= a0) & (dt < a1)
                    r[f"R_{e}"] = float(R[m].mean()) if m.sum() >= 20 else np.nan
                    r[f"exc_{e}"] = r[f"R_{e}"] - base[(k, hold)][e]
                rows.append(r)
X = pd.DataFrame(rows)
out = E.ROOT / "data" / "foundry" / "indicator_zoo.csv"
X.to_csv(out, index=False)
exc_cols = [f"exc_{e}" for e in ERAS]
X["beats_random_all_eras"] = (X[exc_cols] > 0).all(axis=1)
X["net_pos_all_eras"] = (X[[f"R_{e}" for e in ERAS]] > 0).all(axis=1)
pd.set_option("display.width", 250); pd.set_option("display.max_rows", 400)
print(f"{X.indicator.nunique()} indicators, {len(X)} indicator x mode x k x hold setups, {int(X.n.sum()):,} trades -> {out.name}")
print(f"net R > 0 over 2003-26: {(X.net_R > 0).mean():.0%}; beats random over 2003-26: {(X.excess_R > 0).mean():.0%}; "
      f"beats random in ALL four eras: {int(X.beats_random_all_eras.sum())} (a coin flip per era: ~{len(X) / 16:.0f}); "
      f"net > 0 in all four eras: {int(X.net_pos_all_eras.sum())}")
S = X.groupby(["indicator", "mode"]).agg(n=("n", "mean"), net_R=("net_R", "mean"), excess_R=("excess_R", "mean"),
                                         eras_beaten=("beats_random_all_eras", "sum")).round(3)
print("\nper indicator and mode (averaged over k and hold):")
print(S.sort_values("excess_R", ascending=False).to_string())
print("\nsetups beating random in all four eras:")
print(X[X.beats_random_all_eras][["indicator", "mode", "k_atr", "hold_h", "n", "net_R", "excess_R"] + exc_cols].round(3).to_string(index=False))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
fig, ax = plt.subplots(1, 2, figsize=(17, 9), gridspec_kw=dict(width_ratios=[2, 1]))
P = S.reset_index()
P["label"] = P.indicator + " (" + P["mode"] + ")"
P = P.sort_values("excess_R")
ax[0].barh(P.label, P.excess_R, color=np.where(P.excess_R > 0, "tab:green", "tab:red"))
ax[0].axvline(0, color="k", lw=.7); ax[0].set_xlabel("net R per trade minus random entries (same stop, hold)")
ax[0].set_title("Indicator zoo, 1:1 exits, H1 gold 2003-2026, after cost and swap"); ax[0].tick_params(axis="y", labelsize=7)
ax[1].hist(X.net_R, bins=40, color="tab:blue", alpha=.75, label="indicators")
for key, b in base.items():
    ax[1].axvline(b["ALL"], color="tab:gray", lw=1, ls="--")
ax[1].axvline(0, color="k", lw=.8); ax[1].set_title("net R per trade (dashed: random baselines)"); ax[1].set_xlabel("net R")
fig.tight_layout(); fig.savefig(E.ROOT / "data" / "foundry" / "indicator_zoo.png", dpi=110)
print("chart -> indicator_zoo.png")
