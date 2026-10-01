"""X7 of docs/BUNDLE_2026-10-01_PREREG.md = docs/UNCAPPED_COMPARISON_PREREG.md: WRWR with uncapped exits vs the Chandelier long-only baseline.
Candidates: Family 2 signals (gold: signals.load_xau bars; silver: xag.load_xag bars, HistData with the corrected clock), H1 / H4 / D1,
sessions as before, FOLLOW / FADE, initial stop k = 1 or 2 ATR, NO take-profit and NO maximum hold; exits: trailing stop at the best price
since entry -/+ 2 or 3 x ATR at entry (never looser than the initial stop; CHAND2 / CHAND3), or a close beyond the opposite 10- or 20-bar
channel with the initial stop active (CHAN10 / CHAN20). Costs C4, swap contracts.swap_bp. Selector, portfolio, risk rules, vol_scale,
regime cells and the 144 configurations unchanged (run_family.family / run, portfolio.load_pool / simulate), f = 1 %. Out-of-sample
procedure as batch 4 (largest trailing t of weekly net R at the first cut of each year). Baseline: Chandelier long-only D1 from X1.
Usage: python research/bundle/x7_wrwr_uncapped.py"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path[:0] = [str(HERE), str(ROOT / "research" / "wrwr"), str(ROOT / "research" / "foundry"), str(ROOT / "research" / "hyp")]
import common as C  # noqa: E402
import contracts as K  # noqa: E402
import signals as SG  # noqa: E402
import f2_signals as F2  # noqa: E402
import build_f2 as BF2  # noqa: E402
import portfolio as PF  # noqa: E402
import run_family as RF  # noqa: E402
import engine as E  # noqa: E402
import batch4_regime as B4  # noqa: E402

T0 = time.time()
log = lambda *a: print(f"[{time.time() - T0:6.0f}s]", *a, flush=True)
EXITS_U = (("CHAND2", "trail", 2.0), ("CHAND3", "trail", 3.0), ("CHAN10", "chan", 10), ("CHAN20", "chan", 20))
KS = (1, 2)
TFS = ["H1", "H4", "D1"]
CODE_SHA = K.sha_files(Path(__file__))


def sim_one(B, ents, d, stop, kind, par, nxt=None):
    """Uncapped exits for entries ents (bar indices, entry at the open), direction d, stop distances. Returns gross bp and exit bar."""
    n = len(B.c); o, h, l, c = B.o, B.h, B.l, B.c
    g = np.zeros(len(ents)); ex = np.zeros(len(ents), np.int64)
    for i in range(len(ents)):
        e = int(ents[i]); ep = o[e]; st0 = ep - d * stop[i]
        if kind == "chan":
            jc = nxt[e]; jend = min(jc, n - 1)
            hit = (l[e:jend + 1] <= st0) if d > 0 else (h[e:jend + 1] >= st0)
            if hit.any():
                x = e + int(np.argmax(hit)); px = st0 if (x == e or d * (o[x] - st0) > 0) else o[x]
            elif jc < n - 1:
                x = jc + 1; px = o[jc + 1]                      # booked at the fill bar (the next open), never before
            else:
                x = n - 1; px = c[n - 1]
        else:
            m = par[0]; A_e = par[1][i]
            best = ep; j0 = e; W = 64; x = None
            while x is None:
                j1 = min(n, j0 + W)
                ext = h[j0:j1] if d > 0 else l[j0:j1]
                prev_best = (np.maximum.accumulate(np.r_[best, ext]) if d > 0 else np.minimum.accumulate(np.r_[best, ext]))[:-1]
                stp = np.maximum(st0, prev_best - m * A_e) if d > 0 else np.minimum(st0, prev_best + m * A_e)
                hit = (l[j0:j1] <= stp) if d > 0 else (h[j0:j1] >= stp)
                if hit.any():
                    k = int(np.argmax(hit)); x = j0 + k; s_ = stp[k]
                    px = s_ if (x == e or d * (o[x] - s_) > 0) else o[x]
                elif j1 >= n:
                    x = n - 1; px = c[n - 1]
                else:
                    best = (max(best, ext.max()) if d > 0 else min(best, ext.min())); j0 = j1; W *= 4
        g[i] = d * (px / ep - 1) * 1e4; ex[i] = x
    return g, ex


def build_tables(B, cuts, sig, tf, cost_fn, symbol):
    N = len(B.t); step = B.step
    ek, at_cut = K.entry_week(B.t, cuts)
    ok_bar = np.isfinite(B.atr) & (ek >= 0)
    hours = pd.to_datetime(B.t, unit="s").hour.to_numpy()
    sessions = BF2.SESSIONS if tf == "H1" else {"ALL": (0, 24)}
    allent = set()
    for name, (sl, ss) in sig.items():
        allent.update((np.flatnonzero(sl[:-1]) + 1).tolist()); allent.update((np.flatnonzero(ss[:-1]) + 1).tolist())
    U = np.array(sorted(x for x in allent if x < N - 2 and ok_bar[x]), np.int64)
    res = {}
    for k in KS:
        stop = k * B.atr[U]
        for lab, kind, par in EXITS_U:
            for d in (1, -1):
                if kind == "chan":
                    lo, hi = C.chan_levels(B, par)
                    with np.errstate(invalid="ignore"):
                        nxt = C._next_true(B.c < lo) if d > 0 else C._next_true(B.c > hi)
                    g, ex = sim_one(B, U, d, stop, kind, par, nxt)
                else:
                    g, ex = sim_one(B, U, d, stop, kind, (par, B.atr[U]))
                res[(k, lab, d)] = (g, ex)
        log(f"  {symbol} {tf} k={k}: simulated {len(U)} entries x 4 exits x 2 directions")
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
                base_ok = in_sess & ok_bar[ent0] & (ent0 < N - 2)
                rej = base_ok & at_cut[ent0]; keep = base_ok & ~at_cut[ent0]
                e, dd = ent0[keep], d[keep]
                if not len(e):
                    continue
                pos = np.searchsorted(U, e)
                c_bp = cost_fn(e)
                for k in KS:
                    stop = k * B.atr[e]
                    for lab, _, _ in EXITS_U:
                        gL, xL = res[(k, lab, 1)]; gS, xS = res[(k, lab, -1)]
                        g = np.where(dd > 0, gL[pos], gS[pos]); ex = np.where(dd > 0, xL[pos], xS[pos])
                        sw = K.swap_bp(symbol, B.t[e], B.t[ex] + step, dd)
                        ci = len(cands)
                        cands.append(dict(tf=tf, setup=f"{name}|{sname}", mode=mode, k_atr=k, exit=lab, hold=0, n=int(len(e)),
                                          hash=K.candidate_hash(tf, f"{name}|{sname}", mode, k, lab, 0, CODE_SHA)))
                        cols["cand"].append(np.full(len(e), ci, np.int32)); cols["ent"].append(e.astype(np.int32))
                        cols["ex"].append(ex.astype(np.int32)); cols["dir"].append(dd.astype(np.int8))
                        cols["gross_bp"].append(g.astype(np.float32)); cols["cost_bp"].append(np.asarray(c_bp, np.float32))
                        cols["swap_bp"].append(sw.astype(np.float32))
                        cols["stop_px"].append(stop.astype(np.float32)); cols["entry_px"].append(B.o[e].astype(np.float32))
                        if rej.any():
                            rej_c.append(np.full(int(rej.sum()), ci, np.int32)); rej_e.append(ent0[rej].astype(np.int32))
    arr = {x: np.concatenate(v) for x, v in cols.items()}
    arr["bar_t"] = B.t
    arr["rej_cand"] = np.concatenate(rej_c) if rej_c else np.zeros(0, np.int32)
    arr["rej_ent"] = np.concatenate(rej_e) if rej_e else np.zeros(0, np.int32)
    meta = dict(cuts_sha=K.sha_bytes(cuts), step=step, n_rows=int(len(arr["cand"])), n_cands=len(cands), rejected_at_cut=int(len(arr["rej_cand"])),
                array_sha="uncapped", data_sha="", raw_manifest_sha="", code_sha=CODE_SHA)
    return meta, cands, arr


def finance_weekly(Rw, cuts, used):
    eq = 10_000.0; peak = eq; dd = 0.0; yearly = {}
    for k in np.flatnonzero(used):
        eq *= 1 + 0.01 * Rw[k]; peak = max(peak, eq); dd = max(dd, 1 - eq / peak); yearly[pd.Timestamp(int(cuts[k]), unit="s").year] = eq
    yrs = used.sum() / 52.18
    prev = 10_000.0; pos = 0
    for y in sorted(yearly):
        pos += yearly[y] > prev; prev = yearly[y]
    return dict(total_R=float(Rw[used].sum()), R_per_year=float(Rw[used].sum() / max(yrs, 0.1)), cagr=(eq / 10_000) ** (1 / max(yrs, 0.1)) - 1,
                dd=dd, pos_years=f"{pos}/{len(yearly)}")


def run_metal(sym):
    t0 = time.time()
    if sym == "XAUUSD":
        H, _, cuts, cell = E.load()
        loadB = SG.load_xau; sigf = lambda B, cuts: F2.f2_signals(B, cuts)
        costf = lambda B: (lambda e: K.cost_bp("XAUUSD", B.spread_bp[e]))
        H1 = H; years = list(range(2010, 2027))
    else:
        import xag as X
        X.patch_marks()
        H1, cuts, cell = X.load_xag("H1")
        loadB = X.load_xag; sigf = lambda B, cuts: X.xag_signals(B, cuts, "f2"); costf = X.xag_cost
        years = list(range(2012, 2027))
    TAB = {}
    for tf in TFS:
        B, cuts_tf, _ = loadB(tf)
        TAB[tf] = build_tables(B, cuts_tf, sigf(B, cuts_tf), tf, costf(B), sym)
        log(f"{sym} {tf}: {TAB[tf][0]['n_cands']} candidates, {TAB[tf][0]['n_rows']:,} rows")
    P = PF.load_pool(sym, TFS, cuts, verify=False, loader=lambda s, tf, verify=True: TAB[tf])
    S1, S2, NN = PF.shadow_stats(P)
    vs = K.causal_vol_scale(H1.t, H1.c, H1.h, H1.l, cuts, mode="historical", bar_seconds=3600)
    active = np.array([c != "" for c in cell] + [False] * (len(cuts) - len(cell)))[: len(cuts)]
    pools = {"H1": P.tf == "H1", "H4": P.tf == "H4", "D1": P.tf == "D1", "H1+H4+D1": np.isin(P.tf, TFS)}
    fam, _ = RF.family()
    scores = {(Lw, z): PF.window_scores(S1, S2, NN, Lw, z, RF.MINN)[0] for (Lw, z) in sorted({(c["window"], c["lcb_z"]) for c in fam})}
    R, EQ, champs, counters = RF.run(0.01, P, vs, active, pools, scores, fam)
    log(f"{sym}: 144 configurations simulated")
    out, used, picks = B4.oos(R, active, cuts, int(P.mark_t[-1]), years)
    fin = finance_weekly(out, cuts, used)
    tot = R[active].sum(0)
    full = dict(share_positive=float((tot > 0).mean()), best=float(tot.max()), median=float(np.median(tot)), worst=float(tot.min()))
    np.savez_compressed(C.OUT / f"x7_family_{sym}.npz", R=R, EQ=EQ, cuts=cuts, active=active, out=out, used=used)
    return dict(sym=sym, years=f"{years[0]}-{years[-1]}", picks={int(k): int(v) for k, v in picks.items()},
                pick_labels={int(Y): f"{fam[j]['window']}w z{fam[j]['lcb_z']:g} {fam[j]['pool']} m{fam[j]['m']} eq{fam[j]['equity_filter']}" for Y, j in picks.items()},
                oos=fin, full_sample_144=full, secs=time.time() - t0, cuts=cuts, active=active)


def baseline(sym, years):
    T = C.load(f"x1_trades_{sym}_D1.pkl")
    tk = T[(T.system == "CH") & (T.d > 0) & T.taken]
    a, b = f"{years[0]}-01-01", f"{years[-1] + 1}-01-01"
    x = tk[(tk.t >= C.ts(a)) & (tk.t < C.ts(b))]
    r = C.equity(x, 0.01, a, b)
    yrs = (C.ts(b) - C.ts(a)) / (365.25 * 86400)
    return dict(n=len(x), total_R=float(x.R.sum()), R_per_year=float(x.R.sum() / yrs), cagr=r.get("cagr"), dd=r.get("dd"), pos_years=r.get("pos_years"))


def main():
    res = {}
    for sym in ("XAUUSD", "XAGUSD"):
        r = run_metal(sym)
        yrs = list(range(int(r["years"][:4]), int(r["years"][-4:]) + 1))
        r["baseline_chandelier_long_only"] = baseline(sym, yrs)
        r.pop("cuts"); r.pop("active")
        res[sym] = r
        log(json.dumps({k: v for k, v in r.items() if k in ("oos", "baseline_chandelier_long_only", "full_sample_144")}, default=float))
        (C.OUT / "x7_wrwr_uncapped.json").write_text(json.dumps(res, indent=1, default=float))
    g, s = res["XAUUSD"], res["XAGUSD"]
    adds = all(m["oos"]["total_R"] > m["baseline_chandelier_long_only"]["total_R"] and m["oos"]["cagr"] > m["baseline_chandelier_long_only"]["cagr"]
               for m in (g, s))
    res["verdict"] = "WRWR adds value (beats the Chandelier long-only baseline on both metals in total R and CAGR)" if adds else \
        "WRWR does NOT add value over the simple trend rule: the trend rule is the core, WRWR at most a risk overlay"
    (C.OUT / "x7_wrwr_uncapped.json").write_text(json.dumps(res, indent=1, default=float))
    log(res["verdict"])


if __name__ == "__main__":
    main()
