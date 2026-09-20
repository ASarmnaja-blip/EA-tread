#!/usr/bin/env bash
# Everything that can be checked without MetaTrader 5.
#
#   ./tests/run_all.sh
#
# 1. static invariants  - the new fields never reach a decision
# 2. system tests       - real production source, compiled and run
# 3. mutation check     - proves the suite fails when the code is wrong
set -u
cd "$(dirname "$0")/.."
BIN="${TMPDIR:-/tmp}/xaum15_test_system"
rc=0

echo "### 1/3  static invariants"
python3 tools/check_schema_inert.py || rc=1

echo
echo "### 2/3  system tests (executable)"
python3 tests/extract_source.py || exit 1
g++ -std=c++17 -O0 -o "$BIN" tests/test_system.cpp || exit 1
"$BIN" || rc=1

echo
echo "### 3/3  mutation check"
python3 tests/mutation_check.py || rc=1

echo
if [ $rc -eq 0 ]; then
  echo "ALL CONTAINER-SIDE CHECKS PASS."
else
  echo "SOMETHING FAILED (rc=$rc)."
fi
echo "None of this compiles in MetaEditor or runs a backtest."
echo "See docs/ENGINE_PROTOCOL.md section 0: AUTHORED, not VERIFIED."
exit $rc
