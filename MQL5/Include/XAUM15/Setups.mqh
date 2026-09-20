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
   //--- schema v2 (record only) --------------------------------------
   s.symbol=""; s.timeframe=PERIOD_CURRENT; s.regime=REG_NONE; s.regimeScore=0.0;
   s.confidence=-1.0;                 // -1 = not calibrated
   s.invalidation=0.0; s.invalidationRule="";
   s.expiryBars=-1; s.expiryTime=0;   // -1 = no expiry policy selected
   s.formedAt=0; s.riskR=0.0;
   s.evidence=""; s.pricedIn=""; s.newsRisk="";
   s.decision=""; s.decisionReason="";
  }

//--- Stamp the descriptive half of schema v2 onto a signal that has -----
//    ALREADY been accepted. Called after sig.valid=true so it can never
//    sit on an early-return path and can never change an accept/reject.
//    Everything it writes is inert by construction.
void StampSignalContext(TradeSignal &s,CMarketContext &ctx,const int bar=1)
  {
   s.symbol      = _Symbol;
   s.timeframe   = (ENUM_TIMEFRAMES)_Period;
   s.regime      = ctx.regime;
   s.regimeScore = ctx.TrendZoneScore(bar);
   s.formedAt    = (bar>=0 && bar<ctx.bars) ? ctx.rates[bar].time : 0;
   s.riskR       = 1.0;               // R is the unit; one setup risks 1R
   s.confidence  = -1.0;              // not calibrated - see protocol v2 s.3
   s.expiryBars  = -1;                // no expiry policy adopted yet - s.7
   s.expiryTime  = 0;
   // The news engine does not exist yet (Track 2.4). Saying "none" would
   // be a claim; saying so plainly is not.
   s.pricedIn    = "not assessed: no positioning/consensus feed";
   s.newsRisk    = "not assessed: calendar actual/consensus not wired";
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
      StampSignalContext(sig,ctx);
      sig.invalidation     = ev.extreme;
      sig.invalidationRule = "price re-takes the swept extreme: the reversal "
                             "premise is dead, regardless of the stop";
      sig.evidence         = StringFormat("sweep of %s at %.2f, MSS, displacement",
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
      StampSignalContext(sig,ctx);
      sig.invalidation     = mss.brokenLevel;
      sig.invalidationRule = "price closes back through the broken structure "
                             "level: continuation premise gone";
      sig.evidence         = "value acceptance in trend direction, structure "
                             "break, displacement";
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
      StampSignalContext(sig,ctx);
      sig.invalidation     = level;
      sig.invalidationRule = "price closes back inside the opening range: the "
                             "breakout failed";
      sig.evidence         = StringFormat("opening-range break of %.2f with "
                                          "expansion and retest",level);
      return true;
     }
  };

//====================================================================
// SETUP D - TREND ZONE
//====================================================================
// The whole rule is six lines. That is the point: every elaboration
// tested on top of it made results worse.
//
//   z = (Close - SMA200) / ATR
//   long  when  +1.08 <= z <= +7.21
//   short when  -7.21 <= z <= -1.08
//   stop  = 1.8 x ATR, flat
//   exit  = target at 8R, with a 120-bar (30h) time stop behind it
//   size  = 0.5% of equity, one position
//
// The target scan is monotone out to 8R (Sharpe 0.02 -> 6.36 from 1.5R to
// 8R), so the edge really does live in a long right tail - but it is
// captured with a far target, not by refusing to place one.
//====================================================================
class CSetupTrendZone
  {
public:
   double lastScore;

   CSetupTrendZone(void): lastScore(0.0) {}

   bool Evaluate(CMarketContext &ctx,CVWAP &vwap,CVolumeProfile &vp,
                 CRiskManager &rm,const bool tryLong,TradeSignal &sig)
     {
      ZeroSignal(sig);
      if(!InpEnableSetupD) return false;
      if(tryLong  && !InpTrendZoneLong)  return false;
      if(!tryLong && !InpTrendZoneShort) return false;

      double a=ctx.ATR(1);
      if(a<=0.0) return false;

      lastScore=ctx.TrendZoneScore(1);
      if(!ctx.InTrendZone(tryLong,1)) return false;

      // Fire on ENTERING the zone, not on every bar spent inside it.
      // Without this the EA re-signals continuously and the trade count
      // inflates far beyond the ~254/year the notebook measured.
      if(InpTrendRequireEntry && ctx.InTrendZone(tryLong,2)) return false;

      double px=ctx.rates[1].close;
      double slDist=rm.StopDistance(px,px,a);   // flat ATR stop in SL_FIXED_ATR
      if(slDist<=0.0) return false;

      sig.valid=true; sig.setup=SETUP_D; sig.isLong=tryLong;
      sig.entry=px;
      sig.sl = tryLong ? px-slDist : px+slDist;
      sig.riskDistance=slDist;

      rm.BuildExit(tryLong,px,slDist,sig.tp);

      sig.atr=a;
      sig.vwap=vwap.valid?vwap.value:0.0;
      sig.poc=vp.valid?vp.poc:0.0; sig.vah=vp.valid?vp.vah:0.0; sig.val=vp.valid?vp.val:0.0;
      sig.reason=StringFormat("D:trend zone z=%.2f",lastScore);
      StampSignalContext(sig,ctx);
      // The premise is "z is inside the tested zone". It stops being true
      // at the price where z crosses the near edge.
      double smaNow = (1<ArraySize(ctx.sma)) ? ctx.sma[1] : 0.0;
      if(smaNow>0.0)
        {
         sig.invalidation = tryLong ? smaNow + InpTrendZoneMin*a
                                    : smaNow - InpTrendZoneMin*a;
         sig.invalidationRule = StringFormat(
            "z leaves the zone at the near edge (z=%.2f)",InpTrendZoneMin);
        }
      sig.evidence = StringFormat("(Close-SMA%d)/ATR = %.2f, inside tested "
                                  "zone [%.2f, %.2f]",
                                  InpTrendSmaPeriod,lastScore,
                                  InpTrendZoneMin,InpTrendZoneMax);
      return true;
     }
  };
#endif
