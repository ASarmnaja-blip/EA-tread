"""Potential-signal tables for WRWR Family 2 (docs/WRWR_FAMILY2_PREREG.md): same simulator, exits, costs and C5 metadata as
the zoo tables (signals.py), candidates from f2_signals x session x FOLLOW/FADE x stop x exit x hold.
Usage: python research/wrwr/build_f2.py H1|H4|D1   -> data/wrwr/tables_XAUUSD_<TF>_f2.npz"""
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
import signals as SG  # noqa: E402
import f2_signals as F2  # noqa: E402

sys.path.insert(0, str(K.ROOT / "research" / "foundry"))
import engine as E  # noqa: E402

F2_FILES = [HERE / "f2_signals.py", HERE / "build_f2.py"]
SESSIONS = {"ALL": (0, 24), "ASIA": (0, 7), "LONDON": (7, 12), "NY": (12, 17)}


def f2_code_sha():
    return K.sha_files(*F2_FILES)


def build(tf, symbol="XAUUSD"):
    t0 = time.time()
    B, cuts, _ = SG.load_xau(tf)
    N = len(B.t); step = B.step
    sig = F2.f2_signals(B, cuts)
    print(f"{tf}: {len(sig)} signals built ({time.time() - t0:.0f}s)", flush=True)
    ek, at_cut = K.entry_week(B.t, cuts)
    ok_bar = np.isfinite(B.atr) & (ek >= 0)
    hours = pd.to_datetime(B.t, unit="s").hour.to_numpy()
    sessions = SESSIONS if tf == "H1" else {"ALL": (0, 24)}
    cands, cols = [], {x: [] for x in SG.COLS}
    rej_c, rej_e = [], []
    for name, (sl, ss) in sig.items():
        il, is_ = np.flatnonzero(sl[:-1]), np.flatnonzero(ss[:-1])
        ent0 = np.r_[il, is_] + 1; d0 = np.r_[np.ones(len(il)), -np.ones(len(is_))]
        o_ = np.argsort(ent0, kind="stable"); ent0, d0 = ent0[o_], d0[o_]
        if not len(ent0):
            continue
        for sname, (h0, h1) in sessions.items():
            in_sess = (hours[ent0] >= h0) & (hours[ent0] < h1)
            for mode, sgn in (("FOLLOW", 1.0), ("FADE", -1.0)):
                d = d0 * sgn
                for k in SG.KS:
                    for hold in SG.HOLDS[tf]:
                        base_ok = in_sess & ok_bar[ent0] & (ent0 < N - hold - 2)
                        rej = base_ok & at_cut[ent0]
                        keep = base_ok & ~at_cut[ent0]
                        e, dd = ent0[keep], d[keep]
                        if not len(e):
                            continue
                        stop = k * B.atr[e]
                        c_bp = K.cost_bp(symbol, B.spread_bp[e])
                        for lab, mult in SG.EXITS:
                            g, ex = E.simulate(B, e, dd, stop, mult * stop, e + hold - 1)
                            sw = K.swap_bp(symbol, B.t[e], B.t[ex] + step, dd)
                            ci = len(cands)
                            cands.append(dict(tf=tf, setup=f"{name}|{sname}", mode=mode, k_atr=k, exit=lab, hold=hold, n=int(len(e))))
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
    zoo_code = K.sha_files(*SG.CODE_FILES)
    combined = K.sha_bytes(np.frombuffer((zoo_code + f2_code_sha()).encode(), np.uint8))
    for c in cands:
        c["hash"] = K.candidate_hash(c["tf"], c["setup"], c["mode"], c["k_atr"], c["exit"], c["hold"], combined)
    raw_sha, raw_n = K.raw_manifest_sha()
    meta = dict(schema=K.SCHEMA, symbol=symbol, tf=tf, step=step, cost_version=K.COST_VERSION, code_sha=zoo_code, f2_code_sha=f2_code_sha(),
                data_sha=SG.data_sha(B), raw_manifest_sha=raw_sha, raw_manifest_files=raw_n, symbols_sha=K.symbols_sha(),
                treasury_sha=K.treasury_sha(), cuts_sha=K.sha_bytes(cuts), array_sha=SG.array_sha(arr), data_end=int(B.t[-1]),
                n_bars=N, n_cands=len(cands), n_rows=int(len(arr["cand"])), rejected_at_cut=int(len(arr["rej_cand"])),
                sigset="f2", built=pd.Timestamp.now(tz="UTC").isoformat())
    f = SG.OUT / f"tables_{symbol}_{tf}_f2.npz"
    np.savez_compressed(f, meta=json.dumps(meta), cands=json.dumps(cands), **arr)
    print(f"{symbol} {tf} f2: {len(cands)} candidates, {meta['n_rows']:,} rows, {meta['rejected_at_cut']} rejected at a cut -> {f.name} ({time.time() - t0:.0f}s)")


def load_f2(tf, verify=True, symbol="XAUUSD"):
    path = SG.OUT / f"tables_{symbol}_{tf}_f2.npz"
    meta, cands, arr = SG.load(symbol, tf, verify=verify, path=path)
    if meta.get("sigset") != "f2" or (verify and meta["f2_code_sha"] != f2_code_sha()):
        raise ValueError(f"f2 table {tf}: signal set or Family-2 code differs from the current files; rebuild")
    return meta, cands, arr


def loader(symbol, tf, verify=True):
    return load_f2(tf, verify, symbol)


if __name__ == "__main__":
    build(sys.argv[1])
