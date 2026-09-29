"""Foundry forward panel (protocol Amendment 6). History only NOMINATES; confirmation is forward.
  --nominate   one-time: rank every family variant on the last 104 weeks of data (after cost and
               swap), require the same sign on 2021-01..2024-08, keep the top 5 from distinct families,
               freeze them (names + code hash) in data/foundry/shadow/forward_panel.json
  (default)    weekly: paper-trade the frozen panel on the spliced Dukascopy->Exness feed for weeks
               starting at or after the first forward cut; per candidate an e-process
               E_t = prod(1 + lam * clip(week_R, -1, 1)), lam = 0.2, rejects "mean <= 0" when
               E_t >= 1 / alpha_i, alpha_i = 0.01 / 5. No order is ever sent."""
from __future__ import annotations

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

PANEL = E.ROOT / "data" / "foundry" / "shadow" / "forward_panel.json"
SCORES = E.ROOT / "data" / "foundry" / "shadow" / "forward_panel_weeks.csv"
FORWARD = int(np.datetime64("2026-10-02T22:15:00", "s").astype(np.int64))
K, ALPHA, LAM = 5, 0.01, 0.2
CELLS = ["ALL", "NOTCALM/*", "HIGH/*"]


def universe(H, D):
    seen, out = set(), []
    for s in FAM.trackB1(H, D) + FAM.overnight_split(H):
        if s.name not in seen:
            seen.add(s.name); out.append(s)
    return out


def trades(H, D, cell, specs):
    cbH = np.where(H.week >= 0, cell[np.clip(H.week, 0, len(cell) - 1)], "")
    cbD = np.where(D.week >= 0, cell[np.clip(D.week, 0, len(cell) - 1)], "")
    rows = []
    for s in specs:
        B, cb = (H, cbH) if s.tf == "H1" else (D, cbD)
        g, ex = E.simulate(B, s.ent, s.dirs, s.stop, s.tgt, s.last, s.eprice)
        g = g - E.swap_bp(B, s.ent, ex, s.dirs)
        ep = s.eprice if s.eprice is not None else B.o[s.ent]
        sb = s.stop / ep * 1e4
        net = g - E.COST_BP
        rows.append(pd.DataFrame(dict(name=s.name, et=B.t[s.ent], xt=B.t[ex] + B.step, R=net / sb, net=net, cell=cb[s.ent])))
    return pd.concat(rows, ignore_index=True)


def code_hash():
    h = hashlib.sha256()
    for f in ("families.py", "engine.py", "forward_panel.py"):
        h.update((HERE / f).read_bytes())
    return h.hexdigest()


def nominate():
    if PANEL.exists():
        print("panel already frozen:", PANEL); return 1
    H, D, cuts, cell = E.load()
    T = trades(H, D, cell, universe(H, D))
    end = int(H.t[-1])
    lo_recent = end - 104 * E.WEEK
    lo_check = int(np.datetime64("2021-01-01T00:00:00", "s").astype(np.int64))
    rows = []
    for (name), g in T.groupby("name"):
        for c in CELLS:
            m = E.cell_mask(g.cell.to_numpy(), c)
            r = g[m & (g.et > lo_recent)]
            chk = g[m & (g.et > lo_check) & (g.et <= lo_recent)]
            if len(r) < 30 or len(chk) < 30:
                continue
            t = E.cluster_t(r.R.to_numpy(), r.et.to_numpy() // E.WEEK)
            rows.append(dict(name=name, cell=c, n=len(r), R=r.R.mean(), net=r.net.mean(), t_R=t,
                             check_R=chk.R.mean(), check_n=len(chk), family=name.split("_")[0] + ("~INV" if "~INV" in name else "")))
    R = pd.DataFrame(rows)
    R = R[(R.R > 0) & (R.net > 0) & (R.check_R > 0)].sort_values("t_R", ascending=False)
    pick = R.drop_duplicates("family").head(K)
    pd.set_option("display.width", 220)
    print(f"{len(rows)} variant-cells scored on the last 104 weeks; {len(R)} positive in both windows; panel:")
    print(pick.round(3).to_string(index=False))
    PANEL.parent.mkdir(parents=True, exist_ok=True)
    PANEL.write_text(json.dumps(dict(frozen_utc=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"), code_sha256=code_hash(),
                                     forward_from=int(FORWARD), alpha_each=ALPHA / K, lam=LAM,
                                     candidates=pick[["name", "cell", "n", "R", "t_R", "check_R"]].to_dict("records")), indent=1))
    print("frozen ->", PANEL)
    return 0


def score():
    if not PANEL.exists():
        print("no panel"); return 0
    P = json.loads(PANEL.read_text())
    if code_hash() != P["code_sha256"]:
        print("WARNING: code changed since the panel was frozen; scores are computed with the current code")
    H, D, cuts, cell = E.load_spliced()
    names = {c["name"] for c in P["candidates"]}
    T = trades(H, D, cell, [s for s in universe(H, D) if s.name in names])
    end = int(H.t[-1]) + 3600
    now = int(time.time())
    out = []
    for c in P["candidates"]:
        g = T[(T.name == c["name"]) & E.cell_mask(T.cell.to_numpy(), c["cell"]) & (T.et > FORWARD) & (T.xt <= end)]
        e = 1.0
        k = FORWARD
        while k + E.WEEK <= min(now, end):
            w = g[(g.et > k) & (g.et <= k + E.WEEK)]
            wr = float(w.R.mean()) if len(w) else 0.0
            e *= 1 + LAM * float(np.clip(wr, -1, 1))
            out.append(dict(name=c["name"], cell=c["cell"], week=str(pd.to_datetime(k, unit="s")), trades=len(w), week_R=wr, E=e,
                            reject=e >= 1 / P["alpha_each"]))
            k += E.WEEK
    S = pd.DataFrame(out)
    S.to_csv(SCORES, index=False)
    last = S.groupby("name").tail(1) if len(S) else S
    print(f"forward panel: {len(P['candidates'])} candidates, {S.week.nunique() if len(S) else 0} forward weeks")
    if len(last):
        print(last[["name", "cell", "E", "reject"]].to_string(index=False))
    return 0


if __name__ == "__main__":
    os.chdir(E.ROOT)
    sys.exit(nominate() if "--nominate" in sys.argv else score())
