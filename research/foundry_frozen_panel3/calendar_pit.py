"""Point-in-time economic calendar (Codex round 16). Append-only log of releases as FIRST seen:
data/foundry/shadow/calendar_pit.csv. The weekly job calls update() after refreshing data/calendar.csv;
a row is appended for a value_id the first time it appears, and once more the first time its `actual`
is filled. The reader keeps, per value_id, the forecast/previous of its first row and the actual of its
first row that has one - later revisions of an already-published actual are never applied.
Timezone guard: 'Initial Jobless Claims' must sit at hh:30 UTC with hh in {12, 13} for >= 90 % of
the refreshed rows (US 08:30 ET); otherwise nothing is appended and the reason is printed."""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
PIT = ROOT / "data" / "foundry" / "shadow" / "calendar_pit.csv"
COLS = ["value_id", "event_id", "time", "epoch", "currency", "event", "importance", "actual", "forecast", "previous",
        "revised_previous", "recorded_utc"]


def _load_calendar(path):
    if str(Path(__file__).resolve().parent) not in sys.path:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
    try:
        import calendar_feed as C
    except ImportError:
        sys.path.insert(0, str(ROOT / "research" / "pilot"))
        import calendar_feed as C
    return C.load_calendar(str(path))


def tz_ok(cal):
    x = cal[cal.event == "Initial Jobless Claims"]
    if len(x) < 5:
        return False, f"only {len(x)} claims rows in the refreshed dump - cannot verify the timezone (fail closed)"
    t = pd.to_datetime(x.epoch, unit="s")
    share = float(((t.dt.minute == 30) & t.dt.hour.isin([12, 13])).mean())
    return share >= 0.9, f"claims at 12:30/13:30 UTC: {share:.0%}"


def update(calendar_csv=ROOT / "data" / "calendar.csv", check_csv=None):
    """check_csv: the freshly dumped file; the timezone guard runs on IT (R17), not on the merged history."""
    cal = _load_calendar(calendar_csv)
    ok, why = tz_ok(_load_calendar(check_csv) if check_csv else cal)
    if not ok:
        print("calendar_pit: TIMEZONE GUARD FAILED -", why, "- nothing appended"); return 1
    old = pd.read_csv(PIT) if PIT.exists() and PIT.stat().st_size > 0 else pd.DataFrame(columns=COLS)
    seen = set(old.value_id.astype(np.int64)) if len(old) else set()
    have_actual = set(old[old.actual.notna()].value_id.astype(np.int64)) if len(old) else set()
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    c = cal.copy()
    c["value_id"] = c.value_id.astype(np.int64)
    new_rows = c[~c.value_id.isin(seen)]
    filled = c[c.value_id.isin(seen - have_actual) & c.actual.notna()]
    add = pd.concat([new_rows, filled])
    if len(add):
        add = add.assign(recorded_utc=now)[COLS]
        add.to_csv(PIT, mode="a", header=not (PIT.exists() and PIT.stat().st_size > 0), index=False, float_format="%.17g")
    print(f"calendar_pit: {why}; appended {len(new_rows)} new releases and {len(filled)} newly published actuals")
    return 0


def load_pit():
    """Calendar frame in calendar_feed.load_calendar's shape, point-in-time as described above."""
    P = pd.read_csv(PIT, float_precision="round_trip")
    P = P.sort_values(["value_id", "recorded_utc"], kind="stable")
    first = P.groupby("value_id").head(1).set_index("value_id")
    act = P[P.actual.notna()].groupby("value_id").head(1).set_index("value_id").actual
    first["actual"] = act.reindex(first.index)
    return first.reset_index().sort_values(["epoch", "value_id"], kind="stable").reset_index(drop=True)  # chronological


if __name__ == "__main__":
    sys.exit(update(check_csv=sys.argv[1] if len(sys.argv) > 1 else None))
