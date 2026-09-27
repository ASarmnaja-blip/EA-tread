# Amendment 27 implementation record

**Built and audited:** 2026-09-27 Asia/Bangkok

**Pre-registration:** `da52fef`

**Implementation status:** `AUDITS PASS; DEMO MIRROR NOT ACTIVATED`

**Forward clock:** `NOT STARTED`

This record describes the read-only forward logger and the inactive optional
Demo mirror required by Amendment 27 and binding clarification A in
`4318fb5`. No Demo or real order was submitted, no broker process was started
or stopped, and the dry run below is explicitly not week 1.

## 1. Delivered implementation

- `research/pilot/a27_forward.py` implements content-addressed M5 ingestion,
  immutable weekly decision records, decision and event hash chains, the full
  330-stream rebuild path, causal candidate-state reconstruction, and the
  frozen A24 selector on the Amendment 26 chain.
- `research/pilot/test_a27_forward.py` contains the Amendment 27 audit tests.
- The primary shadow gate uses only
  `max(ingested M5 sp[k-1], 0.090)`. The executable live spread is stored as a
  diagnostic and can reject only the optional Demo mirror. It cannot change a
  shadow event.
- Candidate positions whose 288-M5 horizon is incomplete remain unresolved;
  the logger does not fabricate an end-of-data time exit. Candidate pending
  orders and actual shadow state are sealed separately.
- A Weekend Rebuild may seal only from the Friday 22:15 UTC cutoff through the
  following six hours (Saturday 05:15 through 11:15 Asia/Bangkok). This lets
  the last bar close before the rebuild begins and prevents a late backfill.
- The Demo component performs one cycle only; it contains no implicit loop and
  is inactive by default. `guarded_order_send()` is the only call site for
  `mt5.order_send`.

The Demo request builder now emits a native MT5 request containing
`TRADE_ACTION_DEAL`, BUY/SELL type, deviation, GTC time type, and a filling
mode admitted by the symbol. Entry, SL and TP are rounded to `symbol_info.digits`.
The frozen SL/TP are rejected rather than moved if they violate
`trade_stops_level`. The fake-MT5 audit validates the complete request schema;
it calls neither a real `order_check` nor a real `order_send`.
An executable Demo event must also reproduce the sealed shadow admission's
cell, direction, risk, target R, theoretical weight, and time exit exactly;
changing any one of them invalidates the authorization.

## 2. File identities

SHA-256 values after the final audit and dry-run seal:

```text
9c899ec1734ee46eb68992f7b06ae61de6bfe6c7ee2265afa0eb697690c31d00  research/pilot/a27_forward.py
61236833de3ad197d6b195c94b95efe8ea46058ef1465b87ca2c99ee623f35dc  research/pilot/test_a27_forward.py
6790df6369518f3751b63b8c65ff8f8fadd9845fe012ed94f18b827f1db571fc  data/a27_forward/audit_output.txt
df08c6e5d8bcddbe501213aa077788ab166f9d3fa9744d3c2bcf16759d456037  data/a27_forward/audit_receipt.json
55273a3c61d2c40cfc72e14aa7f30fc21c244161df8e4e890132361985c45642  data/a27_forward/dry_run/decision_20260918T2215Z.json
92bcb5ec64dafe44581b79b45c36c4e8ccc55e632e4a09156bea65d8679de4ad  data/a27_forward/dry_run/candidate_state_717edf820fc338802279228a090613fa06886a9e294e55cb2ce65d5582c81c5d.json.gz
dfa12a60ac16c0260522ae30af5132322a6407e3a1be9d4f08a96472614f3c67  data/canonical_XAUUSD_M5.npz
bcde042029119a0d5fbddce33dd88b185d9974ba4bce789f1a75727bfde00ae9  data/amendment24_raw_opportunities_v1_sp090_co140.pkl
```

The canonical seed content digest, distinct from its compressed file hash, is
`613d5e7476deeaa3dc473371028adf9d4724720788b5f1d424e410556dfad158`.
The verified A24 cache stamp digest is
`610822927aca74563eeb204b537e59c108f5cbf73ce772a13fd4cfd58e788518`.

The sealed record also carries the exact hashes of `basket_gate.py`,
`causal_chain.py`, `mtf_engine.py`, `core.py`, and `canonical_history.py`.
The weekly command refuses to run unless the current code hashes match the
`ALL_PASS` audit receipt.

## 3. Section 9 audit result

Final verdict: **ALL PASS**.

- A27 tests: 14 passed, 0 failed.
- Amendment 26 causal-chain tests: 5 passed, 0 failed.
- Amendment 23 basket-DD tests: return code 0.
- Amendment 24 friction-gate tests: return code 0.
- Existing MTF engine suite: 40 passed, 0 failed.

The A27 set covers clarification A, shadow/Demo disagreement, prefix and
future-data invariance, duplicate/gap detection, sealed-record and event-ledger
tampering, unresolved tails, policy truncation, magic isolation, duplicate
event refusal, all registered Demo fail-closed conditions, both activation
gates, native protected MT5 request construction, and the bounded Saturday
seal window. Full raw output is in `data/a27_forward/audit_output.txt`; the
matching machine-readable receipt is `data/a27_forward/audit_receipt.json`.

## 4. Dry run — not week 1

The final dry run used the canonical seed and the fully verified A24 raw cache.

```text
status                 DRY_RUN_NOT_WEEK_1
clock_started          false
cutoff                 2026-09-18T22:15:00Z
nominal week end       2026-09-25T22:15:00Z
record hash            087fffb91fb1b104689b6e1926dae427f1d844504c980b36ad45fd1038fdb078
decision-prefix hash   977c53ee1a4f68c3881bb802333026d72359425b55c80544360678c8155087f2
decision               active
eligible cells         1,565
selected members       5
n_eff                  8.694644203726147
open candidate states  1,728
pending raw orders     10,374
```

Selected members and frozen theoretical weights:

| Rank | Cell | Weight | Stressed score |
|---:|---|---:|---:|
| 1 | `sweep/M15/s2/t3/o0.5e5` | 0.2338582380 | 2.4699657212 |
| 2 | `vwap/M5/s0.75/t3/o1e12` | 0.2020839212 | 2.3468197724 |
| 3 | `failed/M15/s0.75/t1.5/o0.5e8` | 0.1517297395 | 2.1847608806 |
| 4 | `breakout/M30/s1.5/t3/o0.5e12` | 0.3123281013 | 2.0836809979 |
| 5 | `pullback/M5/s1/t3/o1e15` | 0.1000000000 | 1.5950162604 |

These membership, weight, eligibility and `n_eff` values reproduce the
independent A24-on-causal-chain cutoff cross-check. They are development/dry
run information, not forward evidence.

## 5. Weekly read-only procedure

Run the audit first from the repository root:

```powershell
python research/pilot/a27_forward.py audit
```

At or after the registered Friday 22:15 UTC cutoff, and no later than six
hours afterward, convert that exact UTC cutoff to an epoch and seal the next
week. `--allow-rebuild` is required when no content-addressed cache yet exists
for the extended bar set:

```powershell
$a27Cutoff = [DateTimeOffset]::Parse("2026-10-02T22:15:00Z").ToUnixTimeSeconds()
python research/pilot/a27_forward.py weekly --cutoff $a27Cutoff --source mt5 --allow-rebuild
```

This command only reads MT5 M5 bars. It verifies an exact overlap against the
previous snapshot, refuses revised history, excludes every bar not fully
closed by the cutoff, performs gap/duplicate checks, rebuilds or verifies all
330 raw streams, and seals one immutable decision. If ingestion/rebuild misses
the six-hour window, no production record is written and the week is a
`DATA/AUDIT FAILURE`, not a zero week.

Append intra-week observations using a JSON payload and the sealed decision:

```powershell
python research/pilot/a27_forward.py event --decision data/a27_forward/decisions/decision_20261002T2215Z.json --kind SIGNAL --payload-json data/a27_forward/inbox/signal.json --observed-epoch 1790985600
python research/pilot/a27_forward.py event --decision data/a27_forward/decisions/decision_20261002T2215Z.json --kind WOULD_BE_ADMISSION --payload-json data/a27_forward/inbox/admission.json --observed-epoch 1790985900
```

For `WOULD_BE_ADMISSION`, the payload must include `event_id`, `risk`,
`prior_bar_spread`, and `portfolio_admitted`. The logger itself recomputes and
stores the shadow gate from the prior closed M5 bar. A live-spread diagnostic
may be present, but it cannot alter that result. Every append verifies the
existing event chain before writing the next row.

## 6. Demo mirror: current state and later activation

The mirror is currently **NOT ACTIVATED**. Do not create the activation file
or run `--live-demo` until this implementation has been independently reviewed
and committed.

After that review, activation requires all of the following:

1. Record the implementation-review commit and the exact intended Demo login,
   server, and activation equity.
2. Confirm MT5 reports `ACCOUNT_TRADE_MODE_DEMO`, retail hedging, XAUUSD
   `volume_min=0.01`, `volume_step=0.01`, current symbol digits/stops/filling
   capabilities, and that account-wide open positions all have SLs.
3. Create `data/a27_forward/demo_activation.json` with this exact schema,
   substituting the reviewed values:

```json
{
  "enabled": true,
  "document_commit": "da52fef",
  "implementation_review_commit": "REPLACE_WITH_REVIEW_COMMIT",
  "account_login": 12345678,
  "account_server": "REPLACE_WITH_DEMO_SERVER",
  "activation_equity": 300.0,
  "activated_utc": "2026-10-03T00:00:00Z",
  "seed_file_sha256": "dfa12a60ac16c0260522ae30af5132322a6407e3a1be9d4f08a96472614f3c67",
  "seed_content_sha256": "613d5e7476deeaa3dc473371028adf9d4724720788b5f1d424e410556dfad158"
}
```

4. Build the Demo event JSON from an already hash-chained
   `WOULD_BE_ADMISSION` row. It must carry the decision path/hash, event-ledger
   path/hash, stable event ID, cell tag, direction, risk, target R, theoretical
   weight, and time-exit epoch.
5. Evaluate it without connecting to MT5 or sending an order:

```powershell
python research/pilot/a27_forward.py demo --event-json data/a27_forward/inbox/demo_event.json --live-spread 0.090
```

6. Only after the separate activation review, the one-cycle submission command
   is:

```powershell
python research/pilot/a27_forward.py demo --event-json data/a27_forward/inbox/demo_event.json --live-demo --activation data/a27_forward/demo_activation.json
```

The maintenance-only time-exit/safety cycle, also unavailable without both
activation gates, is:

```powershell
python research/pilot/a27_forward.py demo --live-demo --activation data/a27_forward/demo_activation.json
```

There is deliberately no background loop in this implementation. A future
supervisor or scheduler must be reviewed separately before it starts these
one-cycle commands.

Each admitted event maps to one equal 0.01-lot Demo order because the broker
minimum cannot represent the frozen basket weights. The event retains its
theoretical weight, but Demo P/L never replaces the weighted shadow ledger.
All entries require an attached SL; there is no Grid, Martingale, averaging,
child-order weight approximation, or real-money path. Magic `20260927` is
isolated from payoff magic `20260923` and W1 magic `20260922`. Account-wide
35% projected-DD and 40% observed-DD guards, the A27-only 10% kill switch,
the 0.135 live-spread cap, and the W1 blackout remain fail-closed.

## 7. Authorization state

- Shadow forward clock: **not started**.
- Demo activation record: **absent/not authorized by this implementation**.
- Demo or real orders sent during build/audit/dry run: **zero**.
- Autotrader processes started or stopped: **zero**.
- Historical DD sizing: **not run**.
