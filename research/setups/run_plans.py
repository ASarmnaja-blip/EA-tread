"""Runs docs/plans/P01..P15 (rules P00_COMMON.md). Usage: python research/setups/run_plans.py P01 [P02 ...]  -> data/setups/<plan>_rows.csv
and data/setups/<plan>_verdict.csv. `python research/setups/run_plans.py report` merges every verdict into data/setups/all_verdicts.csv."""
from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import engine_s as E  # noqa: E402
import plans_gen as G  # noqa: E402

METALS = ("XAUUSD", "XAGUSD")
ALL = METALS + E.MARKETS
INTRA = ("M5", "M15", "H1")
CFG = {
    "P01": dict(gen=G.gen_P01, tfs={"M15": ALL}, tod=True),
    "P02": dict(gen=G.gen_P02, tfs={"M5": METALS, "M15": ALL}),
    "P03": dict(gen=G.gen_P03, tfs={"M5": ALL, "M15": ALL}),
    "P04": dict(gen=G.gen_P04, tfs={"D1": ALL + ("GOLD_DUKAS",), "H4": ALL + ("GOLD_DUKAS",)}),
    "P05": dict(gen=G.gen_P05, tfs={tf: ALL for tf in INTRA}),
    "P06": dict(gen=G.gen_P06, tfs={tf: ALL for tf in INTRA}),
    "P07": dict(gen=G.gen_P07, tfs={tf: ALL for tf in INTRA}),
    "P08": dict(gen=G.gen_P08, tfs={tf: ALL for tf in INTRA}),
    "P09": dict(gen=G.gen_P09, tfs={tf: ALL for tf in INTRA}),
    "P10": dict(gen=G.gen_P10, tfs={tf: ALL for tf in INTRA}),
    "P11": dict(gen=G.gen_P11, tfs={tf: ALL for tf in INTRA}, post=G.post_P11),
    "P12": dict(gen=G.gen_P12, tfs={tf: ALL for tf in INTRA}),
    "P13": dict(gen=G.gen_P13, tfs={tf: ALL for tf in INTRA}),
    "P14": dict(gen=G.gen_P14, tfs={tf: ALL for tf in INTRA}),
    "P15": dict(gen=None, tfs={tf: ALL for tf in ("M15", "M30", "H1", "H4", "D1")}, modes=("tp", "struct")),
}
T0 = time.time()
log = lambda *a: print(f"[{time.time() - T0:6.0f}s]", *a, flush=True)


def run_one(plan, gen, tfs, modes=("tp", "unc"), tod=False, post=None, mask_fn=None):
    rows = []
    for tf, mkts in tfs.items():
        for mkt in mkts:
            try:
                B = E.bars(mkt, tf)
            except (FileNotFoundError, KeyError, ValueError):
                continue
            try:
                Vs = gen(B, mkt, tf)
            except (FileNotFoundError, KeyError, ValueError, IndexError) as ex:
                log(f"  {plan} {mkt} {tf}: skipped ({type(ex).__name__}: {ex})"); continue
            for variant, O in Vs.items():
                if O is None or not len(O):
                    continue
                O = O.reset_index(drop=True)
                for mode in modes:
                    T = E.simulate(B, E.sym_of(mkt), O, mode)
                    if post is not None and len(T):
                        T = T[post(T, O)].reset_index(drop=True)
                    if not len(T):
                        continue
                    for sname, m in E.samples(mkt, T.t.to_numpy()).items():
                        TT = T[m].reset_index(drop=True)
                        if len(TT) < 5:
                            continue
                        mb = mask_fn(B) if mask_fn else None
                        ctl = E.control(B, E.sym_of(mkt), O, TT, mode, mask_bars=mb, tod=tod)
                        yrs = (TT.t.max() - TT.t.min()) / (365.25 * 86400) if len(TT) > 1 else 0.1
                        rows.append(E.summarize(plan, tf, variant, mode, mkt, sname, TT, ctl, yrs))
            log(f"  {plan} {mkt} {tf}: {sum(len(v) for v in Vs.values())} orders")
        E.drop_cache()
    return pd.DataFrame(rows)


def main():
    if sys.argv[1:2] == ["report"]:
        for f in sorted(E.OUT.glob("P[0-1][0-9]_rows.csv")):
            D = pd.read_csv(f)
            if f.stem.startswith("P16") or not len(D):
                continue
            E.verdict(D).to_csv(E.OUT / f.name.replace("_rows", "_verdict"), index=False)
        V = pd.concat([pd.read_csv(f) for f in sorted(E.OUT.glob("P[0-1][0-9]_verdict.csv")) if not f.stem.startswith("P16")])
        V.to_csv(E.OUT / "all_verdicts.csv", index=False)
        print(V.groupby("plan").PASS.agg(["sum", "size"]).to_string()); return
    for plan in sys.argv[1:]:
        cfg = CFG[plan]
        if plan == "P15":
            D = pd.concat([run_one(plan, lambda B, m, tf, k=k: G.gen_P15(B, m, tf, k), cfg["tfs"], modes=cfg["modes"], mask_fn=lambda B: B.ctl_mask)
                           for k in (2, 3)])
        else:
            D = run_one(plan, cfg["gen"], cfg["tfs"], modes=cfg.get("modes", ("tp", "unc")), tod=cfg.get("tod", False), post=cfg.get("post"))
        D.to_csv(E.OUT / f"{plan}_rows.csv", index=False)
        V = E.verdict(D) if len(D) else pd.DataFrame()
        V.to_csv(E.OUT / f"{plan}_verdict.csv", index=False)
        log(f"{plan}: {len(D)} rows, PASS {int(V.PASS.sum()) if len(V) else 0} of {len(V)}")


if __name__ == "__main__":
    main()
