"""Regime Stability Score v1 - CLAUDE.md gap #2 (see appendix + LOGIC_LEDGER
Part 22's next-step recommendation).

Ports Regime.mqh's Classify() logic to Python exactly (same constants as
MQL5/Include/XAUM15/Config.mqh) and adds the efficiency-ratio diagnostic
validated tonight (Part 20-22) as a second, orthogonal signal: atrPercentile
+ the EMA-slope/compression rule tell you WHICH discrete regime label
(TREND_UP/DOWN, RANGE, HIGH/LOW/EXTREME_VOL) the market is in; efficiency
ratio tells you HOW cleanly directional price has been, which the discrete
label alone does not capture (a market can carry HIGH_VOL and still be pure
chop, or LOW_VOL and still be one-directional).

Regime Stability Score = % of the last InpAtrRegimeLookback-equivalent
window (mapped to calendar days) where the bar-by-bar classified regime
label equals the CURRENT bar's label. High = the current label has held
for most of the recent window (adjust slowly, per CLAUDE.md section 4).
Low = the label has been flipping (adjust fast).

Pulls FRESH M15 data directly from the live MT5 terminal (not the frozen
canonical_XAUUSD_M5.npz research snapshot, which is deliberately immutable
for backtest reproducibility - see historical_regime_walkforward.py). This
script is meant to answer "what is the regime RIGHT NOW", so it needs
current data, not the frozen snapshot.

STILL MISSING from this v1 (stated plainly, per CLAUDE.md item 2): DXY/
yield correlation, liquidity proxies, narrative/positioning, recent
setup performance. This is price-structure + volatility only.
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import core as C5
import data as D

SYMBOL = "XAUUSD"

# --- ported 1:1 from MQL5/Include/XAUM15/Config.mqh ---
EMA_FAST, EMA_SLOW, SMA_TREND = 50, 200, 200
EMA_SLOPE_BARS = 5
EMA_SLOPE_MIN_ATR = 0.05
ATR_PERIOD = 14
ATR_REGIME_LOOKBACK = 100     # bars, on the EA's own timeframe (M15)
LOW_VOL_PCTL, HIGH_VOL_PCTL, EXTREME_VOL_PCT = 25.0, 75.0, 95.0
RANGE_COMPRESS_ATR = 0.6

STABILITY_WINDOW_BARS = ATR_REGIME_LOOKBACK  # same lookback, same timeframe


def ema(x: np.ndarray, span: int) -> np.ndarray:
    a = 2.0 / (span + 1.0)
    out = np.empty_like(x)
    out[0] = x[0]
    for i in range(1, len(x)):
        out[i] = a * x[i] + (1 - a) * out[i - 1]
    return out


def sma(x: np.ndarray, n: int) -> np.ndarray:
    out = np.full_like(x, np.nan)
    c = np.cumsum(x)
    out[n - 1:] = (c[n - 1:] - np.r_[0.0, c[:-n]]) / n
    return out


def fetch_fresh_m15(days: int = 200) -> D.Bars:
    import MetaTrader5 as mt5
    if not mt5.initialize():
        raise RuntimeError(f"MT5 initialize failed: {mt5.last_error()}")
    try:
        info = mt5.symbol_info(SYMBOL)
        if info is None or not mt5.symbol_select(SYMBOL, True):
            raise RuntimeError(f"MT5 symbol unavailable: {SYMBOL}")
        end = datetime.now(timezone.utc)
        start = end.replace(hour=0, minute=0, second=0, microsecond=0)
        from datetime import timedelta
        start -= timedelta(days=days)
        rates = mt5.copy_rates_range(SYMBOL, mt5.TIMEFRAME_M15, start, end)
        if rates is None or len(rates) == 0:
            raise RuntimeError(f"no M15 bars returned: {mt5.last_error()}")
        return D.Bars(rates["time"], rates["open"], rates["high"], rates["low"],
                      rates["close"], rates["tick_volume"], 900, SYMBOL,
                      rates["spread"] * info.point)
    finally:
        mt5.shutdown()


def classify_series(b15: D.Bars):
    """Bar-by-bar regime label, vectorised version of Regime.mqh Classify()."""
    n = len(b15)
    atr = C5.atr(b15, ATR_PERIOD)
    ema_f = ema(b15.c, EMA_FAST)
    ema_s = ema(b15.c, EMA_SLOW)
    sma_t = sma(b15.c, SMA_TREND)

    regime = np.full(n, "NONE", dtype=object)
    atr_pctl = np.full(n, 50.0)

    for i in range(ATR_REGIME_LOOKBACK, n):
        window = atr[max(0, i - ATR_REGIME_LOOKBACK):i]
        cur_atr = atr[i]
        pctl = 100.0 * np.sum(window < cur_atr) / len(window) if cur_atr > 0 else 50.0
        atr_pctl[i] = pctl

        if pctl >= EXTREME_VOL_PCT:
            regime[i] = "EXTREME_VOL"
            continue

        a = atr[i]
        sep = abs(ema_f[i] - ema_s[i]) / a if a > 0 else 0.0
        if i > EMA_SLOPE_BARS:
            slope = (ema_f[i] - ema_f[i - EMA_SLOPE_BARS]) / (EMA_SLOPE_BARS * a) if a > 0 else 0.0
        else:
            slope = 0.0
        compressed = sep < RANGE_COMPRESS_ATR
        low_vol = pctl <= LOW_VOL_PCTL

        if compressed or (low_vol and abs(slope) < EMA_SLOPE_MIN_ATR):
            regime[i] = "LOW_VOL" if low_vol else "RANGE"
            continue
        if b15.c[i] > ema_s[i] and ema_f[i] > ema_s[i] and slope >= EMA_SLOPE_MIN_ATR:
            regime[i] = "TREND_UP"
            continue
        if b15.c[i] < ema_s[i] and ema_f[i] < ema_s[i] and slope <= -EMA_SLOPE_MIN_ATR:
            regime[i] = "TREND_DOWN"
            continue
        regime[i] = "HIGH_VOL" if pctl >= HIGH_VOL_PCTL else "RANGE"

    return regime, atr_pctl, atr


def efficiency_ratio(c: np.ndarray) -> float:
    net = abs(c[-1] - c[0])
    path = np.abs(np.diff(c)).sum()
    return net / path if path > 0 else np.nan


def main() -> int:
    b15 = fetch_fresh_m15(days=200)
    now_t = datetime.fromtimestamp(int(b15.t[-1]), timezone.utc)
    print(f"fresh MT5 pull, {SYMBOL} M15, {len(b15):,} bars, "
          f"{datetime.fromtimestamp(int(b15.t[0]), timezone.utc):%Y-%m-%d} .. {now_t:%Y-%m-%d %H:%M} UTC\n")

    regime, atr_pctl, atr = classify_series(b15)
    valid = regime != "NONE"
    cur_regime = regime[-1]
    cur_pctl = atr_pctl[-1]

    win = regime[valid][-STABILITY_WINDOW_BARS:]
    stability = 100.0 * np.mean(win == cur_regime)

    print(f"CURRENT REGIME: {cur_regime}   ATR percentile: {cur_pctl:.1f}")
    print(f"REGIME STABILITY SCORE: {stability:.1f}%  "
          f"(share of last {len(win)} M15 bars classified the same as now)")
    print("  interpretation: high = regime has held, adjust slowly.")
    print("                  low  = regime flipping, adjust fast.\n")

    label_changes = np.sum(win[1:] != win[:-1])
    print(f"label changes within that window: {label_changes} "
          f"(more changes = less stable even at the same %-match level)\n")

    print("efficiency ratio, trailing windows (secondary diagnostic, chop vs trend "
          "character - a dimension atrPercentile/regime label does not capture):")
    t_arr = b15.t.astype(np.int64)
    for days in (14, 30, 60, 90, 180):
        cutoff = int(b15.t[-1]) - days * 86400
        i0 = int(np.searchsorted(t_arr, cutoff))
        if i0 <= 0:
            print(f"  last {days:>3d}d: not enough fetched history "
                  f"(have {(int(b15.t[-1]) - int(b15.t[0])) / 86400:.0f}d) - skipped")
            continue
        eff = efficiency_ratio(b15.c[i0:])
        net = b15.c[-1] - b15.c[i0]
        print(f"  last {days:>3d}d: net {net:+8.2f}  efficiency={eff:.3f}  n={len(b15)-i0:,}")

    print(f"\nNOT included in this v1 (CLAUDE.md item 2 still open): DXY/yield "
          f"correlation, liquidity proxies, narrative/positioning, recent setup "
          f"performance. This is price-structure + volatility only.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
