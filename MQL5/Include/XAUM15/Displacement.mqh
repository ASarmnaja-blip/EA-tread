//+------------------------------------------------------------------+
//| Displacement.mqh - MODULE 10                                      |
//| Answers MOMENTUM CONFIRMATION.                                    |
//+------------------------------------------------------------------+
#ifndef XAUM15_DISP_MQH
#define XAUM15_DISP_MQH
#include "Config.mqh"
#include "Regime.mqh"

class CDisplacement
  {
public:
   int    lastBar;
   double lastBodyATR;

   CDisplacement(void): lastBar(-1), lastBodyATR(0.0) {}

   //--- is bar `i` a displacement candle in `bullish` direction? ------
   bool IsDisplacement(CMarketContext &ctx,const int i,const bool bullish)
     {
      if(i<1 || i>=ctx.bars) return false;
      double a=ctx.ATR(i);
      if(a<=0.0) return false;

      double o=ctx.rates[i].open, c=ctx.rates[i].close;
      double h=ctx.rates[i].high, l=ctx.rates[i].low;
      double range=h-l;
      if(range<=0.0) return false;

      double body=MathAbs(c-o);
      if(body/a < InpMinBodyATR) return false;

      // direction must match
      if(bullish && c<=o) return false;
      if(!bullish && c>=o) return false;

      // close must sit near the extreme of the bar
      double closeLoc = bullish ? (c-l)/range : (h-c)/range;
      if(closeLoc < InpMinCloseLocation) return false;

      lastBar=i; lastBodyATR=body/a;
      return true;
     }

   //--- any displacement within the recent window ---------------------
   bool FoundRecently(CMarketContext &ctx,const bool bullish,const int fromBar,int &atBar)
     {
      if(!InpAblDisplacement) { atBar=fromBar; return true; }
      int last=MathMin(fromBar+InpDisplacementLookback,ctx.bars-1);
      for(int i=1;i<=last;i++)
         if(IsDisplacement(ctx,i,bullish)) { atBar=i; return true; }
      return false;
     }
  };
#endif
