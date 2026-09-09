//+------------------------------------------------------------------+
//| Liquidity.mqh - MODULE 4                                          |
//| Answers WHERE. Builds the liquidity map with price/type/age/       |
//| distance/strength for every level (spec 6).                       |
//+------------------------------------------------------------------+
#ifndef XAUM15_LIQ_MQH
#define XAUM15_LIQ_MQH
#include "Config.mqh"
#include "Regime.mqh"
#include "Structure.mqh"
#include "SessionFilter.mqh"

class CLiquidityMap
  {
private:
   void Add(const double price,const ENUM_LIQ_TYPE t,const datetime when,const int strength)
     {
      if(price<=0.0) return;
      int n=ArraySize(levels);
      if(n>=InpLiquidityMaxLevels) return;
      // merge duplicates within a tick
      for(int i=0;i<n;i++)
         if(MathAbs(levels[i].price-price) < 1e-8)
           { levels[i].strength += strength; return; }
      ArrayResize(levels,n+1);
      levels[n].price=price; levels[n].type=t; levels[n].created=when;
      levels[n].strength=strength; levels[n].swept=false; levels[n].ageBars=0;
     }

public:
   LiquidityLevel levels[];
   double asianHigh, asianLow, asianRange;
   double pdh, pdl, pwh, pwl;
   double londonHigh, londonLow;
   bool   asianValid;

   CLiquidityMap(void): asianHigh(0),asianLow(0),asianRange(0),
                        pdh(0),pdl(0),pwh(0),pwl(0),
                        londonHigh(0),londonLow(0),asianValid(false) {}

   //--- previous completed D1 / W1 candles ---------------------------
   void LoadHigherTF(const string sym)
     {
      MqlRates d[]; ArraySetAsSeries(d,true);
      if(CopyRates(sym,PERIOD_D1,0,3,d)>=2) { pdh=d[1].high; pdl=d[1].low; }
      MqlRates w[]; ArraySetAsSeries(w,true);
      if(CopyRates(sym,PERIOD_W1,0,3,w)>=2) { pwh=w[1].high; pwl=w[1].low; }
     }

   //--- range of a time window on the working timeframe --------------
   bool RangeBetween(CMarketContext &ctx,const datetime from,const datetime to,
                     double &hi,double &lo,int &barsCounted)
     {
      hi=-DBL_MAX; lo=DBL_MAX; barsCounted=0;
      for(int i=1;i<ctx.bars;i++)
        {
         datetime bt=ctx.rates[i].time;
         if(bt>=to) continue;
         if(bt<from) break;
         hi=MathMax(hi,ctx.rates[i].high);
         lo=MathMin(lo,ctx.rates[i].low);
         barsCounted++;
        }
      return (barsCounted>0 && hi>lo);
     }

   void Build(CMarketContext &ctx,CStructure &st,CSessionFilter &sess,const datetime now)
     {
      ArrayResize(levels,0);
      LoadHigherTF(_Symbol);

      double a=ctx.ATR(1);

      //--- Asian range (accumulation reference) ----------------------
      datetime aS=sess.AsianStart(now), aE=sess.AsianEnd(now);
      int cnt=0;
      asianValid=false;
      datetime aStop=(aE<now)?aE:now;
      if(RangeBetween(ctx,aS,aStop,asianHigh,asianLow,cnt) && cnt>=4)
        {
         asianRange=asianHigh-asianLow;
         if(a>0.0)
            asianValid = (asianRange >= InpAsianRangeMinATR*a &&
                          asianRange <= InpAsianRangeMaxATR*a);
         else
            asianValid = (asianRange>0.0);
        }

      //--- London range so far --------------------------------------
      datetime lS=sess.SessionOpen(now,InpLondonStartHour);
      int lc=0;
      RangeBetween(ctx,lS,now,londonHigh,londonLow,lc);

      //--- populate the map -----------------------------------------
      if(pdh>0) Add(pdh,LQ_PDH,now,3);
      if(pdl>0) Add(pdl,LQ_PDL,now,3);
      if(pwh>0) Add(pwh,LQ_PWH,now,4);
      if(pwl>0) Add(pwl,LQ_PWL,now,4);
      if(asianValid)
        { Add(asianHigh,LQ_ASIA_H,aE,3); Add(asianLow,LQ_ASIA_L,aE,3); }
      if(lc>3)
        { Add(londonHigh,LQ_LDN_H,now,2); Add(londonLow,LQ_LDN_L,now,2); }

      for(int i=0;i<ArraySize(st.swingHigh);i++)
        {
         if(st.swingHighBar[i]>InpLiquidityMaxAgeBars) continue;
         Add(st.swingHigh[i],LQ_SWING_H,st.swingHighTime[i],1);
        }
      for(int i=0;i<ArraySize(st.swingLow);i++)
        {
         if(st.swingLowBar[i]>InpLiquidityMaxAgeBars) continue;
         Add(st.swingLow[i],LQ_SWING_L,st.swingLowTime[i],1);
        }

      MarkEqualLevels(st,a);
      UpdateAges(ctx);
     }

   //--- equal highs/lows are stronger liquidity pools -----------------
   void MarkEqualLevels(CStructure &st,const double atr)
     {
      if(atr<=0.0) return;
      double tol=InpEqualLevelATR*atr;

      for(int i=0;i<ArraySize(st.swingHigh);i++)
         for(int j=i+1;j<ArraySize(st.swingHigh);j++)
            if(MathAbs(st.swingHigh[i]-st.swingHigh[j])<=tol)
               Add(MathMax(st.swingHigh[i],st.swingHigh[j]),LQ_EQH,st.swingHighTime[i],3);

      for(int i=0;i<ArraySize(st.swingLow);i++)
         for(int j=i+1;j<ArraySize(st.swingLow);j++)
            if(MathAbs(st.swingLow[i]-st.swingLow[j])<=tol)
               Add(MathMin(st.swingLow[i],st.swingLow[j]),LQ_EQL,st.swingLowTime[i],3);
     }

   void UpdateAges(CMarketContext &ctx)
     {
      for(int i=0;i<ArraySize(levels);i++)
        {
         int bars=0;
         for(int b=1;b<ctx.bars;b++)
            if(ctx.rates[b].time<=levels[i].created) { bars=b; break; }
         levels[i].ageBars=bars;
        }
     }

   //--- nearest untouched level on one side --------------------------
   bool NearestAbove(const double price,LiquidityLevel &out) const
     {
      double best=DBL_MAX; int idx=-1;
      for(int i=0;i<ArraySize(levels);i++)
         if(!levels[i].swept && levels[i].price>price && levels[i].price<best)
           { best=levels[i].price; idx=i; }
      if(idx<0) return false;
      out=levels[idx];
      return true;
     }
   bool NearestBelow(const double price,LiquidityLevel &out) const
     {
      double best=-DBL_MAX; int idx=-1;
      for(int i=0;i<ArraySize(levels);i++)
         if(!levels[i].swept && levels[i].price<price && levels[i].price>best)
           { best=levels[i].price; idx=i; }
      if(idx<0) return false;
      out=levels[idx];
      return true;
     }

   static string TypeName(const ENUM_LIQ_TYPE t)
     {
      switch(t)
        {
         case LQ_PDH:    return "PDH";     case LQ_PDL:    return "PDL";
         case LQ_ASIA_H: return "AsiaH";   case LQ_ASIA_L: return "AsiaL";
         case LQ_LDN_H:  return "LdnH";    case LQ_LDN_L:  return "LdnL";
         case LQ_PWH:    return "PWH";     case LQ_PWL:    return "PWL";
         case LQ_SWING_H:return "SwingH";  case LQ_SWING_L:return "SwingL";
         case LQ_EQH:    return "EQH";     case LQ_EQL:    return "EQL";
        }
      return "?";
     }
  };
#endif
