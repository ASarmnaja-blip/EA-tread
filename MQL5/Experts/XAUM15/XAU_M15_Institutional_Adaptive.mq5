//+------------------------------------------------------------------+
//|            XAU M15 Institutional Adaptive EA                      |
//|                                                                   |
//| XAU/USD - primary timeframe M15.                                  |
//|                                                                   |
//| DESIGN CONTRACT (spec 1, 22, 37, 40):                             |
//|  - No martingale, no grid, no recovery lot, no risk increase      |
//|    after a loss, no lot increase to chase a daily target.         |
//|  - The daily profit target is a STOP-TRADING mechanism, never a   |
//|    quota that forces the EA to find trades.                       |
//|  - A day with no qualifying setup is a valid outcome: the EA is   |
//|    expected to sit flat rather than manufacture an entry.         |
//|  - Every module has one job (spec 37). Nothing is a voting pool   |
//|    of redundant oscillators.                                      |
//|                                                                   |
//| No performance figure is promised. Backtest, forward test and     |
//| expected performance are different things and must not be mixed.  |
//+------------------------------------------------------------------+
#property copyright "XAU M15 Institutional Adaptive"
#property version   "1.00"
#property description "XAU/USD M15 modular EA: session/news/regime gating, liquidity"
#property description "sweep + MSS + displacement entries, 3 independent TP legs,"
#property description "equity-based sizing, daily and drawdown protection."

#include <XAUM15/Config.mqh>
#include <XAUM15/Broker.mqh>
#include <XAUM15/SessionFilter.mqh>
#include <XAUM15/NewsFilter.mqh>
#include <XAUM15/Regime.mqh>
#include <XAUM15/Structure.mqh>
#include <XAUM15/Liquidity.mqh>
#include <XAUM15/Sweep.mqh>
#include <XAUM15/Displacement.mqh>
#include <XAUM15/VolumeProfile.mqh>
#include <XAUM15/VWAP.mqh>
#include <XAUM15/AMD.mqh>
#include <XAUM15/RiskManager.mqh>
#include <XAUM15/RiskGuards.mqh>
#include <XAUM15/Setups.mqh>
#include <XAUM15/Quality.mqh>
#include <XAUM15/TradeManager.mqh>
#include <XAUM15/Statistics.mqh>
#include <XAUM15/Logger.mqh>
#include <XAUM15/Dashboard.mqh>
#include <XAUM15/SpreadMonitor.mqh>

//--- module instances -----------------------------------------------
CBroker         g_broker;
CSessionFilter  g_session;
CNewsFilter     g_news;
CMarketContext  g_ctx;
CStructure      g_structure;
CLiquidityMap   g_liquidity;
CSweepDetector  g_sweep;
CDisplacement   g_disp;
CVolumeProfile  g_vp;
CVWAP           g_vwap;
CAMD            g_amd;
CRiskManager    g_risk;
CDailyRisk      g_daily;
CDrawdownGuard  g_ddGuard;
CSetupA         g_setupA;
CSetupB         g_setupB;
CSetupC         g_setupC;
CSetupTrendZone g_setupD;
CQualityGrader  g_quality;
CTradeManager   g_tm;
CStatistics     g_stats;
CTradeLogger    g_logger;
CDashboard      g_dash;
CSpreadMonitor  g_spread;

//--- runtime state ---------------------------------------------------
datetime g_lastBarTime      = 0;
datetime g_lastEntryBarTime = 0;      // spec 27: one order per candle
datetime g_cooldownUntil    = 0;
string   g_statusText       = "INIT";
string   g_blockReason      = "";
TradeSignal g_lastSignal;
datetime g_setupOpenTime    = 0;
string   g_setupOpenSession = "";

//+------------------------------------------------------------------+
int OnInit(void)
  {
   if(_Period!=PERIOD_M15)
      PrintFormat("[WARN] designed for M15; running on %s",EnumToString((ENUM_TIMEFRAMES)_Period));

   if(!g_broker.Init(_Symbol,InpMagicBase,InpSlippagePoints))
     { PrintFormat("[INIT] broker init failed: %s",g_broker.lastError); return INIT_FAILED; }

   if(!g_ctx.Init(_Symbol,PERIOD_M15))
     { Print("[INIT] indicator handles failed"); return INIT_FAILED; }

   g_news.Init();
   g_tm.Attach(&g_broker);

   double eq=AccountInfoDouble(ACCOUNT_EQUITY);
   g_daily.Update(TimeCurrent(),eq);
   g_ddGuard.Init(InpMagicBase,eq);
   g_stats.Init(eq);
   g_logger.Init(InpTradeLogFile);
   ZeroSignal(g_lastSignal);

   PrintFormat("[INIT] %s | digits=%d point=%.5f tickVal=%.5f lotMin=%.2f step=%.2f stops=%d",
               _Symbol,g_broker.digits,g_broker.point,g_broker.tickValue,
               g_broker.lotMin,g_broker.lotStep,g_broker.stopsLevelPts);
   PrintFormat("[INIT] equity %.2f | risk %.2f%%/setup | %d legs | daily +%.1f%%/-%.1f%% | DD stop %.0f%%",
               eq,InpRiskPercent,InpPositionsPerSetup,
               InpDailyProfitTarget,InpDailyLossLimit,InpDD_Preferred);
   ReportCapitalAdequacy(eq);
   return INIT_SUCCEEDED;
  }

//+------------------------------------------------------------------+
void OnDeinit(const int reason)
  {
   if(InpPrintStatsOnDeinit)
     {
      g_stats.PrintReport();
      g_spread.PrintReport(InpTrendSLATR*g_ctx.ATR(1));
      g_spread.WriteCsv("XAUM15_spread_by_hour.csv");
     }
   g_logger.Close();
   g_dash.Destroy();
   g_ctx.Deinit();
  }

//+------------------------------------------------------------------+
//| Is the account large enough for the stop this market implies?      |
//|                                                                    |
//| The broker minimum lot cannot shrink. When it forces a risk larger  |
//| than the configured cap, the EA will reject setups rather than      |
//| over-risk - so the operator needs to see that before it happens,    |
//| not after a week of silence.                                        |
//+------------------------------------------------------------------+
void ReportCapitalAdequacy(const double equity)
  {
   double atr=0.0;
   int h=iATR(_Symbol,PERIOD_M15,InpAtrPeriod);
   if(h!=INVALID_HANDLE)
     {
      double buf[]; ArraySetAsSeries(buf,true);
      if(CopyBuffer(h,0,0,3,buf)>0) atr=buf[1];
      IndicatorRelease(h);
     }
   if(atr<=0.0) { Print("[CAPITAL] ATR not available yet - check again after the first bars"); return; }

   double slDist  = (InpSLMode==SL_FIXED_ATR) ? InpTrendSLATR*atr
                                              : (InpMinSLATR+InpSLBufferATR)*atr;
   double minRisk = g_broker.RiskMoney(g_broker.lotMin,slDist)*MathMax(1,InpPositionsPerSetup);
   double minPct  = (equity>0.0) ? 100.0*minRisk/equity : 0.0;
   double needEq  = (InpRiskPercent>0.0) ? minRisk/(InpRiskPercent/100.0) : 0.0;

   Print("---------------- CAPITAL ADEQUACY ----------------");
   PrintFormat("ATR(M15)            : %.2f",atr);
   PrintFormat("Stop distance       : %.2f  (%s)",slDist,
               InpSLMode==SL_FIXED_ATR?"fixed ATR":"structure + buffer");
   PrintFormat("Minimum-lot risk    : %.2f  = %.2f%% of equity",minRisk,minPct);
   PrintFormat("Target risk         : %.2f%%   -> needs equity %.2f",InpRiskPercent,needEq);

   if(minPct > InpMaxRiskPercent)
      PrintFormat("[CAPITAL] WARNING: minimum lot risks %.2f%%, above the %.2f%% cap. "
                  "Setups will be REJECTED until equity reaches ~%.2f.",
                  minPct,InpMaxRiskPercent,needEq);
   else if(minPct > InpRiskPercent*1.5)
      PrintFormat("[CAPITAL] NOTE: minimum lot risks %.2f%%, well above the %.2f%% target. "
                  "Position sizing cannot go finer than this.",minPct,InpRiskPercent);

   if(InpUseDailyLimits && minPct>0.0)
     {
      double lossesToStop=InpDailyLossLimit/minPct;
      PrintFormat("Daily loss limit    : -%.2f%%  = %.1f losing trades",
                  InpDailyLossLimit,lossesToStop);
      if(lossesToStop<3.0)
         PrintFormat("[CAPITAL] WARNING: the daily loss limit stops trading after only "
                     "%.1f losses. A long-tail system with a low win rate will spend most "
                     "days halted. Consider InpUseDailyLimits=false or more equity.",
                     lossesToStop);
     }
   Print("-------------------------------------------------");
  }

//+------------------------------------------------------------------+
bool IsNewBar(void)
  {
   datetime t=iTime(_Symbol,PERIOD_M15,0);
   if(t==0) return false;
   if(t!=g_lastBarTime) { g_lastBarTime=t; return true; }
   return false;
  }

int SessionIndex(const datetime t)
  {
   if(g_session.IsOverlap(t)) return 3;
   if(g_session.IsLondon(t))  return 1;
   if(g_session.IsNewYork(t)) return 2;
   if(g_session.IsAsian(t))   return 0;
   return 1;
  }

//+------------------------------------------------------------------+
//| Realised profit of the finished setup, read from deal history     |
//+------------------------------------------------------------------+
double SetupRealisedProfit(const ENUM_SETUP_ID setup,const datetime from)
  {
   double total=0.0;
   if(!HistorySelect(from-60,TimeCurrent()+60)) return 0.0;
   for(int i=HistoryDealsTotal()-1;i>=0;i--)
     {
      ulong d=HistoryDealGetTicket(i);
      if(d==0) continue;
      if(HistoryDealGetString(d,DEAL_SYMBOL)!=_Symbol) continue;
      long magic=HistoryDealGetInteger(d,DEAL_MAGIC);
      bool mine=false;
      for(int leg=0;leg<3;leg++)
         if(magic==g_tm.LegMagic(InpMagicBase,setup,leg)) { mine=true; break; }
      if(!mine) continue;
      if(HistoryDealGetInteger(d,DEAL_ENTRY)!=DEAL_ENTRY_OUT) continue;
      total += HistoryDealGetDouble(d,DEAL_PROFIT)
             + HistoryDealGetDouble(d,DEAL_SWAP)
             + HistoryDealGetDouble(d,DEAL_COMMISSION);
     }
   return total;
  }

//+------------------------------------------------------------------+
//| A finished setup is booked exactly once                            |
//+------------------------------------------------------------------+
void FinaliseSetupIfClosed(void)
  {
   if(!g_tm.hasOpenSetup) return;
   if(g_tm.AliveCount()>0) return;

   ENUM_SETUP_ID setup=g_tm.current.setup;
   double profit=SetupRealisedProfit(setup,g_setupOpenTime);

   double riskMoney = g_broker.RiskMoney(g_tm.current.lot,g_tm.current.riskDistance)
                    * MathMax(1,g_tm.current.legs);
   double r = (riskMoney>0.0) ? profit/riskMoney : 0.0;
   double durationMin = (double)(TimeCurrent()-g_setupOpenTime)/60.0;

   MqlDateTime dt; TimeToStruct(g_setupOpenTime,dt);
   g_stats.Record(setup,g_tm.current.isLong,SessionIndex(g_setupOpenTime),
                  dt.hour,profit,r,durationMin);

   g_logger.Write(g_setupOpenTime,g_setupOpenSession,
                  CTradeManager::SetupName(setup),
                  g_tm.current.isLong?"LONG":"SHORT",
                  g_tm.current.entry,g_tm.current.sl,
                  g_tm.current.tp[0],g_tm.current.tp[1],g_tm.current.tp[2],
                  100.0*riskMoney/MathMax(1.0,g_stats.startEquity),
                  g_tm.current.lot,g_tm.current.legs,
                  g_lastSignal.spread,g_lastSignal.atr,g_lastSignal.vwap,
                  g_lastSignal.poc,g_lastSignal.vah,g_lastSignal.val,
                  g_lastSignal.liqLevel,
                  g_lastSignal.sweepType==SWEEP_HIGH?"HIGH":
                    (g_lastSignal.sweepType==SWEEP_LOW?"LOW":"NONE"),
                  g_lastSignal.mss,g_lastSignal.displacement,
                  CQualityGrader::Name(g_tm.current.quality),
                  profit,r,g_tm.current.mae,g_tm.current.mfe,durationMin);

   // Spec 27: cooldown measured in M15 candles, longer after a loss.
   int cd = (profit<0.0) ? InpCooldownBarsLoss : InpCooldownBarsWin;
   if(cd>0) g_cooldownUntil = TimeCurrent() + cd*PeriodSeconds(PERIOD_M15);

   PrintFormat("[SETUP %s] closed %s profit=%.2f R=%.3f dur=%.0fmin",
               CTradeManager::SetupName(setup),
               g_tm.current.isLong?"LONG":"SHORT",profit,r,durationMin);

   g_tm.Reset();
  }

//+------------------------------------------------------------------+
//| Veto chain - every gate can only BLOCK, never create a trade       |
//+------------------------------------------------------------------+
bool EntryGatesPass(const datetime now,string &why)
  {
   if(!InpEnableTrading)                 { why="trading disabled";      return false; }
   if(g_ddGuard.BlocksNewTrades(why))                                   return false;
   if(g_daily.BlocksNewTrades(why))                                     return false;
   if(now < g_cooldownUntil)             { why="cooldown after trade";  return false; }
   if(g_tm.hasOpenSetup && InpMaxConcurrentSetups<=1)
                                         { why="setup already open";    return false; }
   if(!g_session.EntryAllowed(now,why))                                 return false;
   if(g_news.IsBlocked(now))             { why="news: "+g_news.lastBlockingEvent; return false; }

   double spread=g_broker.Spread();
   if(spread > InpMaxSpread+InpSpreadBuffer)
     { why=StringFormat("spread %.2f > max %.2f",spread,InpMaxSpread); return false; }

   if(g_ctx.TradingBlockedByRegime(why))                                return false;

   if(g_lastEntryBarTime==g_lastBarTime) { why="already traded this bar"; return false; }
   return true;
  }

//+------------------------------------------------------------------+
//| Setups are evaluated INDEPENDENTLY (spec 16). If more than one     |
//| qualifies, the higher grade wins; ties break A > B > C. No score   |
//| is ever pooled across setups.                                      |
//+------------------------------------------------------------------+
bool CollectSignal(const datetime now,TradeSignal &best)
  {
   ZeroSignal(best);
   TradeSignal cand;
   double spread=g_broker.Spread();
   bool found=false;

   for(int dir=0;dir<2;dir++)
     {
      bool isLong=(dir==0);

      if(g_setupA.Evaluate(g_ctx,g_structure,g_liquidity,g_sweep,g_disp,
                           g_vp,g_vwap,g_amd,g_risk,isLong,cand))
        {
         cand.quality=g_quality.Grade(g_ctx,g_vp,g_vwap,g_amd,g_session,now,spread,cand);
         cand.spread=spread;
         if(g_quality.Allowed(cand.quality) && (!found || cand.quality>best.quality))
           { best=cand; found=true; }
        }

      if(g_setupB.Evaluate(g_ctx,g_structure,g_disp,g_vp,g_vwap,g_risk,isLong,cand))
        {
         cand.quality=g_quality.Grade(g_ctx,g_vp,g_vwap,g_amd,g_session,now,spread,cand);
         cand.spread=spread;
         if(g_quality.Allowed(cand.quality) && (!found || cand.quality>best.quality))
           { best=cand; found=true; }
        }

      if(g_setupC.Evaluate(g_ctx,g_structure,g_disp,g_vp,g_vwap,g_risk,
                           g_session,now,isLong,cand))
        {
         cand.quality=g_quality.Grade(g_ctx,g_vp,g_vwap,g_amd,g_session,now,spread,cand);
         cand.spread=spread;
         if(g_quality.Allowed(cand.quality) && (!found || cand.quality>best.quality))
           { best=cand; found=true; }
        }

      // Setup D deliberately bypasses the quality grader. The research
      // found that every added confluence filter reduced expectancy; the
      // six-line rule is the whole edge and grading it would re-introduce
      // exactly the selection the evidence rejected.
      if(g_setupD.Evaluate(g_ctx,g_vwap,g_vp,g_risk,isLong,cand))
        {
         cand.quality=Q_APLUS;
         cand.spread=spread;
         if(!found) { best=cand; found=true; }
        }
     }
   return found;
  }

//+------------------------------------------------------------------+
void TryEnter(const datetime now)
  {
   TradeSignal sig;
   if(!CollectSignal(now,sig)) { g_blockReason="no qualifying setup"; return; }

   // The signal was formed on the closed bar; size against the price we
   // will actually be filled at, so risk% reflects the real fill.
   double live = sig.isLong ? g_broker.Ask() : g_broker.Bid();
   if(live>0.0)
     {
      double d = MathAbs(live-sig.sl);
      if(d<=0.0) { g_blockReason="stop on the wrong side of price"; return; }
      if(sig.isLong && sig.sl>=live)  { g_blockReason="stale long signal"; return; }
      if(!sig.isLong && sig.sl<=live) { g_blockReason="stale short signal"; return; }
      sig.entry=live;
      sig.riskDistance=d;
      g_risk.BuildTargets(sig.isLong,live,d,sig.tp[0],sig.tp[1],sig.tp[2]);
     }

   double equity=AccountInfoDouble(ACCOUNT_EQUITY);
   SizingResult sz=g_risk.Size(g_broker,equity,sig.riskDistance);
   if(!sz.ok)
     {
      g_blockReason="sizing: "+sz.reason;
      if(InpVerboseLog) PrintFormat("[SIZE] rejected: %s",sz.reason);
      return;
     }
   if(sz.reason!="" && InpVerboseLog) PrintFormat("[SIZE] %s",sz.reason);

   // Final broker-side validation before committing.
   if(!g_broker.StopsAreValid(sig.isLong,sig.entry,sig.sl,sig.tp[0]))
     { g_blockReason="stops too close to market"; return; }

   g_setupOpenTime    = now;
   g_setupOpenSession = g_session.Name(now);
   g_lastSignal       = sig;

   if(g_tm.OpenSetup(sig,sz.lot,sz.positions,InpMagicBase))
     {
      g_lastEntryBarTime=g_lastBarTime;
      g_daily.tradesToday++;
      PrintFormat("[ENTRY] %s %s %s | entry %.2f SL %.2f (%.2f) | %d x %.2f lot | risk %.3f%% | %s",
                  CTradeManager::SetupName(sig.setup),
                  sig.isLong?"LONG":"SHORT",
                  CQualityGrader::Name(sig.quality),
                  sig.entry,sig.sl,sig.riskDistance,
                  sz.positions,sz.lot,sz.riskPercent,sig.reason);
      g_blockReason="";
     }
   else
      g_blockReason="order rejected: "+g_broker.lastError;
  }

//+------------------------------------------------------------------+
void RefreshContext(const datetime now)
  {
   if(!g_ctx.Refresh(InpVPLookbackBars+InpEmaSlow+50)) return;

   g_structure.Detect(g_ctx);
   g_liquidity.Build(g_ctx,g_structure,g_session,now);
   g_amd.Evaluate(g_ctx,g_liquidity,g_session,now);

   if(InpUseVWAP)
     {
      datetime sStart = g_session.IsNewYork(now)
                      ? g_session.SessionOpen(now,InpNewYorkStartHour)
                      : (g_session.IsLondon(now)
                         ? g_session.SessionOpen(now,InpLondonStartHour)
                         : g_session.AsianStart(now));
      g_vwap.Calculate(g_ctx,sStart);
     }

   if(InpUseVolumeProfile)
     {
      g_vp.ResolveSourceName(g_ctx);
      g_vp.Build(g_ctx,1,InpVPLookbackBars);
     }

   g_news.RefreshCalendar(now);
  }

//+------------------------------------------------------------------+
void UpdateDashboard(const datetime now)
  {
   if(!InpShowDashboard) return;

   double eq=AccountInfoDouble(ACCOUNT_EQUITY);
   string status = g_ddGuard.stopped ? "HALTED (DD)"
                 : (!InpEnableTrading ? "DISABLED"
                 : (g_daily.targetHit ? "DAILY TARGET"
                 : (g_daily.lossHit   ? "DAILY LOSS"
                 : (g_tm.hasOpenSetup ? "IN TRADE" : "TRADING"))));

   string activeSetup = g_tm.hasOpenSetup
                      ? CTradeManager::SetupName(g_tm.current.setup)
                      : (g_blockReason==""?"scanning":g_blockReason);

   string bias = (g_ctx.regime==REG_TREND_UP)   ? "BULLISH"
               : (g_ctx.regime==REG_TREND_DOWN) ? "BEARISH" : "NEUTRAL";

   g_dash.Render(status,g_session.Name(now),g_ctx.RegimeName(),g_amd.PhaseName(),
                 g_broker.Bid(),g_broker.Spread(),g_ctx.ATR(1),
                 g_vwap.valid?g_vwap.value:0.0,
                 g_vp.valid?g_vp.poc:0.0,g_vp.valid?g_vp.vah:0.0,g_vp.valid?g_vp.val:0.0,
                 g_liquidity.asianHigh,g_liquidity.asianLow,
                 g_liquidity.pdh,g_liquidity.pdl,
                 bias,activeSetup,
                 g_tm.hasOpenSetup?CQualityGrader::Name(g_tm.current.quality):"-",
                 g_tm.hasOpenSetup?g_tm.current.entry:0.0,
                 g_tm.hasOpenSetup?g_tm.current.sl:0.0,
                 g_tm.hasOpenSetup?g_tm.current.tp[0]:0.0,
                 g_tm.hasOpenSetup?g_tm.current.tp[1]:0.0,
                 g_tm.hasOpenSetup?g_tm.current.tp[2]:0.0,
                 InpRiskPercent,
                 g_daily.PLPercent(eq),g_daily.DDPercent(eq),g_ddGuard.currentDD,
                 g_stats.all.WinRate(),g_stats.all.ProfitFactor(),
                 g_stats.all.Expectancy(),g_stats.all.AvgR(),g_stats.all.trades,
                 g_vp.sourceName,
                 g_ctx.TrendZoneScore(1),
                 g_ctx.InTrendZone(true,1)||g_ctx.InTrendZone(false,1));
  }

//+------------------------------------------------------------------+
void OnTick(void)
  {
   datetime now=TimeCurrent();
   double   eq =AccountInfoDouble(ACCOUNT_EQUITY);

   //--- protection runs on EVERY tick, not once per bar --------------
   g_daily.Update(now,eq);
   g_ddGuard.Update(eq);
   g_stats.UpdateEquity(eq);
   g_spread.Sample(now,g_broker.Spread());

   if(g_ddGuard.closeAllRequested && g_tm.hasOpenSetup)
      g_tm.CloseAll("drawdown emergency");

   if(g_daily.lossHit && InpDailyLossAction==DL_CLOSE_ALL && g_tm.hasOpenSetup)
      g_tm.CloseAll("daily loss limit");

   //--- manage what is already open ----------------------------------
   if(g_tm.hasOpenSetup)
     {
      int barsElapsed=(int)((now-g_setupOpenTime)/PeriodSeconds(PERIOD_M15));
      g_tm.Manage(g_ctx.ATR(1),barsElapsed);
     }
   FinaliseSetupIfClosed();

   //--- heavy analysis only on a closed M15 bar ----------------------
   if(IsNewBar())
     {
      RefreshContext(now);

      string why="";
      if(EntryGatesPass(now,why)) TryEnter(now);
      else                        g_blockReason=why;
     }

   UpdateDashboard(now);
  }

//+------------------------------------------------------------------+
//| Book a setup the moment its last leg closes, without waiting for   |
//| the next tick.                                                     |
//+------------------------------------------------------------------+
void OnTradeTransaction(const MqlTradeTransaction &trans,
                        const MqlTradeRequest &request,
                        const MqlTradeResult &result)
  {
   if(trans.type!=TRADE_TRANSACTION_DEAL_ADD) return;
   if(trans.symbol!=_Symbol) return;
   FinaliseSetupIfClosed();
  }

//+------------------------------------------------------------------+
double OnTester(void)
  {
   // Optimisation target: expectancy weighted by trade count, penalised
   // by drawdown. Deliberately NOT net profit (spec 39).
   if(g_stats.all.trades<30) return 0.0;
   double pf=g_stats.all.ProfitFactor();
   double dd=MathMax(1.0,g_stats.maxDDPercent);
   if(g_stats.maxDDPercent>=InpDD_Emergency) return 0.0;
   return g_stats.all.Expectancy()*MathSqrt((double)g_stats.all.trades)*(pf/dd);
  }
//+------------------------------------------------------------------+
