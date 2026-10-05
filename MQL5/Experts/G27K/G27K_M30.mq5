//+------------------------------------------------------------------+
//|                                                     G27K_M30.mq5 |
//|  The M30 sleeve (ledger m30_sleeve_new_markets), one instance for |
//|  the whole market set. Rules and code: Include/G27K/G27K_Sleeve.mqh|
//|   - M30 bar closes within 1 ATR14 of the high (long) / low (short)|
//|     of the 55 bars before it                                      |
//|   - ATR14 / mean(ATR14, 100) >= 1.5, D1 agrees                    |
//|   - stop 2 x ATR20, target 2R, time exit at the open of bar e+30  |
//|   - 0.5 % of balance per trade                                    |
//|  1.10: a signal bar must come after the bar the last trade ended  |
//|  in (the research's no_overlap); long and short each get their own|
//|  D1 check.                                                        |
//+------------------------------------------------------------------+
#property copyright   "EA-tread"
#property version     "1.10"
#property description "M30 sleeve: near a 55-bar extreme in expanded volatility with D1 agreeing,"
#property description "stop 2xATR20, target 2R, time exit after 30 bars. One instance per account."

//--- book rule: research values. Change only through research/change_ledger.json.
#define BOOK_NAME      "M30"
#define RULE_TF        PERIOD_M30
#define EXT_BARS       55      // the 55-bar extreme the close must be near
#define NEAR_MIN      -1.0     // (close - extreme) / ATR14 must be at least this
#define ATR_RATIO_MIN  1.5     // ATR14 / mean(ATR14,100) must be at least this
#define SETUP_NAME     "M30sleeve"
#define COPY_BARS      220     // 55 + 100 + 14 + room for bars missed while offline
#define NEED_BARS      172
#define DEF_MAGIC      27027030
#define DEF_DELAY      20
#define DEF_STATE      "g27k_m30_state.txt"
#define DEF_LOG        "g27k_m30_log.csv"

#include <G27K/G27K_Sleeve.mqh>
