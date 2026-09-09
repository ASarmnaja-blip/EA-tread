//+------------------------------------------------------------------+
//| Regime.mqh - MODULE 3 + shared bar/indicator cache                |
//| Answers ENVIRONMENT. Owns ATR/EMA handles used by every module.   |
//+------------------------------------------------------------------+
#ifndef XAUM15_REGIME_MQH
#define XAUM15_REGIME_MQH
#include "Config.mqh"

class CMarketContext
  {
private:
   string            m_sym;
   ENUM_TIMEFRAMES   m_tf;
   int               m_hATR, m_hEmaFast, m_hEmaSlow, m_hSma;

public:
   MqlRates          rates[];        // index 0 = current forming bar
   double            atr[];          // aligned with rates
   double            emaFast[];
   double            emaSlow[];
   double            sma[];           // SMA200 - the research used SMA, not EMA
   int               bars;
   ENUM_REGIME       regime;
   double            atrPercentile;

   CMarketContext(void): m_hATR(INVALID_HANDLE), m_hEmaFast(INVALID_HANDLE),
                         m_hEmaSlow(INVALID_HANDLE), m_hSma(INVALID_HANDLE), bars(0),
                         regime(REG_NONE), atrPercentile(50.0) {}

   bool Init(const string sym,const ENUM_TIMEFRAMES tf)
     {
      m_sym=sym; m_tf=tf;
      m_hATR     = iATR(sym,tf,InpAtrPeriod);
      m_hEmaFast = iMA (sym,tf,InpEmaFast,0,MODE_EMA,PRICE_CLOSE);
      m_hEmaSlow = iMA (sym,tf,InpEmaSlow,0,MODE_EMA,PRICE_CLOSE);
      m_hSma     = iMA (sym,tf,InpTrendSmaPeriod,0,MODE_SMA,PRICE_CLOSE);
      if(m_hATR==INVALID_HANDLE||m_hEmaFast==INVALID_HANDLE||
         m_hEmaSlow==INVALID_HANDLE||m_hSma==INVALID_HANDLE)
         return false;
      ArraySetAsSeries(rates,true);
      ArraySetAsSeries(atr,true);
      ArraySetAsSeries(emaFast,true);
      ArraySetAsSeries(emaSlow,true);
      ArraySetAsSeries(sma,true);
      return true;
     }

   void Deinit(void)
     {
      if(m_hATR!=INVALID_HANDLE)     IndicatorRelease(m_hATR);
      if(m_hEmaFast!=INVALID_HANDLE) IndicatorRelease(m_hEmaFast);
      if(m_hEmaSlow!=INVALID_HANDLE) IndicatorRelease(m_hEmaSlow);
      if(m_hSma!=INVALID_HANDLE)     IndicatorRelease(m_hSma);
     }

   //--- pull everything once per bar; all modules read these arrays ---
   bool Refresh(const int depth)
     {
      int want = MathMax(depth, MathMax(InpEmaSlow,InpTrendSmaPeriod)+InpAtrRegimeLookback+10);
      bars = CopyRates(m_sym,m_tf,0,want,rates);
      if(bars < MathMax(InpEmaSlow,InpTrendSmaPeriod)+5) return false;

      if(CopyBuffer(m_hATR,0,0,bars,atr)<=0)         return false;
      if(CopyBuffer(m_hEmaFast,0,0,bars,emaFast)<=0) return false;
      if(CopyBuffer(m_hEmaSlow,0,0,bars,emaSlow)<=0) return false;
      if(CopyBuffer(m_hSma,0,0,bars,sma)<=0)         return false;

      Classify();
      return true;
     }

   double ATR(const int i=1) const
     {
      if(i<0||i>=ArraySize(atr)) return 0.0;
      double v=atr[i];
      return (v>0.0)?v:0.0;
     }

   //--- ATR rank over the lookback window ----------------------------
   double AtrPercentile(void)
     {
      int n=MathMin(InpAtrRegimeLookback,ArraySize(atr)-1);
      if(n<10) return 50.0;
      double cur=ATR(1);
      if(cur<=0.0) return 50.0;
      int below=0;
      for(int i=1;i<=n;i++) if(atr[i]<cur) below++;
      return 100.0*below/n;
     }

   //--- EMA50 slope normalised by ATR --------------------------------
   double SlopeATR(void) const
     {
      int k=InpEmaSlopeBars;
      if(ArraySize(emaFast)<=k+1) return 0.0;
      double a=ATR(1);
      if(a<=0.0) return 0.0;
      return (emaFast[1]-emaFast[1+k])/(k*a);
     }

   void Classify(void)
     {
      atrPercentile = AtrPercentile();

      if(InpBlockExtremeVol && atrPercentile>=InpExtremeVolPct)
        { regime=REG_EXTREME_VOL; return; }

      double close=rates[1].close;
      double a=ATR(1);
      double sep = (a>0.0) ? MathAbs(emaFast[1]-emaSlow[1])/a : 0.0;
      double slope=SlopeATR();

      bool compressed = (sep < InpRangeCompressATR);
      bool lowVol     = (atrPercentile <= InpLowVolPercentile);

      if(compressed || (lowVol && MathAbs(slope)<InpEmaSlopeMinATR))
        { regime = lowVol ? REG_LOW_VOL : REG_RANGE; return; }

      if(close>emaSlow[1] && emaFast[1]>emaSlow[1] && slope>=InpEmaSlopeMinATR)
        { regime=REG_TREND_UP; return; }
      if(close<emaSlow[1] && emaFast[1]<emaSlow[1] && slope<=-InpEmaSlopeMinATR)
        { regime=REG_TREND_DOWN; return; }

      regime = (atrPercentile>=InpHighVolPercentile) ? REG_HIGH_VOL : REG_RANGE;
     }

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
        }
      return "NONE";
     }

   bool TradingBlockedByRegime(string &why) const
     {
      if(!InpAblRegime) return false;
      if(regime==REG_EXTREME_VOL && InpBlockExtremeVol)
        { why="extreme volatility"; return true; }
      return false;
     }

   //--- (Close - SMA200) / ATR : the one statistic that survived testing
   //    Positive = price extended above the mean, negative = below.
   double TrendZoneScore(const int i=1) const
     {
      if(i<0 || i>=ArraySize(sma) || i>=bars) return 0.0;
      double a=ATR(i);
      if(a<=0.0 || sma[i]<=0.0) return 0.0;
      return (rates[i].close - sma[i]) / a;
     }

   //--- is the score inside the tested zone on the given side? --------
   bool InTrendZone(const bool isLong,const int i=1) const
     {
      double z=TrendZoneScore(i);
      if(z==0.0) return false;
      if(isLong) return (z>=InpTrendZoneMin && z<=InpTrendZoneMax);
      return (z<=-InpTrendZoneMin && z>=-InpTrendZoneMax);
     }

   //--- index of the bar that opened at/after `t` ---------------------
   int BarIndexAt(const datetime t) const
     {
      for(int i=0;i<bars;i++) if(rates[i].time<=t) return i;
      return bars-1;
     }
  };
#endif
