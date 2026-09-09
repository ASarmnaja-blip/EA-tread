//+------------------------------------------------------------------+
//| Broker.mqh - symbol specification cache + execution safety        |
//| Spec 26: every order validated against broker constraints.        |
//+------------------------------------------------------------------+
#ifndef XAUM15_BROKER_MQH
#define XAUM15_BROKER_MQH

#include <Trade/Trade.mqh>
#include "Config.mqh"

class CBroker
  {
public:
   string            symbol;
   int               digits;
   double            point;
   double            tickSize;
   double            tickValue;
   double            contractSize;
   double            lotMin, lotMax, lotStep;
   int               stopsLevelPts;
   int               freezeLevelPts;
   CTrade            trade;
   int               lastRetcode;
   string            lastError;

                     CBroker(void): lastRetcode(0), lastError("") {}

   bool Init(const string sym, const long magic, const int slippage)
     {
      symbol = sym;
      if(!SymbolSelect(symbol,true))
        { lastError="SymbolSelect failed for "+symbol; return false; }

      digits        = (int)SymbolInfoInteger(symbol,SYMBOL_DIGITS);
      point         = SymbolInfoDouble(symbol,SYMBOL_POINT);
      tickSize      = SymbolInfoDouble(symbol,SYMBOL_TRADE_TICK_SIZE);
      tickValue     = SymbolInfoDouble(symbol,SYMBOL_TRADE_TICK_VALUE);
      contractSize  = SymbolInfoDouble(symbol,SYMBOL_TRADE_CONTRACT_SIZE);
      lotMin        = SymbolInfoDouble(symbol,SYMBOL_VOLUME_MIN);
      lotMax        = SymbolInfoDouble(symbol,SYMBOL_VOLUME_MAX);
      lotStep       = SymbolInfoDouble(symbol,SYMBOL_VOLUME_STEP);
      stopsLevelPts = (int)SymbolInfoInteger(symbol,SYMBOL_TRADE_STOPS_LEVEL);
      freezeLevelPts= (int)SymbolInfoInteger(symbol,SYMBOL_TRADE_FREEZE_LEVEL);

      // Edge case: some brokers report 0 tick size/value until first tick.
      if(tickSize<=0.0)  tickSize  = point;
      if(point<=0.0)     { lastError="point==0"; return false; }
      if(tickValue<=0.0) { lastError="tickValue==0 (symbol not ready)"; return false; }
      if(lotStep<=0.0)   lotStep = 0.01;

      trade.SetExpertMagicNumber(magic);
      trade.SetDeviationInPoints(slippage);
      trade.SetTypeFillingBySymbol(symbol);
      trade.LogLevel(LOG_LEVEL_ERRORS);
      return true;
     }

   double Ask(void) const { return SymbolInfoDouble(symbol,SYMBOL_ASK); }
   double Bid(void) const { return SymbolInfoDouble(symbol,SYMBOL_BID); }
   double Spread(void) const { return Ask()-Bid(); }

   double NormPrice(const double p) const { return NormalizeDouble(p,digits); }

   //--- clamp volume to broker grid ---------------------------------
   double NormLot(const double vol) const
     {
      if(lotStep<=0.0) return 0.0;
      double v = MathFloor(vol/lotStep+1e-8)*lotStep;
      v = MathMax(v,lotMin);
      v = MathMin(v,lotMax);
      return NormalizeDouble(v,2);
     }

   //--- money risked by `lot` over `priceDistance` -------------------
   double RiskMoney(const double lot,const double priceDistance) const
     {
      if(tickSize<=0.0) return 0.0;
      return lot*(priceDistance/tickSize)*tickValue;
     }

   //--- lot required to risk `money` over `priceDistance` ------------
   double LotForRisk(const double money,const double priceDistance) const
     {
      if(priceDistance<=0.0 || tickValue<=0.0 || tickSize<=0.0) return 0.0;
      double perLot = (priceDistance/tickSize)*tickValue;
      if(perLot<=0.0) return 0.0;
      return money/perLot;
     }

   //--- Spec 26: SL/TP must respect stops level ----------------------
   bool StopsAreValid(const bool isLong,const double entry,
                      const double sl,const double tp) const
     {
      double minDist = stopsLevelPts*point;
      if(minDist<=0.0) minDist = point; // still require non-zero separation
      if(isLong)
        {
         if(entry-sl < minDist) return false;
         if(tp>0.0 && tp-entry < minDist) return false;
        }
      else
        {
         if(sl-entry < minDist) return false;
         if(tp>0.0 && entry-tp < minDist) return false;
        }
      return true;
     }

   //--- widen stops to the broker minimum rather than failing --------
   void EnforceStopsLevel(const bool isLong,const double entry,
                          double &sl,double &tp) const
     {
      double minDist = stopsLevelPts*point;
      if(minDist<=0.0) return;
      if(isLong)
        {
         if(entry-sl < minDist)      sl = NormalizeDouble(entry-minDist,digits);
         if(tp>0.0 && tp-entry<minDist) tp = NormalizeDouble(entry+minDist,digits);
        }
      else
        {
         if(sl-entry < minDist)      sl = NormalizeDouble(entry+minDist,digits);
         if(tp>0.0 && entry-tp<minDist) tp = NormalizeDouble(entry-minDist,digits);
        }
     }

   //--- margin pre-check --------------------------------------------
   bool HasMargin(const ENUM_ORDER_TYPE type,const double lot,const double price) const
     {
      double need=0.0;
      if(!OrderCalcMargin(type,symbol,lot,price,need)) return false;
      return (AccountInfoDouble(ACCOUNT_MARGIN_FREE) > need*1.20);
     }

   //--- bounded retry (spec 26: never retry indefinitely) ------------
   bool Open(const bool isLong,const double lot,const double sl,const double tp,
             const string comment)
     {
      if(lot<=0.0) { lastError="lot<=0"; return false; }
      ENUM_ORDER_TYPE ot = isLong?ORDER_TYPE_BUY:ORDER_TYPE_SELL;

      for(int attempt=0; attempt<InpMaxOrderRetries; attempt++)
        {
         double price = isLong?Ask():Bid();
         if(!HasMargin(ot,lot,price))
           { lastError="insufficient margin"; lastRetcode=TRADE_RETCODE_NO_MONEY; return false; }

         double s=sl, t=tp;
         EnforceStopsLevel(isLong,price,s,t);

         bool ok = isLong ? trade.Buy (lot,symbol,price,s,t,comment)
                          : trade.Sell(lot,symbol,price,s,t,comment);
         lastRetcode = (int)trade.ResultRetcode();

         if(ok && (lastRetcode==TRADE_RETCODE_DONE ||
                   lastRetcode==TRADE_RETCODE_PLACED ||
                   lastRetcode==TRADE_RETCODE_DONE_PARTIAL))
            return true;

         // Retry only on transient conditions.
         if(lastRetcode==TRADE_RETCODE_REQUOTE  ||
            lastRetcode==TRADE_RETCODE_PRICE_OFF||
            lastRetcode==TRADE_RETCODE_PRICE_CHANGED ||
            lastRetcode==TRADE_RETCODE_TIMEOUT)
           {
            Sleep(InpRetryDelayMs);
            continue;
           }
         break; // permanent rejection - do not hammer the server
        }
      lastError = StringFormat("open failed rc=%d (%s)",lastRetcode,trade.ResultRetcodeDescription());
      return false;
     }

   bool ModifySL(const ulong ticket,const double newSL)
     {
      if(!PositionSelectByTicket(ticket)) return false;
      double tp = PositionGetDouble(POSITION_TP);
      double cur= PositionGetDouble(POSITION_SL);
      if(MathAbs(cur-newSL) < point) return true; // already there

      // Freeze level: broker forbids modification too close to market.
      double frz = freezeLevelPts*point;
      if(frz>0.0)
        {
         long ptype = PositionGetInteger(POSITION_TYPE);
         double mkt = (ptype==POSITION_TYPE_BUY)?Bid():Ask();
         if(MathAbs(mkt-newSL) < frz) return false;
        }
      bool ok = trade.PositionModify(ticket,NormalizeDouble(newSL,digits),tp);
      lastRetcode=(int)trade.ResultRetcode();
      return ok;
     }

   bool ClosePosition(const ulong ticket)
     {
      bool ok = trade.PositionClose(ticket,InpSlippagePoints);
      lastRetcode=(int)trade.ResultRetcode();
      return ok;
     }
  };

#endif // XAUM15_BROKER_MQH
