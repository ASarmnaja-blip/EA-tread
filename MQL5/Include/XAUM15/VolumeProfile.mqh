//+------------------------------------------------------------------+
//| VolumeProfile.mqh - MODULE 6 + 9                                  |
//| Answers VALUE / LOCATION. Never a standalone entry signal.        |
//|                                                                   |
//| SOURCE DISCLOSURE (spec 8): XAU/USD spot is OTC. The default      |
//| source is BROKER TICK VOLUME, which is a count of price updates   |
//| at ONE broker - it is NOT global gold volume and it is NOT COMEX  |
//| futures volume. Treat the profile as a broker-local approximation |
//| of where that feed spent time. VOL_EXTERNAL reads a separate      |
//| futures symbol when the broker offers one.                        |
//+------------------------------------------------------------------+
#ifndef XAUM15_VP_MQH
#define XAUM15_VP_MQH
#include "Config.mqh"
#include "Regime.mqh"

class CVolumeProfile
  {
private:
   double m_bin[];
   double m_lo, m_hi, m_binSize;
   string m_srcSymbol;

public:
   double poc, vah, val;
   double totalVolume;
   bool   valid;
   string sourceName;
   double hvn[], lvn[];   // prices of high/low volume nodes

   CVolumeProfile(void): m_lo(0),m_hi(0),m_binSize(0),poc(0),vah(0),val(0),
                         totalVolume(0),valid(false),sourceName("TICK") {}

   //--- pick the volume series honouring InpVolumeSource --------------
   double BarVolume(const MqlRates &r) const
     {
      switch(InpVolumeSource)
        {
         case VOL_EXTERNAL:                     // real volume if broker supplies it
            if(r.real_volume>0) return (double)r.real_volume;
            return (double)r.tick_volume;
         case VOL_AUTO:
            return (r.real_volume>0)?(double)r.real_volume:(double)r.tick_volume;
         default:
            return (double)r.tick_volume;
        }
     }

   void ResolveSourceName(CMarketContext &ctx)
     {
      bool hasReal=false;
      for(int i=1;i<MathMin(50,ctx.bars);i++)
         if(ctx.rates[i].real_volume>0) { hasReal=true; break; }
      if(InpVolumeSource==VOL_BROKER_TICK)      sourceName="BROKER_TICK";
      else if(InpVolumeSource==VOL_EXTERNAL)    sourceName = hasReal?"REAL_VOL":"TICK(fallback)";
      else                                      sourceName = hasReal?"AUTO:REAL":"AUTO:TICK";
     }

   //--- build the profile over [fromBar..toBar] (bar indices) ---------
   bool Build(CMarketContext &ctx,const int fromBar,const int toBar)
     {
      valid=false;
      int a=MathMin(fromBar,toBar), b=MathMax(fromBar,toBar);
      a=MathMax(a,1);
      b=MathMin(b,ctx.bars-1);
      if(b-a < 5) return false;

      m_lo=DBL_MAX; m_hi=-DBL_MAX;
      for(int i=a;i<=b;i++)
        { m_lo=MathMin(m_lo,ctx.rates[i].low); m_hi=MathMax(m_hi,ctx.rates[i].high); }
      if(m_hi<=m_lo) return false;

      int nb=MathMax(10,InpVPBins);
      ArrayResize(m_bin,nb);
      ArrayInitialize(m_bin,0.0);
      m_binSize=(m_hi-m_lo)/nb;
      if(m_binSize<=0.0) return false;

      totalVolume=0.0;
      // Spread each bar's volume evenly across the bins its range covers.
      for(int i=a;i<=b;i++)
        {
         double v=BarVolume(ctx.rates[i]);
         if(v<=0.0) continue;
         int lo=(int)MathFloor((ctx.rates[i].low -m_lo)/m_binSize);
         int hi=(int)MathFloor((ctx.rates[i].high-m_lo)/m_binSize);
         lo=MathMax(0,MathMin(nb-1,lo));
         hi=MathMax(0,MathMin(nb-1,hi));
         int span=hi-lo+1;
         double share=v/span;
         for(int k=lo;k<=hi;k++) m_bin[k]+=share;
         totalVolume+=v;
        }
      if(totalVolume<=0.0) return false;

      ComputeValueArea(nb);
      ComputeNodes(nb);
      valid=true;
      return true;
     }

private:
   double BinPrice(const int k) const { return m_lo+(k+0.5)*m_binSize; }

   //--- standard two-sided expansion from POC to InpValueAreaPercent --
   void ComputeValueArea(const int nb)
     {
      int pocIdx=0;
      for(int k=1;k<nb;k++) if(m_bin[k]>m_bin[pocIdx]) pocIdx=k;
      poc=BinPrice(pocIdx);

      double target=totalVolume*(InpValueAreaPercent/100.0);
      double acc=m_bin[pocIdx];
      int up=pocIdx, dn=pocIdx;

      while(acc<target && (up<nb-1 || dn>0))
        {
         double vUp = (up<nb-1) ? m_bin[up+1] : -1.0;
         double vDn = (dn>0)    ? m_bin[dn-1] : -1.0;
         if(vUp<0.0 && vDn<0.0) break;
         if(vUp>=vDn) { up++; acc+=vUp; }
         else         { dn--; acc+=vDn; }
        }
      vah=BinPrice(up);
      val=BinPrice(dn);
     }

   //--- HVN/LVN relative to mean bin volume --------------------------
   void ComputeNodes(const int nb)
     {
      ArrayResize(hvn,0); ArrayResize(lvn,0);
      double mean=totalVolume/nb;
      if(mean<=0.0) return;
      for(int k=1;k<nb-1;k++)
        {
         bool localMax = (m_bin[k]>m_bin[k-1] && m_bin[k]>m_bin[k+1]);
         bool localMin = (m_bin[k]<m_bin[k-1] && m_bin[k]<m_bin[k+1]);
         if(localMax && m_bin[k]>mean*1.5)
           { int n=ArraySize(hvn); ArrayResize(hvn,n+1); hvn[n]=BinPrice(k); }
         if(localMin && m_bin[k]<mean*0.5)
           { int n=ArraySize(lvn); ArrayResize(lvn,n+1); lvn[n]=BinPrice(k); }
        }
     }

public:
   bool InValueArea(const double p) const { return valid && p<=vah && p>=val; }
   bool AboveValue (const double p) const { return valid && p>vah; }
   bool BelowValue (const double p) const { return valid && p<val; }

   bool NearLevel(const double p,const double level,const double atr) const
     { return valid && atr>0.0 && MathAbs(p-level) <= InpVPTouchATR*atr; }

   //--- spec 9: reclaim of VAL from below (long) / VAH from above -----
   bool ReclaimedVAL(CMarketContext &ctx,const int bar) const
     {
      if(!valid || bar+1>=ctx.bars) return false;
      return (ctx.rates[bar+1].low < val && ctx.rates[bar].close > val);
     }
   bool RejectedVAH(CMarketContext &ctx,const int bar) const
     {
      if(!valid || bar+1>=ctx.bars) return false;
      return (ctx.rates[bar+1].high > vah && ctx.rates[bar].close < vah);
     }

   //--- value acceptance: N consecutive closes inside the area --------
   bool ValueAccepted(CMarketContext &ctx,const int bar,const int n=3) const
     {
      if(!valid) return false;
      for(int i=bar;i<bar+n && i<ctx.bars;i++)
         if(ctx.rates[i].close>vah || ctx.rates[i].close<val) return false;
      return true;
     }
  };
#endif
