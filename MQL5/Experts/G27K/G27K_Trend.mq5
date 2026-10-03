//+------------------------------------------------------------------+
//|                                                   G27K_Trend.mq5 |
//|  G27K #1 trend system. One instance trades every market in the   |
//|  set from a single chart, so the 25 % brake sees the whole       |
//|  account.                                                        |
//|                                                                  |
//|  Rules: docs/HANDOFF_G27K_FINAL.md section 1, matched to the     |
//|  research engine (g27k.prepare, report768.sim_paths):            |
//|   - H4 bar closes above the highest high of the previous 10 bars |
//|   - skip if a USD HIGH event is due in [signal close, +8 h],     |
//|     signal close = signal bar open + 4 h                         |
//|   - buy at the next bar's first tick, stop = bid - 2 x ATR20,    |
//|     ATR = simple mean of true range over 20 bars incl. signal    |
//|   - stop never moves; exit on an H4 close below the lowest low   |
//|     of the previous 20 bars, at the next bar's first tick        |
//|   - one trade per market; the bar in which a trade ended cannot  |
//|     be the next signal bar                                       |
//|   - 1 % of balance per trade, 0.5 % while the NAV drawdown brake |
//|     is on (on at >= 25 %, off at <= 12.5 %, evaluated at entries)|
//|   - lots rounded to the nearest step and floored at the broker   |
//|     minimum (ledger g27k_lot_rounding_nearest,                   |
//|     g27k_min_lot_floor_in_brake)                                 |
//|  Real-money accounts: no orders unless InpAllowRealAccount=true. |
//+------------------------------------------------------------------+
#property copyright   "EA-tread"
#property version     "1.00"
#property description "G27K #1: H4 10-bar breakout, long only, 2xATR20 stop, 20-bar channel exit,"
#property description "USD HIGH news filter, 1% risk with a 25% NAV brake. One instance per account."

#include <Trade/Trade.mqh>

//--- rule constants: research values. Change only through research/change_ledger.json.
#define ENTRY_BARS    10
#define EXIT_BARS     20
#define ATR_BARS      20
#define STOP_ATR      2.0
#define NEWS_HOURS    8
#define RISK_PCT      1.0
#define BRAKE_ON_DD   0.25
#define BRAKE_OFF_DD  0.125
#define BRAKE_MULT    0.5
#define RULE_TF       PERIOD_H4
#define SETUP_NAME    "G27K#1"
#define COPY_BARS     64         // enough to re-check up to ~40 bars missed while the EA was offline

enum ENUM_MARKET_SET
  {
   SET_CENT3        = 0,  // Cent: XAUUSDc XAGUSDc BTCUSDc
   SET_CENT4_USDJPY = 1,  // Cent: XAUUSDc XAGUSDc BTCUSDc USDJPYc
   SET_USD3         = 2,  // Standard: XAUUSD XAGUSD BTCUSD
   SET_USD4_USDJPY  = 3,  // Standard: XAUUSD XAGUSD BTCUSD USDJPY
   SET_USD4_JP225   = 4,  // Standard: XAUUSD XAGUSD BTCUSD JP225 (handoff original)
   SET_USD5         = 5,  // Standard: XAUUSD XAGUSD BTCUSD JP225 USDJPY
   SET_CUSTOM       = 6   // InpCustomSymbols
  };

enum ENUM_NEWS_SOURCE
  {
   NEWS_AUTO = 0,  // economic calendar live, file in the tester
   NEWS_API  = 1,  // MQL5 economic calendar
   NEWS_FILE = 2,  // InpNewsFile in Common\Files
   NEWS_OFF  = 3   // diagnostics only - this changes the rule
  };

input ENUM_MARKET_SET  InpMarketSet        = SET_CENT3;
input string           InpCustomSymbols    = "";                        // comma list, used with SET_CUSTOM
input long             InpMagic            = 27027001;
input ENUM_NEWS_SOURCE InpNewsSource       = NEWS_AUTO;
input string           InpNewsFile         = "g27k_news_usd_high.txt";  // Common\Files, one "YYYY.MM.DD HH:MM" UTC per line
input int              InpMaxEntryDelayMin = 60;     // skip an entry if trading in the new bar began longer ago (EA was offline)
input bool             InpAllowRealAccount = false;  // false: on a real-money account signals are logged and no orders are sent
input string           InpStateFile        = "g27k_state.txt";
input string           InpLogFile          = "g27k_log.csv";
input int              InpTimerSec         = 5;

struct SymState
  {
   string            name;
   int               digits;
   datetime          lastBar;      // open time of the newest H4 bar whose rules have run
   datetime          lastExitBar;  // open time of the H4 bar in which this market's last trade ended
   ulong             pos;          // our open position ticket, 0 = flat
   bool              pendingExit;  // channel exit decided but the close failed; retried every pass
   double            entry;        // fill price
   double            stop;
   double            atr;          // ATR20 at the signal bar
   double            lots;
   double            risk;         // money at risk at entry
   datetime          entryTime;
  };

struct LogRow
  {
   string            ev, sym, sigBar, sigClose, hi10, lo20, atr, news, brake, ndd, bal, riskPct, lots, stop, bid, ask, fill, slip,
                     xp, r, money, delay, margin, note;
  };

SymState g_s[];
CTrade   g_trade;
bool     g_tester   = false;
bool     g_canTrade = true;
bool     g_useApi   = false;
bool     g_useFile  = false;
datetime g_news[];
datetime g_newsFirst = 0;
//--- NAV per unit moves with trading results only, so deposits and withdrawals cannot hide or fake a drawdown
double   g_nav  = 1.0;
double   g_peak = 1.0;
double   g_bal  = 0.0;
bool     g_brake = false;
ulong    g_lastDeal = 0;
datetime g_lastDealTime = 0;
bool     g_dirty = false;

//+------------------------------------------------------------------+
string PresetSymbols(const ENUM_MARKET_SET set)
  {
   switch(set)
     {
      case SET_CENT3:        return "XAUUSDc,XAGUSDc,BTCUSDc";
      case SET_CENT4_USDJPY: return "XAUUSDc,XAGUSDc,BTCUSDc,USDJPYc";
      case SET_USD3:         return "XAUUSD,XAGUSD,BTCUSD";
      case SET_USD4_USDJPY:  return "XAUUSD,XAGUSD,BTCUSD,USDJPY";
      case SET_USD4_JP225:   return "XAUUSD,XAGUSD,BTCUSD,JP225";
      case SET_USD5:         return "XAUUSD,XAGUSD,BTCUSD,JP225,USDJPY";
      default:               return InpCustomSymbols;
     }
  }

int SymIndex(const string sym)
  {
   for(int i = 0; i < ArraySize(g_s); i++)
      if(g_s[i].name == sym)
         return i;
   return -1;
  }

string D(const double v, const int dg) { return DoubleToString(v, dg); }
string T(const datetime t)             { return t > 0 ? TimeToString(t, TIME_DATE | TIME_MINUTES) : ""; }

//+------------------------------------------------------------------+
//| log                                                              |
//+------------------------------------------------------------------+
void ResetRow(LogRow &x)
  {
   x.ev = ""; x.sym = ""; x.sigBar = ""; x.sigClose = ""; x.hi10 = ""; x.lo20 = ""; x.atr = ""; x.news = ""; x.brake = "";
   x.ndd = ""; x.bal = ""; x.riskPct = ""; x.lots = ""; x.stop = ""; x.bid = ""; x.ask = ""; x.fill = ""; x.slip = "";
   x.xp = ""; x.r = ""; x.money = ""; x.delay = ""; x.margin = ""; x.note = "";
  }

string LogName() { return g_tester ? "tester_" + InpLogFile : InpLogFile; }

int LogFlags()
  {
   int f = FILE_READ | FILE_WRITE | FILE_TXT | FILE_ANSI | FILE_SHARE_READ;
   if(g_tester)
      f |= FILE_COMMON;           // so the tester log can be read after the run
   return f;
  }

void LogHeader()
  {
   int h = FileOpen(LogName(), LogFlags());
   if(h == INVALID_HANDLE)
      return;
   if(FileSize(h) == 0)
      FileWriteString(h, "time,event,symbol,tf,setup,signal_bar,signal_close,high10,low20,atr20,news,brake,nav_dd,balance,"
                         "risk_pct,lots,stop,bid,ask,fill,slippage,exit_price,r_gross,money,delay_s,margin,note\r\n");
   FileClose(h);
  }

void WriteRow(const LogRow &x)
  {
   int h = FileOpen(LogName(), LogFlags());
   if(h == INVALID_HANDLE)
      return;
   FileSeek(h, 0, SEEK_END);
   string s = TimeToString(TimeCurrent(), TIME_DATE | TIME_SECONDS) + "," + x.ev + "," + x.sym + ",H4," + SETUP_NAME + "," +
              x.sigBar + "," + x.sigClose + "," + x.hi10 + "," + x.lo20 + "," + x.atr + "," + x.news + "," + x.brake + "," + x.ndd + "," +
              x.bal + "," + x.riskPct + "," + x.lots + "," + x.stop + "," + x.bid + "," + x.ask + "," + x.fill + "," + x.slip + "," +
              x.xp + "," + x.r + "," + x.money + "," + x.delay + "," + x.margin + "," + x.note + "\r\n";
   FileWriteString(h, s);
   FileClose(h);
  }

void LogSimple(const string ev, const string sym, const string note)
  {
   LogRow x;
   ResetRow(x);
   x.ev = ev; x.sym = sym; x.note = note;
   x.brake = g_brake ? "on" : "off";
   x.ndd = D(1.0 - g_nav / g_peak, 4);
   x.bal = D(AccountInfoDouble(ACCOUNT_BALANCE), 2);
   WriteRow(x);
  }

//+------------------------------------------------------------------+
//| state (kept across restarts; the tester always starts fresh)     |
//+------------------------------------------------------------------+
void FreshState()
  {
   g_nav = 1.0; g_peak = 1.0; g_brake = false;
   g_bal = AccountInfoDouble(ACCOUNT_BALANCE);
   g_lastDeal = 0; g_lastDealTime = 0;
   if(HistorySelect(0, TimeCurrent() + 86400))
      for(int i = HistoryDealsTotal() - 1; i >= 0; i--)
        {
         ulong t = HistoryDealGetTicket(i);
         if(t > g_lastDeal)
           {
            g_lastDeal = t;
            g_lastDealTime = (datetime)HistoryDealGetInteger(t, DEAL_TIME);
           }
        }
   g_dirty = true;
  }

bool LoadState()
  {
   int h = FileOpen(InpStateFile, FILE_READ | FILE_TXT | FILE_ANSI);
   if(h == INVALID_HANDLE)
      return false;
   bool ok = false;
   while(!FileIsEnding(h))
     {
      string line = FileReadString(h);
      int eq = StringFind(line, "=");
      if(eq <= 0)
         continue;
      string k = StringSubstr(line, 0, eq), v = StringSubstr(line, eq + 1);
      if(k == "nav")           { g_nav = StringToDouble(v); ok = true; }
      else if(k == "peak")     g_peak = StringToDouble(v);
      else if(k == "bal")      g_bal = StringToDouble(v);
      else if(k == "brake")    g_brake = (v == "1");
      else if(k == "lastdeal") g_lastDeal = (ulong)StringToInteger(v);
      else if(k == "lastdealtime") g_lastDealTime = (datetime)StringToInteger(v);
      else
        {
         int bar = StringFind(k, "|");
         if(bar <= 0)
            continue;
         int i = SymIndex(StringSubstr(k, 0, bar));
         if(i < 0)
            continue;
         string f = StringSubstr(k, bar + 1);
         if(f == "lastbar")        g_s[i].lastBar = (datetime)StringToInteger(v);
         else if(f == "lastexit")  g_s[i].lastExitBar = (datetime)StringToInteger(v);
         else if(f == "pos")       g_s[i].pos = (ulong)StringToInteger(v);
         else if(f == "entry")     g_s[i].entry = StringToDouble(v);
         else if(f == "stop")      g_s[i].stop = StringToDouble(v);
         else if(f == "atr")       g_s[i].atr = StringToDouble(v);
         else if(f == "lots")      g_s[i].lots = StringToDouble(v);
         else if(f == "risk")      g_s[i].risk = StringToDouble(v);
         else if(f == "entrytime") g_s[i].entryTime = (datetime)StringToInteger(v);
        }
     }
   FileClose(h);
   if(g_peak <= 0.0 || g_nav <= 0.0)
      return false;
   return ok;
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
      Print("G27K: cannot write the state file, error ", GetLastError());
      g_dirty = true;
      return;
     }
   FileWriteString(h, "nav=" + D(g_nav, 12) + "\r\n");
   FileWriteString(h, "peak=" + D(g_peak, 12) + "\r\n");
   FileWriteString(h, "bal=" + D(g_bal, 2) + "\r\n");
   FileWriteString(h, "brake=" + (g_brake ? "1" : "0") + "\r\n");
   FileWriteString(h, "lastdeal=" + IntegerToString((long)g_lastDeal) + "\r\n");
   FileWriteString(h, "lastdealtime=" + IntegerToString((long)g_lastDealTime) + "\r\n");
   for(int i = 0; i < ArraySize(g_s); i++)
     {
      string p = g_s[i].name + "|";
      FileWriteString(h, p + "lastbar=" + IntegerToString((long)g_s[i].lastBar) + "\r\n");
      FileWriteString(h, p + "lastexit=" + IntegerToString((long)g_s[i].lastExitBar) + "\r\n");
      FileWriteString(h, p + "pos=" + IntegerToString((long)g_s[i].pos) + "\r\n");
      FileWriteString(h, p + "entry=" + D(g_s[i].entry, g_s[i].digits) + "\r\n");
      FileWriteString(h, p + "stop=" + D(g_s[i].stop, g_s[i].digits) + "\r\n");
      FileWriteString(h, p + "atr=" + D(g_s[i].atr, g_s[i].digits + 2) + "\r\n");
      FileWriteString(h, p + "lots=" + D(g_s[i].lots, 2) + "\r\n");
      FileWriteString(h, p + "risk=" + D(g_s[i].risk, 2) + "\r\n");
      FileWriteString(h, p + "entrytime=" + IntegerToString((long)g_s[i].entryTime) + "\r\n");
     }
   FileClose(h);
   if(!FileMove(tmp, 0, InpStateFile, FILE_REWRITE))
     {
      Print("G27K: state file move failed, error ", GetLastError());
      g_dirty = true;
     }
  }

//+------------------------------------------------------------------+
//| news                                                             |
//+------------------------------------------------------------------+
bool LoadNewsFile()
  {
   int h = FileOpen(InpNewsFile, FILE_READ | FILE_TXT | FILE_ANSI | FILE_COMMON | FILE_SHARE_READ);
   if(h == INVALID_HANDLE)
      return false;
   ArrayResize(g_news, 0, 4096);
   while(!FileIsEnding(h))
     {
      string line = FileReadString(h);
      StringTrimLeft(line);
      StringTrimRight(line);
      if(line == "" || StringGetCharacter(line, 0) == '#')
         continue;
      datetime t = StringToTime(line);
      if(t <= 0)
         continue;
      int k = ArraySize(g_news);
      ArrayResize(g_news, k + 1, 4096);
      g_news[k] = t;
     }
   FileClose(h);
   ArraySort(g_news);
   g_newsFirst = ArraySize(g_news) > 0 ? g_news[0] : 0;
   PrintFormat("G27K: %d USD HIGH events from %s, first %s", ArraySize(g_news), InpNewsFile, T(g_newsFirst));
   return ArraySize(g_news) > 0;
  }

//--- 1 = a USD HIGH event is due in [tc, tc + 8 h], 0 = clear, -1 = calendar unavailable
int NewsBlocked(const datetime tc)
  {
   datetime t1 = tc + NEWS_HOURS * 3600;
   if(g_useFile)
     {
      int n = ArraySize(g_news);
      if(n == 0 || tc < g_newsFirst)
         return 0;                 // as in the research: the filter starts where the calendar data starts
      int lo = 0, hi = n;          // first event at or after tc
      while(lo < hi)
        {
         int mid = (lo + hi) / 2;
         if(g_news[mid] < tc)
            lo = mid + 1;
         else
            hi = mid;
        }
      return (lo < n && g_news[lo] <= t1) ? 1 : 0;
     }
   if(g_useApi)
     {
      //--- calendar times are trade-server time; the Exness server runs on GMT+0, the research calendar is UTC
      MqlCalendarValue vals[];
      ResetLastError();
      bool got = (CalendarValueHistory(vals, tc, t1, NULL, "USD") > 0) || ArraySize(vals) > 0;
      if(!got && GetLastError() != 0)
         return -1;
      for(int i = 0; i < ArraySize(vals); i++)
        {
         if(vals[i].time < tc || vals[i].time > t1)
            continue;
         MqlCalendarEvent ev;
         if(CalendarEventById(vals[i].event_id, ev) && ev.importance == CALENDAR_IMPORTANCE_HIGH)
            return 1;
        }
      return 0;
     }
   return 0;
  }

//+------------------------------------------------------------------+
//| NAV, brake                                                       |
//+------------------------------------------------------------------+
void UpdateNav()
  {
   datetime from = g_lastDealTime > 0 ? g_lastDealTime - 86400 : 0;
   if(!HistorySelect(from, TimeCurrent() + 86400))
      return;
   ulong tk[];
   int n = HistoryDealsTotal();
   for(int i = 0; i < n; i++)
     {
      ulong t = HistoryDealGetTicket(i);
      if(t > g_lastDeal)
        {
         int k = ArraySize(tk);
         ArrayResize(tk, k + 1);
         tk[k] = t;
        }
     }
   int m = ArraySize(tk);
   if(m == 0)
      return;
   ArraySort(tk);
   for(int j = 0; j < m; j++)
     {
      ulong t = tk[j];
      long type = HistoryDealGetInteger(t, DEAL_TYPE);
      double amt = HistoryDealGetDouble(t, DEAL_PROFIT) + HistoryDealGetDouble(t, DEAL_SWAP) +
                   HistoryDealGetDouble(t, DEAL_COMMISSION) + HistoryDealGetDouble(t, DEAL_FEE);
      if(type == DEAL_TYPE_CREDIT)
        {
         // credit is not balance
        }
      else
         if(type == DEAL_TYPE_BALANCE)
            g_bal += amt;          // deposit or withdrawal: NAV per unit unchanged
         else
            if(amt != 0.0)
              {
               if(g_bal > 0.0)
                  g_nav *= (g_bal + amt) / g_bal;
               g_bal += amt;
               if(g_nav > g_peak)
                  g_peak = g_nav;
              }
      g_lastDeal = t;
      g_lastDealTime = (datetime)HistoryDealGetInteger(t, DEAL_TIME);
     }
   double acc = AccountInfoDouble(ACCOUNT_BALANCE);
   if(MathAbs(acc - g_bal) > 0.005 * MathMax(1.0, MathAbs(acc)))
     {
      LogSimple("RESYNC", "", "tracked " + D(g_bal, 2) + " account " + D(acc, 2));
      g_bal = acc;
     }
   g_dirty = true;
  }

//--- the research changes the brake state only when a trade is about to be sized
void EvaluateBrake()
  {
   double dd = 1.0 - g_nav / g_peak;
   if(!g_brake && dd >= BRAKE_ON_DD)
     {
      g_brake = true;
      LogSimple("BRAKE_ON", "", "nav drawdown " + D(dd, 4));
     }
   else
      if(g_brake && dd <= BRAKE_OFF_DD)
        {
         g_brake = false;
         LogSimple("BRAKE_OFF", "", "nav drawdown " + D(dd, 4));
        }
  }

//+------------------------------------------------------------------+
//| helpers                                                          |
//+------------------------------------------------------------------+
double AtrAt(const MqlRates &r[], const int s)
  {
   double sum = 0.0;
   for(int i = s; i < s + ATR_BARS; i++)
     {
      double pc = r[i + 1].close;
      sum += MathMax(r[i].high, pc) - MathMin(r[i].low, pc);
     }
   return sum / ATR_BARS;
  }

double HighestHigh(const MqlRates &r[], const int from, const int count)
  {
   double v = r[from].high;
   for(int k = from + 1; k < from + count; k++)
      v = MathMax(v, r[k].high);
   return v;
  }

double LowestLow(const MqlRates &r[], const int from, const int count)
  {
   double v = r[from].low;
   for(int k = from + 1; k < from + count; k++)
      v = MathMin(v, r[k].low);
   return v;
  }

double RoundLots(const string sym, const double want)
  {
   double step = SymbolInfoDouble(sym, SYMBOL_VOLUME_STEP);
   double vmin = SymbolInfoDouble(sym, SYMBOL_VOLUME_MIN);
   double vmax = SymbolInfoDouble(sym, SYMBOL_VOLUME_MAX);
   if(step <= 0.0)
      step = vmin;
   double lots = MathFloor(want / step + 0.5) * step;   // nearest step, half up
   if(lots < vmin)
      lots = vmin;                                     // keep the minimum lot rather than skip the signal
   if(lots > vmax)
      lots = vmax;
   int dg = (int)MathMax(0.0, MathCeil(-MathLog10(step) - 1e-9));
   return NormalizeDouble(lots, dg);
  }

//--- time of the first trade in the bar opening at barOpen (metals reopen at 22:05 inside the 20:00 bar)
datetime FirstTickInBar(const string sym, const datetime barOpen)
  {
   MqlRates m1[];
   if(CopyRates(sym, PERIOD_M1, barOpen, TimeCurrent(), m1) > 0)
      return m1[0].time;
   return barOpen;
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
   g_s[i].pos = 0; g_s[i].pendingExit = false; g_s[i].entry = 0.0; g_s[i].stop = 0.0; g_s[i].atr = 0.0;
   g_s[i].lots = 0.0; g_s[i].risk = 0.0; g_s[i].entryTime = 0;
   g_dirty = true;
  }

void AdoptPosition(const int i)
  {
   ulong t = FindPosition(g_s[i].name);
   if(t == 0 || !PositionSelectByTicket(t))
      return;
   g_s[i].pos = t;
   if(g_s[i].entry <= 0.0)
      g_s[i].entry = PositionGetDouble(POSITION_PRICE_OPEN);
   if(g_s[i].stop <= 0.0)
      g_s[i].stop = PositionGetDouble(POSITION_SL);
   if(g_s[i].lots <= 0.0)
      g_s[i].lots = PositionGetDouble(POSITION_VOLUME);
   if(g_s[i].entryTime == 0)
      g_s[i].entryTime = (datetime)PositionGetInteger(POSITION_TIME);
   g_dirty = true;
  }

//--- money result of all deals of a position, and its closing deal
bool ExitDetails(const ulong pos, datetime &xt, double &xp, double &money, long &reason)
  {
   xt = 0; xp = 0.0; money = 0.0; reason = -1;
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
   LogRow x;
   ResetRow(x);
   int dg = g_s[i].digits;
   x.ev = ev; x.sym = g_s[i].name; x.atr = D(g_s[i].atr, dg + 2); x.stop = D(g_s[i].stop, dg); x.lots = D(g_s[i].lots, 2);
   x.fill = D(g_s[i].entry, dg); x.xp = D(xp, dg); x.money = D(money, 2);
   x.brake = g_brake ? "on" : "off"; x.ndd = D(1.0 - g_nav / g_peak, 4); x.bal = D(AccountInfoDouble(ACCOUNT_BALANCE), 2);
   if(g_s[i].atr > 0.0)
      x.r = D((xp - g_s[i].entry) / (STOP_ATR * g_s[i].atr), 4);   // gross R on the research risk unit 2 x ATR20
   x.note = note + "; entered " + T(g_s[i].entryTime) + "; exit bar " + T(g_s[i].lastExitBar) + "; exit " + TimeToString(xt, TIME_DATE | TIME_SECONDS);
   WriteRow(x);
  }

//+------------------------------------------------------------------+
//| exits                                                            |
//+------------------------------------------------------------------+
//--- a tracked position that is gone was closed by the stop, a stop-out or by hand
void CheckClosed(const int i)
  {
   ulong t = g_s[i].pos;
   if(t == 0 || PositionSelectByTicket(t))
      return;
   datetime xt; double xp, money; long reason;
   if(!ExitDetails(t, xt, xp, money, reason))
      return;                      // history not synced yet; next pass
   string sym = g_s[i].name;
   int sh = iBarShift(sym, RULE_TF, xt, false);
   datetime xb = sh >= 0 ? iTime(sym, RULE_TF, sh) : xt - (xt % PeriodSeconds(RULE_TF));
   if(xb > g_s[i].lastExitBar)
      g_s[i].lastExitBar = xb;
   string ev = reason == DEAL_REASON_SL ? "EXIT_STOP" : (reason == DEAL_REASON_SO ? "EXIT_STOPOUT" : "EXIT_OTHER");
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
   string sym = g_s[i].name;
   if(!g_trade.PositionClose(t))
     {
      LogSimple("EXIT_FAIL", sym, why + "; retcode " + IntegerToString((long)g_trade.ResultRetcode()) + " " + g_trade.ResultRetcodeDescription());
      return;                      // pendingExit stays set; retried next pass
     }
   uint rc = g_trade.ResultRetcode();
   if(rc != TRADE_RETCODE_DONE && rc != TRADE_RETCODE_DONE_PARTIAL && rc != TRADE_RETCODE_PLACED)
     {
      LogSimple("EXIT_FAIL", sym, why + "; retcode " + IntegerToString((long)rc));
      return;
     }
   datetime xb = iTime(sym, RULE_TF, 0);
   if(xb > g_s[i].lastExitBar)
      g_s[i].lastExitBar = xb;
   datetime xt; double xp, money; long reason;
   if(!ExitDetails(t, xt, xp, money, reason))
     {
      xt = TimeCurrent(); xp = g_trade.ResultPrice(); money = 0.0;
     }
   LogExit(i, "EXIT_CHANNEL", xt, xp, money, why);
   ClearTrade(i);
  }

//--- holding: exit if any completed bar not yet checked closed below its 20-bar low (normally only bar 1)
void CheckChannelExit(const int i, const MqlRates &r[], const int unchecked)
  {
   if(!PositionSelectByTicket(g_s[i].pos))
      return;                      // gone meanwhile; CheckClosed records it on the next pass
   int dg = g_s[i].digits;
   for(int k = unchecked; k >= 1; k--)
     {
      double lo = LowestLow(r, k + 1, EXIT_BARS);
      if(r[k].close < lo)
        {
         g_s[i].pendingExit = true;
         string why = "close " + D(r[k].close, dg) + " < low20 " + D(lo, dg) + " on bar " + T(r[k].time) + (k > 1 ? " (late: EA was offline)" : "");
         TryClose(i, why);
         return;
        }
     }
  }

//+------------------------------------------------------------------+
//| entries                                                          |
//+------------------------------------------------------------------+
void CheckEntry(const int i, const MqlRates &r[], const int unchecked)
  {
   string sym = g_s[i].name;
   int dg = g_s[i].digits;
   //--- signals on older bars missed while offline are logged, never traded
   for(int k = unchecked; k >= 2; k--)
      if(r[k].close > HighestHigh(r, k + 1, ENTRY_BARS) && r[k].time > g_s[i].lastExitBar)
         LogSimple("SKIP_LATE", sym, "missed signal on bar " + T(r[k].time) + " while the EA was offline");
   double hi = HighestHigh(r, 2, ENTRY_BARS);
   if(!(r[1].close > hi))
      return;
   double atr = AtrAt(r, 1);
   datetime tc = r[1].time + PeriodSeconds(RULE_TF);     // signal close as in the research: bar open + 4 h
   LogRow x;
   ResetRow(x);
   x.sym = sym; x.sigBar = T(r[1].time); x.sigClose = D(r[1].close, dg); x.hi10 = D(hi, dg); x.atr = D(atr, dg + 2);
   x.lo20 = D(LowestLow(r, 2, EXIT_BARS), dg);
   if(r[1].time <= g_s[i].lastExitBar)
     {
      x.ev = "SKIP_REENTRY"; x.note = "signal bar is not after the exit bar " + T(g_s[i].lastExitBar);
      WriteRow(x);
      return;
     }
   int nb = NewsBlocked(tc);
   x.news = nb == 1 ? "blocked" : (nb == 0 ? "clear" : "unknown");
   if(nb == 1)
     {
      x.ev = "SKIP_NEWS"; x.note = "USD HIGH event within " + IntegerToString(NEWS_HOURS) + " h after " + T(tc);
      WriteRow(x);
      return;
     }
   datetime first = FirstTickInBar(sym, r[0].time);
   long delay = (long)(TimeCurrent() - first);
   x.delay = IntegerToString(delay);
   if(delay > (long)InpMaxEntryDelayMin * 60)
     {
      x.ev = "SKIP_LATE"; x.note = "trading in the entry bar began " + IntegerToString(delay / 60) + " min ago";
      WriteRow(x);
      return;
     }
   if(atr <= 0.0)
     {
      x.ev = "SKIP_DATA"; x.note = "ATR20 not positive";
      WriteRow(x);
      return;
     }
   EvaluateBrake();
   double mult = g_brake ? BRAKE_MULT : 1.0;
   double bal = AccountInfoDouble(ACCOUNT_BALANCE);
   double riskMoney = bal * RISK_PCT / 100.0 * mult;
   double bid = SymbolInfoDouble(sym, SYMBOL_BID), ask = SymbolInfoDouble(sym, SYMBOL_ASK);
   double stop = NormalizeDouble(bid - STOP_ATR * atr, dg);
   x.brake = g_brake ? "on" : "off"; x.ndd = D(1.0 - g_nav / g_peak, 4); x.bal = D(bal, 2);
   x.bid = D(bid, dg); x.ask = D(ask, dg); x.stop = D(stop, dg);
   double pnl = 0.0;
   if(bid <= 0.0 || !OrderCalcProfit(ORDER_TYPE_BUY, sym, 1.0, bid, stop, pnl) || pnl >= 0.0)
     {
      x.ev = "SKIP_CALC"; x.note = "cannot value the stop distance, error " + IntegerToString(GetLastError());
      WriteRow(x);
      return;
     }
   double lossPerLot = -pnl;
   double lots = RoundLots(sym, riskMoney / lossPerLot);
   double realRisk = lots * lossPerLot;
   double margin = 0.0;
   if(!OrderCalcMargin(ORDER_TYPE_BUY, sym, lots, ask, margin))
      margin = -1.0;
   x.lots = D(lots, 2); x.riskPct = D(100.0 * realRisk / bal, 3); x.margin = D(margin, 2);
   if(margin > AccountInfoDouble(ACCOUNT_MARGIN_FREE))
     {
      x.ev = "SKIP_MARGIN"; x.note = "needs " + D(margin, 2) + " free " + D(AccountInfoDouble(ACCOUNT_MARGIN_FREE), 2);
      WriteRow(x);
      return;
     }
   if(!g_canTrade)
     {
      x.ev = "SIGNAL_ONLY"; x.note = "real-money account with InpAllowRealAccount = false";
      WriteRow(x);
      return;
     }
   g_trade.SetTypeFillingBySymbol(sym);
   if(!g_trade.Buy(lots, sym, 0.0, stop, 0.0, SETUP_NAME))
     {
      x.ev = "ENTRY_FAIL"; x.note = "retcode " + IntegerToString((long)g_trade.ResultRetcode()) + " " + g_trade.ResultRetcodeDescription();
      WriteRow(x);
      return;
     }
   uint rc = g_trade.ResultRetcode();
   if(rc != TRADE_RETCODE_DONE && rc != TRADE_RETCODE_DONE_PARTIAL && rc != TRADE_RETCODE_PLACED)
     {
      x.ev = "ENTRY_FAIL"; x.note = "retcode " + IntegerToString((long)rc);
      WriteRow(x);
      return;
     }
   double fill = g_trade.ResultPrice();
   ulong pos = FindPosition(sym);
   if(pos != 0 && PositionSelectByTicket(pos))
     {
      if(fill <= 0.0)
         fill = PositionGetDouble(POSITION_PRICE_OPEN);
      if(PositionGetDouble(POSITION_SL) <= 0.0 && !g_trade.PositionModify(pos, stop, 0.0))
         LogSimple("STOP_FAIL", sym, "stop not attached, retcode " + IntegerToString((long)g_trade.ResultRetcode()));
     }
   if(fill <= 0.0)
      fill = ask;
   g_s[i].pos = pos; g_s[i].entry = fill; g_s[i].stop = stop; g_s[i].atr = atr; g_s[i].lots = lots; g_s[i].risk = realRisk;
   g_s[i].entryTime = TimeCurrent();
   g_dirty = true;
   x.ev = "ENTRY"; x.fill = D(fill, dg); x.slip = D(fill - ask, dg);
   x.note = "bar open " + D(r[0].open, dg) + "; risk " + D(realRisk, 2) + " of target " + D(riskMoney, 2);
   WriteRow(x);
  }

//+------------------------------------------------------------------+
//| per market, every pass                                           |
//+------------------------------------------------------------------+
void ProcessSymbol(const int i)
  {
   string sym = g_s[i].name;
   CheckClosed(i);
   if(g_s[i].pos == 0)
      AdoptPosition(i);            // an async fill, or a restart
   if(g_s[i].pendingExit)
      TryClose(i, "retry");
   datetime t0 = iTime(sym, RULE_TF, 0);
   if(t0 == 0 || t0 <= g_s[i].lastBar)
      return;
   MqlRates r[];
   ArraySetAsSeries(r, true);
   int got = CopyRates(sym, RULE_TF, 0, COPY_BARS, r);
   if(got < EXIT_BARS + 3 || r[0].time != t0)
      return;                      // history not ready; retried next pass
   //--- completed bars not checked yet: normally 1, more if the EA was offline
   int unchecked = 1;
   if(g_s[i].lastBar > 0)
      while(unchecked + 1 < got - EXIT_BARS - 1 && r[unchecked + 1].time >= g_s[i].lastBar)
         unchecked++;
   if(g_s[i].pos != 0)
      CheckChannelExit(i, r, unchecked);
   else
      CheckEntry(i, r, unchecked);
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
         PrintFormat("G27K: %s is not available on this account", sym);
         return INIT_PARAMETERS_INCORRECT;
        }
      int k = ArraySize(g_s);
      ArrayResize(g_s, k + 1);
      g_s[k].name = sym; g_s[k].digits = (int)SymbolInfoInteger(sym, SYMBOL_DIGITS);
      g_s[k].lastBar = 0; g_s[k].lastExitBar = 0; g_s[k].pos = 0; g_s[k].pendingExit = false;
      g_s[k].entry = 0.0; g_s[k].stop = 0.0; g_s[k].atr = 0.0; g_s[k].lots = 0.0; g_s[k].risk = 0.0; g_s[k].entryTime = 0;
     }
   if(ArraySize(g_s) == 0)
     {
      Print("G27K: empty market set");
      return INIT_PARAMETERS_INCORRECT;
     }
   g_canTrade = !(AccountInfoInteger(ACCOUNT_TRADE_MODE) == ACCOUNT_TRADE_MODE_REAL && !InpAllowRealAccount);
   if(!g_canTrade)
      Alert("G27K: real-money account and InpAllowRealAccount = false - signals are logged, no orders will be sent");
   g_trade.SetExpertMagicNumber(InpMagic);
   g_trade.SetDeviationInPoints(1000);
   g_trade.LogLevel(LOG_LEVEL_ERRORS);
   g_useApi  = InpNewsSource == NEWS_API  || (InpNewsSource == NEWS_AUTO && !g_tester);
   g_useFile = InpNewsSource == NEWS_FILE || (InpNewsSource == NEWS_AUTO && g_tester);
   if(g_useFile && !LoadNewsFile())
     {
      PrintFormat("G27K: news file %s missing or empty in Common\\Files", InpNewsFile);
      return INIT_FAILED;
     }
   if(InpNewsSource == NEWS_OFF)
      Print("G27K: news filter OFF - this is not the research rule");
   if(g_tester)
      FileDelete(LogName(), FILE_COMMON);
   if(g_tester || !LoadState())
      FreshState();
   for(int i = 0; i < ArraySize(g_s); i++)
      if(g_s[i].pos == 0)
         AdoptPosition(i);
   LogHeader();
   string list = "";
   for(int i = 0; i < ArraySize(g_s); i++)
      list += (i > 0 ? " " : "") + g_s[i].name;
   LogSimple("START", "", "markets " + list + "; account " + IntegerToString(AccountInfoInteger(ACCOUNT_LOGIN)) + " " +
             AccountInfoString(ACCOUNT_SERVER) + " " + AccountInfoString(ACCOUNT_CURRENCY) + "; orders " + (g_canTrade ? "on" : "off") +
             "; news " + (g_useApi ? "calendar" : (g_useFile ? "file" : "off")));
   EventSetTimer(g_tester ? 60 : MathMax(1, InpTimerSec));
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
   UpdateNav();
   for(int i = 0; i < ArraySize(g_s); i++)
      ProcessSymbol(i);
   if(g_dirty)
      SaveState();
  }

void OnTick()
  {
  }
//+------------------------------------------------------------------+
