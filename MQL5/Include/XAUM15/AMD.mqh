//+------------------------------------------------------------------+
//| AMD.mqh - MODULE 5 (Power of Three)                               |
//| Answers CONTEXT. Never an entry signal on its own (spec 7).       |
//+------------------------------------------------------------------+
#ifndef XAUM15_AMD_MQH
#define XAUM15_AMD_MQH
#include "Config.mqh"
#include "Regime.mqh"
#include "Liquidity.mqh"
#include "SessionFilter.mqh"

class CAMD
  {
public:
   ENUM_AMD_PHASE phase;
   bool           sweptAsianHigh, sweptAsianLow;
   bool           rangeExpanded;
   int            postSweepDirection;   // +1 up, -1 down, 0 none

   CAMD(void): phase(AMD_NONE), sweptAsianHigh(false), sweptAsianLow(false),
               rangeExpanded(false), postSweepDirection(0) {}

   void Evaluate(CMarketContext &ctx,CLiquidityMap &liq,CSessionFilter &sess,
                 const datetime now)
     {
      phase=AMD_NONE;
      sweptAsianHigh=false; sweptAsianLow=false;
      rangeExpanded=false;  postSweepDirection=0;

      if(!InpUseAMD || !InpAblAMD) return;
      if(!liq.asianValid) return;

      // Accumulation while price is still inside the Asian range.
      double px=ctx.rates[1].close;
      if(px<=liq.asianHigh && px>=liq.asianLow)
         phase=AMD_ACCUMULATION;

      // Manipulation: session takes one side of the Asian range.
      datetime aE=sess.AsianEnd(now);
      for(int i=1;i<ctx.bars;i++)
        {
         if(ctx.rates[i].time < aE) break;
         if(ctx.rates[i].high > liq.asianHigh) sweptAsianHigh=true;
         if(ctx.rates[i].low  < liq.asianLow ) sweptAsianLow =true;
        }
      if(sweptAsianHigh || sweptAsianLow)
         phase=AMD_MANIPULATION;

      // Expansion beyond the range by a meaningful multiple of it.
      double a=ctx.ATR(1);
      if(a>0.0 && liq.asianRange>0.0)
        {
         if(px > liq.asianHigh + 0.5*liq.asianRange) { rangeExpanded=true; postSweepDirection=+1; }
         if(px < liq.asianLow  - 0.5*liq.asianRange) { rangeExpanded=true; postSweepDirection=-1; }
        }

      // Distribution: swept one side and now travelling the other way.
      if(sweptAsianLow  && px>liq.asianLow  && postSweepDirection>=0) { phase=AMD_DISTRIBUTION; postSweepDirection=+1; }
      if(sweptAsianHigh && px<liq.asianHigh && postSweepDirection<=0) { phase=AMD_DISTRIBUTION; postSweepDirection=-1; }
     }

   //--- soft context agreement, used by the quality grader ------------
   bool Supports(const bool isLong) const
     {
      if(!InpUseAMD || !InpAblAMD) return true;
      if(phase==AMD_NONE) return true;
      if(isLong)  return (sweptAsianLow  || postSweepDirection>0);
      return             (sweptAsianHigh || postSweepDirection<0);
     }

   string PhaseName(void) const
     {
      switch(phase)
        {
         case AMD_ACCUMULATION: return "ACCUM";
         case AMD_MANIPULATION: return "MANIP";
         case AMD_DISTRIBUTION: return "DISTR";
        }
      return "-";
     }
  };
#endif
