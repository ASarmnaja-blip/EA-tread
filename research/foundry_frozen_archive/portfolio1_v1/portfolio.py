"""Frozen aggregator for H-FOUNDRY-PORTFOLIO-1 (docs/FOUNDRY_PROTOCOL.md Amendment 10). Do not edit.
Reads the append-only weekly score files of forward panels 1 and 2; for every forward week that BOTH
panels have recorded for all six candidates, portfolio week R = mean of the six weekly R (0 for a
candidate without trades); mixture e-process over lambda (0.05, 0.1, 0.2); reject at E >= 100.
Append-only; each week recorded once. No order is ever sent."""
from __future__ import annotations

import csv
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
SH = ROOT / "data" / "foundry" / "shadow"
OUT = SH / "forward_portfolio1_weeks.csv"
LAMS, THRESH = (0.05, 0.1, 0.2), 100.0
N_CAND = 6


def read(p):
    try:
        return pd.read_csv(p) if p.exists() and p.stat().st_size > 0 else pd.DataFrame()
    except pd.errors.EmptyDataError:
        return pd.DataFrame()


def main():
    A = pd.concat([read(SH / "forward_panel_weeks.csv"), read(SH / "forward_panel2_weeks.csv")])
    old = read(OUT)
    done = set(old.week) if len(old) else set()
    comp = [float(old[f"E_{l:g}"].iloc[-1]) for l in LAMS] if len(old) else [1.0] * len(LAMS)
    new = []
    if len(A):
        g = A.groupby("week")
        for wk in sorted(g.groups):
            if wk in done:
                continue
            x = g.get_group(wk)
            if x.name.nunique() < N_CAND:
                break                                  # wait until every candidate has this week
            wr = float(x.drop_duplicates("name").week_R.mean())
            comp = [c * (1 + l * wr) if (1 + l * wr) > 0 and c > 0 else 0.0 for c, l in zip(comp, LAMS)]
            e = float(np.mean(comp))
            new.append(dict(week=wk, week_R=wr, E=e, **{f"E_{l:g}": c for l, c in zip(LAMS, comp)},
                            reject=bool(e >= THRESH), recorded_utc=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")))
    if new:
        first = not (OUT.exists() and OUT.stat().st_size > 0)
        with open(OUT, "a", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(new[0]))
            if first:
                w.writeheader()
            for r in new:
                w.writerow(r)
    S = read(OUT)
    print(f"portfolio1: {len(new)} new weeks, {len(S)} total; E {S.E.iloc[-1] if len(S) else 1.0:.3f}")


if __name__ == "__main__":
    main()
