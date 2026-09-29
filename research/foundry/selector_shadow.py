"""Forward shadow log of the WPWB Champion/Challenger selector (docs/FOUNDRY_SHADOW_PREREG.md).
Frozen config SELECTOR-SHADOW-1 = nomination 5: menu4, trailing 104 weeks, top 20 %, equal risk
per variant-week, stand aside when WPWB forecasts CALM. Paper only: no order is ever sent.
Usage:
  python research/foundry/selector_shadow.py           log the selection for the latest cut, then score
  python research/foundry/selector_shadow.py --score   only score finished weeks
"""
from __future__ import annotations

import csv
import hashlib
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import engine as E  # noqa: E402
import families as FAM  # noqa: E402

VERSION = "SELECTOR-SHADOW-1"
WEEK = E.WEEK
L_WEEKS, TOP_FRAC, MIN_COUNT, MENU = 104, 0.2, 10, "menu4"
FORWARD = int(np.datetime64("2026-10-02T22:15:00", "s").astype(np.int64))
REOPEN = 47 * 3600 + 45 * 60
DIR = E.ROOT / "data" / "foundry" / "shadow"
LOG = DIR / "selector_shadow_log.csv"
DRY = DIR / "selector_shadow_dryrun.csv"
SCORES = DIR / "selector_shadow_scores.csv"
FIELDS = ["cut_utc", "cut_epoch", "generated_utc", "hours_after_cut", "version", "run", "status", "vol_class",
          "eligible", "n_selected", "selection_file", "selection_sha256", "data_end_utc", "error"]


def utc(ep):
    return datetime.fromtimestamp(int(ep), timezone.utc).strftime("%Y-%m-%d %H:%M")


def append_row(path, row):
    if path.exists():
        with open(path, encoding="utf-8") as fh:
            if fh.readline().strip().split(",") != FIELDS:
                raise RuntimeError(f"{path.name}: schema differs; refusing to append")
    new = not path.exists()
    with open(path, "a", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS, restval="")
        if new:
            w.writeheader()
        w.writerow({k: row.get(k, "") for k in FIELDS})


def trades(H, D, cuts, cell):
    specs = getattr(FAM, MENU)(H, D)
    cbH = np.where(H.week >= 0, cell[np.clip(H.week, 0, len(cell) - 1)], "")
    cbD = np.where(D.week >= 0, cell[np.clip(D.week, 0, len(cell) - 1)], "")
    T = []
    for vi, sp in enumerate(specs):
        B, cb = (H, cbH) if sp.tf == "H1" else (D, cbD)
        g, ex = E.simulate(B, sp.ent, sp.dirs, sp.stop, sp.tgt, sp.last, sp.eprice)
        ep = sp.eprice if sp.eprice is not None else B.o[sp.ent]
        net = g - E.COST_BP
        T.append(pd.DataFrame(dict(v=vi, name=sp.name, et=B.t[sp.ent], xt=B.t[ex] + B.step, xbar=ex, nbars=len(B.t),
                                   net=net, R=net / (sp.stop / ep * 1e4), stress=g - E.STRESS_BP)))
    return pd.concat(T, ignore_index=True), [s.name for s in specs]


def select(T, C):
    past = T[(T.xt <= C) & (T.xt > C - L_WEEKS * WEEK)]
    s = past.groupby("name").R.agg(["sum", "count"])
    s = s[s["count"] >= MIN_COUNT]
    if len(s) < 10:
        return [], len(s)
    score = (s["sum"] / np.sqrt(s["count"])).sort_values(ascending=False)
    top = score.iloc[:max(1, int(np.ceil(TOP_FRAC * len(score))))]
    return [dict(name=n, score=float(v)) for n, v in top.items()], len(s)


def log_cut(now):
    import bars as BR
    C = BR.last_cut_before(now)
    run = ("FORWARD" if now < C + REOPEN else "LATE") if C >= FORWARD else "DRY_RUN"
    target = DRY if run == "DRY_RUN" else LOG
    old = pd.read_csv(target) if target.exists() else pd.DataFrame()
    if len(old) and (old.cut_epoch.astype(int) == C).any():
        print(f"cut {utc(C)} already logged; refusing to rewrite"); return
    if target == LOG and len(old):
        k = int(old.cut_epoch.max()) + WEEK
        while k < C:
            append_row(LOG, dict(cut_utc=utc(k), cut_epoch=k, version=VERSION, run="MISSED", status="MISSED"))
            k += WEEK
    row = dict(cut_utc=utc(C), cut_epoch=C, generated_utc=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
               hours_after_cut=round((now - C) / 3600, 2), version=VERSION, run=run)
    try:
        H, D, cuts, cell = E.load_spliced(until=C)            # nothing after the cut is visible
        row["data_end_utc"] = utc(H.t[-1])
        k = int(np.searchsorted(cuts, C))
        vol = cell[k].split("/")[0] if k < len(cell) and cell[k] else ""
        row["vol_class"] = vol or "UNKNOWN"
        T, names = trades(H, D, cuts, cell)
        sel, elig = select(T, C)
        row["eligible"] = elig
        if vol not in ("NORMAL", "HIGH"):
            row["status"] = "NO_TRADE_CALM" if vol == "CALM" else "NO_TRADE_UNKNOWN_CLASS"
            sel = []
        else:
            row["status"] = "SELECTED" if sel else "NO_TRADE_TOO_FEW"
        DIR.mkdir(parents=True, exist_ok=True)
        f = DIR / f"{run}_{pd.Timestamp(C, unit='s'):%Y%m%dT%H%M}_selection.json"
        body = json.dumps(dict(cut=utc(C), version=VERSION, vol_class=vol, selected=sel), indent=1).encode()
        f.write_bytes(body)
        row.update(n_selected=len(sel), selection_file=f.name, selection_sha256=hashlib.sha256(body).hexdigest())
    except Exception as e:  # noqa: BLE001
        row["status"] = "ERROR"; row["error"] = repr(e)[:200]
    append_row(target, row)
    print(f"logged {run} cut {row['cut_utc']}: {row['status']} ({row.get('n_selected', 0)} variants, class {row.get('vol_class')})")


def score_all(now):
    L = pd.read_csv(LOG) if LOG.exists() else pd.DataFrame()
    L = L[(L.run == "FORWARD")] if len(L) else L
    if not len(L):
        print("no forward rows yet"); return
    H, D, cuts, cell = E.load_spliced()
    end = int(H.t[-1]) + 3600
    T, _ = trades(H, D, cuts, cell)
    rows = []
    for r in L.itertuples():
        C = int(r.cut_epoch)
        if now < C + WEEK or end < C + WEEK - 6 * 3600:
            continue
        if r.status != "SELECTED":
            rows.append(dict(cut_utc=r.cut_utc, status=r.status, week_R=0.0, units=0)); continue
        f = DIR / r.selection_file
        body = f.read_bytes()
        if hashlib.sha256(body).hexdigest() != r.selection_sha256:
            rows.append(dict(cut_utc=r.cut_utc, status="SELECTION HASH MISMATCH")); continue
        names = [x["name"] for x in json.loads(body)["selected"]]
        wk = T[(T.et > C) & (T.et <= C + WEEK) & T.name.isin(names)]
        # a trade still open at the data end is not scored yet
        wk = wk[wk.xt <= end]
        u = wk.groupby("name").R.mean()
        rows.append(dict(cut_utc=r.cut_utc, status="SCORED", units=len(u), trades=len(wk),
                         week_R=float(u.mean()) if len(u) else 0.0, week_R_sum=float(u.sum()) if len(u) else 0.0))
    S = pd.DataFrame(rows)
    S.to_csv(SCORES, index=False)
    sc = S[S.status == "SCORED"] if len(S) else S
    print(f"scored {len(sc)} forward weeks; mean week R {sc.week_R.mean() if len(sc) else float('nan'):+.3f} (descriptive)")


def main() -> int:
    os.chdir(E.ROOT)
    now = int(time.time())
    if "--score" not in sys.argv:
        log_cut(now)
    score_all(now)
    return 0


if __name__ == "__main__":
    sys.exit(main())
