"""C2 event-driven portfolio (docs/WRWR_CONTRACT_PREREG.md v4): one implementation for BASE, the optimiser, holdouts,
compounding, the random-router benchmark and the forward record. Research / paper only; no orders.

Pool  : potential-signal tables of several TFs (signals.py) stacked into global candidate ids.
Shadow: per candidate the chronological one-position filter -> selection statistics binned by the cut at which each
        exit is known (exit bar close <= cut).
Live  : champions chosen at each cut trade their own signals with entries in (cut_k, cut_{k+1}); admission, sizing,
        handover and skip rules exactly as C2."""
from __future__ import annotations

import heapq
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import contracts as K  # noqa: E402

LOT_STEP = 0.01
MIN_LOT = 0.01


@dataclass
class Pool:
    cands: list                      # dicts incl. tf, setup, mode, k_atr, exit, hold, hash
    entry_t: list                    # per candidate arrays (sorted by entry time)
    exit_t: list
    R: list
    R_stress: list
    stop_px: list
    entry_px: list
    ptr: np.ndarray                  # [cand, k] = first row with entry_t > cut_k
    cuts: np.ndarray
    contract: float
    rank_key: np.ndarray             # int ordering of candidate hashes (tie-breaks)
    exit_cfg: np.ndarray             # group id of (tf, k_atr, exit, hold)
    tf: np.ndarray = field(default=None)


def load_pool(symbol, tfs, cuts):
    import signals as SG
    cands, et, xt, R, RS, sp, ep = [], [], [], [], [], [], []
    cuts_sha = K.sha_bytes(cuts)
    for tf in tfs:
        meta, cl, a = SG.load(symbol, tf)
        if meta["cuts_sha"] != cuts_sha:
            raise ValueError(f"{tf}: cut vector differs from the pool's")
        bt = a["bar_t"]; step = meta["step"]
        order = np.lexsort((a["ent"], a["cand"]))
        cand = a["cand"][order]
        bounds = np.searchsorted(cand, np.arange(len(cl) + 1))
        for i, c in enumerate(cl):
            s, e = bounds[i], bounds[i + 1]
            rows = order[s:e]
            cands.append(c)
            et.append(bt[a["ent"][rows]]); xt.append(bt[a["ex"][rows]] + step)
            R.append(a["R"][rows].astype(float)); RS.append(a["R_stress"][rows].astype(float))
            sp.append(a["stop_px"][rows].astype(float)); ep.append(a["entry_px"][rows].astype(float))
    ptr = np.vstack([np.searchsorted(t, cuts, side="right") for t in et]).astype(np.int32)
    rank_key = np.argsort(np.argsort([c["hash"] for c in cands]))
    keys = [(c["tf"], c["k_atr"], c["exit"], c["hold"]) for c in cands]
    uniq = {k: i for i, k in enumerate(sorted(set(keys)))}
    return Pool(cands, et, xt, R, RS, sp, ep, ptr, cuts, float(K.SYMBOLS[symbol]["trade_contract_size"]),
                rank_key, np.array([uniq[k] for k in keys]), np.array([c["tf"] for c in cands]))


def shadow_stats(P):
    """S1, S2, N per candidate x cut index: shadow (one-position) trades binned by the cut at which they are known."""
    NW = len(P.cuts)
    S1 = np.zeros((len(P.cands), NW)); S2 = np.zeros_like(S1); NN = np.zeros_like(S1)
    for c in range(len(P.cands)):
        et, xt, r = P.entry_t[c], P.exit_t[c], P.R[c]
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


def simulate(P, champs, vol_scale, f=0.01, equity0=10_000.0, stress=False, log=None):
    """Event-driven live ledger. champs[k] = ranked champion ids for week k (entries in (cut_k, cut_{k+1})).
    Returns weekly R (exits in (cut_k, cut_{k+1}] / U_k), equity at each cut, and counters."""
    cuts = P.cuts; NW = len(cuts)
    equity = equity0
    open_pos = {}                        # pos id -> [cand, exit_t, pnl$, stop$, margin$]
    live_busy = set()
    heap = []                            # (time, 0 exit, pos id)
    pid = 0
    weekR = np.zeros(NW); eq_cut = np.zeros(NW)
    cnt = dict(entries=0, skip_busy=0, skip_weekstop=0, skip_riskcap=0, skip_margin=0, skip_minlot=0)
    Rarr = P.R_stress if stress else P.R
    for k in range(NW - 1):
        U = f * equity; eq_cut[k] = equity; realised = 0.0
        t_end = cuts[k + 1]
        ev = []
        for rank, c in enumerate(champs[k] if k < len(champs) else []):
            a, b = P.ptr[c, k], P.ptr[c, k + 1]
            for i in range(a, b):
                if P.entry_t[c][i] < t_end:
                    ev.append((int(P.entry_t[c][i]), 1, rank, int(P.rank_key[c]), c, i))
        ev.sort()
        ei = 0
        while True:
            nxt_exit = heap[0][0] if heap else None
            nxt_ent = ev[ei][0] if ei < len(ev) else None
            if nxt_exit is not None and nxt_exit <= t_end and (nxt_ent is None or nxt_exit <= nxt_ent):
                _, _, p = heapq.heappop(heap)
                c, _, pnl, _, _ = open_pos.pop(p)
                equity += pnl; realised += pnl; live_busy.discard(c)
                continue
            if nxt_ent is None:
                break
            _, _, rank, _, c, i = ev[ei]; ei += 1
            if c in live_busy:
                cnt["skip_busy"] += 1; continue
            if realised <= -3 * U:
                cnt["skip_weekstop"] += 1; continue
            risk = f * equity * vol_scale[k]
            lots = np.floor(risk / (P.stop_px[c][i] * P.contract) / LOT_STEP + 1e-9) * LOT_STEP
            if lots < MIN_LOT - 1e-12:
                cnt["skip_minlot"] += 1; continue
            stop_d = lots * P.stop_px[c][i] * P.contract
            if sum(v[3] for v in open_pos.values()) + stop_d > 3 * f * equity + 1e-9:
                cnt["skip_riskcap"] += 1; continue
            margin = lots * P.contract * P.entry_px[c][i] / K.LEVERAGE_FROZEN
            if equity - sum(v[4] for v in open_pos.values()) - margin < 0.5 * equity:
                cnt["skip_margin"] += 1; continue
            pnl = Rarr[c][i] * stop_d
            open_pos[pid] = [c, P.exit_t[c][i], pnl, stop_d, margin]
            heapq.heappush(heap, (int(P.exit_t[c][i]), 0, pid)); pid += 1
            live_busy.add(c); cnt["entries"] += 1
            if log is not None:
                log.append((k, c, int(P.entry_t[c][i]), int(P.exit_t[c][i]), float(lots), float(Rarr[c][i]), float(pnl)))
        weekR[k] = realised / U if U > 0 else 0.0
    eq_cut[NW - 1] = equity
    return weekR, eq_cut, cnt
