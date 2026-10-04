#!/usr/bin/env python3
"""A portfolio engine for OVERLAPPING trades.

WHY SUMMING R IS NOT A PORTFOLIO RESULT

  Every number this repo has reported so far is a per-trade expectancy in R,
  and R is a ratio: it divides by the risk that trade was planned at. Adding
  R across trades that were open AT THE SAME TIME quietly assumes each one was
  sized against the same account and that the account was never short of
  margin, never concentrated, and never drew down between them. None of that
  is true when trades overlap:

    - three positions open at once is three times the risk on the account, not
      one unit of risk three times
    - a 10% drawdown mid-sequence shrinks every subsequent position, so the
      recovery is smaller than the loss even at identical R
    - a position that cannot be opened for want of margin, or that rounds to
      below the minimum lot, contributes nothing - but summing R counts it
    - equity moves between the closes, and a stop-out happens on FLOATING
      equity, not on closed-trade balance

  So this engine does not consume R. It consumes MID prices and a stop, sizes
  each position from live equity, charges its own spread, commission,
  slippage and swap, marks every open position to market on every bar, and
  reports what the account actually did.

  That also means the R that comes out of exec_engine must be handed here
  WITHOUT its cost already subtracted, or the cost is charged twice. `from_
  trades()` takes the raw entry/exit/stop prices for exactly that reason.

WHAT IS MEASURED, AND WHY EACH ONE
  max_concurrent        how many positions were open at the peak
  max_open_risk_frac    the largest fraction of equity at risk across all open
                        positions at once - the number that decides whether a
                        run of correlated stops is survivable
  dd_closed             drawdown of the BALANCE curve, sampled at closes. This
                        is the flattering one and it is the one usually quoted.
  dd_floating           drawdown of the EQUITY curve, bar by bar, including
                        unrealised loss on open positions. This is the one a
                        margin call is measured against, and it is always the
                        larger of the two.

WHAT IS ASSUMED RATHER THAN MEASURED
  Everything in Broker below is a broker policy, not something this repo has
  observed: contract size, leverage, lot granularity, commission, swap rates
  and the stress multipliers. They are defaults chosen to be plausible for a
  retail XAUUSD account and they are configuration, not findings. The spread
  series is real (Dukascopy bid/ask); the slippage is not - no tick-level
  fill study has been done here, so the stress levels are a sensitivity
  analysis, not a measurement.
"""
from dataclasses import dataclass, field, replace
import numpy as np, pandas as pd

# --------------------------------------------------------------- config --
@dataclass
class Broker:
    """Account and instrument policy. All of this is ASSUMPTION."""
    contract_size: float = 100.0       # XAUUSD: 100 oz per 1.00 lot
    min_lot: float = 0.01
    lot_step: float = 0.01
    max_lot: float = 100.0
    leverage: float = 100.0            # 1:100
    commission_per_lot_side: float = 3.5      # USD, so 7.00 round trip
    slippage_points: float = 0.0       # price units, always against the trade
    swap_long_per_lot_night: float = -6.0     # USD/lot/night, gold longs pay
    swap_short_per_lot_night: float = 1.5     # shorts usually receive a little
    spread_mult: float = 1.0
    margin_call_frac: float = 0.5      # equity/used-margin below this = stop out

# Cost stress. The point is not to guess the future but to show how much of a
# result depends on costs staying where they are. A result that only exists at
# "base" is a result about the spread, not about the market.
STRESS = {
    "base":     dict(spread_mult=1.0, slippage_points=0.00,
                     commission_per_lot_side=3.5),
    "elevated": dict(spread_mult=1.5, slippage_points=0.05,
                     commission_per_lot_side=5.0),
    "adverse":  dict(spread_mult=3.0, slippage_points=0.20,
                     commission_per_lot_side=7.0),
}

def stressed(broker, level):
    if level not in STRESS:
        raise KeyError(f"unknown stress level {level!r}; have {list(STRESS)}")
    return replace(broker, **STRESS[level])

# ---------------------------------------------------------------- sizing --
def round_lot(x, step, min_lot, max_lot):
    """Lots always round DOWN. Rounding to nearest would let a position be
    larger than the risk budget allows, which is the wrong direction to err."""
    if not np.isfinite(x) or x <= 0: return 0.0
    n = np.floor(x / step + 1e-9) * step
    n = round(n, 8)
    if n < min_lot: return 0.0
    return min(n, max_lot)

# ------------------------------------------------------------------ core --
def simulate(trades, mid, index, broker=Broker(), risk_frac=0.01,
             start_equity=10_000.0, spread=None, allow_overlap=True,
             max_concurrent=None):
    """Run an account through a list of overlapping trades.

    trades   list of dicts with, at minimum:
               entry_bar, exit_bar   integer bar indices (exit >= entry)
               d                     +1 long, -1 short
               entry_px, exit_px     MID prices, no cost applied
               stop_px               the planned stop, in price units
    mid      full-length mid-price array used to mark open positions to market
    index    the DatetimeIndex, used for swap nights and for CAGR
    spread   full-length spread array in price units; None = broker-free fills

    Returns a dict of results plus the per-bar equity curve and a trade log.
    """
    n = len(mid)
    if spread is None: spread = np.zeros(n)
    spread = np.asarray(spread, float) * broker.spread_mult
    slip = broker.slippage_points

    # bucket trades by the bar they open on, so the loop is one pass
    by_entry = {}
    for t in trades:
        by_entry.setdefault(int(t["entry_bar"]), []).append(t)

    balance = float(start_equity)
    equity_curve = np.full(n, np.nan)
    open_pos = []                 # live positions
    log = []                      # closed positions, in close order
    rejected = dict(min_lot=0, margin=0, concurrency=0, bad_stop=0)
    used_margin = 0.0
    peak_concurrent = 0
    peak_open_risk = 0.0
    peak_margin_use = 0.0
    paid = dict(spread=0.0, commission=0.0, swap=0.0, slippage=0.0)
    stopped_out_at = None

    day = index.normalize().to_numpy() if hasattr(index, "normalize") else None

    def float_pl(b):
        """Unrealised P&L on open positions, including costs already incurred.
        Accrued swap belongs here: a long held for three weeks has really paid
        that money and its floating equity is really lower for it."""
        tot = 0.0
        for p in open_pos:
            tot += (mid[b] - p["fill"]) * p["d"] * p["lots"] * broker.contract_size
            tot -= p["entry_cost"]
            tot += p["swap_paid"]          # signed: negative means paid
        return tot

    def close_due(b):
        """Close every position whose exit bar has arrived.

        The condition is <= b, not == b. A trade that opens and closes on the
        SAME bar - which the intraday session deadline produces constantly,
        since a signal on the last closable bar of the day gets a one-bar
        trade - is opened in step 3, AFTER step 1 has already run. With an
        equality test it was never closed at all: it held margin for the rest
        of the backtest, and thirteen years of them eventually pushed
        used_margin high enough to fire a false margin call, whose liquidation
        realised +4,737 USC of stale profit in a single bar. Hence also the
        second call to this function after opening.
        """
        nonlocal balance, used_margin
        still = []
        for p in open_pos:
            if p["exit_bar"] <= b:
                # exiting: a long SELLS at the bid, a short BUYS at the ask
                half = spread[b] / 2.0
                fill = p["exit_px"] - p["d"] * (half + slip)
                gross = (fill - p["fill"]) * p["d"] * p["lots"] * broker.contract_size
                exit_comm = broker.commission_per_lot_side * p["lots"]
                pl = gross - exit_comm - p["entry_cost"] + p["swap_paid"]
                # NOT floored here. Flooring a losing close at zero mid-run
                # destroys money conservation: the account "loses" the negative
                # amount and then carries on trading from zero, which in one
                # test turned a wiped account into a +7,562 USC recovery it was
                # never alive to make. Negative-balance protection belongs at
                # the liquidation below, which also STOPS the account.
                balance += pl
                used_margin -= p["margin"]
                paid["spread"] += half * p["lots"] * broker.contract_size
                paid["slippage"] += slip * p["lots"] * broker.contract_size
                paid["commission"] += exit_comm
                log.append(dict(
                    entry_bar=p["entry_bar"], exit_bar=b, d=p["d"],
                    lots=p["lots"], entry_fill=p["fill"], exit_fill=fill,
                    stop_px=p["stop_px"], risk_money=p["risk_money"],
                    gross=gross, commission=exit_comm + p["entry_comm"],
                    swap=p["swap_paid"],
                    spread_cost=p["entry_spread_cost"] + half * p["lots"] * broker.contract_size,
                    pl=pl, balance_after=balance,
                    R_account=pl / p["risk_money"] if p["risk_money"] > 0 else np.nan,
                    entry_time=index[p["entry_bar"]], exit_time=index[b]))
            else:
                still.append(p)
        return still

    for b in range(n):
        if stopped_out_at is not None:
            equity_curve[b] = balance
            continue
        # ---- 1. close anything due on this bar (frees margin first) --------
        open_pos = close_due(b)

        # ---- 2. swap, charged when the bar crosses into a new day ---------
        if day is not None and b > 0 and day[b] != day[b - 1]:
            for p in open_pos:
                # SIGN CONVENTION: swap is a signed CASH FLOW, not a cost.
                # A negative rate means the position pays (gold longs do); a
                # positive rate means it receives. The first version negated
                # the rate here and then subtracted the result at close, which
                # charged the right amount but REPORTED a long's swap as
                # positive income. The hand-computed test caught it.
                rate = (broker.swap_long_per_lot_night if p["d"] > 0
                        else broker.swap_short_per_lot_night)
                s = rate * p["lots"]
                p["swap_paid"] += s
                paid["swap"] += s

        # ---- 3. open anything signalled on this bar -----------------------
        eq_now = balance + float_pl(b)
        for t in by_entry.get(b, []):
            if max_concurrent is not None and len(open_pos) >= max_concurrent:
                rejected["concurrency"] += 1; continue
            if not allow_overlap and open_pos:
                rejected["concurrency"] += 1; continue
            half = spread[b] / 2.0
            # entering: a long BUYS at the ask, a short SELLS at the bid
            fill = t["entry_px"] + t["d"] * (half + slip)
            # Risk is measured from the ACTUAL FILL, not from the mid. The
            # spread has already moved the entry against the trade, so the
            # distance left to the stop is genuinely shorter (long) - and the
            # position must be sized on what is really at risk. A test written
            # against the mid expected 0.10 lots here and got 0.09; the 0.09
            # is right.
            risk_pts = (fill - t["stop_px"]) * t["d"]
            if not np.isfinite(risk_pts) or risk_pts <= 0:
                # the fill is already at or through the stop - there is no
                # position to size. exec_engine skips these upstream; this is
                # the second line of defence.
                rejected["bad_stop"] += 1; continue
            want = (eq_now * risk_frac) / (risk_pts * broker.contract_size)
            lots = round_lot(want, broker.lot_step, broker.min_lot, broker.max_lot)
            if lots <= 0:
                rejected["min_lot"] += 1; continue
            margin = lots * broker.contract_size * fill / broker.leverage
            if margin > max(eq_now - used_margin, 0.0):
                rejected["margin"] += 1; continue
            entry_comm = broker.commission_per_lot_side * lots
            sp_cost = half * lots * broker.contract_size
            paid["spread"] += sp_cost
            paid["slippage"] += slip * lots * broker.contract_size
            paid["commission"] += entry_comm
            used_margin += margin
            open_pos.append(dict(
                entry_bar=b, exit_bar=int(t["exit_bar"]), d=int(t["d"]),
                lots=lots, fill=fill, exit_px=t["exit_px"],
                stop_px=t["stop_px"], margin=margin,
                risk_money=risk_pts * lots * broker.contract_size,
                entry_comm=entry_comm, entry_spread_cost=sp_cost,
                entry_cost=entry_comm, swap_paid=0.0))

        # ---- 3b. a trade that opens and closes on the same bar -------------
        open_pos = close_due(b)

        # ---- 4. mark to market --------------------------------------------
        eq = balance + float_pl(b)
        equity_curve[b] = eq
        if open_pos:
            peak_concurrent = max(peak_concurrent, len(open_pos))
            open_risk = sum(p["risk_money"] for p in open_pos)
            if eq > 0:
                peak_open_risk = max(peak_open_risk, open_risk / eq)
            if used_margin > 0:
                peak_margin_use = max(peak_margin_use, used_margin / max(eq, 1e-9))
        # ---- 5. margin call, ENFORCED -------------------------------------
        # Detecting a stop-out and then carrying on is how a backtest reports
        # a recovery the account was never alive to see. A real broker closes
        # the positions; so does this. Once stopped out the account takes no
        # further trades.
        if stopped_out_at is None and (
                (used_margin > 0 and eq / used_margin < broker.margin_call_frac)
                or eq <= 0):
            stopped_out_at = b
            for p in open_pos:
                half = spread[b] / 2.0
                fill = mid[b] - p["d"] * (half + slip)
                gross = (fill - p["fill"]) * p["d"] * p["lots"] * broker.contract_size
                exit_comm = broker.commission_per_lot_side * p["lots"]
                pl = gross - exit_comm - p["entry_cost"] + p["swap_paid"]
                balance += pl
                paid["commission"] += exit_comm
                # Negative-balance protection. A retail account cannot end a
                # liquidation owing money, and logging the raw negative made
                # dd_closed read above 100% - a drawdown deeper than the whole
                # account, which is not a thing. The account is simply gone.
                balance = max(balance, 0.0)
                log.append(dict(
                    entry_bar=p["entry_bar"], exit_bar=b, d=p["d"],
                    lots=p["lots"], entry_fill=p["fill"], exit_fill=fill,
                    stop_px=p["stop_px"], risk_money=p["risk_money"],
                    gross=gross, commission=exit_comm + p["entry_comm"],
                    swap=p["swap_paid"],
                    spread_cost=p["entry_spread_cost"] + half * p["lots"] * broker.contract_size,
                    pl=pl, balance_after=balance,
                    R_account=pl / p["risk_money"] if p["risk_money"] > 0 else np.nan,
                    entry_time=index[p["entry_bar"]], exit_time=index[b],
                    forced="margin_call"))
            open_pos = []
            used_margin = 0.0
            equity_curve[b] = balance
        if stopped_out_at is not None:
            equity_curve[b] = balance
            continue

    # -------------------------------------------------------- drawdowns --
    # Drawdown is capped at 100%. Below zero the account is simply gone, and
    # "a 153% drawdown" is not a deeper loss, it is a reporting artifact of
    # dividing a negative equity by a positive peak.
    eqc = pd.Series(equity_curve).ffill().fillna(start_equity).to_numpy()
    eqc_dd = np.maximum(eqc, 0.0)
    run_max = np.maximum.accumulate(eqc_dd)
    dd_floating = float(min(1.0, np.max(1.0 - eqc_dd / np.maximum(run_max, 1e-9))))

    bal = np.maximum(
        np.array([start_equity] + [r["balance_after"] for r in log], float), 0.0)
    bmax = np.maximum.accumulate(bal)
    dd_closed = float(min(1.0, np.max(1.0 - bal / np.maximum(bmax, 1e-9))))

    # Annualise over the span the account was ACTUALLY TRADING, not the span
    # of the price file. Pricing 13 years of trades against a 23-year index
    # divides the growth by a decade the strategy never traded in and reports
    # a CAGR roughly half what the equity curve did.
    if log:
        t_start, t_end = log[0]["entry_time"], log[-1]["exit_time"]
    else:
        t_start, t_end = index[0], index[-1]
    yrs = (t_end - t_start).days / 365.25
    final = float(eqc[-1])
    # Annualising a span shorter than a year inflates whatever happened in it
    # by a huge power. A six-week test has no CAGR, and reporting one would be
    # the most misleading number on the page, so it is NaN rather than a
    # spectacular figure nobody checks the denominator of.
    if yrs < 1.0:
        cagr = float("nan")
    elif final <= 0:
        cagr = -1.0
    else:
        cagr = (final / start_equity) ** (1.0 / yrs) - 1.0

    return dict(
        final_equity=final, start_equity=start_equity, cagr=cagr, years=yrs,
        blown=stopped_out_at is not None,
        n_taken=len(log), n_offered=len(trades), rejected=rejected,
        max_concurrent=peak_concurrent, max_open_risk_frac=peak_open_risk,
        max_margin_use=peak_margin_use,
        dd_closed=dd_closed, dd_floating=dd_floating,
        margin_call_bar=stopped_out_at,
        costs=paid, equity=eqc, log=log,
        net_pl=final - start_equity,
        risk_frac=risk_frac)

def from_trades(W, R_mask, held, mid, index, spread, exit_px=None, **kw):
    """Adapt a mega_search recorded walk into simulate()'s input.

    `exit_px` IS NOT OPTIONAL IN PRACTICE. The first version of this function
    priced every exit at the CLOSE OF THE EXIT BAR, which is only correct for
    a time exit. A trade stopped out mid-bar exits at its stop, and the bar it
    was stopped in frequently closes somewhere else entirely - measured on
    real XAUUSD H1, one trade's true -1.063R was booked as -0.482R and the
    next one's true -1.042R was booked as -3.639R. That is the same defect as
    the entry-gap bug this repo started with: a price that is not the trade's
    exit being written into the account.

    Pass the resolver's own exit price. If it is omitted the bar close is used
    and a warning is printed, because silently doing the wrong thing is how
    that bug survived in the first place.

    Takes RAW prices: exec_engine already subtracted a round-trip cost when it
    computed R, and this engine charges its own, so R is deliberately not used
    here at all."""
    idxs = np.where(R_mask)[0]
    if exit_px is None:
        import warnings
        warnings.warn("from_trades called without exit_px: stop and target "
                      "exits will be mispriced at the bar close")
    trades = []
    for q in idxs:
        e = int(W["i"][q]) + 1
        h = held[q]
        if not np.isfinite(h): continue
        x = int(W["i"][q] + h)
        if x >= len(mid): x = len(mid) - 1
        if x < e: x = e
        px = float(mid[x]) if exit_px is None else float(exit_px[q])
        if not np.isfinite(px): px = float(mid[x])
        trades.append(dict(entry_bar=e, exit_bar=x, d=int(W["d"][q]),
                           entry_px=float(W["entry"][q]), exit_px=px,
                           stop_px=float(W["stop"][q])))
    return simulate(trades, mid, index, spread=spread, **kw)

def summarise(res, label=""):
    c = res["costs"]
    rj = res["rejected"]
    return "\n".join([
        f"{label}",
        f"  equity      {res['start_equity']:,.0f} -> {res['final_equity']:,.0f} "
        f"over {res['years']:.1f}y   CAGR {res['cagr']*100:+.2f}%",
        f"  trades      {res['n_taken']:,} taken of {res['n_offered']:,} offered "
        f"(rejected: {rj['margin']:,} margin, {rj['min_lot']:,} below min lot, "
        f"{rj['concurrency']:,} concurrency, {rj['bad_stop']:,} bad stop)",
        f"  exposure    max {res['max_concurrent']} positions open at once, "
        f"peak open risk {res['max_open_risk_frac']*100:.1f}% of equity, "
        f"peak margin use {res['max_margin_use']*100:.1f}%",
        f"  drawdown    closed-trade {res['dd_closed']*100:.1f}%   "
        f"FLOATING {res['dd_floating']*100:.1f}%"
        + ("   *** MARGIN CALL at bar "
           f"{res['margin_call_bar']}" if res["margin_call_bar"] is not None else ""),
        f"  costs paid  spread {c['spread']:,.0f}  commission {c['commission']:,.0f}"
        f"  slippage {c['slippage']:,.0f}  swap {c['swap']:+,.0f} (signed: "
        f"negative = paid)",
        f"              total drag {c['spread']+c['commission']+c['slippage']-c['swap']:,.0f} "
        f"against net P&L {res['net_pl']:,.0f}",
    ])

def log_frame(res):
    """The trade log as a DataFrame, so a result can be traced back to the
    individual fills that produced it."""
    return pd.DataFrame(res["log"])
