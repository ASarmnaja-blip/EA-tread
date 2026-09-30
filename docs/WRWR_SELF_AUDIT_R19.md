# WRWR self-audit of the R19 findings (2026-09-30)
Operator instruction: "ตรวจเองเลยไม่ต้องรอ codex". This is a SELF-audit by the author of the code, not an independent
review (CLAUDE.md §7 separation of roles). Codex can still be asked to confirm before any alpha is spent.

| R19 item | status | fix | evidence (all reproducible) |
|---|---|---|---|
| R19-1 equity = realised balance | FIXED | `portfolio.simulate`: equity(t) = balance + mark-to-market of open positions (price move - entry cost, swap at exit), used for U_k, sizing, the 3 x f cap, free margin | `test_portfolio.py` (MTM sizing 0.10 -> 0.14 lot with +10% open position; entry cost charged at once; shorts lose when the mark rises) |
| R19-2 H4/D1 spread = bar median | FIXED | `signals.resample`: first constituent H1 bar's recorded ask-bid | `test_integrity.py` (H4/D1 spread equals the H1 spread at the same timestamp) |
| R19-3 C5 integrity not fail-closed | FIXED | tables carry data sha (incl. volume), raw-manifest sha (562 Dukascopy files), symbol / Treasury / code / cut digests, array digest; `signals.load` recomputes and rejects; pool asserts counts and widths; family cache has metadata; `contracts.validate_seam` implements the splice checks | `test_integrity.py` (7 kinds of tampering rejected), `test_contracts.py` (seam validator: clean passes; offset, spread ratio, jump, 5-day gap, duplicate timestamps rejected) |
| R19-4 audit trail | FIXED | tables store dir, gross_bp, cost_bp, swap_bp; at-cut rejections stored (0 for H1/H4/D1); every live skip logged with rule ID and state | `test_portfolio.py` skip-log assertions; tables report `rejected_at_cut = 0` |
| R19-5 C3 | FIXED | `weekly_rv(bar_seconds=3600)` refuses other bar lengths; `causal_vol_scale(mode="historical"\|"forward")` | `test_contracts.py` |
| R19-6 f levels | FIXED | `run_family.py` runs f = 0.5 / 1 / 2 % | `data/wrwr/family_XAUUSD.xlsx` column `f` |
| R19-7 XAG constant | FIXED | `data/foundry/xag_cost_freeze.json` (median spread 7.08 bp over 217,286 Exness M5 bars -> 11.6 bp), `cost_bp('XAGUSD')` fails closed | `test_contracts.py` |
| R19-8 decomposition | REDONE | full factorial (`decompose_factorial.py`) | ledger section "Factorial decomposition" |
| R19-9 holiday digest | FIXED | LF file + `.gitattributes`; digest defined on LF-normalised text | `test_contracts.py` |
Extra checks added by the self-audit: signal/ATR leak test on H1, H4 and D1 at three cut points each (`test_signal_leak.py`,
PASS); XAG spread units (price units, not points) caught and corrected before the constant was frozen.
