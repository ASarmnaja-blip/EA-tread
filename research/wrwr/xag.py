"""Silver (XAGUSD) for WRWR Test B (docs/WRWR_HISTORY_OOS_PREREG.md). A new file: nothing in forward_shadow.SHADOW_FILES changes.
HistData M1 (New York time with DST -> UTC, as gold in research/history/build_histdata.py) -> H1 bars (price as quoted, volume
proxy = M1 bars in the hour) + the recorded Exness M5 spread (first M5 bar of the hour, 2023-09 onwards); the pre-registered
timezone checks; a generic potential-signal table builder (the exact loops of signals.build / build_f2.build with the cost
function passed in) with a bit-parity test against the frozen gold H4 tables; silver tables and a fail-closed table loader for
portfolio.load_pool. Research only; no orders.
Usage: python research/wrwr/xag.py bars | tzcheck | parity | tables <zoo|f2> <TF> [TF ...]"""
from __future__ import annotations

import hashlib
import io
import json
import sys
import time
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import contracts as K  # noqa: E402
import signals as SG  # noqa: E402
import f2_signals as F2  # noqa: E402
import build_f2 as BF2  # noqa: E402

sys.path[:0] = [str(K.ROOT / "research" / "foundry"), str(K.ROOT / "research" / "sieve")]
import engine as E  # noqa: E402
import features as FT  # noqa: E402

SYM = "XAGUSD"
HD = K.ROOT / "data" / "history" / "histdata" / "xag"
EX = K.ROOT / "data" / "fresh" / "XAGUSD_M5.npz"
OUT = K.ROOT / "data" / "wrwr" / "xag"
BARS = OUT / "XAGUSD_H1.npz"
HD_SHA = "91e3ebdab77ca1d94f1bf850ed6e4a923b071f61a8cf561cfa57fbf1a5955991"      # docs/WRWR_XAG_MANIFEST.md
EX_SHA = "b9698eb6f465c669326de1edadb68389871e7a956ebc20ff31237613a8adb632"
ROUND = {"round50_x": 0.5, "round100_x": 1.0}             # silver's own quote grid (prereg: gold's $50 / $100 divided by 100)
T2023 = int(pd.Timestamp("2023-01-01").timestamp())
_C = {}


# ------------------------------------------------------------------ raw data and bars
def check_raw():
    """Recompute the frozen digests of the HistData zips and the Exness M5 file; fail closed on any difference."""
    if "raw" not in _C:
        lines = [f"{f.name} {f.stat().st_size} {hashlib.sha256(f.read_bytes()).hexdigest()}" for f in sorted(HD.glob("XAGUSD_M1_*.zip"))]
        a = hashlib.sha256("\n".join(lines).encode()).hexdigest()
        b = hashlib.sha256(EX.read_bytes()).hexdigest()
        if a != HD_SHA or b != EX_SHA:
            raise ValueError(f"silver raw data differs from docs/WRWR_XAG_MANIFEST.md (HistData {a[:12]}, Exness {b[:12]})")
        _C["raw"] = (a, b)
    return _C["raw"]


def read_m1():
    parts, dropped = [], 0
    for f in sorted(HD.glob("XAGUSD_M1_*.zip")):
        z = zipfile.ZipFile(f)
        n = [x for x in z.namelist() if x.endswith(".csv")][0]
        d = pd.read_csv(io.BytesIO(z.read(n)), sep=";", header=None, names=["ts", "o", "h", "l", "c", "v"])
        t = pd.to_datetime(d.ts, format="%Y%m%d %H%M%S").dt.tz_localize("America/New_York", ambiguous="NaT", nonexistent="NaT")
        ok = t.notna().to_numpy()
        d = d[ok].copy()
        d["t"] = t[ok].dt.tz_convert("UTC").dt.tz_localize(None).to_numpy().astype("datetime64[s]").astype(np.int64)
        parts.append(d[["t", "o", "h", "l", "c"]]); dropped += int((~ok).sum())
    M = pd.concat(parts).drop_duplicates("t").sort_values("t", kind="stable")
    return M, dropped


def build_bars():
    t0 = time.time()
    hd_sha, ex_sha = check_raw()
    M, dropped = read_m1()
    t = M.t.to_numpy(np.int64); c = M.c.to_numpy(float)
    big = int((np.abs(np.diff(np.log(c))) > 0.05).sum())
    g = pd.DataFrame(dict(k=t // 3600, o=M.o.to_numpy(float), h=M.h.to_numpy(float), l=M.l.to_numpy(float), c=c)).groupby("k").agg(
        o=("o", "first"), h=("h", "max"), l=("l", "min"), c=("c", "last"), n=("o", "size"))
    x = np.load(EX)
    et = x["t"].astype(np.int64)
    if not (np.diff(et) > 0).all():
        raise ValueError("Exness XAGUSD M5 times are not strictly increasing")
    esp = x["sp"].astype(float) / x["c"].astype(float) * 1e4
    first = pd.Series(esp, index=et // 3600).groupby(level=0).first()          # first M5 bar of the hour
    sp = first.reindex(g.index).to_numpy(float)
    a = dict(t=g.index.to_numpy(np.int64) * 3600, o=g.o.to_numpy(float), h=g.h.to_numpy(float), l=g.l.to_numpy(float),
             c=g.c.to_numpy(float), v=g.n.to_numpy(float), sp=sp)
    K.check_series(a["t"], "XAGUSD H1")
    meta = dict(symbol=SYM, hd_manifest_sha=hd_sha, ex_sha=ex_sha, n_m1=int(len(M)), dropped_dst=dropped, m1_moves_over_5pct=big,
                n_h1=int(len(a["t"])), h1_with_spread=int(np.isfinite(sp).sum()), first=int(a["t"][0]), last=int(a["t"][-1]),
                data_sha=K.sha_bytes(*(a[k] for k in ("t", "o", "h", "l", "c", "v", "sp"))), built=pd.Timestamp.now(tz="UTC").isoformat())
    OUT.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(BARS, meta=json.dumps(meta), **a)
    wk = pd.Series(1, index=pd.to_datetime(a["t"], unit="s")).resample("W-FRI").sum()
    wk = wk[wk > 0]
    print(f"XAGUSD M1 {meta['n_m1']:,} bars ({dropped} dropped at DST changes), {big} M1 moves > 5 %; H1 {meta['n_h1']:,} bars "
          f"{pd.to_datetime(meta['first'], unit='s')} .. {pd.to_datetime(meta['last'], unit='s')}, {meta['h1_with_spread']:,} with an Exness spread; "
          f"H1 bars per week: median {int(wk.median())}, 5th pct {int(wk.quantile(0.05))} ({time.time() - t0:.0f}s)")
    return meta


def load_bars():
    if "bars" not in _C:
        z = np.load(BARS, allow_pickle=False)
        meta = json.loads(str(z["meta"]))
        a = {k: z[k] for k in ("t", "o", "h", "l", "c", "v", "sp")}
        hd_sha, ex_sha = check_raw()
        if meta["hd_manifest_sha"] != hd_sha or meta["ex_sha"] != ex_sha:
            raise ValueError("XAGUSD_H1.npz was built from other raw files; rebuild")
        if K.sha_bytes(*(a[k] for k in ("t", "o", "h", "l", "c", "v", "sp"))) != meta["data_sha"]:
            raise ValueError("XAGUSD_H1.npz arrays do not match their digest")
        _C["bars"] = (a, meta)
    return _C["bars"]


def load_xag(tf):
    """Silver twin of signals.load_xau: (bars, cuts, regime cells). Regime cells and cuts from engine.build on silver H1."""
    if "base" not in _C:
        a, _ = load_bars()
        H, _, cuts, cell = E.build(a["t"], a["o"], a["h"], a["l"], a["c"], a["sp"], a["c"], a["h"], a["l"])
        _C["base"] = (SG.mk(a["t"], a["o"], a["h"], a["l"], a["c"], a["v"], a["sp"], 3600), cuts, cell)
    base, cuts, cell = _C["base"]
    if "tf_" + tf not in _C:
        B = base if tf == "H1" else SG.resample(base, SG.STEP[tf])
        K.check_series(B.t, f"XAGUSD {tf}")
        _C["tf_" + tf] = B
    return _C["tf_" + tf], cuts, cell


def patch_marks():
    """portfolio.load_pool reads the mark-price bars through signals.load_xau("H1"); in a silver process that must be silver."""
    SG.load_xau = load_xag


# ------------------------------------------------------------------ timezone checks (prereg Test B)
def _dst(t):
    u = pd.to_datetime(t, unit="s")
    ny = u.tz_localize("UTC").tz_convert("America/New_York").tz_localize(None)
    return np.asarray((ny - u) == pd.Timedelta(hours=-4))


def tzcheck():
    a, _ = load_bars()
    hs = pd.Series(a["c"], index=a["t"])
    x = np.load(EX)
    e = pd.DataFrame(dict(k=x["t"].astype(np.int64) // 3600, c=x["c"].astype(float), n=1)).groupby("k").agg(c=("c", "last"), n=("n", "sum"))
    e = e[e.n >= 10]
    et = e.index.to_numpy(np.int64) * 3600; ec = e.c.to_numpy()
    summer = _dst(et)
    ok = True
    print("(i) HistData H1 close at T + s vs Exness H1 close at T, MAD of the difference (bp):")
    for half, m in (("summer", summer), ("winter", ~summer)):
        mads, meds = {}, {}
        for s in (-2, -1, 0, 1, 2):
            v = hs.reindex(et[m] + s * 3600).to_numpy()
            dfx = (v - ec[m]) / ec[m] * 1e4
            dfx = dfx[np.isfinite(dfx)]
            meds[s] = float(np.median(dfx)); mads[s] = float(np.median(np.abs(dfx - np.median(dfx))))
        best = min(mads, key=mads.get)
        passed = best == 0 and mads[0] <= 0.5 * min(mads[-1], mads[1])
        ok &= passed
        print(f"   {half}: " + "  ".join(f"s{s:+d} {mads[s]:6.2f}" for s in mads) + f"  -> {'PASS' if passed else 'FAIL'}"
              f"  (s=0: median {meds[0]:+.2f} bp, MAD {mads[0]:.2f} bp; C5 info |median|<=2 and MAD<=1: "
              f"{'yes' if abs(meds[0]) <= 2 and mads[0] <= 1 else 'no'})")
    H, _, _, _ = E.load()

    def rets(t, c):
        t = np.asarray(t, np.int64); r = np.full(len(t), np.nan)
        step1 = np.r_[False, np.diff(t) == 3600]
        r[1:] = np.where(step1[1:], np.diff(np.log(np.asarray(c, float))), np.nan)
        return pd.Series(r, index=t)
    rs = rets(a["t"], a["c"]); rg = rets(H.t, H.c)
    ts = rs.index.to_numpy(np.int64)
    yr = pd.to_datetime(ts, unit="s").year.to_numpy(); sm = _dst(ts)
    print("(ii) corr(silver H1 return at T, gold H1 return at T + L), L = -1 / 0 / +1 h, by year and DST half:")
    fails = []
    line = []
    for y in range(2009, 2027):
        for half, hm in (("S", sm), ("W", ~sm)):
            m0 = (yr == y) & hm
            cs = {}
            for L in (-1, 0, 1):
                g = rg.reindex(ts[m0] + L * 3600).to_numpy(); s_ = rs.to_numpy()[m0]
                mm = np.isfinite(g) & np.isfinite(s_)
                cs[L] = float(np.corrcoef(s_[mm], g[mm])[0, 1]) if mm.sum() > 50 else float("nan")
            passed = np.isfinite(cs[0]) and cs[0] > max(cs[-1], cs[1])
            if not passed:
                fails.append((y, half, cs))
            line.append(f"{y}{half} {cs[-1]:+.2f}/{cs[0]:+.2f}/{cs[1]:+.2f}")
    for i in range(0, len(line), 6):
        print("   " + "   ".join(line[i:i + 6]))
    ok &= not fails
    print(f"   -> {'PASS' if not fails else 'FAIL ' + str(fails)}")
    print("TIMEZONE CHECKS PASS" if ok else "TIMEZONE CHECKS FAIL: Test B stops")
    return ok


# ------------------------------------------------------------------ tables
def build_table(B, cuts, sig, tf, cost_fn, symbol, sessions=None, skip_empty=False):
    """The candidate loops of signals.build (sessions=None, skip_empty=False) and build_f2.build (sessions dict, skip_empty=True)
    with the round-trip cost of the entry bars given by cost_fn(entry_bar_indices)."""
    N = len(B.t); step = B.step
    ek, at_cut = K.entry_week(B.t, cuts)
    ok_bar = np.isfinite(B.atr) & (ek >= 0)
    hours = pd.to_datetime(B.t, unit="s").hour.to_numpy()
    cands, cols = [], {x: [] for x in SG.COLS}
    rej_c, rej_e = [], []
    for name, (sl, ss) in sig.items():
        il, is_ = np.flatnonzero(sl[:-1]), np.flatnonzero(ss[:-1])
        ent0 = np.r_[il, is_] + 1; d0 = np.r_[np.ones(len(il)), -np.ones(len(is_))]
        o_ = np.argsort(ent0, kind="stable"); ent0, d0 = ent0[o_], d0[o_]
        if skip_empty and not len(ent0):
            continue
        for sname, (h0, h1) in (sessions or {None: (0, 24)}).items():
            in_sess = (hours[ent0] >= h0) & (hours[ent0] < h1)
            for mode, sgn in (("FOLLOW", 1.0), ("FADE", -1.0)):
                d = d0 * sgn
                for k in SG.KS:
                    for hold in SG.HOLDS[tf]:
                        base_ok = in_sess & ok_bar[ent0] & (ent0 < N - hold - 2)
                        rej = base_ok & at_cut[ent0]
                        keep = base_ok & ~at_cut[ent0]
                        e, dd = ent0[keep], d[keep]
                        if skip_empty and not len(e):
                            continue
                        stop = k * B.atr[e]
                        c_bp = cost_fn(e)
                        for lab, mult in SG.EXITS:
                            g, ex = E.simulate(B, e, dd, stop, mult * stop, e + hold - 1)
                            sw = K.swap_bp(symbol, B.t[e], B.t[ex] + step, dd)
                            ci = len(cands)
                            cands.append(dict(tf=tf, setup=name if sname is None else f"{name}|{sname}", mode=mode, k_atr=k, exit=lab,
                                              hold=hold, n=int(len(e))))
                            cols["cand"].append(np.full(len(e), ci, np.int32)); cols["ent"].append(e.astype(np.int32))
                            cols["ex"].append(ex.astype(np.int32)); cols["dir"].append(dd.astype(np.int8))
                            cols["gross_bp"].append(g.astype(np.float32)); cols["cost_bp"].append(c_bp.astype(np.float32))
                            cols["swap_bp"].append(sw.astype(np.float32))
                            cols["stop_px"].append(stop.astype(np.float32)); cols["entry_px"].append(B.o[e].astype(np.float32))
                            if rej.any():
                                rej_c.append(np.full(int(rej.sum()), ci, np.int32)); rej_e.append(ent0[rej].astype(np.int32))
    arr = {x: np.concatenate(v) for x, v in cols.items()}
    arr["bar_t"] = B.t
    arr["rej_cand"] = np.concatenate(rej_c) if rej_c else np.zeros(0, np.int32)
    arr["rej_ent"] = np.concatenate(rej_e) if rej_e else np.zeros(0, np.int32)
    return cands, arr


def parity():
    """The generic builder must reproduce the frozen gold H4 tables (zoo and Family 2) bit for bit."""
    B, cuts, _ = SG.load_xau("H4")
    cost = lambda e: K.cost_bp("XAUUSD", B.spread_bp[e])
    ok = True
    for sigset, path in (("zoo", SG.OUT / "tables_XAUUSD_H4.npz"), ("f2", SG.OUT / "tables_XAUUSD_H4_f2.npz")):
        t0 = time.time()
        sig = FT.zoo_signals(B) if sigset == "zoo" else F2.f2_signals(B, cuts)
        cands, arr = build_table(B, cuts, sig, "H4", cost, "XAUUSD", sessions=None if sigset == "zoo" else {"ALL": (0, 24)},
                                 skip_empty=sigset == "f2")
        z = np.load(path, allow_pickle=False)
        key = lambda cl: [(c["tf"], c["setup"], c["mode"], c["k_atr"], c["exit"], c["hold"], c["n"]) for c in cl]
        same_c = key(cands) == key(json.loads(str(z["cands"])))
        diff = [x for x in SG.COLS + ("bar_t", "rej_cand", "rej_ent") if not np.array_equal(arr[x], z[x])]
        same_sha = SG.array_sha(arr) == json.loads(str(z["meta"]))["array_sha"]
        passed = same_c and not diff and same_sha
        ok &= passed
        print(f"parity gold H4 {sigset}: {len(cands)} candidates, {len(arr['cand']):,} rows; candidates equal {same_c}, arrays differing {diff}, "
              f"array digest equal {same_sha} -> {'PASS' if passed else 'FAIL'} ({time.time() - t0:.0f}s)", flush=True)
    return ok


def xag_cost(B):
    def f(e):
        c = K.cost_bp(SYM, B.spread_bp[e], entry_t=B.t[e])
        miss = (B.t[e] >= T2023) & ~np.isfinite(B.spread_bp[e])          # 2023+ without a recorded spread: the constant
        return np.where(miss, K.xag_pre2023_constant(), c)
    return f


def xag_signals(B, cuts, sigset):
    if sigset == "zoo":
        return FT.zoo_signals(B)
    sig = F2.f2_signals(B, cuts)
    c = np.asarray(B.c, float); n = len(c)
    for nm, step_ in ROUND.items():                                        # replaces gold's $50 / $100 grid in place
        fl = np.floor(c / step_)
        up = np.zeros(n, bool); dn = np.zeros(n, bool)
        up[1:] = fl[1:] > fl[:-1]; dn[1:] = fl[1:] < fl[:-1]
        sig[nm] = (up, dn)
    return sig


def code_digest():
    return K.sha_files(HERE / "xag.py", *SG.CODE_FILES, *BF2.F2_FILES)


def table_path(tf, sigset):
    return OUT / f"tables_XAGUSD_{tf}_{sigset}.npz"


def build_tables(sigset, tf):
    t0 = time.time()
    B, cuts, _ = load_xag(tf)
    sig = xag_signals(B, cuts, sigset)
    sessions = (BF2.SESSIONS if tf == "H1" else {"ALL": (0, 24)}) if sigset == "f2" else None
    cands, arr = build_table(B, cuts, sig, tf, xag_cost(B), SYM, sessions=sessions, skip_empty=sigset == "f2")
    code_sha = code_digest()
    for c in cands:
        c["hash"] = K.candidate_hash(c["tf"], c["setup"], c["mode"], c["k_atr"], c["exit"], c["hold"], code_sha)
    hd_sha, ex_sha = check_raw()
    meta = dict(schema=K.SCHEMA, symbol=SYM, tf=tf, step=B.step, cost_version=K.COST_VERSION, code_sha=code_sha, sigset=sigset,
                data_sha=SG.data_sha(B), raw_manifest_sha=hd_sha, ex_sha=ex_sha, symbols_sha=K.symbols_sha(), treasury_sha=K.treasury_sha(),
                cuts_sha=K.sha_bytes(cuts), array_sha=SG.array_sha(arr), data_end=int(B.t[-1]), n_bars=len(B.t), n_cands=len(cands),
                n_rows=int(len(arr["cand"])), rejected_at_cut=int(len(arr["rej_cand"])), round_levels=ROUND if sigset == "f2" else None,
                built=pd.Timestamp.now(tz="UTC").isoformat())
    np.savez_compressed(table_path(tf, sigset), meta=json.dumps(meta), cands=json.dumps(cands), **arr)
    print(f"XAGUSD {tf} {sigset}: {len(cands)} candidates, {meta['n_rows']:,} rows, {meta['rejected_at_cut']} rejected at a cut "
          f"-> {table_path(tf, sigset).name} ({time.time() - t0:.0f}s)", flush=True)


def make_loader(sigset):
    """Fail-closed loader for portfolio.load_pool: schema, cost version, signal set, counts, stored-array digest, bar times, and
    (verify) the current silver data, raw files, symbols, Treasury, cuts and code digests."""
    def loader(symbol, tf, verify=True):
        if symbol != SYM:
            raise ValueError(f"silver loader asked for {symbol}")
        z = np.load(table_path(tf, sigset), allow_pickle=False)
        meta = json.loads(str(z["meta"])); cands = json.loads(str(z["cands"]))
        arr = {x: z[x] for x in z.files if x not in ("meta", "cands")}
        if meta["schema"] != K.SCHEMA or meta["cost_version"] != K.COST_VERSION or meta["sigset"] != sigset:
            raise ValueError(f"silver table {tf} {sigset}: schema / cost version / signal set mismatch")
        if len(cands) != meta["n_cands"] or len(arr["cand"]) != meta["n_rows"] or SG.array_sha(arr) != meta["array_sha"]:
            raise ValueError(f"silver table {tf} {sigset}: counts or stored arrays differ from the metadata")
        K.check_series(arr["bar_t"], f"silver table {tf} bar times")
        if verify:
            B, cuts, _ = load_xag(tf)
            hd_sha, ex_sha = check_raw()
            cur = dict(data_sha=SG.data_sha(B), raw_manifest_sha=hd_sha, ex_sha=ex_sha, symbols_sha=K.symbols_sha(),
                       treasury_sha=K.treasury_sha(), cuts_sha=K.sha_bytes(cuts), code_sha=code_digest(), data_end=int(B.t[-1]), n_bars=len(B.t))
            for key, v in cur.items():
                if v != meta[key]:
                    raise ValueError(f"silver table {tf} {sigset}: {key} differs from the current input; rebuild")
        return meta, cands, arr
    return loader


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "bars":
        build_bars()
    elif cmd == "tzcheck":
        sys.exit(0 if tzcheck() else 1)
    elif cmd == "parity":
        sys.exit(0 if parity() else 1)
    elif cmd == "tables":
        for tf in sys.argv[3:]:
            build_tables(sys.argv[2], tf)
    else:
        raise SystemExit(__doc__)
