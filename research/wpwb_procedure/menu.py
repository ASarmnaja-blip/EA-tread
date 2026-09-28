"""Frozen 38-tool menu for the WPWB procedure test (docs/WPWB_PROCEDURE_PREREG.md).

Round 1 (20) + round 2 without META (10) + round 3 (8), code and parameters
unchanged. Each tool has a declared lookback Lb (weeks) taken from its
parameters; a tool-week is valid only if the whole lookback lies inside the
data, so no tool silently runs on a truncated window.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "research" / "wpwb_search"))
import approaches as AP  # noqa: E402
import approaches2 as AP2  # noqa: E402
import common as C  # noqa: E402
from run_round3 import tsmi_week, volman_size  # noqa: E402

# Weeks of history each family reads before a cut (worst case over its code).
# CHOPREV: 20 trading days of M5 (~4 weeks) + H1 ATR14 -> 5.
# GAP: 52 past weeks. DAYREV: 26 weeks + 40 days (~6 weeks) -> 32.
# VOLMAN: 26-week sigma at each of 52 past cuts -> 78.


def _lookback(fam, params):
    if fam in ("A", "K"):
        return int(params["L"]) + 1
    if fam in ("B", "F", "G"):
        return int(params["W"])
    if fam == "C":
        return int(params["W"])
    if fam == "D":
        return 5
    if fam == "D-ungated":
        return 1
    if fam == "E":
        return 53
    if fam == "H":
        return 32
    if fam == "I":
        return 78
    raise ValueError(fam)


def manifest():
    """[(idx, fam, name, params, lookback_weeks)] in frozen menu order."""
    v = [(f, n, p) for f, n, p in AP.variants()]
    v += [(f, n, p) for f, n, p in AP2.variants2()]
    v += [("K", f"TSMI L={L}", dict(L=L)) for L in (8, 13)]
    v += [("I", f"VOLMAN hl={hl}", dict(hl=hl)) for hl in (4, 13)]
    v += [("D-ungated", f"CHOPREV-X z={z} H={H}", dict(z=z, H=H, gated=False))
          for z in (3.0, 4.0) for H in (2, 6)]
    assert len(v) == 38, len(v)
    assert not any(n.startswith("META") for _, n, _ in v)
    return [(i, f, n, p, _lookback(f, p)) for i, (f, n, p) in enumerate(v)]


def validity(m, cuts, man=None):
    """VALID[i, w]: tool i's full lookback before cut w lies inside the data
    and week w is complete. Metadata only - no outcome is read."""
    man = man or manifest()
    first = int(m.t[0])
    last_end = int(m.t[-1]) + C.HOUR
    cuts = np.asarray(cuts, np.int64)
    assert (cuts + C.WEEK <= last_end).all(), "incomplete final week"
    lb = np.array([x[4] for x in man])
    return (cuts[None, :] - lb[:, None] * C.WEEK) >= first


def _trades(fam, params, m, cut, eff, vcache):
    if fam in ("A", "B", "C", "D", "D-ungated", "E"):
        return AP.run_week(fam, m, cut, params, eff)[0], 1.0
    if fam in ("F", "G", "H"):
        return AP2.run_week2(fam, m, cut, params)[0], 1.0
    if fam == "K":
        return tsmi_week(fam, m, cut, params)[0], 1.0
    if fam == "I":
        lo, hi = m.week_bars(cut)
        if hi <= lo:
            return [], 1.0
        return [(lo, hi - 1, 1)], volman_size(m, cut, params["hl"], vcache)
    raise ValueError(fam)


def build_matrix(m, cuts, stress_levels=(1.0, 1.5), man=None):
    """R[stress][i, w] net bp, NTR[i, w] trade counts, INNER[i, w] the tool's
    own past-known position multiplier (VOLMAN's size, else 1). Asserts every
    trade starts and ends inside its own week and that a tool never holds two
    positions at once."""
    man = man or manifest()
    n = len(cuts)
    R = {s: np.zeros((len(man), n)) for s in stress_levels}
    NTR = np.zeros((len(man), n), int)
    INNER = np.ones((len(man), n))
    eff: dict = {}
    vcache: dict = {}
    for w, cut in enumerate(np.asarray(cuts, np.int64)):
        lo, hi = m.week_bars(int(cut))
        for i, fam, _, params, _ in man:
            tr, size = _trades(fam, params, m, int(cut), eff, vcache)
            INNER[i, w] = size
            if not tr:
                continue
            ii = np.array([t[0] for t in tr]); kk = np.array([t[1] for t in tr])
            dd = np.array([t[2] for t in tr])
            assert (ii >= lo).all() and (kk < hi).all() and (kk >= ii).all()
            order = np.argsort(ii)
            assert (ii[order][1:] > kk[order][:-1]).all(), f"overlap tool {i}"
            for s in stress_levels:
                R[s][i, w] = size * m.pnl_bp(ii, kk, dd, s).sum()
            NTR[i, w] = len(tr)
    return R, NTR, INNER
