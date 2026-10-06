#!/usr/bin/env python3
"""Execution stress of the three H1 finalists (ledger h1_family_execution_stress).

Each finalist on the six main markets, 2011-09..2026-09, under: costs x2 / x3,
+0.05R / +0.10R a trade, stop exits 0.10R / 0.25R worse, entry one H1 bar
late, no entries from signal bars closing 20:00-23:59 UTC, without the best
5% of trades, and all of costs x2 + 0.05R + one bar late together. Then the
plan G27K #1 + all three at 0.33% each with the H1 streams fully stressed.

Usage: python3 research/g27k_dev/h1_stress.py --root <snap>
"""
import argparse
import json
import pathlib
import sys

import numpy as np
import pandas as pd

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))
import fresh_validate as FV
import h4d1_pattern_search as P
import multi_market_search as MMS
import per_market_search as PMS
import suite as SU
import tf_finalize as TF
import tf_search as TS
import walkforward_controller as W


def tstat(R):
    R = np.asarray(R, float)
    return float(R.mean() / R.std(ddof=1) * np.sqrt(len(R))) if len(R) > 2 and R.std() > 0 else float("nan")


def select(ev, c, late=False, no_rollover=False):
    """Trade rows of a pattern: optionally one bar late (the same market and
    direction row one bar later) and without signal bars closing 20-24 UTC."""
    E, feats, cats = ev.get("H1")
    R = E[f"R_{c['exit']}"]
    m = W.pmask(feats, cats, [W.parse(n) for n in c["names"]]) & (E["t"] >= TS.LO) & (E["t"] < TS.FIN)
    if no_rollover:
        hr = ((E["t"] + 3600) // 3600) % 24           # hour at which the signal bar closes
        m &= ~((hr >= 20) & (hr <= 23))
    if late:
        idx = np.flatnonzero(m)
        key = pd.Series(np.arange(len(R)), index=pd.MultiIndex.from_arrays([E["mkt"], E["d"], E["s"]]))
        nxt = key.reindex(pd.MultiIndex.from_arrays([E["mkt"][idx], E["d"][idx], E["s"][idx] + 1])).to_numpy()
        m = np.zeros(len(R), bool)
        m[nxt[np.isfinite(nxt)].astype(int)] = True
    m &= np.isfinite(R)
    k = P.no_overlap(E, m, c["exit"])
    return pd.DataFrame(dict(mkt=E["mkt"][k], t=E["t"][k] + 3600, tx=E[f"tx_{c['exit']}"][k], R=R[k]))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    a = ap.parse_args()
    fin = json.loads((HERE / "tf_finalize_H1.json").read_text())["finalists"]
    h = TS.setup(a.root, TS.END)
    TS.l3_setup({m: TS.cut(x, TS.D0, TS.CUT) for m, x in h.items()}, "H1")
    ev = {k: FV.Events(h, k) for k in (1.0, 2.0, 3.0)}
    res = {"patterns": {}}
    stressed = {}
    for i, k in enumerate(fin, 1):
        c = TF.parse_name(k["name"])
        base = select(ev[1.0], c)
        stop = base.R <= -0.9
        late = select(ev[1.0], c, late=True)
        cases = {
            "base": base.R,
            "(a) costs x2": select(ev[2.0], c).R,
            "(b) costs x3": select(ev[3.0], c).R,
            "(c) +0.05R": base.R - 0.05,
            "(d) +0.10R": base.R - 0.10,
            "(e) stop 0.10R worse": base.R - 0.10 * stop,
            "(f) stop 0.25R worse": base.R - 0.25 * stop,
            "(g) one bar late": late.R,
            "(h) no 20-24 UTC": select(ev[1.0], c, no_rollover=True).R,
            "(i) without best 5%": base.R.sort_values().iloc[: int(len(base) * 0.95)],
        }
        j = select(ev[2.0], c, late=True)
        j = j.assign(R=j.R - 0.05)
        cases["(j) x2 + 0.05R + late"] = j.R
        stressed[i] = j
        rows = {nm: dict(n=len(R), mean=float(np.mean(R)), t=tstat(R)) for nm, R in cases.items()}
        y = pd.to_datetime(base.t, unit="s").dt.year
        yr = base.R.groupby(y).mean()
        rows["years_positive"] = f"{int((yr > 0).sum())}/{len(yr)}"
        need = ["(a) costs x2", "(c) +0.05R", "(e) stop 0.10R worse", "(g) one bar late", "(h) no 20-24 UTC"]
        robust = all(rows[n]["mean"] > 0 and rows[n]["t"] > 2 for n in need) and rows["(j) x2 + 0.05R + late"]["mean"] > 0
        rows["robust"] = bool(robust)
        res["patterns"][f"H1#{i}"] = dict(name=k["name"], cases=rows, yearly=yr.round(3).to_dict())
        print(f"\n  H1#{i} {k['name']}  (stop exits {stop.mean():.0%} of trades)")
        for nm, r in rows.items():
            if isinstance(r, dict):
                print(f"    {nm:24s} n {r['n']:5d}  R {r['mean']:+.3f}  t {r['t']:+.2f}")
        print(f"    years positive {rows['years_positive']}   -> {'ROBUST' if robust else 'NOT ROBUST'}", flush=True)
    # plan check
    P.setup(a.root)
    G, K = P._M["G"], P._M["K"]
    sys.path.insert(0, str(pathlib.Path(a.root) / "research" / "grid768"))
    import report768 as RP
    PMS.END = TS.END
    news = W.news_times(a.root)
    H1 = {m: MMS.load(m, G) for m in TF.S5}
    g = SU.g27k_trades(TF.S5, H1, RP, G, K, K.externals())[["mkt", "t", "tx", "R", "vp", "sc"]]
    for name, use in (("G27K alone", []), ("G27K + 3 x 0.33% (stressed j)", [1, 2, 3]),
                      ("G27K + robust only x 0.33%", [i for i in (1, 2, 3) if res["patterns"][f"H1#{i}"]["cases"]["robust"]])):
        parts = [g]
        for i in use:
            x = stressed[i][stressed[i].mkt.isin(TF.S5)]
            parts.append(x.assign(mkt=x.mkt + f"#H1{i}", R=x.R * 0.33, vp=0.0, sc=x.t)[g.columns])
        TT = pd.concat(parts, ignore_index=True)
        st, eq, _ = SU.simulate(TT, "brake", TF.PSTART, TF.END, news=news)
        a1, _, _ = SU.simulate(TT, "brake", TF.PSTART, TF.PMID, news=news)
        a2, _, _ = SU.simulate(TT, "brake", TF.PMID, TF.END, news=news)
        mc = SU.monte_carlo(eq)
        res.setdefault("plan", {})[name] = dict(cagr=st["cagr"], dd=st["dd"], mar=st["mar"], mar_h1=a1["mar"], mar_h2=a2["mar"], p_dd50=mc["p_dd50"])
        p = res["plan"][name]
        print(f"  {name:32s} CAGR {p['cagr']:+6.1%}  DD {p['dd']:5.1%}  MAR {p['mar']:.2f}  halves {p['mar_h1']:+.2f}/{p['mar_h2']:+.2f}  MC P(DD>50%) {p['p_dd50']:.1%}")
    pl = res["plan"]["G27K + 3 x 0.33% (stressed j)"]
    res["plan_pass"] = bool(pl["mar"] > res["plan"]["G27K alone"]["mar"] and pl["p_dd50"] <= 0.05)
    print("  plan pass:", res["plan_pass"])
    (HERE / "h1_stress.json").write_text(json.dumps(res, indent=1, default=float))


if __name__ == "__main__":
    main()
