r"""News file for the G27K EA in the Strategy Tester, where the MQL5 economic calendar is not available.

Writes the USD HIGH events of data/calendar.csv (the calendar the research filter used, UTC = Exness server time) as one
"YYYY.MM.DD HH:MM" per line, the format the EA reads from Common\Files when InpNewsSource is NEWS_AUTO in the tester or NEWS_FILE.

Usage: python research/g27k_dev/make_news_file.py --root <data-snapshot checkout> [--out <path>]
"""
import argparse
import pathlib

import pandas as pd

COMMON = pathlib.Path.home() / "AppData" / "Roaming" / "MetaQuotes" / "Terminal" / "Common" / "Files"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    ap.add_argument("--out", default=str(COMMON / "g27k_news_usd_high.txt"))
    a = ap.parse_args()
    cal = pd.read_csv(pathlib.Path(a.root) / "data" / "calendar.csv", encoding="cp1252")
    hi = cal[(cal.importance == "HIGH") & (cal.currency == "USD")]
    times = sorted(pd.to_datetime(hi.time, format="%Y.%m.%d %H:%M").dt.strftime("%Y.%m.%d %H:%M").unique())
    out = pathlib.Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("# USD HIGH events from data/calendar.csv, UTC\n" + "\n".join(times) + "\n", encoding="ascii")
    print(f"{len(times)} event times, {times[0]} .. {times[-1]} -> {out}")


if __name__ == "__main__":
    main()
