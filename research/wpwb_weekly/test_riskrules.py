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


def test_margin_falls_back_safely_while_unmeasured():
    # LEVERAGE / STOP_OUT_PCT are not measured yet: the code must not invent
    # them, and must fall back to the old zero-equity rule.
    assert RR.LEVERAGE is None and RR.STOP_OUT_PCT is None
    assert not RR.frozen()
    assert np.isnan(RR.margin_required(0.1, 4300.0))
    assert RR.stopped_out(-1.0, 0.1, 4300.0)
    assert not RR.stopped_out(5000.0, 0.1, 4300.0)
    # with specs supplied, the margin-level rule bites before equity hits zero
    # 0.1 lot at $4,300 with 1:2000 needs $21.50 margin; 50% stop-out bites at $10.75
    assert RR.stopped_out(10.0, 0.1, 4300.0, leverage=2000, so_pct=50.0)
    assert not RR.stopped_out(20.0, 0.1, 4300.0, leverage=2000, so_pct=50.0)
    assert not RR.stopped_out(5000.0, 0.1, 4300.0, leverage=2000, so_pct=50.0)


def test_floor_lot():
    assert RR.floor_lot(0.0349) == 0.03
    assert RR.floor_lot(0.009) == 0.0
    assert RR.floor_lot(-5) == 0.0


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn(); print("ok", name)
