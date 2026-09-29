"""Batch 6: WPWB Champion/Challenger selector, evaluated walk-forward (docs/FOUNDRY_LEDGER.md).
At every Friday 22:15 UTC cut the selector ranks a fixed menu of setup variants by their
trailing performance on trades that had EXITED before the cut, picks the champion if its
score clears a bar, and trades the champion's entries during the coming week; otherwise
NO TRADE. The procedure (not a setup) is the candidate.
Usage: python research/foundry/selector.py <batch_name> <menu_fn>"""
from __future__ import annotations

import json
import math
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import engine as E  # noqa: E402
import families as FAM  # noqa: E402
from run_batch import OUT, STATE, TRIALS, state  # noqa: E402

WEEK = E.WEEK


def menu_trades(menu_fn):
    H, D, cuts, cell = E.load()
    cbH = np.where(H.week >= 0, cell[np.clip(H.week, 0, len(cell) - 1)], "")
    cbD = np.where(D.week >= 0, cell[np.clip(D.week, 0, len(cell) - 1)], "")
    specs = getattr(FAM, menu_fn)(H, D)
    T = []
    for vi, sp in enumerate(specs):
        B, cb = (H, cbH) if sp.tf == "H1" else (D, cbD)
        g, ex = E.simulate(B, sp.ent, sp.dirs, sp.stop, sp.tgt, sp.last, sp.eprice)
        ep = sp.eprice if sp.eprice is not None else B.o[sp.ent]
        sb = sp.stop / ep * 1e4
        net = g - E.COST_BP
        T.append(pd.DataFrame(dict(v=vi, name=sp.name, et=B.t[sp.ent], xt=B.t[ex] + B.step, net=net, R=net / sb,
                                   stress=g - E.STRESS_BP, cell=cb[sp.ent])))
    T = pd.concat(T, ignore_index=True)
    T["wk"] = np.searchsorted(cuts, T.et.to_numpy(), side="left") - 1
    T = T[T.wk >= 0]
    return T, cuts, cell, [s.name for s in specs]


def run_selector(T, cuts, cell, nv, L, sbar, regime):
    """Return the selector's trade rows and the equal-weight-menu control per week."""
    out = []
    vol = np.array([c.split("/")[0] if c else "" for c in cell], object)
    et, xt, v, R = T.et.to_numpy(), T.xt.to_numpy(), T.v.to_numpy(), T.R.to_numpy()
    tvol = np.array([c.split("/")[0] if c else "" for c in T.cell], object)
    by_wk = T.groupby("wk").indices
    order = np.argsort(xt); xs = xt[order]
    for k in range(len(cuts)):
        if k not in by_wk:
            continue
        cut = cuts[k]
        lo = np.searchsorted(xs, cut - L * WEEK, side="right"); hi = np.searchsorted(xs, cut, side="right")
        idx = order[lo:hi]
        if regime:
            if not vol[k]:
                continue
            idx = idx[tvol[idx] == vol[k]]
        if len(idx) == 0:
            continue
        s = pd.DataFrame(dict(v=v[idx], R=R[idx])).groupby("v").R.agg(["sum", "count"])
        s = s[s["count"] >= 10]
        if not len(s):
            continue
        score = s["sum"] / np.sqrt(s["count"])
        champ = int(score.idxmax()); best = float(score.max())
        wk_rows = T.iloc[by_wk[k]]
        ctrl = wk_rows.groupby("v").R.mean().mean()          # equal-weight menu this week
        if best < sbar:
            continue
        sel = wk_rows[wk_rows.v == champ]
        for _, r in sel.iterrows():
            out.append(dict(wk=k, et=r.et, v=champ, name=r["name"], net=r.net, R=r.R, stress=r.stress, ctrl=ctrl, score=best))
    return pd.DataFrame(out)


def stats(S, period):
    a, b = E.PERIODS[period]
    d = pd.to_datetime(S.et, unit="s")
    m = (d >= a) & (d < b)
    x = S[m]
    if len(x) < 20:
        return dict(period=period, n=len(x))
    wk = x.wk.to_numpy()
    exc = (x.R - x.ctrl).to_numpy()
    yr = x.groupby(pd.to_datetime(x.et, unit="s").dt.year).R.mean()
    return dict(period=period, n=len(x), weeks_traded=int(x.wk.nunique()), net=x.net.mean(), net_stress=x.stress.mean(),
                net_R=x.R.mean(), t_R=E.cluster_t(x.R.to_numpy(), wk), excess_R=np.nanmean(exc),
                t_excess_R=E.cluster_t(exc[np.isfinite(exc)], wk[np.isfinite(exc)]), yr_pos_R=float((yr > 0).mean()),
                champions=int(x.v.nunique()), R_per_year=x.R.sum() / max(len(yr), 1))


def main(batch, menu_fn) -> int:
    os.chdir(E.ROOT)
    st = state()
    if batch in st["batches"]:
        print("batch already run"); return 1
    T, cuts, cell, names = menu_trades(menu_fn)
    print(f"menu {menu_fn}: {len(names)} variants, {len(T):,} trades")
    grid = [(L, sb, rg) for rg in (False, True) for L in (26, 52, 104) for sb in (1.0, 2.0)]
    rows, keep = [], {}
    for L, sb, rg in grid:
        name = f"SELECT_L{L}_s{sb}{'_regime' if rg else ''}"
        S = run_selector(T, cuts, cell, len(names), L, sb, rg)
        keep[name] = S
        r = stats(S, "DISC"); r["cand"] = name
        rows.append(r)
    R = pd.DataFrame(rows)
    st["disc_candidates"] += len(R)
    R["pass_disc"] = [bool(r.get("n", 0) >= 60 and r["net"] > 0 and r["net_R"] > 0 and r["excess_R"] > 0 and r["t_R"] >= 3.0
                           and r["t_excess_R"] >= 2.0 and r["yr_pos_R"] >= 0.6) if r.get("n", 0) >= 20 else False
                      for r in R.to_dict("records")]
    pd.set_option("display.width", 250); pd.set_option("display.max_columns", 30)
    print(R.round(3).to_string(index=False))
    surv = R[R.pass_disc].sort_values("t_R", ascending=False)
    out = [R.assign(stage="DISC", batch=batch)]
    for _, r in surv.iterrows():
        st["m_val"] += 1; M = st["m_val"]
        v = stats(keep[r.cand], "VAL"); v["cand"] = r.cand
        v["p_net"] = E.one_sided_p(v.get("t_R", np.nan)); v["M"] = M
        v["pass_val"] = bool(v.get("n", 0) >= 20 and v["net"] > 0 and v["net_R"] > 0 and v["excess_R"] > 0 and v["p_net"] < 0.05 / M)
        print("VAL", {k: (round(x, 4) if isinstance(x, float) else x) for k, x in v.items()})
        out.append(pd.DataFrame([v]).assign(stage="VAL", batch=batch))
        if v["pass_val"]:
            st["hold_looks"] += 1; alpha = 0.05 * 2 ** -st["hold_looks"]
            h = stats(keep[r.cand], "HOLD"); h["cand"] = r.cand
            h["p_net"] = E.one_sided_p(h.get("t_R", np.nan)); h["alpha"] = alpha
            h["pass_hold"] = bool(h.get("n", 0) >= 20 and h["net"] > 0 and h["net_stress"] > 0 and h["net_R"] > 0
                                  and h["excess_R"] > 0 and h["p_net"] < alpha)
            print("HOLD", {k: (round(x, 4) if isinstance(x, float) else x) for k, x in h.items()})
            out.append(pd.DataFrame([h]).assign(stage="HOLD", batch=batch))
    pd.concat(out).to_csv(TRIALS, mode="a", header=False, index=False)
    pd.concat(out).to_csv(OUT / f"{batch}_selector.csv", index=False)
    for nm, S in keep.items():
        S.to_csv(OUT / f"{batch}_{nm}_trades.csv", index=False)
    st["batches"].append(batch)
    STATE.write_text(json.dumps(st, indent=1))
    # descriptive only: which champions the selector used in DISC
    best = R.sort_values("t_R", ascending=False).iloc[0].cand
    S = keep[best]
    d = pd.to_datetime(S.et, unit="s")
    print(f"\nchampions used by {best} in DISC (trades):")
    print(S[d < "2015-01-01"].name.value_counts().head(8).to_string())
    return 0




# ------------------------------------------------------------------ batch 7: top-quintile portfolio selector
MIN_COUNT = 10
TOP_FRAC = 0.2


def run_portfolio(T, cuts, L, need_pos):
    """At each cut: score all variants on trades exited in the last L weeks (count >= 10);
    hold the top 20 % (optionally only those with score > 0) for the coming week."""
    out = []
    et, xt, v, R = T.et.to_numpy(), T.xt.to_numpy(), T.v.to_numpy(), T.R.to_numpy()
    by_wk = T.groupby("wk").indices
    order = np.argsort(xt); xs = xt[order]
    for k in range(len(cuts)):
        if k not in by_wk:
            continue
        cut = cuts[k]
        lo = np.searchsorted(xs, cut - L * WEEK, side="right"); hi = np.searchsorted(xs, cut, side="right")
        idx = order[lo:hi]
        if len(idx) == 0:
            continue
        s = pd.DataFrame(dict(v=v[idx], R=R[idx])).groupby("v").R.agg(["sum", "count"])
        s = s[s["count"] >= MIN_COUNT]
        if len(s) < 10:
            continue
        score = (s["sum"] / np.sqrt(s["count"])).sort_values(ascending=False)
        top = score.iloc[:max(1, int(np.ceil(TOP_FRAC * len(score))))]
        if need_pos:
            top = top[top > 0]
        wk_rows = T.iloc[by_wk[k]]
        ctrl = wk_rows.groupby("v").R.mean().mean()
        sel = wk_rows[wk_rows.v.isin(top.index)]
        for r in sel.itertuples():
            out.append(dict(wk=k, et=r.et, v=r.v, name=r.name, net=r.net, R=r.R, stress=r.stress, ctrl=ctrl, score=float(top.iloc[0])))
    return pd.DataFrame(out)


def main_portfolio(batch, menu_fn) -> int:
    os.chdir(E.ROOT)
    st = state()
    if batch in st["batches"]:
        print("batch already run"); return 1
    T, cuts, cell, names = menu_trades(menu_fn)
    rows, keep = [], {}
    for L in (26, 52):
        for need_pos in (False, True):
            name = f"TOPQ_L{L}{'_pos' if need_pos else ''}"
            S = run_portfolio(T, cuts, L, need_pos)
            keep[name] = S
            r = stats(S, "DISC"); r["cand"] = name
            rows.append(r)
    R = pd.DataFrame(rows)
    st["disc_candidates"] += len(R)
    R["pass_disc"] = [bool(r.get("n", 0) >= 60 and r["net"] > 0 and r["net_R"] > 0 and r["excess_R"] > 0 and r["t_R"] >= 3.0
                           and r["t_excess_R"] >= 2.0 and r["yr_pos_R"] >= 0.6) for r in R.to_dict("records")]
    pd.set_option("display.width", 250); pd.set_option("display.max_columns", 30)
    print(R.round(3).to_string(index=False))
    out = [R.assign(stage="DISC", batch=batch)]
    for _, r in R[R.pass_disc].sort_values("t_R", ascending=False).iterrows():
        st["m_val"] += 1; M = st["m_val"]
        v = stats(keep[r.cand], "VAL"); v["cand"] = r.cand
        v["p_net"] = E.one_sided_p(v.get("t_R", np.nan)); v["M"] = M
        v["pass_val"] = bool(v.get("n", 0) >= 20 and v["net"] > 0 and v["net_R"] > 0 and v["excess_R"] > 0 and v["p_net"] < 0.05 / M)
        print("VAL", {k: (round(x, 4) if isinstance(x, float) else x) for k, x in v.items()})
        out.append(pd.DataFrame([v]).assign(stage="VAL", batch=batch))
        if v["pass_val"]:
            st["hold_looks"] += 1; alpha = 0.05 * 2 ** -st["hold_looks"]
            h = stats(keep[r.cand], "HOLD"); h["cand"] = r.cand
            h["p_net"] = E.one_sided_p(h.get("t_R", np.nan)); h["alpha"] = alpha
            h["pass_hold"] = bool(h.get("n", 0) >= 20 and h["net"] > 0 and h["net_stress"] > 0 and h["net_R"] > 0
                                  and h["excess_R"] > 0 and h["p_net"] < alpha)
            print("HOLD", {k: (round(x, 4) if isinstance(x, float) else x) for k, x in h.items()})
            out.append(pd.DataFrame([h]).assign(stage="HOLD", batch=batch))
    pd.concat(out).to_csv(TRIALS, mode="a", header=False, index=False)
    for nm, S in keep.items():
        S.to_csv(OUT / f"{batch}_{nm}_trades.csv", index=False)
    st["batches"].append(batch)
    STATE.write_text(json.dumps(st, indent=1))
    return 0





# ------------------------------------------------------------------ batch 8: equal risk per selected variant per week
def variant_week(S):
    """Collapse a portfolio trade list to one unit per (week, variant): R = mean R of that
    variant's trades that week (1R risk budget per selected variant per week)."""
    g = S.groupby(["wk", "v"]).agg(et=("et", "min"), net=("net", "mean"), R=("R", "mean"), stress=("stress", "mean"),
                                   ctrl=("ctrl", "first"), score=("score", "first"), name=("name", "first")).reset_index()
    return g


def main_ew(batch, menu_fn) -> int:
    os.chdir(E.ROOT)
    st = state()
    if batch in st["batches"]:
        print("batch already run"); return 1
    global MIN_COUNT, TOP_FRAC
    if menu_fn == "menu3":
        MIN_COUNT = 5
    T, cuts, cell, names = menu_trades(menu_fn)
    rows, keep = [], {}
    if batch == "batch17":
        volk = np.array([c.split("/")[0] if c else "" for c in cell], object)
        S = variant_week(run_portfolio_shrunk(T, cuts, names))
        S = S[np.isin(volk[S.wk.to_numpy()], ["NORMAL", "HIGH"])]
        keep["TOPQ_SHRUNK_MULTI_EW_NOTCALM"] = S
        r = stats(S, "DISC"); r["cand"] = "TOPQ_SHRUNK_MULTI_EW_NOTCALM"
        rows.append(r)
    if batch == "batch21":
        volk = np.array([c.split("/")[0] if c else "" for c in cell], object)
        S = variant_week(run_portfolio(T, cuts, 104, False))
        S = S[np.isin(volk[S.wk.to_numpy()], ["NORMAL", "HIGH"])]
        S = weekly_budget(S)
        keep["TOPQ_L104_WEEKBUDGET_NOTCALM"] = S
        r = stats(S, "DISC"); r["cand"] = "TOPQ_L104_WEEKBUDGET_NOTCALM"
        rows.append(r)
    if batch in ("batch15", "batch16", "batch20"):
        volk = np.array([c.split("/")[0] if c else "" for c in cell], object)
        S = variant_week(run_portfolio(T, cuts, 104, False))
        S = S[np.isin(volk[S.wk.to_numpy()], ["NORMAL", "HIGH"])]
        keep["TOPQ_L104_EW_NOTCALM"] = S
        r = stats(S, "DISC"); r["cand"] = "TOPQ_L104_EW_NOTCALM"
        rows.append(r)
    if batch == "batch14":
        for frac in (0.10, 0.05):
            TOP_FRAC = frac
            name = f"TOP{int(frac * 100)}_L104_EW"
            S = variant_week(run_portfolio(T, cuts, 104, False))
            keep[name] = S
            r = stats(S, "DISC"); r["cand"] = name
            rows.append(r)
        TOP_FRAC = 0.2
    grid = () if batch in ("batch14", "batch15", "batch16", "batch17", "batch20", "batch21") else ((52, True), (104, True)) if menu_fn not in ("menu1",) else ((52, True), (104, True), (104, False))
    for L, ew in grid:
        name = f"TOPQ_L{L}{'_EW' if ew else ''}"
        S = run_portfolio(T, cuts, L, False)
        if ew:
            S = variant_week(S)
        keep[name] = S
        r = stats(S, "DISC"); r["cand"] = name
        rows.append(r)
    R = pd.DataFrame(rows)
    st["disc_candidates"] += len(R)
    R["pass_disc"] = [bool(r.get("n", 0) >= 60 and r["net"] > 0 and r["net_R"] > 0 and r["excess_R"] > 0 and r["t_R"] >= 3.0
                           and r["t_excess_R"] >= 2.0 and r["yr_pos_R"] >= 0.6) for r in R.to_dict("records")]
    pd.set_option("display.width", 250); pd.set_option("display.max_columns", 30)
    print(R.round(3).to_string(index=False))
    out = [R.assign(stage="DISC", batch=batch)]
    for _, r in R[R.pass_disc].sort_values("t_R", ascending=False).iterrows():
        st["m_val"] += 1; M = st["m_val"]
        v = stats(keep[r.cand], "VAL"); v["cand"] = r.cand
        v["p_net"] = E.one_sided_p(v.get("t_R", np.nan)); v["M"] = M
        v["pass_val"] = bool(v.get("n", 0) >= 20 and v["net"] > 0 and v["net_R"] > 0 and v["excess_R"] > 0 and v["p_net"] < 0.05 / M)
        print("VAL", {k: (round(x, 4) if isinstance(x, float) else x) for k, x in v.items()})
        out.append(pd.DataFrame([v]).assign(stage="VAL", batch=batch))
        if v["pass_val"]:
            st["hold_looks"] += 1; alpha = 0.05 * 2 ** -st["hold_looks"]
            h = stats(keep[r.cand], "HOLD"); h["cand"] = r.cand
            h["p_net"] = E.one_sided_p(h.get("t_R", np.nan)); h["alpha"] = alpha
            h["pass_hold"] = bool(h.get("n", 0) >= 20 and h["net"] > 0 and h["net_stress"] > 0 and h["net_R"] > 0
                                  and h["excess_R"] > 0 and h["p_net"] < alpha)
            print("HOLD", {k: (round(x, 4) if isinstance(x, float) else x) for k, x in h.items()})
            out.append(pd.DataFrame([h]).assign(stage="HOLD", batch=batch))
    pd.concat(out).to_csv(TRIALS, mode="a", header=False, index=False)
    for nm, S in keep.items():
        S.to_csv(OUT / f"{batch}_{nm}_units.csv", index=False)
    st["batches"].append(batch)
    STATE.write_text(json.dumps(st, indent=1))
    return 0


def nominate_ew(tag, L, menu="menu1") -> int:
    """Amendment 2 nomination for an equal-risk top-quintile selector (VAL, then HOLD if passed)."""
    os.chdir(E.ROOT)
    st = state()
    if tag in st.get("nominated", []):
        print("already nominated"); return 1
    T, cuts, cell, names = menu_trades(menu)
    S = variant_week(run_portfolio(T, cuts, L, False))
    if "NOTCALM" in tag:
        volk = np.array([c.split("/")[0] if c else "" for c in cell], object)
        S = S[np.isin(volk[S.wk.to_numpy()], ["NORMAL", "HIGH"])]
    d = stats(S, "DISC")
    assert d["t_R"] >= 2.0 and d["t_excess_R"] >= 3.0 and d["net"] > 0, d
    st["m_val"] += 1; M = st["m_val"]
    v = stats(S, "VAL"); v["p_net"] = E.one_sided_p(v["t_R"]); v["M"] = M
    v["pass_val"] = bool(v["n"] >= 20 and v["net"] > 0 and v["net_R"] > 0 and v["excess_R"] > 0 and v["p_net"] < 0.05 / M)
    rows = [dict(d, stage="DISC-nominated", cand=tag), dict(v, stage="VAL", cand=tag)]
    print("DISC", {k: (round(x, 4) if isinstance(x, float) else x) for k, x in d.items()})
    print("VAL ", {k: (round(x, 4) if isinstance(x, float) else x) for k, x in v.items()}, "threshold", round(0.05 / M, 5))
    if v["pass_val"]:
        st["hold_looks"] += 1; alpha = 0.05 * 2 ** -st["hold_looks"]
        h = stats(S, "HOLD"); h["p_net"] = E.one_sided_p(h["t_R"]); h["alpha"] = alpha
        h["pass_hold"] = bool(h["n"] >= 20 and h["net"] > 0 and h["net_stress"] > 0 and h["net_R"] > 0
                              and h["excess_R"] > 0 and h["p_net"] < alpha)
        rows.append(dict(h, stage="HOLD", cand=tag))
        print("HOLD", {k: (round(x, 4) if isinstance(x, float) else x) for k, x in h.items()})
    pd.DataFrame(rows).assign(batch=tag).to_csv(TRIALS, mode="a", header=False, index=False)
    S.to_csv(OUT / f"nominate_{tag.replace(':', '_')}_units.csv", index=False)
    st.setdefault("nominated", []).append(tag)
    STATE.write_text(json.dumps(st, indent=1))
    return 0


def run_portfolio_bar(T, cuts, L, sbar):
    """Top 20 % by trailing score, keeping only variants with score >= sbar; else NO TRADE."""
    S = run_portfolio(T, cuts, L, False)
    if not len(S):
        return S
    # recompute each selected variant's own score at its week to apply the bar
    et, xt, v, R = T.et.to_numpy(), T.xt.to_numpy(), T.v.to_numpy(), T.R.to_numpy()
    order = np.argsort(xt); xs = xt[order]
    keep = []
    for k, g in S.groupby("wk"):
        cut = cuts[k]
        lo = np.searchsorted(xs, cut - L * WEEK, side="right"); hi = np.searchsorted(xs, cut, side="right")
        idx = order[lo:hi]
        s = pd.DataFrame(dict(v=v[idx], R=R[idx])).groupby("v").R.agg(["sum", "count"])
        sc = s["sum"] / np.sqrt(s["count"])
        ok = sc[sc >= sbar].index
        keep.append(g[g.v.isin(ok)])
    return pd.concat(keep) if keep else S.iloc[:0]


def main_bar(batch, menu_fn) -> int:
    os.chdir(E.ROOT)
    st = state()
    if batch in st["batches"]:
        print("batch already run"); return 1
    T, cuts, cell, names = menu_trades(menu_fn)
    rows, keep = [], {}
    for sbar in (1.5, 2.0, 3.0):
        name = f"TOPQ_L52_EW_s{sbar}"
        S = variant_week(run_portfolio_bar(T, cuts, 52, sbar))
        keep[name] = S
        r = stats(S, "DISC"); r["cand"] = name
        rows.append(r)
    R = pd.DataFrame(rows)
    st["disc_candidates"] += len(R)
    R["pass_disc"] = [bool(r.get("n", 0) >= 60 and r["net"] > 0 and r["net_R"] > 0 and r["excess_R"] > 0 and r["t_R"] >= 3.0
                           and r["t_excess_R"] >= 2.0 and r["yr_pos_R"] >= 0.6) for r in R.to_dict("records")]
    pd.set_option("display.width", 250); pd.set_option("display.max_columns", 30)
    print(R.round(3).to_string(index=False))
    out = [R.assign(stage="DISC", batch=batch)]
    for _, r in R[R.pass_disc].sort_values("t_R", ascending=False).iterrows():
        st["m_val"] += 1; M = st["m_val"]
        v = stats(keep[r.cand], "VAL"); v["cand"] = r.cand
        v["p_net"] = E.one_sided_p(v.get("t_R", np.nan)); v["M"] = M
        v["pass_val"] = bool(v.get("n", 0) >= 20 and v["net"] > 0 and v["net_R"] > 0 and v["excess_R"] > 0 and v["p_net"] < 0.05 / M)
        print("VAL", {k: (round(x, 4) if isinstance(x, float) else x) for k, x in v.items()})
        out.append(pd.DataFrame([v]).assign(stage="VAL", batch=batch))
        if v["pass_val"]:
            st["hold_looks"] += 1; alpha = 0.05 * 2 ** -st["hold_looks"]
            h = stats(keep[r.cand], "HOLD"); h["cand"] = r.cand
            h["p_net"] = E.one_sided_p(h.get("t_R", np.nan)); h["alpha"] = alpha
            h["pass_hold"] = bool(h.get("n", 0) >= 20 and h["net"] > 0 and h["net_stress"] > 0 and h["net_R"] > 0
                                  and h["excess_R"] > 0 and h["p_net"] < alpha)
            print("HOLD", {k: (round(x, 4) if isinstance(x, float) else x) for k, x in h.items()})
            out.append(pd.DataFrame([h]).assign(stage="HOLD", batch=batch))
    pd.concat(out).to_csv(TRIALS, mode="a", header=False, index=False)
    for nm, S in keep.items():
        S.to_csv(OUT / f"{batch}_{nm}_units.csv", index=False)
    st["batches"].append(batch)
    STATE.write_text(json.dumps(st, indent=1))
    return 0


def run_portfolio_regime(T, cuts, cell, L):
    """Top 20 % where each variant is scored only on its trades from past weeks whose WPWB
    volatility class equals the class forecast for the coming week."""
    out = []
    vol = np.array([c.split("/")[0] if c else "" for c in cell], object)
    tvol = np.array([c.split("/")[0] if c else "" for c in T.cell], object)
    et, xt, v, R = T.et.to_numpy(), T.xt.to_numpy(), T.v.to_numpy(), T.R.to_numpy()
    by_wk = T.groupby("wk").indices
    order = np.argsort(xt); xs = xt[order]
    for k in range(len(cuts)):
        if k not in by_wk or not vol[k]:
            continue
        cut = cuts[k]
        lo = np.searchsorted(xs, cut - L * WEEK, side="right"); hi = np.searchsorted(xs, cut, side="right")
        idx = order[lo:hi]
        idx = idx[tvol[idx] == vol[k]]
        if len(idx) == 0:
            continue
        s = pd.DataFrame(dict(v=v[idx], R=R[idx])).groupby("v").R.agg(["sum", "count"])
        s = s[s["count"] >= MIN_COUNT]
        if len(s) < 10:
            continue
        score = (s["sum"] / np.sqrt(s["count"])).sort_values(ascending=False)
        top = score.iloc[:max(1, int(np.ceil(0.2 * len(score))))]
        wk_rows = T.iloc[by_wk[k]]
        ctrl = wk_rows.groupby("v").R.mean().mean()
        sel = wk_rows[wk_rows.v.isin(top.index)]
        for r in sel.itertuples():
            out.append(dict(wk=k, et=r.et, v=r.v, name=r.name, net=r.net, R=r.R, stress=r.stress, ctrl=ctrl, score=float(top.iloc[0])))
    return pd.DataFrame(out)


def main_regime(batch, menu_fn) -> int:
    os.chdir(E.ROOT)
    st = state()
    if batch in st["batches"]:
        print("batch already run"); return 1
    T, cuts, cell, names = menu_trades(menu_fn)
    name = "TOPQ_L104_EW_regime"
    S = variant_week(run_portfolio_regime(T, cuts, cell, 104))
    r = stats(S, "DISC"); r["cand"] = name
    st["disc_candidates"] += 1
    ok = bool(r.get("n", 0) >= 60 and r["net"] > 0 and r["net_R"] > 0 and r["excess_R"] > 0 and r["t_R"] >= 3.0
              and r["t_excess_R"] >= 2.0 and r["yr_pos_R"] >= 0.6)
    print({k: (round(x, 4) if isinstance(x, float) else x) for k, x in r.items()}, "pass_disc", ok)
    out = [pd.DataFrame([r]).assign(stage="DISC", batch=batch, pass_disc=ok)]
    if ok:
        st["m_val"] += 1; M = st["m_val"]
        v = stats(S, "VAL"); v["cand"] = name; v["p_net"] = E.one_sided_p(v["t_R"]); v["M"] = M
        v["pass_val"] = bool(v["n"] >= 20 and v["net"] > 0 and v["net_R"] > 0 and v["excess_R"] > 0 and v["p_net"] < 0.05 / M)
        print("VAL", v)
        out.append(pd.DataFrame([v]).assign(stage="VAL", batch=batch))
    pd.concat(out).to_csv(TRIALS, mode="a", header=False, index=False)
    S.to_csv(OUT / f"{batch}_{name}_units.csv", index=False)
    st["batches"].append(batch)
    STATE.write_text(json.dumps(st, indent=1))
    return 0



def run_portfolio_shrunk(T, cuts, names, Ls=(52, 104, 156), k_shrink=50.0):
    """Rank = mean over lookbacks of the rank of each variant's family-shrunk trailing mean R;
    hold the top 20 %."""
    fam = np.array([n.split("_")[0] + ("~INV" if "~INV" in n else "") + ("^x" if "^x" in n else "") for n in names], object)
    out = []
    et, xt, v, R = T.et.to_numpy(), T.xt.to_numpy(), T.v.to_numpy(), T.R.to_numpy()
    by_wk = T.groupby("wk").indices
    order = np.argsort(xt); xs = xt[order]
    for k in range(len(cuts)):
        if k not in by_wk:
            continue
        cut = cuts[k]
        ranks = []
        for L in Ls:
            lo = np.searchsorted(xs, cut - L * WEEK, side="right"); hi = np.searchsorted(xs, cut, side="right")
            idx = order[lo:hi]
            if len(idx) == 0:
                continue
            s = pd.DataFrame(dict(v=v[idx], R=R[idx])).groupby("v").R.agg(["mean", "count"])
            s = s[s["count"] >= MIN_COUNT]
            if len(s) < 10:
                continue
            f = pd.Series(fam[s.index], index=s.index)
            fm = (s["mean"] * s["count"]).groupby(f).sum() / s["count"].groupby(f).sum()
            shr = (s["count"] * s["mean"] + k_shrink * fm.reindex(f).to_numpy()) / (s["count"] + k_shrink)
            ranks.append(shr.rank(ascending=False))
        if not ranks:
            continue
        rk = pd.concat(ranks, axis=1).mean(axis=1, skipna=False).dropna().sort_values()
        top = rk.iloc[:max(1, int(np.ceil(TOP_FRAC * len(rk))))]
        wk_rows = T.iloc[by_wk[k]]
        ctrl = wk_rows.groupby("v").R.mean().mean()
        sel = wk_rows[wk_rows.v.isin(top.index)]
        for r in sel.itertuples():
            out.append(dict(wk=k, et=r.et, v=r.v, name=r.name, net=r.net, R=r.R, stress=r.stress, ctrl=ctrl, score=0.0))
    return pd.DataFrame(out)



def weekly_budget(S):
    """Fixed risk budget per week: the week's return = mean R of all selected units that week."""
    g = S.groupby("wk").agg(et=("et", "min"), net=("net", "mean"), R=("R", "mean"), stress=("stress", "mean"),
                            ctrl=("ctrl", "first"), v=("v", "nunique"), name=("name", "first")).reset_index()
    return g


if __name__ == "__main__":
    if sys.argv[1] == "nominate":
        sys.exit(nominate_ew(sys.argv[2], int(sys.argv[3]), sys.argv[4] if len(sys.argv) > 4 else "menu1"))
    mode = sys.argv[3] if len(sys.argv) > 3 else ""
    fn = {"portfolio": main_portfolio, "ew": main_ew, "bar": main_bar, "regime": main_regime}.get(mode, main)
    sys.exit(fn(sys.argv[1], sys.argv[2]))
