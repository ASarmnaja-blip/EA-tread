//+------------------------------------------------------------------+
//| VWAP.mqh - MODULE 7                                               |
//| Session VWAP. Context filter only - never a standalone signal.    |
//+------------------------------------------------------------------+
#ifndef XAUM15_VWAP_MQH
#define XAUM15_VWAP_MQH
#include "Config.mqh"
#include "Regime.mqh"

class CVWAP
  {
public:
   double value;
   double upperBand, lowerBand;
   bool   valid;

   CVWAP(void): value(0.0), upperBand(0.0), lowerBand(0.0), valid(false) {}

   //--- volume-weighted typical price since sessionStart -------------
   void Calculate(CMarketContext &ctx,const datetime sessionStart)
     {
      valid=false; value=0.0;
      double sumPV=0.0, sumV=0.0, sumP2V=0.0;
      int counted=0;

      for(int i=1;i<ctx.bars;i++)
        {
         if(ctx.rates[i].time < sessionStart) break;
         double tp  = (ctx.rates[i].high+ctx.rates[i].low+ctx.rates[i].close)/3.0;
         double vol = (double)ctx.rates[i].tick_volume;
         if(vol<=0.0) vol=1.0;               // guard: dead bar
         sumPV  += tp*vol;
         sumP2V += tp*tp*vol;
         sumV   += vol;
         counted++;
        }
      if(counted<2 || sumV<=0.0) return;

      value = sumPV/sumV;
      double var = sumP2V/sumV - value*value;
      double sd  = (var>0.0)?MathSqrt(var):0.0;
      upperBand = value+sd;
      lowerBand = value-sd;
      valid=true;
     }

   bool BullishContext(const double price) const { return valid && price>value; }
   bool BearishContext(const double price) const { return valid && price<value; }

   //--- soft by default: returns true unless configured as hard gate --
   bool Allows(const bool isLong,const double price) const
     {
      if(!InpUseVWAP || !InpAblVWAP) return true;
      if(!valid) return true;
      if(!InpVWAPHardFilter) return true;
      return isLong ? (price>value) : (price<value);
     }
  };
#endif
