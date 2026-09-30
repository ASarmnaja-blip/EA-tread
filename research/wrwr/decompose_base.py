"""Why did BASE move from +183 R (old walk-forward) to -224 R (corrected C2 simulator)? Plan stop rule (> 20% change):
decompose before going on. Variants of BASE (52w LCB z1, H1 pool, m 2) on the corrected simulator:
  C4      : contract costs (entry spread + 1 bp, floor 2 bp)  = the corrected run
  FLAT2   : old flat 2 bp cost (selection AND trades), everything else corrected
  C4_2011 : contract costs only from 2011 (flat 2 bp before) - how much is the wide early-era spread
and, for each, sized (causal vol_scale) and unsized. Descriptive diagnostics; writes nothing but a log."""
from __future__ import annotations

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

H, _, cuts, cell = E.load()
P = PF.load_pool("XAUUSD", ["H1"], cuts)
B, _, _ = SG.load_xau("H1")
meta, cl, a = SG.load("XAUUSD", "H1")
order = np.lexsort((a["ent"], a["cand"]))
cand = a["cand"][order]; bounds = np.searchsorted(cand, np.arange(len(cl) + 1))
t2011 = int(pd.Timestamp("2011-01-01").timestamp())
R_flat, R_2011 = [], []
for i in range(len(cl)):
    rows = order[bounds[i]:bounds[i + 1]]
    e = a["ent"][rows]
    stop_bp = a["stop_px"][rows].astype(float) / a["entry_px"][rows].astype(float) * 1e4
    c4 = K.cost_bp("XAUUSD", B.spread_bp[e])
    base = a["R"][rows].astype(float) + c4 / stop_bp                   # R before any cost
    R_flat.append(base - 2.0 / stop_bp)
    R_2011.append(np.where(B.t[e] < t2011, base - 2.0 / stop_bp, a["R"][rows].astype(float)))
vs = K.causal_vol_scale(H.t, H.c, H.h, H.l, cuts)
active = np.array([c != "" for c in cell][: len(cuts)] + [False] * max(0, len(cuts) - len(cell)))
wk = pd.to_datetime(cuts, unit="s")
rows = []
for name, RR in (("C4", P.R), ("FLAT2", R_flat), ("C4_2011", R_2011)):
    P.R = RR
    S1, S2, NN = PF.shadow_stats(P)
    sc, _ = PF.window_scores(S1, S2, NN, 52, 1.0, 10)
    ch = PF.champions(sc, np.ones(len(P.cands), bool), 2, P.rank_key, active)
    for sized in (True, False):
        wr, eq, cnt = PF.simulate(P, ch, vs if sized else np.ones(len(cuts)), f=0.01)
        r = wr[active]
        row = dict(variant=name, sized=sized, total_R=r.sum(), entries=cnt["entries"], skip_minlot=cnt["skip_minlot"],
                   skip_weekstop=cnt["skip_weekstop"], final_equity=eq[-1])
        for e_, (a0, a1) in {"2004-08": ("2004", "2009"), "2009-14": ("2009", "2015"), "2015-20": ("2015", "2021"),
                             "2021-26": ("2021", "2027")}.items():
            row[e_] = wr[active & (wk >= a0) & (wk < a1)].sum()
        rows.append(row)
        print(row, flush=True)
pd.set_option("display.width", 250)
print(pd.DataFrame(rows).round(1).to_string(index=False))

# ---- step 2: with FLAT2 costs, reproduce the OLD accounting inside the new framework (shadow trades of the week's
# champions, booked by entry week, unit risk x vol_scale), to see which mechanical fix moves the number
print("\nold-style accounting on the new tables (FLAT2 costs):", flush=True)
P.R = R_flat
S1, S2, NN = PF.shadow_stats(P)
sc, _ = PF.window_scores(S1, S2, NN, 52, 1.0, 10)
NW = len(cuts)
E1 = np.zeros((len(P.cands), NW))
for c in range(len(P.cands)):
    et, xt, r = P.entry_t[c], P.exit_t[c], P.R[c]
    keep, busy = [], -1
    for i in range(len(et)):
        if et[i] >= busy:
            keep.append(i); busy = xt[i]
    keep = np.asarray(keep, int)
    if len(keep):
        ek, at = K.entry_week(et[keep], cuts)
        ok = (ek >= 0) & (ek < NW) & ~at
        E1[c] = np.bincount(ek[ok], r[keep][ok], NW)
import vol as V
rv_raw, _, _, nb = V.weekly_rv(H.t, H.c, H.h, H.l, cuts)
rv = V.mask_invalid(rv_raw, nb); F = V.ewma_forecast(rv)
vs_old = np.full(NW, V.SCALE_MIN)
for k in range(1, NW):
    vs_old[k] = V.effective_scale(V.vol_scale(F[k]), V.calibration(rv[:k], F[:k])[0], bool(nb[k - 1] >= V.MIN_BARS))
for act_name, act in (("cell != ''", active),):
    ch = PF.champions(sc, np.ones(len(P.cands), bool), 2, P.rank_key, act)
    for vs_name, vv in (("causal vol_scale", vs), ("old B_REF vol_scale", vs_old), ("unsized", np.ones(NW))):
        wk_old = np.array([E1[ch[k], k].sum() if len(ch[k]) else 0.0 for k in range(NW)]) * vv
        m_ = act
        print(f"  shadow trades by entry week, {vs_name}: total {wk_old[m_].sum():+.1f} R; eras",
              [round(wk_old[m_ & (wk >= a0) & (wk < a1)].sum(), 1) for a0, a1 in
               (("2004", "2009"), ("2009", "2015"), ("2015", "2021"), ("2021", "2027"))], flush=True)

# ---- step 3: live ledger with the risk rules switched off (diagnostic), FLAT2 costs
print("\nlive ledger, FLAT2 costs, rules OFF (diagnostic):", flush=True)
ch = PF.champions(sc, np.ones(len(P.cands), bool), 2, P.rank_key, active)
for vs_name, vv in (("causal vol_scale", vs), ("unsized", np.ones(NW))):
    wr, eq, cnt = PF.simulate(P, ch, vv, f=0.01, rules=False)
    print(f"  {vs_name}: total {wr[active].sum():+.1f} R, entries {cnt['entries']}, busy skips {cnt['skip_busy']}; eras",
          [round(wr[active & (wk >= a0) & (wk < a1)].sum(), 1) for a0, a1 in
           (("2004", "2009"), ("2009", "2015"), ("2015", "2021"), ("2021", "2027"))], flush=True)

# ---- step 4: which risk rule? FLAT2 costs, sized, all rules vs without the weekly -3U entry stop
print("\nrisk rules split (FLAT2 costs, causal vol_scale):", flush=True)
for lab, kw in (("all rules", {}), ("no weekly -3U stop", dict(weekstop=False))):
    wr, eq, cnt = PF.simulate(P, ch, vs, f=0.01, **kw)
    print(f"  {lab}: total {wr[active].sum():+.1f} R, final equity {eq[-1]:,.0f}, weekstop skips {cnt['skip_weekstop']}, "
          f"minlot skips {cnt['skip_minlot']}, entries {cnt['entries']}", flush=True)
