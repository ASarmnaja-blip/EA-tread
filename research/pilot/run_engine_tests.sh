#!/usr/bin/env bash
# Everything in the engine that can be tested without MT5 and without reading
# a market price. Each suite runs on cases whose answer is known in advance.
set -u
cd "$(dirname "$0")"
rc=0
for s in test_news.py test_regime.py test_decide.py; do
  echo "### $s"
  python3 "$s" | tail -3 || rc=1
  echo
done
echo "### mutation: news layer"
python3 test_news_mutation.py | tail -4 || rc=1
echo
[ $rc -eq 0 ] && echo "ALL ENGINE TESTS PASS." || echo "SOMETHING FAILED (rc=$rc)."
echo "No MT5, no market price, no order. See docs/MT5_ENV_REQUIREMENTS.md."
exit $rc
