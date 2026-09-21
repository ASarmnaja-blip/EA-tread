"""
Candle anatomy — body, wicks, gaps, and each bar against its neighbours.

measure.py describes the chart at the level of ranges and percentiles. That is
too coarse to answer where a move was rejected, which side did the rejecting,
or whether a bar was large for the market or merely large for itself. This
module adds the anatomy and then MEASURES which parts of it carry information,
rather than adding features because they are traditional.

Every directional feature here is SIGNED. The previous round found an
information coefficient of +0.033 for directional efficiency, which is an
UNSIGNED quantity measured against a SIGNED return - so it described a
conditional drift, not a tradable direction. That mistake is not repeated:
where a feature has a side, the side is kept, and where it does not, it is
tested against the ABSOLUTE forward move instead.

Multiplicity is stated with the results. Roughly forty features by two
horizons is eighty tests, so the family-wise bar sits near |t| = 3.4, and a
feature at |t| = 2 is noise wearing a decimal point.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import core
import data as D

HORIZONS = (12, 36)          # [DEF] 1h and 3h on M5
NEIGH = (12, 72)             # [DEF] windows a bar is compared against
SPLIT = 0.70                 # [DEF] time-ordered, fit half is never reported
STOP_ATR = 1.5               # [DEF] the R unit


def anatomy(b: D.Bars) -> pd.DataFrame:
    o, h, l, c, v = b.o, b.h, b.l, b.c, np.asarray(b.v, float)
    rng = h - l
    atr = core.atr(b, 14)
    safe_r = np.where(rng > 0, rng, np.nan)
    safe_a = np.where(atr > 0, atr, np.nan)

    body = c - o                                   # signed
    upper = h - np.maximum(o, c)
    lower = np.minimum(o, c) - l
    prev_c = np.concatenate(([c[0]], c[:-1]))
    prev_o = np.concatenate(([o[0]], o[:-1]))
    prev_h = np.concatenate(([h[0]], h[:-1]))
    prev_l = np.concatenate(([l[0]], l[:-1]))
    prev_body = np.concatenate(([0.0], body[:-1]))

    f = {}
    # --- size, absolute and relative
    f["range_atr"] = rng / safe_a
    f["body_atr"] = body / safe_a                       # signed
    f["absbody_atr"] = np.abs(body) / safe_a
    f["body_frac"] = np.abs(body) / safe_r              # body share of the bar
    f["upper_frac"] = upper / safe_r
    f["lower_frac"] = lower / safe_r
    # positive = long lower wick = the low was rejected = bullish shape
    f["wick_imbalance"] = (lower - upper) / safe_r
    f["close_pos"] = (c - l) / safe_r

    # --- the bar against its neighbours
    for k in NEIGH:
        mr = pd.Series(rng).shift(1).rolling(k).mean().to_numpy()
        f[f"range_rel_{k}"] = rng / np.where(mr > 0, mr, np.nan)
        mv = pd.Series(v).shift(1).rolling(k).mean().to_numpy()
        f[f"vol_rel_{k}"] = v / np.where(mv > 0, mv, np.nan)

    # --- gap and overlap with the bar before
    f["gap_atr"] = (o - prev_c) / safe_a                 # signed
    ov_hi = np.minimum(h, prev_h)
    ov_lo = np.maximum(l, prev_l)
    f["overlap_frac"] = np.maximum(ov_hi - ov_lo, 0.0) / safe_r

    # --- two-bar shapes
    f["inside_bar"] = ((h <= prev_h) & (l >= prev_l)).astype(float)
    f["outside_bar"] = ((h > prev_h) & (l < prev_l)).astype(float)
    engulf = (np.abs(body) > np.abs(prev_body)) & (np.sign(body) != np.sign(prev_body))
    f["engulf_signed"] = np.where(engulf, np.sign(body), 0.0)   # signed
    f["body_flip"] = (np.sign(body) != np.sign(prev_body)).astype(float)

    # --- runs of same-direction bodies, signed
    s = np.sign(body)
    run = np.zeros(len(s))
    for i in range(1, len(s)):
        run[i] = run[i - 1] + s[i] if s[i] == s[i - 1] and s[i] != 0 else s[i]
    f["body_run"] = run

    # --- move per unit of activity: how far price travelled for the volume it
    # took. A large move on little volume is a different animal from the same
    # move on heavy volume, and neither ATR nor range distinguishes them.
    for k in NEIGH:
        mv = pd.Series(v).shift(1).rolling(k).mean().to_numpy()
        vr = v / np.where(mv > 0, mv, np.nan)
        f[f"impact_{k}"] = (np.abs(body) / safe_a) / np.where(vr > 0, vr, np.nan)

    # --- wick rejection at an extreme: a long wick only means something where
    # it happened, so the raw wick and the wick-at-an-extreme are separated
    hh = core.rolling_max(h, 48)
    ll = core.rolling_min(l, 48)
    f["upper_wick_at_high"] = np.where(np.isfinite(hh) & (h > hh),
                                       upper / safe_r, 0.0)
    f["lower_wick_at_low"] = np.where(np.isfinite(ll) & (l < ll),
                                      lower / safe_r, 0.0)
    return pd.DataFrame(f)


def forward(b: D.Bars, k: int) -> np.ndarray:
    """Forward move in R units, R = STOP_ATR x ATR at the signal bar."""
    atr = core.atr(b, 14)
    risk = STOP_ATR * atr
    fwd = pd.Series(b.c).shift(-k).to_numpy() - b.c
    with np.errstate(divide="ignore", invalid="ignore"):
        return fwd / np.where(risk > 0, risk, np.nan)


SIGNED = {"body_atr", "wick_imbalance", "gap_atr", "engulf_signed", "body_run",
          "close_pos"}


def main() -> int:
    b = D.load_csv("data/XAUUSD_M5.csv")
    A = anatomy(b)
    n = len(A)
    cut = int(n * SPLIT)
    test = np.arange(cut, n)
    print("=" * 94)
    print("CANDLE ANATOMY - which parts of a bar carry information")
    print("=" * 94)
    print(f"bars {n:,} | features {A.shape[1]} | horizons {HORIZONS}")
    print(f"held-out half: bars {cut:,}..{n:,}")
    ntests = A.shape[1] * len(HORIZONS)
    zbar = core.bonferroni_z(ntests)
    print(f"tests {ntests} -> family-wise bar |t| = {zbar:.2f}\n")

    rows = []
    for k in HORIZONS:
        y = forward(b, k)
        ay = np.abs(y)
        for col in A.columns:
            x = A[col].to_numpy()
            signed = col in SIGNED
            target = y if signed else ay
            m = np.isfinite(x) & np.isfinite(target)
            m[:cut] = False
            if m.sum() < 5000:
                continue
            ic = float(np.corrcoef(x[m], target[m])[0, 1])
            se = 1.0 / np.sqrt(m.sum())
            rows.append(dict(feature=col, h=k, kind="signed" if signed else "|move|",
                             ic=ic, t=ic / se, n=int(m.sum())))
    r = pd.DataFrame(rows)

    print("--- SIGNED features vs the SIGNED forward move (a direction claim) ---")
    s = r[r.kind == "signed"].reindex(r[r.kind == "signed"].t.abs()
                                      .sort_values(ascending=False).index)
    print(s.to_string(index=False, float_format=lambda v: f"{v:9.4f}"))

    print("\n--- UNSIGNED features vs the ABSOLUTE forward move (a size claim) ---")
    u = r[r.kind == "|move|"].reindex(r[r.kind == "|move|"].t.abs()
                                      .sort_values(ascending=False).index)
    print(u.head(14).to_string(index=False, float_format=lambda v: f"{v:9.4f}"))

    print(f"\nclearing the family-wise bar |t| >= {zbar:.2f}:")
    keep = r[r.t.abs() >= zbar]
    if len(keep) == 0:
        print("  none")
    else:
        for _, q in keep.sort_values("t", key=abs, ascending=False).iterrows():
            print(f"  {q.feature:22s} h={q.h:3d} {q.kind:8s} "
                  f"IC {q.ic:+.4f}  t {q.t:+7.2f}")

    # what a direction claim is worth once cost is paid
    y12 = forward(b, 12)
    sd = float(pd.Series(y12[test]).std())
    atr = core.atr(b, 14)
    cost = (0.260 + 2 * 0.10) / float(np.nanmedian(STOP_ATR * atr))
    print(f"\nsd of the 1h move {sd:.3f} R | round turn {cost:.4f} R")
    print(f"{'feature':22s}{'IC':>9s}{'edge@1sd':>10s}{'net@1sd':>9s}{'sd to break even':>18s}")
    for _, q in s.head(6).iterrows():
        if q.h != 12:
            continue
        edge = abs(q.ic) * sd
        print(f"{q.feature:22s}{q.ic:9.4f}{edge:10.4f}{edge - cost:+9.4f}"
              f"{cost / edge if edge > 0 else np.inf:18.2f}")

    print("\nAn IC is a correlation. The columns above convert it into the only")
    print("units that decide anything: R earned against R paid.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
