"""Find calendar months where XAUUSD was genuinely flat/ranging (not
trending), restricted to windows MT5 can actually backtest with decent
data quality on this broker (M5 reliable from ~2021-01, M1-tick-quality
from 2023-11-27 - established by probing the live terminal).

Efficiency ratio = |net move| / sum(|bar-to-bar moves|) over the month.
Near 0 = pure chop/flat. Near 1 = one-directional trend. Also reports
realized range (high-low over the month, in ATR units) so a "flat" month
isn't just a dead/illiquid one. Read-only.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import core as C5
import historical_regime_walkforward as hist

MT5_M5_START = "2021-01-01"  # established by probing the terminal directly


def main() -> int:
    b5 = hist.load_history()
    t = pd.to_datetime(b5.t, unit="s", utc=True)
    atr = C5.atr(b5, 14)
    df = pd.DataFrame({"t": t, "c": b5.c, "h": b5.h, "l": b5.l, "atr": atr})
    df = df[df.t >= MT5_M5_START].reset_index(drop=True)
    df["ym"] = df.t.dt.strftime("%Y-%m")

    rows = []
    for ym, g in df.groupby("ym"):
        net_move = abs(g.c.iloc[-1] - g.c.iloc[0])
        path_len = g.c.diff().abs().sum()
        eff = net_move / path_len if path_len > 0 else np.nan
        month_range = g.h.max() - g.l.min()
        atr_mean = g.atr.mean()
        rows.append(dict(month=ym, efficiency=eff,
                         range_in_atr=month_range / atr_mean if atr_mean else np.nan,
                         n_bars=len(g), avg_atr=atr_mean))

    out = pd.DataFrame(rows).sort_values("efficiency")
    pd.set_option("display.width", 120)
    print("Flattest months first (low efficiency = choppy/no net direction):\n")
    print(out.to_string(index=False,
                        formatters={"efficiency": "{:.3f}".format,
                                   "range_in_atr": "{:.1f}".format,
                                   "avg_atr": "{:.2f}".format}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
