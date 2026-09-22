"""Demo-only execution for the three fixed payoff sleeves.

The module does not search or retune parameters.  It evaluates only the three
frozen M15-to-M5 rules below and, when explicitly launched with ``--live``,
sends a protected market order to the verified MT5 demo account.  Its default
mode is dry-run.
"""
from __future__ import annotations

import argparse
import json
import math
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import current_edge as ce
import payoff_shape_search as ps


SYMBOL = "XAUUSD"
MAGIC = 20260923
COMMENT = "PAYOFF_DEMO_A20"
STATE_FILE = Path("data/payoff_demo_autotrader_state.json")
LOG_FILE = Path("data/payoff_demo_autotrader_log.json")
POLL_SECONDS = 15
MAX_DD = 0.40
MAX_SPREAD = 0.135             # 1.5x the 90-point demo-account spread
DEVIATION_POINTS = 100
MAX_LOG_ROWS = 1_000


@dataclass(frozen=True)
class Sleeve:
    name: str
    family: str
    flip: bool
    stop_atr: float
    target_r: float
    time_bars: int
    risk_fraction: float


# Fixed on 2026-09-22.  A/B/C are not re-optimised by this program.
SLEEVES = (
    Sleeve("A_breakout_flip_5R", "crowded:breakout_into_level", True,
           1.0, 5.0, 144, 0.020),
    Sleeve("B_gap_follow_1R", "crowded:gap_continuation", False,
           3.0, 1.0, 144, 0.023),
    Sleeve("C_vwap_flip_8R", "core:S5V1:VWAP reversion 2.5sd", True,
           1.0, 8.0, 144, 0.020),
)


def _utc(ts: int | float | None = None) -> str:
    return datetime.fromtimestamp(time.time() if ts is None else ts,
                                  timezone.utc).isoformat(timespec="seconds")


def _read_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def _write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def _record(state: dict, kind: str, **fields) -> None:
    rows = _read_json(LOG_FILE, [])
    rows.append({"utc": _utc(), "kind": kind, **fields})
    _write_json(LOG_FILE, rows[-MAX_LOG_ROWS:])
    state["last_event"] = {"utc": _utc(), "kind": kind, **fields}


def _raw90_cost_mode() -> None:
    """Use recorded 90-point spread + raw commission, never the 260-point account."""
    ce.SPREAD_STANDARD = 0.0


def _health(rows: list[ps.Row], now: int) -> tuple[bool, dict]:
    m30 = ps._metrics(ps._window(rows, now, 30))
    m60 = ps._metrics(ps._window(rows, now, 60))
    m90 = ps._metrics(ps._window(rows, now, 90))
    ready = bool(m30 and m60 and m90
                 and m90["trades"] >= 20 and m30["trades"] >= 5
                 and m30["mean_R"] > 0 and m60["mean_R"] > 0
                 and m90["mean_R"] > 0 and m90["stress_mean_R"] > 0)
    return ready, {"m30": m30, "m60": m60, "m90": m90}


def current_signals() -> tuple[list[dict], str]:
    """Return only signals whose exact next-M5-open entry is still available."""
    _raw90_cost_mode()
    b5, b15, nxt, atr, profile, events, last_closed, now, source = ps._load_context()
    latest_i = len(b15) - 1
    k = int(nxt[latest_i])
    if not ce._entry_is_actionable(now, b5, k):
        return [], f"entry window is closed or unavailable (k={k})"

    signals = []
    for sleeve in SLEEVES:
        rows = ps._eval(events[sleeve.family], sleeve.flip, b15, b5, nxt, atr,
                        profile, last_closed, sleeve.stop_atr, sleeve.target_r,
                        sleeve.time_bars)
        ready, health = _health(rows, now)
        if not ready:
            continue
        dirs = [d for i, d in events[sleeve.family] if i == latest_i]
        if not dirs:
            continue
        direction = -dirs[-1] if sleeve.flip else dirs[-1]
        unit_risk = sleeve.stop_atr * float(atr[latest_i])
        if not np.isfinite(unit_risk) or unit_risk <= 0:
            continue
        signals.append({
            "sleeve": sleeve.name,
            "direction": int(direction),
            "risk_distance": unit_risk,
            "target_r": sleeve.target_r,
            "risk_fraction": sleeve.risk_fraction,
            "entry_bar_utc": _utc(int(b5.t[k])),
            "entry_epoch": int(b5.t[k]),
            "expiry_epoch": int(b5.t[k] + sleeve.time_bars * b5.step),
            "health": health,
            "source": source,
        })
    return signals, "ok"


def _normalise_volume(volume: float, info) -> float | None:
    step = float(info.volume_step)
    minimum = float(info.volume_min)
    maximum = float(info.volume_max)
    if step <= 0 or volume < minimum:
        return None
    units = math.floor((min(volume, maximum) + 1e-12) / step)
    result = round(units * step, 8)
    return result if result >= minimum else None


def _managed_positions(mt5):
    positions = mt5.positions_get(symbol=SYMBOL) or ()
    return [p for p in positions if int(getattr(p, "magic", 0)) == MAGIC]


def _close_position(mt5, position, reason: str, state: dict, dry_run: bool) -> bool:
    tick = mt5.symbol_info_tick(SYMBOL)
    if tick is None:
        _record(state, "close_rejected", reason="no quote", ticket=position.ticket)
        return False
    is_buy = int(position.type) == mt5.POSITION_TYPE_BUY
    request = {
        "action": mt5.TRADE_ACTION_DEAL, "symbol": SYMBOL,
        "volume": float(position.volume),
        "type": mt5.ORDER_TYPE_SELL if is_buy else mt5.ORDER_TYPE_BUY,
        "position": int(position.ticket), "price": tick.bid if is_buy else tick.ask,
        "deviation": DEVIATION_POINTS, "magic": MAGIC,
        "comment": f"{COMMENT}_{reason}",
        "type_time": mt5.ORDER_TIME_GTC, "type_filling": mt5.ORDER_FILLING_IOC,
    }
    if dry_run:
        _record(state, "dry_run_close", reason=reason, request=request)
        return True
    result = mt5.order_send(request)
    ok = result is not None and result.retcode == mt5.TRADE_RETCODE_DONE
    _record(state, "close", reason=reason, ok=ok, request=request,
            retcode=None if result is None else int(result.retcode),
            fill=None if result is None else float(result.price))
    return ok


def _check_drawdown(mt5, state: dict, dry_run: bool) -> bool:
    account = mt5.account_info()
    if account is None:
        _record(state, "halt", reason="account info unavailable")
        state["halted"] = True
        return False
    equity = float(account.equity)
    peak = max(float(state.get("peak_equity", equity)), equity)
    state["peak_equity"] = peak
    state.setdefault("start_equity", equity)
    dd = max(0.0, (peak - equity) / peak) if peak > 0 else 1.0
    state["drawdown_fraction"] = dd
    if state.get("halted") or dd >= MAX_DD:
        state["halted"] = True
        for position in _managed_positions(mt5):
            _close_position(mt5, position, "DD_HALT", state, dry_run)
        _record(state, "halt", reason="drawdown limit", dd_fraction=dd,
                peak_equity=peak, equity=equity)
        return False
    return True


def _send_signal(mt5, signal: dict, state: dict, dry_run: bool) -> None:
    info = mt5.symbol_info(SYMBOL)
    tick = mt5.symbol_info_tick(SYMBOL)
    if info is None or tick is None or tick.ask <= 0 or tick.bid <= 0:
        _record(state, "rejected", reason="symbol or quote unavailable", signal=signal)
        return
    spread = float(tick.ask - tick.bid)
    if spread > MAX_SPREAD:
        _record(state, "rejected", reason="spread above safety limit", spread=spread,
                signal=signal)
        return
    is_buy = signal["direction"] > 0
    entry = float(tick.ask if is_buy else tick.bid)
    stop = entry - signal["direction"] * signal["risk_distance"]
    target = entry + signal["direction"] * signal["target_r"] * signal["risk_distance"]
    order_type = mt5.ORDER_TYPE_BUY if is_buy else mt5.ORDER_TYPE_SELL
    min_volume = float(info.volume_min)
    loss_at_min = mt5.order_calc_profit(order_type, SYMBOL, min_volume, entry, stop)
    account = mt5.account_info()
    if loss_at_min is None or loss_at_min >= 0 or account is None:
        _record(state, "rejected", reason="cannot calculate protected risk", signal=signal)
        return
    risk_cash = float(account.equity) * signal["risk_fraction"]
    volume = _normalise_volume(risk_cash / abs(float(loss_at_min)) * min_volume, info)
    if volume is None:
        _record(state, "rejected", reason="minimum lot exceeds intended risk",
                risk_cash=risk_cash, loss_at_min=float(loss_at_min), signal=signal)
        return
    request = {
        "action": mt5.TRADE_ACTION_DEAL, "symbol": SYMBOL, "volume": volume,
        "type": order_type, "price": entry, "sl": stop, "tp": target,
        "deviation": DEVIATION_POINTS, "magic": MAGIC, "comment": COMMENT,
        "type_time": mt5.ORDER_TIME_GTC, "type_filling": mt5.ORDER_FILLING_IOC,
    }
    key = f"{signal['sleeve']}|{signal['entry_epoch']}"
    if dry_run:
        _record(state, "dry_run_order", key=key, request=request, signal=signal,
                intended_risk_cash=risk_cash, spread=spread)
        return
    result = mt5.order_send(request)
    ok = result is not None and result.retcode == mt5.TRADE_RETCODE_DONE
    _record(state, "order", key=key, ok=ok, request=request, signal=signal,
            intended_risk_cash=risk_cash, spread=spread,
            retcode=None if result is None else int(result.retcode),
            fill=None if result is None else float(result.price),
            deal=None if result is None else int(result.deal))
    if ok:
        state.setdefault("seen", []).append(key)
        # A market deal's order id is not necessarily its position ticket on a
        # netting account, so resolve the live position rather than guessing.
        expiries = state.setdefault("managed_expiry", {})
        for position in _managed_positions(mt5):
            expiries[str(position.ticket)] = signal["expiry_epoch"]


def run_once(dry_run: bool) -> dict:
    import MetaTrader5 as mt5
    if not mt5.initialize():
        raise RuntimeError(f"MT5 initialize failed: {mt5.last_error()}")
    try:
        account = mt5.account_info()
        if account is None or account.trade_mode != mt5.ACCOUNT_TRADE_MODE_DEMO:
            raise RuntimeError("refusing to trade: account is not verified DEMO")
        state = _read_json(STATE_FILE, {"seen": [], "halted": False})
        state.setdefault("seen", [])
        state["updated_utc"] = _utc()
        state["mode"] = "DRY_RUN" if dry_run else "LIVE_DEMO"
        if not _check_drawdown(mt5, state, dry_run):
            _write_json(STATE_FILE, state)
            return state
        now_epoch = int(time.time())
        for position in _managed_positions(mt5):
            expiry = state.get("managed_expiry", {}).get(str(position.ticket))
            if expiry is not None and now_epoch >= int(expiry):
                _close_position(mt5, position, "TIME_EXIT", state, dry_run)
        # Preserve the demo protocol: never add or compete with any open position.
        if mt5.positions_total():
            _record(state, "skip", reason="an MT5 position is already open")
            _write_json(STATE_FILE, state)
            return state
        signals, reason = current_signals()
        state["scan_reason"] = reason
        state["signals_found"] = len(signals)
        for signal in signals:
            key = f"{signal['sleeve']}|{signal['entry_epoch']}"
            if key not in state["seen"]:
                _send_signal(mt5, signal, state, dry_run)
                break                 # hard one-position limit
        if not signals:
            _record(state, "no_trade", reason=reason)
        state["seen"] = state["seen"][-500:]
        _write_json(STATE_FILE, state)
        return state
    finally:
        mt5.shutdown()


def main() -> int:
    parser = argparse.ArgumentParser(description="Fixed-payoff XAUUSD demo autotrader")
    parser.add_argument("--live", action="store_true", help="permit DEMO order_send")
    parser.add_argument("--loop", action="store_true", help="poll continuously")
    parser.add_argument("--poll-seconds", type=int, default=POLL_SECONDS)
    args = parser.parse_args()
    if args.poll_seconds < 5:
        raise SystemExit("poll interval must be at least 5 seconds")
    while True:
        state = run_once(dry_run=not args.live)
        print(json.dumps({k: state.get(k) for k in (
            "mode", "halted", "drawdown_fraction", "scan_reason", "signals_found", "last_event"
        )}, ensure_ascii=False))
        if not args.loop:
            return 0
        time.sleep(args.poll_seconds)


if __name__ == "__main__":
    raise SystemExit(main())
