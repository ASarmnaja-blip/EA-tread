"""Download the news / macro data the operator approved on 2026-10-01 ("อนุญาตทั้งหมด") into data/macro/ (never into data/external,
whose files are digest-locked by the frozen forward records). Writes data/macro/manifest.json (url, bytes, sha256, time).
Usage: python research/hyp/fetch_macro.py"""
from __future__ import annotations

import hashlib
import json
import time
import urllib.request
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "macro"
FRED = ["USEPUINDXD", "DFII10", "T10YIE", "VIXCLS", "BAMLH0A0HYM2", "DGS2", "DGS10", "DTWEXBGS"]
FILES = {
    "gpr_daily.xls": "https://www.matteoiacoviello.com/gpr_files/data_gpr_daily_recent.xls",
    "tpu_web_latest.xlsx": "https://www.matteoiacoviello.com/tpu_files/tpu_web_latest.xlsx",
    "truth_archive.csv": "https://ix.cnn.io/data/truth-social/truth_archive.csv",
    "tweets_in_office.csv": "https://raw.githubusercontent.com/MarkHershey/CompleteTrumpTweetsArchive/master/data/realDonaldTrump_in_office.csv",
    "tweets_bf_office.csv": "https://raw.githubusercontent.com/MarkHershey/CompleteTrumpTweetsArchive/master/data/realDonaldTrump_bf_office.csv",
    "gld_archive.csv": "https://www.spdrgoldshares.com/assets/dynamic/GLD/GLD_US_archive_EN.csv",
    **{f"fred_{s}.csv": f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={s}" for s in FRED},
    **{f"cftc/deacot{y}.zip": f"https://www.cftc.gov/files/dea/history/deacot{y}.zip" for y in range(2004, 2021)},
}


def main():
    OUT.mkdir(parents=True, exist_ok=True); (OUT / "cftc").mkdir(exist_ok=True)
    man_f = OUT / "manifest.json"
    man = json.loads(man_f.read_text()) if man_f.exists() else {}
    for name, url in FILES.items():
        f = OUT / name
        if name in man and f.exists():
            continue
        t0 = time.time()
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (research; EA-tread)"})
            data = urllib.request.urlopen(req, timeout=180).read()
        except Exception as e:
            print(f"FAILED {name}: {e!r}"); continue
        f.write_bytes(data)
        man[name] = dict(url=url, bytes=len(data), sha256=hashlib.sha256(data).hexdigest(), fetched=pd.Timestamp.now(tz="UTC").isoformat())
        print(f"{name}: {len(data):,} bytes ({time.time() - t0:.1f}s)", flush=True)
        man_f.write_text(json.dumps(man, indent=1))
    print(f"total {sum(v['bytes'] for v in man.values()) / 1e6:.1f} MB in {len(man)} files")


if __name__ == "__main__":
    main()
