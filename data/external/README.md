# External WPWB trace data (Codex, retrieved 2026-09-28)

These are first-party public files fetched for the tests frozen in
`docs/WPWB_LIVE_PREREG.md` amendments 7 and 7a. They are research inputs only;
no broker or order API was used. `manifest.json` records the retrieval time,
exact URL, final redirected URL, byte count, and SHA-256 of every raw file.

## Sources and fields used

- **U.S. Treasury daily nominal par yield curve**, yearly XML for 2016-2026:
  `https://home.treasury.gov/resource-center/data-chart-center/interest-rates/pages/xml?data=daily_treasury_yield_curve&field_tdr_date_value=YYYY`.
  Fields: `NEW_DATE`, `BC_2YEAR`, and `BC_10YEAR`.
- **U.S. Treasury daily real par yield curve**, yearly XML for 2021-2026:
  `https://home.treasury.gov/resource-center/data-chart-center/interest-rates/pages/xml?data=daily_treasury_real_yield_curve&field_tdr_date_value=YYYY`.
  Fields: `NEW_DATE` and `TC_10YEAR`.
- **Cboe Gold ETF Volatility Index (GVZ)** daily history:
  `https://cdn.cboe.com/api/global/us_indices/daily_prices/GVZ_History.csv`
  (redirected by Cboe to its `cdn-api.cboe.com` host). Fields: `DATE`, `GVZ`.
- **CFTC Disaggregated Futures-Only Commitments of Traders**, annual ZIP files
  for 2021-2026:
  `https://www.cftc.gov/files/dea/history/fut_disagg_txt_YYYY.zip`.
  Market: `GOLD - COMMODITY EXCHANGE INC.` / contract code `088691`. Fields:
  report date and managed-money long/short positions.

The Treasury XML endpoint and field families are documented by the Treasury's
“Daily Interest Rate XML Feed.” The CFTC states that disaggregated reports
separate managed money and that positions are as of Tuesday; causal availability
here follows the actual CFTC release timestamp in `data/calendar.csv` where
present. If no exact release is present, availability defaults to Saturday
00:00 UTC, deliberately too late for that Friday's 22:15 UTC rebuild.

## Causal transformations

- At a Friday 22:15 UTC rebuild, Treasury and GVZ values are dated no later
  than Thursday.
- A 13-week change is the current eligible observation minus the observation
  63 trading rows earlier.
- GVZ risk premium is GVZ divided by annualised trailing-20-day realised gold
  volatility, with gold observations also ending no later than Thursday.
- Managed-money net is long minus short. `C1` is its percentile within the
  trailing 52 available reports (minimum 12); `C2` is its four-report change.
- Missing values remain missing. No future fill is used.

Retrieval is reproducible with `research/wpwb_live/fetch_external.py`. The
single pre-registered analysis is `research/wpwb_live/external_traces.py`.
