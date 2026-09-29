## Verdict

Not ready for the first FORWARD cut. The shadow cannot programmatically change the existing risk report, sizing, or orders, but the forward evidence can become incomplete, mutable, or incorrectly scored.

Only the 2026-09-25 DRY_RUN row and its ensemble exist; no forward log exists yet.

## Findings

1. **BLOCKER — Exness history is not durable and will eventually break HAR/MVOL permanently.**  
   Shadow reconstructs all post-splice RV from `bars.load_bars(frozen=False)` ([outlook_shadow.py:99](</C:/Users/66985/Documents/EA-tread/research/wpwb_weekly/outlook_shadow.py:99>)). The weekly fetch overwrites one NPZ with only the latest 60 days ([bars.py:79](</C:/Users/66985/Documents/EA-tread/research/wpwb_weekly/bars.py:79>), [bars.py:105](</C:/Users/66985/Documents/EA-tread/research/wpwb_weekly/bars.py:105>)); loading merely appends that rolling file after the fixed base ([bars.py:41](</C:/Users/66985/Documents/EA-tread/research/wpwb_weekly/bars.py:41>)). Once the rolling window no longer overlaps the fixed base, a permanent gap appears. Because HAR/MVOL require 26 consecutive finite lags, they will cease issuing, and old realised weeks will disappear when `outlook_shadow_scores.csv` is recomputed.

2. **HIGH — Forward scoring does not implement the registered score contract.**  
   It records only CRPS, QLIKE and 80% coverage ([outlook_shadow.py:249](</C:/Users/66985/Documents/EA-tread/research/wpwb_weekly/outlook_shadow.py:249>)). RPS, onset Brier, exit Brier and 95% coverage promised by the preregistration are absent. It also scores whatever models happen to exist instead of the development contract’s common issued set. Paired reporting covers CRPS only, omits calendar positions when calling the block bootstrap, and uses global row count rather than paired count ([outlook_shadow.py:263](</C:/Users/66985/Documents/EA-tread/research/wpwb_weekly/outlook_shadow.py:263>)). With 26 partial rows, missing model columns or an empty difference can raise instead of reporting.

3. **HIGH — The actual forecast distributions are mutable and unauthenticated.**  
   CRPS depends on separate NPZ ensemble files, but their SHA-256 is not stored in the immutable CSV row. Scoring trusts whichever file currently occupies the predictable pathname ([outlook_shadow.py:244](</C:/Users/66985/Documents/EA-tread/research/wpwb_weekly/outlook_shadow.py:244>)). The NPZ is written before the row ([outlook_shadow.py:201](</C:/Users/66985/Documents/EA-tread/research/wpwb_weekly/outlook_shadow.py:201>)); a crash after that write allows a rerun to overwrite the orphan. Neither NPZ nor CSV append is atomic or locked, so concurrent runs can also duplicate or replace evidence.

4. **HIGH — Partial/failure rows corrupt the CSV schema.**  
   `append()` derives field order independently from each row instead of using a fixed schema ([outlook_shadow.py:142](</C:/Users/66985/Documents/EA-tread/research/wpwb_weekly/outlook_shadow.py:142>)). Fields are conditional on GVZ success and model issuance. A partial row written after a full header shifts values into the wrong columns; if the first FORWARD row is partial, a later full row can contain more fields than its header and make `pd.read_csv` fail.

5. **HIGH — Late runs are accepted as prospective forecasts; missed cuts are never backfilled.**  
   `last_cut_before(now)` always selects the latest cut and there is no lateness bound or `--cut` recovery path ([outlook_shadow.py:151](</C:/Users/66985/Documents/EA-tread/research/wpwb_weekly/outlook_shadow.py:151>)). If the PC starts Monday, the Friday forecast is logged after observing part of its target week. If it is off across two Fridays, only the newest cut is logged. Even the normal 06:00 Bangkok schedule generates at approximately 23:00 UTC—45 minutes after the registered 22:15 cut. Price/GVZ indexing remains causal, but the record is not demonstrably made at the cut.

6. **HIGH — GVZ revision control does not match the preregistration.**  
   The code compares every overlapping row only against the development file ([outlook_shadow.py:81](</C:/Users/66985/Documents/EA-tread/research/wpwb_weekly/outlook_shadow.py:81>)). It never compares the selected Thursday against every earlier downloaded snapshot, nor logs the old/new Thursday values. Consequently a revision relative to last week’s snapshot can go undetected. Moreover, every run rebuilds all historical G features from the newest full-history file, so past “out-of-sample” residuals can change with later GVZ revisions.

7. **MEDIUM — Incomplete Exness weeks can be accepted, and scoring can occur before week-end.**  
   Completeness requires only global feed end within six hours of the boundary plus the generic 80-bar rule ([outlook_shadow.py:101](</C:/Users/66985/Documents/EA-tread/research/wpwb_weekly/outlook_shadow.py:101>)). There is no timestamp-continuity test, so internal gaps or up to six missing closing hours can enter RV. More seriously, `score_all(now)` never checks wall-clock completion: once the feed reaches boundary-minus-six-hours, `--score` can score a still-running week ([outlook_shadow.py:229](</C:/Users/66985/Documents/EA-tread/research/wpwb_weekly/outlook_shadow.py:229>)).

8. **MEDIUM — Residual pools are causal but not calendar-matched.**  
   Ensembles are correctly formed before appending residual k, and use exactly 104 residuals ([outlook_dev.py:120](</C:/Users/66985/Documents/EA-tread/research/wpwb_weekly/outlook_dev.py:120>)). However, each model independently skips unavailable predictions, so its last 104 residuals can cover different weeks. That contradicts the amended development contract’s claim of calendar parity and becomes material with GVZ or Exness gaps.

9. **MEDIUM — “Fixed” Dukascopy history is read from a mutable cache.**  
   Every run calls `O.load()` ([outlook_shadow.py:96](</C:/Users/66985/Documents/EA-tread/research/wpwb_weekly/outlook_shadow.py:96>)), which assembles all current cache files rather than loading a frozen development snapshot ([build_all_tf.py:43](</C:/Users/66985/Documents/EA-tread/research/history/build_all_tf.py:43>)). The logged RV hash detects the resulting row’s values but does not refuse historical changes or preserve the input series.

10. **MEDIUM — Only network failure degrades cleanly.**  
    A caught HTTP failure permits B0/HAR and suppresses MVOL. But a truncated, HTML, malformed, or schema-changed download is first marked `OK` and saved, then parsing raises ([outlook_shadow.py:74](</C:/Users/66985/Documents/EA-tread/research/wpwb_weekly/outlook_shadow.py:74>)). No shadow row is produced, so the promised B0/HAR record is lost. A crash after append but before `write_latest` also leaves the latest summary stale, while rerun refusal prevents repair.

## Operational isolation

No direct code path from shadow outputs into `weekly_report.py`, `vol_scale`, `effective_scale`, `riskrules.py`, or order APIs was found. The scheduler generates the report first, keeps its return code, and runs shadow afterward under a non-blocking exception handler ([run_weekly.py:131](</C:/Users/66985/Documents/EA-tread/research/wpwb_weekly/run_weekly.py:131>), [run_weekly.py:138](</C:/Users/66985/Documents/EA-tread/research/wpwb_weekly/run_weekly.py:138>)). The remaining operational route is human: `outlook_shadow_latest.md` displays actionable-looking probabilities despite its shadow warning.