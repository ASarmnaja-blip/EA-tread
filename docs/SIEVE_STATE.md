# Sieve state (for resuming; 2026-09-30 10:31 Bangkok)
- Prereg: docs/SIEVE_PREREG.md (+ Amendments 1, 2). Code: research/sieve/features.py, research/sieve/run_scan.py.
- Scan A statistic history: within-month Spearman IC withdrawn (look-ahead, 5,250 survivors); Amendment 1
  (trailing-demeaned timing edge) failed placebo (2,514 survivors); Amendment 2 (constant per-period drift)
  ALSO failed placebo: 2,534 survivors (`data/sieve/scan_A_PLACEBO.log`). Real scan A under Amendment 2 NOT run yet.
- Placebo = `mirror()` in run_scan.py (per-bar random sign flip). Placebo survivors are level features
  (c_sma200, pw_range_pos, z100, donch55_pos...) inside level-tercile masks (ret120_HI, z100_LO...), mean t -0.40
  on the ALL mask at h=1 too -> a bias that detrending does not explain.
- NEXT: find the bias with a direct check on the placebo (x = rank of c_sma200, y h=1, ALL): overall mean of x*y,
  per-month s_m, whether the mirror path is a martingale in OPENS (target uses opens) - suspect the mirror or the
  a14 / clip normalisation. Fix, write Amendment 3, re-run placebo until <= a handful survive, then real A, B, B2,
  then layers 3-5. Do not read real-scan results before the placebo passes.
