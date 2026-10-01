"""Read-only fetch of M30 / M15 / M5 history from the running demo MT5 terminal for Bundle 2 (docs/BUNDLE2_2026-10-01_PREREG.md).
Demo account enforced; no order API is used. Writes data/bundle/mt5/<SYMBOL>_<TF>.npz (same fields as research/hyp/mt5_cache.py)."""
from __future__ import annotations

import hashlib
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "bundle" / "mt5"
SYMS = ["EURUSD", "USDJPY", "AUDUSD", "USDCHF", "US500", "USTEC", "USOIL", "BTCUSD", "DE30", "JP225", "XCUUSD", "XPTUSD", "USDCNH",
        "USDINR", "USDMXN", "USDZAR", "XAUUSD", "XAGUSD"]


def main():
    import MetaTrader5 as mt5
    assert mt5.initialize(), mt5.last_error()
    a = mt5.account_info()
    assert a is not None and a.trade_mode == 0, "not a demo account: refusing"
    OUT.mkdir(parents=True, exist_ok=True)
    man = {}
    for s in SYMS:
        mt5.symbol_select(s, True)
        info = mt5.symbol_info(s)
        for tf, nm in ((mt5.TIMEFRAME_M30, "M30"), (mt5.TIMEFRAME_M15, "M15"), (mt5.TIMEFRAME_M5, "M5")):
            t0 = time.time()
            r = mt5.copy_rates_from_pos(s, tf, 0, 100000)
            if r is None or not len(r):
                print(s, nm, "none", mt5.last_error(), flush=True); continue
            f = OUT / f"{s}_{nm}.npz"
            np.savez_compressed(f, t=r["time"].astype(np.int64), o=r["open"], h=r["high"], l=r["low"], c=r["close"],
                                tick_volume=r["tick_volume"].astype(np.int64), spread_points=r["spread"].astype(np.int64), point=np.float64(info.point))
            man[f.name] = dict(sha256=hashlib.sha256(f.read_bytes()).hexdigest(), bars=int(len(r)),
                               first=str(pd.to_datetime(r["time"][0], unit="s")), last=str(pd.to_datetime(r["time"][-1], unit="s")))
            print(f"{s:<7s} {nm}: {len(r):6d} bars {man[f.name]['first']} .. {man[f.name]['last']} ({time.time() - t0:.1f}s)", flush=True)
    mt5.shutdown()
    (OUT / "manifest.json").write_text(json.dumps(man, indent=1))


if __name__ == "__main__":
    sys.exit(main())
