# H1 bars for the 16-market work (added 2026-10-03)

Bid-side H1 OHLCV, UTC, one parquet per market, columns o h l c v.

| file | source | from |
|---|---|---|
| BTCUSD_H1BID.parquet | Binance BTCUSDT spot 1h klines (data.binance.vision) | 2017-08-17 |
| JP225, US500, USTEC, DE30, USOIL, XCUUSD, USDCNH, USDMXN, USDZAR, EURUSD, USDJPY, AUDUSD, USDCHF | Dukascopy hourly bid candles | each instrument's first month (indices/oil 2011-09, copper 2012-03, USDCNH 2012-06, DAX 2013-09, FX 2009-01) |

Flat filler bars (h == l) are kept in the files; the research loader drops them.
Gold and silver H1 are not here: the research uses Candle Lab H1 (data/bundle) before 2021 and the MT5 export after.

To use with the code branch, copy these files into `research/.cache_duka/` of the code checkout
(that folder is gitignored there):

    cp data/universe_h1/*_H1BID.parquet <code-checkout>/research/.cache_duka/
    cp data/macro/fred/*.csv <code-checkout>/research/g27k_dev/macro_data/

Fetch scripts: research/g27k_dev/fetch_universe.py on branch claude/order-position-choch-gab-im08db.
