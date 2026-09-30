"""Read the frozen WRWR gates (docs/WRWR_MANIFEST.md, contract v6) from the family results and a benchmark stage.
Usage: python research/wrwr/analyze_gates.py BASE|S|F [--pbo] [--cost]
  BASE : endpoint 1 only (BASE alone vs its 10,000-path random-router benchmark)
  S / F: endpoint 2 (studentized Reality Check over the benchmarked configurations), sensitivities block 4 / 26
  --pbo : endpoint 3 (PBO point estimate and 999-replicate upper bound) on the full family
  --cost: endpoint 4 for BASE and the 3 configurations with the largest t (stress run needs the pool cache)
Writes data/wrwr/gates_<stage>.json."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import contracts as K  # noqa: E402
import gates as G  # noqa: E402

import os  # noqa: E402
SET = os.environ.get("WRWR_SET", "")
SUF = f"_{SET}" if SET else ""
FAM = K.ROOT / "data" / "wrwr" / f"family_XAUUSD{SUF}.npz"


def main():
    stage = sys.argv[1]
    do_pbo = "--pbo" in sys.argv; do_cost = "--cost" in sys.argv
    z = np.load(FAM, allow_pickle=False)
    fam = json.loads(str(z["family"])); active = z["active"]
    R = z["R_0.01"][active]                                     # T x 144 weekly R at f = 1 %
    T = R.shape[0]
    b = np.load(K.ROOT / "data" / "wrwr" / f"bench_{stage}{SUF}.npz", allow_pickle=False)
    cfgs = [int(x) for x in b["configs"]]
    B = b["B"][active][:, cfgs]
    D = R[:, cfgs] - B
    base_j = [j for j, c in enumerate(fam) if (c["window"], c["lcb_z"], c["pool"], c["m"], c["equity_filter"]) == (52, 1.0, "H1", 2, 0)][0]
    out = dict(stage=stage, weeks=int(T), paths=int(b["paths"][cfgs[0]]), n_config=len(cfgs))
    print(f"stage {stage}: {len(cfgs)} configurations, {int(b['paths'][cfgs[0]])} paths each, T = {T} active weeks")
    se_time = np.sqrt((b["SE"][active][:, cfgs] ** 2).sum(0)) / T
    print(f"benchmark Monte Carlo SE of the time-averaged weekly B (R): max {se_time.max():.4f}  (contract target < 0.01)")
    out["bench_se_time_avg_max"] = float(se_time.max())
    for blk in (10, 4, 26):
        r = G.reality_check(D, mean_block=blk, K=999)
        out[f"rc_block{blk}"] = dict(p=r["p"], V=r["V"])
        print(f"Reality Check (mean block {blk:2d}): V = {r['V']:.2f}  p = {r['p']:.3f}")
        if blk == 10:
            rc = r
    order = np.argsort(-np.nan_to_num(rc["t"], nan=-9))
    print("top 8 configurations by studentized mean(d):")
    rows = []
    for i in order[:8]:
        j = cfgs[i]; c = fam[j]
        rows.append(dict(j=j, **c, mean_d=float(rc["mean"][i]), t=float(rc["t"][i]), p_each=float(rc["p_each"][i]), lb95=float(rc["lb95_each"][i]),
                         mean_R=float(R[:, j].mean()), mean_B=float(B[:, i].mean())))
        print(f"  cfg {j:3d} {c['window']}w z{c['lcb_z']} {c['pool']} m{c['m']} eq{c['equity_filter']:2d}: mean d {rc['mean'][i]:+.4f}, t {rc['t'][i]:+.2f}, "
              f"p_each {rc['p_each'][i]:.3f}, lb95 {rc['lb95_each'][i]:+.4f}, mean R {R[:, j].mean():+.4f}, mean B {B[:, i].mean():+.4f}")
    out["top"] = rows
    if base_j in cfgs:
        i = cfgs.index(base_j)
        r1 = G.reality_check(D[:, [i]], mean_block=10, K=999)
        out["base"] = dict(mean_d=float(r1["mean"][0]), p=float(r1["p"]), lb95=float(r1["lb95_each"][0]), mean_R=float(R[:, base_j].mean()),
                           mean_B=float(B[:, i].mean()))
        print(f"BASE alone: mean R {R[:, base_j].mean():+.4f}/wk, benchmark {B[:, i].mean():+.4f}/wk, mean d {r1['mean'][0]:+.4f}, "
              f"one-sided p {r1['p']:.3f}, 95% lower bound {r1['lb95_each'][0]:+.4f}  (pass needs p <= 0.05 and lb95 > 0)")
    if do_pbo:
        pb, lam = G.pbo(R)
        up, vals = G.pbo_upper(R, K=999)
        out["pbo"] = dict(point=pb, upper95=up)
        print(f"PBO = {pb:.3f}, bootstrap upper 95% = {up:.3f}  (robust needs upper <= 0.20; lower bound >= 0.50 = stop)")
    if do_cost:
        import portfolio as PF
        P = PF.load_pool_cache(K.ROOT / "data" / "wrwr" / f"cache_pool{SUF}")
        vs = np.load(K.ROOT / "data" / "wrwr" / f"cache_pool{SUF}" / "vol_scale.npy")
        champs = json.loads(str(z["champs"]))
        eq = z["EQ_0.01"][active]
        res = []
        for j in [base_j] + [cfgs[i] for i in order[:3]]:
            ch = [[int(x) for x in w] for w in champs[str(j)]]
            wr, eqs, _ = PF.simulate(P, ch, vs, f=0.01, stress=True)
            lb, m = G.lower_bound_mean(R[:, j])
            dd_base = float((1 - eq[:, j] / np.maximum.accumulate(eq[:, j])).max())
            dd_str = float((1 - eqs[active] / np.maximum.accumulate(eqs[active])).max())
            res.append(dict(j=j, base_mean=m, base_lb95=lb, stress_mean=float(wr[active].mean()), dd_base=dd_base, dd_stress=dd_str,
                            passed=bool(lb > 0 and wr[active].mean() > 0 and dd_str <= 1.25 * dd_base)))
            print(f"  cost gate cfg {j}: base mean {m:+.4f} (lb95 {lb:+.4f}), +2bp mean {wr[active].mean():+.4f}, DD {dd_base:.2f} -> {dd_str:.2f}, "
                  f"{'PASS' if res[-1]['passed'] else 'FAIL'}")
        out["cost_gate"] = res
    (K.ROOT / "data" / "wrwr" / f"gates_{stage}{SUF}.json").write_text(json.dumps(out, indent=1, default=float))


if __name__ == "__main__":
    main()
