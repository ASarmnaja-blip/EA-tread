//+------------------------------------------------------------------+
//| TradeManager.mqh - MODULE 13                                      |
//| Spec 19: THREE REAL POSITIONS, not one position partially closed. |
//| Spec 20: when TP1 closes, legs 2 and 3 move to break-even.        |
//+------------------------------------------------------------------+
#ifndef XAUM15_TM_MQH
#define XAUM15_TM_MQH
#include "Config.mqh"
#include "Broker.mqh"

struct SetupTicket
  {
   ulong          ticket[3];
   bool           active[3];
   double         entry;
   double         sl;
   double         tp[3];
   bool           isLong;
   ENUM_SETUP_ID  setup;
   ENUM_QUALITY   quality;
   datetime       opened;
   int            legs;
   bool           beApplied;
   double         riskDistance;
   double         lot;
   double         mae, mfe;      // spec 36
  };

class CTradeManager
  {
private:
   CBroker *m_br;

public:
   SetupTicket current;
   bool        hasOpenSetup;

   CTradeManager(void): m_br(NULL), hasOpenSetup(false) { Reset(); }

   void Attach(CBroker *br) { m_br=br; }

   void Reset(void)
     {
      for(int i=0;i<3;i++) { current.ticket[i]=0; current.active[i]=false; current.tp[i]=0; }
      current.entry=0; current.sl=0; current.isLong=false; current.setup=SETUP_NONE;
      current.quality=Q_NONE; current.opened=0; current.legs=0; current.beApplied=false;
      current.riskDistance=0; current.lot=0; current.mae=0; current.mfe=0;
      hasOpenSetup=false;
     }

   long LegMagic(const long base,const ENUM_SETUP_ID s,const int leg) const
     { return base + (long)s*10 + (leg+1); }

   //--- open the ladder; a partially filled ladder is still valid -----
   bool OpenSetup(const TradeSignal &sig,const double lot,const int legs,const long magicBase)
     {
      if(m_br==NULL) return false;
      Reset();
      current.isLong=sig.isLong; current.setup=sig.setup; current.quality=sig.quality;
      current.entry=sig.entry;   current.sl=sig.sl;      current.opened=TimeCurrent();
      current.riskDistance=sig.riskDistance; current.lot=lot; current.legs=legs;

      int filled=0;
      for(int i=0;i<legs;i++)
        {
         current.tp[i]=sig.tp[i];
         m_br.trade.SetExpertMagicNumber(LegMagic(magicBase,sig.setup,i));
         string cm=StringFormat("%s_%s_TP%d",InpTradeComment,SetupName(sig.setup),i+1);

         if(m_br.Open(sig.isLong,lot,sig.sl,sig.tp[i],cm))
           {
            current.ticket[i]=m_br.trade.ResultOrder();
            // ResultOrder returns the deal/order; resolve to the position ticket
            if(current.ticket[i]==0) current.ticket[i]=FindPositionByMagic(LegMagic(magicBase,sig.setup,i));
            current.active[i]=(current.ticket[i]>0);
            if(current.active[i]) filled++;
           }
         else
            PrintFormat("[TM] leg %d rejected: %s",i+1,m_br.lastError);
        }

      if(filled==0) { Reset(); return false; }
      // Edge case: partial ladder. Keep what filled rather than unwinding
      // into a second round of spread cost.
      if(filled<legs)
         PrintFormat("[TM] partial ladder: %d/%d legs filled",filled,legs);

      hasOpenSetup=true;
      return true;
     }

   ulong FindPositionByMagic(const long magic) const
     {
      for(int i=PositionsTotal()-1;i>=0;i--)
        {
         ulong t=PositionGetTicket(i);
         if(t==0) continue;
         if(PositionGetInteger(POSITION_MAGIC)==magic &&
            PositionGetString(POSITION_SYMBOL)==m_br.symbol)
            return t;
        }
      return 0;
     }

   bool LegAlive(const int i) const
     {
      if(!current.active[i] || current.ticket[i]==0) return false;
      return PositionSelectByTicket(current.ticket[i]);
     }

   int AliveCount(void)
     {
      int n=0;
      for(int i=0;i<3;i++)
        {
         if(current.active[i] && !PositionSelectByTicket(current.ticket[i]))
            current.active[i]=false;      // closed by SL/TP
         if(current.active[i]) n++;
        }
      return n;
     }

   //--- break-even price honouring the configured mode ----------------
   double BreakEvenPrice(const double atr) const
     {
      double e=current.entry;
      double sp=m_br.Spread();
      switch(InpBEMode)
        {
         case BE_ENTRY:  return e;
         case BE_SPREAD: return current.isLong ? e+sp : e-sp;
         case BE_BUFFER: return current.isLong ? e+sp+InpBEBufferPoints*m_br.point
                                               : e-sp-InpBEBufferPoints*m_br.point;
         case BE_ATR:    return current.isLong ? e+sp+InpBEBufferATR*atr
                                               : e-sp-InpBEBufferATR*atr;
        }
      return e;
     }

   //--- per-tick management ------------------------------------------
   void Manage(const double atr,const int barsElapsed)
     {
      if(!hasOpenSetup) return;

      int alive=AliveCount();
      if(alive==0) { hasOpenSetup=false; return; }

      TrackExcursion();

      // Spec 20: TP1 gone -> legs 2 and 3 to break-even.
      if(InpMoveBEOnTP1 && !current.beApplied && !current.active[0] && current.ticket[0]!=0)
        {
         double be=m_br.NormPrice(BreakEvenPrice(atr));
         bool anyMoved=false;
         for(int i=1;i<3;i++)
            if(LegAlive(i) && m_br.ModifySL(current.ticket[i],be)) anyMoved=true;
         if(anyMoved) { current.beApplied=true; current.sl=be; }
        }

      // Time stop on whatever is left. Under EXIT_TIME_STOP_ONLY no target
      // is placed, so this is the only exit besides the stop - it cannot be
      // switched off there without leaving the position open indefinitely.
      bool timeStopRequired = (InpExitMode==EXIT_TIME_STOP_ONLY);
      if((InpUseTimeStop||timeStopRequired) && barsElapsed>=InpTimeStopBars)
         CloseAll("time stop");
     }

   void TrackExcursion(void)
     {
      double px = current.isLong ? m_br.Bid() : m_br.Ask();
      double move = current.isLong ? (px-current.entry) : (current.entry-px);
      if(move<current.mae) current.mae=move;
      if(move>current.mfe) current.mfe=move;
     }

   void CloseAll(const string why)
     {
      for(int i=0;i<3;i++)
         if(LegAlive(i))
           {
            if(m_br.ClosePosition(current.ticket[i])) current.active[i]=false;
            else PrintFormat("[TM] close failed leg %d rc=%d",i+1,m_br.lastRetcode);
           }
      if(AliveCount()==0) { hasOpenSetup=false; PrintFormat("[TM] setup closed: %s",why); }
     }

   double RMultiple(const double profitPrice) const
     {
      if(current.riskDistance<=0.0) return 0.0;
      return profitPrice/current.riskDistance;
     }

   static string SetupName(const ENUM_SETUP_ID s)
     {
      switch(s) { case SETUP_A: return "A"; case SETUP_B: return "B";
                  case SETUP_C: return "C"; case SETUP_D: return "D"; }
      return "-";
     }
  };
#endif
