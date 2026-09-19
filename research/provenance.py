#!/usr/bin/env python3
"""The run's memory: what was attempted, on which data, at which commit.

WHY A SEPARATE LOG WHEN A LEDGER ALREADY EXISTS

  change_ledger.py answers one question - how many hypotheses have been spent,
  and did this one clear the bar that count implies. It deliberately records
  nothing else, because every extra field is somewhere for a result to be
  quietly reinterpreted later.

  That leaves a second question unanswered: what did the run DO. Which phase,
  which tools, which data, how long, what was learned, what happens next. A
  ledger entry for a rejected hypothesis says REJECTED and stops; the reason a
  later phase can act on it is the diagnosis, and the diagnosis has nowhere to
  live.

  So: the ledger stays the statistical record and does not grow. This file is
  the operational one. They are append-only for different reasons - the ledger
  because editing it would destroy the hypothesis count, this one because
  editing it would destroy the account of how a conclusion was reached.

WHAT IS HASHED AND WHY

  A result is only reproducible if the inputs are pinned. Three things get
  fingerprinted:

    code      the git commit, plus whether the tree was dirty when the run
              started. A dirty tree makes the commit a lie, so it is recorded
              as such rather than silently ignored.
    data      sha256 of each parquet actually read, taken from the file bytes.
              Cheap because the cache is static; the point is that a silent
              re-download that changed history would show up.
    config    the parameter dict the run used, serialised.

  A manifest is the three together. Two runs with the same manifest that
  disagree are a bug; that is the only use for it.
"""
import datetime as dt
import hashlib
import json
import os
import pathlib
import subprocess
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
LOG = ROOT / "logs" / "autonomous_progress.jsonl"
_DATA_HASH_CACHE = {}


def git_state():
    """Commit and cleanliness. A dirty tree is reported, never assumed away."""
    def run(*a):
        try:
            return subprocess.run(a, cwd=ROOT, capture_output=True,
                                  text=True, timeout=30).stdout.strip()
        except Exception:
            return ""
    commit = run("git", "rev-parse", "HEAD")
    dirty = bool(run("git", "status", "--porcelain"))
    return {"commit": commit or "unknown", "dirty": dirty,
            "branch": run("git", "rev-parse", "--abbrev-ref", "HEAD")}


def file_hash(path, chunk=1 << 20):
    """sha256 of a file's bytes, memoised by (path, mtime, size).

    Memoised on mtime and size rather than path alone: a cache keyed on the
    name would keep returning the old digest after a re-download, which is the
    exact event the digest exists to catch."""
    p = pathlib.Path(path)
    if not p.exists():
        return None
    st = p.stat()
    key = (str(p), st.st_mtime_ns, st.st_size)
    if key in _DATA_HASH_CACHE:
        return _DATA_HASH_CACHE[key]
    h = hashlib.sha256()
    with p.open("rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    d = h.hexdigest()
    _DATA_HASH_CACHE[key] = d
    return d


def data_manifest(paths):
    """{name: {sha256, bytes, mtime}} for every input file a run touched."""
    out = {}
    for p in paths:
        p = pathlib.Path(p)
        if not p.exists():
            out[p.name] = {"sha256": None, "missing": True}
            continue
        st = p.stat()
        out[p.name] = {"sha256": file_hash(p), "bytes": st.st_size,
                       "mtime": dt.datetime.fromtimestamp(
                           st.st_mtime, dt.UTC).isoformat()}
    return out


def config_hash(cfg):
    """Order-independent digest of a parameter dict."""
    s = json.dumps(cfg, sort_keys=True, default=str)
    return hashlib.sha256(s.encode()).hexdigest()[:16]


def manifest(config=None, data_paths=()):
    return {"git": git_state(),
            "config_hash": config_hash(config or {}),
            "config": config or {},
            "data": data_manifest(data_paths)}


def log(phase, question, *, hypothesis=None, tools=(), result=None,
        status="INFO", finding=None, next_action=None, started=None,
        config=None, data_paths=(), extra=None):
    """Append one record. Never overwrites, never rewrites.

    `status` is free text by design rather than an enum: the run's own status
    vocabulary (REJECTED / MEASUREMENT_FAILURE / INCONCLUSIVE /
    RESEARCH_CANDIDATE / FINALIST) belongs to the research layer, and pinning
    it here would mean the logger had to be edited every time that vocabulary
    grew - which is how a log starts refusing to record the thing that did not
    fit."""
    now = time.time()
    rec = {
        "ts": dt.datetime.now(dt.UTC).isoformat(),
        "phase": phase,
        "question": question,
        "hypothesis": hypothesis,
        "tools": list(tools),
        "started": (dt.datetime.fromtimestamp(started, dt.UTC).isoformat()
                    if started else None),
        "elapsed_s": round(now - started, 1) if started else None,
        "status": status,
        "result": result,
        "finding": finding,
        "next_action": next_action,
        "git": git_state(),
    }
    if config is not None:
        rec["config_hash"] = config_hash(config)
    if data_paths:
        rec["data"] = data_manifest(data_paths)
    if extra:
        rec["extra"] = extra
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a") as f:
        f.write(json.dumps(rec, default=str) + "\n")
    return rec


def read_log():
    if not LOG.exists():
        return []
    out = []
    for line in LOG.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def phase_summary():
    """Counts by phase and status - the run's own progress, from the log."""
    recs = read_log()
    by = {}
    for r in recs:
        k = r.get("phase", "?")
        by.setdefault(k, {"n": 0, "status": {}})
        by[k]["n"] += 1
        s = r.get("status", "INFO")
        by[k]["status"][s] = by[k]["status"].get(s, 0) + 1
    return by


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "summary":
        for k, v in phase_summary().items():
            print(f"  {k:<28}{v['n']:>5} records   {v['status']}")
    else:
        print(json.dumps(manifest(), indent=1))
