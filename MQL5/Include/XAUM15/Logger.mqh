//+------------------------------------------------------------------+
//| Logger.mqh - MODULE 36                                            |
//| One CSV row per closed setup with the full context snapshot.      |
//+------------------------------------------------------------------+
#ifndef XAUM15_LOGGER_MQH
#define XAUM15_LOGGER_MQH
#include "Config.mqh"

class CTradeLogger
  {
private:
   int    m_h;
   string m_file;

public:
   CTradeLogger(void): m_h(INVALID_HANDLE) {}

   bool Init(const string fname)
     {
      if(!InpWriteTradeLog) return true;
      m_file=fname;
      m_h=FileOpen(m_file,FILE_WRITE|FILE_READ|FILE_CSV|FILE_ANSI,',');
      if(m_h==INVALID_HANDLE)
        { PrintFormat("[LOG] cannot open %s err=%d",m_file,GetLastError()); return false; }
      FileSeek(m_h,0,SEEK_END);
      if(FileTell(m_h)==0)
         FileWrite(m_h,"date","time","session","setup","direction","entry","sl",
                   "tp1","tp2","tp3","risk_pct","lot","legs","spread","atr","vwap",
                   "poc","vah","val","liq_level","sweep_type","mss","displacement",
                   "quality","result","r_multiple","mae","mfe","duration_min");
      return true;
     }

   void Close(void)
     { if(m_h!=INVALID_HANDLE) { FileClose(m_h); m_h=INVALID_HANDLE; } }

   void Write(const datetime when,const string session,const string setup,
              const string dir,const double entry,const double sl,
              const double tp1,const double tp2,const double tp3,
              const double riskPct,const double lot,const int legs,
              const double spread,const double atr,const double vwap,
              const double poc,const double vah,const double val,
              const double liq,const string sweep,const bool mss,
              const bool disp,const string quality,const double result,
              const double rMultiple,const double mae,const double mfe,
              const double durationMin)
     {
      if(m_h==INVALID_HANDLE) return;
      FileWrite(m_h,
                TimeToString(when,TIME_DATE),
                TimeToString(when,TIME_MINUTES),
                session,setup,dir,
                DoubleToString(entry,2),DoubleToString(sl,2),
                DoubleToString(tp1,2),DoubleToString(tp2,2),DoubleToString(tp3,2),
                DoubleToString(riskPct,3),DoubleToString(lot,2),IntegerToString(legs),
                DoubleToString(spread,3),DoubleToString(atr,3),DoubleToString(vwap,2),
                DoubleToString(poc,2),DoubleToString(vah,2),DoubleToString(val,2),
                DoubleToString(liq,2),sweep,(mss?"1":"0"),(disp?"1":"0"),quality,
                DoubleToString(result,2),DoubleToString(rMultiple,3),
                DoubleToString(mae,2),DoubleToString(mfe,2),
                DoubleToString(durationMin,1));
      FileFlush(m_h);
     }
  };
#endif
