"""Predeclared intraday impulse-pullback candidate for the current market.

This file tests one mechanism observed before results were inspected:

* XAUUSD has moved at least 2 ATR over the prior hour;
* DXY confirms in the opposite direction and XAGUSD confirms in the same;
* the current M5 candle pulls back against the impulse without crossing EMA20;
* entries are limited to London and the London/New York overlap (07:00-16:59 UTC).

Entry is the next M5 open. Stop is 1 ATR, target is 1.5R, and the time stop is
12 bars. Costs are $0.09 spread plus $0.10 slippage per side. No parameter is
selected from the reported results. The final 10 calendar days are a locked
holdout and are never used to select or alter the candidate.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
IMPULSE_BARS = 12
IMPULSE_ATR = 2.0
STOP_ATR = 1.0
TARGET_R = 1.5
MAX_BARS = 12
SPREAD = 0.09
SLIP_SIDE = 0.10
HOLDOUT_DAYS = 10


@dataclass
class Trade:
    time: pd.Timestamp
    direction: int
    net_r: float
    exit_reason: str


def load(symbol: str) -> pd.DataFrame:
    d = pd.read_csv(DATA / f"{symbol}_M5.csv", parse_dates=["time"])
    d["time"] = pd.to_datetime(d["time"], utc=True)
    return d.set_index("time").sort_index()


def features() -> pd.DataFrame:
    x = load("XAUUSD")
    d = load("DXY")[['close']].rename(columns={'close': 'dxy_close'})
    s = load("XAGUSD")[['close']].rename(columns={'close': 'xag_close'})
    z = x.join(d, how="inner").join(s, how="inner")
    prev = z.close.shift(1)
    tr = pd.concat([(z.high-z.low), (z.high-prev).abs(), (z.low-prev).abs()], axis=1).max(axis=1)
    z["atr"] = tr.rolling(14).mean()
    z["ema20"] = z.close.ewm(span=20, adjust=False).mean()
    z["x_imp"] = z.close - z.close.shift(IMPULSE_BARS)
    z["d_imp"] = z.dxy_close - z.dxy_close.shift(IMPULSE_BARS)
    z["s_imp"] = z.xag_close - z.xag_close.shift(IMPULSE_BARS)
    z["bar"] = z.close - z.close.shift(1)
    direction = np.sign(z.x_imp)
    hours = z.index.hour
    z["direction"] = direction
    z["signal"] = (
        (hours >= 7) & (hours < 17)
        & (z.x_imp.abs() >= IMPULSE_ATR * z.atr)
        & (np.sign(z.d_imp) == -direction)
        & (np.sign(z.s_imp) == direction)
        & (np.sign(z.bar) == -direction)
        & (z.bar.abs() <= 0.75 * z.atr)
        & (((direction > 0) & (z.close > z.ema20))
           | ((direction < 0) & (z.close < z.ema20)))
    )
    return z


def simulate(z: pd.DataFrame) -> list[Trade]:
    out: list[Trade] = []
    last_exit = -1
    sig = np.flatnonzero(z.signal.to_numpy())
    for i in sig:
        if i + 1 >= len(z) or i < last_exit:
            continue
        d = int(z.direction.iloc[i])
        atr = float(z.atr.iloc[i])
        entry = float(z.open.iloc[i+1])
        risk = STOP_ATR * atr
        stop = entry - d * risk
        target = entry + d * TARGET_R * risk
        end = min(i + 1 + MAX_BARS, len(z) - 1)
        px = float(z.close.iloc[end]); why = "TIME"; exit_i = end
        for k in range(i+1, end+1):
            hit_stop = z.low.iloc[k] <= stop if d > 0 else z.high.iloc[k] >= stop
            hit_target = z.high.iloc[k] >= target if d > 0 else z.low.iloc[k] <= target
            if hit_stop and hit_target:
                px, why, exit_i = stop, "BOTH_STOP_FIRST", k
                break
            if hit_stop:
                px, why, exit_i = stop, "STOP", k
                break
            if hit_target:
                px, why, exit_i = target, "TARGET", k
                break
        gross = d * (px-entry) / risk
        net = gross - (SPREAD + 2*SLIP_SIDE) / risk
        out.append(Trade(z.index[i+1], d, float(net), why))
        last_exit = exit_i
    return out


def stats(trades: list[Trade]) -> dict:
    if not trades:
        return dict(n=0, mean=np.nan, win=np.nan, lo=np.nan, hi=np.nan)
    x = np.array([t.net_r for t in trades])
    days = pd.Series(x, index=[t.time.floor('D') for t in trades]).groupby(level=0).mean().to_numpy()
    rng = np.random.default_rng(20260921)
    boot = np.array([rng.choice(days, len(days), replace=True).mean() for _ in range(2000)])
    return dict(n=len(x), mean=float(x.mean()), win=float((x>0).mean()),
                lo=float(np.quantile(boot, .025)), hi=float(np.quantile(boot, .975)))


def show(name: str, trades: list[Trade]) -> dict:
    s = stats(trades)
    print(f"{name:20s} n={s['n']:4d} mean={s['mean']:+.4f}R "
          f"win={100*s['win']:.1f}% day-bootstrap=[{s['lo']:+.4f},{s['hi']:+.4f}]")
    return s


def main() -> int:
    z = features()
    trades = simulate(z)
    end = z.index[-1]
    holdout_cut = end - pd.Timedelta(days=HOLDOUT_DAYS)
    recent_cut = end - pd.Timedelta(days=60)
    old = [t for t in trades if t.time < recent_cut]
    recent_dev = [t for t in trades if recent_cut <= t.time < holdout_cut]
    holdout = [t for t in trades if t.time >= holdout_cut]
    print("PREDECLARED INTRADAY IMPULSE-PULLBACK")
    print(f"data {z.index[0]} -> {end}; holdout begins {holdout_cut}")
    show("older sanity", old)
    sd = show("recent 50d dev", recent_dev)
    sh = show("locked 10d holdout", holdout)
    passed = (sd['n'] >= 30 and sd['mean'] > 0 and sd['lo'] > 0
              and sh['n'] >= 8 and sh['mean'] > 0)
    print("DECISION", "PASS" if passed else "FAIL")
    print("No order function exists in this file.")
    return 0 if passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
