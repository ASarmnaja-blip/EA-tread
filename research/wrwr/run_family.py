"""Run the pre-registered 144-configuration deployable family (docs/WRWR_CONTRACT_PREREG.md C6) through the event-driven
portfolio (C2, v5: mark-to-market equity) on gold H1 / H4 / D1 for f = 0.5 %, 1 %, 2 %, and write the weekly R matrices
with C5 metadata. No gate statistic is computed here (that needs the frozen manifest and the random-router benchmark).
Writes data/wrwr/family_XAUUSD.npz (+ metadata json) and data/wrwr/family_XAUUSD.xlsx."""
from __future__ import annotations

import hashlib
import itertools
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import contracts as K  # noqa: E402
import portfolio as PF  # noqa: E402
import signals as SG  # noqa: E402

sys.path.insert(0, str(K.ROOT / "research" / "foundry"))
import engine as E  # noqa: E402

WINDOWS, ZS, POOLS, MS, EQF = (26, 52, 78), (0.5, 1.0, 2.0), ("H1", "H4", "D1", "H1+H4+D1"), (1, 2), (0, 26)
FS = (0.005, 0.01, 0.02)
MINN = 10
TFS = ["H1", "H4", "D1"]
CODE = [HERE / "run_family.py", HERE / "portfolio.py", HERE / "contracts.py", HERE / "signals.py"]


def family():
    fam = [dict(window=L, lcb_z=z, pool=p, m=m, equity_filter=e, min_trades=MINN)
           for L, z, p, m, e in itertools.product(WINDOWS, ZS, POOLS, MS, EQF)]
    key = json.dumps([[c["window"], c["lcb_z"], c["pool"], c["m"], c["equity_filter"], c["min_trades"]] for c in fam])
    return fam, hashlib.sha256(key.encode()).hexdigest()


def run(f, P, vs, active, pools, scores, fam):
    NW = len(P.cuts)
    R = np.zeros((NW, len(fam))); EQ = np.zeros((NW, len(fam))); champs_all = {}; counters = []
    twin = {}
    for j, c in enumerate(fam):
        sc = scores[(c["window"], c["lcb_z"])]
        act = active.copy()
        if c["equity_filter"]:
            wr_twin = twin[(c["window"], c["lcb_z"], c["pool"], c["m"])]
            cs = np.r_[0.0, np.cumsum(wr_twin)]
            k = np.arange(NW)
            act &= (cs[k] - cs[np.maximum(k - c["equity_filter"], 0)]) > 0          # weeks k-26..k-1, exits <= cut_k
        ch = PF.champions(sc, pools[c["pool"]], c["m"], P.rank_key, act)
        wr, eq, cnt = PF.simulate(P, ch, vs, f=f, equity0=10_000.0)
        if not c["equity_filter"]:
            twin[(c["window"], c["lcb_z"], c["pool"], c["m"])] = wr
        R[:, j] = wr; EQ[:, j] = eq; champs_all[j] = ch; counters.append(cnt)
    return R, EQ, champs_all, counters


def main():
    t0 = time.time()
    H, _, cuts, cell = E.load()
    P = PF.load_pool("XAUUSD", TFS, cuts, verify=True)
    print(f"pool: {len(P.cands)} candidates (C5 verified), {P.rejected_at_cut} rejected at a cut, {time.time() - t0:.0f}s", flush=True)
    S1, S2, NN = PF.shadow_stats(P)
    vs = K.causal_vol_scale(H.t, H.c, H.h, H.l, cuts, mode="historical", bar_seconds=3600)
    active = np.array([c != "" for c in cell] + [False] * (len(cuts) - len(cell)))[: len(cuts)]
    pools = {"H1": P.tf == "H1", "H4": P.tf == "H4", "D1": P.tf == "D1", "H1+H4+D1": np.isin(P.tf, TFS)}
    fam, fam_sha = family()
    scores = {(L, z): PF.window_scores(S1, S2, NN, L, z, MINN)[0] for L in WINDOWS for z in ZS}
    wk = pd.to_datetime(cuts, unit="s")
    out_npz = {}; rows = []
    yrs = active.sum() / 52.18
    for f in FS:
        R, EQ, champs_all, counters = run(f, P, vs, active, pools, scores, fam)
        out_npz[f"R_{f}"] = R; out_npz[f"EQ_{f}"] = EQ
        if f == 0.01:
            out_npz["champs"] = json.dumps({str(j): [[int(x) for x in w] for w in ch] for j, ch in champs_all.items()})
        for j, c in enumerate(fam):
            r = R[active, j]; eq = EQ[active, j]
            dd = float((1 - eq / np.maximum.accumulate(eq)).max()); cumR = np.cumsum(r); ddR = float((np.maximum.accumulate(cumR) - cumR).max())
            row = dict(f=f, **c, total_R=r.sum(), R_per_year=r.sum() / yrs, maxDD_R=ddR, calmar=(r.sum() / yrs) / max(ddR, 1e-9),
                       final_equity=eq[-1], CAGR=(eq[-1] / 10_000) ** (1 / yrs) - 1 if eq[-1] > 0 else -1.0, maxDD_pct=dd, **counters[j])
            for nm, a in (("L5", 260), ("L3", 156)):
                row[f"{nm}_R"] = R[active, j][-a:].sum()
            for e, (a0, a1) in {"2004-08": ("2004", "2009"), "2009-14": ("2009", "2015"), "2015-20": ("2015", "2021"),
                                "2021-26": ("2021", "2027")}.items():
                row[f"R_{e}"] = R[active & (wk >= a0) & (wk < a1), j].sum()
            rows.append(row)
        print(f"f = {f:.3%} done ({time.time() - t0:.0f}s)", flush=True)
    meta = dict(schema=K.SCHEMA, cost_version=K.COST_VERSION, family_sha=fam_sha, n_config=len(fam), f_levels=list(FS),
                code_sha=K.sha_files(*CODE), cuts_sha=K.sha_bytes(cuts), data_end=int(P.mark_t[-1]),
                tables={tf: dict(array_sha=m["array_sha"], data_sha=m["data_sha"], raw_manifest_sha=m["raw_manifest_sha"],
                                 code_sha=m["code_sha"], rejected_at_cut=m["rejected_at_cut"]) for tf, m in P.meta.items()},
                vol_scale_mode="historical", built=pd.Timestamp.now(tz="UTC").isoformat())
    out = K.ROOT / "data" / "wrwr" / "family_XAUUSD.npz"
    np.savez_compressed(out, cuts=cuts, active=active, vol_scale=vs, family=json.dumps(fam), meta=json.dumps(meta),
                        cand_hash=json.dumps([c["hash"] for c in P.cands]), **out_npz)
    X = pd.DataFrame(rows)
    X.to_excel(K.ROOT / "data" / "wrwr" / "family_XAUUSD.xlsx", index=False)
    pd.set_option("display.width", 250)
    print(f"\nfamily sha256 {fam_sha}; {len(fam)} configurations; {int(active.sum())} active weeks")
    b = X[(X.window == 52) & (X.lcb_z == 1.0) & (X.pool == "H1") & (X.m == 2) & (X.equity_filter == 0)]
    print("BASE (52w, z1, H1, m2):"); print(b[["f", "total_R", "R_per_year", "maxDD_R", "calmar", "CAGR", "maxDD_pct", "L5_R", "L3_R",
                                              "R_2004-08", "R_2009-14", "R_2015-20", "R_2021-26", "entries"]].round(3).to_string(index=False))
    x1 = X[X.f == 0.01].sort_values("total_R", ascending=False)
    print("best 10 of 144 at f = 1% (descriptive):")
    print(x1.head(10)[["window", "lcb_z", "pool", "m", "equity_filter", "total_R", "R_per_year", "maxDD_R", "calmar", "CAGR", "L5_R", "L3_R"]].round(3).to_string(index=False))
    print(f"done {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
