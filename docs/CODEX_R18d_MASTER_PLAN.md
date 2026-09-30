## R18d review

| Item | Status | Exact contract line and finding |
|---|---|---|
| **R18b-1** | **PARTIAL** | Independent consumption is correctly specified: “`the shadow ledger ... and the live ledger ... each consume the potential-signal table independently`” ([C2 lines 22–24](C:/Users/66985/Documents/EA-tread/docs/WRWR_CONTRACT_PREREG.md:22)). However, line 24 says “`Any skipped live signal, for any reason, leaves that candidate live-flat`.” A signal is also skipped when the candidate already has an open position ([lines 29–32](C:/Users/66985/Documents/EA-tread/docs/WRWR_CONTRACT_PREREG.md:29)), while positions may never be force-closed ([line 36](C:/Users/66985/Documents/EA-tread/docs/WRWR_CONTRACT_PREREG.md:36)). Those rules cannot all hold simultaneously. |
| **R18b-2** | **RESOLVED** | “`entry-bar open_time in the OPEN interval (cut_k, cut_{k+1})`” and “`opens exactly at a cut is rejected`,” with event order `exits -> cut processing -> entries` ([C1 lines 13–15](C:/Users/66985/Documents/EA-tread/docs/WRWR_CONTRACT_PREREG.md:13)). |
| **R18b-5** | **RESOLVED** | The complete 64-hex symbol-file digest is recorded ([C4 lines 49–50](C:/Users/66985/Documents/EA-tread/docs/WRWR_CONTRACT_PREREG.md:49)). Historical swap is an annual percentage of notional using the latest Treasury date strictly before rollover day, fixed markups, a pre-2016 fallback, exact night counts, and `(entry open time, exit bar close time]` charging ([lines 62–67](C:/Users/66985/Documents/EA-tread/docs/WRWR_CONTRACT_PREREG.md:62)). |
| **R18b-7** | **RESOLVED** | Activation is cut-known: “`j selects n_k = the number of candidates with score > 0`” ([C6 lines 83–89](C:/Users/66985/Documents/EA-tread/docs/WRWR_CONTRACT_PREREG.md:83)). The bootstrap object is explicitly “`the T x 144 matrix of weekly (R_{j,k}, B_{j,k}) pairs`”; fixed configurations are not re-simulated, while any return-dependent meta-selector is recomputed inside each replicate ([lines 90–95](C:/Users/66985/Documents/EA-tread/docs/WRWR_CONTRACT_PREREG.md:90)). |
| **R18b-9** | **RESOLVED** | The placebo construction now specifies geometric block segmentation without reordering, blockwise Rademacher signs, OHLC/gap mirroring, higher-TF rebuilding, unchanged external series, and whole-pipeline recomputation ([C11 lines 153–160](C:/Users/66985/Documents/EA-tread/docs/WRWR_CONTRACT_PREREG.md:153)). Flag contrasts use fixed effects with equal bar weights and 20/20 cell minimums ([lines 166–168](C:/Users/66985/Documents/EA-tread/docs/WRWR_CONTRACT_PREREG.md:166)); the family-generation and maxT rules are fixed at [lines 169–172](C:/Users/66985/Documents/EA-tread/docs/WRWR_CONTRACT_PREREG.md:169). |
| **R18b-10** | **PARTIAL** | C8 correctly removes the exemption: “`every week from the first cut is included`,” with reconstruction or `g = -4` after eight weeks ([lines 123–126](C:/Users/66985/Documents/EA-tread/docs/WRWR_CONTRACT_PREREG.md:123)). But “`entered when complete`” does not specify whether later weeks are withheld, appended first, or later recomputed when the missing earlier week arrives. Those choices produce different anytime e-process paths and stopping events. Additionally, mandatory raw-R reporting ([line 122](C:/Users/66985/Documents/EA-tread/docs/WRWR_CONTRACT_PREREG.md:122)) is impossible for a week declared unreconstructable under line 126. |
| **R18b-4** | **RESOLVED** | “`timestamps strictly increasing and unique`” is explicit ([C5 line 73](C:/Users/66985/Documents/EA-tread/docs/WRWR_CONTRACT_PREREG.md:73)); the holiday-list construction and manifest hashing are specified at [lines 74–77](C:/Users/66985/Documents/EA-tread/docs/WRWR_CONTRACT_PREREG.md:74). |

No item is **OPEN**.

## BLOCKING

1. **C2 has contradictory skip semantics.** Replace “leaves that candidate live-flat” with an executable rule such as: a skipped signal creates no position and does not alter an existing position; a candidate that was flat remains flat.

2. **C8 does not preserve a defined chronological e-process under delayed reconstruction.** Require later weeks to remain pending until every earlier week is reconstructed or assigned `g=-4`, then append strictly in cut order; alternatively freeze another provably valid delayed-observation rule. Permit raw R to be `NA` with an audit reason when reconstruction is impossible.

## MINOR

- C4 should name the Treasury field/source snapshot—such as `BC_2YEAR`—and its digest, and call `+0.02/−0.20` percentage-point markups.
- C5 should record the actual generated holiday digest and pandas version before use.
- C11 should record the actual family digest and placebo seeds before real-statistic calculation; the master-plan precedence text should also stop referring to contract “v2.”

NOT OK UNTIL: C2 makes skipped-signal state transitions non-contradictory, and C8 fixes chronological treatment of delayed weeks and unreconstructable raw returns.