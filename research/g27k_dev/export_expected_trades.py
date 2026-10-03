#!/usr/bin/env python3
"""Expected G27K #1 trades on the final four markets, for checking an MT5 EA
against the research engine trade by trade.

Two files, one per H4 bar alignment:
  handoff_expected_trades_h4_00utc.json  H4 bars start 00/04/08/12/16/20 UTC
                                         (MT5 native H4 when the server clock is GMT+0, as Exness's is)
  handoff_expected_trades_h4_22utc.json  H4 bars start 22/02/06/10/14/18 UTC (what every research
                                         report used); results are close either way (see HANDOFF)

Usage: python3 research/g27k_dev/export_expected_trades.py --root <data-snapshot checkout>
"""
import argparse
import json
import pathlib
import sys

import numpy as np
import pandas as pd

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))
import h4d1_pattern_search as P
import multi_market_search as MMS
import walkforward_controller as W

M4 = ("XAUUSD", "XAGUSD", "BTCUSD", "JP225")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    a = ap.parse_args()
    P.setup(a.root)
    G, K = P._M["G"], P._M["K"]
    sys.path.insert(0, str(pathlib.Path(a.root) / "research" / "grid768"))
    import report768 as RP
    ext = K.externals()
    K.START = W.ts("2009-09-01")
    H1 = {m: MMS.load(m, G) for m in M4}
    orig = G.frames
    for off, name in ((0, "00utc"), (22, "22utc")):
        def frames(b, off=off):
            t = b["t"]
            return {"H4": G.agg(b, (t - off * 3600) // 14400), "D1": G.agg(b, t // 86400),
                    "W1": G.agg(b, np.searchsorted(G.CUTS, t, side="right") - 1)}
        G.frames = frames
        rows = []
        for m in M4:
            Mk = K.prepare(m, H1[m], ext)
            X = G.features(G.frames(H1[m]), m, "H4")
            d = K.directions(Mk, "C8", "D3", "E1", "J1")
            idx = np.flatnonzero(d)
            for r in RP.sim_paths(X, m, idx, d[idx], "I1"):
                s = r["e"] - 1
                stop = r["ep"] - r["risk"]
                rows.append(dict(
                    market=m, signal_bar_first_h1_utc=str(pd.Timestamp(int(X["t"][s]), unit="s")),
                    entry_time_utc=str(pd.Timestamp(r["t"], unit="s")), entry_price=round(float(r["ep"]), 5),
                    signal_close=round(float(X["c"][s]), 5), prior10_high=round(float(Mk["hi10"][s]), 5),
                    atr20_sma_at_signal=round(float(X["a20"][s]), 5), stop_price=round(float(stop), 5),
                    exit_time_utc=str(pd.Timestamp(r["t_exit"], unit="s")), exit_price=round(float(r["px"]), 5),
                    exit_reason="stop" if r["px"] <= stop + 1e-9 else "channel",
                    R_gross=round(float(r["R_gross"]), 4), R_net=round(float(r["R"]), 4)))
        note = (f"G27K #1 trades, research engine (report768.sim_paths); times UTC; H4 bars aggregate H1 bars with the boundary at "
                f"{off:02d}:00 UTC (every 4 h); signal = H4 close > highest high of the previous 10 H4 bars, no HIGH-impact USD event in "
                f"the 8 h after the signal close (calendar from 2022 only); entry = open of the next H4 bar; stop = entry - 2 x ATR20, "
                f"ATR = simple 20-bar mean of true range including the signal bar; stops checked on H1 bars, a gap through the stop fills "
                f"at that H1 open; exit = open of the bar after an H4 close below the lowest low of the previous 20 H4 bars; one trade "
                f"per market; prices are the research data (gold/silver: Candle Lab to 2020 then MT5; JP225: Dukascopy bid; BTC: Binance), "
                f"so broker prices differ slightly; R_net includes spread + 1 bp and the broker-spec swap.")
        p = HERE / f"handoff_expected_trades_h4_{name}.json"
        p.write_text(json.dumps(dict(note=note, trades=rows), indent=0))
        print(f"  {p.name}: {len(rows)} trades")
    G.frames = orig


if __name__ == "__main__":
    main()
