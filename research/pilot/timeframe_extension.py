"""Apply the verified weekly diverse selector separately to M5/M15/H1."""
from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import evolution_portfolio_audit as audit


def main() -> int:
    b5 = audit.hist.load_history()
    first, last = int(b5.t[0]), int(b5.t[-1] + b5.step)
    uni, meta = audit.load_universe(b5)
    rankings, purged = audit.weekly_rankings(uni, first, last)
    market = [(cut, end, [tag for tag in ranked
                           if meta[tag]["off"] == 0 and meta[tag]["exp"] == 0])
              for cut, end, ranked in rankings]
    market_rows, market_info = audit.weekly_portfolio(
        b5, uni, meta, market, purged, 5, True)
    print("MARKET_ONLY_ALL_TF", market_info)
    print("FULL", audit.metrics(market_rows))
    print("365D", audit.metrics(market_rows, last - 365 * audit.DAY))
    print("90D", audit.metrics(market_rows, last - 90 * audit.DAY))
    print("MTM", audit.mark_to_market(market_rows, b5))
    for tf in ("M5", "M15", "H1"):
        filtered = [(cut, end, [tag for tag in ranked if meta[tag]["tf"] == tf])
                    for cut, end, ranked in rankings]
        rows, info = audit.weekly_portfolio(
            b5, uni, meta, filtered, purged, 5, True)
        print(tf, info)
        print("FULL", audit.metrics(rows))
        print("365D", audit.metrics(rows, last - 365 * audit.DAY))
        print("90D", audit.metrics(rows, last - 90 * audit.DAY))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
