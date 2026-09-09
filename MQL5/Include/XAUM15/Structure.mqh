//+------------------------------------------------------------------+
//| Structure.mqh - MODULE 8                                          |
//| Answers STRUCTURE CONFIRMATION: swings, BOS, MSS, CHOCH.          |
//+------------------------------------------------------------------+
#ifndef XAUM15_STRUCTURE_MQH
#define XAUM15_STRUCTURE_MQH
#include "Config.mqh"
#include "Regime.mqh"

class CStructure
  {
public:
   double   swingHigh[], swingLow[];
   datetime swingHighTime[], swingLowTime[];
   int      swingHighBar[], swingLowBar[];

   //--- fractal swing detection over the structure lookback -----------
   void Detect(CMarketContext &ctx)
     {
      ArrayResize(swingHigh,0);      ArrayResize(swingLow,0);
      ArrayResize(swingHighTime,0);  ArrayResize(swingLowTime,0);
      ArrayResize(swingHighBar,0);   ArrayResize(swingLowBar,0);

      int w=MathMax(1,InpSwingLookback);
      int last=MathMin(InpStructureLookback+w, ctx.bars-w-1);

      for(int i=w+1;i<=last;i++)
        {
         bool isHigh=true, isLow=true;
         for(int k=1;k<=w;k++)
           {
            if(ctx.rates[i].high <= ctx.rates[i-k].high || ctx.rates[i].high <= ctx.rates[i+k].high) isHigh=false;
            if(ctx.rates[i].low  >= ctx.rates[i-k].low  || ctx.rates[i].low  >= ctx.rates[i+k].low ) isLow =false;
            if(!isHigh && !isLow) break;
           }
         if(isHigh)
           {
            int n=ArraySize(swingHigh);
            ArrayResize(swingHigh,n+1); ArrayResize(swingHighTime,n+1); ArrayResize(swingHighBar,n+1);
            swingHigh[n]=ctx.rates[i].high; swingHighTime[n]=ctx.rates[i].time; swingHighBar[n]=i;
           }
         if(isLow)
           {
            int n=ArraySize(swingLow);
            ArrayResize(swingLow,n+1); ArrayResize(swingLowTime,n+1); ArrayResize(swingLowBar,n+1);
            swingLow[n]=ctx.rates[i].low; swingLowTime[n]=ctx.rates[i].time; swingLowBar[n]=i;
           }
        }
     }

   //--- most recent swing strictly newer than `afterBar` --------------
   bool RecentSwingHigh(const int afterBar,double &price,int &bar) const
     {
      for(int i=0;i<ArraySize(swingHigh);i++)
         if(swingHighBar[i]>=afterBar) { price=swingHigh[i]; bar=swingHighBar[i]; return true; }
      return false;
     }
   bool RecentSwingLow(const int afterBar,double &price,int &bar) const
     {
      for(int i=0;i<ArraySize(swingLow);i++)
         if(swingLowBar[i]>=afterBar) { price=swingLow[i]; bar=swingLowBar[i]; return true; }
      return false;
     }

   //--- nearest swing high ABOVE price (the level a long must break) --
   bool NearestSwingHighAbove(const double price,double &out) const
     {
      double best=DBL_MAX; bool found=false;
      for(int i=0;i<ArraySize(swingHigh);i++)
         if(swingHigh[i]>price && swingHigh[i]<best) { best=swingHigh[i]; found=true; }
      if(found) out=best;
      return found;
     }
   bool NearestSwingLowBelow(const double price,double &out) const
     {
      double best=-DBL_MAX; bool found=false;
      for(int i=0;i<ArraySize(swingLow);i++)
         if(swingLow[i]<price && swingLow[i]>best) { best=swingLow[i]; found=true; }
      if(found) out=best;
      return found;
     }

   //--- Market Structure Shift: break of the opposing swing after a
   //    liquidity event, by close, with a minimum ATR-scaled distance.
   bool DetectMSS(CMarketContext &ctx,const bool bullish,const int sinceBar,
                  StructureEvent &ev) const
     {
      ev.valid=false;
      double a=ctx.ATR(1);
      if(a<=0.0) return false;
      double minBreak=InpMinBreakATR*a;

      if(bullish)
        {
         // reference = highest swing high formed between sinceBar and now
         double ref=-DBL_MAX; int refBar=-1;
         for(int i=0;i<ArraySize(swingHigh);i++)
            if(swingHighBar[i]<=sinceBar && swingHigh[i]>ref)
              { ref=swingHigh[i]; refBar=swingHighBar[i]; }
         if(refBar<0) return false;

         for(int b=MathMin(sinceBar,ctx.bars-1); b>=1; b--)
           {
            double px = InpRequireCloseBreak ? ctx.rates[b].close : ctx.rates[b].high;
            if(px > ref+minBreak)
              {
               ev.valid=true; ev.bullish=true; ev.brokenLevel=ref;
               ev.time=ctx.rates[b].time; ev.barIndex=b;
               return true;
              }
           }
        }
      else
        {
         double ref=DBL_MAX; int refBar=-1;
         for(int i=0;i<ArraySize(swingLow);i++)
            if(swingLowBar[i]<=sinceBar && swingLow[i]<ref)
              { ref=swingLow[i]; refBar=swingLowBar[i]; }
         if(refBar<0) return false;

         for(int b=MathMin(sinceBar,ctx.bars-1); b>=1; b--)
           {
            double px = InpRequireCloseBreak ? ctx.rates[b].close : ctx.rates[b].low;
            if(px < ref-minBreak)
              {
               ev.valid=true; ev.bullish=false; ev.brokenLevel=ref;
               ev.time=ctx.rates[b].time; ev.barIndex=b;
               return true;
              }
           }
        }
      return false;
     }
  };
#endif
