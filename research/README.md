# Research cells

Paste-and-run cells for a QuantConnect **Research** notebook (not an
algorithm). Each is self-contained — it does not depend on helpers defined
in earlier cells — so it can be dropped into a fresh notebook.

| File | Question it answers |
|---|---|
| `qc_crossasset_test.py` | Does the trend zone exist off gold, or was it fitted to it? |

## qc_crossasset_test.py

The outstanding test. Everything measured so far — permutation p = 0.0005,
in-zone vs out-of-zone t = +9.33, drift-adjusted t = +5.08 — was measured on
**gold only**, and the zone edges were found on the *full* sample rather than
a held-out half. If `(Close − SMA200)/ATR ∈ [1.08, 7.21]` is a real effect it
has to show up elsewhere. If it does not, it is gold overfit.

**Nothing is refitted per instrument.** The zone edges, stop multiple, target
and hold are fixed at gold's values. Retuning them per market would turn one
overfit into three.

Pre-registered pass criteria, stated before the output is seen:

```
PASS = net E > 0 AND t > 2.0 on BOTH XAGUSD and EURUSD (long side, 8R target)
FAIL = anything else
```

The drift-adjusted column is reported alongside and is the honest one: gold
rose across the whole sample, so a long-only rule inherits that. On gold,
removing drift takes longs in the zone from +0.0569R (t +4.45) to **−0.0494R
(t −4.14)**, while shorts go to +0.1092R (t +7.56). Watch whether the same
happens on the new instruments.

### Two implementation details that changed earlier results

**Exits resolve on minute bars.** Resolving on the 15-minute signal bar
misses stops that were actually hit and inflated the earlier work by +0.06R
at 1.5R and +0.20R at 3R.

**The 15-minute → minute mapping uses the LAST minute of each bin.** pandas
labels a resampled bin by its left edge; searching that label into the minute
index lands on the *first* minute of the bar, a 15-minute look-ahead. That
bug once lifted a win rate from 66.7% to 79.8% on driftless data.

### Running it

Free-tier memory is the constraint, so it loads one instrument at a time in
quarterly chunks and frees each before the next. Expect several minutes.

Output is deliberately compact — one line per instrument per side, then a
verdict block — because long cell output gets truncated in the browser.

### Spreads

`SPREAD` is in price units per instrument and is a **cost assumption**, not a
measurement. The gold figure is OANDA's measured 2023–2026 mean ($0.7525),
which is 2.9× the $0.26 the original work costed with. Replace the FX values
with your broker's real numbers before trusting the verdict — at a 1.8×ATR
stop this input alone moves gold's net expectancy from +0.2312R to +0.1253R.
