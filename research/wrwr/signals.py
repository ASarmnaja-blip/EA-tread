"""C2 potential-signal tables (docs/WRWR_CONTRACT_PREREG.md v5). For one symbol and timeframe, every signal of every
candidate (31 zoo indicators x FOLLOW/FADE x stop 1/2 ATR x 9 exits x 2 holds = 2,232) is simulated independently:
entry at the next bar open (signals whose entry bar opens exactly at a cut go to a separate rejected table), exit at
stop / target / max hold (stop-first on a same-bar tie, gap through the stop at the open), C4 cost (entry-bar spread:
for H4 / D1 the FIRST constituent H1 bar's recorded ask-bid) and swap. Columns: direction, gross_bp, cost_bp, swap_bp,
stop / entry price; net R columns are derived at load. Writes data/wrwr/tables_<SYM>_<TF>.npz with C5 metadata.
Usage: python research/wrwr/signals.py XAUUSD H1   (also H4, D1)."""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import contracts as K  # noqa: E402

sys.path[:0] = [str(K.ROOT / "research" / "foundry"), str(K.ROOT / "research" / "sieve")]
import engine as E  # noqa: E402
import features as FT  # noqa: E402

OUT = K.ROOT / "data" / "wrwr"
EXITS = [("1:1", 1.0), ("1:2", 2.0), ("1:3", 3.0), ("1:5", 5.0), ("1:10", 10.0),
         ("2:1", 1 / 2), ("3:1", 1 / 3), ("5:1", 1 / 5), ("10:1", 1 / 10)]
KS = (1, 2)
HOLDS = {"H1": (24, 72), "H4": (6, 30), "D1": (5, 20)}          # bars (D1 = days)
STEP = {"H1": 3600, "H4": 14400, "D1": 86400}
COLS = ("cand", "ent", "ex", "dir", "gross_bp", "cost_bp", "swap_bp", "stop_px", "entry_px")
CODE_FILES = [HERE / "signals.py", HERE / "contracts.py", K.ROOT / "research" / "foundry" / "engine.py",
              K.ROOT / "research" / "foundry" / "indicator_zoo.py", K.ROOT / "research" / "sieve" / "features.py",
              K.ROOT / "research" / "wpwb_weekly" / "vol.py", K.ROOT / "research" / "pilot" / "external_traces.py"]
_INPUTS = {}


class Bars:
    pass


def mk(t, o, h, l, c, v, sp, step):
    B = Bars()
    B.t = np.asarray(t, np.int64); B.o, B.h, B.l, B.c, B.v, B.spread_bp = (np.asarray(x, float) for x in (o, h, l, c, v, sp))
    B.step = int(step); B.atr = E._atr(B.h, B.l, B.c, 14)      # ATR known at each bar's open (bars before it)
    return B


def resample(H, step):
    """H4 / D1 bars from H1. The spread of a resampled bar is the FIRST constituent bar's recorded ask-bid at the
    bar's open (C4, Codex R19-2), never a median over the bar."""
    off = 22 * 3600 if step == 86400 else 0
    k = (H.t - off) // step
    df = pd.DataFrame(dict(k=k, t=H.t, o=H.o, h=H.h, l=H.l, c=H.c, v=H.v, sp=H.spread_bp))
    g = df.groupby("k").agg(t=("t", "first"), o=("o", "first"), h=("h", "max"), l=("l", "min"), c=("c", "last"),
                            v=("v", "sum"), sp=("sp", "first"), n=("t", "size"))
    g = g[g.n >= (18 if step == 86400 else 2)]
    return mk(g.t.to_numpy(np.int64), g.o, g.h, g.l, g.c, g.v, g.sp, step)


def load_xau(tf):
    H, _, cuts, cell = E.load()
    base = mk(H.t, H.o, H.h, H.l, H.c, H.v, H.spread_bp, 3600)
    B = base if tf == "H1" else resample(base, STEP[tf])
    K.check_series(B.t, f"XAUUSD {tf}")
    return B, cuts, cell


def data_sha(B):
    return K.sha_bytes(B.t, B.o, B.h, B.l, B.c, B.v, B.spread_bp)          # volume included (VWAP / OBV use it)


def array_sha(arr):
    return K.sha_bytes(*(arr[x] for x in COLS), arr["bar_t"], arr["rej_cand"], arr["rej_ent"])


def build(symbol, tf):
    t0 = time.time()
    if symbol != "XAUUSD":
        raise SystemExit("XAGUSD tables are built only after C7 is frozen (docs/WRWR_CONTRACT_PREREG.md)")
    B, cuts, _ = load_xau(tf)
    N = len(B.t); step = B.step
    sig = FT.zoo_signals(B)
    ek, at_cut = K.entry_week(B.t, cuts)
    ok_bar = np.isfinite(B.atr) & (ek >= 0)
    cands = []
    cols = {x: [] for x in COLS}
    rej_c, rej_e = [], []
    for name, (sl, ss) in sig.items():
        il, is_ = np.flatnonzero(sl[:-1]), np.flatnonzero(ss[:-1])
        ent0 = np.r_[il, is_] + 1; d0 = np.r_[np.ones(len(il)), -np.ones(len(is_))]
        o_ = np.argsort(ent0, kind="stable"); ent0, d0 = ent0[o_], d0[o_]
        for mode, sgn in (("FOLLOW", 1.0), ("FADE", -1.0)):
            d = d0 * sgn
            for k in KS:
                for hold in HOLDS[tf]:
                    base_ok = ok_bar[ent0] & (ent0 < N - hold - 2)
                    rej = base_ok & at_cut[ent0]                          # entry bar opens exactly at a cut: rejected
                    keep = base_ok & ~at_cut[ent0]
                    e, dd = ent0[keep], d[keep]
                    stop = k * B.atr[e]
                    c_bp = K.cost_bp(symbol, B.spread_bp[e])
                    for lab, mult in EXITS:
                        g, ex = E.simulate(B, e, dd, stop, mult * stop, e + hold - 1)
                        sw = K.swap_bp(symbol, B.t[e], B.t[ex] + step, dd)
                        ci = len(cands)
                        cands.append(dict(tf=tf, setup=name, mode=mode, k_atr=k, exit=lab, hold=hold, n=int(len(e))))
                        cols["cand"].append(np.full(len(e), ci, np.int32)); cols["ent"].append(e.astype(np.int32))
                        cols["ex"].append(ex.astype(np.int32)); cols["dir"].append(dd.astype(np.int8))
                        cols["gross_bp"].append(g.astype(np.float32)); cols["cost_bp"].append(c_bp.astype(np.float32))
                        cols["swap_bp"].append(sw.astype(np.float32))
                        cols["stop_px"].append(stop.astype(np.float32)); cols["entry_px"].append(B.o[e].astype(np.float32))
                        if rej.any():
                            rej_c.append(np.full(int(rej.sum()), ci, np.int32)); rej_e.append(ent0[rej].astype(np.int32))
        print(f"  {name}: {len(cands)} candidates, {sum(len(x) for x in cols['cand']):,} rows, {time.time() - t0:.0f}s", flush=True)
    arr = {x: np.concatenate(v) for x, v in cols.items()}
    arr["bar_t"] = B.t
    arr["rej_cand"] = np.concatenate(rej_c) if rej_c else np.zeros(0, np.int32)
    arr["rej_ent"] = np.concatenate(rej_e) if rej_e else np.zeros(0, np.int32)
    code_sha = K.sha_files(*CODE_FILES)
    for c in cands:
        c["hash"] = K.candidate_hash(c["tf"], c["setup"], c["mode"], c["k_atr"], c["exit"], c["hold"], code_sha)
    raw_sha, raw_n = K.raw_manifest_sha()
    meta = dict(schema=K.SCHEMA, symbol=symbol, tf=tf, step=step, cost_version=K.COST_VERSION, code_sha=code_sha,
                data_sha=data_sha(B), raw_manifest_sha=raw_sha, raw_manifest_files=raw_n, symbols_sha=K.symbols_sha(),
                treasury_sha=K.treasury_sha(), cuts_sha=K.sha_bytes(cuts), array_sha=array_sha(arr),
                data_end=int(B.t[-1]), n_bars=N, n_cands=len(cands), n_rows=int(len(arr["cand"])),
                rejected_at_cut=int(len(arr["rej_cand"])), built=pd.Timestamp.now(tz="UTC").isoformat())
    OUT.mkdir(parents=True, exist_ok=True)
    f = OUT / f"tables_{symbol}_{tf}.npz"
    np.savez_compressed(f, meta=json.dumps(meta), cands=json.dumps(cands), **arr)
    print(f"{symbol} {tf}: {len(cands)} candidates, {meta['n_rows']:,} signal rows, {meta['rejected_at_cut']} rejected at a cut "
          f"-> {f.name} ({time.time() - t0:.0f}s)")
    return f


def current_inputs(tf):
    """Digests of the inputs as they are NOW (cached per process): data, raw manifest, symbols, Treasury, code, cuts."""
    if tf not in _INPUTS:
        B, cuts, _ = load_xau(tf)
        raw_sha, _ = K.raw_manifest_sha()
        _INPUTS[tf] = dict(data_sha=data_sha(B), data_end=int(B.t[-1]), n_bars=len(B.t), cuts_sha=K.sha_bytes(cuts),
                           raw_manifest_sha=raw_sha, symbols_sha=K.symbols_sha(), treasury_sha=K.treasury_sha(),
                           code_sha=K.sha_files(*CODE_FILES))
    return _INPUTS[tf]


def load(symbol, tf, verify=True, path=None):
    """Load a table with the fail-closed C5 checks: schema / cost version / stored-array digest / strictly increasing bar
    times / recomputed data, raw-manifest, symbol-JSON, Treasury, cut-vector, code digests, data end and bar count."""
    z = np.load(path or (OUT / f"tables_{symbol}_{tf}.npz"), allow_pickle=False)
    meta = json.loads(str(z["meta"])); cands = json.loads(str(z["cands"]))
    arr = {x: z[x] for x in z.files if x not in ("meta", "cands")}
    if meta["schema"] != K.SCHEMA or meta["cost_version"] != K.COST_VERSION:
        raise ValueError(f"table {symbol} {tf}: schema/cost version mismatch {meta['schema']} {meta['cost_version']}")
    if len(cands) != meta["n_cands"] or len(arr["cand"]) != meta["n_rows"]:
        raise ValueError(f"table {symbol} {tf}: candidate or row count differs from its metadata")
    if array_sha(arr) != meta["array_sha"]:
        raise ValueError(f"table {symbol} {tf}: stored arrays do not match their digest")
    K.check_series(arr["bar_t"], f"table {symbol} {tf} bar times")
    if verify:
        cur = current_inputs(tf)
        for key in ("data_sha", "raw_manifest_sha", "symbols_sha", "treasury_sha", "cuts_sha", "code_sha", "data_end", "n_bars"):
            if cur[key] != meta[key]:
                raise ValueError(f"table {symbol} {tf}: {key} differs from the current input; rebuild")
    return meta, cands, arr


if __name__ == "__main__":
    build(sys.argv[1], sys.argv[2])
