//+------------------------------------------------------------------+
//| CalendarDump.mq5                                                  |
//|                                                                   |
//| Dumps the terminal's own economic calendar to CSV so the Python   |
//| side can read it. The MetaTrader5 Python package exposes no       |
//| calendar at all - 269 public names, none of them calendar, news   |
//| or event - so MQL5 is the only route to the fields CLAUDE.md      |
//| section 2 requires: actual against consensus and previous, plus   |
//| the revision.                                                     |
//|                                                                   |
//| Reads only. No trade function is called or imported.              |
//+------------------------------------------------------------------+
#property copyright "EA-tread"
#property version   "1.00"
#property script_show_inputs
#property strict

input datetime InpFrom       = D'2025.04.01 00:00'; // from (covers the M5 export)
input datetime InpTo         = 0;                   // to (0 = now + 14 days)
input string   InpCurrencies = "USD,XAU,EUR";       // comma separated, empty = every currency
input string   InpFile       = "calendar_dump.csv"; // written to MQL5/Files/

//+------------------------------------------------------------------+
//| RFC 4180 escaping.                                                |
//|                                                                   |
//| MQL5's FileWrite does not escape anything, and event names carry  |
//| commas ("Core PCE Price Index m/m, n.s.a.") and the occasional    |
//| quote. Without this one logical row is torn into two lines, which |
//| is the exact bug the research log records against Setups.mqh.     |
//+------------------------------------------------------------------+
string CsvEscape(const string s)
{
   bool needs = (StringFind(s, ",") >= 0 || StringFind(s, "\"") >= 0 ||
                 StringFind(s, "\n") >= 0 || StringFind(s, "\r") >= 0);
   if(!needs)
      return s;
   string out = s;
   StringReplace(out, "\"", "\"\"");
   return "\"" + out + "\"";
}

//+------------------------------------------------------------------+
//| Calendar values are int64 scaled by 1e6; LONG_MIN means absent.   |
//| An absent value must stay empty rather than become 0, or a        |
//| missing consensus silently reads as a forecast of zero.           |
//+------------------------------------------------------------------+
string Num(const long v, const int digits)
{
   if(v == LONG_MIN)
      return "";
   return DoubleToString(v / 1000000.0, digits);
}

string ImportanceName(const ENUM_CALENDAR_EVENT_IMPORTANCE imp)
{
   switch(imp)
   {
      case CALENDAR_IMPORTANCE_LOW:      return "LOW";
      case CALENDAR_IMPORTANCE_MODERATE: return "MODERATE";
      case CALENDAR_IMPORTANCE_HIGH:     return "HIGH";
      default:                           return "NONE";
   }
}

string SectorName(const ENUM_CALENDAR_EVENT_SECTOR s)
{
   switch(s)
   {
      case CALENDAR_SECTOR_MARKET:       return "MARKET";
      case CALENDAR_SECTOR_GDP:          return "GDP";
      case CALENDAR_SECTOR_JOBS:         return "JOBS";
      case CALENDAR_SECTOR_PRICES:       return "PRICES";
      case CALENDAR_SECTOR_MONEY:        return "MONEY";
      case CALENDAR_SECTOR_TRADE:        return "TRADE";
      case CALENDAR_SECTOR_GOVERNMENT:   return "GOVERNMENT";
      case CALENDAR_SECTOR_BUSINESS:     return "BUSINESS";
      case CALENDAR_SECTOR_CONSUMER:     return "CONSUMER";
      case CALENDAR_SECTOR_HOUSING:      return "HOUSING";
      case CALENDAR_SECTOR_TAXES:        return "TAXES";
      case CALENDAR_SECTOR_HOLIDAYS:     return "HOLIDAYS";
      default:                           return "NONE";
   }
}

//+------------------------------------------------------------------+
int DumpCurrency(const int handle, const string currency,
                 const datetime from, const datetime to)
{
   MqlCalendarValue values[];
   int n = CalendarValueHistory(values, from, to, NULL,
                                currency == "" ? NULL : currency);
   if(n <= 0)
   {
      PrintFormat("  %-4s : 0 values (last_error=%d)",
                  currency == "" ? "ALL" : currency, GetLastError());
      return 0;
   }

   int written = 0;
   for(int i = 0; i < n; i++)
   {
      MqlCalendarEvent event;
      if(!CalendarEventById(values[i].event_id, event))
         continue;

      // the currency lives on the country, not on the event
      MqlCalendarCountry country;
      string country_name = "";
      string country_code = "";
      string country_ccy  = "";
      if(CalendarCountryById(event.country_id, country))
      {
         country_name = country.name;
         country_code = country.code;
         country_ccy  = country.currency;
      }

      // times are terminal/server time; the exporter writes the server
      // offset into every meta.json so the Python side can align them
      FileWrite(handle,
                TimeToString(values[i].time, TIME_DATE | TIME_MINUTES),
                (string)values[i].id,
                (string)values[i].event_id,
                CsvEscape(country_code),
                CsvEscape(country_ccy),
                CsvEscape(event.name),
                ImportanceName(event.importance),
                SectorName(event.sector),
                (string)values[i].period,
                (string)values[i].revision,
                Num(values[i].actual_value,       event.digits),
                Num(values[i].forecast_value,     event.digits),
                Num(values[i].prev_value,         event.digits),
                Num(values[i].revised_prev_value, event.digits),
                (string)event.unit,
                (string)event.multiplier,
                CsvEscape(country_name));
      written++;
   }
   PrintFormat("  %-4s : %d values, %d written",
               currency == "" ? "ALL" : currency, n, written);
   return written;
}

//+------------------------------------------------------------------+
void OnStart()
{
   datetime from = InpFrom;
   datetime to   = (InpTo == 0) ? (TimeCurrent() + 14 * 86400) : InpTo;

   PrintFormat("CalendarDump: %s .. %s  ->  MQL5/Files/%s",
               TimeToString(from, TIME_DATE), TimeToString(to, TIME_DATE),
               InpFile);

   int handle = FileOpen(InpFile, FILE_WRITE | FILE_CSV | FILE_ANSI, ',');
   if(handle == INVALID_HANDLE)
   {
      PrintFormat("CalendarDump: cannot open %s, error %d", InpFile, GetLastError());
      return;
   }

   FileWrite(handle, "time", "value_id", "event_id", "country_code", "currency",
             "event", "importance", "sector", "period", "revision",
             "actual", "forecast", "previous", "revised_previous",
             "unit", "multiplier", "country");

   int total = 0;
   if(StringLen(InpCurrencies) == 0)
   {
      total += DumpCurrency(handle, "", from, to);
   }
   else
   {
      string parts[];
      int k = StringSplit(InpCurrencies, ',', parts);
      for(int i = 0; i < k; i++)
      {
         string cur = parts[i];
         StringTrimLeft(cur);
         StringTrimRight(cur);
         if(StringLen(cur) > 0)
            total += DumpCurrency(handle, cur, from, to);
      }
   }

   FileClose(handle);
   PrintFormat("CalendarDump: %d rows written to MQL5/Files/%s", total, InpFile);
   PrintFormat("CalendarDump: no trade function is called anywhere in this script");
}
//+------------------------------------------------------------------+
