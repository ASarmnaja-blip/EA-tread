//+------------------------------------------------------------------+
//| Setups.mqh - MODULE 11 entry engine                               |
//| Spec 16: A, B and C are INDEPENDENT evaluators. They never share  |
//| a combined score, they can be toggled separately and their stats  |
//| are reported separately.                                          |
//+------------------------------------------------------------------+
#ifndef XAUM15_SETUPS_MQH
#define XAUM15_SETUPS_MQH
#include "Config.mqh"
#include "Regime.mqh"
#include "Structure.mqh"
#include "Liquidity.mqh"
#include "Sweep.mqh"
#include "Displacement.mqh"
#include "VolumeProfile.mqh"
#include "VWAP.mqh"
#include "AMD.mqh"
#include "SessionFilter.mqh"
#include "RiskManager.mqh"

//--- shared helper: has price returned to the trigger zone? ----------
bool RetestSatisfied(CMarketContext &ctx,const bool isLong,const double level,
                     const int sinceBar,const double atr)
  {
   if(InpEntryMode!=ENTRY_RETEST) return true;
   if(atr<=0.0) return false;
   double zone=InpRetestZoneATR*atr;
   int last=MathMin(sinceBar,InpRetestMaxBars);
   for(int i=1;i<=last && i<ctx.bars;i++)
     {
      if(isLong  && ctx.rates[i].low  <= level+zone && ctx.rates[i].close > level) return true;
      if(!isLong && ctx.rates[i].high >= level-zone && ctx.rates[i].close < level) return true;
     }
   return false;
  }

void ZeroSignal(TradeSignal &s)
  {
   s.valid=false; s.setup=SETUP_NONE; s.isLong=false;
   s.entry=0; s.sl=0; s.riskDistance=0; s.quality=Q_NONE; s.reason="";
   s.tp[0]=0; s.tp[1]=0; s.tp[2]=0;
   s.atr=0; s.vwap=0; s.poc=0; s.vah=0; s.val=0; s.liqLevel=0; s.spread=0;
   s.sweepType=SWEEP_NONE; s.mss=false; s.displacement=false;
  }

//====================================================================
// SETUP A - AMD LIQUIDITY REVERSAL (spec 13)
//====================================================================
class CSetupA
  {
public:
   bool Evaluate(CMarketContext &ctx,CStructure &st,CLiquidityMap &liq,
                 CSweepDetector &sw,CDisplacement &disp,CVolumeProfile &vp,
                 CVWAP &vwap,CAMD &amd,CRiskManager &rm,const bool tryLong,
                 TradeSignal &sig)
     {
      ZeroSignal(sig);
      if(!InpEnableSetupA) return false;

      double a=ctx.ATR(1);
      if(a<=0.0) return false;
      if(InpAblLiquidity && !liq.asianValid) return false;   // 1. Asian range established

      // 2-4. Sweep of the Asian extreme with a close back inside
      double target = tryLong ? liq.asianLow : liq.asianHigh;
      ENUM_LIQ_TYPE lt = tryLong ? LQ_ASIA_L : LQ_ASIA_H;
      SweepEvent ev;
      if(!sw.FindOnLevel(ctx,target,!tryLong,lt,ev))
        {
         // fall back to any liquidity pool on the correct side
         if(!InpAblLiquidity) return false;
         if(!sw.FindRecent(ctx,liq,!tryLong,ev)) return false;
        }

      // 5. Market structure shift in the trade direction
      StructureEvent mss;
      if(!st.DetectMSS(ctx,tryLong,ev.barIndex,mss)) return false;

      // 6. Displacement confirming momentum
      int dBar=0;
      if(!disp.FoundRecently(ctx,tryLong,mss.barIndex,dBar)) return false;

      // 7. Optional context filters
      double px=ctx.rates[1].close;
      if(!vwap.Allows(tryLong,px)) return false;

      // 8. Retest of the broken structure level
      if(!RetestSatisfied(ctx,tryLong,mss.brokenLevel,mss.barIndex,a)) return false;

      // 9. Build the order
      // stop sits beyond the sweep extreme on either side
      double slDist = rm.StopDistance(px,ev.extreme,a);
      if(slDist<=0.0) return false;

      sig.valid=true; sig.setup=SETUP_A; sig.isLong=tryLong;
      sig.entry=px;
      sig.sl = tryLong ? px-slDist : px+slDist;
      sig.riskDistance=slDist;
      rm.BuildTargets(tryLong,px,slDist,sig.tp[0],sig.tp[1],sig.tp[2]);
      sig.atr=a; sig.liqLevel=ev.level; sig.sweepType=ev.side;
      sig.mss=true; sig.displacement=true;
      sig.vwap=vwap.valid?vwap.value:0.0;
      sig.poc=vp.valid?vp.poc:0.0; sig.vah=vp.valid?vp.vah:0.0; sig.val=vp.valid?vp.val:0.0;
      sig.reason=StringFormat("A:sweep %s @%.2f + MSS + displacement",
                              CLiquidityMap::TypeName(ev.liqType),ev.level);
      return true;
     }
  };

//====================================================================
// SETUP B - VOLUME PROFILE CONTINUATION (spec 14)
//====================================================================
class CSetupB
  {
public:
   bool Evaluate(CMarketContext &ctx,CStructure &st,CDisplacement &disp,
                 CVolumeProfile &vp,CVWAP &vwap,CRiskManager &rm,
                 const bool tryLong,TradeSignal &sig)
     {
      ZeroSignal(sig);
      if(!InpEnableSetupB) return false;
      if(InpAblVolumeProfile && !vp.valid) return false;

      double a=ctx.ATR(1);
      if(a<=0.0) return false;

      // 1. Trend regime must agree
      if(InpAblRegime)
        {
         if(tryLong  && ctx.regime!=REG_TREND_UP)   return false;
         if(!tryLong && ctx.regime!=REG_TREND_DOWN) return false;
        }

      double px=ctx.rates[1].close;

      // 2. VWAP side
      if(InpAblVWAP && vwap.valid)
        {
         if(tryLong  && px<=vwap.value) return false;
         if(!tryLong && px>=vwap.value) return false;
        }

      // 3. Pullback into value, then acceptance rather than rejection
      if(InpAblVolumeProfile)
        {
         double ref = tryLong ? vp.val : vp.vah;
         bool pulledBack=false;
         for(int i=1;i<=InpRetestMaxBars && i<ctx.bars;i++)
            if(vp.NearLevel(ctx.rates[i].low,vp.poc,a) ||
               vp.NearLevel(ctx.rates[i].high,vp.poc,a) ||
               vp.NearLevel(ctx.rates[i].close,ref,a))
              { pulledBack=true; break; }
         if(!pulledBack) return false;
         if(!vp.ValueAccepted(ctx,1,2)) return false;
        }

      // 4. Structure continuation in the trend direction
      StructureEvent mss;
      if(!st.DetectMSS(ctx,tryLong,MathMin(InpRetestMaxBars,ctx.bars-1),mss)) return false;

      // 5. Displacement
      int dBar=0;
      if(!disp.FoundRecently(ctx,tryLong,mss.barIndex,dBar)) return false;

      // 6. Retest
      if(!RetestSatisfied(ctx,tryLong,mss.brokenLevel,mss.barIndex,a)) return false;

      // 7. Stop behind the pullback extreme
      double structureLevel=px;
      if(tryLong)
        { structureLevel=ctx.rates[1].low;
          for(int i=1;i<=InpRetestMaxBars && i<ctx.bars;i++)
             structureLevel=MathMin(structureLevel,ctx.rates[i].low); }
      else
        { structureLevel=ctx.rates[1].high;
          for(int i=1;i<=InpRetestMaxBars && i<ctx.bars;i++)
             structureLevel=MathMax(structureLevel,ctx.rates[i].high); }

      double slDist=rm.StopDistance(px,structureLevel,a);
      if(slDist<=0.0) return false;

      sig.valid=true; sig.setup=SETUP_B; sig.isLong=tryLong;
      sig.entry=px;
      sig.sl = tryLong ? px-slDist : px+slDist;
      sig.riskDistance=slDist;
      rm.BuildTargets(tryLong,px,slDist,sig.tp[0],sig.tp[1],sig.tp[2]);
      sig.atr=a; sig.mss=true; sig.displacement=true;
      sig.vwap=vwap.valid?vwap.value:0.0;
      sig.poc=vp.valid?vp.poc:0.0; sig.vah=vp.valid?vp.vah:0.0; sig.val=vp.valid?vp.val:0.0;
      sig.reason="B:value acceptance + trend continuation";
      return true;
     }
  };

//====================================================================
// SETUP C - OPENING RANGE EXPANSION (spec 15)
//====================================================================
class CSetupC
  {
public:
   double orHigh, orLow;
   bool   orValid;
   datetime orEnd;

   CSetupC(void): orHigh(0), orLow(0), orValid(false), orEnd(0) {}

   //--- build the opening range for the session that just opened ------
   void BuildOR(CMarketContext &ctx,CSessionFilter &sess,const datetime now)
     {
      orValid=false; orHigh=-DBL_MAX; orLow=DBL_MAX;

      datetime open=0;
      if(sess.IsNewYork(now) && InpTradeNewYork) open=sess.SessionOpen(now,InpNewYorkStartHour);
      else if(sess.IsLondon(now) && InpTradeLondon) open=sess.SessionOpen(now,InpLondonStartHour);
      if(open==0) return;

      orEnd = open + InpORMinutes*60;
      if(now < orEnd) return;                 // range still forming

      int counted=0;
      for(int i=1;i<ctx.bars;i++)
        {
         datetime bt=ctx.rates[i].time;
         if(bt>=orEnd) continue;
         if(bt<open) break;
         orHigh=MathMax(orHigh,ctx.rates[i].high);
         orLow =MathMin(orLow ,ctx.rates[i].low);
         counted++;
        }
      orValid = (counted>=1 && orHigh>orLow);
     }

   bool Evaluate(CMarketContext &ctx,CStructure &st,CDisplacement &disp,
                 CVolumeProfile &vp,CVWAP &vwap,CRiskManager &rm,
                 CSessionFilter &sess,const datetime now,
                 const bool tryLong,TradeSignal &sig)
     {
      ZeroSignal(sig);
      if(!InpEnableSetupC) return false;

      BuildOR(ctx,sess,now);
      if(!orValid) return false;

      double a=ctx.ATR(1);
      if(a<=0.0) return false;
      double px=ctx.rates[1].close;
      double orSize=orHigh-orLow;

      // 1. Breakout beyond the range
      double level = tryLong ? orHigh : orLow;
      if(tryLong  && px <= level) return false;
      if(!tryLong && px >= level) return false;

      // 2. ATR expansion - the breakout bar must be meaningfully large
      if(MathAbs(px-level) < InpORMinExpansionATR*a) return false;

      // 3. Volume expansion vs the range's own average
      if(InpAblVolumeProfile)
        {
         double sum=0.0; int n=0;
         for(int i=2;i<=10 && i<ctx.bars;i++) { sum+=(double)ctx.rates[i].tick_volume; n++; }
         double avg = (n>0)?sum/n:0.0;
         if(avg>0.0 && (double)ctx.rates[1].tick_volume < avg*1.2) return false;
        }

      // 4. Structure break confirming the expansion
      StructureEvent mss;
      if(!st.DetectMSS(ctx,tryLong,MathMin(InpRetestMaxBars,ctx.bars-1),mss)) return false;

      // 5. Displacement
      int dBar=0;
      if(!disp.FoundRecently(ctx,tryLong,mss.barIndex,dBar)) return false;

      // 6. Retest of the range edge - never enter on the breakout alone
      if(!RetestSatisfied(ctx,tryLong,level,InpRetestMaxBars,a)) return false;

      // 7. Stop on the far side of the opening range edge
      double structureLevel = tryLong ? orLow+orSize*0.5 : orHigh-orSize*0.5;
      if(tryLong)  structureLevel=MathMin(structureLevel,level-0.1*a);
      else         structureLevel=MathMax(structureLevel,level+0.1*a);

      double slDist=rm.StopDistance(px,structureLevel,a);
      if(slDist<=0.0) return false;

      sig.valid=true; sig.setup=SETUP_C; sig.isLong=tryLong;
      sig.entry=px;
      sig.sl = tryLong ? px-slDist : px+slDist;
      sig.riskDistance=slDist;
      rm.BuildTargets(tryLong,px,slDist,sig.tp[0],sig.tp[1],sig.tp[2]);
      sig.atr=a; sig.mss=true; sig.displacement=true; sig.liqLevel=level;
      sig.vwap=vwap.valid?vwap.value:0.0;
      sig.poc=vp.valid?vp.poc:0.0; sig.vah=vp.valid?vp.vah:0.0; sig.val=vp.valid?vp.val:0.0;
      sig.reason=StringFormat("C:OR breakout %.2f + retest",level);
      return true;
     }
  };
#endif
