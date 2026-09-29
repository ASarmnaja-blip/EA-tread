"""Tests for the frozen hole-closing rules. Synthetic only; no market data."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import riskrules as RR  # noqa: E402


def test_breaker_needs_minimum_bars():
    # variance already 10x the pace, but only 5 bars in: must not trip
    assert not RR.breaker_tripped(1e6, 5, 1e5)
    assert RR.breaker_tripped(1e6, 30, 1e5)


def test_breaker_threshold_is_the_frozen_class_edge():
    f = 115_000.0                      # forecast weekly variance
    n = 23                             # bars elapsed
    pace = f * n / RR.BARS_PER_WEEK
    assert not RR.breaker_tripped(pace * 1.49, n, f)
    assert RR.breaker_tripped(pace * 1.51, n, f)
    assert RR.BREAKER_K == 1.5          # same edge as NORMAL -> HIGH in spec v2


def test_breaker_silent_without_a_forecast():
    for bad in (np.nan, 0.0, -1.0):
        assert not RR.breaker_tripped(1e9, 100, bad)


def test_weekend_rules_only_reduce():
    # p99 gap of 175 bp at $4,300 costs $75.3 per 0.01 lot; a $100 budget
    # therefore allows 0.01 lot and no more
    lots = RR.weekend_max_lots(100.0, 4300.0)
    assert lots == 0.01
    assert RR.weekend_max_lots(10.0, 4300.0) == 0.0       # budget too small -> no carry
    assert RR.weekend_max_lots(1000.0, 4300.0) > lots     # bigger budget, bigger cap
    assert RR.weekend_hold_allowed("NORMAL") and RR.weekend_hold_allowed("CALM")
    assert not RR.weekend_hold_allowed("HIGH")
    assert not RR.weekend_hold_allowed("EXTREME")


def test_news_rule_refuses_tight_stops():
    assert not RR.news_hold_allowed(50.0)                  # ordinary stop: refused
    assert not RR.news_hold_allowed(RR.NEWS_JUMP_P95_BP - 0.1)
    assert RR.news_hold_allowed(RR.NEWS_JUMP_P95_BP + 0.1)
    assert not RR.news_hold_allowed(np.nan)


def test_tier1_window():
    ev = [(100, "Nonfarm Payrolls"), (200, "Initial Jobless Claims"), (300, "CPI m/m")]
    assert RR.tier1_in_window(ev, 0, 250) == ["Nonfarm Payrolls"]
    assert RR.tier1_in_window(ev, 0, 400) == ["Nonfarm Payrolls", "CPI m/m"]
    assert RR.tier1_in_window(ev, 150, 250) == []


def test_broker_specs_measured_and_stopout_is_zero_equity():
    # Read from MT5 on 2026-09-29: 1:2000, stop-out 0%, margin call 30%.
    assert RR.LEVERAGE == 2000 and RR.STOP_OUT_PCT == 0.0
    assert RR.frozen()
    # 0.03 lot at $4,133 needs $6.20 margin -- margin is never the binding
    # constraint here; a 0% stop-out means liquidation at zero equity.
    assert abs(RR.margin_required(0.03, 4132.885) - 6.20) < 0.01
    assert RR.stopped_out(-1.0, 0.1, 4300.0)
    assert RR.stopped_out(0.0, 0.1, 4300.0)
    assert not RR.stopped_out(0.01, 0.1, 4300.0)     # any positive equity survives
    assert not RR.stopped_out(5000.0, 0.1, 4300.0)
    # a broker with a 50% stop-out would bite far earlier on the same position
    assert RR.stopped_out(10.0, 0.1, 4300.0, leverage=2000, so_pct=50.0)
    assert not RR.stopped_out(20.0, 0.1, 4300.0, leverage=2000, so_pct=50.0)


def test_floor_lot():
    assert RR.floor_lot(0.0349) == 0.03
    assert RR.floor_lot(0.009) == 0.0
    assert RR.floor_lot(-5) == 0.0


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn(); print("ok", name)
