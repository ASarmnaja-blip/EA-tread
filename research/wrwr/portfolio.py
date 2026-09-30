"""C2 event-driven portfolio (docs/WRWR_CONTRACT_PREREG.md v5): one implementation for BASE, the optimiser, holdouts,
compounding, the random-router benchmark and the forward record. Research / paper only; no orders.

Pool  : potential-signal tables of several TFs (signals.py) stacked into global candidate ids (C5-verified loads).
Shadow: per candidate the chronological one-position filter -> selection statistics binned by the cut at which each
        exit is known (exit bar close <= cut).
Live  : champions chosen at each cut trade their own signals with entries in (cut_k, cut_{k+1}); admission, sizing,
        handover and skip rules exactly as C2; equity = balance + mark-to-market of open positions (v5)."""
from __future__ import annotations

import heapq
import sys
from bisect import bisect_right
from dataclasses import dataclass
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import contracts as K  # noqa: E402

LOT_STEP = 0.01
MIN_LOT = 0.01
RULES = ("BUSY", "WEEKSTOP", "MINLOT", "RISKCAP", "MARGIN", "RUIN")


@dataclass
class Pool:
    cands: list                      # dicts incl. tf, setup, mode, k_atr, exit, hold, hash
    entry_t: list                    # per candidate arrays (sorted by entry time)
    exit_t: list                     # exit BAR CLOSE time
    dir: list
    gross_bp: list
    cost_bp: list
    swap_bp: list
    stop_px: list
    entry_px: list
    R: list                          # net R of the candidate's own stop (float)
    stop_bp: list
    ptr: np.ndarray                  # [cand, k] = first row with entry_t > cut_k
    cuts: np.ndarray
    contract: float
    rank_key: np.ndarray             # int ordering of candidate hashes (tie-breaks)
    exit_cfg: np.ndarray             # group id of (tf, k_atr, exit, hold)
    tf: np.ndarray
    mark_t: np.ndarray               # H1 bar close times and closes: the mark price source (C2)
    mark_c: np.ndarray
    meta: dict
    rejected_at_cut: int = 0

    def R_stress(self, c):
        return self.R[c] - 2.0 / self.stop_bp[c]         # K.STRESS_BP = 2 bp of round-trip cost, in R of this stop


def load_pool(symbol, tfs, cuts, verify=True):
    import signals as SG
    cands, et, xt, dr, gb, cb, sb, sp, ep, R, stb = ([] for _ in range(11))
    cuts_sha = K.sha_bytes(cuts)
    metas = {}
    for tf in tfs:
        meta, cl, a = SG.load(symbol, tf, verify=verify)
        if meta["cuts_sha"] != cuts_sha:
            raise ValueError(f"{tf}: cut vector differs from the pool's")
        metas[tf] = meta
        bt = a["bar_t"]; step = meta["step"]
        order = np.lexsort((a["ent"], a["cand"]))
        cand = a["cand"][order]
        bounds = np.searchsorted(cand, np.arange(len(cl) + 1))
        if bounds[-1] != meta["n_rows"]:
            raise ValueError(f"{tf}: row count mismatch after sorting")
        gross, cost, swap = a["gross_bp"][order], a["cost_bp"][order], a["swap_bp"][order]
        stop_px, entry_px = a["stop_px"][order], a["entry_px"][order]
        stop_bp = (stop_px.astype(np.float64) / entry_px.astype(np.float64) * 1e4)
        Rall = ((gross.astype(np.float64) - cost - swap) / stop_bp)
        ent_t = bt[a["ent"][order]]; ex_t = bt[a["ex"][order]] + step
        dirs = a["dir"][order]
        stop_bp32 = stop_bp.astype(np.float32); R32 = Rall.astype(np.float32)
        del stop_bp, Rall
        for i, c in enumerate(cl):
            s, e = bounds[i], bounds[i + 1]
            cands.append(c)
            et.append(ent_t[s:e]); xt.append(ex_t[s:e]); dr.append(dirs[s:e]); gb.append(gross[s:e]); cb.append(cost[s:e])
            sb.append(swap[s:e]); sp.append(stop_px[s:e]); ep.append(entry_px[s:e]); R.append(R32[s:e]); stb.append(stop_bp32[s:e])
    if not tfs or "H1" not in tfs:
        raise ValueError("the pool needs H1 (mark price source)")
    widths = {len(c) for c in (cands,)}
    assert sum(m["n_cands"] for m in metas.values()) == len(cands), "candidate count differs from the table metadata"
    B1, cuts1, _ = SG.load_xau("H1")
    if K.sha_bytes(cuts1) != cuts_sha:
        raise ValueError("H1 cut vector differs from the pool's")
    ptr = np.vstack([np.searchsorted(t, cuts, side="right") for t in et]).astype(np.int32)
    assert ptr.shape == (len(cands), len(cuts)), "pointer matrix width"
    rank_key = np.argsort(np.argsort([c["hash"] for c in cands]))
    keys = [(c["tf"], c["k_atr"], c["exit"], c["hold"]) for c in cands]
    uniq = {k: i for i, k in enumerate(sorted(set(keys)))}
    return Pool(cands, et, xt, dr, gb, cb, sb, sp, ep, R, stb, ptr, cuts, float(K.SYMBOLS[symbol]["trade_contract_size"]),
                rank_key, np.array([uniq[k] for k in keys]), np.array([c["tf"] for c in cands]),
                B1.t + B1.step, B1.c, metas, sum(m["rejected_at_cut"] for m in metas.values()))


def shadow_stats(P):
    """S1, S2, N per candidate x cut index: shadow (one-position) trades binned by the cut at which they are known."""
    NW = len(P.cuts)
    S1 = np.zeros((len(P.cands), NW)); S2 = np.zeros_like(S1); NN = np.zeros_like(S1)
    for c in range(len(P.cands)):
        et, xt, r = P.entry_t[c], P.exit_t[c], P.R[c].astype(np.float64)
        keep, busy = [], -1
        for i in range(len(et)):
            if et[i] >= busy:                    # next entry opens at or after the previous exit bar's close
                keep.append(i); busy = xt[i]
        keep = np.asarray(keep, int)
        if not len(keep):
            continue
        kn = K.known_at_cut(xt[keep], P.cuts)
        ok = kn < NW
        S1[c] = np.bincount(kn[ok], r[keep][ok], NW); S2[c] = np.bincount(kn[ok], r[keep][ok] ** 2, NW)
        NN[c] = np.bincount(kn[ok], None, NW)
    return S1, S2, NN


def window_scores(S1, S2, NN, L, z, minn):
    """Score of every candidate at every cut k from shadow exits known at cuts (k-L, k]: mean - z * se; -inf if < minn."""
    cum = lambda A: np.c_[np.zeros((A.shape[0], 1)), np.cumsum(A, axis=1)]
    c1, c2, cn = cum(S1), cum(S2), cum(NN)
    NW = S1.shape[1]
    k = np.arange(NW); a = np.maximum(k - L + 1, 0)
    s1 = c1[:, k + 1] - c1[:, a]; s2 = c2[:, k + 1] - c2[:, a]; n = cn[:, k + 1] - cn[:, a]
    with np.errstate(invalid="ignore", divide="ignore"):
        mu = s1 / np.maximum(n, 1)
        var = (s2 - s1 * s1 / np.maximum(n, 1)) / np.maximum(n - 1, 1)
        sc = mu - z * np.sqrt(np.maximum(var, 0) / np.maximum(n, 1))
    return np.where(n >= minn, sc, -np.inf), n >= minn


def champions(sc, pool_mask, m, rank_key, active):
    """Per cut: up to m candidates of the pool with score > 0, best first, ties by candidate hash order."""
    out = []
    for k in range(sc.shape[1]):
        if not active[k]:
            out.append([]); continue
        s = np.where(pool_mask, sc[:, k], -np.inf)
        idx = np.flatnonzero(s > 0)
        if not len(idx):
            out.append([]); continue
        idx = idx[np.lexsort((rank_key[idx], -s[idx]))][:m]
        out.append(list(idx))
    return out


def _mark_lists(P):
    if not hasattr(P, "_mark_lists"):
        P._mark_lists = (P.mark_t.tolist(), P.mark_c.tolist())
    return P._mark_lists


def simulate(P, champs, vol_scale, f=0.01, equity0=10_000.0, stress=False, log=None, skiplog=None, rules=True, weekstop=True,
             evcache=None):
    """Event-driven live ledger. champs[k] = ranked champion ids for week k (entries in (cut_k, cut_{k+1})).
    Returns weekly R (exits in (cut_k, cut_{k+1}] / U_k, U_k = f x equity(cut_k)), equity(cut_k), and counters.
    equity(t) = balance + sum over open positions of notional x (dir x (mark_t / entry - 1) - cost_bp / 1e4) (v5).
    log: admitted trades; skiplog: every skipped signal with its rule and the causing state.
    rules=False is a DIAGNOSTIC only (fixed equity, no week stop / caps / margin / lot rounding); never a result."""
    cuts = P.cuts.tolist(); NW = len(cuts)
    mt, mc = _mark_lists(P)
    contract = P.contract
    lev = K.LEVERAGE_FROZEN
    balance = equity0
    open_pos = {}            # pid -> dict(c, lots, stop_d, notional, dir, entry_px, cost_frac, pnl)
    live_busy = set()
    heap = []
    pid = 0
    weekR = np.zeros(NW); eq_cut = np.zeros(NW)
    cnt = {"entries": 0, **{"skip_" + r.lower(): 0 for r in RULES}}

    def mark(t):
        i = bisect_right(mt, t) - 1
        return mc[i] if i >= 0 else float("nan")

    def equity_at(t):
        if not open_pos:
            return balance
        m = mark(t)
        return balance + sum(v["notional"] * (v["dir"] * (m / v["entry_px"] - 1.0) - v["cost_frac"]) for v in open_pos.values())

    def skip(rule, k, c, t, eq, realised):
        cnt["skip_" + rule.lower()] += 1
        if skiplog is not None:
            m = mark(t)
            used = sum(v["lots"] * contract * m / lev for v in open_pos.values())
            skiplog.append((k, int(c), int(t), rule, float(eq), float(realised), float(sum(v["stop_d"] for v in open_pos.values())), float(used)))

    stress_bp = 2e-4 if stress else 0.0
    for k in range(NW - 1):
        eq0 = equity_at(cuts[k]) if rules else equity0
        U = f * eq0; eq_cut[k] = eq0; realised = 0.0
        t_end = cuts[k + 1]
        ev = []
        for rank, c in enumerate(champs[k] if k < len(champs) else []):
            base = evcache.get((c, k)) if evcache is not None else None
            if base is None:
                a, b = int(P.ptr[c, k]), int(P.ptr[c, k + 1])
                base = []
                if b > a:
                    et = P.entry_t[c][a:b].tolist(); xt = P.exit_t[c][a:b].tolist(); spx = P.stop_px[c][a:b].tolist()
                    epx = P.entry_px[c][a:b].tolist(); cbp = P.cost_bp[c][a:b].tolist(); drr = P.dir[c][a:b].tolist()
                    rr = (P.R[c][a:b] - 2.0 / P.stop_bp[c][a:b] if stress else P.R[c][a:b]).tolist()
                    rk = int(P.rank_key[c])
                    for q in range(b - a):
                        if et[q] < t_end:                           # an entry exactly at the next cut is never traded
                            base.append((et[q], rk, c, xt[q], spx[q], epx[q], cbp[q], drr[q], rr[q]))
                if evcache is not None:
                    evcache[(c, k)] = base
            for t_, rk_, c_, xt_, sp_, ep_, cb_, dr_, r_ in base:
                ev.append((t_, rank, rk_, c_, xt_, sp_, ep_, cb_, dr_, r_))
        ev.sort()
        ei = 0
        while True:
            nxt_exit = heap[0][0] if heap else None
            nxt_ent = ev[ei][0] if ei < len(ev) else None
            if nxt_exit is not None and nxt_exit <= t_end and (nxt_ent is None or nxt_exit <= nxt_ent):
                _, p_ = heapq.heappop(heap)
                v = open_pos.pop(p_)
                balance += v["pnl"]; realised += v["pnl"]; live_busy.discard(v["c"])
                continue
            if nxt_ent is None:
                break
            te, rank, _rk, c, xt_i, stop_px, entry_px, cost_i, dir_i, R_i = ev[ei]; ei += 1
            if c in live_busy:
                skip("BUSY", k, c, te, equity_at(te) if skiplog is not None else 0.0, realised); continue
            eq = equity_at(te) if rules else equity0
            if rules and eq <= 0:
                skip("RUIN", k, c, te, eq, realised); continue
            if rules and weekstop and realised <= -3 * U:
                skip("WEEKSTOP", k, c, te, eq, realised); continue
            risk = f * eq * vol_scale[k]
            lots = (np.floor(risk / (stop_px * contract) / LOT_STEP + 1e-9) * LOT_STEP if rules
                    else risk / (stop_px * contract))
            if lots < MIN_LOT - 1e-12:
                skip("MINLOT", k, c, te, eq, realised); continue
            stop_d = lots * stop_px * contract
            if rules and sum(v["stop_d"] for v in open_pos.values()) + stop_d > 3 * f * eq + 1e-9:
                skip("RISKCAP", k, c, te, eq, realised); continue
            if rules and open_pos:
                m = mark(te)
                used = sum(v["lots"] * contract * m / lev for v in open_pos.values())
            else:
                used = 0.0
            new_margin = lots * contract * entry_px / lev
            if rules and eq - used - new_margin < 0.5 * eq:
                skip("MARGIN", k, c, te, eq, realised); continue
            notional = lots * contract * entry_px
            pnl = R_i * stop_d
            open_pos[pid] = dict(c=c, lots=lots, stop_d=stop_d, notional=notional, dir=float(dir_i), entry_px=entry_px,
                                 cost_frac=cost_i / 1e4 + stress_bp, pnl=pnl)
            heapq.heappush(heap, (xt_i, pid)); pid += 1
            live_busy.add(c); cnt["entries"] += 1
            if log is not None:
                log.append((k, c, int(te), int(xt_i), float(lots), float(R_i), float(pnl), float(eq)))
        weekR[k] = realised / U if U > 0 else 0.0
    eq_cut[NW - 1] = equity_at(cuts[NW - 1]) if rules else balance
    return weekR, eq_cut, cnt


# ------------------------------------------------------------------ shared-memory cache for worker processes
_CACHE_ARRAYS = ("entry_t", "exit_t", "dir", "cost_bp", "stop_px", "entry_px", "R", "stop_bp")


def save_pool_cache(P, dirpath, extra=None):
    """Concatenate the per-candidate arrays into .npy files (one per field) so worker processes can memory-map them
    (one shared copy in the page cache instead of one copy per process). `extra` = dict of numpy arrays saved alongside."""
    import json
    d = Path(dirpath); d.mkdir(parents=True, exist_ok=True)
    lens = np.array([len(x) for x in P.entry_t], np.int64)
    off = np.r_[0, np.cumsum(lens)]
    for name in _CACHE_ARRAYS:
        np.save(d / f"{name}.npy", np.concatenate(getattr(P, name)))
    np.save(d / "offsets.npy", off); np.save(d / "ptr.npy", P.ptr); np.save(d / "cuts.npy", P.cuts)
    np.save(d / "mark_t.npy", P.mark_t); np.save(d / "mark_c.npy", P.mark_c)
    for k, v in (extra or {}).items():
        np.save(d / f"{k}.npy", v)
    (d / "meta.json").write_text(json.dumps(dict(cands=P.cands, contract=P.contract, meta=P.meta, rejected_at_cut=P.rejected_at_cut,
                                                 tf=[str(x) for x in P.tf], rank_key=[int(x) for x in P.rank_key],
                                                 exit_cfg=[int(x) for x in P.exit_cfg])))


def load_pool_cache(dirpath):
    import json
    d = Path(dirpath)
    m = json.loads((d / "meta.json").read_text())
    off = np.load(d / "offsets.npy")
    arr = {n: np.load(d / f"{n}.npy", mmap_mode="r").view(np.ndarray) for n in _CACHE_ARRAYS}      # plain views: fast slicing
    n = len(m["cands"])
    sl = lambda name: [arr[name][off[i]:off[i + 1]] for i in range(n)]
    empty = [None] * n
    return Pool(m["cands"], sl("entry_t"), sl("exit_t"), sl("dir"), empty, sl("cost_bp"), empty, sl("stop_px"), sl("entry_px"),
                sl("R"), sl("stop_bp"), np.load(d / "ptr.npy"), np.load(d / "cuts.npy"), float(m["contract"]),
                np.array(m["rank_key"]), np.array(m["exit_cfg"]), np.array(m["tf"]), np.load(d / "mark_t.npy"),
                np.load(d / "mark_c.npy"), m["meta"], int(m["rejected_at_cut"]))
