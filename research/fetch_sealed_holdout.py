#!/usr/bin/env python3
"""Fetch a holdout this project has never seen: FX crosses, no USD leg.

WHY A NEW UNIVERSE IS THE ONLY HOLDOUT LEFT

  Every market in this repo's cache - XAUUSD, XAGUSD, and seven majors - has
  been searched, re-searched, and looked at across 33 topics and 824
  hypotheses. A "holdout" carved out of data that has already been examined
  is not a holdout; it is a slice of the training set with a later date on
  it. There is nothing clean left in there.

  These fourteen crosses have never been fetched, never been plotted, and
  never appeared in a result table here. They also share no USD leg, so they
  are not a re-expression of the dollar factor that sits on one side of six
  of the nine markets already used.

WHAT THIS MAKES POSSIBLE, AND THE CORRECTION IT RESTS ON

  change_ledger.py charges every hypothesis ever spent against every later
  test. That is the correct rule for the thing it was built to stop - tweak,
  retest on the same data, repeat - and it is too strict for a properly
  nested design. If N rules are searched on data that is ALREADY burned, one
  finalist is chosen using nothing but that burned data, and it is then
  tested ONCE against data never examined, the holdout statistic is a single
  draw under the null. The selection consumed no holdout information, so it
  costs no holdout significance.

  That is ordinary train/test logic, and it is what makes a large search
  affordable again: the search itself becomes free, and only the finalists
  are paid for.

  It holds only while three things are true, which is why the manifest below
  records a hash of every file:
    - the holdout is examined exactly once
    - the number of finalists tested on it is fixed BEFORE looking
    - nothing is re-tuned afterwards and re-run

  Break any of them and this data is burned too, permanently, and there is
  no third universe waiting.
"""
import hashlib
import json
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import fetch_dukascopy as D

CACHE = pathlib.Path(__file__).parent / ".cache_duka"
MANIFEST = pathlib.Path(__file__).parent / "sealed_holdout.json"
Y0, Y1 = 2012, 2026

# Divisors are the quote's decimal count and a wrong one silently rescales
# every price, so each is recorded rather than inferred. JPY crosses quote to
# three decimals, the rest to five.
CROSS_POINTS = {
    "EURJPY": 1000.0, "GBPJPY": 1000.0, "AUDJPY": 1000.0,
    "CHFJPY": 1000.0, "CADJPY": 1000.0, "NZDJPY": 1000.0,
    "EURGBP": 100000.0, "EURCHF": 100000.0, "EURAUD": 100000.0,
    "EURCAD": 100000.0, "AUDNZD": 100000.0, "AUDCAD": 100000.0,
    "GBPCHF": 100000.0, "GBPAUD": 100000.0,
}

# Rough level bands for the decode check. A fetch whose median lands outside
# its band has a wrong divisor and is discarded rather than kept and trusted.
SANE = {
    "EURJPY": (90, 180), "GBPJPY": (110, 220), "AUDJPY": (55, 115),
    "CHFJPY": (85, 200), "CADJPY": (70, 130), "NZDJPY": (50, 110),
    "EURGBP": (0.65, 0.98), "EURCHF": (0.85, 1.35), "EURAUD": (1.20, 2.00),
    "EURCAD": (1.20, 1.80), "AUDNZD": (0.95, 1.35), "AUDCAD": (0.80, 1.15),
    "GBPCHF": (0.95, 1.70), "GBPAUD": (1.40, 2.20),
}


def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    D.POINTS.update(CROSS_POINTS)
    CACHE.mkdir(exist_ok=True)
    rows = {}
    print(f"SEALED HOLDOUT - {len(CROSS_POINTS)} FX crosses, {Y0}-{Y1}, H1")
    print("=" * 78, flush=True)
    for sym in CROSS_POINTS:
        p = CACHE / f"{sym}_H1_{Y0}_{Y1}.parquet"
        if p.exists():
            print(f"  {sym:<8} cached", flush=True)
        else:
            t0 = time.time()
            try:
                df = D.load_h1(Y0, Y1, verbose=False, symbol=sym)
            except Exception as e:
                print(f"  {sym:<8} FAILED {e}", flush=True)
                continue
            if df is None or len(df) < 20000:
                print(f"  {sym:<8} too little data", flush=True)
                continue
            mid = (df["bid_close"] + df["ask_close"]) / 2
            lo, hi = SANE[sym]
            med = float(mid.median())
            if not (lo <= med <= hi):
                print(f"  {sym:<8} DECODE CHECK FAILED median {med:.4f} "
                      f"outside [{lo}, {hi}] - discarded", flush=True)
                continue
            df.to_parquet(p)
            print(f"  {sym:<8} {len(df):>7,} bars  median {med:>9.4f}  "
                  f"{time.time()-t0:.0f}s", flush=True)
        rows[sym] = dict(file=p.name, sha256=sha(p),
                         points=CROSS_POINTS[sym])

    MANIFEST.write_text(json.dumps(dict(
        created=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        years=[Y0, Y1], timeframe="H1",
        purpose="sealed holdout - examined once, after finalists are fixed",
        examined=False, finalists_declared=None,
        symbols=rows), indent=1))
    print(f"\n  {len(rows)} symbols sealed -> {MANIFEST.name}")
    print(f"  The manifest records a sha256 per file. It is the only thing")
    print(f"  that can later show this data was not quietly refetched,")
    print(f"  reordered, or peeked at between sealing and testing.")


if __name__ == "__main__":
    main()
