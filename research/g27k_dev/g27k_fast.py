"""numba port of research/grid27k/g27k.py simulate(): the same loop, line for
line, compiled. Nights and R are computed afterwards in numpy with the same
C.nights. check() compares it with the original trade by trade."""
import numpy as np
from numba import njit

HCODE = {"H1": 1, "H2": 2, "H3": 3, "H4": 4, "H5": 5, "H6": 6}
TP = {"H4": 2.0, "H5": 3.0, "H6": 5.0}


@njit(cache=True)
def _sim(o, h, l, c, a14, a20, a22, t, bo, bh, bl, bt, k0, k1, lo20, hi20, lo10, hi10, swl, swh,
         s_idx, d_arr, fm, gm, hm, tpk, add):
    n = len(c)
    m = len(s_idx)
    TE = np.empty(m, np.int64); TX = np.empty(m, np.int64); DD = np.empty(m, np.int64)
    RISK = np.empty(m); PX = np.empty(m); U = np.zeros((m, 4)); UT = np.zeros((m, 4), np.int64); NU = np.zeros(m, np.int64)
    k = 0
    busy = -1
    for ii in range(m):
        s = s_idx[ii]; d = d_arr[ii]
        if s <= busy or s + 1 >= n:
            continue
        N = a20[s]
        e = -1; q0 = 0; ep = 0.0
        if fm == 1:
            e = s + 1; q0 = k0[e]; ep = o[e]
        else:
            lim = c[s] - d * 0.5 * N
            for jj in range(s + 1, min(s + 4, n)):
                for q in range(k0[jj], k1[jj]):
                    if (d > 0 and bl[q] <= lim) or (d < 0 and bh[q] >= lim):
                        ep = min(bo[q], lim) if d > 0 else max(bo[q], lim); e = jj; q0 = q
                        break
                if e >= 0:
                    break
            if e < 0:
                continue
        if gm == 1:
            sw = swl[s] if d > 0 else swh[s]
            if sw == sw and d * (ep - sw) > 0 and abs(ep - sw) <= 4 * a14[s]:
                sl = sw - d * 0.1 * a14[s]
            else:
                sl = ep - d * 2 * N
        else:
            sl = ep - d * (2.0 if gm == 2 else 3.0) * N
        risk = abs(ep - sl)
        if not risk > 0:
            continue
        tp = ep + d * tpk * risk if tpk > 0 else 0.0
        nu = 1; U[k, 0] = ep; UT[k, 0] = bt[q0]
        stop = sl; best = ep; px = np.nan; tx = 0; j = e; qs = q0
        while j < n:
            for q in range(qs, k1[j]):
                oq = ep if q == q0 else bo[q]; hq = bh[q]; lq = bl[q]
                if (d > 0 and lq <= stop) or (d < 0 and hq >= stop):
                    px = stop if d * (oq - stop) > 0 else oq; tx = bt[q]
                    break
                if tpk > 0 and ((d > 0 and hq >= tp) or (d < 0 and lq <= tp)):
                    px = tp if d * (tp - oq) > 0 else oq; tx = bt[q]
                    break
                if add and nu < 4:
                    n0 = nu
                    while nu < 4 and ((d > 0 and hq >= U[k, nu - 1] + 0.5 * N) or (d < 0 and lq <= U[k, nu - 1] - 0.5 * N)):
                        lvl = U[k, nu - 1] + d * 0.5 * N
                        f = max(lvl, oq) if d > 0 else min(lvl, oq)
                        U[k, nu] = f; UT[k, nu] = bt[q]; nu += 1
                        stop = max(stop, f - 2 * N) if d > 0 else min(stop, f + 2 * N)
                    if nu > n0 and ((d > 0 and lq <= stop) or (d < 0 and hq >= stop)):
                        px = stop; tx = bt[q]
                        break
            if px == px:
                break
            qs = -1
            if hm <= 3:
                best = max(best, h[j]) if d > 0 else min(best, l[j])
                if hm == 1:
                    hit = (c[j] < best - 3 * a22[j]) if d > 0 else (c[j] > best + 3 * a22[j])
                elif hm == 2:
                    hit = (c[j] < lo20[j]) if d > 0 else (c[j] > hi20[j])
                else:
                    hit = (c[j] < lo10[j]) if d > 0 else (c[j] > hi10[j])
                if hit and j + 1 < n:
                    j += 1; px = o[j]; tx = t[j]
                    break
            j += 1
            if j < n:
                qs = k0[j]
        if not (px == px):
            j = n - 1; px = c[j]; tx = t[j]
        TE[k] = t[e]; TX[k] = tx; DD[k] = d; RISK[k] = risk; PX[k] = px; NU[k] = nu
        k += 1
        busy = j
    return TE[:k], TX[:k], DD[:k], RISK[:k], PX[:k], U[:k], UT[:k], NU[:k]


def simulate(M, s_idx, d_arr, Fm, Gm, Hm, Im, nights):
    """Same return as g27k.simulate: list of (entry time, exit time, R, direction)."""
    f = lambda x: np.ascontiguousarray(x, dtype=np.float64)
    TE, TX, D, RISK, PX, U, UT, NU = _sim(
        f(M["o"]), f(M["h"]), f(M["l"]), f(M["c"]), f(M["a14"]), f(M["a20"]), f(M["a22"]), np.asarray(M["t"], np.int64),
        f(M["bo"]), f(M["bh"]), f(M["bl"]), np.asarray(M["bt"], np.int64), np.asarray(M["k0"], np.int64), np.asarray(M["k1"], np.int64),
        f(M["lo20"]), f(M["hi20"]), f(M["lo10"]), f(M["hi10"]), f(M["swl"]), f(M["swh"]),
        np.asarray(s_idx, np.int64), np.asarray(d_arr, np.int64), 1 if Fm == "F1" else 2, int(Gm[1]), HCODE[Hm], TP.get(Hm, 0.0), Im == "I2")
    if not len(TE):
        return []
    mask = np.arange(4)[None, :] < NU[:, None]
    ti, ui = np.nonzero(mask)
    nts = np.zeros(U.shape)
    nts[ti, ui] = nights(UT[ti, ui], TX[ti], M["rollover3"])
    swr = np.where(D > 0, M["swr"][1], M["swr"][-1])
    gross = (D[:, None] * (PX[:, None] - U) * mask).sum(1)
    cost = (U * (M["cost"] + swr[:, None] * nts) * mask).sum(1)
    R = (gross - cost) / RISK
    return [(int(a), int(b), float(r), int(d)) for a, b, r, d in zip(TE, TX, R, D)]
