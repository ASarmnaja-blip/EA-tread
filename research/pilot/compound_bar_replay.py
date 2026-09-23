"""Causal bar-by-bar finance replay for the weekly M5 candidate.

The first calendar year is sizing calibration.  Its drawdown is frozen before
the 2022+ evaluation starts; future drawdowns are never used to choose volume.
Cash is added at the first tradable bar of every new month.  Every open position
is marked Bid/Ask on every M5 close, so overlap and floating drawdown are visible.

Research only: this module imports no broker order API.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import argparse
import math
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import evolution_candidate_validation as valid
import evolution_portfolio_audit as audit
import mtf_engine as E


DAY = 86400
INITIAL_USD = 100.0
MONTHLY_DCA_USD = 100.0
LOT_STEP = 0.01                 # cent lots
MAX_CENT_LOT = 200.0
LEVERAGE = 2000.0
CALIBRATION_BUFFER = 1.25
TARGETS = (0.30, 0.35, 0.40, 0.45, 0.50)


@dataclass
class Position:
    trade: audit.Trade
    volume: float               # Exness cent lots; 1.00 == 0.01 standard lot


def _month(t: int) -> tuple[int, int]:
    d = datetime.fromtimestamp(t, timezone.utc)
    return d.year, d.month


def _open_pnl(p: Position, k: int, bars) -> float:
    r = p.trade
    fee = E.COMMISSION_RT + 2 * E.SLIP_PER_FILL
    if r.direction > 0:
        x = float(bars.c[k]) - r.entry - fee
        nights = E.rollover_nights(r.t, int(bars.t[k]))
        x -= nights * E.SWAP_LONG
    else:
        x = r.entry - (float(bars.c[k]) + E.spread_at(bars, k)) - fee
    return x * p.volume


def _calibration(rows: list[audit.Trade], bars, end: int) -> dict:
    train = [r for r in rows if r.t < end and r.exit_t < end]
    mtm = audit.mark_to_market(train, bars)
    realised = audit.metrics(train)
    raw = max(abs(float(mtm["mtm_DD_USD_001"])),
              abs(float(realised.get("DD_USD_001", 0.0))))
    return {"trades": len(train), "raw_unit_DD": raw,
            "buffered_unit_DD": raw * CALIBRATION_BUFFER}


def replay(rows: list[audit.Trade], bars, start: int, end: int,
           target_dd: float, unit_dd: float) -> dict:
    chosen = [r for r in rows if start <= r.t < end]
    by_entry, by_exit = defaultdict(list), defaultdict(list)
    for r in chosen:
        by_entry[r.entry_k].append(r)
        by_exit[r.exit_k].append(r)
    k0 = int(np.searchsorted(bars.t, start, side="left"))
    k1 = int(np.searchsorted(bars.t, end, side="left"))
    cash = INITIAL_USD
    deposits = INITIAL_USD
    peak = INITIAL_USD
    worst_dd = 0.0
    open_positions: list[Position] = []
    halted = False
    halt_t = None
    trades = rejected_margin = rejected_min = 0
    max_concurrent = 0
    max_volume = 0.0
    prior_month = _month(int(bars.t[k0]))

    for k in range(k0, k1):
        now_month = _month(int(bars.t[k]))
        if now_month != prior_month:
            cash += MONTHLY_DCA_USD
            deposits += MONTHLY_DCA_USD
            prior_month = now_month

        # Positions that resolve on this bar are realised before new entries.
        closing = {id(r): r for r in by_exit.get(k, [])}
        if closing:
            keep = []
            for p in open_positions:
                if id(p.trade) in closing:
                    cash += p.trade.dollars * p.volume
                else:
                    keep.append(p)
            open_positions = keep

        floating = sum(_open_pnl(p, k, bars) for p in open_positions)
        equity = cash + floating
        peak = max(peak, equity)
        dd = 0.0 if peak <= 0 else max(0.0, (peak - equity) / peak)
        worst_dd = max(worst_dd, dd)
        if dd >= target_dd and not halted:
            halted = True
            halt_t = int(bars.t[k])

        if not halted:
            for r in by_entry.get(k, []):
                floating = sum(_open_pnl(p, k, bars) for p in open_positions)
                equity = cash + floating
                raw_volume = equity * target_dd / unit_dd
                volume = math.floor(raw_volume / LOT_STEP + 1e-12) * LOT_STEP
                volume = min(volume, MAX_CENT_LOT)
                if volume < LOT_STEP:
                    rejected_min += 1
                    continue
                used_margin = sum(p.trade.entry * p.volume / LEVERAGE
                                  for p in open_positions)
                affordable = max(0.0, (equity - used_margin) * LEVERAGE / r.entry)
                affordable = math.floor(affordable / LOT_STEP) * LOT_STEP
                volume = min(volume, affordable)
                if volume < LOT_STEP:
                    rejected_margin += 1
                    continue
                trades += 1
                max_volume = max(max_volume, volume)
                if r.exit_k == k:
                    # Entry-bar stop/target is already resolved conservatively
                    # by the execution engine; realise it on this same bar.
                    cash += r.dollars * volume
                else:
                    open_positions.append(Position(r, volume))
                    max_concurrent = max(max_concurrent, len(open_positions))

        floating = sum(_open_pnl(p, k, bars) for p in open_positions)
        equity = cash + floating
        peak = max(peak, equity)
        dd = 0.0 if peak <= 0 else max(0.0, (peak - equity) / peak)
        worst_dd = max(worst_dd, dd)
        if equity <= 0:
            halted = True
            halt_t = halt_t or int(bars.t[k])
            break

    final_equity = cash + (sum(_open_pnl(p, max(k0, k1 - 1), bars)
                               for p in open_positions) if k1 > k0 else 0.0)
    return {
        "target_DD_pct": 100 * target_dd,
        "actual_MTM_DD_pct": 100 * worst_dd,
        "final_equity_USD": final_equity,
        "deposits_USD": deposits,
        "net_profit_USD": final_equity - deposits,
        "trades": trades,
        "max_concurrent": max_concurrent,
        "max_cent_lot": max_volume,
        "halted": halted,
        "halt_utc": (datetime.fromtimestamp(halt_t, timezone.utc).isoformat()
                     if halt_t is not None else None),
        "rejected_margin": rejected_margin,
        "rejected_min_volume": rejected_min,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", choices=("demo90", "cent260"),
                        default="demo90")
    args = parser.parse_args()
    if args.profile == "cent260":
        # User-supplied live-account spread: 260 points at three decimals.
        # Exness Standard Cent has no trading commission; slippage remains.
        E.SPREAD_FALLBACK = 0.260
        E.COMMISSION_RT = 0.0
    bars = audit.hist.load_history()
    first, last = int(bars.t[0]), int(bars.t[-1] + bars.step)
    uni, meta = audit.load_universe(bars)
    rankings, purged = audit.weekly_rankings(uni, first, last)
    m5 = [(cut, end, [tag for tag in ranked if meta[tag]["tf"] == "M5"])
          for cut, end, ranked in rankings]
    rows, info = audit.weekly_portfolio(bars, uni, meta, m5, purged, 5, True)

    calibration_end = int(datetime(2022, 1, 1, tzinfo=timezone.utc).timestamp())
    cal = _calibration(rows, bars, calibration_end)
    if cal["buffered_unit_DD"] <= 0:
        raise RuntimeError("calibration drawdown is zero; sizing is undefined")
    print("profile", args.profile, "spread_floor", E.SPREAD_FALLBACK,
          "commission_rt", E.COMMISSION_RT, "slip_per_fill", E.SLIP_PER_FILL)
    print("candidate", info)
    print("calibration", cal,
          "period", datetime.fromtimestamp(first, timezone.utc).date(),
          "..", datetime.fromtimestamp(calibration_end, timezone.utc).date())
    for label, end in (("EXCLUDE_LATEST_365D", last - 365 * DAY),
                       ("ALL_FORWARD", last)):
        months = ((datetime.fromtimestamp(end, timezone.utc).year - 2022) * 12
                  + datetime.fromtimestamp(end, timezone.utc).month - 1)
        print(f"\n[{label}] start=2022-01-01 end="
              f"{datetime.fromtimestamp(end, timezone.utc):%Y-%m-%d} months={months}")
        for target in TARGETS:
            print(replay(rows, bars, calibration_end, end, target,
                         cal["buffered_unit_DD"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
