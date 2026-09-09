//+------------------------------------------------------------------+
//| RiskManager.mqh - MODULE 12                                       |
//| Answers SURVIVAL. Equity-based sizing only - no fixed lot, no     |
//| martingale, no grid, no recovery lot, no risk increase on loss.   |
//+------------------------------------------------------------------+
#ifndef XAUM15_RISK_MQH
#define XAUM15_RISK_MQH
#include "Config.mqh"
#include "Broker.mqh"

struct SizingResult
  {
   bool   ok;
   int    positions;      // how many legs actually fit the risk cap
   double lot;            // lot PER LEG
   double riskMoney;      // total risk across all legs
   double riskPercent;    // total risk as % of equity
   string reason;
  };

class CRiskManager
  {
public:
   //--- Structure-based SL distance (spec 18) -------------------------
   //    SL = structure extreme +/- ATR buffer, clamped to [min,max]*ATR
   double StopDistance(const double entry,const double structureLevel,const double atr) const
     {
      if(atr<=0.0) return 0.0;
      // SL_FIXED_ATR reproduces the configuration that won the research:
      // a flat 1.8 x ATR stop, no structure term, no buffer.
      if(InpSLMode==SL_FIXED_ATR) return InpTrendSLATR*atr;
      double raw = MathAbs(entry-structureLevel) + InpSLBufferATR*atr;
      double lo  = InpMinSLATR*atr;
      double hi  = InpMaxSLATR*atr;
      if(raw<lo) raw=lo;
      if(raw>hi) return 0.0;         // too wide: reject rather than clip the stop
      return raw;
     }

   //--- Position sizing with graceful degradation ---------------------
   //    On a small account the broker minimum lot can exceed the risk
   //    budget for 3 legs. Rather than silently over-risking, drop legs
   //    3 -> 2 -> 1; if one minimum leg still breaches the cap, reject.
   SizingResult Size(CBroker &br,const double equity,const double slDistance) const
     {
      SizingResult r;
      r.ok=false; r.positions=0; r.lot=0.0; r.riskMoney=0.0; r.riskPercent=0.0; r.reason="";

      if(slDistance<=0.0) { r.reason="sl distance<=0"; return r; }
      if(equity<=0.0)     { r.reason="equity<=0";      return r; }

      double budget = equity*(InpRiskPercent/100.0);
      double cap    = equity*(InpMaxRiskPercent/100.0);

      int wanted = MathMax(1,MathMin(InpPositionsPerSetup,LegsForExitMode()));
      for(int legs=wanted; legs>=1; legs--)
        {
         double perLeg = budget/legs;
         double raw    = br.LotForRisk(perLeg,slDistance);
         double lot    = br.NormLot(raw);
         if(lot<=0.0) continue;

         double total  = br.RiskMoney(lot,slDistance)*legs;

         if(total<=cap)
           {
            r.ok=true; r.positions=legs; r.lot=lot;
            r.riskMoney=total; r.riskPercent=100.0*total/equity;
            if(lot<=br.lotMin+1e-9 && legs<wanted)
               r.reason=StringFormat("min lot floor: %d legs instead of %d",
                                     legs,wanted);
            return r;
           }

         if(InpLotFitMode==LOTFIT_REJECT) break;
         if(InpLotFitMode==LOTFIT_ALLOW_OVER)
           {
            r.ok=true; r.positions=legs; r.lot=lot;
            r.riskMoney=total; r.riskPercent=100.0*total/equity;
            r.reason="risk cap overridden by LOTFIT_ALLOW_OVER";
            return r;
           }
         // LOTFIT_REDUCE_POSITIONS: try fewer legs
        }

      r.reason=StringFormat("min lot %.2f risks more than %.2f%% cap at SL %.2f",
                            br.lotMin,InpMaxRiskPercent,slDistance);
      return r;
     }

   //--- TP ladder at 1R / 2R / 3R -------------------------------------
   void BuildTargets(const bool isLong,const double entry,const double slDistance,
                     double &tp1,double &tp2,double &tp3) const
     {
      double s = isLong?1.0:-1.0;
      tp1 = entry + s*slDistance*InpTP1R;
      tp2 = entry + s*slDistance*InpTP2R;
      tp3 = entry + s*slDistance*InpTP3R;
     }

   //--- how many real positions this exit mode needs -------------------
   static int LegsForExitMode(void)
     {
      switch(InpExitMode)
        {
         case EXIT_TP_LADDER:      return 3;
         case EXIT_PARTIAL_RUNNER: return 2;   // equal lots = the tested 50/50
         default:                  return 1;   // single target, or time stop only
        }
     }

   //--- fill tp[] according to the configured exit model ---------------
   //    A zero entry in tp[] means "no target on that leg".
   void BuildExit(const bool isLong,const double entry,const double slDistance,
                  double &tp[]) const
     {
      double s = isLong?1.0:-1.0;
      tp[0]=0.0; tp[1]=0.0; tp[2]=0.0;

      switch(InpExitMode)
        {
         case EXIT_TP_LADDER:
            tp[0]=entry+s*slDistance*InpTP1R;
            tp[1]=entry+s*slDistance*InpTP2R;
            tp[2]=entry+s*slDistance*InpTP3R;
            break;

         case EXIT_SINGLE_TARGET:
            tp[0]=entry+s*slDistance*InpTargetR;
            break;

         case EXIT_PARTIAL_RUNNER:
            tp[0]=entry+s*slDistance*InpPartialR;   // banked half
            tp[1]=entry+s*slDistance*InpTargetR;    // runner
            break;

         case EXIT_TIME_STOP_ONLY:
            break;                                  // nothing to place
        }
     }
  };
#endif
