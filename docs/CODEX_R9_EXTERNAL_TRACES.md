Verdict: do not run or interpret the study yet. Three defects create definite look-ahead or prevent the preregistered analysis from occurring.

### Critical

1. **Both cross-asset traces contain post-cut data.** M5 bars are resampled with `.resample("1h").last()`, which labels each hourly bucket at its start. At a 22:15 cut, the included 22:00 value can contain the last M5 bar from as late as 22:55. `searchsorted(..., cut, side="right")` then admits it. This affects both `xasset_vol` and `xasset_ret`. It also conflicts with the registered Thursday cutoff.  
   `research/pilot/external_traces.py:97,170-185`; `docs/EXTERNAL_TRACE_PREREG.md:32-35,48-49`

2. **All three CFTC traces use invented—not actual—release timestamps.** The preregistration requires each report’s own timestamp, but code sets every release to Tuesday + 3 days at 20:30 UTC. Holiday-delayed and disruption-delayed reports are therefore exposed before publication, contaminating `mm_net`, `mm_pct`, and `mm_chg4`. The repository calendar itself contains multi-day and multi-week delayed CFTC releases.  
   `docs/EXTERNAL_TRACE_PREREG.md:34-35,97-99`; `research/pilot/external_traces.py:52-56,77-79,152-162`

3. **The external study is not implemented end-to-end.** `external_traces.py` only builds traces and prints coverage. `regime_atlas.py` neither imports them nor combines them with the internal traces; its main path scores only the 21 internal traces. Thus none of the promised 84 external pair-results, combined tables, intervals, or workbook output can currently be produced.  
   `docs/EXTERNAL_TRACE_PREREG.md:51-68`; `research/pilot/external_traces.py:202-209`; `research/pilot/regime_atlas.py:421-462`

### High

4. **`news_tier1` uses an ex-post calendar, not a historical schedule-as-known-at-cut.** The loader retains only final event timestamps; it has no creation/revision timestamp or calendar vintage. Reschedules, cancellations, and late additions are therefore known retrospectively. The `(cut, cut+7d]` inequality itself is correct, but its input is not point-in-time.  
   `research/pilot/external_traces.py:82-87,163-165`; `docs/EXTERNAL_TRACE_PREREG.md:47`

5. **The power table is not power for the implemented procedure.** It uses all covered onsets and an ordinary AUC approximation, while predictions begin only after 30 prior events and 30 prior non-events. Consequently:

   - news and cross-asset V-on generate no predictions at the stated totals;
   - real-yield/CFTC V-on generate virtually no printable post-burn-in events;
   - nominal-yield V-on retains only the events after the 30-event training threshold;
   - the actual primary decision is a bootstrapped Brier-skill interval, not a raw AUC test.

   Calling the listed AUCs “smallest detectable” materially overstates power.  
   `docs/EXTERNAL_TRACE_PREREG.md:77-95`; `research/pilot/regime_atlas.py:209-233,256-264`

6. **Multiplicity is described with the wrong unit.** There are 210 trace-target pairs but two reported windows, hence 420 overall pair-window intervals, before inspecting strata and rolling windows. “About 10” happens to equal roughly 2.5% of 420, but the document attributes it to 210 95% intervals. The self-check covers only expanding-window synthetic traces with the internal missingness pattern, so it does not validate external or trailing-window interval size.  
   `docs/EXTERNAL_TRACE_PREREG.md:53-60`; `research/pilot/regime_atlas.py:374-409`

7. **There is an operational-use loophole.** The text says no activation follows from history, then explicitly permits an unconfirmed, historically selected alarm to reduce live risk under a separately frozen rule. That is operational licensing before prospective confirmation. Ranking “best 3” and positive intervals further facilitates historical selection, while the generated workbook carries no no-licence/exploratory warning.  
   `docs/REGIME_MAP_PREREG.md:78-85`; `docs/EXTERNAL_TRACE_PREREG.md:62-68`; `research/pilot/regime_atlas.py:447-462`

### Medium

8. **The eight Treasury traces pass the row-date test but not a full point-in-time-vintage test.** `y2_lvl`, `y10_lvl`, `slope_2s10s`, their three changes, `y10r_lvl`, and `y10r_chg` use only dates at or before Thursday and causal lagged observations. However, the loader reads present-day historical XML without vintage or publication metadata, so later corrections cannot be detected or excluded. This is an as-of audit gap, not demonstrated leakage.  
   `research/pilot/external_traces.py:28-49,103-151`

9. **The cross-asset definitions do not match the preregistration.** `xasset_ret` is a volatility-scaled raw return, not a z-score: no trailing mean is removed and no return standard deviation is calculated. “52-week baseline required” is also false because only 30 usable past weeks are required. Code accepts two assets although the definition says the median across three, and imposes no end-of-week freshness check.  
   `docs/EXTERNAL_TRACE_PREREG.md:48-49,91-95`; `research/pilot/external_traces.py:166-188`

10. **CFTC percentile history is off by one and underspecified.** The amendment says 26 prior reports; code starts with 25 prior plus the current report. It also uses strict `<`, so ties are excluded and the maximum empirical percentile is below 100.  
    `docs/EXTERNAL_TRACE_PREREG.md:45,97-99`; `research/pilot/external_traces.py:158-160`

11. **The promised reporting safeguards are not implemented correctly.** “First ready week” is actually the first week where trace and outcome coexist, before the 30/30 readiness threshold. Bootstrap intervals are produced only for Brier skill and lift—not AUC, precision, sensitivity, FPR, or FDR. Console output omits FDR and provides positive rows/best-three rather than one complete sorted table per target.  
    `docs/REGIME_MAP_PREREG.md:62-76`; `research/pilot/regime_atlas.py:256-296,423-455`

### Low

12. **Calendar coverage can encode incomplete history as zero.** The lower-bound test allows cuts as early as one week before the first calendar observation; those weeks receive a numeric zero rather than missing. “Distinct releases” are also counted as distinct timestamps, collapsing simultaneous qualifying releases.  
    `research/pilot/external_traces.py:86-87,163-165`

13. **The moving-block bootstrap excludes the final legal block start.** `integers` has an exclusive upper bound, but the code supplies `span - BLOCK` rather than `span - BLOCK + 1`.  
    `research/pilot/regime_atlas.py:277-295`

14. **“Gap-free” is not enforced.** The full-run assertion detects only gaps exceeding eight days; shorter data outages are allowed despite the preregistered requirement. Weekly invalidation mitigates some consequences but does not establish a gap-free cache.  
    `docs/REGIME_MAP_PREREG.md:8-14`; `research/pilot/regime_atlas.py:47-58,419-420`

No direct look-ahead was found in the lag/change arithmetic of the eight Treasury traces, or in the CFTC percentile/change transformations once true availability is supplied. No files were edited.