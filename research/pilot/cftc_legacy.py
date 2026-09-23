"""Load official CFTC Legacy Futures-Only gold positioning without look-ahead."""
from __future__ import annotations

from pathlib import Path
import pandas as pd


MARKET = "GOLD - COMMODITY EXCHANGE INC."


def load(path="data/cftc_legacy", calendar_path="data/calendar.csv") -> pd.DataFrame:
    rows = []
    use = ["Market and Exchange Names", "As of Date in Form YYYY-MM-DD",
           "Noncommercial Positions-Long (All)",
           "Noncommercial Positions-Short (All)"]
    for p in sorted(Path(path).glob("*/annual.txt")):
        d = pd.read_csv(p, usecols=use, skipinitialspace=True)
        d = d[d[use[0]].str.strip() == MARKET].copy()
        rows.append(d)
    if not rows:
        return pd.DataFrame(columns=["as_of", "available", "net", "chg", "pct_rank"])
    out = pd.concat(rows, ignore_index=True).drop_duplicates(use[1])
    out["as_of"] = pd.to_datetime(out[use[1]], utc=True)
    out["net"] = (pd.to_numeric(out[use[2]]) - pd.to_numeric(out[use[3]])) / 1000.0

    # The report describes Tuesday positions.  Default availability is the
    # following Saturday 00:00 UTC, deliberately later than the normal Friday
    # release and therefore after the Friday 22:15 weekly decision boundary.
    # Where the broker calendar records the actual CFTC release timestamp, use
    # that exact timestamp instead (important for holiday/delayed releases).
    out["available"] = out["as_of"] + pd.Timedelta(days=4)
    try:
        import calendar_feed
        cal = calendar_feed.load_calendar(calendar_path)
        exact = cal[(cal.event == calendar_feed.COT_GOLD)
                    & cal.actual.notna()].sort_values("time")
        for r in exact.itertuples():
            candidates = out[(out.as_of <= pd.Timestamp(r.time, tz="UTC"))
                             & ((pd.Timestamp(r.time, tz="UTC") - out.as_of)
                                <= pd.Timedelta(days=10))]
            if len(candidates):
                idx = candidates.as_of.idxmax()
                out.loc[idx, "available"] = pd.Timestamp(r.time, tz="UTC")
    except Exception:
        pass
    out = out.sort_values("available").reset_index(drop=True)
    out["chg"] = out.net.diff()
    out["pct_rank"] = [
        float("nan") if i < 12 else 100.0 * float((out.net.iloc[:i] < out.net.iloc[i]).mean())
        for i in range(len(out))
    ]
    return out[["as_of", "available", "net", "chg", "pct_rank"]]


if __name__ == "__main__":
    x = load()
    print(x.tail().to_string(index=False))
