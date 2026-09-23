"""Read timestamped 10-year TIPS yields downloaded from the U.S. Treasury."""
from __future__ import annotations

from pathlib import Path
import xml.etree.ElementTree as ET
import pandas as pd


def load(path="data") -> pd.DataFrame:
    rows = []
    for p in sorted(Path(path).glob("treasury_real_yields_*.xml")):
        root = ET.parse(p).getroot()
        for props in root.findall(".//{http://schemas.microsoft.com/ado/2007/08/dataservices/metadata}properties"):
            d = {x.tag.rsplit("}", 1)[-1]: x.text for x in props}
            if d.get("NEW_DATE") and d.get("TC_10YEAR"):
                rows.append((pd.Timestamp(d["NEW_DATE"], tz="UTC"), float(d["TC_10YEAR"])))
    out = pd.DataFrame(rows, columns=["time", "tips10y"]).drop_duplicates("time")
    return out.sort_values("time").reset_index(drop=True)


if __name__ == "__main__":
    x = load()
    print(f"rows={len(x):,} {x.time.min():%Y-%m-%d}..{x.time.max():%Y-%m-%d} "
          f"tips10y={x.tips10y.iloc[-1]:.2f}%")
