"""Fetch the first-party public files used by WPWB prereg amendment 7.2.

This script only performs HTTP GETs and writes raw research data.  It has no
MetaTrader5 dependency and no trading or broker interaction.
"""
from __future__ import annotations

import hashlib
import json
import os
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "external"


def download(url: str, path: Path) -> dict:
    request = urllib.request.Request(url, headers={"User-Agent": "EA-tread-research/1.0"})
    with urllib.request.urlopen(request, timeout=90) as response:
        payload = response.read()
        final_url = response.url
    path.write_bytes(payload)
    return {
        "file": path.name,
        "url": url,
        "final_url": final_url,
        "bytes": len(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
    }


def main() -> int:
    os.chdir(ROOT)
    OUT.mkdir(parents=True, exist_ok=True)
    sources: list[tuple[str, str]] = []
    treasury = "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/pages/xml"
    for year in range(2016, 2027):
        sources.append((f"treasury_nominal_{year}.xml",
                        f"{treasury}?data=daily_treasury_yield_curve&field_tdr_date_value={year}"))
    for year in range(2021, 2027):
        sources.append((f"treasury_real_{year}.xml",
                        f"{treasury}?data=daily_treasury_real_yield_curve&field_tdr_date_value={year}"))
    sources.append(("GVZ_History.csv",
                    "https://cdn.cboe.com/api/global/us_indices/daily_prices/GVZ_History.csv"))
    for year in range(2021, 2027):
        sources.append((f"cftc_fut_disagg_{year}.zip",
                        f"https://www.cftc.gov/files/dea/history/fut_disagg_txt_{year}.zip"))

    manifest = []
    for name, url in sources:
        row = download(url, OUT / name)
        manifest.append(row)
        print(f"{name}: {row['bytes']:,} bytes {row['sha256'][:12]}")
    record = {
        "retrieved_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "sources": manifest,
    }
    (OUT / "manifest.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
