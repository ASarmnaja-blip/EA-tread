"""Run the pre-registered 144-configuration deployable family (docs/WRWR_CONTRACT_PREREG.md C6) through the corrected
event-driven portfolio (C2) on gold H1 / H4 / D1, and write the weekly R matrix plus the family manifest pieces.
Old-vs-new reconciliation of BASE is printed. Writes data/wrwr/family_XAUUSD.npz and data/wrwr/family_XAUUSD.xlsx.
No gate statistic is computed here (that needs the frozen manifest and the random-router benchmark)."""
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

sys.path.insert(0, str(K.ROOT / "research" / "foundry"))
import engine as E  # noqa: E402

WINDOWS, ZS, POOLS, MS, EQF = (26, 52, 78), (0.5, 1.0, 2.0), ("H1", "H4", "D1", "H1+H4+D1"), (1, 2), (0, 26)
MINN = 10
BASE = (52, 1.0, "H1", 2, 0)


def family():
    fam = [dict(window=L, lcb_z=z, pool=p, m=m, equity_filter=e, min_trades=MINN)
           for L, z, p, m, e in itertools.product(WINDOWS, ZS, POOLS, MS, EQF)]
    key = json.dumps([[c["window"], c["lcb_z"], c["pool"], c["m"], c["equity_filter"], c["min_trades"]] for c in fam])
    return fam, hashlib.sha256(key.encode()).hexdigest()


def main():
    t0 = time.time()
    H, _, cuts, cell = E.load()
    P = PF.load_pool("XAUUSD", ["H1", "H4", "D1"], cuts)
    print(f"pool: {len(P.cands)} candidates, {time.time() - t0:.0f}s", flush=True)
    S1, S2, NN = PF.shadow_stats(P)
    vs = K.causal_vol_scale(H.t, H.c, H.h, H.l, cuts)
    active = np.array([c != "" for c in cell] + [False] * (len(cuts) - len(cell)))[: len(cuts)]
    pools = {"H1": P.tf == "H1", "H4": P.tf == "H4", "D1": P.tf == "D1", "H1+H4+D1": np.isin(P.tf, ["H1", "H4", "D1"])}
    fam, fam_sha = family()
    NW = len(cuts)
    R = np.zeros((NW, len(fam))); EQ = np.zeros((NW, len(fam))); champs_all = {}
    counters = []
    scores = {(L, z): PF.window_scores(S1, S2, NN, L, z, MINN)[0] for L in WINDOWS for z in ZS}
    twin = {}
    for j, c in enumerate(fam):
        sc = scores[(c["window"], c["lcb_z"])]
        act = active.copy()
        if c["equity_filter"]:
            base_key = (c["window"], c["lcb_z"], c["pool"], c["m"])
            wr_twin = twin[base_key]
            cs = np.r_[0.0, np.cumsum(wr_twin)]
            k = np.arange(NW)
            act &= (cs[k] - cs[np.maximum(k - c["equity_filter"], 0)]) > 0          # weeks k-26..k-1, all exits <= cut_k
        ch = PF.champions(sc, pools[c["pool"]], c["m"], P.rank_key, act)
        wr, eq, cnt = PF.simulate(P, ch, vs, f=0.01, equity0=10_000.0)
        if not c["equity_filter"]:
            twin[(c["window"], c["lcb_z"], c["pool"], c["m"])] = wr
        R[:, j] = wr; EQ[:, j] = eq; champs_all[j] = ch
        counters.append(cnt)
        if j % 24 == 0:
            print(f"  {j + 1}/{len(fam)} {c} entries {cnt['entries']} ({time.time() - t0:.0f}s)", flush=True)
    wk = pd.to_datetime(cuts, unit="s")
    live = active
    out = K.ROOT / "data" / "wrwr" / "family_XAUUSD.npz"
    np.savez_compressed(out, R=R, EQ=EQ, cuts=cuts, active=live, vol_scale=vs, family=json.dumps(fam), family_sha=fam_sha,
                        champs=json.dumps({str(j): [[int(x) for x in w] for w in ch] for j, ch in champs_all.items()}),
                        cand_hash=json.dumps([c["hash"] for c in P.cands]))
    yrs = live.sum() / 52.18
    rows = []
    for j, c in enumerate(fam):
        r = R[live, j]; eq = EQ[live, j]
        dd = float((1 - eq / np.maximum.accumulate(eq)).max()); cumR = np.cumsum(r); ddR = float((np.maximum.accumulate(cumR) - cumR).max())
        row = dict(c, total_R=r.sum(), R_per_year=r.sum() / yrs, maxDD_R=ddR, calmar=(r.sum() / yrs) / max(ddR, 1e-9),
                   final_equity=eq[-1], CAGR=(eq[-1] / 10_000) ** (1 / yrs) - 1, maxDD_pct=dd, **counters[j])
        for nm, a in (("L5", 260), ("L3", 156)):
            rr = R[live, j][-a:]; row[f"{nm}_R"] = rr.sum()
        for e, (a0, a1) in {"2004-08": ("2004", "2009"), "2009-14": ("2009", "2015"), "2015-20": ("2015", "2021"),
                            "2021-26": ("2021", "2027")}.items():
            m_ = live & (wk >= a0) & (wk < a1); row[f"R_{e}"] = R[m_, j].sum()
        rows.append(row)
    X = pd.DataFrame(rows)
    X.to_excel(K.ROOT / "data" / "wrwr" / "family_XAUUSD.xlsx", index=False)
    b = X[(X.window == 52) & (X.lcb_z == 1.0) & (X.pool == "H1") & (X.m == 2) & (X.equity_filter == 0)].iloc[0]
    pd.set_option("display.width", 250)
    print(f"\nfamily sha256 {fam_sha}; {len(fam)} configurations; {int(live.sum())} active weeks")
    print("BASE (corrected):", b[["total_R", "R_per_year", "maxDD_R", "calmar", "CAGR", "maxDD_pct", "L5_R", "L3_R",
                                 "R_2004-08", "R_2009-14", "R_2015-20", "R_2021-26", "entries", "skip_busy", "skip_minlot",
                                 "skip_riskcap", "skip_weekstop"]].to_dict())
    print("BASE (old walk-forward, entry-week, unit R): +182.6 R 2004-26; eras +5.5 / +112.2 / +42.9 / +22.1")
    print(X.sort_values("total_R", ascending=False).head(10)[["window", "lcb_z", "pool", "m", "equity_filter", "total_R",
          "R_per_year", "maxDD_R", "calmar", "CAGR", "L5_R", "L3_R"]].round(3).to_string(index=False))
    print(f"done {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
