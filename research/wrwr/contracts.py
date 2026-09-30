"""WRWR contracts (docs/WRWR_CONTRACT_PREREG.md v4): time axis (C1), symbol costs and swap (C4), causal vol_scale (C3),
hashing and cache metadata (C5). Research only; nothing here can place an order."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "research" / "foundry"), str(ROOT / "research" / "pilot"), str(ROOT / "research" / "wpwb_weekly")]
import vol as V  # noqa: E402

SCHEMA = "wrwr-v1"
COST_VERSION = "C4-v4"
SYMBOLS = json.loads((ROOT / "data" / "foundry" / "mt5_symbols_20260930.json").read_text())
MARKUP_PP = {"XAUUSD": 0.02, "XAGUSD": -0.20}            # percentage points per year over US 2y
COST_FLOOR_BP = {"XAUUSD": 2.0, "XAGUSD": 4.0}
SLIPPAGE_BP = 1.0
STRESS_BP = 2.0
LEVERAGE_FROZEN = 100.0


# ------------------------------------------------------------------ C1 time axis
def entry_week(open_t, cuts):
    """Week k of an entry whose bar opens at open_t: cut_k < open_t < cut_{k+1}. Returns (k, at_cut): an entry opening
    exactly at a cut is flagged at_cut=True and must be rejected; k = -1 before the first cut."""
    open_t = np.asarray(open_t, np.int64)
    i = np.searchsorted(cuts, open_t, side="left")           # cuts[i-1] < t <= cuts[i]
    at_cut = (i < len(cuts)) & (cuts[np.minimum(i, len(cuts) - 1)] == open_t)
    return i - 1, at_cut


def known_at_cut(close_t, cuts):
    """Index of the first cut at which something that closes at close_t is known: smallest i with close_t <= cut_i."""
    return np.searchsorted(cuts, np.asarray(close_t, np.int64), side="left")


def usable_bars(bar_open_t, bar_len, cut):
    """Bars that may inform a decision at `cut`: close time (open + length) <= cut."""
    return np.asarray(bar_open_t, np.int64) + int(bar_len) <= int(cut)


# ------------------------------------------------------------------ C4 costs and swap
def cost_bp(symbol, spread_bp, entry_t=None, xag_pre2023_const=None, stress=False):
    """Round-trip cost in bp: one entry spread + exactly 1.0 bp slippage, floored per symbol (+2 bp under stress)."""
    sp = np.asarray(spread_bp, float)
    if symbol == "XAGUSD" and entry_t is not None and xag_pre2023_const is not None:
        pre = np.asarray(entry_t, np.int64) < int(pd.Timestamp("2023-01-01").timestamp())
        c = np.where(pre, xag_pre2023_const, np.maximum(COST_FLOOR_BP[symbol], sp + SLIPPAGE_BP))
    else:
        c = np.maximum(COST_FLOOR_BP[symbol], np.where(np.isfinite(sp), sp, 0.0) + SLIPPAGE_BP)
    return c + (STRESS_BP if stress else 0.0)


_Y2 = {}


def _y2_series():
    if "s" not in _Y2:
        import external_traces as X
        y2 = X.treasury("nominal")["BC_2YEAR"].dropna().astype(float)
        y2.index = pd.to_datetime(y2.index)
        _Y2["s"] = y2.sort_index()
    return _Y2["s"]


def swap_bp(symbol, entry_open_t, exit_close_t, dirs):
    """C4 historical swap for longs (shorts 0): each rollover at 17:00 New York on day d charges
    nights_d x (US 2y of the latest Treasury date strictly before d + markup) / 100 / 365 x 1e4 bp, rollovers counted in
    (entry open, exit close]. Wednesday 3 nights, Saturday/Sunday none."""
    t0 = np.asarray(entry_open_t, np.int64); t1 = np.asarray(exit_close_t, np.int64); dirs = np.asarray(dirs, float)
    out = np.zeros(len(t0))
    idx = np.flatnonzero(dirs > 0)
    if not len(idx):
        return out
    y2 = _y2_series()
    d0 = pd.to_datetime(t0[idx].min() - 3 * 86400, unit="s").normalize()
    d1 = pd.to_datetime(t1[idx].max() + 3 * 86400, unit="s").normalize()
    days = pd.date_range(d0, d1, freq="D")
    roll = (days.tz_localize("America/New_York") + pd.Timedelta(hours=17)).tz_convert("UTC")
    roll_ep = roll.tz_localize(None).astype("datetime64[s]").astype(np.int64).to_numpy()
    dow = days.dayofweek.to_numpy()
    nights = np.where(dow == 2, 3, np.where(dow >= 5, 0, 1)).astype(float)
    j = np.searchsorted(y2.index.values.astype("datetime64[s]").astype(np.int64),
                        days.values.astype("datetime64[s]").astype(np.int64), side="left") - 1   # strictly before d
    rate = np.where(j >= 0, y2.to_numpy()[np.clip(j, 0, None)], y2.iloc[0]) + MARKUP_PP[symbol]
    rate = np.maximum(rate, 0.0)
    cum = np.r_[0.0, np.cumsum(nights * rate / 100 / 365 * 1e4)]
    a = np.searchsorted(roll_ep, t0[idx], side="right"); b = np.searchsorted(roll_ep, t1[idx], side="right")
    out[idx] = cum[b] - cum[a]
    return out


# ------------------------------------------------------------------ C3 causal vol_scale
def causal_vol_scale(h1_t, h1_c, h1_h, h1_l, cuts):
    """vol_scale_k from H1 bars only: F_k and calibration from weeks < k; B_REF_k = median valid RV over k-260 <= i < k
    (>= 52 valid weeks else 0.50); clip(sqrt(B_REF_k / F_k), 0.5, 1.0) with the calibration / last-week fail-safe."""
    rv_raw, _, _, nb = V.weekly_rv(h1_t, h1_c, h1_h, h1_l, cuts)
    rv = V.mask_invalid(rv_raw, nb)
    F = V.ewma_forecast(rv)
    out = np.full(len(cuts), V.SCALE_MIN)
    for k in range(1, len(cuts)):
        w = rv[max(0, k - 260):k]
        w = w[np.isfinite(w)]
        if len(w) < 52 or not np.isfinite(F[k]) or F[k] <= 0:
            continue
        raw = V.vol_scale(F[k], b_ref=float(np.median(w)))
        out[k] = V.effective_scale(raw, V.calibration(rv[:k], F[:k])[0], bool(nb[k - 1] >= V.MIN_BARS))
    return out


# ------------------------------------------------------------------ C5 hashing
def sha_bytes(*arrays):
    h = hashlib.sha256()
    for a in arrays:
        h.update(np.ascontiguousarray(a).tobytes())
    return h.hexdigest()


def sha_files(*paths):
    h = hashlib.sha256()
    for p in paths:
        h.update(Path(p).read_bytes())
    return h.hexdigest()


def check_series(t, name="series"):
    t = np.asarray(t, np.int64)
    if len(t) > 1 and not (np.diff(t) > 0).all():
        bad = int((np.diff(t) <= 0).sum())
        raise ValueError(f"{name}: {bad} non-increasing or duplicate timestamps")


def candidate_hash(tf, setup, mode, k_atr, exit_label, hold, code_sha):
    return hashlib.sha256(json.dumps([tf, setup, mode, float(k_atr), exit_label, int(hold), code_sha]).encode()).hexdigest()
