"""Fast Amendment 27 audits.  These tests never connect to MT5."""
from __future__ import annotations

import json
import os
from pathlib import Path
from types import SimpleNamespace

import numpy as np

import a27_forward as F
import data as D


def bars(n: int = 12) -> D.Bars:
    t = np.arange(n, dtype=np.int64) * 300
    o = np.full(n, 100.0)
    h = np.full(n, 100.3)
    l = np.full(n, 99.7)
    c = np.full(n, 100.0)
    v = np.ones(n)
    sp = np.full(n, 0.090)
    return D.Bars(t, o, h, l, c, v, 300, "XAUUSD", sp)


def test_clarification_a_shadow_uses_only_prior_bar_spread():
    risk = 4.0
    a = F.shadow_gate(0.090, risk, live_spread_diagnostic=0.500)
    b = F.shadow_gate(0.090, risk, live_spread_diagnostic=0.001)
    assert a["passed"] == b["passed"]
    assert a["friction_r"] == b["friction_r"]
    assert a["source"] == "ingested_M5_sp[k-1]"


def test_shadow_demo_disagreement_does_not_change_shadow():
    event = {"event_id": "x", "risk": 4.0, "direction": 1,
             "target_r": 1.0, "weight": 0.2}
    shadow = F.shadow_gate(0.090, event["risk"], 0.500)
    before = F.object_hash(event)
    demo = F.dry_demo_evaluate(event, 0.500)
    assert shadow["passed"]
    assert not demo["demo_gate"]["passed"]
    assert demo["shadow_unchanged"]
    assert F.object_hash(event) == before


def test_prefix_digest_is_future_invariant_and_prefix_mutation_is_caught():
    original = bars(10)
    changed_future = bars(10)
    changed_future.c[8:] += 7.0
    cutoff = 8 * 300
    assert F.prefix_digest(original, cutoff) == F.prefix_digest(changed_future, cutoff)
    changed_past = bars(10)
    changed_past.c[2] += 1.0
    assert F.prefix_digest(original, cutoff) != F.prefix_digest(changed_past, cutoff)
    try:
        F.assert_prefix_unchanged(original, changed_past)
    except F.A27Error:
        pass
    else:
        raise AssertionError("past bar mutation was not caught")


def test_bar_duplicate_gap_and_content_hash_checks():
    good = bars(8)
    assert F.bar_quality(good, grandfather_history=False)["passed"]
    duplicate = bars(8)
    duplicate.t[4] = duplicate.t[3]
    try:
        F.bar_quality(duplicate)
    except ValueError:
        pass
    else:
        raise AssertionError("duplicate timestamp was not rejected")
    gap = bars(8)
    gap.t[5:] += 300
    assert not F.bar_quality(gap, extension_start=5)["passed"]
    assert F.object_hash({"code": "a"}) != F.object_hash({"code": "b"})


def test_sealed_record_and_event_ledgers_detect_tampering():
    root = Path("data")
    token = f"a27_test_{os.getpid()}"
    record_path = root / f"{token}_decision.json"
    ledger = root / f"{token}_events.jsonl"
    for p in (record_path, ledger, record_path.with_suffix(".json.tmp")):
        if p.exists(): p.unlink()
    try:
        row = F.seal_record({"schema": F.SCHEMA, "value": 1}, record_path, "GENESIS")
        assert F.verify_record(record_path, "GENESIS")["record_hash"] == row["record_hash"]
        bad = json.loads(record_path.read_text(encoding="utf-8"))
        bad["value"] = 2
        record_path.write_text(json.dumps(bad), encoding="utf-8")
        try:
            F.verify_record(record_path)
        except F.A27Error:
            pass
        else:
            raise AssertionError("decision tampering was not caught")

        F.append_event(ledger, "decision", "signal", {"x": 1}, 1000)
        F.append_event(ledger, "decision", "exit", {"x": 2}, 1100)
        lines = ledger.read_text(encoding="utf-8").splitlines()
        first = json.loads(lines[0]); first["payload"]["x"] = 9
        lines[0] = json.dumps(first)
        ledger.write_text("\n".join(lines) + "\n", encoding="utf-8")
        try:
            F.append_event(ledger, "decision", "correction", {}, 1200)
        except F.A27Error:
            pass
        else:
            raise AssertionError("event-ledger tampering was not caught")
    finally:
        for p in (record_path, ledger, record_path.with_suffix(".json.tmp")):
            if p.exists(): p.unlink()


def test_tail_resolver_does_not_fabricate_time_exit():
    b = bars(20)
    open_row = F.resolve_asof(b, 10, 1, 100.0, 1.0, 3.0, 3.0, True)
    assert not open_row["resolved"]
    hit = bars(20)
    hit.h[12] = 104.0
    resolved = F.resolve_asof(hit, 10, 1, 100.0, 1.0, 1.0, 3.0, True)
    assert resolved["resolved"] and resolved["why"] == "target"


def test_policy_builder_ignores_bars_after_cutoff():
    n = 420
    t = np.arange(n, dtype=np.int64) * 300
    base = D.Bars(t, np.full(n, 100.0), np.full(n, 100.2),
                  np.full(n, 99.8), np.full(n, 100.0), np.ones(n), 300,
                  "XAUUSD", np.full(n, 0.090))
    mutated = D.Bars(t.copy(), base.o.copy(), base.h.copy(), base.l.copy(),
                     base.c.copy(), base.v.copy(), 300, "XAUUSD", base.sp.copy())
    cutoff = 360 * 300
    mutated.h[361:] += 20.0
    mutated.l[361:] -= 20.0
    stream = {
        "order_k": np.asarray([10, 350, 370], np.int32),
        "entry_k": np.asarray([10, 350, 370], np.int32),
        "direction": np.asarray([1, 1, 1], np.int8),
        "entry": np.asarray([100.0, 100.0, 100.0]),
        "atr": np.asarray([1.0, 1.0, 1.0]),
        "at_open": np.asarray([True, True, True]),
        "gross": np.zeros((3, 1)),
        "held": np.asarray([[287], [69], [49]], np.uint16),
    }
    tag = "breakout/M5/s3/t3/o0e0"
    meta = {tag: {"setup": "breakout", "tf": "M5", "mult": 1,
                  "stop": 3.0, "target": 3.0, "off": 0.0, "exp": 0,
                  "stream": "s", "plane": 0}}
    pd_a, state_a = F.build_policy_asof(base, {"s": stream}, meta, cutoff)
    pd_b, state_b = F.build_policy_asof(mutated, {"s": stream}, meta, cutoff)
    assert F._policy_digest(pd_a) == F._policy_digest(pd_b)
    assert state_a["available_digest"] == state_b["available_digest"]


def _safe_check(**updates):
    kwargs = dict(account_is_demo=True, hedging=True, login_matches=True,
                  server_matches=True, quote_age=1.0, live_spread=0.090,
                  risk=4.0, volume_min=0.01, volume_step=0.01,
                  margin_ok=True, all_positions_have_sl=True,
                  peak_equity=1000.0, current_equity=1000.0,
                  additional_losses=[], proposed_loss=10.0, own_pnl=0.0,
                  activation_equity=1000.0, own_positions=0, cell_flat=True,
                  event_seen=False, w1_blackout=False)
    kwargs.update(updates)
    return F.demo_preflight(**kwargs)


def test_demo_fail_closed_matrix_and_risk_limits():
    assert _safe_check().allowed
    cases = [
        ({"account_is_demo": False}, "ACCOUNT_NOT_DEMO"),
        ({"hedging": False}, "ACCOUNT_NOT_HEDGING"),
        ({"quote_age": 31.0}, "STALE_QUOTE"),
        ({"all_positions_have_sl": False}, "UNBOUNDED_POSITION_WITHOUT_SL"),
        ({"live_spread": 0.136}, "SPREAD_ABOVE_0.135"),
        ({"margin_ok": False}, "INSUFFICIENT_MARGIN"),
        ({"volume_min": 0.1}, "CHANGED_MINIMUM_LOT"),
        ({"event_seen": True}, "DUPLICATE_EVENT"),
        ({"cell_flat": False}, "A27_CELL_BUSY"),
        ({"own_positions": 5}, "A27_SLOT_LIMIT"),
        ({"current_equity": 650.0}, "OBSERVED_DD_SOFT_HALT"),
        ({"current_equity": 600.0}, "OBSERVED_DD_HARD_HALT"),
        ({"own_pnl": -100.0}, "A27_10PCT_LOSS_HALT"),
        ({"additional_losses": [350.0]}, "PROJECTED_DD_ABOVE_35"),
        ({"w1_blackout": True}, "W1_PROBE_BLACKOUT"),
    ]
    for update, reason in cases:
        result = _safe_check(**update)
        assert not result.allowed and reason in result.reasons, (update, result)


def test_magic_isolation_and_one_event_one_order_guard():
    positions = [SimpleNamespace(magic=F.MAGIC),
                 SimpleNamespace(magic=F.PAYOFF_MAGIC),
                 SimpleNamespace(magic=F.W1_MAGIC)]
    selected = F.managed_positions(positions)
    assert len(selected) == 1 and selected[0].magic == F.MAGIC
    assert "DUPLICATE_EVENT" in _safe_check(event_seen=True).reasons
    mt5 = _FakeMT5RequestSchema()
    req = F.demo_request(mt5,
                         {"event_id": "e", "direction": 1, "risk": 4.0,
                          "target_r": 2.0, "weight": 0.2},
                         SimpleNamespace(ask=100.1234, bid=100.0334),
                         _fake_symbol_info())
    assert req["volume"] == 0.01 and req["sl"] == 96.123 and req["tp"] == 108.123
    assert req["magic"] == F.MAGIC and req["comment"].startswith("A27_")


class _FakeMT5RequestSchema:
    """Constants plus an order_check-shaped, side-effect-free validator."""
    TRADE_ACTION_DEAL = 1
    ORDER_TYPE_BUY = 10
    ORDER_TYPE_SELL = 11
    ORDER_TIME_GTC = 20
    ORDER_FILLING_FOK = 30
    ORDER_FILLING_IOC = 31
    ORDER_FILLING_RETURN = 32
    SYMBOL_FILLING_FOK = 1
    SYMBOL_FILLING_IOC = 2
    SYMBOL_TRADE_EXECUTION_MARKET = 2

    @classmethod
    def validate_like_order_check(cls, request):
        required = {"action", "symbol", "volume", "type", "price", "sl", "tp",
                    "deviation", "magic", "comment", "type_time", "type_filling"}
        assert set(request) == required
        assert request["action"] == cls.TRADE_ACTION_DEAL
        assert request["type"] in {cls.ORDER_TYPE_BUY, cls.ORDER_TYPE_SELL}
        assert request["type_time"] == cls.ORDER_TIME_GTC
        assert request["type_filling"] in {cls.ORDER_FILLING_FOK,
                                            cls.ORDER_FILLING_IOC}
        return SimpleNamespace(retcode=0)


def _fake_symbol_info(**updates):
    values = dict(volume_min=0.01, volume_step=0.01, digits=3, point=0.001,
                  trade_stops_level=100, filling_mode=2, trade_exemode=2)
    values.update(updates)
    return SimpleNamespace(**values)


def test_demo_request_is_native_rounded_protected_and_order_check_shaped():
    mt5 = _FakeMT5RequestSchema()
    event = {"event_id": "native", "direction": -1, "risk": 0.5004,
             "target_r": 2.0, "weight": 0.2}
    tick = SimpleNamespace(ask=2000.2234, bid=2000.1234)
    request = F.demo_request(mt5, event, tick, _fake_symbol_info())
    checked = mt5.validate_like_order_check(request)
    assert checked.retcode == 0
    assert request["type"] == mt5.ORDER_TYPE_SELL
    assert request["price"] == 2000.123
    assert request["sl"] == 2000.624 and request["tp"] == 1999.123
    assert all(round(request[key], 3) == request[key]
               for key in ("price", "sl", "tp"))
    assert request["sl"] - tick.ask >= 0.100 - 1e-9
    assert tick.ask - request["tp"] >= 0.100 - 1e-9

    too_close = dict(event, direction=1, risk=0.050, target_r=1.0)
    try:
        F.demo_request(mt5, too_close, tick, _fake_symbol_info())
    except F.A27Error as exc:
        assert "trade_stops_level" in str(exc)
    else:
        raise AssertionError("too-close protected levels were accepted")

    fok = F.demo_request(mt5, dict(event, direction=1, risk=1.0), tick,
                         _fake_symbol_info(filling_mode=1))
    assert fok["type_filling"] == mt5.ORDER_FILLING_FOK


def test_order_send_unreachable_without_both_gates():
    class Fake:
        calls = 0
        def order_send(self, _request):
            self.calls += 1
            return object()
    fake = Fake()
    try:
        F.guarded_order_send(fake, {}, live_demo=False,
                             activation_path=Path("does-not-exist"))
    except F.A27Error:
        pass
    assert fake.calls == 0
    try:
        F.guarded_order_send(fake, {}, live_demo=True,
                             activation_path=Path("does-not-exist"))
    except F.A27Error:
        pass
    assert fake.calls == 0


def test_live_event_must_be_hash_chained_shadow_admission():
    root = Path("data")
    token = f"a27_test_{os.getpid()}_auth"
    decision_path = root / f"{token}_decision.json"
    ledger_path = root / f"{token}_events.jsonl"
    for p in (decision_path, ledger_path, decision_path.with_suffix(".json.tmp")):
        if p.exists(): p.unlink()
    try:
        decision = F.seal_record(
            {"schema": F.SCHEMA, "status": "FORWARD_WEEK",
             "decision": {"members": [{"tag": "cell", "target": 1.0,
                                          "weight": 0.2}]}},
            decision_path, "GENESIS")
        payload = {"event_id": "evt", "tag": "cell", "risk": 4.0,
                   "direction": 1, "target_r": 1.0, "weight": 0.2,
                   "time_exit_epoch": 2000, "shadow_gate_passed": True,
                   "portfolio_admitted": True}
        shadow = F.append_event(ledger_path, decision["record_hash"],
                                "WOULD_BE_ADMISSION", payload, 1000)
        event = {"event_id": "evt", "decision_record": str(decision_path),
                 "decision_hash": decision["record_hash"],
                 "event_ledger": str(ledger_path),
                 "shadow_event_hash": shadow["event_hash"], "tag": "cell",
                 "risk": 4.0, "direction": 1, "target_r": 1.0, "weight": 0.2,
                 "time_exit_epoch": 2000}
        assert F.verify_live_shadow_event(event)["event_hash"] == shadow["event_hash"]
        event["risk"] = 8.0
        try:
            F.verify_live_shadow_event(event)
        except F.A27Error:
            pass
        else:
            raise AssertionError("mutated live risk was accepted")
        event["risk"] = 4.0
        event["event_id"] = "different"
        try:
            F.verify_live_shadow_event(event)
        except F.A27Error:
            pass
        else:
            raise AssertionError("unanchored live event was accepted")
    finally:
        for p in (decision_path, ledger_path, decision_path.with_suffix(".json.tmp")):
            if p.exists(): p.unlink()


def test_activation_requires_review_and_exact_document_commit():
    p = Path("data") / f"a27_test_{os.getpid()}_activation.json"
    if p.exists(): p.unlink()
    try:
        base = {"enabled": True, "document_commit": F.DOCUMENT_COMMIT,
                "implementation_review_commit": "reviewed", "account_login": 1,
                "account_server": "Demo", "activation_equity": 1000.0,
                "seed_file_sha256": F.SEED_FILE_SHA256,
                "seed_content_sha256": F.SEED_CONTENT_SHA256}
        p.write_text(json.dumps(base), encoding="utf-8")
        assert F.load_activation(p)["document_commit"] == F.DOCUMENT_COMMIT
        base["implementation_review_commit"] = ""
        p.write_text(json.dumps(base), encoding="utf-8")
        try:
            F.load_activation(p)
        except F.A27Error:
            pass
        else:
            raise AssertionError("unreviewed activation was accepted")
    finally:
        if p.exists(): p.unlink()


def test_weekend_seal_window_is_after_cutoff_and_bounded():
    cutoff = 1_000_000
    assert F.validate_weekend_seal_time(cutoff, cutoff) == (
        cutoff + F.WEEKEND_SEAL_GRACE_SECONDS)
    assert F.validate_weekend_seal_time(
        cutoff, cutoff + F.WEEKEND_SEAL_GRACE_SECONDS) == (
            cutoff + F.WEEKEND_SEAL_GRACE_SECONDS)
    for now in (cutoff - 1, cutoff + F.WEEKEND_SEAL_GRACE_SECONDS + 1):
        try:
            F.validate_weekend_seal_time(cutoff, now)
        except F.A27Error:
            pass
        else:
            raise AssertionError("out-of-window weekly seal was accepted")


def main() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failures = []
    for fn in tests:
        try:
            fn()
            print(f"PASS {fn.__name__}")
        except Exception as exc:
            failures.append((fn.__name__, repr(exc)))
            print(f"FAIL {fn.__name__}: {exc!r}")
    print(f"tests={len(tests)} passed={len(tests)-len(failures)} failures={len(failures)}")
    return int(bool(failures))


if __name__ == "__main__":
    raise SystemExit(main())
