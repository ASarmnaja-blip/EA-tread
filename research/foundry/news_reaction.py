"""Descriptive (no gate, no alpha): what gold does in the hours after a scheduled HIGH-importance
USD release, by whether the release-hour move AGREES with the surprise (acceptance) or OPPOSES it
(rejection) - CLAUDE.md section 2: news sets the hypothesis, the price reaction decides it.

Per release time (simultaneous releases combined): implied gold direction = sign of
sum( -z if a higher print is gold-negative else +z ), z = (actual - forecast) / trailing sigma
(calendar_feed; sigma from prior prints only). Release bar = the H1 bar containing the release.
Move m = its close - its open, in ATR. Entry at the next bar's open; hold h hours; stop 2 ATR.
Cases: ACCEPT (sign m = implied, |z_net| >= 0.5), REJECT (sign m = -implied, |z_net| >= 0.5),
INLINE (|z_net| < 0.5), CONFLICT (series disagree in sign). Trades: FOLLOW the bar's move or FADE it.
2022-01..2026-08; halves 2022-23 / 2024-26 reported separately."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parents[1] / "research" / "pilot")]
import engine as E  # noqa: E402
import calendar_feed as C  # noqa: E402

H, D, cuts, cell = E.load()
cal = C.load_calendar(str(E.ROOT / "data" / "calendar.csv"))
ev = [e for e in C.build_events(cal) if e.usable]
df = pd.DataFrame([dict(epoch=e.epoch, name=e.name, z=(e.actual - e.consensus) / e.sigma,
                        s=(-1 if e.higher_is_gold_negative else 1)) for e in ev])
df["g"] = df.z * df.s
agg = df.groupby("epoch").agg(g=("g", "sum"), n=("g", "size"), pos=("g", lambda x: (x > 0.25).sum()),
                              neg=("g", lambda x: (x < -0.25).sum()), names=("name", lambda x: ",".join(sorted(set(x)))[:60]))
rows = []
for ep, r in agg.iterrows():
    i = int(np.searchsorted(H.t, ep, side="right") - 1)          # bar containing the release
    if i < 20 or i + 30 >= len(H.t) or not (H.t[i] <= ep < H.t[i] + 3600) or not np.isfinite(H.atr[i]):
        continue
    m = (H.c[i] - H.o[i]) / H.atr[i]
    if r.pos and r.neg:
        case = "CONFLICT"
    elif abs(r.g) < 0.5:
        case = "INLINE"
    else:
        case = "ACCEPT" if np.sign(m) == np.sign(r.g) else "REJECT"
    rows.append(dict(epoch=ep, i=i, m=m, g=r.g, case=case))
X = pd.DataFrame(rows)
print(f"usable release times {len(agg)}; with an H1 bar {len(X)}; cases {X.case.value_counts().to_dict()}")
out = []
for mth in (0.5, 1.0):
    for hold in (4, 12, 24):
        for side in ("FOLLOW", "FADE"):
            Y = X[X.m.abs() > mth]
            ent = Y.i.to_numpy() + 1
            d = np.sign(Y.m.to_numpy()) * (1 if side == "FOLLOW" else -1)
            a = H.atr[ent]
            last = np.searchsorted(H.t, H.t[ent] + (hold - 1) * 3600, side="right") - 1
            g, ex = E.simulate(H, ent, d, 2 * a, np.full(len(ent), np.nan), last)
            g = g - E.swap_bp(H, ent, ex, d) - E.COST_BP
            R = g / (2 * a / H.o[ent] * 1e4)
            yr = pd.to_datetime(H.t[ent], unit="s").year
            for case in ("ACCEPT", "REJECT", "INLINE", "CONFLICT"):
                mk = (Y.case == case).to_numpy()
                h1 = mk & (yr <= 2023); h2 = mk & (yr >= 2024)
                if mk.sum() < 10:
                    continue
                out.append(dict(move=mth, hold=hold, trade=side, case=case, n=int(mk.sum()), R=R[mk].mean(),
                                t=E.cluster_t(R[mk], H.t[ent][mk] // E.WEEK), R_22_23=R[h1].mean() if h1.sum() else np.nan,
                                n1=int(h1.sum()), R_24_26=R[h2].mean() if h2.sum() else np.nan, n2=int(h2.sum())))
O = pd.DataFrame(out)
pd.set_option("display.width", 220)
print(O.round(3).to_string(index=False))
both = O[(O.R_22_23 > 0) & (O.R_24_26 > 0) & (O.n1 >= 15) & (O.n2 >= 15)]
print(f"\n{len(both)} of {len(O)} rows positive in both halves (a coin flip per half would give ~{len(O) / 4:.0f})")
print(both.round(3).to_string(index=False))
