"""Portfolio aggregator template (Amendment 11). A frozen copy runs as
`python research/foundry_frozen_<label>/portfolio.py data/foundry/shadow/<label>.json`.
For each forward week, in order: every listed component (scores file, candidate name) must have exactly
one row for that week, else stop and wait. If any component's status is not OK -> factor 1 (no bet).
Otherwise g = mean of the components' week_R_clip (each in [-2, 2]); E = mean over lambda in the JSON
of prod(1 + lambda g) (factors >= 0.2 for lambda <= 0.4). Append-only with a hash chain, validated
before appending. No order is ever sent."""
from __future__ import annotations

import csv
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
FIELDS = ["week", "status", "n_components", "week_R", "E", "E_0.05", "E_0.1", "E_0.2", "E_0.4", "reject",
          "prev_sha", "row_sha", "recorded_utc"]


def read(p):
    try:
        return pd.read_csv(p) if p.exists() and p.stat().st_size > 0 else pd.DataFrame()
    except pd.errors.EmptyDataError:
        return pd.DataFrame()


def _canon(v):
    """Canonical text of a value so a row hashes the same before and after a CSV round trip."""
    if isinstance(v, (bool, np.bool_)):
        return "True" if v else "False"
    if isinstance(v, str) and v in ("True", "False"):
        return v
    try:
        x = float(v)
        return "nan" if x != x else f"{x:.9g}"
    except (TypeError, ValueError):
        return str(v)


def rh(r):
    return hashlib.sha256(json.dumps({k: _canon(r[k]) for k in FIELDS if k not in ("row_sha", "recorded_utc")},
                                     sort_keys=True).encode()).hexdigest()[:16]


def main(pj):
    P = json.loads(Path(pj).read_text())
    out = ROOT / P["scores_file"]
    lams = [float(x) for x in P["lams"]]
    comps = [(ROOT / c["scores_file"], c["name"]) for c in P["components"]]
    old = read(out)
    prev = "GENESIS"
    for r in old.to_dict("records"):
        if list(old.columns) != FIELDS or r["prev_sha"] != prev or rh(r) != r["row_sha"]:
            print("STOP: portfolio file schema or hash chain broken"); return 1
        prev = r["row_sha"]
    comp = [float(old[f"E_{l:g}"].iloc[-1]) for l in lams] if len(old) else [1.0] * len(lams)
    k = int(P["forward_from"]) + 7 * 86400 * len(old)
    frames = {c: read(f) for f, c in comps}
    new = []
    while True:
        wk = str(pd.to_datetime(k, unit="s"))
        rows = []
        for f, c in comps:
            x = frames[c]
            x = x[(x.name == c) & (x.week == wk)] if len(x) else x
            if len(x) != 1:
                rows = None; break
            rows.append(x.iloc[0])
        if rows is None:
            break
        if all(r.status == "OK" for r in rows):
            g = float(np.mean([r.week_R_clip for r in rows])); status = "OK"
            comp = [ci * (1 + l * g) for ci, l in zip(comp, lams)]
        else:
            g = float("nan"); status = "NO_BET"
        e = float(np.mean(comp))
        r = dict(week=wk, status=status, n_components=len(rows), week_R=g, E=e, **{f"E_{l:g}": ci for l, ci in zip(lams, comp)},
                 reject=bool(e >= P["threshold"]), prev_sha=prev, row_sha="",
                 recorded_utc=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"))
        r["row_sha"] = rh(r); prev = r["row_sha"]
        new.append(r)
        k += 7 * 86400
    if new:
        first = not (out.exists() and out.stat().st_size > 0)
        with open(out, "a", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=FIELDS)
            if first:
                w.writeheader()
            for r in new:
                w.writerow(r)
    S = read(out)
    print(f"{Path(pj).name}: {len(new)} new weeks, {len(S)} total; E {S.E.iloc[-1] if len(S) else 1.0:.3f}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
