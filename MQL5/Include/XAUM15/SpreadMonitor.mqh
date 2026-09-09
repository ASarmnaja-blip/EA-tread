//+------------------------------------------------------------------+
//| SpreadMonitor.mqh                                                 |
//|                                                                   |
//| Settles an open question rather than assuming an answer.          |
//|                                                                   |
//| The research log carries a three-fold conflict in the single most  |
//| important cost input: $0.26 reported from the terminal, $0.4824    |
//| average measured on OANDA data, $0.7525 during the Asian hours.    |
//| At a 1.8xATR stop that is the difference between 0.013R and 0.037R |
//| per trade - roughly 17% of expectancy.                             |
//|                                                                   |
//| This module measures what YOUR broker actually charges, hour by    |
//| hour, and writes it out. No backtest can supply this number.       |
//+------------------------------------------------------------------+
#ifndef XAUM15_SPREADMON_MQH
#define XAUM15_SPREADMON_MQH
#include "Config.mqh"

class CSpreadMonitor
  {
private:
   double   m_sum[24];
   double   m_max[24];
   double   m_min[24];
   long     m_n[24];
   datetime m_lastSample;

public:
   CSpreadMonitor(void): m_lastSample(0) { Reset(); }

   void Reset(void)
     {
      for(int h=0;h<24;h++)
        { m_sum[h]=0.0; m_max[h]=0.0; m_min[h]=DBL_MAX; m_n[h]=0; }
     }

   //--- one sample per second is plenty and keeps the tester fast -----
   void Sample(const datetime now,const double spread)
     {
      if(spread<=0.0) return;
      if(now==m_lastSample) return;
      m_lastSample=now;

      MqlDateTime dt; TimeToStruct(now,dt);
      int h=dt.hour;
      if(h<0||h>23) return;
      m_sum[h]+=spread;
      m_n[h]++;
      if(spread>m_max[h]) m_max[h]=spread;
      if(spread<m_min[h]) m_min[h]=spread;
     }

   double AvgAt(const int h) const
     { return (h>=0&&h<24&&m_n[h]>0) ? m_sum[h]/m_n[h] : 0.0; }

   double OverallAvg(void) const
     {
      double s=0.0; long n=0;
      for(int h=0;h<24;h++) { s+=m_sum[h]; n+=m_n[h]; }
      return (n>0)?s/n:0.0;
     }

   //--- cost of one round turn as a fraction of R --------------------
   double CostInR(const double slDistance) const
     {
      if(slDistance<=0.0) return 0.0;
      return OverallAvg()/slDistance;
     }

   void PrintReport(const double typicalSL)
     {
      Print("================= MEASURED SPREAD (broker server hours) =================");
      PrintFormat("overall average: %.4f   samples: %s",OverallAvg(),
                  IntegerToString(TotalSamples()));
      Print("hour |    avg |    min |    max |   samples");
      for(int h=0;h<24;h++)
        {
         if(m_n[h]==0) continue;
         PrintFormat("%02d:00| %6.4f | %6.4f | %6.4f | %s",
                     h,AvgAt(h),(m_min[h]==DBL_MAX?0.0:m_min[h]),m_max[h],
                     IntegerToString(m_n[h]));
        }
      if(typicalSL>0.0)
         PrintFormat("cost per trade at a %.2f stop: %.4f R",typicalSL,CostInR(typicalSL));
      Print("Compare this against the figure assumed in any backtest. If the");
      Print("measured value is materially higher, the backtest overstates results.");
      Print("========================================================================");
     }

   long TotalSamples(void) const
     {
      long n=0;
      for(int h=0;h<24;h++) n+=m_n[h];
      return n;
     }

   void WriteCsv(const string fname)
     {
      int f=FileOpen(fname,FILE_WRITE|FILE_CSV|FILE_ANSI,',');
      if(f==INVALID_HANDLE) return;
      FileWrite(f,"hour","avg_spread","min_spread","max_spread","samples");
      for(int h=0;h<24;h++)
        {
         if(m_n[h]==0) continue;
         FileWrite(f,IntegerToString(h),
                   DoubleToString(AvgAt(h),4),
                   DoubleToString(m_min[h]==DBL_MAX?0.0:m_min[h],4),
                   DoubleToString(m_max[h],4),
                   IntegerToString(m_n[h]));
        }
      FileClose(f);
     }
  };
#endif
