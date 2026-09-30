"""Random-router benchmark B_{j,k} for the 144-configuration family (docs/WRWR_CONTRACT_PREREG.md v6).
For configuration j every champion slot of the actual cut-known champion set is replaced by a uniformly random candidate
with the same exit configuration that is eligible at the cut (n >= 10 shadow trades in the window); the whole C2
event-driven path is simulated (f = 1 %, causal vol_scale); the weekly R of many seeded paths is averaged.
Usage: python research/wrwr/run_bench.py S|F|BASE [workers]      (S: 500 paths x 144 cfg; F: 10,000 x 144; BASE: 10,000 x BASE)
Writes data/wrwr/bench_<stage>.npz (B mean, standard error, path counts)."""
from __future__ import annotations

import json
import multiprocessing as mp
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import contracts as K  # noqa: E402
import portfolio as PF  # noqa: E402

import os  # noqa: E402
SET = os.environ.get("WRWR_SET", "")                      # "" = zoo family, "f2" = Family 2
SUF = f"_{SET}" if SET else ""
CACHE = K.ROOT / "data" / "wrwr" / f"cache_pool{SUF}"
FAM = K.ROOT / "data" / "wrwr" / f"family_XAUUSD{SUF}.npz"
WINDOWS = (26, 52, 78)
MINN = 10
STAGES = {"S": dict(paths=500, configs=None), "F": dict(paths=2_000, configs=None), "BASE": dict(paths=10_000, configs="BASE")}
_G = {}


def build_cache():
    sys.path.insert(0, str(K.ROOT / "research" / "foundry"))
    import engine as E
    H, _, cuts, cell = E.load()
    loader = None
    if SET == "f2":
        import build_f2 as BF2
        loader = BF2.loader
    P = PF.load_pool("XAUUSD", ["H1", "H4", "D1"], cuts, verify=True, loader=loader)
    S1, S2, NN = PF.shadow_stats(P)
    vs = K.causal_vol_scale(H.t, H.c, H.h, H.l, cuts, mode="historical", bar_seconds=3600)
    active = np.array([c != "" for c in cell] + [False] * (len(cuts) - len(cell)))[: len(cuts)]
    PF.save_pool_cache(P, CACHE, extra=dict(NN=NN, vol_scale=vs, active=active))
    return P


def init_worker():
    P = PF.load_pool_cache(CACHE)
    _G["P"] = P
    _G["vs"] = np.load(CACHE / "vol_scale.npy")
    NN = np.load(CACHE / "NN.npy")
    cum = np.c_[np.zeros((NN.shape[0], 1)), np.cumsum(NN, axis=1)]
    k = np.arange(NN.shape[1])
    _G["elig"] = {}
    for L in WINDOWS:
        a = np.maximum(k - L + 1, 0)
        _G["elig"][L] = (cum[:, k + 1] - cum[:, a]) >= MINN
    z = np.load(FAM, allow_pickle=False)
    _G["fam"] = json.loads(str(z["family"]))
    _G["champs"] = json.loads(str(z["champs"]))
    _G["slots"] = {}


def slots_for(j):
    """Per week, per champion rank: sorted array of candidate ids drawn from (same pool, eligible, same exit config)."""
    if j in _G["slots"]:
        return _G["slots"][j]
    P = _G["P"]; cfg = _G["fam"][j]
    pool_mask = {"H1": P.tf == "H1", "H4": P.tf == "H4", "D1": P.tf == "D1", "H1+H4+D1": np.ones(len(P.tf), bool)}[cfg["pool"]]
    elig = _G["elig"][cfg["window"]]
    ch = _G["champs"][str(j)]
    out = {}
    for k, w in enumerate(ch):
        if not w:
            continue
        sets = []
        for c in w:
            m = pool_mask & elig[:, k] & (P.exit_cfg == P.exit_cfg[c])
            ids = np.flatnonzero(m)
            ids = ids[np.argsort(P.rank_key[ids])]                  # candidate-hash order (determinism)
            sets.append(ids)
        out[k] = sets
    _G["slots"][j] = out
    return out


def task(args):
    j, lo, hi = args
    P = _G["P"]; vs = _G["vs"]; NW = len(P.cuts)
    slots = slots_for(j)
    if _G.get("ev_j") != j:                                   # event cache is per configuration (bounded memory)
        _G["evcache"] = {}; _G["ev_j"] = j
    weeks = sorted(slots)
    sum1 = np.zeros(NW); sum2 = np.zeros(NW)
    for p in range(lo, hi):
        rng = np.random.default_rng([j, p])
        champs = [[] for _ in range(NW)]
        for k in weeks:
            picks = []
            for r, S in enumerate(slots[k]):
                if not len(S):
                    continue
                u = rng.random()
                if r > 0 and picks:
                    avail = S[~np.isin(S, picks)]
                    if not len(avail):
                        continue
                    picks.append(int(avail[int(u * len(avail))]))
                else:
                    picks.append(int(S[int(u * len(S))]))
            champs[k] = picks
        wr, _, _ = PF.simulate(P, champs, vs, f=0.01, evcache=_G["evcache"])
        sum1 += wr; sum2 += wr * wr
    return j, hi - lo, sum1, sum2


def main():
    stage = sys.argv[1]
    workers = int(sys.argv[2]) if len(sys.argv) > 2 else 6
    if stage not in STAGES:
        raise SystemExit("stage must be S, F or BASE")
    t0 = time.time()
    if not (CACHE / "meta.json").exists():
        build_cache(); print(f"pool cache built ({time.time() - t0:.0f}s)", flush=True)
    z = np.load(FAM, allow_pickle=False)
    fam = json.loads(str(z["family"]))
    cfgs = list(range(len(fam)))
    if STAGES[stage]["configs"] == "BASE":
        cfgs = [j for j, c in enumerate(fam) if (c["window"], c["lcb_z"], c["pool"], c["m"], c["equity_filter"]) == (52, 1.0, "H1", 2, 0)]
    import os
    npaths = int(os.environ.get("WRWR_BENCH_PATHS", STAGES[stage]["paths"]))      # smoke tests only; stages are frozen
    chunk = 25 if npaths <= 500 else 100
    tasks = [(j, lo, min(lo + chunk, npaths)) for j in cfgs for lo in range(0, npaths, chunk)]
    NW = len(z["cuts"])
    S1 = np.zeros((NW, len(fam))); S2 = np.zeros((NW, len(fam))); cnt = np.zeros(len(fam))
    done = 0
    with mp.Pool(workers, initializer=init_worker) as pool:
        for j, n, s1, s2 in pool.imap_unordered(task, tasks):
            S1[:, j] += s1; S2[:, j] += s2; cnt[j] += n; done += 1
            if done % max(len(tasks) // 20, 1) == 0:
                print(f"  {done}/{len(tasks)} tasks ({time.time() - t0:.0f}s)", flush=True)
    B = np.where(cnt > 0, S1 / np.maximum(cnt, 1), np.nan)
    var = S2 / np.maximum(cnt, 1) - B ** 2
    SE = np.sqrt(np.maximum(var, 0) / np.maximum(cnt, 1))
    out = K.ROOT / "data" / "wrwr" / f"bench_{stage}{SUF}{'_smoke' if npaths != STAGES[stage]['paths'] else ''}.npz"
    np.savez_compressed(out, B=B, SE=SE, paths=cnt, configs=np.array(cfgs), stage=stage, family_sha=str(z["meta"]))
    print(f"{stage}: {len(tasks)} tasks, paths per config {int(cnt[cfgs[0]])}, -> {out.name} ({time.time() - t0:.0f}s)")
    se_mean = np.nanmean(SE[:, cfgs], axis=0)
    print(f"mean weekly benchmark SE (R) per config: median {np.median(se_mean):.4f}, max {se_mean.max():.4f}")


if __name__ == "__main__":
    mp.freeze_support()
    main()
