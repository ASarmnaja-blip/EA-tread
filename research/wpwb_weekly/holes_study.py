"""Where the risk frame still leaks, measured on data already held (2026-09-29).

Operator: volatile periods are where losses are largest; read every trace to
close that hole, and find holes not yet closed. DEVELOPMENT / DESCRIPTIVE on
2021-07..2026-09 (a period already used for volatility work); anything found
here must pass the Outlook pre-registration and forward weeks before use.

Part A — onset early warning. Population: weeks whose PREVIOUS week was not
volatile. Positive = the week turns HIGH/EXTREME (an episode onset). For each
pre-declared trace (T1..T12, all known at the Friday cut) report AUC with a
bootstrap 90% interval, and hits / false alarms when alarming on the top 20%.
Part B — intraweek blow-up: after Monday and Tuesday, how much of a volatile
week's movement is still to come, and does early-week RV flag it?
Part C — weekend gaps: Friday last close to the next first H1 open.
Part D — spread at USD HIGH releases vs normal (Exness M5 spread, 2023-09..).
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import bars as BR  # noqa: E402
import vol as V  # noqa: E402

sys.path.insert(0, str(BR.ROOT / "research" / "pilot"))
import calendar_feed  # noqa: E402

OUT = BR.WEEKLY_DIR / "holes_study.xlsx"
RNG = np.random.default_rng(20260929)
KEY = ("Fed Interest Rate Decision", "Nonfarm Payrolls", "CPI m/m", "Core PCE Price Index m/m")


def auc(score, y):
    s, y = np.asarray(score, float), np.asarray(y, bool)
    ok = np.isfinite(s)
    s, y = s[ok], y[ok]
    if y.sum() == 0 or (~y).sum() == 0:
        return np.nan, np.nan, np.nan, 0
    r = pd.Series(s).rank().to_numpy()
    a = (r[y].sum() - y.sum() * (y.sum() + 1) / 2) / (y.sum() * (~y).sum())
    bs = []
    idx = np.arange(len(s))
    for _ in range(2000):
        b = RNG.choice(idx, len(idx))
        yb, sb = y[b], s[b]
        if yb.sum() == 0 or (~yb).sum() == 0:
            continue
        rb = pd.Series(sb).rank().to_numpy()
        bs.append((rb[yb].sum() - yb.sum() * (yb.sum() + 1) / 2) / (yb.sum() * (~yb).sum()))
    return a, np.percentile(bs, 5), np.percentile(bs, 95), int(y.sum())


def weekly_rv_of(npz, cuts):
    z = np.load(npz)
    s = pd.Series(z["c"], index=pd.to_datetime(z["t"], unit="s")).resample("1h").last().dropna()
    t = s.index.astype("datetime64[s]").astype(np.int64).to_numpy()
    rv, _, _, n = V.weekly_rv(t, s.to_numpy(), s.to_numpy(), s.to_numpy(), cuts)
    rv[n < 50] = np.nan
    return rv


def main() -> int:
    m = BR.market(BR.load_bars(frozen=False))
    cuts = BR.cuts_between(m, BR.FIRST_CUT, 10 ** 12)
    rv, rng, ret, n = V.weekly_rv(m.t, m.c, m.h, m.l, cuts)
    f = V.ewma_forecast(rv)
    med = V.past_median52(rv)
    lab = np.array([V.label(rv[k] / med[k])[1] if np.isfinite(med[k]) else "U" for k in range(len(rv))])
    hi = np.isin(lab, ["HIGH", "EXTREME"])
    close_t = m.t + 3600
    lr = np.r_[np.nan, np.diff(np.log(m.c))]

    # ---------------- traces at cut k (describe week k, known before it) --------
    gvz = pd.read_csv(BR.ROOT / "data" / "external" / "GVZ_History.csv")
    gvz["d"] = pd.to_datetime(gvz.DATE, format="%m/%d/%Y")
    gvz = gvz.set_index("d").GVZ.astype(float)
    cal = calendar_feed.load_calendar(str(BR.ROOT / "data" / "calendar.csv"))
    key = cal[(cal.currency == "USD") & cal.event.isin(KEY)]
    fresh = BR.ROOT / "data" / "fresh"
    x_rv = {nm: weekly_rv_of(fresh / f"{nm}_M5.npz", cuts - BR.WEEK) for nm in ("DXY", "US500", "XAGUSD")}
    rows = []
    for k in range(53, len(cuts)):
        c = int(cuts[k])
        prev = k - 1
        # T3: Thursday+Friday share of last week's variance, scaled to a full week
        use = (close_t > c - BR.WEEK) & (close_t <= c)
        late = use & (close_t > c - 2 * 86400 - 3600)
        v_all = np.nansum(lr[use] ** 2); v_late = np.nansum(lr[late] ** 2)
        g_hist = gvz[gvz.index < pd.Timestamp(c, unit="s").normalize() - pd.Timedelta(hours=0)]
        g_hist = g_hist[g_hist.index <= pd.Timestamp(c, unit="s").normalize() - pd.Timedelta(days=1)]
        g_now = g_hist.iloc[-1] if len(g_hist) else np.nan
        g_prev = g_hist[g_hist.index <= g_hist.index[-1] - pd.Timedelta(days=6)].iloc[-1] if len(g_hist) > 10 else np.nan
        g_med = g_hist.iloc[-260:].median() if len(g_hist) > 100 else np.nan
        w = (m.t >= c - 52 * BR.WEEK) & (m.t < c)
        hi52 = m.h[w].max(); last_c = m.c[np.flatnonzero(m.t < c)[-1]]
        nxt = key[(key.epoch > c) & (key.epoch <= c + BR.WEEK)]
        rows.append({
            "cut": pd.Timestamp(c, unit="s"), "prev_hi": bool(hi[prev]), "onset": bool(hi[k] and not hi[prev]),
            "vol_next": bool(hi[k]),
            "T1_ewma_ratio": f[k] / med[k],
            "T2_lastweek_ratio": rv[prev] / med[k],
            "T3_late_week_accel": (v_late / max(v_all, 1e-12)) / (2 / 5),
            "T4_gvz_level_ratio": g_now / g_med,
            "T5_gvz_1w_change": g_now / g_prev - 1 if np.isfinite(g_prev) else np.nan,
            "T6_gvz_premium": (g_now / 100) ** 2 / 52 * 1e8 / rv[prev],
            "T7_key_news_next": int(nxt.event.nunique()) if c >= int(key.epoch.min()) - BR.WEEK else np.nan,
            "T8_dxy_rv_ratio": x_rv["DXY"][k] / np.nanmedian(x_rv["DXY"][max(0, k - 52):k]) if np.isfinite(x_rv["DXY"][k]) else np.nan,
            "T9_us500_rv_ratio": x_rv["US500"][k] / np.nanmedian(x_rv["US500"][max(0, k - 52):k]) if np.isfinite(x_rv["US500"][k]) else np.nan,
            "T10_xag_rv_ratio": x_rv["XAGUSD"][k] / np.nanmedian(x_rv["XAGUSD"][max(0, k - 52):k]) if np.isfinite(x_rv["XAGUSD"][k]) else np.nan,
            "T11_range_expansion": rng[prev] / np.sqrt(rv[prev]),
            "T12_near_52w_high": last_c / hi52,
        })
    tr = pd.DataFrame(rows)
    pop = tr[~tr.prev_hi]
    A = []
    for col in [c for c in tr.columns if c.startswith("T")]:
        a, lo, up, npos = auc(pop[col], pop.onset)
        s = pop[col]; ok = s.notna()
        thr = s[ok].quantile(0.8) if ok.sum() else np.nan
        alarm = s >= thr
        A.append({"trace": col, "weeks": int(ok.sum()), "onsets": npos,
                  "AUC": round(a, 3), "AUC 90% lo": round(lo, 3), "AUC 90% hi": round(up, 3),
                  "hits@top20%": int((alarm & pop.onset).sum()), "false alarms@top20%": int((alarm & ~pop.onset).sum())})
    A = pd.DataFrame(A)

    # ---------------- B: intraweek -------------------------------------------------
    B = []
    for k in range(53, len(cuts)):
        c = int(cuts[k])
        use = (close_t > c) & (close_t <= c + BR.WEEK)
        idx = np.flatnonzero(use)
        if len(idx) < 60:
            continue
        day = (m.t[idx] - c) // 86400
        # trading days since cut: Sunday evening + Monday ~ day 1-2
        early = idx[m.t[idx] < c + 3 * 86400 + 2 * 3600]           # Sunday reopen through Monday 24:00 UTC
        v_early = np.nansum(lr[early] ** 2); v_all = np.nansum(lr[idx] ** 2)
        B.append({"cut": pd.Timestamp(c, unit="s"), "volatile": bool(hi[k]),
                  "early_share": v_early / max(v_all, 1e-12),
                  "early_vs_forecast": (v_early / max(len(early), 1) * len(idx)) / f[k]})
    B = pd.DataFrame(B)
    bv = B[B.volatile]
    b_auc = auc(B.early_vs_forecast, B.volatile)

    # ---------------- C: weekend gaps ----------------------------------------------
    gaps = []
    for c in cuts[1:]:
        before = np.flatnonzero(m.t < c)
        after = np.flatnonzero(m.t >= c)
        if not len(before) or not len(after):
            continue
        i, j = before[-1], after[0]
        if m.t[j] - m.t[i] < 24 * 3600:
            continue
        gaps.append({"cut": pd.Timestamp(int(c), unit="s"),
                     "gap_bp": (m.o[j] / m.c[i] - 1) * 1e4})
    C = pd.DataFrame(gaps)
    C["abs"] = C.gap_bp.abs()

    # ---------------- D: spread at news ---------------------------------------------
    z = np.load(BR.ROOT / "data" / "fresh" / "XAUUSD_M5.npz")
    sp = pd.Series(z["sp"], index=pd.to_datetime(z["t"], unit="s"))
    hi_ev = cal[(cal.currency == "USD") & (cal.importance == "HIGH")]
    ev_t = pd.to_datetime(hi_ev.epoch.unique(), unit="s")
    ev_t = ev_t[(ev_t >= sp.index[0]) & (ev_t <= sp.index[-1])]
    at = sp.reindex(ev_t.floor("5min")).dropna()
    D = {"normal_median_spread": float(sp.median()), "normal_p95": float(sp.quantile(.95)),
         "news_bar_median": float(at.median()), "news_bar_p95": float(at.quantile(.95)),
         "news_bar_max": float(at.max()), "n_news": int(len(at)),
         "rollover_21utc_median": float(sp[sp.index.hour == 21].median()),
         "rollover_21utc_p95": float(sp[sp.index.hour == 21].quantile(.95))}

    with pd.ExcelWriter(OUT) as xw:
        A.to_excel(xw, sheet_name="A onset traces", index=False)
        tr.to_excel(xw, sheet_name="A weekly traces", index=False)
        B.to_excel(xw, sheet_name="B intraweek", index=False)
        C.sort_values("abs", ascending=False).to_excel(xw, sheet_name="C weekend gaps", index=False)
        pd.DataFrame([D]).to_excel(xw, sheet_name="D news spread", index=False)
    pd.set_option("display.width", 220)
    print(f"A. onset early warning: {int(pop.onset.sum())} onsets among {len(pop)} at-risk weeks")
    print(A.to_string(index=False))
    print(f"\nB. intraweek: volatile weeks {len(bv)}; median share of the week's variance realised "
          f"by Monday close {bv.early_share.median():.0%} (all weeks {B.early_share.median():.0%}); "
          f"AUC of early RV vs forecast for 'this week is volatile' {b_auc[0]:.3f} [{b_auc[1]:.3f}, {b_auc[2]:.3f}]")
    print(f"\nC. weekend gaps: n {len(C)}, median |gap| {C['abs'].median():.1f} bp, p95 {C['abs'].quantile(.95):.1f} bp, "
          f"max {C['abs'].max():.1f} bp; top 5:")
    print(C.sort_values("abs", ascending=False).head(5).to_string(index=False))
    print(f"\nD. spread ($): {D}")
    print(f"\nsaved {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
