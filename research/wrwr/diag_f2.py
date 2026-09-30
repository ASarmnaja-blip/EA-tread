"""Diagnostics for the Family 2 result (descriptive, not a gate): what do the champions of the significant configurations
look like, and is the positive d a drift-persistence effect? For chosen configurations it reports (a) how often each candidate
kind is champion, (b) the long / short split of the live trades and the net R by direction, (c) the same for the random-router
candidates in the same slots (drift exposure of the benchmark), (d) the contribution of the 5 most frequent candidates."""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import contracts as K  # noqa: E402
import portfolio as PF  # noqa: E402

SUF = "_f2"
P = PF.load_pool_cache(K.ROOT / "data" / "wrwr" / f"cache_pool{SUF}")
vs = np.load(K.ROOT / "data" / "wrwr" / f"cache_pool{SUF}" / "vol_scale.npy")
z = np.load(K.ROOT / "data" / "wrwr" / f"family{SUF}_XAUUSD.npz".replace("family_f2_XAUUSD", "family_XAUUSD_f2"), allow_pickle=False) \
    if False else np.load(K.ROOT / "data" / "wrwr" / "family_XAUUSD_f2.npz", allow_pickle=False)
fam = json.loads(str(z["family"])); champs = json.loads(str(z["champs"]))
active = z["active"]
C = P.cands
for j in (66, 134, 86, 78):
    c = fam[j]
    ch = [[int(x) for x in w] for w in champs[str(j)]]
    cnt = Counter(C[x]["setup"].split("|")[0] + f"|{C[x]['setup'].split('|')[1]}" for w in ch for x in w)
    mode = Counter(C[x]["mode"] for w in ch for x in w)
    exits = Counter((C[x]["tf"], C[x]["exit"]) for w in ch for x in w)
    log = []
    wr, eq, cn = PF.simulate(P, ch, vs, f=0.01, log=log)
    L = pd.DataFrame(log, columns=["k", "c", "entry_t", "exit_t", "lots", "R", "pnl", "eq"])
    row = {}
    for i, (kk, cc, et) in enumerate(zip(L.k, L.c, L.entry_t)):
        pos = int(np.searchsorted(P.entry_t[cc], et))
        row[i] = int(P.dir[cc][pos])
    L["dir"] = pd.Series(row)
    print(f"\n=== cfg {j}: {c['window']}w z{c['lcb_z']} {c['pool']} m{c['m']} eq{c['equity_filter']}: live trades {len(L)}, total weekly R {wr[active].sum():+.1f}")
    print("  top candidate kinds:", cnt.most_common(6))
    print("  FOLLOW/FADE:", dict(mode), " exits:", exits.most_common(4))
    if len(L):
        lg = L[L.dir > 0]; sh = L[L.dir < 0]
        print(f"  long trades {len(lg)} (net R sum {lg.R.sum():+.1f}, mean {lg.R.mean():+.3f}); short trades {len(sh)} (net R sum {sh.R.sum():+.1f}, mean {sh.R.mean():+.3f})")
        big = L.assign(kind=[C[x]["setup"].split("|")[0] for x in L.c]).groupby("kind").R.agg(["size", "sum", "mean"]).sort_values("sum", ascending=False)
        print("  R by signal kind (top 5 / bottom 3):"); print(big.head(5).round(2).to_string()); print(big.tail(3).round(2).to_string())
