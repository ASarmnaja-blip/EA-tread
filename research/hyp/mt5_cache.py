"""Read-only snapshot of MT5 (Exness demo) H1 and D1 history for the cross-asset hypotheses (docs/HYPOTHESIS_BATCH2_PREREG.md). No order
API is used; the account must be demo. Writes data/mt5/<SYMBOL>_<TF>.npz (t, o, h, l, c, tick_volume, spread_points, point) and a manifest
with sha256 of every file. Usage: python research/hyp/mt5_cache.py"""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "mt5"
SYMBOLS = ["XAUUSD", "XAGUSD", "USDJPY", "EURUSD", "USDCHF", "USDCNH", "AUDUSD", "USDINR", "USDZAR", "USDMXN", "DXY", "US500", "USTEC",
           "JP225", "DE30", "USOIL", "BTCUSD", "XCUUSD", "XPTUSD"]


def main():
    import MetaTrader5 as mt5
    assert mt5.initialize(), mt5.last_error()
    a = mt5.account_info()
    assert a is not None and a.trade_mode == 0, "not a demo account: refusing"
    OUT.mkdir(parents=True, exist_ok=True)
    man = {}
    for s in SYMBOLS:
        mt5.symbol_select(s, True)
        info = mt5.symbol_info(s)
        for tf, nm, n in ((mt5.TIMEFRAME_H1, "H1", 80000), (mt5.TIMEFRAME_D1, "D1", 8000)):
            t0 = time.time()
            r = mt5.copy_rates_from_pos(s, tf, 0, n)
            if r is None or not len(r):
                print(s, nm, "none"); continue
            f = OUT / f"{s}_{nm}.npz"
            np.savez_compressed(f, t=r["time"].astype(np.int64), o=r["open"], h=r["high"], l=r["low"], c=r["close"],
                                tick_volume=r["tick_volume"].astype(np.int64), spread_points=r["spread"].astype(np.int64), point=np.float64(info.point))
            man[f.name] = dict(sha256=hashlib.sha256(f.read_bytes()).hexdigest(), bars=int(len(r)),
                               first=str(pd.to_datetime(r["time"][0], unit="s")), last=str(pd.to_datetime(r["time"][-1], unit="s")))
            print(f"{s:<8s} {nm}: {len(r):6d} bars {man[f.name]['first']} .. {man[f.name]['last']} ({time.time() - t0:.1f}s)", flush=True)
    mt5.shutdown()
    (OUT / "manifest.json").write_text(json.dumps(dict(server=a.server, retrieved=pd.Timestamp.now(tz="UTC").isoformat(), files=man), indent=1))


if __name__ == "__main__":
    main()
