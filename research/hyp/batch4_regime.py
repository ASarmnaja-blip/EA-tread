"""Hypothesis batch 4 (docs/HYPOTHESIS_BATCH4_PREREG.md): regime-conditional champion selection vs WRWR v2 (Family 2 tables).
Usage: python research/hyp/batch4_regime.py XAUUSD   (then XAGUSD, then: report)
Writes data/hyp/batch4_<SYM>.npz / .json; report prints the pre-registered endpoints and writes data/hyp/batch4.json."""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "research" / "wrwr"), str(ROOT / "research" / "foundry")]
import contracts as K  # noqa: E402
import gates as G  # noqa: E402
import portfolio as PF  # noqa: E402

OUT = ROOT / "data" / "hyp"
SEED = 20261001
YEARS = {"XAUUSD": list(range(2010, 2027)), "XAGUSD": list(range(2012, 2027))}
FAMFILE = {"XAUUSD": ROOT / "data" / "wrwr" / "family_XAUUSD_f2.npz", "XAGUSD": ROOT / "data" / "wrwr" / "xag" / "family_XAGUSD_f2.npz"}
SHADOW = {"F2-66": 66, "F2-78": 78, "F2-134": 134, "F2-86": 86}


def load(sym):
    import run_family as RF
    if sym == "XAUUSD":
        import engine as E
        import build_f2 as BF2
        H, _, cuts, cell = E.load()
        P = PF.load_pool(sym, RF.TFS, cuts, verify=True, loader=BF2.loader)
        vs = K.causal_vol_scale(H.t, H.c, H.h, H.l, cuts, mode="historical", bar_seconds=3600)
    else:
        import xag as X
        X.patch_marks()
        B1, cuts, cell = X.load_xag("H1")
        P = PF.load_pool(sym, RF.TFS, cuts, verify=True, loader=X.make_loader("f2"))
        vs = K.causal_vol_scale(B1.t, B1.c, B1.h, B1.l, cuts, mode="historical", bar_seconds=3600)
    cell = np.array(list(cell) + [""] * (len(cuts) - len(cell)), object)[: len(cuts)]
    active = cell != ""
    return RF, P, vs, active, cell


def shadow_parts(P):
    """Per candidate: known-cut index, entry-week index and R of its one-position shadow trades."""
    NW = len(P.cuts); parts = []
    for c in range(len(P.cands)):
        et, xt, r = P.entry_t[c], P.exit_t[c], P.R[c].astype(np.float64)
        keep, busy = [], -1
        for i in range(len(et)):
            if et[i] >= busy:
                keep.append(i); busy = xt[i]
        keep = np.asarray(keep, int)
        if not len(keep):
            parts.append(None); continue
        kn = K.known_at_cut(xt[keep], P.cuts)
        we = np.searchsorted(P.cuts, et[keep], side="left") - 1
        ok = (kn < NW) & (we >= 0)
        parts.append((kn[ok], we[ok], r[keep][ok]))
    return parts


def class_stats(parts, week_cls, X, NW):
    n = len(parts)
    S1 = np.zeros((n, NW)); S2 = np.zeros((n, NW)); NN = np.zeros((n, NW))
    for c, pt in enumerate(parts):
        if pt is None:
            continue
        kn, we, r = pt
        m = week_cls[we] == X
        if m.any():
            S1[c] = np.bincount(kn[m], r[m], NW); S2[c] = np.bincount(kn[m], r[m] ** 2, NW); NN[c] = np.bincount(kn[m], None, NW)
    return S1, S2, NN


def conditional_scores(parts, week_cls, classes, NW, combos, minn):
    scores = {lz: np.full((len(parts), NW), -np.inf) for lz in combos}
    for X in classes:
        S1, S2, NN = class_stats(parts, week_cls, X, NW)
        cols = week_cls == X
        for (L, z) in combos:
            sc = PF.window_scores(S1, S2, NN, L, z, minn)[0]
            scores[(L, z)][:, cols] = sc[:, cols]
            del sc
        del S1, S2, NN
    return scores


def run_sym(sym):
    t0 = time.time()
    RF, P, vs, active, cell = load(sym)
    NW = len(P.cuts)
    print(f"{sym}: pool {len(P.cands)} candidates, {int(active.sum())} active weeks ({time.time() - t0:.0f}s)", flush=True)
    fam, _ = RF.family()
    combos = sorted({(c["window"], c["lcb_z"]) for c in fam})
    pools = {"H1": P.tf == "H1", "H4": P.tf == "H4", "D1": P.tf == "D1", "H1+H4+D1": np.isin(P.tf, RF.TFS)}
    parts = shadow_parts(P)
    print(f"  shadow parts ({time.time() - t0:.0f}s)", flush=True)
    # equivalence check: one class covering every active week must reproduce WRWR v2 exactly (same champions, same weekly R)
    z0 = np.load(FAMFILE[sym], allow_pickle=False)
    one = np.full(NW, "A", object)                                   # every week in one class = v2 (v2 counts trades of inactive weeks too)
    sc1 = conditional_scores(parts, one, ("A",), NW, [(52, 1.0)], RF.MINN)
    j66 = [c for c in fam if (c["window"], c["lcb_z"], c["pool"], c["m"], c["equity_filter"]) == (52, 1.0, "H1", 2, 0)]
    R1, _, _, _ = RF.run(0.01, P, vs, active, pools, sc1, j66)
    diff = float(np.abs(R1[:, 0] - z0["R_0.01"][:, 66]).max())
    print(f"  equivalence check (one class = v2, config 66): max |weekly R difference| {diff:.2e}", flush=True)
    if diff > 1e-9:
        raise SystemExit("conditional machinery does not reproduce WRWR v2: stop")
    del sc1
    vol = np.array([x.split("/")[0] if x else "" for x in cell], object)
    trd = np.array([x.split("/")[1] if x else "" for x in cell], object)
    out = {}
    for name, wc, classes in (("V", vol, ("CALM", "NORMAL", "HIGH")), ("T", trd, ("DOWN", "FLAT", "UP"))):
        scores = conditional_scores(parts, wc, classes, NW, combos, RF.MINN)
        R, EQ, champs, counters = RF.run(0.01, P, vs, active, pools, scores, fam)
        out[name] = R
        del scores
        print(f"  variant {name}: done ({time.time() - t0:.0f}s); SHADOW configs total R " +
              ", ".join(f"{k} {R[active, j].sum():+.1f}" for k, j in SHADOW.items()), flush=True)
    z = np.load(FAMFILE[sym], allow_pickle=False)
    meta = json.loads(str(z["meta"]))
    OUT.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(OUT / f"batch4_{sym}.npz", R_V=out["V"], R_T=out["T"], R_v2=z["R_0.01"], active=active, cuts=P.cuts,
                        data_end=np.int64(meta["data_end"]))
    print(f"-> batch4_{sym}.npz ({time.time() - t0:.0f}s)")


def oos(R, active, cuts, data_end, years):
    NW = len(cuts); k = np.arange(NW); complete = np.r_[cuts[1:] <= data_end, False]
    ks = {Y: int(np.searchsorted(cuts, int(pd.Timestamp(f"{Y}-01-01").timestamp()))) for Y in years + [years[-1] + 1]}
    out = np.zeros(NW); used = np.zeros(NW, bool); picks = {}
    for Y in years:
        hist = active & (k < ks[Y]); fut = active & complete & (k >= ks[Y]) & (k < ks[Y + 1])
        X = R[hist]
        with np.errstate(invalid="ignore", divide="ignore"):
            t = X.mean(0) / (X.std(0, ddof=1) / np.sqrt(len(X)))
        t = np.nan_to_num(t, nan=-np.inf)
        j = int(np.lexsort((np.arange(len(t)), -t))[0])
        out[fut] = R[fut, j]; used[fut] = True; picks[Y] = j
    return out, used, picks


def boot_one_sided(x, seed=SEED):
    m = float(x.mean())
    if m <= 0:
        return m, 1.0
    idx = G.stationary_indices(len(x), 10, 999, np.random.default_rng(seed))
    ms = x[idx].mean(1)
    return m, float((1 + np.sum(ms - m >= m)) / 1000)


def report():
    res = {}
    for sym in ("XAUUSD", "XAGUSD"):
        z = np.load(OUT / f"batch4_{sym}.npz")
        act, cuts, de = z["active"], z["cuts"], int(z["data_end"])
        base, used, pb = oos(z["R_v2"], act, cuts, de, YEARS[sym])
        res[sym] = {"v2": dict(total=float(base[used].sum()), mean=float(base[used].mean()), picks=pb)}
        for v in ("V", "T"):
            cond, used2, pc = oos(z[f"R_{v}"], act, cuts, de, YEARS[sym])
            d = (cond - base)[used]
            md, pd_ = boot_one_sided(d)
            mc, pc_ = boot_one_sided(cond[used])
            growth = float(np.prod(1 + 0.01 * cond[used]))
            res[sym][v] = dict(total=float(cond[used].sum()), mean=mc, p_abs=pc_, diff_mean=md, p_diff=pd_, growth=growth, picks=pc,
                               shadow_full={k: float(z[f"R_{v}"][act, j].sum()) for k, j in SHADOW.items()})
        res[sym]["v2"]["shadow_full"] = {k: float(z["R_v2"][act, j].sum()) for k, j in SHADOW.items()}
    pv = np.array([res["XAUUSD"][v]["p_diff"] for v in ("V", "T")])
    rej = np.zeros(2, bool)
    for r_, j in enumerate(np.argsort(pv)):
        if pv[j] <= 0.05 / (2 - r_):
            rej[j] = True
        else:
            break
    print("Batch 4: out-of-sample yearly procedure (largest trailing t of weekly net R), 1 % risk, R per week")
    for sym in ("XAUUSD", "XAGUSD"):
        b = res[sym]["v2"]
        print(f"{sym} v2 (unconditional): total {b['total']:+.1f} R, mean {b['mean']:+.4f}/wk; SHADOW full-sample " +
              ", ".join(f"{k} {v:+.1f}" for k, v in b["shadow_full"].items()))
        for v in ("V", "T"):
            x = res[sym][v]
            print(f"{sym} {v} (conditional on {'volatility' if v == 'V' else 'trend'} class): total {x['total']:+.1f} R, mean {x['mean']:+.4f}/wk "
                  f"(p {x['p_abs']:.3f}), minus v2 {x['diff_mean']:+.4f}/wk (p {x['p_diff']:.3f}), equity x{x['growth']:.2f}; SHADOW full-sample " +
                  ", ".join(f"{k} {val:+.1f}" for k, val in x["shadow_full"].items()))
    for i, v in enumerate(("V", "T")):
        g, s = res["XAUUSD"][v], res["XAGUSD"][v]
        passed = bool(rej[i] and s["diff_mean"] > 0 and s["p_diff"] <= 0.10 and g["mean"] > 0 and s["mean"] > 0)
        res[f"PASS_{v}"] = passed
        print(f"variant {v}: gold Holm {'reject' if rej[i] else 'keep H0'} -> {'PASS' if passed else 'FAIL'}")
    (OUT / "batch4.json").write_text(json.dumps(res, indent=1, default=float))


if __name__ == "__main__":
    if sys.argv[1] == "report":
        report()
    else:
        run_sym(sys.argv[1])
