"""News batch N (docs/HYPOTHESIS_BATCH_NEWS_PREREG.md), run after the operator allowed the downloads (2026-10-01).
Primaries N2 GPR spike -> short 20 D1; N3 GPR regime -> long blocks; N4 EPU / TPU spike -> long 5 D1; N6 Trump keyword posts -> 12 H1 (DEV sign).
Read-outs N1 / N5: weekend GPR change and weekend post counts vs the Monday gap. Usage: python research/hyp/news_run.py"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import batch1 as B1  # noqa: E402
import batch2 as B2  # noqa: E402
import batch3 as B3  # noqa: E402
import batch5 as B5  # noqa: E402
import macro_data as MD  # noqa: E402

KEYWORDS = ("tariff", "china", "fed ", "federal reserve", "powell", " war", "iran", "russia", "israel")
TRUMP = {"DEV": ("2017-01-20", "2021-01-09"), "CHECK": ("2025-01-20", "2026-10-01")}


def spike_ends(df, col, q, n=750, minn=250):
    thr = B2.causal_q(df[col].to_numpy(float), q, n=n, minn=minn)
    m = np.isfinite(thr) & (df[col].to_numpy(float) >= thr)
    return df.avail.to_numpy(np.int64)[m]


def rule_N3(M, g):
    D = M["D1"]
    m30 = g.GPRD.rolling(30, min_periods=30).mean(); med = m30.rolling(250, min_periods=250).median()
    av = g.avail.to_numpy(np.int64)
    e_list = []
    for e in range(0, len(D.t) - 22, 21):
        j = int(np.searchsorted(av, D.t[e], side="right")) - 1
        if j >= 0 and np.isfinite(med.iloc[j]) and m30.iloc[j] > med.iloc[j]:
            e_list.append(e)
    e = np.array(e_list, int)
    return D, dict(e=e, d=np.ones(len(e)), stop=3 * D.atr[e], tgt=np.full(len(e), np.nan), last=e + 20)


def rule_N6(M, sign, pt):
    H = M["H1"]
    e = np.searchsorted(H.t, pt + 1, side="left")
    ok = e < len(H.t) - 13
    e = e[ok]; ok2 = (H.t[e] - pt[ok]) <= 3 * 3600                                # the market opened within 3 h of the post
    e = np.unique(e[ok2])
    return H, dict(e=e, d=float(sign) * np.ones(len(e)), stop=1.5 * H.atr[e], tgt=np.full(len(e), np.nan), last=e + 11)


def eval_periods(M, build, hold, k_stop, periods):
    B, ev = build(M)
    tr = B1.simulate_events(B, M["sym"], **ev)
    out = {}
    for p, (a, b) in periods.items():
        S, N, sub = B1.weekly(tr, M["cuts"], a, b)
        m, pv = B1.boot_p(S, N)
        share = {1.0: float((sub.d > 0).mean()) if len(sub) else 0.0, -1.0: float((sub.d < 0).mean()) if len(sub) else 0.0}
        ctl = B2.control(M, B, hold, k_stop, a, b, share) if len(sub) else float("nan")
        out[p] = dict(**B1.summarize(sub), p=pv, control_R=ctl, excess=float(sub.R.mean() - ctl) if len(sub) else float("nan"))
    return out


def weekend_readouts(M, g, posts):
    H = M["H1"]; iw = np.flatnonzero(B1.weekend_after(H.t, 3600)); iw = iw[iw + 1 < len(H.t)]
    gap = (H.o[iw + 1] / H.c[iw] - 1) * 1e4
    fri = pd.to_datetime(H.t[iw], unit="s").normalize()
    gd = g.set_index("date").GPRD
    rows = []
    for f, gp in zip(fri, gap):
        wkd = gd.reindex([f + pd.Timedelta(days=1), f + pd.Timedelta(days=2)]).mean()
        wk = gd.reindex(pd.date_range(f - pd.Timedelta(days=4), f)).mean()
        n_posts = int(((posts.t >= int((f + pd.Timedelta(days=1)).timestamp())) & (posts.t < int((f + pd.Timedelta(days=3)).timestamp()))).sum())
        rows.append(dict(fri=f, gap=gp, dg=wkd - wk, posts=n_posts))
    X = pd.DataFrame(rows)
    X["dg_z"] = (X.dg - X.dg.rolling(52, min_periods=26).mean().shift(1)) / X.dg.rolling(52, min_periods=26).std().shift(1)
    X["p_z"] = (X.posts - X.posts.rolling(52, min_periods=26).mean().shift(1)) / X.posts.rolling(52, min_periods=26).std().shift(1)
    res = {}
    for nm, col, m in (("N1 weekend GPR change", "dg_z", X.dg_z.notna()), ("N5 weekend Trump posts", "p_z", X.p_z.notna() & (X.fri >= "2017-01-20"))):
        x = X[m]
        c1 = float(np.corrcoef(x[col], x.gap)[0, 1]); c2 = float(np.corrcoef(x[col], x.gap.abs())[0, 1])
        hi = x[x[col] > (1 if col == "dg_z" else 2)]
        res[nm] = dict(n=int(len(x)), corr_gap=c1, corr_absgap=c2, n_high=int(len(hi)), absgap_high=float(hi.gap.abs().mean()) if len(hi) else float("nan"),
                       absgap_all=float(x.gap.abs().mean()), gap_high=float(hi.gap.mean()) if len(hi) else float("nan"))
        r = res[nm]
        print(f"  {M['sym']} {nm}: n {r['n']}, corr with gap {r['corr_gap']:+.3f}, with |gap| {r['corr_absgap']:+.3f}; weekends above the threshold "
              f"{r['n_high']}: mean |gap| {r['absgap_high']:.1f} bp vs all {r['absgap_all']:.1f} bp, mean gap {r['gap_high']:+.1f} bp")
    return res


def main():
    t0 = time.time()
    Gd = B5.light_gold(); Sv = B5.light_silver()
    g = MD.gprd(); ep = MD.fred("USEPUINDXD").rename(columns={"value": "EPU"}); tp = MD.tpu()
    posts = MD.trump_posts()
    kw = posts[posts.text.apply(lambda s: any(k in s for k in KEYWORDS))]
    print(f"data: GPRD {len(g):,} days, EPU {len(ep):,}, TPU {len(tp):,}, posts {len(posts):,} ({len(kw):,} with keywords) ({time.time() - t0:.0f}s)")
    res = {}
    e2 = spike_ends(g, "GPRD", 0.99)
    res["N2"] = B3.evaluate(Gd, Sv, lambda M: B2.daily_rule(M, e2, -np.ones(len(e2)), 20, 3), 20, 3)
    res["N3"] = B3.evaluate(Gd, Sv, lambda M: rule_N3(M, g), 21, 3)
    e4 = np.unique(np.r_[spike_ends(ep, "EPU", 0.975), spike_ends(tp, "TPU", 0.975)])
    res["N4"] = B3.evaluate(Gd, Sv, lambda M: B2.daily_rule(M, e4, np.ones(len(e4)), 5, 2), 5, 2)
    pt = kw.t.to_numpy(np.int64)
    best = None
    for s in (1, -1):
        r = eval_periods(Gd, lambda M, s=s: rule_N6(M, s, pt), 12, 1.5, {"DEV": TRUMP["DEV"]})
        if best is None or r["DEV"]["mean_R"] > best[1]["DEV"]["mean_R"]:
            best = (s, r)
    s6 = best[0]
    r6 = eval_periods(Gd, lambda M: rule_N6(M, s6, pt), 12, 1.5, TRUMP)
    r6.update(eval_periods(Sv, lambda M: rule_N6(M, s6, pt), 12, 1.5, {"SILVER": ("2017-01-20", "2026-09-25")}))
    r6["DEV"]["p"] = min(1.0, 2 * r6["DEV"]["p"]); r6["sign"] = s6
    res["N6"] = r6
    order = ["N2", "N3", "N4", "N6"]
    pdev = np.array([res[h]["DEV"]["p"] for h in order], float)
    rej = np.zeros(4, bool)
    for r_, j in enumerate(np.argsort(pdev)):
        if pdev[j] <= 0.05 / (4 - r_):
            rej[j] = True
        else:
            break
    print("\nNews batch (net R per trade after cost and swap; DEV Holm over 4; control = same-direction random timing):")
    print(f"{'hyp':<4s} {'period':<7s} {'n':>5s} {'meanR':>8s} {'grossR':>8s} {'win':>5s} {'totalR':>8s} {'p':>6s} {'ctlR':>7s} {'excess':>7s}")
    for j, h in enumerate(order):
        r = res[h]
        for p in ("DEV", "CHECK", "SILVER"):
            x = r[p]
            print(f"{h:<4s} {p:<7s} {x['n']:5d} {x['mean_R']:+8.3f} {x['mean_gross_R']:+8.3f} {x['win']:5.2f} {x['total_R']:+8.1f} {x['p']:6.3f} "
                  f"{x['control_R']:+7.3f} {x['excess']:+7.3f}")
        c, s = r["CHECK"], r["SILVER"]
        r["PASS"] = bool(rej[j] and c["mean_R"] > 0 and c["p"] <= 0.05 and c["excess"] > 0 and s["mean_R"] > 0 and s["p"] <= 0.10)
        print(f"     -> DEV Holm {'reject' if rej[j] else 'keep H0'}; {'PASS' if r['PASS'] else 'FAIL'}" + (f" (sign {r['sign']:+d})" if "sign" in r else ""))
    print("\nweekend risk read-outs (descriptive):")
    res["readouts"] = {"gold": weekend_readouts(Gd, g, posts), "silver": weekend_readouts(Sv, g, posts)}
    (B1.OUT / "news_batch.json").write_text(json.dumps(res, indent=1, default=float))
    print(f"-> {B1.OUT / 'news_batch.json'} ({time.time() - t0:.0f}s)")


if __name__ == "__main__":
    main()
