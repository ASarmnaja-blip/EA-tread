//+------------------------------------------------------------------+
//| RiskGuards.mqh - MODULE 14 (daily) + MODULE 15 (drawdown)         |
//| Protection only. These never create trades and never size up.     |
//+------------------------------------------------------------------+
#ifndef XAUM15_GUARDS_MQH
#define XAUM15_GUARDS_MQH
#include "Config.mqh"

class CDailyRisk
  {
public:
   datetime dayStamp;
   double   dayStartEquity;
   double   dayPeakEquity;
   int      tradesToday;       // setups opened today
   bool     targetHit;
   bool     lossHit;

   CDailyRisk(void): dayStamp(0), dayStartEquity(0), dayPeakEquity(0),
                     tradesToday(0), targetHit(false), lossHit(false) {}

   //--- broker-day rollover -------------------------------------------
   void Update(const datetime now,const double equity)
     {
      datetime day = now - (now % 86400);
      if(day!=dayStamp)
        {
         dayStamp=day;
         dayStartEquity=equity;
         dayPeakEquity=equity;
         tradesToday=0;
         targetHit=false;
         lossHit=false;
        }
      if(equity>dayPeakEquity) dayPeakEquity=equity;

      if(!InpUseDailyLimits) { targetHit=false; lossHit=false; return; }
      double pl=PLPercent(equity);
      if(pl>= InpDailyProfitTarget) targetHit=true;
      if(pl<=-InpDailyLossLimit)    lossHit=true;
     }

   double PLPercent(const double equity) const
     {
      if(dayStartEquity<=0.0) return 0.0;
      return 100.0*(equity-dayStartEquity)/dayStartEquity;
     }
   double DDPercent(const double equity) const
     {
      if(dayPeakEquity<=0.0) return 0.0;
      return 100.0*(dayPeakEquity-equity)/dayPeakEquity;
     }

   bool BlocksNewTrades(string &why) const
     {
      if(targetHit) { why=StringFormat("daily target +%.2f%% reached",InpDailyProfitTarget); return true; }
      if(lossHit)   { why=StringFormat("daily loss -%.2f%% reached",InpDailyLossLimit);      return true; }
      if(tradesToday>=InpMaxTradesPerDay)
        { why=StringFormat("max %d setups/day",InpMaxTradesPerDay); return true; }
      return false;
     }
  };

class CDrawdownGuard
  {
private:
   string m_gvName;

public:
   double peakEquity;
   double currentDD;
   bool   stopped;
   bool   closeAllRequested;
   int    breachedLevel;      // 0 none, 1..5

   CDrawdownGuard(void): peakEquity(0), currentDD(0), stopped(false),
                         closeAllRequested(false), breachedLevel(0) {}

   //--- peak survives terminal restarts via a global variable ---------
   void Init(const long magic,const double equity)
     {
      m_gvName=StringFormat("XAUM15_PEAK_%I64d",magic);
      if(!MQLInfoInteger(MQL_TESTER) && GlobalVariableCheck(m_gvName))
         peakEquity=GlobalVariableGet(m_gvName);
      if(peakEquity<=0.0) peakEquity=equity;
     }

   void Persist(void)
     {
      if(!MQLInfoInteger(MQL_TESTER))
         GlobalVariableSet(m_gvName,peakEquity);
     }

   ENUM_DD_ACTION ActionFor(const int level) const
     {
      switch(level)
        {
         case 1: return InpDDAction1;
         case 2: return InpDDAction2;
         case 3: return InpDDAction3;
         case 4: return InpDDActionPreferred;
         case 5: return InpDDActionEmergency;
        }
      return DD_NOTHING;
     }

   void Update(const double equity)
     {
      if(equity>peakEquity) { peakEquity=equity; Persist(); }
      currentDD = (peakEquity>0.0) ? 100.0*(peakEquity-equity)/peakEquity : 0.0;

      int lvl=0;
      if(currentDD>=InpDD_Level1)    lvl=1;
      if(currentDD>=InpDD_Level2)    lvl=2;
      if(currentDD>=InpDD_Level3)    lvl=3;
      if(currentDD>=InpDD_Preferred) lvl=4;
      if(currentDD>=InpDD_Emergency) lvl=5;
      breachedLevel=lvl;

      ENUM_DD_ACTION act=ActionFor(lvl);
      if(act==DD_STOP_NEW)            stopped=true;
      if(act==DD_CLOSE_ALL_AND_STOP) { stopped=true; closeAllRequested=true; }
     }

   bool BlocksNewTrades(string &why) const
     {
      if(stopped)
        { why=StringFormat("drawdown %.2f%% (level %d) - EA halted",currentDD,breachedLevel); return true; }
      return false;
     }
  };
#endif
