//+------------------------------------------------------------------+
//| Quality.mqh - MODULE 28                                           |
//| Spec 28: this is a CLASSIFIER, not the entry trigger. A setup     |
//| must already be structurally valid before it is graded here; the  |
//| grade only decides whether that valid setup is allowed to trade.  |
//+------------------------------------------------------------------+
#ifndef XAUM15_QUALITY_MQH
#define XAUM15_QUALITY_MQH
#include "Config.mqh"
#include "Regime.mqh"
#include "VolumeProfile.mqh"
#include "VWAP.mqh"
#include "AMD.mqh"
#include "SessionFilter.mqh"

class CQualityGrader
  {
public:
   string detail;

   ENUM_QUALITY Grade(CMarketContext &ctx,CVolumeProfile &vp,CVWAP &vwap,
                      CAMD &amd,CSessionFilter &sess,const datetime now,
                      const double spread,TradeSignal &sig)
     {
      detail="";
      if(!InpAblQuality) return Q_APLUS;

      int confluence=0;
      string parts="";

      //--- session quality: overlap > single session -----------------
      if(sess.IsOverlap(now))      { confluence+=2; parts+="overlap "; }
      else if(sess.IsLondon(now)||sess.IsNewYork(now)) { confluence+=1; parts+="session "; }

      //--- trend alignment -------------------------------------------
      if((sig.isLong  && ctx.regime==REG_TREND_UP) ||
         (!sig.isLong && ctx.regime==REG_TREND_DOWN)) { confluence+=2; parts+="trend "; }
      else if(ctx.regime==REG_RANGE)                  { confluence-=1; parts+="range "; }

      //--- AMD context ----------------------------------------------
      if(amd.Supports(sig.isLong) && amd.phase!=AMD_NONE) { confluence+=1; parts+="amd "; }

      //--- VWAP side -------------------------------------------------
      if(vwap.valid)
        {
         if((sig.isLong && sig.entry>vwap.value) || (!sig.isLong && sig.entry<vwap.value))
           { confluence+=1; parts+="vwap "; }
         else confluence-=1;
        }

      //--- volume profile location -----------------------------------
      if(vp.valid)
        {
         bool goodLoc = sig.isLong ? (sig.entry>=vp.val) : (sig.entry<=vp.vah);
         if(goodLoc) { confluence+=1; parts+="value "; }
        }

      //--- liquidity + sweep quality ---------------------------------
      if(sig.sweepType!=SWEEP_NONE) { confluence+=2; parts+="sweep "; }
      if(sig.mss)                   { confluence+=1; parts+="mss "; }
      if(sig.displacement)          { confluence+=1; parts+="disp "; }

      //--- volatility sanity -----------------------------------------
      if(ctx.regime==REG_EXTREME_VOL) confluence-=3;
      if(ctx.regime==REG_LOW_VOL)     confluence-=1;

      //--- execution cost --------------------------------------------
      if(sig.riskDistance>0.0)
        {
         double costRatio=spread/sig.riskDistance;
         if(costRatio>0.15) { confluence-=2; parts+="wide-spread "; }
         else if(costRatio<0.05) confluence+=1;
        }

      //--- reward -----------------------------------------------------
      double rr=InpTP3R;
      if(rr<InpMinRR) confluence-=2;

      ENUM_QUALITY q;
      if(confluence>=9)      q=Q_APLUS;
      else if(confluence>=7) q=Q_A;
      else if(confluence>=5) q=Q_B;
      else                   q=Q_C;

      detail=StringFormat("score %d [%s]",confluence,parts);
      return q;
     }

   bool Allowed(const ENUM_QUALITY q) const
     {
      switch(q)
        {
         case Q_APLUS: return InpAllowAPlus;
         case Q_A:     return InpAllowA;
         case Q_B:     return InpAllowBSetup;
         case Q_C:     return InpAllowCSetup;
        }
      return false;
     }

   static string Name(const ENUM_QUALITY q)
     {
      switch(q)
        {
         case Q_APLUS: return "A+";
         case Q_A:     return "A";
         case Q_B:     return "B";
         case Q_C:     return "C";
        }
      return "-";
     }
  };
#endif
