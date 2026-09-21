"""
Calendar feed — turns the MT5 economic calendar into what news.py needs.

`news.surprise_z` returns None unless an Event carries a `sigma`, and a None
surprise is a NO_TRADE by construction. So the missing piece was never just
"no calendar": it was that nothing computed the historical dispersion of
(actual - consensus) per series. With MQL5/Scripts/CalendarDump.mq5 exporting
10,211 rows over 522 days, that dispersion is measurable.

Three rules this module refuses to break:

1. **Sigma is trailing, never full-sample.** Standardising an event with a
   dispersion computed from data that includes it - and includes everything
   after it - is look-ahead. Every sigma here uses PRIOR observations of the
   same series only, and is None until `MIN_HISTORY` of them exist.

2. **The gold sign is declared, never inferred.** news.Event documents
   `higher_is_gold_negative` as a property of the series. Series whose sign is
   genuinely two-sided are marked AMBIGUOUS and EXCLUDED rather than assigned a
   direction that happens to fit. Inflation is the honest example: a hot CPI is
   gold-bullish as a hedge and gold-bearish through the Fed, and which one wins
   is a regime question, not a definition.

3. **Positioning is reported when it exists and not otherwise.** The calendar
   carries CFTC Gold Non-Commercial Net Positions weekly, so `positioning` can
   stop being NOT ASSESSED - but only for timestamps after a release, and only
   with the report's own lag stated.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

MIN_HISTORY = 8          # prior prints of a series before its sigma is usable
COT_TRAILING_WEEKS = 52  # window for the crowding percentile

# --------------------------------------------------------------- sign table
# True  -> a HIGHER print is gold-NEGATIVE (strong economy, firmer USD/yields)
# False -> a HIGHER print is gold-POSITIVE (weaker economy)
# None  -> genuinely two-sided; excluded from hypothesis formation
GOLD_SIGN: dict[str, bool | None] = {
    # labour: strength is gold-negative
    "Nonfarm Payrolls": True,
    "ADP Nonfarm Employment Change": True,
    "JOLTS Job Openings": True,
    "Average Hourly Earnings m/m": True,
    "Average Hourly Earnings y/y": True,
    "Nonfarm Payrolls Private": True,
    # labour: weakness is gold-positive, so higher = gold-positive
    "Unemployment Rate": False,
    "Initial Jobless Claims": False,
    "Continuing Jobless Claims": False,
    # activity surveys: strength is gold-negative
    "ISM Manufacturing PMI": True,
    "ISM Non-Manufacturing PMI": True,
    "ISM Manufacturing Employment": True,
    "ISM Non-Manufacturing Employment": True,
    "ISM Manufacturing New Orders": True,
    "ISM Non-Manufacturing New Orders": True,
    "S&P Global Manufacturing PMI": True,
    "S&P Global Services PMI": True,
    "S&P Global Composite PMI": True,
    "Philadelphia Fed Manufacturing Index": True,
    "Chicago PMI": True,
    "Industrial Production m/m": True,
    "Retail Sales m/m": True,
    "Core Retail Sales m/m": True,
    "Durable Goods Orders m/m": True,
    "GDP q/q": True,
    "GDP Price Index q/q": True,
    "CB Consumer Confidence": True,
    "Michigan Consumer Sentiment": True,
    "New Home Sales": True,
    "Existing Home Sales": True,
    "Building Permits": True,
    "Housing Starts": True,

    # AMBIGUOUS - excluded. A hot print is gold-bullish as an inflation hedge
    # and gold-bearish through the policy path. Which dominates is a regime
    # question this module will not pretend to settle.
    "CPI m/m": None,
    "CPI y/y": None,
    "Core CPI m/m": None,
    "Core CPI y/y": None,
    "PPI m/m": None,
    "Core PPI m/m": None,
    "PCE Price Index m/m": None,
    "Core PCE Price Index m/m": None,
    "Core PCE Price Index y/y": None,
    "ISM Manufacturing Prices Paid": None,
    "ISM Non-Manufacturing Prices Paid": None,
    "Fed Interest Rate Decision": None,
    "Trade Balance": None,
    "EIA Crude Oil Stocks Change": None,   # an oil series, not a gold driver
}

COT_GOLD = "CFTC Gold Non-Commercial Net Positions"


# ------------------------------------------------------------------ loading
def load_calendar(path="data/calendar.csv") -> pd.DataFrame:
    """Read the dump and return it sorted, with epoch seconds attached.

    The MQL5 script writes broker server time. The exporter measured this
    server at +0.00 hours from UTC and the dump's own USD HIGH cluster sits at
    12:30, which is 08:30 New York - the release time of payrolls and CPI. Two
    independent facts agreeing is why these timestamps are treated as UTC.
    """
    p = Path(path)
    raw = p.read_bytes()
    try:
        txt = raw.decode("utf-8")
    except UnicodeDecodeError:
        # MQL5 FileOpen(..., FILE_ANSI) writes the machine's ANSI codepage
        txt = raw.decode("cp1252")
    import io
    df = pd.read_csv(io.StringIO(txt))
    df["time"] = pd.to_datetime(df["time"], format="mixed")
    df = df.sort_values("time").reset_index(drop=True)
    df["epoch"] = (df["time"].astype("int64") // 10**9).astype("int64")
    return df


# ------------------------------------------------------------ trailing sigma
def trailing_sigma(df: pd.DataFrame, min_history: int = MIN_HISTORY) -> pd.Series:
    """sd of (actual - forecast) over PRIOR prints of the same series.

    Expanding, shifted by one, so the value standardising an event never saw
    that event or anything after it. NaN until `min_history` priors exist,
    which news.surprise_z correctly turns into NO_TRADE rather than a zero.
    """
    surprise = df["actual"] - df["forecast"]
    out = pd.Series(np.nan, index=df.index, dtype=float)
    for name, idx in df.groupby("event", sort=False).groups.items():
        s = surprise.loc[idx]
        prior = s.shift(1).expanding(min_periods=min_history).std()
        out.loc[idx] = prior
    return out


# ------------------------------------------------------------------- events
@dataclass
class EventRow:
    epoch: int
    name: str
    importance: str
    actual: float | None
    consensus: float | None
    previous: float | None
    previous_revised: float | None
    sigma: float | None
    higher_is_gold_negative: bool | None

    @property
    def usable(self) -> bool:
        return (self.higher_is_gold_negative is not None
                and self.sigma is not None and np.isfinite(self.sigma)
                and self.sigma > 0 and self.actual is not None
                and self.consensus is not None)


def build_events(df: pd.DataFrame, currency="USD",
                 importance=("HIGH",)) -> list[EventRow]:
    """Every release of the chosen currency and importance, with its trailing
    sigma and declared sign. Unusable ones are returned too, carrying the
    reason in their fields, so the caller can count what was dropped and why
    instead of silently seeing fewer events."""
    d = df[(df.currency == currency) & (df.importance.isin(importance))].copy()
    d["sigma"] = trailing_sigma(d.reset_index(drop=True)).values
    out = []
    for r in d.itertuples():
        out.append(EventRow(
            epoch=int(r.epoch), name=str(r.event), importance=str(r.importance),
            actual=None if pd.isna(r.actual) else float(r.actual),
            consensus=None if pd.isna(r.forecast) else float(r.forecast),
            previous=None if pd.isna(r.previous) else float(r.previous),
            previous_revised=(None if pd.isna(r.revised_previous)
                              else float(r.revised_previous)),
            sigma=None if pd.isna(r.sigma) else float(r.sigma),
            higher_is_gold_negative=GOLD_SIGN.get(str(r.event)),
        ))
    return out


def to_news_events(rows: list[EventRow]):
    """Convert to news.Event. Only usable rows are converted - an unusable one
    would enter news.assess as a None surprise and turn the whole window into
    NO_TRADE, hiding the fact that a different, usable release shared it."""
    import news
    return [news.Event(t=r.epoch, name=r.name, importance=r.importance,
                       actual=r.actual, consensus=r.consensus,
                       previous=r.previous, previous_revised=r.previous_revised,
                       sigma=r.sigma,
                       higher_is_gold_negative=bool(r.higher_is_gold_negative))
            for r in rows if r.usable]


# -------------------------------------------------------------- positioning
def positioning_series(df: pd.DataFrame) -> pd.DataFrame:
    """CFTC gold net positions with a trailing crowding percentile.

    The percentile uses prior weeks only. The release lag is real and is not
    smoothed away: the CFTC reports Tuesday's book on Friday, so the value
    published at time t describes the market three days earlier, and any caller
    must treat it as such.
    """
    g = df[df.event == COT_GOLD].dropna(subset=["actual"]).copy()
    g = g.sort_values("time").reset_index(drop=True)
    g["pct_rank"] = [
        (np.nan if i < 12 else
         100.0 * (g["actual"].iloc[:i] < g["actual"].iloc[i]).mean())
        for i in range(len(g))
    ]
    g["chg"] = g["actual"].diff()
    return g[["time", "epoch", "actual", "previous", "chg", "pct_rank"]]


def positioning_at(pos: pd.DataFrame, epoch: int) -> str:
    """The most recent CFTC print STRICTLY BEFORE `epoch`, as a sentence, or
    the NOT ASSESSED string news.Assessment defaults to when none exists."""
    prior = pos[pos.epoch < epoch]
    if len(prior) == 0:
        return "NOT ASSESSED: no CFTC print before this event"
    r = prior.iloc[-1]
    age_d = (epoch - int(r.epoch)) / 86400.0
    pct = "unknown" if not np.isfinite(r.pct_rank) else f"{r.pct_rank:.0f}th pct"
    return (f"CFTC gold net non-commercial {r.actual:,.1f}k, "
            f"change {r.chg:+,.1f}k, {pct} of the prior 52 weeks, "
            f"reported {age_d:.1f} days earlier (survey date earlier still)")


# ------------------------------------------------------------------ report
def main() -> int:
    df = load_calendar()
    print("=" * 78)
    print("CALENDAR FEED")
    print("=" * 78)
    print(f"rows {len(df):,}  {df.time.min()} .. {df.time.max()}")

    rows = build_events(df, "USD", ("HIGH",))
    usable = [r for r in rows if r.usable]
    print(f"\nUSD HIGH releases              : {len(rows):,}")
    print(f"  usable (sign + sigma + both) : {len(usable):,}")

    from collections import Counter
    why = Counter()
    for r in rows:
        if r.usable:
            continue
        if r.higher_is_gold_negative is None:
            why["no declared sign (ambiguous or unlisted)"] += 1
        elif r.actual is None or r.consensus is None:
            why["missing actual or consensus"] += 1
        else:
            why[f"sigma not yet estimable (<{MIN_HISTORY} priors)"] += 1
    for k, v in why.most_common():
        print(f"  dropped: {k:44s} {v:5,d}")

    print("\n  usable by series:")
    c = Counter(r.name for r in usable)
    for n, k in c.most_common(12):
        sig = np.median([r.sigma for r in usable if r.name == n])
        print(f"    {k:4d}  sigma~{sig:10.4f}  {n}")

    pos = positioning_series(df)
    print(f"\nCFTC gold positioning prints   : {len(pos):,}")
    if len(pos):
        print("  latest 3:")
        for r in pos.tail(3).itertuples():
            pct = "n/a" if not np.isfinite(r.pct_rank) else f"{r.pct_rank:.0f}th"
            print(f"    {r.time}  net {r.actual:>8,.1f}k  chg {r.chg:+7.1f}k  {pct} pct")
        if usable:
            print("\n  positioning as news.py would see it at the last usable event:")
            print("   ", positioning_at(pos, usable[-1].epoch))

    print("\nNothing above reads a market price. No order is placed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
