"""End-to-end tests of the SHADOW pipeline (forward_shadow.py):
 A. equivalence: on the full data the weekly champions of every shadow configuration equal the research pipeline's champions
    (family_XAUUSD_f2.npz, cache_pool_f2) at every cut up to 2026-08-07;
 B. causality: with the data truncated at the cut 2026-08-14 22:15 UTC the champions at every cut up to that one equal the full-data
    run's champions (nothing after the cut leaks into the selection, and trades that resolved before the cut are counted).
Run directly; takes about 10 minutes."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import contracts as K  # noqa: E402
import forward_shadow as FS  # noqa: E402

RES_INDEX = {"F2-66": 66, "F2-78": 78, "F2-134": 134, "F2-86": 86}


def tup(cd):
    return (cd["tf"], cd["setup"], cd["mode"], cd["k_atr"], cd["exit"], cd["hold"])


def champ_tuples(P, out, name):
    ch = out[name][0]
    return [[tup(P.cands[c]) for c in w] for w in ch]


def main():
    zm = json.loads(str(np.load(K.ROOT / "data" / "wrwr" / "tables_XAUUSD_H1_f2.npz", allow_pickle=False)["meta"]))
    salt = K.sha_bytes(np.frombuffer((zm["code_sha"] + zm["f2_code_sha"]).encode(), np.uint8))       # the research tie-break salt
    P, out, active, vs, cuts, cell, base, data_end = FS.compute(None, salt=salt)
    full = {n: champ_tuples(P, out, n) for n in FS.CONFIGS}
    # ---- A
    meta = json.loads((K.ROOT / "data" / "wrwr" / "cache_pool_f2" / "meta.json").read_text())
    rc = meta["cands"]
    z = np.load(K.ROOT / "data" / "wrwr" / "family_XAUUSD_f2.npz", allow_pickle=False)
    champs = json.loads(str(z["champs"]))
    kmax = int(np.searchsorted(cuts, int(pd.Timestamp("2026-08-07 22:15:00").timestamp())))
    n_cmp = n_diff = 0
    for name, j in RES_INDEX.items():
        res = [[tup(rc[c]) for c in w] for w in champs[str(j)]]
        for k in range(kmax):
            n_cmp += 1
            if full[name][k] != res[k]:
                n_diff += 1
                if n_diff <= 3:
                    print("DIFF", name, k, pd.Timestamp(cuts[k], unit="s"), full[name][k], res[k])
    assert n_diff == 0, f"{n_diff} of {n_cmp} champion sets differ from the research pipeline"
    print(f"PASS A: forward pipeline = research pipeline for {n_cmp} (config, cut) champion sets up to 2026-08-07")
    # ---- B
    tcut = pd.Timestamp("2026-08-14 22:15:00")
    P2, out2, active2, vs2, cuts2, cell2, base2, data_end2 = FS.compute(tcut.strftime("%Y-%m-%d %H:%M:%S"), salt=salt)
    trunc = {n: champ_tuples(P2, out2, n) for n in FS.CONFIGS}
    k2 = int(np.searchsorted(cuts2, int(tcut.timestamp())))
    assert cuts2[k2] == int(tcut.timestamp()) and data_end2 <= int(tcut.timestamp()) + 3600, (pd.Timestamp(cuts2[k2], unit="s"), pd.Timestamp(data_end2, unit="s"))
    n_cmp = n_diff = 0
    for name in FS.CONFIGS:
        for k in range(60, k2 + 1):
            n_cmp += 1
            if trunc[name][k] != full[name][k]:
                n_diff += 1
                if n_diff <= 3:
                    print("DIFF", name, k, pd.Timestamp(cuts[k], unit="s"), trunc[name][k], full[name][k])
    assert n_diff == 0, f"{n_diff} of {n_cmp} champion sets change when the data after the cut is removed"
    print(f"PASS B: with data truncated at {tcut}, {n_cmp} champion sets up to that cut are identical to the full-data run (no leak, live-edge trades handled)")
    print("ALL FORWARD SHADOW TESTS PASS")


if __name__ == "__main__":
    main()
