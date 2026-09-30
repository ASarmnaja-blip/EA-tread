"""WRWR contracts (docs/WRWR_CONTRACT_PREREG.md v5): time axis (C1), symbol costs and swap (C4), causal vol_scale (C3),
hashing, cache integrity and splice validation (C5). Research only; nothing here can place an order."""
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

SCHEMA = "wrwr-v2"
COST_VERSION = "C4-v5"
SYMBOLS_FILE = ROOT / "data" / "foundry" / "mt5_symbols_20260930.json"
SYMBOLS = json.loads(SYMBOLS_FILE.read_text())
XAG_FREEZE_FILE = ROOT / "data" / "foundry" / "xag_cost_freeze.json"
HOLIDAY_FILE = ROOT / "data" / "foundry" / "wrwr_holidays_2003_2026.txt"
HOLIDAY_SHA = "35a2d982c06c84faa9809c2a9b6073fcff4a2de70b79d7430e0c506854464e8f"      # of the LF-normalised text (C5)
SYMBOLS_SHA = "4627adb587949264f4cd3ae8921f5df4b5ab7265f20d04e00298a5b70c4161bf"
TREASURY_SHA = "ced897410400c41167d2711e942a3fceac2d76f812720c9ea9ace3097560751b"
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


def mark_price(bar_close_t, bar_close_px, t):
    """Mark price at time t (C2 equity): close of the last bar whose close time <= t. NaN before the first bar."""
    i = np.searchsorted(np.asarray(bar_close_t, np.int64), np.asarray(t, np.int64), side="right") - 1
    return np.where(i >= 0, np.asarray(bar_close_px, float)[np.clip(i, 0, None)], np.nan)


# ------------------------------------------------------------------ C4 costs and swap
_XAG = {}


def xag_pre2023_constant():
    """Frozen C4 constant for XAGUSD entries before 2023 (data/foundry/xag_cost_freeze.json); fails closed if absent."""
    if "c" not in _XAG:
        if not XAG_FREEZE_FILE.exists():
            raise FileNotFoundError(f"{XAG_FREEZE_FILE} missing: XAG pre-2023 cost is not frozen (C4)")
        j = json.loads(XAG_FREEZE_FILE.read_text())
        if abs(j["constant_bp"] - max(4.0, 1.5 * j["median_spread_bp"] + 1.0)) > 1e-9:
            raise ValueError("xag_cost_freeze.json constant does not follow the C4 formula")
        _XAG["c"] = float(j["constant_bp"])
    return _XAG["c"]


def cost_bp(symbol, spread_bp, entry_t=None, stress=False):
    """Round-trip cost in bp: one entry spread + exactly 1.0 bp slippage, floored per symbol (+2 bp under stress).
    XAGUSD requires entry_t (and the frozen constant for entries before 2023); XAUUSD ignores entry_t."""
    sp = np.asarray(spread_bp, float)
    sp = np.where(np.isfinite(sp), sp, 0.0)
    obs = np.maximum(COST_FLOOR_BP[symbol], sp + SLIPPAGE_BP)
    if symbol == "XAGUSD":
        if entry_t is None:
            raise ValueError("cost_bp('XAGUSD') needs entry_t (C4: pre-2023 entries use the frozen constant)")
        pre = np.asarray(entry_t, np.int64) < int(pd.Timestamp("2023-01-01").timestamp())
        obs = np.where(pre, xag_pre2023_constant(), obs)
    return obs + (STRESS_BP if stress else 0.0)


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
def causal_vol_scale(h1_t, h1_c, h1_h, h1_l, cuts, mode="historical", bar_seconds=3600):
    """vol_scale_k from H1 bars only (bar_seconds must be 3600).
    historical: F_k and calibration from weeks < k; B_REF_k = median valid RV over k-260 <= i < k (>= 52 valid weeks,
    else 0.50); clip(sqrt(B_REF_k / F_k), 0.5, 1.0) with the calibration / last-week fail-safe.
    forward: same, but B_REF is the frozen spec constant vol.B_REF (known now)."""
    if mode not in ("historical", "forward"):
        raise ValueError(mode)
    rv_raw, _, _, nb = V.weekly_rv(h1_t, h1_c, h1_h, h1_l, cuts, bar_seconds=bar_seconds)
    rv = V.mask_invalid(rv_raw, nb)
    F = V.ewma_forecast(rv)
    out = np.full(len(cuts), V.SCALE_MIN)
    for k in range(1, len(cuts)):
        if not np.isfinite(F[k]) or F[k] <= 0:
            continue
        if mode == "historical":
            w = rv[max(0, k - 260):k]
            w = w[np.isfinite(w)]
            if len(w) < 52:
                continue
            bref = float(np.median(w))
        else:
            bref = V.B_REF
        raw = V.vol_scale(F[k], b_ref=bref)
        out[k] = V.effective_scale(raw, V.calibration(rv[:k], F[:k])[0], bool(nb[k - 1] >= V.MIN_BARS))
    return out


# ------------------------------------------------------------------ C5 hashing and integrity
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


def raw_manifest_sha():
    """Ordered manifest of the raw Dukascopy hour files behind every H1/H4/D1 series: sha256 of the lines
    '<SIDE>/<file> <sha256 of the file>' in name order (BID then ASK)."""
    base = ROOT / "data" / "history" / "dukascopy" / "cache" / "hour"
    lines = []
    for side in ("BID", "ASK"):
        for f in sorted((base / side).glob("*.npy")):
            lines.append(f"{side}/{f.name} {hashlib.sha256(f.read_bytes()).hexdigest()}")
    return hashlib.sha256("\n".join(lines).encode()).hexdigest(), len(lines)


def symbols_sha():
    return hashlib.sha256(SYMBOLS_FILE.read_bytes()).hexdigest()


def treasury_sha():
    return sha_files(*sorted((ROOT / "data" / "external").glob("treasury_nominal_*.xml")))


def holiday_sha():
    """sha256 of the holiday file's LF-normalised text (CRLF checkouts hash identically)."""
    return hashlib.sha256(HOLIDAY_FILE.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def holidays():
    if holiday_sha() != HOLIDAY_SHA:
        raise ValueError("holiday list digest differs from the pre-registered C5 digest")
    return {pd.Timestamp(x).date() for x in HOLIDAY_FILE.read_text().split()}


def check_series(t, name="series"):
    t = np.asarray(t, np.int64)
    if len(t) > 1 and not (np.diff(t) > 0).all():
        bad = int((np.diff(t) <= 0).sum())
        raise ValueError(f"{name}: {bad} non-increasing or duplicate timestamps")


def candidate_hash(tf, setup, mode, k_atr, exit_label, hold, code_sha):
    return hashlib.sha256(json.dumps([tf, setup, mode, float(k_atr), exit_label, int(hold), code_sha]).encode()).hexdigest()


def validate_seam(a, b, seam_t, hol=None, max_gap_h=3.0, strict=True):
    """C5 splice checks for a seam between source A (before) and B (after). a, b: dicts with numpy arrays t (bar OPEN
    time), c (close), o (open), sp (spread bp); both H1-level (or finer, but then only the gap test is meaningful).
    Window = 4 weeks either side of seam_t. Checks: timestamps strictly increasing inside each source and across the
    spliced series; gaps <= 3 h except weekends <= 72 h and holiday-adjacent <= 96 h; median spread ratio in [0.5, 2];
    source offset on the overlap |median| <= 2 bp and MAD <= 1 bp; seam |log return| < 10 x median |H1 log return|
    (seam excluded). Returns a dict of check -> (passed, value); raises ValueError on any failure when strict."""
    W = 28 * 86400
    hol = holidays() if hol is None else hol
    res = {}
    for nm, s in (("A", a), ("B", b)):
        check_series(s["t"], f"source {nm}")
    ta, tb = np.asarray(a["t"], np.int64), np.asarray(b["t"], np.int64)
    ma = (ta >= seam_t - W) & (ta < seam_t); mb = (tb >= seam_t) & (tb < seam_t + W)
    sp_t = np.r_[ta[ma], tb[mb]]; sp_c = np.r_[np.asarray(a["c"], float)[ma], np.asarray(b["c"], float)[mb]]
    sp_o = np.r_[np.asarray(a["o"], float)[ma], np.asarray(b["o"], float)[mb]]
    res["monotonic_spliced"] = (bool((np.diff(sp_t) > 0).all()) if len(sp_t) > 1 else False, len(sp_t))
    gaps = np.diff(sp_t)
    bad = 0
    for g, t0_, t1_ in zip(gaps, sp_t[:-1], sp_t[1:]):
        if g <= max_gap_h * 3600:
            continue
        d0 = pd.Timestamp(t0_, unit="s"); d1 = pd.Timestamp(t1_, unit="s")
        span_days = pd.date_range(d0.normalize(), d1.normalize(), freq="D")
        weekend = bool((span_days.dayofweek == 5).any())                       # the gap covers a Saturday
        touches_hol = any(d.date() in hol for d in span_days)
        if (weekend and g <= 72 * 3600) or (touches_hol and g <= 96 * 3600):
            continue
        bad += 1
    res["gaps"] = (bad == 0, bad)
    spa = np.asarray(a["sp"], float)[ma]; spb = np.asarray(b["sp"], float)[mb]
    ratio = float(np.nanmedian(spb) / np.nanmedian(spa)) if len(spa) and len(spb) else float("nan")
    res["spread_ratio"] = (bool(0.5 <= ratio <= 2.0), ratio)
    lo = seam_t - W
    oa = (ta >= lo) & (ta < seam_t); ob = (tb >= lo) & (tb < seam_t)
    common, ia, ib = np.intersect1d(ta[oa], tb[ob], return_indices=True)
    if len(common) >= 50:
        ca = np.asarray(a["c"], float)[oa][ia]; cb = np.asarray(b["c"], float)[ob][ib]
        off = (ca - cb) / cb * 1e4
        med = float(np.median(off)); mad = float(np.median(np.abs(off - np.median(off))))
        res["offset_bp"] = (bool(abs(med) <= 2.0 and mad <= 1.0), (med, mad, len(common)))
    else:
        res["offset_bp"] = (False, ("NO_OVERLAP", len(common)))
    lr = np.abs(np.diff(np.log(sp_c)))
    i_seam = int(np.searchsorted(sp_t, seam_t, side="left"))
    seam_ret = abs(np.log(sp_o[i_seam] / sp_c[i_seam - 1])) if 0 < i_seam < len(sp_t) else float("nan")
    base = np.delete(lr, max(i_seam - 1, 0)) if 0 < i_seam <= len(lr) else lr
    thr = 10 * float(np.median(base)) if len(base) else float("nan")
    res["seam_return"] = (bool(seam_ret < thr), (float(seam_ret), thr))
    if strict and not all(v[0] for v in res.values()):
        raise ValueError(f"splice validation failed: { {k: v for k, v in res.items() if not v[0]} }")
    return res
