"""Run one registered Foundry batch through DISC -> VAL -> HOLD gates (docs/FOUNDRY_PROTOCOL.md).
Usage: python research/foundry/run_batch.py <batch_name>
VAL numbers are computed only for DISC survivors, HOLD only for VAL survivors."""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import engine as E  # noqa: E402
import families as FAM  # noqa: E402

OUT = E.ROOT / "data" / "foundry"
STATE = OUT / "state.json"
TRIALS = OUT / "trials.csv"
MAX_VAL = 20


def state():
    if STATE.exists():
        return json.loads(STATE.read_text())
    return dict(m_val=0, hold_looks=0, disc_candidates=0, batches=[])


def run_spec(sp, H, D, cellbar_H, cellbar_D, rng):
    B, cb, key = (H, cellbar_H, "hour") if sp.tf == "H1" else (D, cellbar_D, "dow")
    if getattr(sp, "trail", None):
        im, tm, mb = sp.trail
        a = B.atr[sp.ent]
        gross, ex = E.simulate_trail(B, sp.ent, sp.dirs, a, im, tm, mb)
        ctrl = E.matched_control_trail(B, cb, sp.ent, sp.dirs, im, tm, mb, rng, key=key)
        return B, cb, gross, ctrl
    gross, ex = E.simulate(B, sp.ent, sp.dirs, sp.stop, sp.tgt, sp.last, sp.eprice)
    a = B.atr[sp.ent]
    ctrl = E.matched_control(B, cb, sp.ent, sp.dirs, sp.stop / a, sp.tgt / a, sp.last - sp.ent, rng, key=key)
    return B, cb, gross, ctrl


ROUTER_CELLS = {"batch4": ["HIGH/*", "NOTCALM/*", "ALL"], "batch5": ["ALL", "NOTCALM/*"], "batch18": ["ALL", "NOTCALM/*", "HIGH/*"], "batch19": ["ALL"], "batch22": ["ALL", "NOTCALM/*", "HIGH/*"]}   # WPWB router: only these pre-declared cells


def disc_pass_R(r):
    return (r.get("n", 0) >= 60 and r["net"] > 0 and r.get("net_R", -1) > 0 and r["excess"] > 0
            and r.get("t_R", 0) >= 3.0 and r.get("t_excess_R", 0) >= 2.0 and r.get("yr_pos_R", 0) >= 0.6)


def disc_pass(r):
    return (r.get("n", 0) >= 60 and r["net"] > 0 and r["excess"] > 0 and r["t_net"] >= 3.0
            and r["t_excess"] >= 2.0 and r["yr_pos"] >= 0.6)


def main(batch) -> int:
    os.chdir(E.ROOT)
    OUT.mkdir(parents=True, exist_ok=True)
    st = state()
    if batch in st["batches"]:
        print(f"batch {batch} already run; a changed batch needs a new name"); return 1
    t0 = time.time()
    H, D, cuts, cell = E.load()
    cellbar_H = np.where(H.week >= 0, cell[np.clip(H.week, 0, len(cell) - 1)], "")
    cellbar_D = np.where(D.week >= 0, cell[np.clip(D.week, 0, len(cell) - 1)], "")
    specs = getattr(FAM, batch)(H, D)
    rng = np.random.default_rng(abs(hash(batch)) % 2 ** 32)
    rows, keep = [], {}
    for sp in specs:
        B, cb, gross, ctrl = run_spec(sp, H, D, cellbar_H, cellbar_D, rng)
        dir_opts = (("both", np.ones(len(sp.dirs), bool)), ("long", sp.dirs > 0), ("short", sp.dirs < 0))
        if batch in ROUTER_CELLS:
            dir_opts = dir_opts[:1]
        for dn, dm in dir_opts:
            if dm.sum() < 20:
                continue
            name = f"{sp.name}|{dn}"
            sb = (sp.stop / (sp.eprice if sp.eprice is not None else B.o[sp.ent]) * 1e4)[dm]
            rr = E.evaluate(name, B, cb, sp.ent[dm], sp.dirs[dm], gross[dm], ctrl[dm],
                            cells=ROUTER_CELLS.get(batch, E.CELLS if batch == "batch1" else E.CELLS2), stop_bp=sb)
            rows += rr
            keep[name] = (B, cb, sp.ent[dm], sp.dirs[dm], gross[dm], ctrl[dm], sb)
    R = pd.DataFrame(rows)
    R["batch"] = batch
    ok = R[R.n >= 20].copy()
    useR = batch not in ("batch1", "batch2")
    ok["pass_disc"] = ok.apply(lambda r: (disc_pass_R if useR else disc_pass)(r.to_dict()), axis=1)
    st["disc_candidates"] += int(len(ok))
    surv = ok[ok.pass_disc].sort_values("t_R" if useR else "t_net", ascending=False).head(MAX_VAL)
    print(f"batch {batch}: {len(specs)} specs, {len(ok)} DISC candidates (cumulative {st['disc_candidates']}); "
          f"DISC pass {int(ok.pass_disc.sum())}; sent to VAL {len(surv)}  [{time.time() - t0:.0f}s]")
    val_rows, hold_rows = [], []
    if len(surv):
        st["m_val"] += len(surv)
        M = st["m_val"]
        for _, r in surv.iterrows():
            B, cb, ent, dirs, gross, ctrl, sb = keep[r.cand]
            v = E.evaluate(r.cand, B, cb, ent, dirs, gross, ctrl, periods=("VAL",), cells=[r.cell], stop_bp=sb)[0]
            v["p_net"] = E.one_sided_p(v.get("t_R" if useR else "t_net", np.nan))
            v["pass_val"] = bool(v.get("n", 0) >= 20 and v["net"] > 0 and v["excess"] > 0 and v["p_net"] < 0.05 / M
                                 and (not useR or v.get("net_R", -1) > 0))
            v["M"] = M
            val_rows.append(v)
            if v["pass_val"]:
                st["hold_looks"] += 1
                j = st["hold_looks"]
                alpha = 0.05 * 2 ** -j
                h = E.evaluate(r.cand, B, cb, ent, dirs, gross, ctrl, periods=("HOLD",), cells=[r.cell], stop_bp=sb)[0]
                h["p_net"] = E.one_sided_p(h.get("t_R" if useR else "t_net", np.nan))
                h["alpha"] = alpha
                h["pass_hold"] = bool(h.get("n", 0) >= 20 and h["net"] > 0 and h["net_stress"] > 0
                                      and h["excess"] > 0 and h["p_net"] < alpha)
                hold_rows.append(h)
    V_ = pd.DataFrame(val_rows); Hd = pd.DataFrame(hold_rows)
    for df_, nm in ((R, "disc"), (V_, "val"), (Hd, "hold")):
        if len(df_):
            df_.assign(batch=batch, stage=nm).to_csv(OUT / f"{batch}_{nm}.csv", index=False)
    allrows = pd.concat([R.assign(stage="DISC")] + ([V_.assign(stage="VAL", batch=batch)] if len(V_) else [])
                        + ([Hd.assign(stage="HOLD", batch=batch)] if len(Hd) else []))
    allrows.to_csv(TRIALS, mode="a", header=not TRIALS.exists(), index=False)
    st["batches"].append(batch)
    STATE.write_text(json.dumps(st, indent=1))
    pd.set_option("display.width", 250); pd.set_option("display.max_columns", 30)
    cols = ["cand", "cell", "n", "gross", "net", "t_net", "excess", "t_excess", "yr_pos", "long_share"]
    if useR:
        cols = ["cand", "cell", "n", "net", "t_net", "net_R", "t_R", "excess_R", "t_excess_R", "yr_pos_R", "stop_bp_med", "long_share"]
    print("\nDISC survivors:" if len(surv) else "\nno DISC survivor")
    if len(surv):
        print(surv[cols].round(2).to_string(index=False))
    if len(V_):
        print("\nVAL:"); print(V_[[c for c in ["cand", "cell", "n", "net", "t_net", "net_R", "t_R", "excess", "p_net", "M", "pass_val"] if c in V_]].round(4).to_string(index=False))
    if len(Hd):
        print("\nHOLD:"); print(Hd[[c for c in ["cand", "cell", "n", "net", "net_stress", "t_net", "net_R", "t_R", "excess", "p_net", "alpha", "pass_hold"] if c in Hd]].round(4).to_string(index=False))
    # diagnosis material (DISC only): per family variant, ALL cell
    a = ok[(ok.cell == "ALL")].copy()
    a["family"] = a.cand.str.split("|").str[0]
    print("\nDISC diagnosis, ALL cell (gross, net, excess in bp per trade):")
    print(a[[c for c in ["cand", "n", "gross", "net", "t_net", "net_R", "t_R", "excess", "t_excess", "net_dukas", "yr_pos"] if c in a]].round(2).to_string(index=False))
    best = ok.sort_values("t_R" if useR else "t_net", ascending=False).head(15)
    print("\nDISC top 15 by t_net (any cell):")
    print(best[cols].round(2).to_string(index=False))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
