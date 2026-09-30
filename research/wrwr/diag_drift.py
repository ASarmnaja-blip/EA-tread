"""Auditor check (CLAUDE.md role 5): is a configuration's profit SIGNAL TIMING or just the DIRECTION (gold's drift)?
For every live trade of a configuration the same trade (same direction, tf, stop k, exit shape, hold, same entry-hour bucket for H1) is
re-simulated at M random other bars of the SAME WEEK; the trade's net R is compared with the mean net R of those matched entries.
excess = actual - matched per trade; t from week clusters. A configuration whose edge is only drift shows excess ~ 0 (and matched
long trades earning the same as the actual ones). Descriptive; writes nothing.
Usage: WRWR_SET=f2 python research/wrwr/diag_drift.py <cfg index> [...]"""
from __future__ import annotations

import json
import os
import sys
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

SET = os.environ.get("WRWR_SET", ""); SUF = f"_{SET}" if SET else ""
M = 30
EXITS = dict(SG.EXITS)


def main(cfgs):
    P = PF.load_pool_cache(K.ROOT / "data" / "wrwr" / f"cache_pool{SUF}")
    vs = np.load(K.ROOT / "data" / "wrwr" / f"cache_pool{SUF}" / "vol_scale.npy")
    z = np.load(K.ROOT / "data" / "wrwr" / f"family_XAUUSD{SUF}.npz", allow_pickle=False)
    fam = json.loads(str(z["family"])); champs = json.loads(str(z["champs"]))
    bars = {tf: SG.load_xau(tf) for tf in ("H1", "H4", "D1")}
    rng = np.random.default_rng(99)
    for j in cfgs:
        ch = [[int(x) for x in w] for w in champs[str(j)]]
        log = []
        PF.simulate(P, ch, vs, f=0.01, log=log)
        L = pd.DataFrame(log, columns=["k", "c", "entry_t", "exit_t", "lots", "R", "pnl", "eq"])
        rows = []
        for c, et in zip(L.c, L.entry_t):
            pos = int(np.searchsorted(P.entry_t[c], et)); cd = P.cands[c]
            rows.append((cd["tf"], cd["k_atr"], cd["exit"], cd["hold"], int(P.dir[c][pos])))
        L[["tf", "k_atr", "exit", "hold", "dir"]] = pd.DataFrame(rows)
        L["matched"] = np.nan
        for (tf, k_atr, ex_lab, hold, dr), G in L.groupby(["tf", "k_atr", "exit", "hold", "dir"]):
            B, cuts, _ = bars[tf]
            N = len(B.t); hours = pd.to_datetime(B.t, unit="s").hour.to_numpy()
            week, _ = K.entry_week(B.t, cuts)
            ok = np.isfinite(B.atr) & (np.arange(N) < N - hold - 2)
            ent_bar = np.searchsorted(B.t, G.entry_t.to_numpy())
            samp_idx, samp_owner = [], []
            for n_, (idx, eb) in enumerate(zip(G.index, ent_bar)):
                w = week[eb]
                lo, hi = np.searchsorted(week, w, "left"), np.searchsorted(week, w, "right")
                pool = np.arange(lo, hi)
                pool = pool[ok[pool] & (pool != eb)]
                if tf == "H1":
                    pool = pool[hours[pool] == hours[eb]]
                if not len(pool):
                    continue
                pick = rng.choice(pool, M, replace=len(pool) < M)
                samp_idx.append(pick); samp_owner.append(np.full(M, idx))
            if not samp_idx:
                continue
            e = np.concatenate(samp_idx); own = np.concatenate(samp_owner)
            stop = k_atr * B.atr[e]
            g, xx = E.simulate(B, e, np.full(len(e), float(dr)), stop, EXITS[ex_lab] * stop, e + hold - 1)
            sw = K.swap_bp("XAUUSD", B.t[e], B.t[xx] + B.step, np.full(len(e), float(dr)))
            r = (g - K.cost_bp("XAUUSD", B.spread_bp[e]) - sw) / (stop / B.o[e] * 1e4)
            m = pd.Series(r).groupby(own).mean()
            L.loc[m.index, "matched"] = m.to_numpy()
        L = L.dropna(subset=["matched"])
        L["excess"] = L.R - L.matched
        wk = L.k.to_numpy()
        cl = L.groupby("k").excess.sum()
        t = cl.mean() / (cl.std(ddof=1) / np.sqrt(len(cl))) if len(cl) > 2 else np.nan
        c = fam[j]
        print(f"\n=== cfg {j} ({SET or 'zoo'}): {c['window']}w z{c['lcb_z']} {c['pool']} m{c['m']} eq{c['equity_filter']}: {len(L)} live trades")
        for nm, g_ in (("all", L), ("long", L[L.dir > 0]), ("short", L[L.dir < 0])):
            if len(g_):
                print(f"  {nm:5s}: n {len(g_):4d}  actual mean R {g_.R.mean():+.3f}  timing-matched {g_.matched.mean():+.3f}  excess {g_.excess.mean():+.3f}  (sum excess {g_.excess.sum():+.1f} R)")
        print(f"  weekly-cluster t of the excess: {t:+.2f} over {len(cl)} weeks")


if __name__ == "__main__":
    main([int(x) for x in sys.argv[1:]])
