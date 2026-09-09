//+------------------------------------------------------------------+
//| Sweep.mqh - MODULE 9                                              |
//| Answers LIQUIDITY EVENT: wick takes a level, body closes back.    |
//+------------------------------------------------------------------+
#ifndef XAUM15_SWEEP_MQH
#define XAUM15_SWEEP_MQH
#include "Config.mqh"
#include "Regime.mqh"
#include "Liquidity.mqh"

class CSweepDetector
  {
public:
   SweepEvent last;

   CSweepDetector(void) { last.valid=false; }

   //--- Did bar `i` sweep `level` and reclaim within N bars? ----------
   bool CheckLevel(CMarketContext &ctx,const int i,const double level,
                   const bool sweepHigh,const ENUM_LIQ_TYPE t,SweepEvent &ev)
     {
      ev.valid=false;
      if(i<1 || i>=ctx.bars || level<=0.0) return false;
      double a=ctx.ATR(i);
      if(a<=0.0) return false;

      double minPen=InpSweepMinPenATR*a;
      double maxPen=InpSweepMaxPenATR*a;

      if(sweepHigh)
        {
         double pen=ctx.rates[i].high-level;
         if(pen<minPen || pen>maxPen) return false;
         // must close back BELOW the level within the reclaim window
         bool reclaimed=false;
         for(int k=i;k>=MathMax(1,i-InpSweepReclaimBars);k--)
            if(ctx.rates[k].close < level) { reclaimed=true; break; }
         if(!reclaimed) return false;

         ev.valid=true; ev.side=SWEEP_HIGH; ev.level=level;
         ev.extreme=ctx.rates[i].high; ev.time=ctx.rates[i].time;
         ev.barIndex=i; ev.liqType=t;
         return true;
        }
      else
        {
         double pen=level-ctx.rates[i].low;
         if(pen<minPen || pen>maxPen) return false;
         bool reclaimed=false;
         for(int k=i;k>=MathMax(1,i-InpSweepReclaimBars);k--)
            if(ctx.rates[k].close > level) { reclaimed=true; break; }
         if(!reclaimed) return false;

         ev.valid=true; ev.side=SWEEP_LOW; ev.level=level;
         ev.extreme=ctx.rates[i].low; ev.time=ctx.rates[i].time;
         ev.barIndex=i; ev.liqType=t;
         return true;
        }
     }

   //--- scan the liquidity map for the freshest actionable sweep ------
   bool FindRecent(CMarketContext &ctx,CLiquidityMap &liq,const bool wantHigh,
                   SweepEvent &ev)
     {
      ev.valid=false;
      int scan=MathMin(InpSweepValidBars,ctx.bars-1);
      int bestBar=INT_MAX;
      SweepEvent best; best.valid=false;

      for(int i=1;i<=scan;i++)
        {
         for(int L=0;L<ArraySize(liq.levels);L++)
           {
            if(liq.levels[L].swept) continue;
            bool isHighSide = (liq.levels[L].type==LQ_PDH || liq.levels[L].type==LQ_ASIA_H ||
                               liq.levels[L].type==LQ_LDN_H|| liq.levels[L].type==LQ_PWH  ||
                               liq.levels[L].type==LQ_SWING_H||liq.levels[L].type==LQ_EQH);
            if(isHighSide!=wantHigh) continue;

            SweepEvent tmp;
            if(CheckLevel(ctx,i,liq.levels[L].price,wantHigh,liq.levels[L].type,tmp))
               if(tmp.barIndex<bestBar)
                 { bestBar=tmp.barIndex; best=tmp; }
           }
        }
      if(!best.valid) return false;
      ev=best; last=best;
      return true;
     }

   //--- sweep of a specific price (used by Setup A for Asian H/L) -----
   bool FindOnLevel(CMarketContext &ctx,const double level,const bool wantHigh,
                    const ENUM_LIQ_TYPE t,SweepEvent &ev)
     {
      ev.valid=false;
      int scan=MathMin(InpSweepValidBars,ctx.bars-1);
      for(int i=1;i<=scan;i++)
         if(CheckLevel(ctx,i,level,wantHigh,t,ev)) { last=ev; return true; }
      return false;
     }
  };
#endif
