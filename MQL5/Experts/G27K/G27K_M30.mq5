//+------------------------------------------------------------------+
//|                                                     G27K_M30.mq5 |
//|  The M30 sleeve (ledger m30_sleeve_new_markets), one instance for |
//|  the whole market set.                                            |
//|                                                                   |
//|  Rules: research/g27k_dev/handoff/HANDOFF.md section 3.2, matched  |
//|  to h4d1_pattern_search.py (features + sim_all mode 4 "tp2"):      |
//|   - M30 bars, higher timeframe D1, closed bars only                |
//|   - long when  (close - high55) / ATR14 >= -1, short when          |
//|     (low55 - close) / ATR14 >= -1, where high55/low55 are the 55   |
//|     bars BEFORE the signal bar                                     |
//|   - and ATR14 / mean(ATR14, 100) >= 1.5                            |
//|   - and the last closed D1 bar agrees: its close above (long) or   |
//|     below (short) the midpoint of its own 55-bar high-low range    |
//|   - enter at the next bar's open, both directions                  |
//|   - risk = 2 x ATR20 of the signal bar; stop at 1R, take profit    |
//|     at 2R, neither moves                                           |
//|   - time exit: hold bars e..e+29, close at the open of bar e+30    |
//|   - one position per market                                        |
//|   - 0.5 % of balance per trade at every risk level (the 25 % brake |
//|     applies to G27K-F, not to this sleeve)                         |
//|  Real-money accounts: no orders unless InpAllowRealAccount=true.   |
//+------------------------------------------------------------------+
#property copyright   "EA-tread"
#property version     "1.00"
#property description "M30 sleeve: near a 55-bar extreme in expanded volatility with D1 agreeing,"
#property description "stop 2xATR20, target 2R, time exit after 30 bars. One instance per account."

#include <Trade/Trade.mqh>

//--- rule constants: research values. Change only through research/change_ledger.json.
#define EXT_BARS      55      // the 55-bar extreme the close must be near
#define ATR_FAST      14      // ATR used for the distance and the expansion ratio
#define ATR_SLOW     100      // the mean of ATR14 the ratio divides by
#define ATR_RISK      20      // ATR used for the stop
#define BRK_MIN      -1.0     // (close - extreme) / ATR14 must be at least this
#define ATR_RATIO_MIN 1.5     // ATR14 / mean(ATR14,100) must be at least this
#define STOP_ATR      2.0     // risk = 2 x ATR20
#define TP_R          2.0     // target in R
#define HOLD_BARS     30      // bars held before the time exit (exit opens bar e+30)
#define HTF_BARS      55      // the D1 range whose midpoint sets the trend
#define RULE_TF       PERIOD_M30
#define HTF           PERIOD_D1
#define SETUP_NAME    "M30sleeve"
#define COPY_BARS    220      // 55 + 100 + room for bars missed while offline

enum ENUM_MARKET_SET
  {
   SET_CENT5  = 0,  // Cent: XAUUSDc XAGUSDc BTCUSDc ETHUSDc USDJPYc
   SET_CENT4  = 1,  // Cent without USDJPY (its minimum lot needs about 880 USD)
   SET_STD5   = 2,  // Standard: XAUUSD XAGUSD BTCUSD ETHUSD USDJPY
   SET_STD4   = 3,  // Standard without USDJPY
   SET_CUSTOM = 4   // InpCustomSymbols
  };

input ENUM_MARKET_SET InpMarketSet        = SET_STD5;
input string          InpCustomSymbols    = "";
input double          InpRiskPct          = 0.5;    // % of balance per trade
input long            InpMagic            = 27027030;
input int             InpMaxEntryDelayMin = 20;     // skip an entry if the new bar began longer ago (EA was offline)
input bool            InpAllowRealAccount = false;  // false: on a real-money account signals are logged, no orders
input string          InpStateFile        = "g27k_m30_state.txt";
input string          InpLogFile          = "g27k_m30_log.csv";
input int             InpTimerSec         = 5;

struct SymState
  {
   string            name;
   int               digits;
   datetime          lastBar;      // open time of the newest M30 bar whose rules have run
   ulong             pos;
   bool              pendingExit;
   datetime          entryBar;     // open time of the bar the position was entered on
   double            entry, stop, tp, atr20, lots, risk;
   datetime          entryTime;
  };

SymState g_s[];
CTrade   g_trade;
bool     g_tester = false, g_canTrade = true, g_dirty = false;

string D(const double v, const int dg) { return DoubleToString(v, dg); }
string T(const datetime t)             { return t > 0 ? TimeToString(t, TIME_DATE | TIME_MINUTES) : ""; }

string PresetSymbols(const ENUM_MARKET_SET s)
  {
   switch(s)
     {
      case SET_CENT5: return "XAUUSDc,XAGUSDc,BTCUSDc,ETHUSDc,USDJPYc";
      case SET_CENT4: return "XAUUSDc,XAGUSDc,BTCUSDc,ETHUSDc";
      case SET_STD5:  return "XAUUSD,XAGUSD,BTCUSD,ETHUSD,USDJPY";
      case SET_STD4:  return "XAUUSD,XAGUSD,BTCUSD,ETHUSD";
      default:        return InpCustomSymbols;
     }
  }

int SymIndex(const string s)
  {
   for(int i = 0; i < ArraySize(g_s); i++)
      if(g_s[i].name == s)
         return i;
   return -1;
  }

//+------------------------------------------------------------------+
//| log                                                              |
//+------------------------------------------------------------------+
string LogName() { return g_tester ? "tester_" + InpLogFile : InpLogFile; }

int LogFlags()
  {
   int f = FILE_READ | FILE_WRITE | FILE_TXT | FILE_ANSI | FILE_SHARE_READ;
   if(g_tester)
      f |= FILE_COMMON;
   return f;
  }

void LogHeader()
  {
   int h = FileOpen(LogName(), LogFlags());
   if(h == INVALID_HANDLE)
      return;
   if(FileSize(h) == 0)
      FileWriteString(h, "time,event,symbol,dir,signal_bar,close,ext55,brk55,atr14,atr_ratio,atr20,htf,balance,risk_pct,lots,"
                         "entry,stop,tp,bid,ask,fill,slippage,exit_price,bars_held,r_gross,money,delay_s,margin,note\r\n");
   FileClose(h);
  }

//--- the note is the last field and free text, so no comma may survive in it
string Clean(const string s)
  {
   string out = s;
   StringReplace(out, ",", ";");
   return out;
  }

void Row(const string ev, const string sym, const string dir, const string sigbar, const string close, const string ext,
         const string brk, const string atr14, const string ratio, const string atr20, const string htf, const string lots,
         const string entry, const string stop, const string tp, const string bid, const string ask, const string fill,
         const string slip, const string xp, const string bars, const string r, const string money, const string delay,
         const string margin, const string riskpct, const string note)
  {
   int h = FileOpen(LogName(), LogFlags());
   if(h == INVALID_HANDLE)
      return;
   FileSeek(h, 0, SEEK_END);
   FileWriteString(h, TimeToString(TimeCurrent(), TIME_DATE | TIME_SECONDS) + "," + ev + "," + sym + "," + dir + "," + sigbar + "," +
                   close + "," + ext + "," + brk + "," + atr14 + "," + ratio + "," + atr20 + "," + htf + "," +
                   D(AccountInfoDouble(ACCOUNT_BALANCE), 2) + "," + riskpct + "," + lots + "," + entry + "," + stop + "," + tp + "," +
                   bid + "," + ask + "," + fill + "," + slip + "," + xp + "," + bars + "," + r + "," + money + "," + delay + "," +
                   margin + "," + Clean(note) + "\r\n");
   FileClose(h);
  }

void LogSimple(const string ev, const string sym, const string note)
  {
   Row(ev, sym, "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", note);
  }

//+------------------------------------------------------------------+
//| state                                                            |
//+------------------------------------------------------------------+
bool LoadState()
  {
   int h = FileOpen(InpStateFile, FILE_READ | FILE_TXT | FILE_ANSI);
   if(h == INVALID_HANDLE)
      return false;
   while(!FileIsEnding(h))
     {
      string line = FileReadString(h);
      int eq = StringFind(line, "=");
      if(eq <= 0)
         continue;
      string k = StringSubstr(line, 0, eq), v = StringSubstr(line, eq + 1);
      int bar = StringFind(k, "|");
      if(bar <= 0)
         continue;
      int i = SymIndex(StringSubstr(k, 0, bar));
      if(i < 0)
         continue;
      string f = StringSubstr(k, bar + 1);
      if(f == "lastbar")        g_s[i].lastBar = (datetime)StringToInteger(v);
      else if(f == "pos")       g_s[i].pos = (ulong)StringToInteger(v);
      else if(f == "entrybar")  g_s[i].entryBar = (datetime)StringToInteger(v);
      else if(f == "entry")     g_s[i].entry = StringToDouble(v);
      else if(f == "stop")      g_s[i].stop = StringToDouble(v);
      else if(f == "tp")        g_s[i].tp = StringToDouble(v);
      else if(f == "atr20")     g_s[i].atr20 = StringToDouble(v);
      else if(f == "lots")      g_s[i].lots = StringToDouble(v);
      else if(f == "risk")      g_s[i].risk = StringToDouble(v);
      else if(f == "entrytime") g_s[i].entryTime = (datetime)StringToInteger(v);
     }
   FileClose(h);
   return true;
  }

void SaveState()
  {
   g_dirty = false;
   if(g_tester)
      return;
   string tmp = InpStateFile + ".tmp";
   int h = FileOpen(tmp, FILE_WRITE | FILE_TXT | FILE_ANSI);
   if(h == INVALID_HANDLE)
     {
      g_dirty = true;
      return;
     }
   for(int i = 0; i < ArraySize(g_s); i++)
     {
      string p = g_s[i].name + "|";
      FileWriteString(h, p + "lastbar=" + IntegerToString((long)g_s[i].lastBar) + "\r\n");
      FileWriteString(h, p + "pos=" + IntegerToString((long)g_s[i].pos) + "\r\n");
      FileWriteString(h, p + "entrybar=" + IntegerToString((long)g_s[i].entryBar) + "\r\n");
      FileWriteString(h, p + "entry=" + D(g_s[i].entry, g_s[i].digits) + "\r\n");
      FileWriteString(h, p + "stop=" + D(g_s[i].stop, g_s[i].digits) + "\r\n");
      FileWriteString(h, p + "tp=" + D(g_s[i].tp, g_s[i].digits) + "\r\n");
      FileWriteString(h, p + "atr20=" + D(g_s[i].atr20, g_s[i].digits + 2) + "\r\n");
      FileWriteString(h, p + "lots=" + D(g_s[i].lots, 2) + "\r\n");
      FileWriteString(h, p + "risk=" + D(g_s[i].risk, 2) + "\r\n");
      FileWriteString(h, p + "entrytime=" + IntegerToString((long)g_s[i].entryTime) + "\r\n");
     }
   FileClose(h);
   if(!FileMove(tmp, 0, InpStateFile, FILE_REWRITE))
      g_dirty = true;
  }

//+------------------------------------------------------------------+
//| indicators, computed exactly as the research does                |
//+------------------------------------------------------------------+
//--- simple mean of true range over n bars ENDING at bar s (bar s included)
double AtrAt(const MqlRates &r[], const int s, const int n)
  {
   double sum = 0.0;
   for(int i = s; i < s + n; i++)
     {
      double pc = r[i + 1].close;
      sum += MathMax(r[i].high, pc) - MathMin(r[i].low, pc);
     }
   return sum / n;
  }

//--- mean of ATR14 over the ATR_SLOW bars ending at bar s
double AtrSlowAt(const MqlRates &r[], const int s)
  {
   double sum = 0.0;
   for(int i = s; i < s + ATR_SLOW; i++)
      sum += AtrAt(r, i, ATR_FAST);
   return sum / ATR_SLOW;
  }

//--- highest high / lowest low of the EXT_BARS bars BEFORE bar s
double Hi55(const MqlRates &r[], const int s)
  {
   double v = r[s + 1].high;
   for(int k = s + 2; k <= s + EXT_BARS; k++)
      v = MathMax(v, r[k].high);
   return v;
  }

double Lo55(const MqlRates &r[], const int s)
  {
   double v = r[s + 1].low;
   for(int k = s + 2; k <= s + EXT_BARS; k++)
      v = MathMin(v, r[k].low);
   return v;
  }

//--- +1 / -1 / 0 from the last CLOSED daily bar: its close against the midpoint of its own 55-bar range
int HtfDir(const string sym, const datetime sigClose)
  {
   MqlRates d[];
   ArraySetAsSeries(d, true);
   int got = CopyRates(sym, HTF, 0, HTF_BARS + 5, d);
   if(got < HTF_BARS + 1)
      return 0;
   int k = -1;                                     // newest daily bar that had already closed at sigClose
   for(int i = 0; i < got; i++)
      if(d[i].time + PeriodSeconds(HTF) <= sigClose)
        {
         k = i;
         break;
        }
   if(k < 0 || k + HTF_BARS > got)
      return 0;
   double hi = d[k].high, lo = d[k].low;
   for(int i = k + 1; i < k + HTF_BARS; i++)
     {
      hi = MathMax(hi, d[i].high);
      lo = MathMin(lo, d[i].low);
     }
   double mid = (hi + lo) / 2.0;
   if(d[k].close > mid)
      return 1;
   if(d[k].close < mid)
      return -1;
   return 0;
  }

double RoundLots(const string sym, const double want)
  {
   double step = SymbolInfoDouble(sym, SYMBOL_VOLUME_STEP);
   double vmin = SymbolInfoDouble(sym, SYMBOL_VOLUME_MIN);
   double vmax = SymbolInfoDouble(sym, SYMBOL_VOLUME_MAX);
   if(step <= 0.0)
      step = vmin;
   double lots = MathFloor(want / step + 0.5) * step;
   if(lots < vmin)
      lots = vmin;
   if(lots > vmax)
      lots = vmax;
   int dg = (int)MathMax(0.0, MathCeil(-MathLog10(step) - 1e-9));
   return NormalizeDouble(lots, dg);
  }

ulong FindPosition(const string sym)
  {
   for(int p = PositionsTotal() - 1; p >= 0; p--)
     {
      ulong t = PositionGetTicket(p);
      if(t != 0 && PositionGetInteger(POSITION_MAGIC) == InpMagic && PositionGetString(POSITION_SYMBOL) == sym)
         return t;
     }
   return 0;
  }

void ClearTrade(const int i)
  {
   g_s[i].pos = 0; g_s[i].pendingExit = false; g_s[i].entryBar = 0; g_s[i].entry = 0; g_s[i].stop = 0;
   g_s[i].tp = 0; g_s[i].atr20 = 0; g_s[i].lots = 0; g_s[i].risk = 0; g_s[i].entryTime = 0;
   g_dirty = true;
  }

bool ExitDetails(const ulong pos, datetime &xt, double &xp, double &money, long &reason)
  {
   xt = 0; xp = 0; money = 0; reason = -1;
   if(!HistorySelectByPosition(pos))
      return false;
   for(int k = 0; k < HistoryDealsTotal(); k++)
     {
      ulong d = HistoryDealGetTicket(k);
      money += HistoryDealGetDouble(d, DEAL_PROFIT) + HistoryDealGetDouble(d, DEAL_SWAP) +
               HistoryDealGetDouble(d, DEAL_COMMISSION) + HistoryDealGetDouble(d, DEAL_FEE);
      long e = HistoryDealGetInteger(d, DEAL_ENTRY);
      if(e == DEAL_ENTRY_OUT || e == DEAL_ENTRY_OUT_BY)
        {
         xt = (datetime)HistoryDealGetInteger(d, DEAL_TIME);
         xp = HistoryDealGetDouble(d, DEAL_PRICE);
         reason = HistoryDealGetInteger(d, DEAL_REASON);
        }
     }
   return xt > 0;
  }

void LogExit(const int i, const string ev, const datetime xt, const double xp, const double money, const string note)
  {
   int dg = g_s[i].digits;
   int bars = g_s[i].entryBar > 0 ? (int)((xt - g_s[i].entryBar) / PeriodSeconds(RULE_TF)) : -1;
   double r = g_s[i].risk > 0 && g_s[i].atr20 > 0 ? (xp - g_s[i].entry) / (STOP_ATR * g_s[i].atr20) : 0.0;
   if(g_s[i].lots > 0 && g_s[i].entry > 0 && g_s[i].stop > g_s[i].entry)
      r = -r;                                          // short
   Row(ev, g_s[i].name, g_s[i].stop < g_s[i].entry ? "long" : "short", "", "", "", "", "", "", D(g_s[i].atr20, dg + 2), "",
       D(g_s[i].lots, 2), D(g_s[i].entry, dg), D(g_s[i].stop, dg), D(g_s[i].tp, dg), "", "", D(g_s[i].entry, dg), "",
       D(xp, dg), IntegerToString(bars), D(r, 4), D(money, 2), "", "", "",
       note + "; entry bar " + T(g_s[i].entryBar) + "; exit " + TimeToString(xt, TIME_DATE | TIME_SECONDS));
  }

//+------------------------------------------------------------------+
void CheckClosed(const int i)
  {
   ulong t = g_s[i].pos;
   if(t == 0 || PositionSelectByTicket(t))
      return;
   datetime xt; double xp, money; long reason;
   if(!ExitDetails(t, xt, xp, money, reason))
      return;
   string ev = reason == DEAL_REASON_SL ? "EXIT_STOP" : (reason == DEAL_REASON_TP ? "EXIT_TP" :
               (reason == DEAL_REASON_SO ? "EXIT_STOPOUT" : "EXIT_OTHER"));
   LogExit(i, ev, xt, xp, money, "deal reason " + IntegerToString(reason));
   ClearTrade(i);
  }

void TryClose(const int i, const string why)
  {
   ulong t = g_s[i].pos;
   if(t == 0 || !PositionSelectByTicket(t))
     {
      g_s[i].pendingExit = false;
      return;
     }
   if(!g_trade.PositionClose(t))
     {
      LogSimple("EXIT_FAIL", g_s[i].name, why + "; retcode " + IntegerToString((long)g_trade.ResultRetcode()));
      return;
     }
   uint rc = g_trade.ResultRetcode();
   if(rc != TRADE_RETCODE_DONE && rc != TRADE_RETCODE_DONE_PARTIAL && rc != TRADE_RETCODE_PLACED)
     {
      LogSimple("EXIT_FAIL", g_s[i].name, why + "; retcode " + IntegerToString((long)rc));
      return;
     }
   datetime xt; double xp, money; long reason;
   if(!ExitDetails(t, xt, xp, money, reason))
     {
      xt = TimeCurrent(); xp = g_trade.ResultPrice(); money = 0;
     }
   LogExit(i, "EXIT_TIME", xt, xp, money, why);
   ClearTrade(i);
  }

//--- the research holds bars e..e+29 and exits at the open of bar e+30. It counts BARS, so the entry bar has to be found in the
//--- series: dividing elapsed time by the bar length counts clock slots instead, and a market that closes has fewer bars than slots.
void CheckTimeExit(const int i, const MqlRates &r[], const int got)
  {
   if(!PositionSelectByTicket(g_s[i].pos) || g_s[i].entryBar <= 0)
      return;
   int held = -1;
   for(int k = 0; k < got; k++)
      if(r[k].time == g_s[i].entryBar)
        {
         held = k;                                  // r[0] is the current bar, so k bars have passed since entry
         break;
        }
   if(held < 0)
     {
      if(r[got - 1].time > g_s[i].entryBar)         // entry bar older than the window: far past the limit
         held = HOLD_BARS;
      else
         return;                                    // history not ready yet
     }
   if(held >= HOLD_BARS)
     {
      g_s[i].pendingExit = true;
      TryClose(i, "held " + IntegerToString(held) + " bars; the research closes at the open of bar " + IntegerToString(HOLD_BARS));
     }
  }

//+------------------------------------------------------------------+
void CheckEntry(const int i, const MqlRates &r[])
  {
   string sym = g_s[i].name;
   int dg = g_s[i].digits;
   double a14 = AtrAt(r, 1, ATR_FAST), a20 = AtrAt(r, 1, ATR_RISK), a100 = AtrSlowAt(r, 1);
   if(!(a14 > 0) || !(a20 > 0) || !(a100 > 0))
      return;
   double ratio = a14 / a100;
   double hi = Hi55(r, 1), lo = Lo55(r, 1), c = r[1].close;
   double brkL = (c - hi) / a14, brkS = (lo - c) / a14;
   int dir = 0;
   double brk = 0, ext = 0;
   if(brkL >= BRK_MIN)
     {
      dir = 1; brk = brkL; ext = hi;
     }
   else
      if(brkS >= BRK_MIN)
        {
         dir = -1; brk = brkS; ext = lo;
        }
   if(dir == 0 || ratio < ATR_RATIO_MIN)
      return;
   datetime sigClose = r[1].time + PeriodSeconds(RULE_TF);
   int htf = HtfDir(sym, sigClose);
   string sdir = dir > 0 ? "long" : "short";
   string base = T(r[1].time) + "," + D(c, dg) + "," + D(ext, dg) + "," + D(brk, 3) + "," + D(a14, dg + 2) + "," +
                 D(ratio, 3) + "," + D(a20, dg + 2) + "," + IntegerToString(htf);
   if(htf != dir)
     {
      Row("SKIP_HTF", sym, sdir, T(r[1].time), D(c, dg), D(ext, dg), D(brk, 3), D(a14, dg + 2), D(ratio, 3), D(a20, dg + 2),
          IntegerToString(htf), "", "", "", "", "", "", "", "", "", "", "", "", "", "", "",
          "daily trend does not agree");
      return;
     }
   datetime first = r[0].time;
   MqlRates m1[];
   if(CopyRates(sym, PERIOD_M1, r[0].time, TimeCurrent(), m1) > 0)
      first = m1[0].time;
   long delay = (long)(TimeCurrent() - first);
   double bid = SymbolInfoDouble(sym, SYMBOL_BID), ask = SymbolInfoDouble(sym, SYMBOL_ASK);
   double px = dir > 0 ? ask : bid;
   double risk = STOP_ATR * a20;
   double stop = NormalizeDouble(px - dir * risk, dg);
   double tp = NormalizeDouble(px + dir * TP_R * risk, dg);
   double bal = AccountInfoDouble(ACCOUNT_BALANCE);
   double riskMoney = bal * InpRiskPct / 100.0;
   if(delay > (long)InpMaxEntryDelayMin * 60)
     {
      Row("SKIP_LATE", sym, sdir, T(r[1].time), D(c, dg), D(ext, dg), D(brk, 3), D(a14, dg + 2), D(ratio, 3), D(a20, dg + 2),
          IntegerToString(htf), "", "", D(stop, dg), D(tp, dg), D(bid, dg), D(ask, dg), "", "", "", "", "", "",
          IntegerToString(delay), "", D(InpRiskPct, 3), "trading in the entry bar began " + IntegerToString((int)(delay / 60)) + " min ago");
      return;
     }
   double pnl = 0;
   if(!OrderCalcProfit(dir > 0 ? ORDER_TYPE_BUY : ORDER_TYPE_SELL, sym, 1.0, px, stop, pnl) || pnl >= 0.0)
     {
      LogSimple("SKIP_CALC", sym, "cannot value the stop distance, error " + IntegerToString(GetLastError()));
      return;
     }
   double lossPerLot = -pnl;
   double lots = RoundLots(sym, riskMoney / lossPerLot);
   double realRisk = lots * lossPerLot;
   double margin = 0;
   if(!OrderCalcMargin(dir > 0 ? ORDER_TYPE_BUY : ORDER_TYPE_SELL, sym, lots, px, margin))
      margin = -1;
   if(margin > AccountInfoDouble(ACCOUNT_MARGIN_FREE))
     {
      LogSimple("SKIP_MARGIN", sym, "needs " + D(margin, 2) + ", free " + D(AccountInfoDouble(ACCOUNT_MARGIN_FREE), 2));
      return;
     }
   if(!g_canTrade)
     {
      Row("SIGNAL_ONLY", sym, sdir, T(r[1].time), D(c, dg), D(ext, dg), D(brk, 3), D(a14, dg + 2), D(ratio, 3), D(a20, dg + 2),
          IntegerToString(htf), D(lots, 2), "", D(stop, dg), D(tp, dg), D(bid, dg), D(ask, dg), "", "", "", "", "", "",
          IntegerToString(delay), D(margin, 2), D(100.0 * realRisk / bal, 3), "real-money account, InpAllowRealAccount = false");
      return;
     }
   g_trade.SetTypeFillingBySymbol(sym);
   bool ok = dir > 0 ? g_trade.Buy(lots, sym, 0.0, stop, tp, SETUP_NAME)
                     : g_trade.Sell(lots, sym, 0.0, stop, tp, SETUP_NAME);
   uint rc = g_trade.ResultRetcode();
   if(!ok || (rc != TRADE_RETCODE_DONE && rc != TRADE_RETCODE_DONE_PARTIAL && rc != TRADE_RETCODE_PLACED))
     {
      Row("ENTRY_FAIL", sym, sdir, T(r[1].time), D(c, dg), D(ext, dg), D(brk, 3), D(a14, dg + 2), D(ratio, 3), D(a20, dg + 2),
          IntegerToString(htf), D(lots, 2), "", D(stop, dg), D(tp, dg), D(bid, dg), D(ask, dg), "", "", "", "", "", "",
          IntegerToString(delay), D(margin, 2), D(InpRiskPct, 3), "retcode " + IntegerToString((long)rc) + " " + g_trade.ResultRetcodeDescription());
      return;
     }
   double fill = g_trade.ResultPrice();
   ulong pos = FindPosition(sym);
   if(pos != 0 && PositionSelectByTicket(pos))
     {
      if(fill <= 0.0)
         fill = PositionGetDouble(POSITION_PRICE_OPEN);
      if((PositionGetDouble(POSITION_SL) <= 0.0 || PositionGetDouble(POSITION_TP) <= 0.0) && !g_trade.PositionModify(pos, stop, tp))
         LogSimple("STOP_FAIL", sym, "stop or target not attached, retcode " + IntegerToString((long)g_trade.ResultRetcode()));
     }
   if(fill <= 0.0)
      fill = px;
   g_s[i].pos = pos; g_s[i].entryBar = r[0].time; g_s[i].entry = fill; g_s[i].stop = stop; g_s[i].tp = tp;
   g_s[i].atr20 = a20; g_s[i].lots = lots; g_s[i].risk = realRisk; g_s[i].entryTime = TimeCurrent();
   g_dirty = true;
   Row("ENTRY", sym, sdir, T(r[1].time), D(c, dg), D(ext, dg), D(brk, 3), D(a14, dg + 2), D(ratio, 3), D(a20, dg + 2),
       IntegerToString(htf), D(lots, 2), D(fill, dg), D(stop, dg), D(tp, dg), D(bid, dg), D(ask, dg), D(fill, dg),
       D(fill - px, dg), "", "", "", "", IntegerToString(delay), D(margin, 2), D(100.0 * realRisk / bal, 3),
       "bar open " + D(r[0].open, dg) + "; risk " + D(realRisk, 2) + " of target " + D(riskMoney, 2));
  }

//+------------------------------------------------------------------+
void ProcessSymbol(const int i)
  {
   string sym = g_s[i].name;
   CheckClosed(i);
   if(g_s[i].pos == 0)
     {
      ulong t = FindPosition(sym);
      if(t != 0 && PositionSelectByTicket(t))
        {
         g_s[i].pos = t;
         if(g_s[i].entry <= 0)
            g_s[i].entry = PositionGetDouble(POSITION_PRICE_OPEN);
         if(g_s[i].lots <= 0)
            g_s[i].lots = PositionGetDouble(POSITION_VOLUME);
         g_dirty = true;
        }
     }
   if(g_s[i].pendingExit)
      TryClose(i, "retry");
   datetime t0 = iTime(sym, RULE_TF, 0);
   if(t0 == 0 || t0 <= g_s[i].lastBar)
      return;
   MqlRates r[];
   ArraySetAsSeries(r, true);
   int got = CopyRates(sym, RULE_TF, 0, COPY_BARS, r);
   if(got < EXT_BARS + ATR_SLOW + ATR_FAST + 3 || r[0].time != t0)
      return;
   if(g_s[i].pos != 0)
      CheckTimeExit(i, r, got);
   else
      CheckEntry(i, r);
   g_s[i].lastBar = t0;
   g_dirty = true;
  }

//+------------------------------------------------------------------+
int OnInit()
  {
   g_tester = (bool)MQLInfoInteger(MQL_TESTER);
   string parts[];
   int n = StringSplit(PresetSymbols(InpMarketSet), ',', parts);
   ArrayResize(g_s, 0);
   for(int i = 0; i < n; i++)
     {
      string sym = parts[i];
      StringTrimLeft(sym);
      StringTrimRight(sym);
      if(sym == "")
         continue;
      if(!SymbolSelect(sym, true))
        {
         PrintFormat("G27K_M30: %s is not available on this account", sym);
         return INIT_PARAMETERS_INCORRECT;
        }
      int k = ArraySize(g_s);
      ArrayResize(g_s, k + 1);
      g_s[k].name = sym; g_s[k].digits = (int)SymbolInfoInteger(sym, SYMBOL_DIGITS);
      g_s[k].lastBar = 0; g_s[k].pos = 0; g_s[k].pendingExit = false; g_s[k].entryBar = 0;
      g_s[k].entry = 0; g_s[k].stop = 0; g_s[k].tp = 0; g_s[k].atr20 = 0; g_s[k].lots = 0; g_s[k].risk = 0; g_s[k].entryTime = 0;
     }
   if(ArraySize(g_s) == 0)
     {
      Print("G27K_M30: empty market set");
      return INIT_PARAMETERS_INCORRECT;
     }
   if(InpRiskPct <= 0.0 || InpRiskPct > 5.0)
     {
      Print("G27K_M30: InpRiskPct out of range");
      return INIT_PARAMETERS_INCORRECT;
     }
   g_canTrade = !(AccountInfoInteger(ACCOUNT_TRADE_MODE) == ACCOUNT_TRADE_MODE_REAL && !InpAllowRealAccount);
   if(!g_canTrade)
      Alert("G27K_M30: real-money account and InpAllowRealAccount = false - signals are logged, no orders will be sent");
   g_trade.SetExpertMagicNumber(InpMagic);
   g_trade.SetDeviationInPoints(1000);
   g_trade.LogLevel(LOG_LEVEL_ERRORS);
   if(g_tester)
      FileDelete(LogName(), FILE_COMMON);
   else
      LoadState();
   LogHeader();
   string list = "";
   for(int i = 0; i < ArraySize(g_s); i++)
      list += (i > 0 ? " " : "") + g_s[i].name;
   LogSimple("START", "", "markets " + list + "; risk " + D(InpRiskPct, 2) + "%; account " +
             IntegerToString(AccountInfoInteger(ACCOUNT_LOGIN)) + " " + AccountInfoString(ACCOUNT_SERVER) + " " +
             AccountInfoString(ACCOUNT_CURRENCY) + "; orders " + (g_canTrade ? "on" : "off"));
   EventSetTimer(g_tester ? 30 : MathMax(1, InpTimerSec));
   return INIT_SUCCEEDED;
  }

void OnDeinit(const int reason)
  {
   EventKillTimer();
   if(g_dirty)
      SaveState();
  }

void OnTimer()
  {
   for(int i = 0; i < ArraySize(g_s); i++)
      ProcessSymbol(i);
   if(g_dirty)
      SaveState();
  }

void OnTick()
  {
  }
//+------------------------------------------------------------------+
