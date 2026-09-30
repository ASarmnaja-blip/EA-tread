"""HistData local time -> UTC (2026-10-01; docs/WRWR_HISTORY_OOS_PREREG.md Amendment 1). Every US/EU daylight-saving transition window
was classified against Dukascopy gold (UTC) and Exness: files up to 2018 follow New York time with US summer time; from 2019 they are
EST (UTC-5) plus one hour while EUROPE is on summer time (gold 2019-2021 and silver 2019-2026 transition weeks were 1 h early under the
New York rule; after this rule every window matches at shift 0). Same rule as research/wrwr/xag.py histdata_utc()."""
from __future__ import annotations

import numpy as np
import pandas as pd

SWITCH = pd.Timestamp("2019-01-01")


def histdata_utc(ts):
    """ts: HistData 'YYYYMMDD HHMMSS' strings -> float Series of UTC epoch seconds (NaN for ambiguous / nonexistent New York times)."""
    local = pd.to_datetime(ts, format="%Y%m%d %H%M%S")
    old = local < SWITCH
    out = pd.Series(np.nan, index=local.index)
    ny = local[old].dt.tz_localize("America/New_York", ambiguous="NaT", nonexistent="NaT").dt.tz_convert("UTC").dt.tz_localize(None)
    out[old] = ny.astype("datetime64[s]").astype("int64").where(ny.notna(), np.nan)
    utc0 = local[~old] + pd.Timedelta(hours=5)
    eu = (utc0.dt.tz_localize("UTC").dt.tz_convert("Europe/London").dt.tz_localize(None) - utc0) == pd.Timedelta(hours=1)
    out[~old] = (utc0 - pd.to_timedelta(eu.astype(int), unit="h")).astype("datetime64[s]").astype("int64")
    return out
