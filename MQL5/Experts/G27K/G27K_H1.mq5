//+------------------------------------------------------------------+
//|                                                      G27K_H1.mq5 |
//|  The H1 sleeve (ledger h1_search_mirror_m30, h1_sleeve.py pick),  |
//|  one instance for the whole market set.                           |
//|  Rules and code: Include/G27K/G27K_Sleeve.mqh                     |
//|   - H1 close in the top 10 % (long) / bottom 10 % (short) of the  |
//|     high-low range of the 250 bars before it                      |
//|   - ATR14 / mean(ATR14, 100) >= 1.25, D1 agrees                   |
//|   - stop 2 x ATR20, target 2R, time exit at the open of bar e+30  |
//|   - 1 % of balance per trade (InpRiskPct; the research ran 0.5 %)  |
//+------------------------------------------------------------------+
#property copyright   "EA-tread"
#property version     "1.10"
#property description "H1 sleeve: in the top/bottom 10% of the 250-bar range in expanded volatility with D1 agreeing,"
#property description "stop 2xATR20, target 2R, time exit after 30 bars. One instance per account."

//--- book rule: research values. Change only through research/change_ledger.json.
#define BOOK_NAME      "H1"
#define RULE_TF        PERIOD_H1
#define NEAR_POS                // nearness = position of the close inside the 250-bar range
#define POS_BARS       250
#define NEAR_MIN       0.9     // pos250 (long) or 1 - pos250 (short) must be at least this
#define ATR_RATIO_MIN  1.25    // ATR14 / mean(ATR14,100) must be at least this
#define SETUP_NAME     "H1sleeve"
#define COPY_BARS      320     // 250 + room; the ATR ratio needs 115
#define NEED_BARS      262
#define DEF_MAGIC      27027060
#define DEF_DELAY      40
#define DEF_STATE      "g27k_h1_state.txt"
#define DEF_LOG        "g27k_h1_log.csv"

#include <G27K/G27K_Sleeve.mqh>
