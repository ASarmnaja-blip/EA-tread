"""Plan step 2d (same-bar SL/TP ties), bound first: every realised live trade of the four SHADOW configurations is re-simulated with the
tie rule reversed (target first when one bar touches both levels; engine.simulate stop_first=False, an optimistic bound) and the weekly-R
change is summed. Rule fixed before running (docs/FOUNDRY_LEDGER.md, 2026-09-30): if the bound moves no configuration by more than 10 R
over the history and flips no sign of the lower bound of mean weekly R, the stop-first convention is kept and tick resolution is not
needed; otherwise ties are resolved from finer data (silver: HistData M1, the finest silver data on disk; an M1 bar touching both
levels stays stop-first). Descriptive; no endpoint changes.
Usage: python research/wrwr/tie_bound.py XAUUSD|XAGUSD"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import contracts as K  # noqa: E402
import gates as G  # noqa: E402
import portfolio as PF  # noqa: E402
import signals as SG  # noqa: E402

sys.path.insert(0, str(K.ROOT / "research" / "foundry"))
import engine as E  # noqa: E402

SHADOW = {"F2-66": 66, "F2-78": 78, "F2-134": 134, "F2-86": 86}
MULT = dict(SG.EXITS)


def setup(sym):
    if sym == "XAUUSD":
        import build_f2 as BF2
        _, _, cuts, _ = E.load()
        P = PF.load_pool(sym, ["H1", "H4", "D1"], cuts, verify=True, loader=BF2.loader)
        z = np.load(K.ROOT / "data" / "wrwr" / "family_XAUUSD_f2.npz", allow_pickle=False)
        bars = {tf: SG.load_xau(tf)[0] for tf in ("H1", "H4", "D1")}
    else:
        import xag as X
        import xag_run as XR
        X.patch_marks()
        _, cuts, _ = X.load_xag("H1")
        P = PF.load_pool(sym, ["H1", "H4", "D1"], cuts, verify=True, loader=X.make_loader("f2"))
        z = np.load(XR.fam_path("f2"), allow_pickle=False)
        bars = {tf: X.load_xag(tf)[0] for tf in ("H1", "H4", "D1")}
    return P, z, bars


def bound(P, z, bars, j, M1=None):
    ch = [[int(x) for x in w] for w in json.loads(str(z["champs"]))[str(j)]]
    log = []
    wr, eq, _ = PF.simulate(P, ch, z["vol_scale"], f=0.01, log=log)
    cuts = P.cuts; NW = len(cuts)
    dW = np.zeros(NW); ties = 0; n = 0; worst_mismatch = 0.0; tie_list = []
    for (k, c, te, xt, lots, R_i, pnl, eqe) in log:
        kx = int(np.searchsorted(cuts, xt, side="left")) - 1
        if kx >= NW - 1:
            continue
        cd = P.cands[c]; B = bars[cd["tf"]]
        i = int(np.searchsorted(P.entry_t[c], te)); e = int(np.searchsorted(B.t, te))
        d = float(P.dir[c][i]); stop = cd["k_atr"] * B.atr[e]; last = e + cd["hold"] - 1
        args = (B, [e], [d], [stop], [MULT[cd["exit"]] * stop], [last])
        g1, _ = E.simulate(*args, stop_first=True); g2, _ = E.simulate(*args, stop_first=False)
        worst_mismatch = max(worst_mismatch, abs(float(g1[0]) - float(P.gross_bp[c][i])))
        n += 1
        if g2[0] != g1[0]:
            ties += 1
            stop_d = lots * float(P.stop_px[c][i]) * P.contract
            wgt = stop_d / (0.01 * eq[kx]) / float(P.stop_bp[c][i])
            dW[kx] += (float(g2[0]) - float(g1[0])) * wgt
            _, ex1 = E.simulate(*args, stop_first=True)
            tie_list.append(dict(kx=kx, wgt=wgt, g1=float(g1[0]), d=d, ep=float(B.o[e]), stop=float(stop),
                                 tgt=float(MULT[cd["exit"]] * stop), t0=int(B.t[int(ex1[0])]), t1=int(B.t[int(ex1[0])]) + int(B.step),
                                 first_bar=int(ex1[0]) == e))
    act = z["active"]
    r0 = wr[act]; r1 = r0 + dW[act]
    out = dict(trades=n, ties=ties, total_R=float(r0.sum()), bound_R=float(dW[act].sum()), lb_before=G.lower_bound_mean(r0)[0],
               lb_after=G.lower_bound_mean(r1)[0], resim_max_abs_diff_bp=worst_mismatch)
    if M1 is not None:
        dR = np.zeros(NW); res = {"target": 0, "stop": 0, "both_in_one_m1": 0, "no_m1": 0}
        for tl in tie_list:
            how, g = resolve_m1(M1, tl)
            res[how] += 1
            dR[tl["kx"]] += (g - tl["g1"]) * tl["wgt"]
        r2 = r0 + dR[act]
        out.update(m1_resolved_R=float(dR[act].sum()), m1_outcomes=res, total_R_m1=float(r2.sum()), lb_m1=G.lower_bound_mean(r2)[0])
    return out


def resolve_m1(M1, tl):
    """Walk the M1 bars inside the tied bar in time order: the first M1 bar touching a level decides; touching both in one M1 bar
    stays stop-first; a first M1 bar opening beyond the stop fills at its open (the simulator's gap rule)."""
    t, o, h, l = M1
    a, b = np.searchsorted(t, tl["t0"], "left"), np.searchsorted(t, tl["t1"], "left")
    d, ep = tl["d"], tl["ep"]
    sl = ep - d * tl["stop"]; tp = ep + d * tl["tgt"]
    for q in range(a, b):
        hs = (l[q] <= sl) if d > 0 else (h[q] >= sl)
        ht = (h[q] >= tp) if d > 0 else (l[q] <= tp)
        if hs and ht:
            return "both_in_one_m1", tl["g1"]
        if ht:
            return "target", d * (tp / ep - 1) * 1e4
        if hs:
            gap = (o[q] < sl) if d > 0 else (o[q] > sl)
            px = o[q] if (gap and q == a and not tl["first_bar"]) else sl
            return "stop", d * (px / ep - 1) * 1e4
    return "no_m1", tl["g1"]


def main():
    sym = sys.argv[1]
    P, z, bars = setup(sym)
    M1 = None
    if sym == "XAGUSD":
        import xag as X
        m, _ = X.read_m1()
        M1 = tuple(m[c].to_numpy(np.int64 if c == "t" else float) for c in ("t", "o", "h", "l"))
    out = {}
    for nm, j in SHADOW.items():
        r = bound(P, z, bars, j, M1); out[nm] = r
        keep = abs(r["bound_R"]) <= 10 and np.sign(r["lb_before"]) == np.sign(r["lb_after"])
        print(f"{sym} {nm}: {r['trades']} trades, {r['ties']} same-bar ties ({r['ties'] / max(r['trades'], 1):.1%}); total R {r['total_R']:+.1f}, "
              f"target-first bound {r['bound_R']:+.2f} R; lb of mean weekly R {r['lb_before']:+.4f} -> {r['lb_after']:+.4f}; "
              f"re-simulation check {r['resim_max_abs_diff_bp']:.4f} bp -> {'stop-first kept' if keep else 'NEEDS FINER DATA'}", flush=True)
        if "m1_resolved_R" in r:
            print(f"    M1 resolution of the ties {r['m1_outcomes']}: change {r['m1_resolved_R']:+.2f} R -> total R {r['total_R_m1']:+.1f}, "
                  f"lb {r['lb_m1']:+.4f}", flush=True)
    (K.ROOT / "data" / "wrwr" / f"tie_bound_{sym}.json").write_text(json.dumps(out, indent=1, default=float))


if __name__ == "__main__":
    main()
