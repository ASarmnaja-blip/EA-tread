"""Foundry forward panel (protocol Amendment 6). History only NOMINATES; confirmation is forward.
  --nominate   one-time: rank every family variant on the last 104 weeks of data (after cost and
               swap), require the same sign on 2021-01..2024-08, keep the top 5 from distinct families,
               freeze them (names + code hash) in data/foundry/shadow/forward_panel.json
  (default)    weekly: paper-trade the frozen panel on the spliced Dukascopy->Exness feed for weeks
               starting at or after the first forward cut; per candidate an e-process
               E_t = mean over lam in (0.05, 0.1, 0.2) of prod(1 + lam * week_R) (Amendment 8), no
               clipping (R12-1). Null: the conditional
               mean of week_R given the past is <= 0 each week. Valid while 1 + lam * week_R > 0,
               i.e. week_R > -5 R for the largest lambda; a component whose factor is <= 0 becomes 0.
               Reject the null when E_t >= 1 / alpha_i, alpha_i = 0.01 / 5.
               Append-only (R12-2): each completed week is scored once, with the hash of the bars it
               used, and never rewritten; a code change after freezing stops scoring.
               No order is ever sent."""
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
K, ALPHA, LAMS = 5, 0.01, (0.05, 0.1, 0.2)
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
                                     forward_from=int(FORWARD), alpha_each=ALPHA / K, lams=list(LAMS),
                                     candidates=pick[["name", "cell", "n", "R", "t_R", "check_R"]].to_dict("records")), indent=1))
    print("frozen ->", PANEL)
    return 0


def score():
    if not PANEL.exists():
        print("no panel"); return 0
    P = json.loads(PANEL.read_text())
    if code_hash() != P["code_sha256"]:
        print("STOP: code changed since the panel was frozen; no forward week is scored (R12-2)"); return 1
    lams = [float(x) for x in P["lams"]]
    H, D, cuts, cell = E.load_spliced()
    end = int(H.t[-1]) + 3600
    now = int(time.time())
    names = {c["name"] for c in P["candidates"]}
    T = trades(H, D, cell, [s for s in universe(H, D) if s.name in names])
    old = pd.read_csv(SCORES) if SCORES.exists() and SCORES.stat().st_size > 0 else pd.DataFrame()
    done = set(zip(old.name, old.week)) if len(old) else set()
    new = []
    for c in P["candidates"]:
        g = T[(T.name == c["name"]) & E.cell_mask(T.cell.to_numpy(), c["cell"])]
        prev = old[old.name == c["name"]] if len(old) else old
        # mixture e-process (Amendment 8): the average of one product per lambda
        comp = [float(prev[f"E_{l:g}"].iloc[-1]) for l in lams] if len(prev) else [1.0] * len(lams)
        k = FORWARD + (len(prev) * E.WEEK)
        # a week is scored once every trade entered in it has closed (max hold 48 h + 20 d guard)
        while k + E.WEEK <= min(now, end):
            wk = str(pd.to_datetime(k, unit="s"))
            if (c["name"], wk) in done:
                k += E.WEEK; continue
            w = g[(g.et > k) & (g.et <= k + E.WEEK)]
            if len(w) and (w.xt > end).any():
                break                                          # a trade of this week is still open
            bars = (H.t > k - 400 * 3600) & (H.t <= min(k + E.WEEK + 60 * 3600, end))
            bh = hashlib.sha256(np.round(np.c_[H.t[bars], H.o[bars], H.h[bars], H.l[bars], H.c[bars]], 4).tobytes()).hexdigest()[:16]
            wr = float(w.R.mean()) if len(w) else 0.0
            comp = [ci * (1 + l * wr) if (1 + l * wr) > 0 and ci > 0 else 0.0 for ci, l in zip(comp, lams)]
            e = float(np.mean(comp))
            new.append(dict(name=c["name"], cell=c["cell"], week=wk, trades=len(w), week_R=wr, E=e,
                            **{f"E_{l:g}": ci for l, ci in zip(lams, comp)},
                            reject=bool(e >= 1 / P["alpha_each"]), failed=bool(e == 0.0), bars_sha=bh,
                            recorded_utc=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")))
            k += E.WEEK
    if new:
        pd.DataFrame(new).to_csv(SCORES, mode="a", header=not (SCORES.exists() and SCORES.stat().st_size > 0), index=False)
    S = pd.read_csv(SCORES) if SCORES.exists() and SCORES.stat().st_size > 0 else pd.DataFrame()
    print(f"forward panel: {len(P['candidates'])} candidates, {len(new)} new week-rows, "
          f"{S.week.nunique() if len(S) else 0} forward weeks recorded")
    if len(S):
        print(S.groupby("name").tail(1)[["name", "cell", "E", "reject", "failed"]].to_string(index=False))
    return 0


if __name__ == "__main__":
    os.chdir(E.ROOT)
    sys.exit(nominate() if "--nominate" in sys.argv else score())
