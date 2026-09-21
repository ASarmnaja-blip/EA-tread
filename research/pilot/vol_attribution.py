"""
Where does XAUUSD's volatility come from, and what is left after it?

Every R in this project is defined as 1.5 x ATR, so every result is quoted in
a unit whose size we had not explained. If volatility is mostly a clock -
London opens, a release lands - then a "big move" is not information, it is a
schedule, and a setup that fires on big moves is trading the calendar.

Part 1 attributes volatility to blocks of drivers and reports how much each
block adds, in and out of sample:

    time        hour of day, day of week      - a clock, knowable forever ahead
    persistence its own recent level          - internal, knowable now
    news        minutes to the next release   - knowable ahead
                surprise size of the last one - knowable only after
    cross       DXY and silver volatility     - external, contemporaneous
    positioning CFTC crowding percentile      - external, weekly, lagged

Part 2 divides the forward move by the volatility the model EXPECTED rather
than by the volatility that happened, and asks whether any directional
information survives. Dividing by realised ATR hides a predictable quantity in
the denominator; dividing by expected volatility does not.

Nothing here reads a setup's result. The dependent variables are the market's
own volatility and its own forward return.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import core
import data as D
import measure

HORIZON = 12                 # [DEF] one hour on M5 - the volatility horizon
MIN_OBS = 5000               # [CAL] refuse to report a block below this
SPLIT = 0.70                 # [DEF] in-sample fraction, time-ordered


# ------------------------------------------------------------------ fitting
def ols_r2(X: np.ndarray, y: np.ndarray, idx_fit: np.ndarray,
           idx_test: np.ndarray) -> tuple[float, float]:
    """R2 in and out of sample for a design already containing its intercept.

    Out-of-sample R2 is computed against the IN-SAMPLE mean, not the test
    mean. Using the test mean would hand the model knowledge of the test
    period's average, which is the quantity most likely to have drifted.
    """
    Xf, yf = X[idx_fit], y[idx_fit]
    beta, *_ = np.linalg.lstsq(Xf, yf, rcond=None)
    yhat_f = Xf @ beta
    ss_f = ((yf - yf.mean()) ** 2).sum()
    r2_in = 1.0 - ((yf - yhat_f) ** 2).sum() / ss_f if ss_f > 0 else np.nan

    Xt, yt = X[idx_test], y[idx_test]
    yhat_t = Xt @ beta
    ss_t = ((yt - yf.mean()) ** 2).sum()
    r2_out = 1.0 - ((yt - yhat_t) ** 2).sum() / ss_t if ss_t > 0 else np.nan
    return float(r2_in), float(r2_out)


def dummies(v: np.ndarray, values) -> np.ndarray:
    return np.column_stack([(v == k).astype(float) for k in values])


def build_blocks(df: pd.DataFrame, cal_ev: pd.DataFrame | None,
                 xag: D.Bars | None, dxy: D.Bars | None,
                 pos: pd.DataFrame | None) -> dict[str, np.ndarray]:
    n = len(df)
    t = df["t"]
    hour = t.dt.hour.to_numpy()
    dow = t.dt.dayofweek.to_numpy()

    blocks: dict[str, np.ndarray] = {}
    blocks["time"] = np.column_stack([
        dummies(hour, range(1, 24)),          # hour 0 is the reference
        dummies(dow, range(1, 5)),
    ])

    lrv12 = np.log(np.maximum(df["rv_12"].to_numpy(), 1e-12))
    lrv72 = np.log(np.maximum(df["rv_72"].to_numpy(), 1e-12))
    latr = np.log(np.maximum(df["atr"].to_numpy(), 1e-12))
    blocks["persistence"] = np.column_stack([lrv12, lrv72, latr,
                                             df["vol_of_vol"].fillna(0).to_numpy()])

    # news: what is knowable BEFORE the release is the schedule; the surprise
    # is knowable only after, so the two enter as separate columns and the
    # pre-release one is the only honest predictor of what is about to happen.
    mtn = np.clip(df["min_to_next_news"].to_numpy(), 0, 24 * 60)
    msn = np.clip(df["min_since_news"].to_numpy(), 0, 24 * 60)
    blocks["news"] = np.column_stack([
        np.exp(-mtn / 30.0),                  # rises as a release approaches
        np.exp(-msn / 30.0),                  # decays after one
        (mtn <= 15).astype(float),
        (msn <= 15).astype(float),
    ])

    cross = []
    for b, name in ((dxy, "dxy"), (xag, "xag")):
        if b is None:
            continue
        s = pd.Series(np.log(np.maximum(b.c, 1e-9)),
                      index=pd.to_datetime(b.t, unit="s", utc=True))
        s = s[~s.index.duplicated()].reindex(t, method="ffill")
        r = s.diff().fillna(0.0)
        cross.append(np.log(np.maximum(
            r.rolling(HORIZON).std().ffill().fillna(0.0).to_numpy(),
            1e-12)))
    if cross:
        blocks["cross"] = np.column_stack(cross)

    if pos is not None and len(pos):
        p = pos.dropna(subset=["pct_rank"]).copy()
        ps = pd.Series(p["pct_rank"].to_numpy(),
                       index=pd.to_datetime(p["epoch"], unit="s", utc=True))
        ps = ps[~ps.index.duplicated()].reindex(t, method="ffill")
        blocks["positioning"] = np.column_stack([
            ps.fillna(50.0).to_numpy() / 100.0,
            (ps.fillna(50.0).to_numpy() > 80).astype(float),
        ])
    return blocks


def main() -> int:
    b5 = D.load_csv("data/XAUUSD_M5.csv")
    dxy = xag = None
    for p, nm in (("data/DXY_M5.csv", "dxy"), ("data/XAGUSD_M5.csv", "xag")):
        try:
            b = D.load_csv(p)
            if nm == "dxy":
                dxy = b
            else:
                xag = b
        except Exception as e:
            print(f"  {nm} unavailable: {e}")

    cal = pos = None
    try:
        import calendar_feed
        c = calendar_feed.load_calendar("data/calendar.csv")
        pos = calendar_feed.positioning_series(c)
        cal = c[(c.currency == "USD") & (c.importance == "HIGH")]
    except Exception as e:
        print("  calendar unavailable:", e)

    print("=" * 92)
    print("VOLATILITY ATTRIBUTION - what makes XAUUSD move as much as it does")
    print("=" * 92)

    df = measure.build_states(b5, cal, dxy)

    # dependent variable: realised volatility over the NEXT hour
    logc = np.log(np.maximum(b5.c, 1e-9))
    r1 = np.concatenate(([0.0], np.diff(logc)))
    fwd_rv = (pd.Series(r1).shift(-1).rolling(HORIZON).std()
              .shift(-(HORIZON - 1)).to_numpy())
    y = np.log(np.maximum(fwd_rv, 1e-12))

    blocks = build_blocks(df, cal, xag, dxy, pos)
    ok = np.isfinite(y)
    for B in blocks.values():
        ok &= np.isfinite(B).all(axis=1)
    idx = np.flatnonzero(ok)
    cut = idx[int(len(idx) * SPLIT)]
    fit = idx[idx <= cut]
    test = idx[idx > cut]
    print(f"usable bars {len(idx):,}  | fit {len(fit):,} "
          f"({df['t'].iloc[fit[0]]:%Y-%m-%d} .. {df['t'].iloc[fit[-1]]:%Y-%m-%d})"
          f"  | test {len(test):,} "
          f"({df['t'].iloc[test[0]]:%Y-%m-%d} .. {df['t'].iloc[test[-1]]:%Y-%m-%d})")

    order = [k for k in ("time", "persistence", "news", "cross", "positioning")
             if k in blocks]
    print(f"\n{'block added':14s}{'R2 in':>9s}{'R2 out':>9s}"
          f"{'dR2 in':>9s}{'dR2 out':>9s}   interpretation")
    print("-" * 92)
    X = np.ones((len(df), 1))
    prev_in = prev_out = 0.0
    for k in order:
        X = np.column_stack([X, blocks[k]])
        r_in, r_out = ols_r2(X, y, fit, test)
        note = {
            "time": "a clock - knowable for ever, carries no information",
            "persistence": "internal memory - volatility clusters",
            "news": "the schedule, not the surprise",
            "cross": "external: DXY and silver volatility",
            "positioning": "external: CFTC crowding, weekly and lagged",
        }[k]
        print(f"{k:14s}{r_in:9.4f}{r_out:9.4f}{r_in - prev_in:9.4f}"
              f"{r_out - prev_out:9.4f}   {note}")
        prev_in, prev_out = r_in, r_out

    # each block alone, so a block that only looks weak because an earlier one
    # already carried its information is visible as such
    print(f"\n{'block alone':14s}{'R2 in':>9s}{'R2 out':>9s}")
    print("-" * 34)
    for k in order:
        Xk = np.column_stack([np.ones(len(df)), blocks[k]])
        a, b = ols_r2(Xk, y, fit, test)
        print(f"{k:14s}{a:9.4f}{b:9.4f}")

    # ---------------------------------------------------------------- part 2
    print("\n" + "=" * 92)
    print("WHAT SURVIVES THE VOLATILITY - direction, standardised by EXPECTED vol")
    print("=" * 92)
    Xfull = np.column_stack([np.ones(len(df))] + [blocks[k] for k in order])
    beta, *_ = np.linalg.lstsq(Xfull[fit], y[fit], rcond=None)
    vol_hat = np.exp(Xfull @ beta)                 # expected sd of log return
    fwd_ret = pd.Series(logc).shift(-HORIZON).to_numpy() - logc
    with np.errstate(divide="ignore", invalid="ignore"):
        z_exp = fwd_ret / (vol_hat * np.sqrt(HORIZON))
        z_real = fwd_ret / (np.log1p(df["atr"].to_numpy() / np.maximum(b5.c, 1e-9))
                            * np.sqrt(HORIZON))

    def report(name, z, sel):
        s = z[sel]
        s = s[np.isfinite(s)]
        if len(s) < MIN_OBS:
            print(f"  {name:34s} n={len(s):7,d}  too few")
            return
        se = s.std(ddof=1) / np.sqrt(len(s))
        print(f"  {name:34s} n={len(s):7,d}  mean {s.mean():+.4f}"
              f"  se {se:.4f}  t {s.mean()/se:+6.2f}"
              f"  P(up) {100*(s > 0).mean():5.1f}%")

    print("\ndrift, in units of the volatility the model expected:")
    report("all bars (expected-vol units)", z_exp, test)
    report("all bars (realised-ATR units)", z_real, test)

    print("\nby state, expected-vol units, TEST half only:")
    for col, vals in (("session", ["ASIA", "LONDON", "OVERLAP", "NY"]),
                      ("regime", ["TREND", "QUIET_RANGE", "MIXED", "EXTREME_VOL"])):
        for v in vals:
            sel = np.zeros(len(df), bool)
            sel[test] = (df[col].to_numpy()[test] == v)
            report(f"{col}={v}", z_exp, sel)

    print("\ninformation coefficient of each state feature vs the next hour,")
    print("after standardising by expected volatility (TEST half):")
    feats = ["dir_eff_36", "vr_12", "close_pos", "atr_pct", "mrs",
             "corr_dxy_288", "min_since_news"]
    zz = pd.Series(z_exp)
    for f in feats:
        if f not in df:
            continue
        a = df[f].to_numpy()[test]
        b = zz.to_numpy()[test]
        m = np.isfinite(a) & np.isfinite(b)
        if m.sum() < MIN_OBS:
            continue
        ic = float(np.corrcoef(a[m], b[m])[0, 1])
        se = 1.0 / np.sqrt(m.sum())
        print(f"  {f:18s} IC {ic:+.4f}  se {se:.4f}  t {ic/se:+6.2f}  n {m.sum():,}")

    print("\nIC is a correlation, not a return. An IC of 0.02 with 30,000 bars")
    print("is statistically real and economically invisible once cost is paid.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
