#!/usr/bin/env python3
"""P01's actual trades, in money - not R multiples, not t-statistics.

WHY THIS FILE EXISTS

  Every result so far reports E(R), skill, and t. Those are the right
  numbers for deciding whether an effect is real, and they are also easy to
  lose a account behind: R is a ratio, and a ratio does not show what a
  losing streak looks like in cash, what the worst week cost, or whether the
  win rate a trader would actually feel matches the one printed in a table.

  This dumps the FIXED P01 engine's real trades - real entry/exit price,
  real timestamp, real exit reason, real dollar P&L on the Exness cent
  account this project has used throughout - so the result can be read as
  a trading log rather than a statistic.

  This is the corrected engine (see test_spec_engine_calibration.py and the
  retraction in change_ledger.json under xauusd1000_p01_realfill_crossmarket).
  The pre-fix version of this same rule would have shown a different, better,
  and wrong log.
"""
import argparse, pathlib, sys
import numpy as np, pandas as pd

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import xauusd_1000_setups as X
from exness_cent import ExnessCent

ACC = ExnessCent()


def trade_log(P, dvec, Ivec, lo, hi, tick, risk_frac):
    """Every trade P01 actually takes, with real prices and real money.

    This mirrors run_e01's mechanics exactly (same gate, same fill, same
    exit scan) but keeps the full record instead of collapsing it to R."""
    o, h, l, c, N = P["o"], P["h"], P["l"], P["c"], P["N"]
    idx, bid, ask, A, spread = P["idx"], P["bid"], P["ask"], P["A"], P["spread"]
    rows = []
    busy = -1
    equity = 500.0          # USC, matching this project's standard start
    peak = equity
    for t in range(max(lo, 300), min(hi, N - 1)):
        d = dvec[t]
        if d == 0 or t <= busy:
            continue
        a = A[t]
        if not np.isfinite(a) or a <= 0:
            continue
        e = t + 1
        entry = P["ask_o"][e] if d > 0 else P["bid_o"][e]
        if not np.isfinite(entry):
            continue
        b = max(0.10 * a, spread[t] if np.isfinite(spread[t]) else 0, 2 * tick)
        inval = Ivec[t]
        if not np.isfinite(inval):
            continue
        stop = (X.tick_round(inval - b, False, tick) if d > 0
                else X.tick_round(inval + b, True, tick))
        dist = abs(entry - stop)
        sp = spread[e] if np.isfinite(spread[e]) else spread[t]
        if not np.isfinite(sp) or sp > 0.10 * a:
            continue
        if not (max(0.30 * a, 5 * sp) <= dist <= 3 * a):
            continue
        if (entry <= stop) if d > 0 else (entry >= stop):
            continue
        target = entry + dist if d > 0 else entry - dist
        ex_lo = P["bid_l"] if d > 0 else P["ask_l"]
        ex_hi = P["bid_h"] if d > 0 else P["ask_h"]
        exit_px, exit_bar, reason = None, None, None
        for k in range(e, min(e + X.HOLD_BARS, N)):
            hit_stop = (ex_lo[k] <= stop) if d > 0 else (ex_hi[k] >= stop)
            hit_tp = (ex_hi[k] >= target) if d > 0 else (ex_lo[k] <= target)
            if hit_stop:
                exit_px, exit_bar, reason = stop, k, "stop"; break
            if hit_tp:
                exit_px, exit_bar, reason = target, k, "target"; break
        if exit_px is None:
            kx = min(e + X.HOLD_BARS - 1, N - 1)
            exit_px = bid[kx] if d > 0 else ask[kx]
            exit_bar, reason = kx, "time"
        r_mult = (exit_px - entry) * d / dist

        # size the trade at a fixed fraction of the account already reached,
        # the same fixed-fractional convention as every other book in this
        # project - so the log shows what compounding actually does
        risk_money = risk_frac * equity
        lots = ACC.lots_for_risk(risk_money, dist)
        pnl = r_mult * risk_money if lots >= ACC.min_lot else 0.0
        equity += pnl
        peak = max(peak, equity)
        dd = 1.0 - equity / peak if peak > 0 else 0.0

        rows.append(dict(
            signal_time=idx[t], entry_time=idx[e], exit_time=idx[exit_bar],
            direction="BUY" if d > 0 else "SELL",
            entry_px=entry, stop_px=stop, target_px=target, exit_px=exit_px,
            exit_reason=reason, held_bars=exit_bar - e + 1,
            R=r_mult, risk_money_USC=risk_money, lots=lots,
            pnl_USC=pnl, equity_USC=equity, drawdown_pct=dd * 100))
        busy = exit_bar
    return pd.DataFrame(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--risk", type=float, default=0.01)
    a = ap.parse_args()

    df = pd.read_parquet(".cache_duka/XAUUSD_H1_2003_2026.parquet")
    df = df[df.index.year >= 2004]
    for k in ("open", "high", "low", "close"):
        df[k] = (df[f"bid_{k}"] + df[f"ask_{k}"]) / 2
    spr = df["ask_close"] - df["bid_close"]
    df = df[(spr > 0) & (df.high >= df.low) & (df.low > 0)]

    P = X.prep(df, 60)
    dvec, Ivec = X.make_templates(P)["P01"]()
    T = trade_log(P, dvec, Ivec, 0, P["N"], 0.001, a.risk)

    print("P01 (Donchian-20 breakout) - FIXED ENGINE - real trade log")
    print("=" * 84)
    print(f"XAUUSD H1, {P['idx'][0].date()} -> {P['idx'][-1].date()}, "
          f"risk {a.risk*100:.1f}% of equity/trade, start 500 USC\n")

    n = len(T)
    wins = T[T.R > 0]
    losses = T[T.R <= 0]
    print(f"trades              {n:,}")
    print(f"win rate            {len(wins)/n*100:.1f}%")
    print(f"avg win / avg loss  {wins.R.mean():+.3f}R / {losses.R.mean():+.3f}R")
    print(f"exit reasons        "
          + ", ".join(f"{k} {v} ({v/n*100:.0f}%)"
                      for k, v in T.exit_reason.value_counts().items()))
    print(f"\nfinal equity        {T.equity_USC.iloc[-1]:,.2f} USC "
          f"(from 500.00)")
    print(f"total P&L           {T.pnl_USC.sum():+,.2f} USC")
    print(f"max drawdown        {T.drawdown_pct.max():.1f}%")
    print(f"best trade          {T.pnl_USC.max():+,.2f} USC")
    print(f"worst trade         {T.pnl_USC.min():+,.2f} USC")

    print(f"\nfirst 5 trades:")
    print(T.head(5).drop(columns=["risk_money_USC", "lots"]).to_string(index=False))
    print(f"\nlast 5 trades:")
    print(T.tail(5).drop(columns=["risk_money_USC", "lots"]).to_string(index=False))

    print(f"\nyear-by-year:")
    T["year"] = T.entry_time.dt.year
    yr = T.groupby("year").agg(trades=("R", "size"), win_rate=("R", lambda x: (x > 0).mean()*100),
                               sum_R=("R", "sum"), pnl_USC=("pnl_USC", "sum"))
    print(yr.round(2).to_string())

    out = pathlib.Path(__file__).parent / "p01_trade_log.csv"
    T.to_csv(out, index=False)
    zeroed = int((T.pnl_USC == 0).sum()) - len(T[T.R.abs() < 0.001])
    if zeroed > 0:
        print(f"\nNOTE: {zeroed} trades show pnl_USC=0 near the end of the log.")
        print(f"That is the min-lot floor, not a bug: at {a.risk*100:.0f}% risk")
        print(f"on a {T.equity_USC.iloc[-1]:.0f} USC account with gold's stop")
        print(f"distance now tens of dollars wide, the position size needed")
        print(f"is BELOW Exness's 0.01 minimum lot, so the trade cannot be")
        print(f"sized at all - a real constraint a small account hits, not")
        print(f"an artefact of this script.")

    print(f"\nfull trade-by-trade log -> {out}")


if __name__ == "__main__":
    main()
