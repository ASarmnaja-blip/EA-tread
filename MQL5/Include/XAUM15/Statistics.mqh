//+------------------------------------------------------------------+
//| Statistics.mqh - MODULE 17 + MODULE 31                            |
//| Spec 30: split by direction, by setup and by session.             |
//| Spec 31: hour-of-day table for XAU/USD M15 timing research.       |
//+------------------------------------------------------------------+
#ifndef XAUM15_STATS_MQH
#define XAUM15_STATS_MQH
#include "Config.mqh"

struct StatBucket
  {
   int    trades, wins, losses;
   double grossProfit, grossLoss;
   double sumR, sumRSq;
   double maxWin, maxLoss;
   int    consecWins, consecLosses, maxConsecWins, maxConsecLosses;
   double durationSum;

   void Reset(void)
     {
      trades=0; wins=0; losses=0; grossProfit=0; grossLoss=0;
      sumR=0; sumRSq=0; maxWin=0; maxLoss=0;
      consecWins=0; consecLosses=0; maxConsecWins=0; maxConsecLosses=0;
      durationSum=0;
     }

   void Add(const double profit,const double r,const double durationMin)
     {
      trades++;
      sumR+=r; sumRSq+=r*r;
      durationSum+=durationMin;
      if(profit>=0.0)
        {
         wins++; grossProfit+=profit;
         if(profit>maxWin) maxWin=profit;
         consecWins++; consecLosses=0;
         if(consecWins>maxConsecWins) maxConsecWins=consecWins;
        }
      else
        {
         losses++; grossLoss+=MathAbs(profit);
         if(profit<maxLoss) maxLoss=profit;
         consecLosses++; consecWins=0;
         if(consecLosses>maxConsecLosses) maxConsecLosses=consecLosses;
        }
     }

   double NetProfit(void)     const { return grossProfit-grossLoss; }
   double WinRate(void)       const { return trades>0 ? 100.0*wins/trades : 0.0; }
   double ProfitFactor(void)  const { return grossLoss>0.0 ? grossProfit/grossLoss
                                            : (grossProfit>0.0?999.0:0.0); }
   double AvgWin(void)        const { return wins>0   ? grossProfit/wins   : 0.0; }
   double AvgLoss(void)       const { return losses>0 ? grossLoss/losses   : 0.0; }
   double AvgR(void)          const { return trades>0 ? sumR/trades        : 0.0; }
   double Expectancy(void)    const { return AvgR(); }
   double AvgDuration(void)   const { return trades>0 ? durationSum/trades : 0.0; }
   // Sharpe of the per-trade R series (not annualised - see docs).
   double SharpeR(void) const
     {
      if(trades<2) return 0.0;
      double m=AvgR();
      double var=sumRSq/trades - m*m;
      if(var<=0.0) return 0.0;
      return m/MathSqrt(var);
     }
  };

class CStatistics
  {
public:
   StatBucket all, longs, shorts;
   StatBucket bySetup[5];      // index by ENUM_SETUP_ID (A=1..D=4)
   StatBucket bySession[4];    // 0 asian 1 london 2 ny 3 overlap
   StatBucket byHour[24];

   double     peakEquity, maxDrawdown, maxDDPercent;
   double     startEquity;

   CStatistics(void): peakEquity(0), maxDrawdown(0), maxDDPercent(0), startEquity(0) { ResetAll(); }

   void ResetAll(void)
     {
      all.Reset(); longs.Reset(); shorts.Reset();
      for(int i=0;i<5;i++) bySetup[i].Reset();
      for(int i=0;i<4;i++) bySession[i].Reset();
      for(int i=0;i<24;i++) byHour[i].Reset();
     }

   void Init(const double equity) { startEquity=equity; peakEquity=equity; }

   void UpdateEquity(const double equity)
     {
      if(equity>peakEquity) peakEquity=equity;
      double dd=peakEquity-equity;
      if(dd>maxDrawdown)
        {
         maxDrawdown=dd;
         maxDDPercent = peakEquity>0.0 ? 100.0*dd/peakEquity : 0.0;
        }
     }

   void Record(const ENUM_SETUP_ID setup,const bool isLong,const int sessionIdx,
               const int hour,const double profit,const double r,const double durationMin)
     {
      all.Add(profit,r,durationMin);
      if(isLong) longs.Add(profit,r,durationMin); else shorts.Add(profit,r,durationMin);
      if(setup>=0 && setup<5)        bySetup[setup].Add(profit,r,durationMin);
      if(sessionIdx>=0&&sessionIdx<4)bySession[sessionIdx].Add(profit,r,durationMin);
      if(hour>=0 && hour<24)         byHour[hour].Add(profit,r,durationMin);
     }

   double RecoveryFactor(void) const
     { return maxDrawdown>0.0 ? all.NetProfit()/maxDrawdown : 0.0; }

   void PrintBucket(const string name,StatBucket &b)
     {
      if(b.trades==0) { PrintFormat("%-12s | no trades",name); return; }
      PrintFormat("%-12s | n=%-4d win%%=%-6.2f PF=%-6.2f net=%-10.2f expR=%-7.3f avgW=%-8.2f avgL=%-8.2f maxCL=%-3d dur=%.0fm",
                  name,b.trades,b.WinRate(),b.ProfitFactor(),b.NetProfit(),
                  b.Expectancy(),b.AvgWin(),b.AvgLoss(),b.maxConsecLosses,b.AvgDuration());
     }

   void PrintReport(void)
     {
      Print("==================== BACKTEST STATISTICS (spec 30) ====================");
      PrintFormat("Start equity %.2f  Net %.2f  Gross+ %.2f  Gross- %.2f",
                  startEquity,all.NetProfit(),all.grossProfit,all.grossLoss);
      PrintFormat("Profit Factor %.3f | Win rate %.2f%% | Expectancy %.4fR | Sharpe(R) %.3f",
                  all.ProfitFactor(),all.WinRate(),all.Expectancy(),all.SharpeR());
      PrintFormat("Max DD %.2f (%.2f%%) | Recovery factor %.3f | Trades %d",
                  maxDrawdown,maxDDPercent,RecoveryFactor(),all.trades);
      PrintFormat("Max consecutive wins %d | losses %d",
                  all.maxConsecWins,all.maxConsecLosses);

      Print("--- by direction ---");
      PrintBucket("LONG",longs); PrintBucket("SHORT",shorts);

      Print("--- by setup (spec 16: reported separately) ---");
      PrintBucket("SETUP A",bySetup[SETUP_A]);
      PrintBucket("SETUP B",bySetup[SETUP_B]);
      PrintBucket("SETUP C",bySetup[SETUP_C]);
      PrintBucket("SETUP D",bySetup[SETUP_D]);

      Print("--- by session ---");
      PrintBucket("ASIAN",bySession[0]);  PrintBucket("LONDON",bySession[1]);
      PrintBucket("NEWYORK",bySession[2]);PrintBucket("LDN+NY",bySession[3]);

      Print("--- hour of day (spec 31) ---");
      Print("hour |  n | win%  |  PF   |  avgR  |  net");
      for(int h=0;h<24;h++)
        {
         if(byHour[h].trades==0) continue;
         PrintFormat("%02d:00| %2d | %5.1f | %5.2f | %6.3f | %8.2f",
                     h,byHour[h].trades,byHour[h].WinRate(),
                     byHour[h].ProfitFactor(),byHour[h].AvgR(),byHour[h].NetProfit());
        }
      Print("=======================================================================");
      Print("NOTE: these are BACKTEST figures from one broker's history. They are");
      Print("not forward-test results and not expected live performance.");
     }
  };
#endif
