"""Protocol Amendment 2: send ONE diagnosis-nominated candidate straight to VAL
(counts in M like any other; VAL/HOLD gates unchanged).
Usage: python research/foundry/nominate.py <batch_fn> <spec_name> <cell>"""
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
from run_batch import OUT, STATE, TRIALS, run_spec, state  # noqa: E402


def main(batch_fn, spec_name, cell) -> int:
    os.chdir(E.ROOT)
    st = state()
    tag = f"NOMINATE:{batch_fn}:{spec_name}:{cell}"
    if tag in st.get("nominated", []):
        print("already nominated; not repeated"); return 1
    nom_disc = [r for r in (st.get("nominated_disc") or [])]
    H, D, cuts, cell_arr = E.load()
    cbH = np.where(H.week >= 0, cell_arr[np.clip(H.week, 0, len(cell_arr) - 1)], "")
    cbD = np.where(D.week >= 0, cell_arr[np.clip(D.week, 0, len(cell_arr) - 1)], "")
    sp = [s for s in getattr(FAM, batch_fn)(H, D) if s.name == spec_name][0]
    rng = np.random.default_rng(abs(hash(tag)) % 2 ** 32)
    B, cb, gross, ctrl = run_spec(sp, H, D, cbH, cbD, rng)
    sb = sp.stop / (sp.eprice if sp.eprice is not None else B.o[sp.ent]) * 1e4
    d = E.evaluate(spec_name, B, cb, sp.ent, sp.dirs, gross, ctrl, periods=("DISC",), cells=[cell], stop_bp=sb)[0]
    if not (d.get("t_R", 0) >= 2.0 and d.get("t_excess_R", 0) >= 3.0 and d["net"] > 0):
        print("nomination conditions not met in DISC:", {k: d.get(k) for k in ("t_R", "t_excess_R", "net")}); return 1
    st["m_val"] += 1
    M = st["m_val"]
    v = E.evaluate(spec_name, B, cb, sp.ent, sp.dirs, gross, ctrl, periods=("VAL",), cells=[cell], stop_bp=sb)[0]
    v["p_net"] = E.one_sided_p(v.get("t_R", np.nan)); v["M"] = M
    v["pass_val"] = bool(v.get("n", 0) >= 20 and v["net"] > 0 and v.get("net_R", -1) > 0 and v["excess"] > 0
                         and v["p_net"] < 0.05 / M)
    rows = [dict(d, stage="DISC-nominated"), dict(v, stage="VAL")]
    print(f"{tag}: DISC t_R {d['t_R']:.2f} excess t_R {d['t_excess_R']:.2f}")
    print(f"VAL: n {v.get('n')} net {v.get('net', np.nan):+.2f} bp  R {v.get('net_R', np.nan):+.3f}  t_R {v.get('t_R', np.nan):.2f}  "
          f"excess {v.get('excess', np.nan):+.2f}  p {v['p_net']:.4f} vs {0.05 / M:.4f} (M={M}) -> {'PASS' if v['pass_val'] else 'FAIL'}")
    if v["pass_val"]:
        st["hold_looks"] += 1
        alpha = 0.05 * 2 ** -st["hold_looks"]
        h = E.evaluate(spec_name, B, cb, sp.ent, sp.dirs, gross, ctrl, periods=("HOLD",), cells=[cell], stop_bp=sb)[0]
        h["p_net"] = E.one_sided_p(h.get("t_R", np.nan)); h["alpha"] = alpha
        h["pass_hold"] = bool(h.get("n", 0) >= 20 and h["net"] > 0 and h["net_stress"] > 0 and h.get("net_R", -1) > 0
                              and h["excess"] > 0 and h["p_net"] < alpha)
        rows.append(dict(h, stage="HOLD"))
        print(f"HOLD (look {st['hold_looks']}, alpha {alpha:.4f}): n {h.get('n')} net {h['net']:+.2f} bp stress {h['net_stress']:+.2f} "
              f"R {h.get('net_R', np.nan):+.3f} t_R {h.get('t_R', np.nan):.2f} p {h['p_net']:.4f} -> {'PASS' if h['pass_hold'] else 'FAIL'}")
    pd.DataFrame(rows).assign(batch=tag).to_csv(TRIALS, mode="a", header=False, index=False)
    pd.DataFrame(rows).to_csv(OUT / f"nominate_{spec_name}_{cell.replace('/', '-').replace('*', 'x')}.csv", index=False)
    st.setdefault("nominated", []).append(tag)
    save_state(st)
    return 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:4]))
