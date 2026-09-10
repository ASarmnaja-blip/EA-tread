# ============================================================================
# DOBBY 3-LEG  -  QUANTCONNECT (LEAN) ALGORITHM
#
# Purpose: settle whether the EMA 9/21 cross + 3-leg ladder has an edge, using
# real order fills instead of a hand-rolled tally, on 2025-onward data only.
#
# WHAT THIS ANSWERS THAT THE PINE BUILD COULD NOT
#
#  1. EXITS RESOLVE ON MINUTE BARS.
#     Signals are computed on 5-minute bars but stops and targets are real
#     LEAN orders against minute data, so a bar that touched both the stop and
#     the target resolves in the order it actually happened. Resolving on the
#     signal bar inflated earlier work by +0.06R at 1.5R and +0.20R at 3R.
#
#  2. RISK PER SIGNAL IS CONSTANT.
#     The Pine build used a fixed lot with a stop that ranged over 10x
#     (0.30-3.00 x ATR), so money risk varied 10x per signal. Its +182 cent
#     September result came out ~25% larger than its own +5R because the
#     winners happened to carry wider stops. Here quantity is derived from
#     the stop distance, so 1R is the same money every time and the R
#     statistics and the money statistics agree by construction.
#
#  3. TP1 IS A REAL FILL, NOT A BAR TOUCH.
#     Break-even moves when leg 1's limit order actually fills.
#
#  4. THE SPREAD IS THE MEASURED ONE.
#     Default 0.7525 = OANDA's measured 2023-2026 mean for gold. The Pine
#     build assumed 0.26, which is 2.9x optimistic. Half the spread is
#     charged per order, so each leg pays one full spread per round trip.
#
# OUTPUT
#   Per-signal R outcomes, expectancy, t-statistic, and the sample size that
#   would be needed to reach t = 2.0. Long and short are reported separately
#   alongside buy-and-hold, because a long-only rule on gold inherits gold's
#   drift and that is not timing skill.
# ============================================================================

from AlgorithmImports import *
from datetime import timedelta
import math


class HalfSpreadFeeModel(FeeModel):
    """Half the spread per order, so a leg's round trip pays one full spread.
    Mirrors how the Pine build costs the same system, which keeps the two
    results comparable."""

    def __init__(self, spread_price):
        self.half_spread = spread_price / 2.0

    def get_order_fee(self, parameters):
        quantity = abs(parameters.order.quantity)
        return OrderFee(CashAmount(self.half_spread * quantity, "USD"))


class Leg:
    def __init__(self, name, quantity, target, r_multiple):
        self.name = name
        self.quantity = quantity
        self.target = target
        self.r_multiple = r_multiple
        self.stop_ticket = None
        self.limit_ticket = None
        self.closed = False
        self.exit_price = None
        self.outcome = None


class DobbyThreeLegGold(QCAlgorithm):

    # ---- run window: 2025 onward only -------------------------------------
    START = (2025, 1, 1)
    END   = (2026, 9, 10)

    def initialize(self):
        self.set_start_date(*self.START)
        self.set_end_date(*self.END)
        self.set_cash(100000)

        # ---- signal parameters (match the Pine build) ---------------------
        self.fast_len      = 9
        self.slow_len      = 21
        self.trend_len     = 50
        self.atr_len       = 14
        self.pivot_left    = 5
        self.pivot_right   = 5
        self.fallback_look = 10
        self.min_risk_atr  = 0.30
        self.max_risk_atr  = 3.00
        self.use_trend_filter = True
        self.max_hold_bars = 120          # 5-minute bars

        # ---- risk: constant money per signal ------------------------------
        # 1.0% per signal across three legs. The Pine build was running ~3.8%
        # per signal, which is why a routine 6-loss run cost it 22%.
        self.risk_per_signal_pct = 1.0
        self.max_gross_leverage  = 20.0

        # ---- cost assumption ----------------------------------------------
        # OANDA measured mean for gold, 2023-2026. Replace with your broker's
        # own measurement before trusting any verdict.
        self.spread_price = 0.7525

        cfd = self.add_cfd("XAUUSD", Resolution.MINUTE, Market.OANDA)
        self.symbol = cfd.symbol
        cfd.set_fee_model(HalfSpreadFeeModel(self.spread_price))
        cfd.set_leverage(50)

        # ---- 5-minute signal stream ---------------------------------------
        self.five = TradeBarConsolidator(timedelta(minutes=5))
        self.five.data_consolidated += self.on_five_minute
        self.subscription_manager.add_consolidator(self.symbol, self.five)

        self.ema_fast = ExponentialMovingAverage(self.fast_len)
        self.ema_slow = ExponentialMovingAverage(self.slow_len)
        self.atr      = AverageTrueRange(self.atr_len, MovingAverageType.WILDERS)
        self.register_indicator(self.symbol, self.ema_fast, self.five, lambda x: x.close)
        self.register_indicator(self.symbol, self.ema_slow, self.five, lambda x: x.close)
        self.register_indicator(self.symbol, self.atr, self.five)

        # ---- 15-minute trend filter ---------------------------------------
        self.fifteen = TradeBarConsolidator(timedelta(minutes=15))
        self.subscription_manager.add_consolidator(self.symbol, self.fifteen)
        self.trend_ema = ExponentialMovingAverage(self.trend_len)
        self.register_indicator(self.symbol, self.trend_ema, self.fifteen, lambda x: x.close)

        # ---- structure ----------------------------------------------------
        self.window = []
        self.last_swing_low = None
        self.last_swing_high = None
        self.prev_fast = None
        self.prev_slow = None

        # ---- trade state --------------------------------------------------
        self.reset_trade()

        # ---- statistics ---------------------------------------------------
        self.signal_r = []          # realised R per completed signal
        self.signal_dir = []        # +1 long, -1 short, aligned with signal_r
        self.total_signals = 0
        self.skipped_risk = 0
        self.skipped_leverage = 0
        self.skipped_size = 0
        self.leg_stats = {n: {"TP": 0, "SL": 0, "BE": 0, "TIME": 0}
                          for n in ("L1", "L2", "L3")}
        self.double_fills = 0
        self.first_price = None
        self.last_price = None

    # -----------------------------------------------------------------------
    def reset_trade(self):
        self.in_trade = False
        self.direction = 0
        self.entry_price = None
        self.stop_price = None
        self.time_stopping = False
        self.risk_distance = None
        self.risk_money_leg = None
        self.be_level = None
        self.tp1_hit = False
        self.legs = []
        self.bars_held = 0
        self.entry_ticket = None
        self.signal_pnl = 0.0
        self.entry_fee = 0.0

    # -----------------------------------------------------------------------
    def on_five_minute(self, sender, bar):
        if self.first_price is None:
            self.first_price = bar.close
        self.last_price = bar.close

        self.window.append(bar)
        if len(self.window) > 60:
            self.window.pop(0)
        self.update_pivots()

        if not (self.ema_fast.is_ready and self.ema_slow.is_ready
                and self.atr.is_ready and self.trend_ema.is_ready):
            self.prev_fast = self.ema_fast.current.value
            self.prev_slow = self.ema_slow.current.value
            return

        fast = self.ema_fast.current.value
        slow = self.ema_slow.current.value

        if self.in_trade:
            self.bars_held += 1
            if self.bars_held > self.max_hold_bars:
                self.close_on_time()
            self.prev_fast, self.prev_slow = fast, slow
            return

        if self.prev_fast is None:
            self.prev_fast, self.prev_slow = fast, slow
            return

        bull = self.prev_fast <= self.prev_slow and fast > slow
        bear = self.prev_fast >= self.prev_slow and fast < slow
        self.prev_fast, self.prev_slow = fast, slow

        if not (bull or bear):
            return

        trend = self.trend_ema.current.value
        if self.use_trend_filter:
            if bull and bar.close <= trend:
                return
            if bear and bar.close >= trend:
                return

        self.try_enter(bar, +1 if bull else -1)

    # -----------------------------------------------------------------------
    def update_pivots(self):
        need = self.pivot_left + self.pivot_right + 1
        if len(self.window) < need:
            return
        cand = self.window[-(self.pivot_right + 1)]
        left = self.window[-need:-(self.pivot_right + 1)]
        right = self.window[-self.pivot_right:]
        if all(cand.low < b.low for b in left) and all(cand.low < b.low for b in right):
            self.last_swing_low = cand.low
        if all(cand.high > b.high for b in left) and all(cand.high > b.high for b in right):
            self.last_swing_high = cand.high

    # -----------------------------------------------------------------------
    def try_enter(self, bar, direction):
        atr = self.atr.current.value
        recent = self.window[-self.fallback_look:]

        if direction > 0:
            stop = self.last_swing_low if self.last_swing_low is not None \
                else min(b.low for b in recent)
        else:
            stop = self.last_swing_high if self.last_swing_high is not None \
                else max(b.high for b in recent)

        risk = abs(bar.close - stop)
        if risk < self.min_risk_atr * atr or risk > self.max_risk_atr * atr:
            self.skipped_risk += 1
            return

        equity = self.portfolio.total_portfolio_value
        risk_money_leg = equity * (self.risk_per_signal_pct / 100.0) / 3.0
        qty_leg = round(risk_money_leg / risk, 2)
        if qty_leg < 0.01:
            self.skipped_size += 1
            return

        if (qty_leg * 3.0 * bar.close) > (equity * self.max_gross_leverage):
            self.skipped_leverage += 1
            return

        self.reset_trade()
        self.direction = direction
        self.risk_distance = risk
        self.risk_money_leg = risk_money_leg
        self.stop_price = stop
        self.legs = [
            Leg("L1", qty_leg, bar.close + direction * risk * 1.0, 1.0),
            Leg("L2", qty_leg, bar.close + direction * risk * 2.0, 2.0),
            Leg("L3", qty_leg, bar.close + direction * risk * 3.0, 3.0),
        ]
        self.in_trade = True
        self.total_signals += 1
        self.entry_ticket = self.market_order(self.symbol, direction * qty_leg * 3.0)

    # -----------------------------------------------------------------------
    def place_exits(self):
        d = self.direction
        for leg in self.legs:
            leg.stop_ticket = self.stop_market_order(
                self.symbol, -d * leg.quantity, self.stop_price)
            leg.limit_ticket = self.limit_order(
                self.symbol, -d * leg.quantity, leg.target)

    # -----------------------------------------------------------------------
    def move_to_break_even(self):
        # Break-even sits one spread inside profit: a long fills at the ask and
        # exits at the bid, so a stop at the entry price returns minus a spread.
        self.be_level = self.entry_price + self.direction * self.spread_price
        for leg in self.legs[1:]:
            if leg.closed or leg.stop_ticket is None:
                continue
            fields = UpdateOrderFields()
            fields.stop_price = self.be_level
            leg.stop_ticket.update(fields)

    # -----------------------------------------------------------------------
    def close_on_time(self):
        open_legs = 0
        for leg in self.legs:
            if leg.closed:
                continue
            if leg.stop_ticket is not None:
                leg.stop_ticket.cancel()
            if leg.limit_ticket is not None:
                leg.limit_ticket.cancel()
            leg.outcome = "TIME"
            open_legs += 1
        self.time_stopping = True
        self.time_stop_legs = open_legs
        if open_legs and self.portfolio[self.symbol].invested:
            self.liquidate(self.symbol)
        else:
            self.finalise_signal()

    # -----------------------------------------------------------------------
    def on_order_event(self, order_event):
        if order_event.status != OrderStatus.FILLED:
            return
        if not self.in_trade:
            return

        oid = order_event.order_id

        if self.entry_ticket is not None and oid == self.entry_ticket.order_id:
            self.entry_price = order_event.fill_price
            self.entry_fee = order_event.order_fee.value.amount
            self.place_exits()
            return

        if self.time_stopping:
            is_leg_order = any(
                (l.stop_ticket is not None and oid == l.stop_ticket.order_id) or
                (l.limit_ticket is not None and oid == l.limit_ticket.order_id)
                for l in self.legs)
            if not is_leg_order:
                fee = order_event.order_fee.value.amount
                qty = abs(order_event.fill_quantity)
                gross = ((order_event.fill_price - self.entry_price)
                         * self.direction * qty)
                share = self.entry_fee * self.time_stop_legs / 3.0
                self.signal_pnl += gross - fee - share
                self.finalise_signal()
                return

        for leg in self.legs:
            hit_stop = leg.stop_ticket is not None and oid == leg.stop_ticket.order_id
            hit_limit = leg.limit_ticket is not None and oid == leg.limit_ticket.order_id
            if not (hit_stop or hit_limit):
                continue

            if leg.closed:
                # Both sides of a pair filled inside the same minute before the
                # cancel landed. Counted so it cannot pass unnoticed.
                self.double_fills += 1
                return

            sibling = leg.limit_ticket if hit_stop else leg.stop_ticket
            if sibling is not None:
                sibling.cancel()

            leg.closed = True
            leg.exit_price = order_event.fill_price
            fee = order_event.order_fee.value.amount
            gross = (leg.exit_price - self.entry_price) * self.direction * leg.quantity
            self.signal_pnl += gross - fee - (self.entry_fee / 3.0)

            if hit_limit:
                leg.outcome = "TP"
                if leg.name == "L1":
                    self.tp1_hit = True
                    self.move_to_break_even()
            elif self.tp1_hit and leg.name != "L1":
                leg.outcome = "BE"
            else:
                leg.outcome = "SL"
            break

        if all(l.closed or l.outcome == "TIME" for l in self.legs):
            self.finalise_signal()

    # -----------------------------------------------------------------------
    def finalise_signal(self):
        if not self.in_trade:
            return
        for leg in self.legs:
            if leg.outcome:
                self.leg_stats[leg.name][leg.outcome] += 1
        self.signal_r.append(self.signal_pnl / self.risk_money_leg)
        self.signal_dir.append(self.direction)
        self.reset_trade()

    # -----------------------------------------------------------------------
    def on_end_of_algorithm(self):
        if self.portfolio[self.symbol].invested:
            self.liquidate(self.symbol)

        def block(label, rs):
            n = len(rs)
            if n == 0:
                self.log(f"{label:<10} no completed signals")
                return
            mean = sum(rs) / n
            if n > 1:
                var = sum((x - mean) ** 2 for x in rs) / (n - 1)
                sd = math.sqrt(var)
                t = mean / (sd / math.sqrt(n)) if sd > 0 else float("nan")
                need = (2.0 * sd / mean) ** 2 if mean != 0 else float("inf")
            else:
                sd, t, need = float("nan"), float("nan"), float("inf")
            wins = sum(1 for x in rs if x > 0)
            self.log(f"{label:<10} n={n:<5} E={mean:+.4f}R  sd={sd:.2f}R  "
                     f"t={t:+.2f}  win={100.0*wins/n:.1f}%  "
                     f"n for t=2.0: {need:.0f}")

        self.log("=" * 74)
        self.log(f"DOBBY 3-LEG  XAUUSD  {self.START[0]}-{self.START[1]:02d}-{self.START[2]:02d}"
                 f" to {self.END[0]}-{self.END[1]:02d}-{self.END[2]:02d}")
        self.log(f"spread charged {self.spread_price} price units per round trip per leg")
        self.log(f"risk {self.risk_per_signal_pct}% per signal, constant money per R")
        self.log("-" * 74)
        self.log(f"signals taken {self.total_signals}   "
                 f"skipped: risk-band {self.skipped_risk}, "
                 f"leverage {self.skipped_leverage}, min-size {self.skipped_size}")
        for name in ("L1", "L2", "L3"):
            s = self.leg_stats[name]
            self.log(f"  {name}  TP {s['TP']:<4} SL {s['SL']:<4} "
                     f"BE {s['BE']:<4} TIME {s['TIME']}")
        if self.double_fills:
            self.log(f"  WARNING stop and limit both filled on {self.double_fills} leg(s)")
        self.log("-" * 74)
        block("ALL", self.signal_r)
        block("LONG", [r for r, d in zip(self.signal_r, self.signal_dir) if d > 0])
        block("SHORT", [r for r, d in zip(self.signal_r, self.signal_dir) if d < 0])
        self.log("-" * 74)
        if self.first_price and self.last_price:
            bh = 100.0 * (self.last_price / self.first_price - 1.0)
            self.log(f"buy and hold over the same window: {bh:+.1f}%   "
                     f"(a long-only rule inherits this; it is not timing skill)")
        self.log(f"total R across all signals: {sum(self.signal_r):+.1f}R")
        self.log("VERDICT: an edge needs t > 2.0 on the side you intend to trade.")
        self.log("=" * 74)
