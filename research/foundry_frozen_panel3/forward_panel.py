"""Foundry forward panels (protocol Amendments 6-11). History only NOMINATES; forward weeks CONFIRM.

  --nominate                     print the Amendment-6 ranking (last 104 weeks, after cost and swap)
  --freeze <label> <alpha> <fn:spec:cell> ...
                                 freeze a panel: data/foundry/shadow/forward_<label>.json plus a code
                                 snapshot research/foundry_frozen_<label>/ (engine, families, this file,
                                 vol.py, build_all_tf.py, external_traces.py, a frozen 2y-yield series,
                                 a FROZEN marker); the JSON holds the SHA-256 over every snapshot file
  --score --panel-file F --scores-file S
                                 score one panel with THIS code (called inside its snapshot)
  (default)                      dispatcher: score every frozen panel from its own snapshot, then the
                                 frozen portfolio aggregator(s)

Test (Amendments 11, 14): per candidate and forward week, g = max(week R, -2) (floor only)
(week R = mean R of the candidate's trades entered that week, 0 if none). Null: the conditional mean
of g given the past is <= 0 each week. E = mean over lambda in (0.05, 0.1, 0.2, 0.4) of prod(1 + lambda g);
every factor is >= 1 - 0.4 * 2 = 0.2 > 0, so E is a nonnegative supermartingale under the null (valid for dependent
weeks). A week that cannot be scored cleanly - data gap (< 80 H1 bars) or scored more than 8 days
after it became scorable (LATE) - gets factor 1 (no bet); that choice does not depend on the outcome.
A week is scorable only once the feed extends 6 days past its end, so every trade (max hold 72 h +
weekend) has closed. Rows are append-only with a hash chain; the file is validated before appending.
No order is ever sent."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
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

SHADOW = E.ROOT / "data" / "foundry" / "shadow"
FORWARD = int(np.datetime64("2026-10-02T22:15:00", "s").astype(np.int64))
LAMS = (0.05, 0.1, 0.2, 0.4)
FLOOR = -2.0     # Amendment 14: floor only (validity needs a lower bound; no ceiling, big wins count)
SETTLE = 6 * 86400          # feed must extend this far past a week's end before the week is scored
LATE = 8 * 86400
CELLS = ["ALL", "NOTCALM/*", "HIGH/*"]
FIELDS = ["name", "cell", "week", "status", "trades", "week_R_raw", "week_R_clip", "E"] + [f"E_{l:g}" for l in LAMS] + \
         ["reject", "bars_sha", "cal_sha", "prev_sha", "row_sha", "recorded_utc"]
SNAP_FILES = {"engine.py": "research/foundry/engine.py", "families.py": "research/foundry/families.py",
              "forward_panel.py": "research/foundry/forward_panel.py", "vol.py": "research/wpwb_weekly/vol.py",
              "build_all_tf.py": "research/history/build_all_tf.py", "external_traces.py": "research/pilot/external_traces.py",
              "calendar_feed.py": "research/pilot/calendar_feed.py", "calendar_pit.py": "research/foundry/calendar_pit.py"}


def universe(H, D):
    seen, out = set(), []
    for s in FAM.trackB1(H, D) + FAM.overnight_split(H) + FAM.panel2(H, D) + FAM.panel3(H, D):
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


def dir_hash(d: Path) -> str:
    h = hashlib.sha256()
    for f in sorted(p for p in d.iterdir() if p.is_file() and p.name != "README.md"):
        h.update(f.name.encode()); h.update(f.read_bytes())
    return h.hexdigest()


TEXT_FIELDS = {"name", "cell", "week", "status", "bars_sha", "cal_sha", "prev_sha", "row_sha", "recorded_utc"}
BOOL_FIELDS = {"reject"}


def _canon(v, field=None):
    """Exact, CSV-round-trip-stable text of a value: text fields as str, booleans as True/False,
    every number as float.hex of its float value (so 1, 1.0 and "1" hash alike, nothing is rounded)."""
    if field in TEXT_FIELDS:
        return str(v)
    if field in BOOL_FIELDS or isinstance(v, (bool, np.bool_)):
        return "True" if (v is True or v == True or str(v) == "True") else "False"  # noqa: E712
    try:
        x = float(v)
        return "nan" if x != x else float.hex(x)
    except (TypeError, ValueError):
        return str(v)


def row_hash(r):
    return hashlib.sha256(json.dumps({k: _canon(r[k], k) for k in FIELDS if k != "row_sha"}, sort_keys=True).encode()).hexdigest()[:16]


RUNS = SHADOW / "forward_runs.csv"          # append-only log of every scoring run and the feed end it saw


def log_run(feed_end):
    first = not RUNS.exists()
    with open(RUNS, "a", encoding="utf-8") as fh:
        if first:
            fh.write("run_epoch,feed_end\n")
        fh.write(f"{int(time.time())},{int(feed_end)}\n")


def had_run_between(a, b):
    if not RUNS.exists():
        return False
    R = pd.read_csv(RUNS)
    return bool(((R.run_epoch >= a) & (R.run_epoch < b)).any())


# ------------------------------------------------------------------ nomination (Amendment 6)
def nominate(k=5):
    H, D, cuts, cell = E.load()
    T = trades(H, D, cell, universe(H, D))
    end = int(H.t[-1])
    lo_recent = end - 104 * E.WEEK
    lo_check = int(np.datetime64("2021-01-01T00:00:00", "s").astype(np.int64))
    rows = []
    for name, g in T.groupby("name"):
        for c in CELLS:
            m = E.cell_mask(g.cell.to_numpy(), c)
            r = g[m & (g.et > lo_recent)]
            chk = g[m & (g.et > lo_check) & (g.et <= lo_recent)]
            if len(r) < 30 or len(chk) < 30:
                continue
            rows.append(dict(name=name, cell=c, n=len(r), R=r.R.mean(), net=r.net.mean(),
                             t_R=E.cluster_t(r.R.to_numpy(), r.et.to_numpy() // E.WEEK), check_R=chk.R.mean(),
                             family=name.split("_")[0] + ("~INV" if "~INV" in name else "")))
    R = pd.DataFrame(rows)
    R = R[(R.R > 0) & (R.net > 0) & (R.check_R > 0)].sort_values("t_R", ascending=False)
    print(R.drop_duplicates("family").head(k).round(3).to_string(index=False))
    return 0


# ------------------------------------------------------------------ freezing
def freeze(label, alpha, items):
    js = SHADOW / f"forward_{label}.json"
    snap = E.ROOT / "research" / f"foundry_frozen_{label}"
    if js.exists() or snap.exists():
        print("already frozen:", js); return 1
    snap.mkdir(parents=True)
    for dst, src in SNAP_FILES.items():
        shutil.copy2(E.ROOT / src, snap / dst)
    y2 = E._swap_rate_series()[0] - E.SWAP_MARKUP       # the 2y yield series as loaded now
    y2.to_frame("y2").to_csv(snap / "y2_frozen.csv")
    (snap / "FROZEN").write_text("forward-record snapshot; do not edit\n")
    (snap / "README.md").write_text(f"Frozen code snapshot for forward panel `{label}` ({js.name}). Do not edit. "
                                    "Unfrozen: research/wpwb_weekly/bars.py (Exness data access) and the data files.\n", encoding="utf-8")
    H, D, _, _ = E.load()
    names = {s.name for s in universe(H, D)}
    cands = []
    for x in items:
        fn, spec, cell = x.split(":")
        assert spec in names, f"{spec} not in universe"
        cands.append(dict(name=spec, cell=cell, source_fn=fn))
    js.write_text(json.dumps(dict(frozen_utc=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
                                  snapshot_dir=str(snap.relative_to(E.ROOT)).replace("\\", "/"), snapshot_sha256=dir_hash(snap),
                                  forward_from=FORWARD, alpha_each=alpha / len(cands), lams=list(LAMS), floor=FLOOR,
                                  candidates=cands), indent=1))
    print("frozen", js.name, "->", snap.name, dir_hash(snap)[:16])
    return 0


# ------------------------------------------------------------------ scoring (append-only)
def validate(old, cands):
    """Existing rows must be: exactly the frozen names, contiguous weeks from FORWARD, one row per
    (name, week), an intact hash chain. Anything else stops scoring."""
    if not len(old):
        return True
    if list(old.columns) != FIELDS:
        print("STOP: score file schema differs"); return False
    for c in cands:
        g = old[old.name == c["name"]]
        wk = pd.to_datetime(g.week).astype("datetime64[s]").astype(np.int64).to_numpy()
        want = FORWARD + E.WEEK * np.arange(len(g))
        if len(g) and not np.array_equal(wk, want):
            print(f"STOP: {c['name']} weeks are not contiguous from the forward start"); return False
        prev = "GENESIS"
        for r in g.to_dict("records"):
            if r["prev_sha"] != prev or row_hash(r) != r["row_sha"]:
                print(f"STOP: hash chain broken for {c['name']} at {r['week']}"); return False
            prev = r["row_sha"]
    if set(old.name) - {c["name"] for c in cands}:
        print("STOP: unknown candidate in score file"); return False
    counts = {c["name"]: int((old.name == c["name"]).sum()) for c in cands}
    if len(set(counts.values())) != 1:
        print("STOP: candidates are not in lockstep (a row was added or removed):", counts); return False
    return True


def score(panel_file: Path, scores_file: Path):
    P = json.loads(panel_file.read_text())
    snap = E.ROOT / P["snapshot_dir"]
    if Path(__file__).resolve().parent != snap.resolve():
        print("STOP: --score must run inside the panel's own snapshot"); return 1
    if dir_hash(snap) != P["snapshot_sha256"]:
        print("STOP: snapshot changed since freezing"); return 1
    old = pd.read_csv(scores_file, float_precision="round_trip") if scores_file.exists() and scores_file.stat().st_size > 0 else pd.DataFrame(columns=FIELDS)
    if not validate(old, P["candidates"]):
        return 1
    H, D, cuts, cell = E.load_spliced()
    specs = {s.name: s for s in universe(H, D)}
    missing = [c["name"] for c in P["candidates"] if c["name"] not in specs]
    if missing:
        print("STOP: frozen candidates missing from the universe:", missing); return 1
    T = trades(H, D, cell, [specs[c["name"]] for c in P["candidates"]])
    end = int(H.t[-1]) + 3600
    now = int(time.time())
    lams = [float(x) for x in P["lams"]]
    new = []
    for c in P["candidates"]:
        g = T[(T.name == c["name"]) & E.cell_mask(T.cell.to_numpy(), c["cell"])]
        prev_rows = old[old.name == c["name"]]
        comp = [float(prev_rows[f"E_{l:g}"].iloc[-1]) for l in lams] if len(prev_rows) else [1.0] * len(lams)
        prev_sha = prev_rows.row_sha.iloc[-1] if len(prev_rows) else "GENESIS"
        k = FORWARD + E.WEEK * len(prev_rows)
        while k + E.WEEK + SETTLE <= min(now, end):
            w = g[(g.et > k) & (g.et <= k + E.WEEK)]
            nbar = int(((H.t + 3600 > k) & (H.t + 3600 <= k + E.WEEK)).sum())
            span = H.t[(H.t > k) & (H.t <= k + E.WEEK + SETTLE)]
            max_gap = float(np.diff(span).max() / 3600) if len(span) > 1 else 999.0
            wr = float(w.R.mean()) if len(w) else 0.0
            gc = float(max(wr, FLOOR))
            ready = k + E.WEEK + SETTLE
            cal_missing = False
            if c["name"].startswith("NEWS_"):                     # the week's HIGH USD releases must carry actuals
                import calendar_pit as CP
                pc = CP.load_pit()
                wk_rel = pc[(pc.epoch > k) & (pc.epoch <= k + E.WEEK) & (pc.currency == "USD") & (pc.importance == "HIGH")
                            & pc.forecast.notna()]
                # R17: fail closed - no HIGH USD rows at all, a calendar not reaching the week's end, or < 90 % actuals
                cal_missing = (len(wk_rel) == 0 or int(pc.epoch.max()) < k + E.WEEK
                               or float(wk_rel.actual.notna().mean()) < 0.9)
            if nbar < 80 or max_gap > 72 or cal_missing:        # gap in the week, its settlement window, or its news data
                status = "DATA_GAP"
            elif now > ready + LATE and not had_run_between(ready, ready + LATE):   # R15: only the first 8 days count
                status = "LATE"                                   # the job was not running when it became scorable
            else:
                status = "OK"
            if status == "OK":
                comp = [ci * (1 + l * gc) for ci, l in zip(comp, lams)]
            bars = (H.t > k - 400 * 3600) & (H.t <= k + E.WEEK + SETTLE)
            bh = hashlib.sha256(np.round(np.c_[H.t[bars], H.o[bars], H.h[bars], H.l[bars], H.c[bars]], 4).tobytes()).hexdigest()[:16]
            e = float(np.mean(comp))
            ch = "none"
            if c["name"].startswith("NEWS_"):                      # R16: hash the calendar rows the week's signals used
                import calendar_pit as CP
                pc = CP.load_pit()                                 # R17: every row the signal can depend on (sigma uses all history)
                pc = pc[(pc.epoch <= k + E.WEEK) & (pc.currency == "USD") & (pc.importance == "HIGH")]
                ch = hashlib.sha256(pc[["value_id", "epoch", "event", "currency", "importance", "actual", "forecast"]]
                                    .to_csv(index=False, float_format="%.17g").encode()).hexdigest()[:16]
            r = dict(name=c["name"], cell=c["cell"], week=str(pd.to_datetime(k, unit="s")), status=status, trades=len(w),
                     week_R_raw=wr, week_R_clip=gc, E=e, **{f"E_{l:g}": ci for l, ci in zip(lams, comp)},
                     reject=bool(e >= 1 / P["alpha_each"]), bars_sha=bh, cal_sha=ch, prev_sha=prev_sha, row_sha="",
                     recorded_utc=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"))
            r["row_sha"] = row_hash(r)
            prev_sha = r["row_sha"]
            new.append(r)
            k += E.WEEK
    if new:
        first = not (scores_file.exists() and scores_file.stat().st_size > 0)
        pd.DataFrame(new, columns=FIELDS).to_csv(scores_file, mode="a", header=first, index=False, float_format="%.17g")
        chk = pd.read_csv(scores_file, float_precision="round_trip")                            # R14: the written file must re-validate
        if not validate(chk, P["candidates"]):
            print("STOP: file failed re-validation after append"); return 1
    S = pd.read_csv(scores_file, float_precision="round_trip") if scores_file.exists() and scores_file.stat().st_size > 0 else pd.DataFrame(columns=FIELDS)
    print(f"{panel_file.name}: {len(new)} new rows; {S.week.nunique()} forward weeks recorded")
    if len(S):
        print(S.groupby("name").tail(1)[["name", "cell", "status", "E", "reject"]].to_string(index=False))
    return 0


# ------------------------------------------------------------------ dispatcher
def dispatch():
    import subprocess
    lock = SHADOW / ".forward.lock"
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        if time.time() - lock.stat().st_mtime < 3 * 3600:
            print("another scoring run holds the lock; exiting"); return 0
        lock.unlink(); fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    try:
        return _dispatch(subprocess)
    finally:
        os.close(fd); lock.unlink()


def _dispatch(subprocess):
    rc = 0
    H, _, _, _ = E.load_spliced()
    log_run(int(H.t[-1]) + 3600)
    for js in sorted(SHADOW.glob("forward_panel*.json")):
        P = json.loads(js.read_text())
        if "snapshot_sha256" not in P:
            continue                                    # archived pre-Amendment-11 format
        snap = E.ROOT / P["snapshot_dir"]
        sc = SHADOW / (js.stem + "_weeks.csv")
        r = subprocess.run([sys.executable, str(snap / "forward_panel.py"), "--score", "--panel-file", str(js), "--scores-file", str(sc)],
                           cwd=E.ROOT, capture_output=True, text=True, encoding="utf-8", env={**os.environ, "PYTHONIOENCODING": "utf-8"})
        out = "\n".join(x for x in r.stdout.splitlines() if not x.startswith("canonical_history"))
        print(f"[{js.name}] exit {r.returncode}: {out[-700:]}")
        rc |= r.returncode
    for pj in sorted(SHADOW.glob("portfolio*.json")):
        if rc:
            print(f"[{pj.name}] skipped: a component panel failed this run (fail-closed)"); continue
        P = json.loads(pj.read_text())
        if "snapshot_sha256" not in P:
            continue
        snap = E.ROOT / P["snapshot_dir"]
        if dir_hash(snap) != P["snapshot_sha256"]:
            print(f"[{pj.name}] STOP: aggregator changed since freezing"); rc |= 1; continue
        r = subprocess.run([sys.executable, str(snap / "portfolio.py"), str(pj)], cwd=E.ROOT, capture_output=True, text=True,
                           encoding="utf-8", env={**os.environ, "PYTHONIOENCODING": "utf-8"})
        print(f"[{pj.name}] exit {r.returncode}: {r.stdout.strip()[-400:]}")
        rc |= r.returncode
    return rc


if __name__ == "__main__":
    os.chdir(E.ROOT)
    if "--nominate" in sys.argv:
        sys.exit(nominate())
    if "--freeze" in sys.argv:
        i = sys.argv.index("--freeze")
        sys.exit(freeze(sys.argv[i + 1], float(sys.argv[i + 2]), sys.argv[i + 3:]))
    if "--score" in sys.argv:
        pf = Path(sys.argv[sys.argv.index("--panel-file") + 1]); sf = Path(sys.argv[sys.argv.index("--scores-file") + 1])
        sys.exit(score(pf, sf))
    sys.exit(dispatch())
