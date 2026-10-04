#!/usr/bin/env python3
"""The real account: Exness-MT5Trial25, XAUUSDc, Standard Cent, 500 USC.

THE NUMBER I GOT WRONG, AND WHAT IT ACTUALLY IS

  The supplied spec said "Contract size: 1". I assumed that had to be a
  misreading, because the same message said 0.01 lot costs about 0.26 USC at
  a 260-point spread, and 0.260 x 1 x 0.01 = 0.0026, a hundred times smaller.
  I resolved it to 100 and said so.

  THE TERMINAL SCREENSHOT SETTLES IT: contract size really is 1. Both figures
  were right and my explanation was wrong. The factor of 100 is not the
  contract - it is the CENT ACCOUNT:

      contract size          1 oz per lot          (per the terminal)
      profit currency        USD                   (per the terminal)
      account currency       USC, i.e. US cents    1 USD = 100 USC

      0.01 lot = 0.01 oz
      gold moves 1.000  ->  0.01 oz x $1 = $0.01  =  1.00 USC
      spread 0.260      ->  0.260 x 0.01 oz = $0.0026 = 0.26 USC   <- the anchor

  So the money value of one price unit, per lot, IN ACCOUNT CURRENCY is
      contract_size x usd_to_account = 1 x 100 = 100 USC
  which is the number the engine needs and is what every table already used.
  The arithmetic in this repo was correct throughout; only the reason given
  for it was not, and that is corrected here rather than quietly left.

UNITS, STATED ONCE

  digits = 3, tick size = 0.001, so ONE POINT = 0.001 PRICE UNITS.
  A 260-point spread is 0.260 in gold price terms (26 US cents of gold).

  value of one price unit, per lot   = 100 USC   (= 1 oz x 100 cents/USD)
  value of one point, per lot        = 0.1 USC
  value of one point, at 0.01 lot    = 0.001 USC

  Account currency is USC (cents). 500 USC is 5.00 USD of real money.

CONFIRMED FROM THE TERMINAL
  digits 3, contract size 1, min volume 0.01, max volume 200, volume step
  0.01, swap type "in points", swap long -534.9, swap short 0, stop level 0,
  floating spread, chart mode BY BID PRICE, margin currency XAU, profit
  currency USD, market execution, fill policy FOK/IOC.

STILL ASSUMED, BECAUSE THE TERMINAL DID NOT SHOW IT
  leverage        1:500 assumed. The spec page does not list it. Margin is
                  small relative to the risk budgets tested here, so it binds
                  rarely - but it is an assumption and it is flagged in every
                  table.
  rollover time   21:00 UTC (00:00 server, GMT+3).
  slippage        every slippage figure. No tick-level fill study exists here.
  data source     Dukascopy bid/ask 2004-2026, whose median spread is 377
                  points - WIDER than the 260 the terminal shows now, so the
                  260-point scenario is the optimistic one, not the base case.
  bid vs mid      the terminal charts BY BID; this study's OHLC is mid, with
                  the spread applied around it. For a symmetric spread the
                  two differ by half a spread on the level, not on the P&L.
"""
from dataclasses import dataclass, replace

POINT = 0.001                  # digits = 3, tick size = 0.001

@dataclass(frozen=True)
class ExnessCent:
    """The account as supplied, in the units the engine works in."""
    name: str = "Exness-MT5Trial25 / XAUUSDc / Standard Cent"
    currency: str = "USC"
    balance: float = 500.0                 # USC (= 5.00 USD)
    # The engine needs MONEY PER PRICE UNIT PER LOT, in account currency.
    # That is contract_size (1 oz, per the terminal) x 100 cents per USD.
    # Kept as one number because every downstream formula wants the product,
    # with the two factors named separately below so the 100 is never again
    # mistaken for the contract size.
    contract_oz: float = 1.0               # per the terminal
    usd_to_account: float = 100.0          # USC per USD (cent account)
    contract_size: float = 100.0           # = contract_oz * usd_to_account
    min_lot: float = 0.01
    lot_step: float = 0.01                 # ASSUMED equal to min_lot
    max_lot: float = 200.0                 # per the terminal
    leverage: float = 500.0                # ASSUMED - the spec page omits it
    digits: int = 3
    tick_size: float = 0.001
    commission_per_lot_side: float = 0.0   # supplied: commission = 0
    swap_long_points: float = -534.9       # per lot, per night
    swap_short_points: float = 0.0
    spread_points_live: float = 260.0      # what the terminal shows now

    # ---- conversions -----------------------------------------------------
    def px(self, points):
        """points -> price units."""
        return points * POINT

    def money_per_price_unit(self, lots):
        """USC earned per 1.000 of gold price move."""
        return self.contract_size * lots

    def cost_round_trip(self, spread_points, lots, slip_points=0.0):
        """Total USC paid to open and close, at this spread and slippage.

        The spread is crossed ONCE (buy the ask, sell the bid), so it is
        charged once in full, not twice. Slippage is applied on BOTH sides."""
        spread_cost = self.px(spread_points) * self.contract_size * lots
        slip_cost = 2.0 * self.px(slip_points) * self.contract_size * lots
        comm = 2.0 * self.commission_per_lot_side * lots
        return spread_cost + slip_cost + comm

    def min_risk_price_units(self, spread_points, slip_points=0.0,
                             multiple=3.0):
        """Rule 10: a signal is only eligible if its risk is at least
        `multiple` times the total round-trip cost.

        Expressed in PRICE UNITS, which makes it lot-independent: both risk
        and cost scale linearly with lots, so the ratio does not."""
        cost_px = self.px(spread_points) + 2.0 * self.px(slip_points)
        comm_px = (2.0 * self.commission_per_lot_side /
                   self.contract_size) if self.contract_size else 0.0
        return multiple * (cost_px + comm_px)

    def swap_per_lot_night(self, direction):
        """USC per lot per night, signed (negative = the position pays)."""
        pts = self.swap_long_points if direction > 0 else self.swap_short_points
        return self.px(pts) * self.contract_size

    def lots_for_risk(self, risk_money, risk_price_units):
        """Unrounded lot size. Rounding and the minimum-lot floor happen in
        the portfolio engine, which is where rejections get counted."""
        denom = risk_price_units * self.contract_size
        return (risk_money / denom) if denom > 0 else 0.0

    def min_lot_risk_money(self, risk_price_units):
        """The SMALLEST amount of money that can be put at risk on a trade
        with this stop distance, because 0.01 lot is the smallest deal.

        This is the number that decides whether a 500 USC account can trade a
        setup at all: if 0.01 lot already risks more than the risk budget,
        the trade is rejected, and no amount of 'risking less' can fix it."""
        return risk_price_units * self.contract_size * self.min_lot

    def describe(self):
        L = []
        L.append(f"{self.name}")
        L.append(f"  balance            {self.balance:,.0f} {self.currency} "
                 f"(= {self.balance/100:,.2f} USD)")
        L.append(f"  contract size      {self.contract_oz:g} oz/lot "
                 f"(confirmed in the terminal)")
        L.append(f"  account conversion 1 USD = {self.usd_to_account:g} USC "
                 f"(cent account) -> {self.contract_size:g} USC per price "
                 f"unit per lot")
        L.append(f"  min / step / max   {self.min_lot} / {self.lot_step} / "
                 f"{self.max_lot:g} (confirmed in the terminal)")
        L.append(f"  leverage           1:{self.leverage:g} (ASSUMED - not supplied)")
        L.append(f"  digits / tick      {self.digits} / {self.tick_size} "
                 f"-> 1 point = {POINT} price units")
        L.append(f"  commission         {self.commission_per_lot_side} per lot per side")
        L.append(f"  swap long          {self.swap_long_points:+.1f} points/lot/night "
                 f"= {self.swap_per_lot_night(+1):+.2f} {self.currency}/lot/night")
        L.append(f"  swap short         {self.swap_short_points:+.1f} points/lot/night "
                 f"= {self.swap_per_lot_night(-1):+.2f} {self.currency}/lot/night")
        L.append(f"  live spread        {self.spread_points_live:g} points "
                 f"= {self.px(self.spread_points_live):.3f} price units")
        return "\n".join(L)

# The three spread scenarios asked for, in points.
SPREAD_SCENARIOS = {"normal": 260.0, "stress": 400.0, "high": 600.0}

# Slippage as a MULTIPLE OF THE SPREAD, as asked. 0.1 x 260 = 26 points.
SLIPPAGE_MULTIPLES = (0.0, 0.1, 0.3)

# Risk per trade, as a fraction of live equity.
RISK_LEVELS = (0.005, 0.01, 0.02, 0.03, 0.05, 0.07, 0.10)

# Drawdown ceilings used to filter candidates.
DD_LIMITS = (0.20, 0.30, 0.35, 0.50, 0.70)

def slip_points(spread_points, multiple):
    return spread_points * multiple
