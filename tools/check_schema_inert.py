#!/usr/bin/env python3
"""
Static invariant tests for Track 1.1 (schema v2) and 1.2 (decision log).

These changes make one narrow claim: the new fields and the decision log are
RECORD-ONLY, so trading behaviour cannot have changed. A compiler cannot check
that, and no backtest has been run. These tests check the claim on the source.

    python3 tools/check_schema_inert.py

Exit 0 = every invariant holds.

What this does NOT prove: that the code compiles in MetaEditor, or that a
backtest reproduces the previous numbers. Only MetaTrader 5 can show either.
"""
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EA = ROOT / "MQL5/Experts/XAUM15/XAU_M15_Institutional_Adaptive.mq5"
CONFIG = ROOT / "MQL5/Include/XAUM15/Config.mqh"
SETUPS = ROOT / "MQL5/Include/XAUM15/Setups.mqh"
DECLOG = ROOT / "MQL5/Include/XAUM15/DecisionLog.mqh"

V2_FIELDS = [
    "symbol", "timeframe", "regime", "regimeScore", "confidence",
    "invalidation", "invalidationRule", "expiryBars", "expiryTime",
    "formedAt", "riskR", "evidence", "pricedIn", "newsRisk",
    "decision", "decisionReason",
]

ORDER_CALLS = ["OrderSend", "PositionClose", "PositionModify", "OrderModify",
               "OrderClose", "CTrade", "g_tm.", "Buy(", "Sell("]

# The only pre-existing lines this work was allowed to touch, and what they
# became. Semantically identical: EntryGatesPass is still evaluated once, in
# the same position, with the same branch taken.
EXPECTED_REMOVED = [
    "if(EntryGatesPass(now,why)) TryEnter(now);",
    "else                        g_blockReason=why;",
]
EXPECTED_REPLACEMENT = [
    "bool gatePassed=EntryGatesPass(now,why);",
    "if(gatePassed) TryEnter(now);",
    "else           g_blockReason=why;",
]

failures, notes = [], []


def read(p):
    return p.read_text(encoding="utf-8", errors="surrogateescape")


def strip_comments(src):
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    return re.sub(r"//[^\n]*", "", src)


def tradesignal_vars(src):
    """Names bound to a TradeSignal, so the field checks do not collide with
    identically named members of other structs (ctx.regime, trans.symbol)."""
    names = set(re.findall(r"\bTradeSignal\s+&?\s*([A-Za-z_][A-Za-z0-9_]*)", src))
    names |= {"g_lastSignal", "g_barCandidate", "g_tm.current"}
    return names


# --------------------------------------------------------------------------
def test_zerosignal_covers_every_field():
    cfg = strip_comments(read(CONFIG))
    m = re.search(r"struct\s+TradeSignal\s*\{(.*?)\}\s*;", cfg, flags=re.S)
    if not m:
        failures.append("TradeSignal struct not found")
        return
    fields = []
    for line in m.group(1).splitlines():
        line = line.strip().rstrip(";")
        mm = re.match(r"^[A-Za-z_][A-Za-z0-9_]*\s+(.*)$", line) if line else None
        if not mm:
            continue
        for name in mm.group(1).split(","):
            name = name.strip().split("[")[0].strip()
            if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
                fields.append(name)

    z = re.search(r"void\s+ZeroSignal\s*\([^)]*\)\s*\{(.*?)\n\s*\}",
                  strip_comments(read(SETUPS)), flags=re.S)
    if not z:
        failures.append("ZeroSignal not found")
        return
    missing = [f for f in fields
               if not re.search(r"\.\s*" + re.escape(f) + r"\s*(\[\s*\d+\s*\])?\s*=", z.group(1))]
    if missing:
        failures.append("ZeroSignal does not clear: " + ", ".join(missing))
    else:
        notes.append(f"ZeroSignal clears all {len(fields)} TradeSignal fields")


def test_only_expected_lines_were_removed():
    """The decisive test. Behaviour can only change if an existing line was
    removed or modified. Every other change is pure addition."""
    diff = subprocess.run(["git", "diff", "-U0", "--", "MQL5/"],
                          cwd=ROOT, capture_output=True, text=True).stdout
    removed = [l[1:].strip() for l in diff.splitlines()
               if l.startswith("-") and not l.startswith("---") and l[1:].strip()]
    if removed != EXPECTED_REMOVED:
        failures.append("unexpected lines removed/modified:\n" +
                        "\n".join("  " + r for r in removed))
        return
    ea = strip_comments(read(EA))
    for line in EXPECTED_REPLACEMENT:
        if line not in ea:
            failures.append(f"expected replacement line missing: {line}")
            return
    notes.append("only the 2 known lines changed; replacement is equivalent "
                 "(EntryGatesPass still evaluated once, same branch)")


def test_v2_fields_are_write_only():
    bad = []
    for path in (EA, SETUPS):
        src = strip_comments(read(path))
        tsvars = tradesignal_vars(src)
        for ln, line in enumerate(src.splitlines(), 1):
            for f in V2_FIELDS:
                for mm in re.finditer(
                        r"\b([A-Za-z_][A-Za-z0-9_.]*)\.\s*" + re.escape(f) + r"\b", line):
                    if mm.group(1) not in tsvars:
                        continue                       # another struct's member
                    if re.match(r"\s*=(?!=)", line[mm.end():]):
                        continue                       # assignment target
                    bad.append(f"  {path.name}:{ln}: {line.strip()[:90]}")
    if bad:
        failures.append("v2 field READ outside DecisionLog.mqh:\n" + "\n".join(bad))
    else:
        notes.append("v2 fields are write-only in EA and Setups")


def test_v2_fields_never_in_conditions():
    bad = []
    for path in (EA, SETUPS):
        src = strip_comments(read(path))
        tsvars = tradesignal_vars(src)
        for ln, line in enumerate(src.splitlines(), 1):
            cond = re.search(r"\b(?:if|while|for)\s*\((.*)\)", line)
            payload = cond.group(1) if cond else (
                line if re.match(r"\s*return\b", line) else "")
            if not payload:
                continue
            for f in V2_FIELDS:
                for mm in re.finditer(
                        r"\b([A-Za-z_][A-Za-z0-9_.]*)\.\s*" + re.escape(f) + r"\b", payload):
                    if mm.group(1) in tsvars:
                        bad.append(f"  {path.name}:{ln}: {line.strip()[:90]}")
    if bad:
        failures.append("v2 field reaches control flow:\n" + "\n".join(bad))
    else:
        notes.append("no v2 field appears in any condition or return")


def test_audit_never_inside_a_condition():
    """g_audit may be the TARGET of a statement guarded by a condition; it must
    never appear INSIDE the condition."""
    src = strip_comments(read(EA))
    bad = []
    for ln, line in enumerate(src.splitlines(), 1):
        for mm in re.finditer(r"\b(?:if|while|for)\s*\(", line):
            depth, i = 0, mm.end() - 1
            while i < len(line):
                depth += (line[i] == "(") - (line[i] == ")")
                if depth == 0:
                    break
                i += 1
            if "g_audit" in line[mm.end():i]:
                bad.append(f"  EA:{ln}: {line.strip()[:90]}")
    if bad:
        failures.append("g_audit inside a condition:\n" + "\n".join(bad))
    else:
        notes.append("g_audit never appears inside a condition")


def test_decisionlog_places_no_orders():
    src = strip_comments(read(DECLOG))
    hits = [c for c in ORDER_CALLS if c in src]
    if hits:
        failures.append(f"DecisionLog.mqh references order calls: {hits}")
    else:
        notes.append("DecisionLog.mqh contains no order-placing call")


def test_log_call_site():
    """LogBarDecision must be called exactly once, after the decision."""
    src = strip_comments(read(EA))
    calls = [ln for ln, l in enumerate(src.splitlines(), 1)
             if re.search(r"^\s*LogBarDecision\s*\(", l)]
    if len(calls) != 1:
        failures.append(f"LogBarDecision called {len(calls)} times, expected 1")
        return
    lines = src.splitlines()
    entry = next((ln for ln, l in enumerate(lines, 1) if "TryEnter(now);" in l), None)
    if entry is None or calls[0] <= entry:
        failures.append("LogBarDecision does not run after TryEnter")
    else:
        notes.append("LogBarDecision called once, after the entry decision")


def test_gate_call_count_unchanged():
    n = len(re.findall(r"EntryGatesPass\s*\(", strip_comments(read(EA))))
    if n != 2:
        failures.append(f"EntryGatesPass appears {n} times, expected 2 (def + 1 call)")
    else:
        notes.append("EntryGatesPass still has exactly one call site")


def test_stamp_runs_only_on_accepted_signals():
    """StampSignalContext must sit after sig.valid=true in every setup, so it
    can never appear on an early-return path."""
    src = strip_comments(read(SETUPS))
    lines = src.splitlines()
    valid_at = [ln for ln, l in enumerate(lines, 1) if re.search(r"sig\.valid\s*=\s*true", l)]
    stamp_at = [ln for ln, l in enumerate(lines, 1) if re.search(r"^\s*StampSignalContext\s*\(", l)]
    if len(stamp_at) != 4:
        failures.append(f"StampSignalContext called {len(stamp_at)} times, expected 4 (A-D)")
        return
    for s_ln in stamp_at:
        if not any(v < s_ln for v in valid_at):
            failures.append(f"StampSignalContext at line {s_ln} precedes sig.valid=true")
            return
    notes.append("StampSignalContext runs only after a signal is accepted (4/4 setups)")


def main():
    for t in (test_zerosignal_covers_every_field,
              test_only_expected_lines_were_removed,
              test_v2_fields_are_write_only,
              test_v2_fields_never_in_conditions,
              test_audit_never_inside_a_condition,
              test_decisionlog_places_no_orders,
              test_log_call_site,
              test_gate_call_count_unchanged,
              test_stamp_runs_only_on_accepted_signals):
        t()

    print("=" * 68)
    print("SCHEMA INERTNESS TESTS  (static analysis, container-only)")
    print("=" * 68)
    for n in notes:
        print(f"  PASS  {n}")
    for f in failures:
        print(f"  FAIL  {f}")
    print("-" * 68)
    if failures:
        print(f"{len(failures)} invariant(s) VIOLATED")
        return 1
    print(f"{len(notes)}/{len(notes)} invariants hold.")
    print()
    print("Scope: this shows the new fields are inert IN THE SOURCE.")
    print("It does NOT show the file compiles, and it does NOT show the")
    print("backtest is unchanged. Both still require MetaTrader 5.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
