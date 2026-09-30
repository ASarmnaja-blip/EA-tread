"""WRWR Test B runner (docs/WRWR_HISTORY_OOS_PREREG.md): the frozen 144-configuration selector family on silver (Family 2) and the
zoo BASE (C7 as frozen), the same-exit-configuration random-router benchmark and the pre-registered read-outs. The gold code is
reused unchanged (run_family.family / run, portfolio.load_pool / simulate, run_bench.task, gates); only the data source is silver.
Usage: python research/wrwr/xag_run.py family f2|zoo
       python research/wrwr/xag_run.py bench f2 S|F [workers]   /   bench zoo BASE [workers]
       python research/wrwr/xag_run.py gates
Writes data/wrwr/xag/family_XAGUSD_<set>.npz, cache_pool_<set>/, bench_<stage>_<set>.npz, gates_xag.json."""
from __future__ import annotations

import json
import multiprocessing as mp
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import contracts as K  # noqa: E402
import gates as G  # noqa: E402
import portfolio as PF  # noqa: E402
import xag as X  # noqa: E402

OUT = X.OUT
TFS = ["H1", "H4", "D1"]
BASE_KEY = (52, 1.0, "H1", 2, 0)
SHADOW = {"F2-66": 66, "F2-78": 78, "F2-134": 134, "F2-86": 86}
STAGE_PATHS = {"S": 500, "F": 2_000, "BASE": 10_000}
ERAS = {"2010-14": ("2010", "2015"), "2015-20": ("2015", "2021"), "2021-26": ("2021", "2027")}


def key(c):
    return (c["window"], c["lcb_z"], c["pool"], c["m"], c["equity_filter"])


def fam_path(s):
    return OUT / f"family_XAGUSD_{s}.npz"


def cache_dir(s):
    return OUT / f"cache_pool_{s}"


def family(sigset):
    import run_family as RF
    t0 = time.time()
    X.patch_marks()
    B1, cuts, cell = X.load_xag("H1")
    tfs = TFS if sigset == "f2" else ["H1"]
    P = PF.load_pool(X.SYM, tfs, cuts, verify=True, loader=X.make_loader(sigset))
    print(f"silver pool {sigset}: {len(P.cands)} candidates (C5 verified), {P.rejected_at_cut} rejected at a cut, contract {P.contract:g} "
          f"({time.time() - t0:.0f}s)", flush=True)
    S1, S2, NN = PF.shadow_stats(P)
    vs = K.causal_vol_scale(B1.t, B1.c, B1.h, B1.l, cuts, mode="historical", bar_seconds=3600)
    active = np.array([c != "" for c in cell] + [False] * (len(cuts) - len(cell)))[: len(cuts)]
    fam, fam_sha = RF.family()
    if sigset == "zoo":
        fam = [c for c in fam if key(c) == BASE_KEY]                     # C7 as frozen: BASE only
    pools = {"H1": P.tf == "H1", "H4": P.tf == "H4", "D1": P.tf == "D1", "H1+H4+D1": np.isin(P.tf, TFS)}
    scores = {(L, z): PF.window_scores(S1, S2, NN, L, z, RF.MINN)[0] for (L, z) in sorted({(c["window"], c["lcb_z"]) for c in fam})}
    R, EQ, champs, counters = RF.run(0.01, P, vs, active, pools, scores, fam)
    meta = dict(schema=K.SCHEMA, cost_version=K.COST_VERSION, symbol=X.SYM, sigset=sigset, family_sha=fam_sha, n_config=len(fam),
                code_sha=K.sha_files(HERE / "xag_run.py", HERE / "run_family.py", HERE / "portfolio.py", HERE / "contracts.py", HERE / "xag.py"),
                cuts_sha=K.sha_bytes(cuts), data_end=int(P.mark_t[-1]), tables={tf: m["array_sha"] for tf, m in P.meta.items()},
                vol_scale_mode="historical", built=pd.Timestamp.now(tz="UTC").isoformat())
    np.savez_compressed(fam_path(sigset), cuts=cuts, active=active, vol_scale=vs, family=json.dumps(fam), meta=json.dumps(meta),
                        cand_hash=json.dumps([c["hash"] for c in P.cands]), **{"R_0.01": R, "EQ_0.01": EQ},
                        champs=json.dumps({str(j): [[int(x) for x in w] for w in ch] for j, ch in champs.items()}),
                        counters=json.dumps(counters))
    PF.save_pool_cache(P, cache_dir(sigset), extra=dict(NN=NN, vol_scale=vs, active=active))
    wk = pd.to_datetime(cuts, unit="s")
    print(f"{len(fam)} configurations, {int(active.sum())} active weeks ({wk[active][0]:%Y-%m-%d} .. {wk[active][-1]:%Y-%m-%d}), "
          f"vol_scale median {np.median(vs[active]):.2f} ({time.time() - t0:.0f}s)")
    for j, c in enumerate(fam):
        if key(c) == BASE_KEY or j in SHADOW.values():
            print(f"  cfg {j:3d} {c['window']}w z{c['lcb_z']:g} {c['pool']} m{c['m']} eq{c['equity_filter']}: total R {R[active, j].sum():+.1f}, "
                  f"entries {counters[j]['entries']}")


def init_worker(sigset):
    import run_bench as RB
    d = cache_dir(sigset)
    RB._G["P"] = PF.load_pool_cache(d)
    RB._G["vs"] = np.load(d / "vol_scale.npy")
    NN = np.load(d / "NN.npy")
    cum = np.c_[np.zeros((NN.shape[0], 1)), np.cumsum(NN, axis=1)]
    k = np.arange(NN.shape[1])
    RB._G["elig"] = {L: (cum[:, k + 1] - cum[:, np.maximum(k - L + 1, 0)]) >= RB.MINN for L in RB.WINDOWS}
    z = np.load(fam_path(sigset), allow_pickle=False)
    RB._G["fam"] = json.loads(str(z["family"])); RB._G["champs"] = json.loads(str(z["champs"])); RB._G["slots"] = {}


def bench(sigset, stage, workers):
    import run_bench as RB
    t0 = time.time()
    z = np.load(fam_path(sigset), allow_pickle=False)
    fam = json.loads(str(z["family"]))
    npaths = STAGE_PATHS[stage]
    cfgs = list(range(len(fam)))
    chunk = 25 if npaths <= 500 else 100
    tasks = [(j, lo, min(lo + chunk, npaths)) for j in cfgs for lo in range(0, npaths, chunk)]
    NW = len(z["cuts"])
    S1 = np.zeros((NW, len(fam))); S2 = np.zeros((NW, len(fam))); cnt = np.zeros(len(fam))
    done = 0
    with mp.Pool(workers, initializer=init_worker, initargs=(sigset,)) as pool:
        for j, n, s1, s2 in pool.imap_unordered(RB.task, tasks):
            S1[:, j] += s1; S2[:, j] += s2; cnt[j] += n; done += 1
            if done % max(len(tasks) // 20, 1) == 0:
                print(f"  {done}/{len(tasks)} tasks ({time.time() - t0:.0f}s)", flush=True)
    B = np.where(cnt > 0, S1 / np.maximum(cnt, 1), np.nan)
    SE = np.sqrt(np.maximum(S2 / np.maximum(cnt, 1) - B ** 2, 0) / np.maximum(cnt, 1))
    out = OUT / f"bench_{stage}_{sigset}.npz"
    np.savez_compressed(out, B=B, SE=SE, paths=cnt, configs=np.array(cfgs), stage=stage, family_sha=str(z["meta"]))
    print(f"{stage} {sigset}: {len(tasks)} tasks, {int(cnt[0])} paths per configuration -> {out.name} ({time.time() - t0:.0f}s)")


def _load_d(sigset, stage):
    z = np.load(fam_path(sigset), allow_pickle=False)
    b = np.load(OUT / f"bench_{stage}_{sigset}.npz", allow_pickle=False)
    if str(b["family_sha"]) != str(z["meta"]):
        raise ValueError(f"bench_{stage}_{sigset} was not computed from family_XAGUSD_{sigset}")
    active = z["active"]
    R = z["R_0.01"][active]; B = b["B"][active]
    return z, active, R, B, R - B


def holm(ps, alpha=0.05):
    order = np.argsort(ps); rej = np.zeros(len(ps), bool)
    for i, j in enumerate(order):
        if ps[j] <= alpha / (len(ps) - i):
            rej[j] = True
        else:
            break
    return rej


def cost_gate(sigset, z, active, j):
    P = PF.load_pool_cache(cache_dir(sigset)); vs = np.load(cache_dir(sigset) / "vol_scale.npy")
    ch = [[int(x) for x in w] for w in json.loads(str(z["champs"]))[str(j)]]
    wr, eqs, _ = PF.simulate(P, ch, vs, f=0.01, stress=True)
    r = z["R_0.01"][active][:, j]; eq = z["EQ_0.01"][active][:, j]
    lb, m = G.lower_bound_mean(r)
    dd_b = float((1 - eq / np.maximum.accumulate(eq)).max()); dd_s = float((1 - eqs[active] / np.maximum.accumulate(eqs[active])).max())
    return dict(mean=m, lb95=lb, stress_mean=float(wr[active].mean()), dd_base=dd_b, dd_stress=dd_s,
                passed=bool(lb > 0 and wr[active].mean() > 0 and dd_s <= 1.25 * dd_b))


def long_short(sigset, z, j):
    P = PF.load_pool_cache(cache_dir(sigset)); vs = np.load(cache_dir(sigset) / "vol_scale.npy")
    ch = [[int(x) for x in w] for w in json.loads(str(z["champs"]))[str(j)]]
    log = []
    PF.simulate(P, ch, vs, f=0.01, log=log)
    out = {}
    for sgn, nm in ((1, "long"), (-1, "short")):
        rr = [R_i for (k, c, te, xt, lots, R_i, pnl, eq) in log
              if int(P.dir[c][int(np.searchsorted(P.entry_t[c], te))]) == sgn]
        out[nm] = dict(n=len(rr), mean_R=float(np.mean(rr)) if rr else float("nan"))
    return out


def eras(z, active, j):
    wk = pd.to_datetime(z["cuts"], unit="s")
    return {e: float(z["R_0.01"][active & (wk >= a) & (wk < b), j].sum()) for e, (a, b) in ERAS.items()}


def gates():
    res = {}
    zf = np.load(fam_path("f2"), allow_pickle=False)
    fam = json.loads(str(zf["family"]))
    stages = [s for s in ("S", "F") if (OUT / f"bench_{s}_f2.npz").exists()]
    for s in stages:
        z, active, R, B, D = _load_d("f2", s)
        rc = G.reality_check(D, mean_block=10, K=999)
        res[f"B1_stage_{s}"] = dict(p=rc["p"], V=rc["V"], T=int(D.shape[0]))
        print(f"B1 Family 2 Reality Check on silver, stage {s}: V = {rc['V']:.2f}, p = {rc['p']:.3f} (T = {D.shape[0]} weeks)")
    dec = stages[-1]
    z, active, R, B, D = _load_d("f2", dec)
    rc = G.reality_check(D, mean_block=10, K=999)
    if dec == "S" and rc["p"] < 0.20:
        raise SystemExit("stage S p < 0.20: run stage F before reading B1")
    res["B1"] = dict(stage=dec, p=rc["p"], V=rc["V"], passed=bool(rc["p"] <= 0.05))
    order = np.argsort(-np.nan_to_num(rc["t"], nan=-9))
    res["top"] = [dict(j=int(j), cfg=fam[j], t=float(rc["t"][j]), mean_d=float(rc["mean"][j]), mean_R=float(R[:, j].mean()),
                       total_R=float(R[:, j].sum())) for j in order[:5]]
    print(f"  -> B1 {'PASS' if res['B1']['passed'] else 'FAIL'} (decisive stage {dec}); top 5 by t:")
    for r in res["top"]:
        c = r["cfg"]
        print(f"     cfg {r['j']:3d} {c['window']}w z{c['lcb_z']:g} {c['pool']} m{c['m']} eq{c['equity_filter']}: t {r['t']:+.2f}, "
              f"mean d {r['mean_d']:+.4f}, mean R {r['mean_R']:+.4f}, total R {r['total_R']:+.1f}")
    ps = []
    rows = {}
    for nm, j in SHADOW.items():
        r1 = G.reality_check(D[:, [j]], mean_block=10, K=999)
        ps.append(r1["p"])
        rows[nm] = dict(j=j, mean_d=float(r1["mean"][0]), p=float(r1["p"]), lb95_d=float(r1["lb95_each"][0]), total_R=float(R[:, j].sum()),
                        eras=eras(z, active, j), cost_gate=cost_gate("f2", z, active, j), long_short=long_short("f2", z, j))
    rej = holm(np.array(ps))
    print("B2 shadow configurations on silver (Holm over 4, familywise 0.05):")
    for (nm, r), rj in zip(rows.items(), rej):
        r["holm_reject"] = bool(rj)
        cg = r["cost_gate"]; ls = r["long_short"]
        print(f"  {nm}: mean d {r['mean_d']:+.4f}/wk (lb {r['lb95_d']:+.4f}), p {r['p']:.3f} -> {'SIGNIFICANT' if rj else 'not significant'}; "
              f"total R {r['total_R']:+.1f}; eras " + ", ".join(f"{e} {v:+.1f}" for e, v in r["eras"].items()) +
              f"; cost gate mean {cg['mean']:+.4f} (lb {cg['lb95']:+.4f}), +2bp {cg['stress_mean']:+.4f}, DD {cg['dd_base']:.0%}->{cg['dd_stress']:.0%} "
              f"{'PASS' if cg['passed'] else 'FAIL'}; long {ls['long']['n']} x {ls['long']['mean_R']:+.3f}R, short {ls['short']['n']} x {ls['short']['mean_R']:+.3f}R")
    res["B2"] = rows
    pb, _ = G.pbo(z["R_0.01"][active])
    res["pbo"] = pb
    print(f"PBO (silver, 144 configurations) = {pb:.3f}")
    if (OUT / "bench_BASE_zoo.npz").exists():
        z0, a0, R0, B0, D0 = _load_d("zoo", "BASE")
        r1 = G.reality_check(D0[:, [0]], mean_block=10, K=999)
        res["B3"] = dict(mean_R=float(R0[:, 0].mean()), mean_B=float(B0[:, 0].mean()), mean_d=float(r1["mean"][0]), p=float(r1["p"]),
                         lb95=float(r1["lb95_each"][0]), total_R=float(R0[:, 0].sum()), eras=eras(z0, a0, 0), passed=bool(r1["lb95_each"][0] > 0))
        b3 = res["B3"]
        print(f"B3 (C7 as frozen) zoo BASE on silver: mean R {b3['mean_R']:+.4f}/wk, benchmark {b3['mean_B']:+.4f}, mean d {b3['mean_d']:+.4f} "
              f"(lb {b3['lb95']:+.4f}), p {b3['p']:.3f}, total R {b3['total_R']:+.1f} -> {'PASS' if b3['passed'] else 'FAIL'}")
    (OUT / "gates_xag.json").write_text(json.dumps(res, indent=1, default=float))
    print("->", OUT / "gates_xag.json")


if __name__ == "__main__":
    mp.freeze_support()
    cmd = sys.argv[1]
    if cmd == "family":
        family(sys.argv[2])
    elif cmd == "bench":
        bench(sys.argv[2], sys.argv[3], int(sys.argv[4]) if len(sys.argv) > 4 else 6)
    elif cmd == "gates":
        gates()
    else:
        raise SystemExit(__doc__)
