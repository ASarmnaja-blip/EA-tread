"""Protocol Amendment 3 - current-era route: ONE full-DISC-pass candidate that failed VAL may be
tested on HOLD (2021-01..2026-08), spending the next alpha_j = 0.05 * 2^-j.
Usage: python research/foundry/current_era.py <batch_fn> <spec_name> <cell> <dir>"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import engine as E  # noqa: E402
import families as FAM  # noqa: E402
from run_batch import OUT, STATE, TRIALS, run_spec, state, disc_pass_R  # noqa: E402


def main(batch_fn, spec_name, cell, dn) -> int:
    os.chdir(E.ROOT)
    st = state()
    tag = f"CURRENT_ERA:{batch_fn}:{spec_name}:{cell}:{dn}"
    if tag in st.get("current_era", []):
        print("already tested"); return 1
    H, D, cuts, cell_arr = E.load()
    cbH = np.where(H.week >= 0, cell_arr[np.clip(H.week, 0, len(cell_arr) - 1)], "")
    cbD = np.where(D.week >= 0, cell_arr[np.clip(D.week, 0, len(cell_arr) - 1)], "")
    sp = [s for s in getattr(FAM, batch_fn)(H, D) if s.name == spec_name][0]
    rng = np.random.default_rng(abs(hash(tag)) % 2 ** 32)
    B, cb, gross, ctrl = run_spec(sp, H, D, cbH, cbD, rng)
    dm = {"both": np.ones(len(sp.dirs), bool), "long": sp.dirs > 0, "short": sp.dirs < 0}[dn]
    sb = (sp.stop / (sp.eprice if sp.eprice is not None else B.o[sp.ent]) * 1e4)[dm]
    args = (spec_name, B, cb, sp.ent[dm], sp.dirs[dm], gross[dm], ctrl[dm])
    d = E.evaluate(*args, periods=("DISC",), cells=[cell], stop_bp=sb)[0]
    assert disc_pass_R(d), d
    st["hold_looks"] += 1
    alpha = 0.05 * 2 ** -st["hold_looks"]
    h = E.evaluate(*args, periods=("HOLD",), cells=[cell], stop_bp=sb)[0]
    h["p_net"] = E.one_sided_p(h.get("t_R", np.nan)); h["alpha"] = alpha
    h["pass_hold"] = bool(h.get("n", 0) >= 20 and h["net"] > 0 and h["net_stress"] > 0 and h.get("net_R", -1) > 0
                          and h["excess"] > 0 and h["p_net"] < alpha)
    print("DISC", {k: (round(v, 4) if isinstance(v, float) else v) for k, v in d.items()})
    print(f"HOLD look {st['hold_looks']} alpha {alpha:.5f}:",
          {k: (round(v, 4) if isinstance(v, float) else v) for k, v in h.items()})
    pd.DataFrame([dict(d, stage="DISC"), dict(h, stage="HOLD-current-era")]).assign(batch=tag).to_csv(
        TRIALS, mode="a", header=False, index=False)
    st.setdefault("current_era", []).append(tag)
    STATE.write_text(json.dumps(st, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:5]))
