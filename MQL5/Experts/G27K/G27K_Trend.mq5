//+------------------------------------------------------------------+
//|                                                   G27K_Trend.mq5 |
//|  G27K-F: the G27K #1 trend system with the Fed rule. One instance |
//|  trades every market in the set from a single chart.              |
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
//|   - InpRiskPct (1 %) of balance per trade; with InpBrake on, half |
//|     while the NAV drawdown brake is on (on at >= 25 %, off at     |
//|     <= 12.5 %, evaluated at entries). The operator runs it off.   |
//|   - lots rounded to the nearest step and floored at the broker   |
//|     minimum (ledger g27k_lot_rounding_nearest,                   |
//|     g27k_min_lot_floor_in_brake)                                 |
//|  Fed rule (G27K-F; research/g27k_dev/news_shock.py fed_shocks,   |
//|  apply), gold, silver, BTC and ETH only:                         |
//|   - a day on which the US 2-year yield (FRED DGS2) rises by at    |
//|     least 2 SD of the previous 250 daily changes acts at 22:00 UTC|
//|     of the next US federal business day                          |
//|   - an open trade entered before that time closes at the first   |
//|     tick of the hour after it; no entry for 5 days after it      |
//|   - the research drops those trades from the G27K #1 list, so the|
//|     market stays taken until the dropped or cut trade would have |
//|     ended: the EA follows it as a shadow and enters nothing then  |
//|  Real-money accounts: no orders unless InpAllowRealAccount=true. |
//+------------------------------------------------------------------+
#property copyright   "EA-tread"
#property version     "1.10"
#property description "G27K-F: H4 10-bar breakout, long only, 2xATR20 stop, 20-bar channel exit, USD HIGH news filter,"
#property description "Fed 2-year-yield rule, risk per trade InpRiskPct, optional 25% NAV brake. One instance per account."

#include <Trade/Trade.mqh>

//--- rule constants: research values. Change only through research/change_ledger.json.
#define ENTRY_BARS    10
#define EXIT_BARS     20
#define ATR_BARS      20
#define STOP_ATR      2.0
#define NEWS_HOURS    8
#define BRAKE_ON_DD   0.25
#define BRAKE_OFF_DD  0.125
#define BRAKE_MULT    0.5
#define RULE_TF       PERIOD_H4
#define SETUP_NAME    "G27K#1"
#define COPY_BARS     64         // enough to re-check up to ~40 bars missed while the EA was offline
//--- Fed rule (news_shock.fed_shocks / news_shock.apply)
#define FED_SD_MULT    2.0       // a daily rise of at least 2 SD ...
#define FED_SD_WIN     250       // ... of the previous 250 daily changes (pandas rolling(250).std().shift(1))
#define FED_SD_MINP    120       // pandas min_periods
#define FED_PUB_HOUR   22        // usable from 22:00 UTC of the next US federal business day
#define FED_BLOCK_DAYS 5         // no entry for 5 days after that time
#define FED_HIT        "XAUUSD,XAGUSD,BTCUSD,ETHUSD"

enum ENUM_MARKET_SET
  {
   SET_CENT3        = 0,  // Cent: XAUUSDc XAGUSDc BTCUSDc
   SET_CENT4_USDJPY = 1,  // Cent: XAUUSDc XAGUSDc BTCUSDc USDJPYc
   SET_USD3         = 2,  // Standard: XAUUSD XAGUSD BTCUSD
   SET_USD4_USDJPY  = 3,  // Standard: XAUUSD XAGUSD BTCUSD USDJPY
   SET_USD4_JP225   = 4,  // Standard: XAUUSD XAGUSD BTCUSD JP225 (handoff original)
   SET_USD5         = 5,  // Standard: XAUUSD XAGUSD BTCUSD JP225 USDJPY
   SET_CUSTOM       = 6,  // InpCustomSymbols
   SET_CENT4_ETH    = 7,  // Cent: XAUUSDc XAGUSDc BTCUSDc ETHUSDc (G27K-F without USDJPY)
   SET_USD4_ETH     = 8   // Standard/demo: XAUUSD XAGUSD BTCUSD ETHUSD (mirrors SET_CENT4_ETH at 100x the balance)
  };

enum ENUM_FED_SOURCE
  {
   FED_AUTO = 0,  // live: download from FRED and keep a copy in the file; tester: the file
   FED_WEB  = 1,  // download from FRED (allow the URL in Tools > Options > Expert Advisors)
   FED_FILE = 2,  // InpFedFile in Common\Files (FRED DGS2 csv: observation_date,DGS2)
   FED_OFF  = 3   // diagnostics only - this is G27K #1, not G27K-F
  };

enum ENUM_NEWS_SOURCE
  {
   NEWS_AUTO = 0,  // economic calendar live, file in the tester
   NEWS_API  = 1,  // MQL5 economic calendar
   NEWS_FILE = 2,  // InpNewsFile in Common\Files
   NEWS_OFF  = 3   // diagnostics only - this changes the rule
  };

input ENUM_MARKET_SET  InpMarketSet        = SET_USD4_ETH;
input string           InpCustomSymbols    = "";                        // comma list, used with SET_CUSTOM
input int              InpH4StartHour      = 22;     // H4 bars built from H1 from this UTC hour: 22 (22/02/06/10/14/18) as every research report; 0 = 00/04/08/..
input double           InpRiskPct          = 1.0;    // % of balance per trade
input bool             InpBrake            = false;  // true: half risk while the NAV drawdown is >= 25 % (until <= 12.5 %)
input long             InpMagic            = 27027001;
input ENUM_NEWS_SOURCE InpNewsSource       = NEWS_AUTO;
input string           InpNewsFile         = "g27k_news_usd_high.txt";  // Common\Files, one "YYYY.MM.DD HH:MM" UTC per line
input ENUM_FED_SOURCE  InpFedSource        = FED_AUTO;
input string           InpFedFile          = "g27k_DGS2.csv";           // Common\Files, FRED DGS2 csv
input string           InpFedUrl           = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=DGS2";
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
   bool              pendingFed;   // the pending exit is the Fed rule's
   datetime          waitTick;     // the close met a closed market: retry only after a tick newer than this
   bool              entryWait;    // the entry met a closed market: the same bar is checked again at the next tick
   datetime          waitBar;      // the bar whose entry wait was logged (one log line per bar)
   bool              sessions;     // the symbol publishes trading sessions (false: treat it as always open)
   double            entry;        // fill price
   double            stop;
   double            atr;          // ATR20 at the signal bar
   double            lots;
   double            risk;         // money at risk at entry
   datetime          entryTime;
   datetime          entryBar;     // open time of the H4 bar the position was entered in (the research's trade time)
   bool              fed;          // the Fed rule covers this market
   bool              shadow;       // a trade the Fed rule dropped or cut is still running in the research: no entries
   datetime          shEntryBar;   // its entry bar
   double            shStop;       // its stop
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
double   g_seenBal = -1.0;          // balance at the last deal scan; a scan is needed only when it changes
//--- Fed rule
datetime g_fedPub[];                // times the rule acts (UTC), ascending
datetime g_fedLastObs = 0;          // newest DGS2 observation date loaded
bool     g_fedOn = false, g_fedWeb = false, g_fedFile = false;
datetime g_fedNextFetch = 0;
int      g_fedStaleDay = -1;

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
      case SET_CENT4_ETH:    return "XAUUSDc,XAGUSDc,BTCUSDc,ETHUSDc";
      case SET_USD4_ETH:     return "XAUUSD,XAGUSD,BTCUSD,ETHUSD";
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
         else if(f == "entrybar")  g_s[i].entryBar = (datetime)StringToInteger(v);
         else if(f == "shadow")    g_s[i].shadow = (v == "1");
         else if(f == "shentrybar") g_s[i].shEntryBar = (datetime)StringToInteger(v);
         else if(f == "shstop")    g_s[i].shStop = StringToDouble(v);
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
      FileWriteString(h, p + "entrybar=" + IntegerToString((long)g_s[i].entryBar) + "\r\n");
      FileWriteString(h, p + "shadow=" + (g_s[i].shadow ? "1" : "0") + "\r\n");
      FileWriteString(h, p + "shentrybar=" + IntegerToString((long)g_s[i].shEntryBar) + "\r\n");
      FileWriteString(h, p + "shstop=" + D(g_s[i].shStop, g_s[i].digits) + "\r\n");
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
//| Fed rule: US federal business days (pandas USFederalHolidayCalendar) |
//+------------------------------------------------------------------+
datetime MkDate(const int y, const int m, const int d)
  {
   MqlDateTime t;
   ZeroMemory(t);
   t.year = y; t.mon = m; t.day = d;
   return StructToTime(t);
  }

int Dow(const datetime d)                          // 0 = Sunday
  {
   MqlDateTime t;
   TimeToStruct(d, t);
   return t.day_of_week;
  }

datetime DayStart(const datetime t) { return t - (t % 86400); }

datetime NearestWorkday(const datetime d)          // Saturday -> Friday, Sunday -> Monday
  {
   int w = Dow(d);
   return w == 6 ? d - 86400 : (w == 0 ? d + 86400 : d);
  }

datetime NthWeekday(const int y, const int m, const int d, const int wd, const int n)   // n-th weekday wd on or after y-m-d
  {
   datetime x = MkDate(y, m, d);
   while(Dow(x) != wd)
      x += 86400;
   return x + (n - 1) * 7 * 86400;
  }

datetime LastWeekdayOnOrBefore(const int y, const int m, const int d, const int wd)
  {
   datetime x = MkDate(y, m, d);
   while(Dow(x) != wd)
      x -= 86400;
   return x;
  }

bool UsHoliday(const datetime day)
  {
   MqlDateTime t;
   TimeToStruct(day, t);
   int y = t.year;
   datetime d = MkDate(y, t.mon, t.day);
   if(d == NearestWorkday(MkDate(y, 1, 1)) || d == NearestWorkday(MkDate(y + 1, 1, 1)))   // 1 Jan can be observed on 31 Dec
      return true;
   if(y >= 1986 && d == NthWeekday(y, 1, 1, 1, 3))   return true;    // Martin Luther King Jr. Day
   if(d == NthWeekday(y, 2, 1, 1, 3))                return true;    // Washington's Birthday
   if(d == LastWeekdayOnOrBefore(y, 5, 31, 1))       return true;    // Memorial Day
   if(d >= MkDate(2021, 6, 18) && d == NearestWorkday(MkDate(y, 6, 19))) return true;   // Juneteenth
   if(d == NearestWorkday(MkDate(y, 7, 4)))          return true;    // Independence Day
   if(d == NthWeekday(y, 9, 1, 1, 1))                return true;    // Labor Day
   if(d == NthWeekday(y, 10, 1, 1, 2))               return true;    // Columbus Day
   if(d == NearestWorkday(MkDate(y, 11, 11)))        return true;    // Veterans Day
   if(d == NthWeekday(y, 11, 1, 4, 4))               return true;    // Thanksgiving
   if(d == NearestWorkday(MkDate(y, 12, 25)))        return true;    // Christmas
   return false;
  }

bool UsBusinessDay(const datetime d) { int w = Dow(d); return w != 0 && w != 6 && !UsHoliday(d); }

datetime NextUsBusinessDay(const datetime day)
  {
   datetime x = DayStart(day) + 86400;
   while(!UsBusinessDay(x))
      x += 86400;
   return x;
  }

datetime PrevUsBusinessDay(const datetime day)
  {
   datetime x = DayStart(day) - 86400;
   while(!UsBusinessDay(x))
      x -= 86400;
   return x;
  }

//+------------------------------------------------------------------+
//| Fed rule: data                                                   |
//+------------------------------------------------------------------+
bool IsNumber(const string s)
  {
   int digits = 0;
   for(int i = 0; i < StringLen(s); i++)
     {
      ushort c = StringGetCharacter(s, i);
      if(c >= '0' && c <= '9')
         digits++;
      else
         if(c != '.' && c != '-' && c != '+')
            return false;
     }
   return digits > 0;
  }

//--- FRED csv lines ("YYYY-MM-DD,value", missing values empty or ".") -> the times the rule acts, exactly as fed_shocks():
//--- change = value - previous value over the observed days; sd = sample SD of the previous 250 changes (at least 120);
//--- a rise of at least 2 sd acts at 22:00 UTC of the next US federal business day
bool FedParse(string &lines[], const int n, datetime &pub[], datetime &lastObs, string &why)
  {
   datetime dt[];
   double   v[];
   ArrayResize(dt, n);
   ArrayResize(v, n);
   int m = 0;
   for(int i = 0; i < n; i++)
     {
      string s = lines[i];
      StringTrimLeft(s);
      StringTrimRight(s);
      if(StringLen(s) < 12 || StringGetCharacter(s, 10) != ',')
         continue;                                  // header or blank
      string ds = StringSubstr(s, 0, 10), vs = StringSubstr(s, 11);
      if(!IsNumber(vs))
         continue;                                  // missing value
      StringReplace(ds, "-", ".");
      datetime d = StringToTime(ds);
      if(d <= 0 || (m > 0 && d <= dt[m - 1]))
         continue;
      dt[m] = d;
      v[m] = StringToDouble(vs);
      m++;
     }
   if(m < FED_SD_MINP + 2)
     {
      why = "only " + IntegerToString(m) + " observations";
      return false;
     }
   ArrayResize(pub, 0, 512);
   for(int i = 2; i < m; i++)
     {
      int lo = MathMax(1, i - FED_SD_WIN), cnt = i - lo;
      if(cnt < FED_SD_MINP)
         continue;
      double mean = 0.0;
      for(int j = lo; j < i; j++)
         mean += v[j] - v[j - 1];
      mean /= cnt;
      double ss = 0.0;
      for(int j = lo; j < i; j++)
        {
         double e = (v[j] - v[j - 1]) - mean;
         ss += e * e;
        }
      double sd = MathSqrt(ss / (cnt - 1));
      if(v[i] - v[i - 1] >= FED_SD_MULT * sd)
        {
         int k = ArraySize(pub);
         ArrayResize(pub, k + 1, 512);
         pub[k] = NextUsBusinessDay(dt[i]) + FED_PUB_HOUR * 3600;
        }
     }
   lastObs = dt[m - 1];
   return true;
  }

bool FedInstall(string &lines[], const int n, string &why)
  {
   datetime pub[];
   datetime last = 0;
   if(!FedParse(lines, n, pub, last, why))
      return false;
   ArrayFree(g_fedPub);
   ArrayCopy(g_fedPub, pub);
   g_fedLastObs = last;
   return true;
  }

bool FedLoadFile(string &why)
  {
   int h = FileOpen(InpFedFile, FILE_READ | FILE_TXT | FILE_ANSI | FILE_COMMON | FILE_SHARE_READ);
   if(h == INVALID_HANDLE)
     {
      why = InpFedFile + " not found in Common\\Files";
      return false;
     }
   string lines[];
   ArrayResize(lines, 0, 16384);
   int n = 0;
   while(!FileIsEnding(h))
     {
      ArrayResize(lines, n + 1, 16384);
      lines[n++] = FileReadString(h);
     }
   FileClose(h);
   return FedInstall(lines, n, why);
  }

bool FedFetchWeb(string &why)
  {
   char body[], res[];
   string head;
   ResetLastError();
   int code = WebRequest("GET", InpFedUrl, "", 20000, body, res, head);
   if(code != 200)
     {
      int err = GetLastError();
      why = code == -1 ? "WebRequest error " + IntegerToString(err) +
            (err == 4014 ? " - add https://fred.stlouisfed.org in Tools > Options > Expert Advisors" : "")
            : "HTTP " + IntegerToString(code);
      return false;
     }
   string lines[];
   int n = StringSplit(CharArrayToString(res, 0, WHOLE_ARRAY, CP_UTF8), '\n', lines);
   if(!FedInstall(lines, n, why))
      return false;
   int h = FileOpen(InpFedFile, FILE_WRITE | FILE_TXT | FILE_ANSI | FILE_COMMON);   // a copy for when the next download fails
   if(h != INVALID_HANDLE)
     {
      for(int i = 0; i < n; i++)
        {
         string s = lines[i];
         StringTrimRight(s);
         if(s != "")
            FileWriteString(h, s + "\r\n");
        }
      FileClose(h);
     }
   return true;
  }

string FedSummary()
  {
   int n = ArraySize(g_fedPub);
   datetime now = g_tester ? TimeCurrent() : TimeGMT();
   int k = n - 1;
   while(k >= 0 && g_fedPub[k] > now)
      k--;
   return IntegerToString(n) + " rule times; newest observation " + TimeToString(g_fedLastObs, TIME_DATE) +
          (k >= 0 ? "; latest rule time " + T(g_fedPub[k]) : "") + (k + 1 < n ? "; next " + T(g_fedPub[k + 1]) : "");
  }

//--- live: download at fixed times around the 22:00 UTC decision, warn once a day when the data is behind
void FedMaintain()
  {
   if(!g_fedOn || g_tester || !g_fedWeb)
      return;
   datetime now = TimeGMT();
   if(now >= g_fedNextFetch)
     {
      string why;
      if(FedFetchWeb(why))
        {
         LogSimple("FED_DATA", "", "download: " + FedSummary());
         int slots[] = {7 * 60 + 35, 19 * 60 + 35, 20 * 60 + 35, 21 * 60 + 5, 21 * 60 + 35, 21 * 60 + 55, 22 * 60 + 35, 23 * 60 + 35};
         datetime d0 = DayStart(now), nxt = d0 + 86400 + slots[0] * 60;
         for(int k = 0; k < ArraySize(slots); k++)
            if(d0 + slots[k] * 60 > now)
              {
               nxt = d0 + slots[k] * 60;
               break;
              }
         g_fedNextFetch = nxt;
        }
      else
        {
         LogSimple("FED_FAIL", "", why + "; using the data loaded earlier (" + FedSummary() + "); retry in 10 min");
         g_fedNextFetch = now + 600;
        }
     }
   datetime d0 = DayStart(now);
   MqlDateTime t;
   TimeToStruct(now, t);
   if(UsBusinessDay(d0) && t.hour == 23 && t.min >= 40 && g_fedStaleDay != t.day_of_year && g_fedLastObs < PrevUsBusinessDay(d0))
     {
      g_fedStaleDay = t.day_of_year;
      LogSimple("FED_STALE", "", "newest DGS2 observation " + TimeToString(g_fedLastObs, TIME_DATE) + " is older than " +
                TimeToString(PrevUsBusinessDay(d0), TIME_DATE) + " - the Fed rule may act late");
     }
  }

//+------------------------------------------------------------------+
//| Fed rule: use                                                    |
//+------------------------------------------------------------------+
bool FedCovers(const string sym)
  {
   string base = StringLen(sym) > 6 ? StringSubstr(sym, 0, 6) : sym;   // XAUUSDc -> XAUUSD
   return StringFind(FED_HIT, base) >= 0;
  }

int FedIndexAtOrBefore(const datetime t)            // last rule time <= t, -1 if none
  {
   int lo = 0, hi = ArraySize(g_fedPub);
   while(lo < hi)
     {
      int mid = (lo + hi) / 2;
      if(g_fedPub[mid] <= t)
         lo = mid + 1;
      else
         hi = mid;
     }
   return lo - 1;
  }

//--- the rule time that blocks an entry at t (the research's trade time: the entry bar's open), 0 if none
datetime FedBlock(const datetime t)
  {
   int k = FedIndexAtOrBefore(t);
   return (k >= 0 && t - g_fedPub[k] < FED_BLOCK_DAYS * 86400) ? g_fedPub[k] : 0;
  }

//--- the first rule time after a trade entered at t, 0 if none
datetime FedFirstAfter(const datetime t)
  {
   int k = FedIndexAtOrBefore(t) + 1;
   return k < ArraySize(g_fedPub) ? g_fedPub[k] : 0;
  }

//+------------------------------------------------------------------+
//| NAV, brake                                                       |
//+------------------------------------------------------------------+
void UpdateNav()
  {
   double accNow = AccountInfoDouble(ACCOUNT_BALANCE);
   if(accNow == g_seenBal)
      return;                      // nothing closed, deposited or withdrawn since the last scan that was in sync
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
   if(m > 0)
     {
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
               g_bal += amt;       // deposit or withdrawal: NAV per unit unchanged
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
      g_dirty = true;
     }
   double tol = 0.005 * MathMax(1.0, MathAbs(accNow));
   if(MathAbs(accNow - g_bal) <= tol)
      g_seenBal = accNow;          // in sync: skip scans until the balance moves again
   else
      if(m > 0)
        {
         LogSimple("RESYNC", "", "tracked " + D(g_bal, 2) + " account " + D(accNow, 2));
         g_bal = accNow;
         g_seenBal = accNow;
         g_dirty = true;
        }
      // m == 0 and out of sync: the deal is not in the history yet; scan again next pass
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
   g_s[i].pos = 0; g_s[i].pendingExit = false; g_s[i].pendingFed = false; g_s[i].waitTick = 0;
   g_s[i].entry = 0.0; g_s[i].stop = 0.0; g_s[i].atr = 0.0;
   g_s[i].lots = 0.0; g_s[i].risk = 0.0; g_s[i].entryTime = 0; g_s[i].entryBar = 0;
   g_dirty = true;
  }

//+------------------------------------------------------------------+
//| H4 bars as the research builds them (g768.frames): H1 bars grouped |
//| by (time - start hour) // 4 h; a bar's time is its FIRST H1 bar's  |
//| time (a metals bar starting 22:00 opens at 23:00), its open that   |
//| bar's open, its close the last H1 close                            |
//+------------------------------------------------------------------+
long KeyOf(const datetime t) { return ((long)t - (long)InpH4StartHour * 3600) / 14400; }

//--- the newest `want` complete-or-current H4 bars, newest first (index 0 = the bar in progress); returns how many
int BuildBars(const string sym, MqlRates &r[], const int want)
  {
   MqlRates h[];
   ArraySetAsSeries(h, true);
   int got = CopyRates(sym, PERIOD_H1, 0, want * 4 + 12, h);
   if(got <= 0)
      return 0;
   ArrayResize(r, 0, want + 1);
   int n = 0;
   long cur = 0;
   bool full = false;                               // stopped at a newer group's end, so every kept group is complete
   for(int k = 0; k < got; k++)                     // newest H1 bar first
     {
      long key = KeyOf(h[k].time);
      if(n == 0 || key != cur)
        {
         if(n >= want)
           {
            full = true;
            break;
           }
         ArrayResize(r, n + 1, want + 1);
         r[n] = h[k];                                // the newest H1 bar of the group sets the close
         cur = key;
         n++;
        }
      else
        {
         r[n - 1].time = h[k].time;                  // an older H1 bar of the same group: becomes the first bar
         r[n - 1].open = h[k].open;
         r[n - 1].high = MathMax(r[n - 1].high, h[k].high);
         r[n - 1].low = MathMin(r[n - 1].low, h[k].low);
         r[n - 1].tick_volume += h[k].tick_volume;
        }
     }
   if(!full && n > 0)
      n--;                                          // the H1 history ran out: the oldest group may be cut short
   ArrayResize(r, n);
   return n;
  }

//+------------------------------------------------------------------+
//| trading sessions: no order is sent while the symbol's session is |
//| closed (quotes can tick through the metals' daily break)          |
//+------------------------------------------------------------------+
bool HasSessions(const string sym)
  {
   datetime from, to;
   for(int dw = 0; dw < 7; dw++)
      if(SymbolInfoSessionTrade(sym, (ENUM_DAY_OF_WEEK)dw, 0, from, to))
         return true;
   return false;
  }

bool InTradeSession(const string sym, const datetime t)
  {
   MqlDateTime d;
   TimeToStruct(t, d);
   long secs = (long)t % 86400;
   for(int k = 0; k < 16; k++)
     {
      datetime from, to;
      if(!SymbolInfoSessionTrade(sym, (ENUM_DAY_OF_WEEK)d.day_of_week, k, from, to))
         break;
      long f = (long)from % 86400, e = (long)to;   // `to` is seconds from midnight, 86400 for 24:00
      if(e > 86400)
         e %= 86400;
      if(secs >= f && secs < e)
         return true;
     }
   return false;
  }

bool TradeOpen(const int i) { return !g_s[i].sessions || InTradeSession(g_s[i].name, TimeCurrent()); }

datetime BarOf(const string sym, const datetime t)  // time of the H4 bar (its first H1 bar) that contains t
  {
   datetime start = (datetime)(KeyOf(t) * 14400 + (long)InpH4StartHour * 3600);
   MqlRates h[];
   if(CopyRates(sym, PERIOD_H1, start, start + 14399, h) > 0)
      return h[0].time;
   return start;
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
   if(g_s[i].entryBar == 0)
      g_s[i].entryBar = BarOf(g_s[i].name, g_s[i].entryTime);
   g_dirty = true;
  }

//--- money result of all deals of a position, and its closing deal
double g_lastProfit = 0.0, g_lastSwap = 0.0, g_lastComm = 0.0, g_lastFee = 0.0;

bool ExitDetails(const ulong pos, datetime &xt, double &xp, double &money, long &reason)
  {
   xt = 0; xp = 0.0; money = 0.0; reason = -1;
   g_lastProfit = 0.0; g_lastSwap = 0.0; g_lastComm = 0.0; g_lastFee = 0.0;
   if(!HistorySelectByPosition(pos))
      return false;
   for(int k = 0; k < HistoryDealsTotal(); k++)
     {
      ulong d = HistoryDealGetTicket(k);
      g_lastProfit += HistoryDealGetDouble(d, DEAL_PROFIT);
      g_lastSwap   += HistoryDealGetDouble(d, DEAL_SWAP);
      g_lastComm   += HistoryDealGetDouble(d, DEAL_COMMISSION);
      g_lastFee    += HistoryDealGetDouble(d, DEAL_FEE);
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
   x.note = note + "; entered " + T(g_s[i].entryTime) + "; exit bar " + T(g_s[i].lastExitBar) + "; exit " +
            TimeToString(xt, TIME_DATE | TIME_SECONDS) + "; profit " + D(g_lastProfit, 2) + "; swap " + D(g_lastSwap, 2) +
            "; commission " + D(g_lastComm, 2) + "; fee " + D(g_lastFee, 2);
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
   datetime xb = BarOf(sym, xt);
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
      g_s[i].pendingFed = false;
      return;
     }
   string sym = g_s[i].name;
   bool fed = g_s[i].pendingFed;
   bool open = TradeOpen(i);
   bool sent = open && g_trade.PositionClose(t);
   uint rc = open ? g_trade.ResultRetcode() : (uint)TRADE_RETCODE_MARKET_CLOSED;
   if(!sent || (rc != TRADE_RETCODE_DONE && rc != TRADE_RETCODE_DONE_PARTIAL && rc != TRADE_RETCODE_PLACED))
     {
      if(rc == TRADE_RETCODE_MARKET_CLOSED)
        {
         //--- e.g. a Fed rule time on a Friday night: close at the first tick after the reopen, as the research does
         if(g_s[i].waitTick == 0)
            LogSimple("EXIT_WAIT", sym, why + "; market closed - closing at the first tick after it reopens");
         g_s[i].waitTick = (datetime)SymbolInfoInteger(sym, SYMBOL_TIME);
         return;
        }
      LogSimple("EXIT_FAIL", sym, why + "; retcode " + IntegerToString((long)rc) + " " + g_trade.ResultRetcodeDescription());
      return;                      // pendingExit stays set; retried next pass
     }
   datetime xb = BarOf(sym, TimeCurrent());
   if(xb > g_s[i].lastExitBar)
      g_s[i].lastExitBar = xb;
   datetime xt; double xp, money; long reason;
   if(!ExitDetails(t, xt, xp, money, reason))
     {
      xt = TimeCurrent(); xp = g_trade.ResultPrice(); money = 0.0;
     }
   datetime eb = g_s[i].entryBar;
   double stop = g_s[i].stop;
   LogExit(i, fed ? "EXIT_FED" : "EXIT_CHANNEL", xt, xp, money, why);
   ClearTrade(i);
   if(fed)
     {
      //--- the research only shortens this trade: until its own stop or channel exit the market stays taken
      g_s[i].shadow = true; g_s[i].shEntryBar = eb; g_s[i].shStop = stop;
      g_dirty = true;
     }
  }

//--- the Fed rule: an open trade entered before a rule time closes at the first tick of the hour after it
void CheckFedExit(const int i)
  {
   if(!g_fedOn || !g_s[i].fed || g_s[i].pos == 0 || g_s[i].pendingExit)
      return;
   datetime eb = g_s[i].entryBar > 0 ? g_s[i].entryBar : g_s[i].entryTime;
   datetime s = FedFirstAfter(eb);
   if(s == 0 || TimeCurrent() < s + 3600 || !PositionSelectByTicket(g_s[i].pos))
      return;
   g_s[i].pendingExit = true;
   g_s[i].pendingFed = true;
   TryClose(i, "Fed rule time " + T(s) + " (2-year yield rise of 2 SD); closed in the hour after it");
  }

//--- a trade the Fed rule dropped or cut: follow it to its own stop or channel exit, then free the market
void CheckShadow(const int i, const MqlRates &r[], const int unchecked)
  {
   int dg = g_s[i].digits;
   for(int k = unchecked; k >= 1; k--)
     {
      if(r[k].time < g_s[i].shEntryBar)
         continue;
      string why = "";
      datetime xb = 0;
      if(r[k].low <= g_s[i].shStop)
        {
         xb = r[k].time;                          // the stop was hit inside bar k
         why = "stop " + D(g_s[i].shStop, dg) + " hit in bar " + T(r[k].time);
        }
      else
        {
         double lo = LowestLow(r, k + 1, EXIT_BARS);
         if(r[k].close < lo)
           {
            xb = r[k - 1].time;                   // channel exit decided on bar k, taken at the next bar's open
            why = "close " + D(r[k].close, dg) + " < low20 " + D(lo, dg) + " on bar " + T(r[k].time);
           }
        }
      if(xb > 0)
        {
         g_s[i].shadow = false;
         if(xb > g_s[i].lastExitBar)
            g_s[i].lastExitBar = xb;
         LogSimple("SHADOW_END", g_s[i].name, "the research's trade from bar " + T(g_s[i].shEntryBar) + " ends: " + why + "; exit bar " + T(xb));
         g_dirty = true;
         return;
        }
     }
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
   if(g_s[i].shadow)
     {
      x.ev = "SKIP_SHADOW"; x.note = "the research's trade from bar " + T(g_s[i].shEntryBar) + " (dropped or cut by the Fed rule) is still running";
      WriteRow(x);
      return;
     }
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
   if(g_fedOn && g_s[i].fed)
     {
      datetime fb = FedBlock(r[0].time);       // the research's trade time is the entry bar's open
      if(fb > 0)
        {
         x.ev = "SKIP_FED";
         x.note = "Fed rule time " + T(fb) + ": no entry for " + IntegerToString(FED_BLOCK_DAYS) +
                  " days; the research's trade is followed as a shadow until its own exit";
         WriteRow(x);
         g_s[i].shadow = true; g_s[i].shEntryBar = r[0].time; g_s[i].shStop = r[0].open - STOP_ATR * atr;
         g_dirty = true;
         return;
        }
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
   if(InpBrake)
      EvaluateBrake();
   double mult = (InpBrake && g_brake) ? BRAKE_MULT : 1.0;
   double bal = AccountInfoDouble(ACCOUNT_BALANCE);
   double riskMoney = bal * InpRiskPct / 100.0 * mult;
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
   bool open = TradeOpen(i);
   bool sent = open && g_trade.Buy(lots, sym, 0.0, stop, 0.0, SETUP_NAME);
   uint rc = open ? g_trade.ResultRetcode() : (uint)TRADE_RETCODE_MARKET_CLOSED;
   if(!sent || (rc != TRADE_RETCODE_DONE && rc != TRADE_RETCODE_DONE_PARTIAL && rc != TRADE_RETCODE_PLACED))
     {
      if(rc == TRADE_RETCODE_MARKET_CLOSED)
        {
         //--- the bar has opened but the market has not (metals' daily break): the research enters at its next price, so retry
         //--- once the session opens, while the entry is still within InpMaxEntryDelayMin; ProcessSymbol keeps the bar open for it
         if(g_s[i].waitBar != r[0].time)
           {
            x.ev = "ENTRY_WAIT"; x.note = "market closed - entering when it opens if within " + IntegerToString(InpMaxEntryDelayMin) + " min of the bar's first tick";
            WriteRow(x);
            g_s[i].waitBar = r[0].time;
           }
         g_s[i].entryWait = true;
         g_s[i].waitTick = (datetime)SymbolInfoInteger(sym, SYMBOL_TIME);
         return;
        }
      x.ev = "ENTRY_FAIL"; x.note = "retcode " + IntegerToString((long)rc) + " " + g_trade.ResultRetcodeDescription();
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
   g_s[i].entryTime = TimeCurrent(); g_s[i].entryBar = r[0].time;
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
   if(g_s[i].pendingExit && (g_s[i].waitTick == 0 || (TradeOpen(i) && (datetime)SymbolInfoInteger(sym, SYMBOL_TIME) > g_s[i].waitTick)))
      TryClose(i, "retry");
   CheckFedExit(i);
   datetime h0 = iTime(sym, PERIOD_H1, 0);
   if(g_s[i].entryWait)
     {
      if(g_s[i].pos != 0 || (TradeOpen(i) && (datetime)SymbolInfoInteger(sym, SYMBOL_TIME) > g_s[i].waitTick))
         g_s[i].entryWait = false;  // a new tick: run the bar again (the entry is retried or skipped as late)
      else
         return;                   // the market is still closed
     }
   else
      if(h0 == 0 || (g_s[i].lastBar > 0 && KeyOf(h0) <= KeyOf(g_s[i].lastBar)))
         return;                   // still the same H4 bar
   MqlRates r[];
   int got = BuildBars(sym, r, COPY_BARS);
   if(got < EXIT_BARS + 3 || KeyOf(r[0].time) != KeyOf(h0))
      return;                      // history not ready; retried next pass
   datetime t0 = r[0].time;
   //--- completed bars not checked yet: normally 1, more if the EA was offline
   int unchecked = 1;
   if(g_s[i].lastBar > 0)
      while(unchecked + 1 < got - EXIT_BARS - 1 && r[unchecked + 1].time >= g_s[i].lastBar)
         unchecked++;
   if(g_s[i].pos != 0)
      CheckChannelExit(i, r, unchecked);
   else
     {
      if(g_s[i].shadow)
         CheckShadow(i, r, unchecked);
      CheckEntry(i, r, unchecked);
      if(g_s[i].entryWait)
         return;                   // keep this bar open for the retry
     }
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
      g_s[k].lastBar = 0; g_s[k].lastExitBar = 0; g_s[k].pos = 0; g_s[k].pendingExit = false; g_s[k].pendingFed = false; g_s[k].waitTick = 0;
      g_s[k].entryWait = false; g_s[k].waitBar = 0; g_s[k].sessions = HasSessions(sym);
      g_s[k].entry = 0.0; g_s[k].stop = 0.0; g_s[k].atr = 0.0; g_s[k].lots = 0.0; g_s[k].risk = 0.0; g_s[k].entryTime = 0;
      g_s[k].entryBar = 0; g_s[k].fed = FedCovers(sym); g_s[k].shadow = false; g_s[k].shEntryBar = 0; g_s[k].shStop = 0.0;
     }
   if(InpRiskPct <= 0.0 || InpRiskPct > 5.0)
     {
      Print("G27K: InpRiskPct out of range");
      return INIT_PARAMETERS_INCORRECT;
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
   g_fedOn   = InpFedSource != FED_OFF;
   g_fedWeb  = InpFedSource == FED_WEB  || (InpFedSource == FED_AUTO && !g_tester);
   g_fedFile = InpFedSource == FED_FILE || (InpFedSource == FED_AUTO && g_tester);
   if(g_fedOn)
     {
      string why = "", why2 = "";
      bool ok = false;
      if(g_fedWeb && !g_tester)
        {
         ok = FedFetchWeb(why);
         if(!ok && FedLoadFile(why2))
           {
            ok = true;
            PrintFormat("G27K: Fed data download failed (%s); using the saved copy %s", why, InpFedFile);
           }
         g_fedNextFetch = TimeGMT() + (ok ? 1800 : 600);
        }
      else
         ok = FedLoadFile(why);
      if(!ok)
        {
         Alert("G27K: no data for the Fed rule (" + why + ") - G27K-F cannot run. Allow https://fred.stlouisfed.org in "
               "Tools > Options > Expert Advisors, or put the FRED DGS2 csv in Common\\Files\\" + InpFedFile);
         return INIT_FAILED;
        }
      if(g_tester)
        {
         int h = FileOpen("tester_g27k_fed_times.txt", FILE_WRITE | FILE_TXT | FILE_ANSI | FILE_COMMON);
         if(h != INVALID_HANDLE)
           {
            for(int k = 0; k < ArraySize(g_fedPub); k++)
               FileWriteString(h, TimeToString(g_fedPub[k], TIME_DATE | TIME_MINUTES) + "\r\n");
            FileClose(h);
           }
        }
     }
   else
      Print("G27K: Fed rule OFF - this is G27K #1, not G27K-F");
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
             "; risk " + D(InpRiskPct, 2) + "%; brake " + (InpBrake ? "on" : "off") +
             "; news " + (g_useApi ? "calendar" : (g_useFile ? "file" : "off")) +
             "; Fed rule " + (g_fedOn ? (g_fedWeb ? "download: " : "file: ") + FedSummary() : "OFF") +
             "; H4 bars from " + IntegerToString(InpH4StartHour) + ":00 UTC; algo trading: terminal " +
             (TerminalInfoInteger(TERMINAL_TRADE_ALLOWED) ? "on" : "OFF") + ", this EA " + (MQLInfoInteger(MQL_TRADE_ALLOWED) ? "on" : "OFF"));
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
   FedMaintain();
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
