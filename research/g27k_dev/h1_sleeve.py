#!/usr/bin/env python3
"""Ledger h1_search_mirror_m30, part D: the part C pick as an H1 sleeve, run
the way the M30 sleeve was.

  --part newmkt   the pick unchanged on ETHUSD, USDJPY, JP225 (criterion of
                  m30_sleeve_new_markets part 1); writes every H1 sleeve trade
                  of the six markets to .cache_wf/h1_sleeve6.pkl
  --part combo    G27K-F + M30 (5 markets) vs G27K-F + M30 + H1 sleeve
                  (0.5% each), Cent and Standard, G27K-F 0.75% / 1% /
                  1% + brake; the four conditions judged at 1% + brake
  --part robust   the battery of m30_sleeve_new_markets part 3 on the final
                  H1 sleeve. Neighbours (b), fixed before the pick was known:
                  near-extreme threshold one step either side (ATR features
                  +-0.25, pos250 +-0.05) x volatility (atr_ratio x: x-0.25, x,
                  x+0.25; none: none, 1.0, 1.25) x context as picked / the
                  other of (none, htf1_with) = 18; exit and direction fixed.

The pick = the part C candidate with the highest all-period net t
(h1_mirror_real.json).

Usage: python3 research/g27k_dev/h1_sleeve.py --root <snap> --part newmkt|combo|robust
"""
import argparse
import itertools
import json
import pathlib
import pickle
import sys
import time

import numpy as np
import pandas as pd

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))
import h4d1_pattern_search as P
import m30_combo as MC
import m30_new_markets as NM
import m30_robust as MRB
import minute_reverse as MR
import news_shock as NS
import per_market_search as PMS

START, MID, END = NM.START, NM.MID, NM.END
VCONF = {"0.75%": (0.75, "normal"), "1%": (1.0, "normal"), "1% + brake": (1.0, "brake")}


def pick():
    rows = json.loads((HERE / "h1_mirror_real.json").read_text())["C"]
    c = [r for r in rows if r["cand"]]
    if not c:
        raise SystemExit("part C has no candidate: nothing to run")
    return max(c, key=lambda r: r["all"]["t"])


def spec_of(r):
    fk, thr = MR.NEAR[r["near"]]
    return dict(tf=r["tf"], near=fk, thr=thr, vol=MR.VOL[r["vol"]], ctx=r["ctx"], dir=r["dir"], exit=r["exit"], scope=r["scope"])


def mask(E, feats, cats, s):
    m = np.isfinite(E[f"R_{s['exit']}"]) & (feats[s["near"]] >= s["thr"])
    if s["vol"] is not None:
        m &= feats["atr_ratio"] >= s["vol"]
    if s["ctx"] == "htf1_with":
        m &= cats["htf1_with"]
    elif s["ctx"] == "ema20_50>=0":
        m &= feats["ema20_50"] >= 0
    if s["dir"] == "long":
        m &= E["d"] > 0
    return m


def trades(E, k, s):
    ex, sec = s["exit"], P.TF_SEC[s["tf"]]
    g = E["d"][k] * (E[f"px_{ex}"][k] - E[f"ep_{ex}"][k]) / E[f"rk_{ex}"][k]
    T = pd.DataFrame(dict(mkt=E["mkt"][k], t=(E["t"][k] + sec).astype(np.int64), tx=E[f"tx_{ex}"][k].astype(np.int64),
                          R=E[f"R_{ex}"][k], gross=g, d=E["d"][k], i=k))
    T = T.sort_values("t").reset_index(drop=True)
    return T[(T.t >= NS.W.ts(START)) & (T.t < NS.W.ts(END))].reset_index(drop=True)


def build(s, markets, h1=None):
    if h1 is None:
        h1 = P._M["h1"]
    return P.build({m: h1[m] for m in markets}, s["tf"])


def part_newmkt(a, s):
    NM.prepare(a.root)
    E, feats, cats = build(s, NM.ALL)
    T = trades(E, P.no_overlap(E, mask(E, feats, cats, s), s["exit"]), s)
    (PMS.CACHE / "h1_sleeve6.pkl").write_bytes(pickle.dumps(T))
    mid = NS.W.ts(MID)
    out = dict(spec=s, markets={})
    for m in NM.ALL:
        x = T[T.mkt == m]
        om = NS.W.ts(NM.OWN_MID.get(m, MID))
        r = dict(all=NM.summ(x), h1=NM.summ(x[x.t < mid]), h2=NM.summ(x[x.t >= mid]), own_h1=NM.summ(x[x.t < om]), own_h2=NM.summ(x[x.t >= om]))
        out["markets"][m] = r
        print(f"  {m:7s} n {r['all']['n']:4d} net {r['all']['net']:+.3f} t {r['all']['t']:+.2f} gross {r['all']['gross']:+.3f} cost {r['all']['cost']:.3f} | "
              f"2011-18 {r['h1']['net']:+.3f} (n {r['h1']['n']}) 2019-26 {r['h2']['net']:+.3f} | own halves {r['own_h1']['net']:+.3f} / {r['own_h2']['net']:+.3f}", flush=True)
    for nm, ms in (("pooled_new", NM.NEW), ("pooled_old", NM.OLD)):
        x = T[T.mkt.isin(ms)]
        out[nm] = dict(all=NM.summ(x), h1=NM.summ(x[x.t < mid]), h2=NM.summ(x[x.t >= mid]))
        r = out[nm]
        print(f"  {nm}: n {r['all']['n']} net {r['all']['net']:+.3f} t {r['all']['t']:+.2f} | 2011-18 {r['h1']['net']:+.3f} 2019-26 {r['h2']['net']:+.3f}", flush=True)
    pn = out["pooled_new"]
    ok = bool(pn["all"]["net"] > 0 and pn["all"]["t"] >= 2.0 and pn["h1"]["net"] > 0 and pn["h2"]["net"] > 0)
    add = [m for m in NM.NEW if ok and out["markets"][m]["all"]["net"] > 0 and out["markets"][m]["own_h1"]["net"] > 0 and out["markets"][m]["own_h2"]["net"] > 0]
    old = [m for m in NM.OLD if s["scope"] in ("pooled", m)]
    out.update(newmkt_pass=ok, added=add, final=old + add)
    print(f"  new markets {'PASS' if ok else 'FAIL'} -> added {add or 'none'}; final H1 sleeve markets {old + add}")
    (HERE / "h1_sleeve_newmkt.json").write_text(json.dumps(out, indent=1, default=float))


def frame(rows_g, books, kg, extra=0.0):
    """G27K-F rows at kg, plus sleeves [(trades, suffix, k)] at k each."""
    parts = [pd.DataFrame(dict(mkt=[r["mkt"] for r in rows_g], t=[r["t"] for r in rows_g], tx=[r["t_exit"] for r in rows_g],
                               R=[(r["R"] - extra) * kg for r in rows_g]))]
    for S, suf, k in books:
        parts.append(pd.DataFrame(dict(mkt=S.mkt + suf, t=S.t, tx=S.tx, R=(S.R - extra) * k)))
    F = pd.concat(parts, ignore_index=True)
    return F.assign(vp=0.0, sc=F.t)


def part_combo(a, s):
    P.setup(a.root)
    nm = json.loads((HERE / "h1_sleeve_newmkt.json").read_text())
    final = nm["final"]
    M30 = pickle.loads((PMS.CACHE / "m30_sleeve6.pkl").read_bytes())
    M30 = M30[M30.mkt.isin(list(NM.OLD) + ["ETHUSD", "USDJPY"])]
    H1 = pickle.loads((PMS.CACHE / "h1_sleeve6.pkl").read_bytes())
    H1 = H1[H1.mkt.isin(final)]
    G, K, C = P._M["G"], P._M["K"], P._M["C"]
    sys.path.insert(0, str(pathlib.Path(a.root) / "research" / "grid768"))
    import report768 as RP
    C.SPECS.update(NS.FM.specs(C))
    Hh = {m: (NS.MMS.load(m, G) if m in NS.MMS.MARKETS else NS.L3.load(m, "2009-01-01", END)) for m in NS.RF.STD}
    NS.RSD.START = START
    news = NS.W.news_times(a.root)
    raw = [{k: v for k, v in r.items() if k != "X"} for r in NS.RSD.g27k_rows(NS.RF.STD, Hh, RP, G, K, K.externals()) if NS.W.ts(START) <= r["t"] < NS.W.ts(END)]
    gf = NS.apply(raw, NS.fed_shocks(a.root), Hh, True)
    # overlap with the M30 sleeve and G27K-F, monthly correlation
    mon = lambda x: pd.Series(x.R.to_numpy(), index=pd.to_datetime(x.tx, unit="s")).resample("ME").sum()
    gd = pd.DataFrame(dict(R=[r["R"] for r in gf], tx=[r["t_exit"] for r in gf]))
    corr = {}
    for nm_, X in (("M30", M30), ("G27K-F", gd)):
        a_, b_ = mon(H1), mon(X)
        i = a_.index.union(b_.index)
        corr[nm_] = float(np.corrcoef(a_.reindex(i, fill_value=0), b_.reindex(i, fill_value=0))[0, 1])
    print(f"  H1 sleeve: {len(H1)} trades {H1.R.mean():+.3f}R on {final} | monthly R corr with M30 {corr['M30']:+.2f}, with G27K-F {corr['G27K-F']:+.2f}", flush=True)
    out = dict(final=final, n=len(H1), R=float(H1.R.mean()), corr=corr, runs={})
    for acct_nm, ms in (("Cent", NS.RF.CENT), ("Standard", NS.RF.STD)):
        rows = [r for r in gf if r["mkt"] in ms]
        m30 = M30[M30.mkt.isin(ms)]
        h1 = H1[H1.mkt.isin(ms)]
        for vn, (kg, ver) in VCONF.items():
            res = {}
            for nm_, books in (("F", []), ("F+M30", [(m30, "_M30", 0.5)]), ("F+M30+H1", [(m30, "_M30", 0.5), (h1, "_H1", 0.5)])):
                F, Fs = frame(rows, books, kg), frame(rows, books, kg, 0.10)
                res[nm_] = dict(full=MC.acct(F, ver, news, mc=True), h1=MC.acct(F, ver, news, end=MC.MID), h2=MC.acct(F, ver, news, start=MC.MID),
                                stress=MC.acct(Fs, ver, news))
                r = res[nm_]
                print(f"  {acct_nm:8s} {vn:10s} {nm_:9s} CAGR {r['full']['cagr']:+6.1%} DD {r['full']['dd']:5.1%} MAR {r['full']['mar']:.2f} | halves {r['h1']['mar']:+.2f}/{r['h2']['mar']:+.2f} "
                      f"| -0.10R MAR {r['stress']['mar']:.2f} | P(DD>50%) {r['full']['p50']:.1%} | trades {r['full']['n']}", flush=True)
            b, x = res["F+M30"], res["F+M30+H1"]
            ok = bool(x["full"]["mar"] > b["full"]["mar"] and x["h1"]["mar"] > b["h1"]["mar"] and x["h2"]["mar"] > b["h2"]["mar"]
                      and x["stress"]["mar"] > b["stress"]["mar"] and x["full"]["p50"] <= b["full"]["p50"] + 0.01)
            out["runs"][f"{acct_nm} {vn}"] = dict(res=res, pass_=ok)
            print(f"    -> H1 sleeve {'PASSES' if ok else 'fails'} for {acct_nm} {vn}", flush=True)
    v = out["runs"]["Cent 1% + brake"]["pass_"] and out["runs"]["Standard 1% + brake"]["pass_"]
    out["verdict"] = bool(v)
    print(f"  ACCOUNT VERDICT (Cent and Standard, 1% + brake): {'ADOPT H1 sleeve' if v else 'do not adopt'}")
    (HERE / ("h1_sleeve_combo" + ("_cent" + str(len(NS.RF.CENT)) if a.cent else "") + ".json")).write_text(json.dumps(out, indent=1, default=float))


def neighbours(s):
    if s["near"].startswith("brk"):
        nears = (s["thr"] + 0.25, s["thr"], s["thr"] - 0.25)
    else:
        nears = (s["thr"] - 0.05, s["thr"], s["thr"] + 0.05)
    vols = (s["vol"] - 0.25, s["vol"], s["vol"] + 0.25) if s["vol"] is not None else (None, 1.0, 1.25)
    ctxs = (s["ctx"], "htf1_with" if s["ctx"] == "-" else "-") if s["ctx"] in ("-", "htf1_with") else (s["ctx"], "-")
    return [dict(s, thr=n, vol=v, ctx=c) for n, v, c in itertools.product(nears, vols, ctxs)]


def part_robust(a, s):
    t0 = time.time()
    nm = json.loads((HERE / "h1_sleeve_newmkt.json").read_text())
    mk = nm["final"]
    NM.prepare(a.root, mk)
    E, feats, cats = build(s, mk)
    ex = s["exit"]
    base = trades(E, P.no_overlap(E, mask(E, feats, cats, s), ex), s)
    st = MRB.st
    out = dict(markets=mk, spec=s, base=st(base))
    print(f"  base: n {len(base)} net {base.R.mean():+.3f} t {NM.tstat(base.R):+.2f}", flush=True)
    cost = base.gross - base.R
    out["a"] = {f"-{x:.2f}R": st(base.assign(R=base.R - x)) for x in (0.05, 0.10, 0.15)}
    out["a"]["cost x2"] = st(base.assign(R=base.R - cost))
    out["a"]["median cost R"] = float(cost.median())
    for k, v in out["a"].items():
        print(f"  (a) {k}: {v}", flush=True)
    nb = []
    for q in neighbours(s):
        T = trades(E, P.no_overlap(E, mask(E, feats, cats, q), ex), s)
        r = dict(near=q["near"], thr=q["thr"], vol=q["vol"], ctx=q["ctx"], **st(T), ok=bool(len(T) > 2 and T.R.mean() > 0 and NM.tstat(T.R) >= 2))
        nb.append(r)
        print(f"  (b) {q['near']}>={q['thr']:+.2f} atr_ratio>={q['vol']} ctx {q['ctx']:12s}: n {r['n']:5d} net {r['net']:+.3f} t {r['t']:+.2f} {'ok' if r['ok'] else '--'}", flush=True)
    out["b"] = dict(rows=nb, n_ok=sum(r["ok"] for r in nb))
    MRB.EX = ex
    D = trades(E, MRB.delayed(E, mask(E, feats, cats, s)), s)
    out["c"] = st(D)
    print(f"  (c) one bar later: {out['c']}", flush=True)
    out["e"] = {m: st(base[base.mkt != m]) for m in mk} if len(mk) > 1 else {}
    out["per_market"] = {m: st(base[base.mkt == m]) for m in mk}
    yr = base.groupby(pd.to_datetime(base.t, unit="s").dt.year).R.mean()
    out["f"] = dict(years={int(y): float(v) for y, v in yr.items()}, share_pos=float((yr > 0).mean()))
    print(f"  (e) leave one out: " + "  ".join(f"-{m} {v['net']:+.3f}" for m, v in out["e"].items()), flush=True)
    print(f"  (f) positive years {out['f']['share_pos']:.0%}: " + " ".join(f"{y}:{v:+.2f}" for y, v in out["f"]["years"].items()), flush=True)
    del E, feats, cats
    pl = []
    for p in range(5):
        Ep, fp, cp = P.build(P.drift_placebo(p), s["tf"])
        T = trades(Ep, P.no_overlap(Ep, mask(Ep, fp, cp, s), ex), s)
        pl.append(st(T))
        print(f"  (d) drift placebo {p}: {pl[-1]}  {time.time() - t0:.0f}s", flush=True)
        del Ep, fp, cp
    out["d"] = pl
    tb = out["base"]["t"]
    checks = dict(a=out["a"]["-0.10R"]["net"] > 0, b=out["b"]["n_ok"] >= 14, c=out["c"]["net"] > 0,
                  d=all(tb > x["t"] for x in pl), e=all(v["net"] > 0 for v in out["e"].values()))
    out["checks"] = checks
    out["robust"] = bool(all(checks.values()))
    print(f"  ROBUSTNESS: {checks} -> {'ROBUST' if out['robust'] else 'NOT ROBUST'}  {time.time() - t0:.0f}s")
    (HERE / "h1_robust.json").write_text(json.dumps(out, indent=1, default=float))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    ap.add_argument("--part", choices=("newmkt", "combo", "robust"), required=True)
    ap.add_argument("--cent", default="", help="markets tradable on the Cent account (combo)")
    a = ap.parse_args()
    if a.cent:
        NS.RF.CENT = tuple(a.cent.split(","))
    s = spec_of(pick())
    print(f"  pick: {s}", flush=True)
    {"newmkt": part_newmkt, "combo": part_combo, "robust": part_robust}[a.part](a, s)


if __name__ == "__main__":
    main()
