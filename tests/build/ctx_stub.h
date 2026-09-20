// Test scaffold: the slice of CMarketContext the extracted code touches.
#pragma once
#include "Config.mqh"

struct MqlRates { datetime time = 0; double open=0,high=0,low=0,close=0; long tick_volume=0; };

class CMarketContext
  {
public:
   MqlRates    rates[512];
   double      sma[512];
   int         bars = 0;
   ENUM_REGIME regime = REG_NONE;
   double      zscore = 0.0;     // what TrendZoneScore returns
   double      atrValue = 0.0;

   double ATR(const int i=1) const { (void)i; return atrValue>0.0?atrValue:0.0; }
   double TrendZoneScore(const int i=1) const { (void)i; return zscore; }
   string RegimeName(void) const
     {
      switch(regime)
        {
         case REG_TREND_UP:    return "TREND UP";
         case REG_TREND_DOWN:  return "TREND DOWN";
         case REG_RANGE:       return "RANGE";
         case REG_HIGH_VOL:    return "HIGH VOL";
         case REG_LOW_VOL:     return "LOW VOL";
         case REG_EXTREME_VOL: return "EXTREME VOL";
         default: break;
        }
      return "NONE";
     }
  };
