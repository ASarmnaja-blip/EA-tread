//+------------------------------------------------------------------+
//| DecisionLog.mqh - Track 1.2                                       |
//|                                                                   |
//| One row per evaluated M15 bar, whether or not a trade was taken.  |
//|                                                                   |
//| A system that refuses every setup and a system that is broken     |
//| produce the same silence. CLAUDE.md section 6 requires the reason |
//| a trade was NOT taken to be part of the output, and section 11 of |
//| the protocol requires NO TRADE to be a conclusion rather than an  |
//| unexamined default. This module is how that becomes checkable.    |
//|                                                                   |
//| OBSERVABILITY ONLY. Nothing here is read back by a decision path. |
//| Writing a CSV cannot change which trades are taken, and no        |
//| function in this file places, modifies or closes an order.        |
//|                                                                   |
//| KNOWN GAP, recorded rather than papered over: in the current EA   |
//| the veto chain runs BEFORE the setups are evaluated, so on a      |
//| gate-blocked bar no candidate is evaluated at all. Those rows are |
//| written with evaluation_ran=0 and decision_reason prefixed        |
//| "gate_blocked_before_evaluation". Reordering the chain would      |
//| change trading behaviour and is out of scope for Track 1.         |
//+------------------------------------------------------------------+
#ifndef XAUM15_DECISIONLOG_MQH
#define XAUM15_DECISIONLOG_MQH
#include "Config.mqh"

//--- how far this bar got down the pipeline -------------------------
//    Each value is set at the point it becomes PROVABLE. Nothing is
//    inferred: a state is recorded because the code reached the line that
//    establishes it, never because a later state seemed likely.
enum ENUM_CANDIDATE_STATE
  {
   CAND_NOT_EVALUATED=0,      // veto chain stopped the bar; no setup ran
   CAND_EVALUATED_NO_SIGNAL,  // setups ran, none produced a candidate
   CAND_CANDIDATE_SIGNAL,     // candidate produced; no order attempted
   CAND_ORDER_ATTEMPTED,      // OpenSetup called, outcome not yet known
   CAND_ORDER_ACCEPTED,       // OpenSetup returned true
   CAND_ORDER_REJECTED,       // OpenSetup returned false
   // NOT OBSERVABLE IN TRACK 1.2, and therefore never set. Proving a
   // position exists means querying broker state at a later moment; that
   // is a different measurement, not a stronger reading of this one.
   CAND_POSITION_OPENED
  };

string CandidateStateName(const ENUM_CANDIDATE_STATE st)
  {
   switch(st)
     {
      case CAND_NOT_EVALUATED:     return "NOT_EVALUATED";
      case CAND_EVALUATED_NO_SIGNAL:return "EVALUATED_NO_SIGNAL";
      case CAND_CANDIDATE_SIGNAL:  return "CANDIDATE_SIGNAL";
      case CAND_ORDER_ATTEMPTED:   return "ORDER_ATTEMPTED";
      case CAND_ORDER_ACCEPTED:    return "ORDER_ACCEPTED";
      case CAND_ORDER_REJECTED:    return "ORDER_REJECTED";
      case CAND_POSITION_OPENED:   return "POSITION_OPENED";
     }
   return "UNKNOWN";
  }

//--- what the candidate sweep actually did on this bar ---------------
struct CandidateAudit
  {
   ENUM_CANDIDATE_STATE state;
   bool  evaluationRan;      // false = gates blocked before any evaluation
   bool  enabled[5];         // index by ENUM_SETUP_ID
   int   produced[5];        // candidates produced (both directions)
   int   qualityAllowed[5];  // of those, how many passed the quality gate
   int   totalProduced;

   void Reset(void)
     {
      state=CAND_NOT_EVALUATED;
      evaluationRan=false;
      totalProduced=0;
      for(int i=0;i<5;i++) { enabled[i]=false; produced[i]=0; qualityAllowed[i]=0; }
     }

   //--- compact "A:0/1 B:- C:- D:2/2" style summary for the CSV ------
   string Summary(void) const
     {
      string names[5]={"-","A","B","C","D"};
      string out="";
      for(int i=1;i<5;i++)
        {
         if(out!="") out+=" ";
         if(!enabled[i]) { out+=names[i]+":off"; continue; }
         out+=StringFormat("%s:%d/%d",names[i],qualityAllowed[i],produced[i]);
        }
      return out;
     }
  };

class CDecisionLog
  {
private:
   int    m_h;
   string m_file;
   long   m_rows;
   long   m_noTrade;

public:
   CDecisionLog(void): m_h(INVALID_HANDLE), m_rows(0), m_noTrade(0) {}

   bool Init(const string fname)
     {
      if(!InpWriteDecisionLog) return true;
      m_file=fname;
      m_h=FileOpen(m_file,FILE_WRITE|FILE_READ|FILE_CSV|FILE_ANSI,',');
      if(m_h==INVALID_HANDLE)
        {
         PrintFormat("[DECISIONLOG] cannot open %s err=%d",m_file,GetLastError());
         return false;
        }
      FileSeek(m_h,0,SEEK_END);
      if(FileTell(m_h)==0)
         FileWrite(m_h,
            "date","time","symbol","timeframe",
            "regime","regime_score","atr","spread",
            "candidate_state","evaluation_ran","gate_passed","gate_reason",
            "candidates_produced","candidate_detail",
            "decision","decision_reason",
            "setup","direction","entry","sl","invalidation","invalidation_rule",
            "risk_r","confidence","expiry_bars","expiry_time",
            "evidence","priced_in","news_risk");
      return true;
     }

   void Close(void)
     { if(m_h!=INVALID_HANDLE) { FileClose(m_h); m_h=INVALID_HANDLE; } }

   //--- RFC 4180 field quoting ---------------------------------------
   //    MQL5's FileWrite joins its arguments with the separator and
   //    escapes nothing. A comma inside a reason string therefore shifts
   //    every column after it, and a newline splits one record across two
   //    lines - which is exactly what the reason strings in Setups.mqh do
   //    ("premise is dead, regardless of the stop").
   //
   //    Newlines are folded to a space rather than quoted. RFC 4180 allows
   //    a quoted newline, but a log that is read with grep, tail or a
   //    line-per-record parser should stay one record per line.
   static string CsvEscape(const string value)
     {
      string s=value;
      StringReplace(s,"\r\n"," ");
      StringReplace(s,"\r"," ");
      StringReplace(s,"\n"," ");
      bool needQuotes=(StringFind(s,",")>=0 || StringFind(s,"\"")>=0);
      if(StringFind(s,"\"")>=0) StringReplace(s,"\"","\"\"");
      if(needQuotes) s="\""+s+"\"";
      return s;
     }

   long Rows(void)    const { return m_rows; }
   long NoTrades(void) const { return m_noTrade; }

   //--- one row per evaluated bar ------------------------------------
   void Write(const datetime when,const string regimeName,
              const double regimeScore,const double atr,const double spread,
              const CandidateAudit &audit,
              const bool gatePassed,const string gateReason,
              const TradeSignal &sig)
     {
      m_rows++;
      bool traded = (sig.decision=="TRADE");
      if(!traded) m_noTrade++;
      if(m_h==INVALID_HANDLE) return;

      string dir = (!sig.valid) ? "" : (sig.isLong?"LONG":"SHORT");
      string setupName="";
      switch(sig.setup)
        {
         case SETUP_A: setupName="A"; break;
         case SETUP_B: setupName="B"; break;
         case SETUP_C: setupName="C"; break;
         case SETUP_D: setupName="D"; break;
         default:      setupName="";  break;
        }

      FileWrite(m_h,
         TimeToString(when,TIME_DATE),
         TimeToString(when,TIME_MINUTES),
         CsvEscape(sig.symbol==""?_Symbol:sig.symbol),
         EnumToString((ENUM_TIMEFRAMES)_Period),
         CsvEscape(regimeName),
         DoubleToString(regimeScore,3),
         DoubleToString(atr,3),
         DoubleToString(spread,3),
         CandidateStateName(audit.state),
         (audit.evaluationRan?"1":"0"),
         (gatePassed?"1":"0"),
         CsvEscape(gateReason),
         IntegerToString(audit.totalProduced),
         CsvEscape(audit.Summary()),
         CsvEscape(sig.decision),
         CsvEscape(sig.decisionReason),
         CsvEscape(setupName),
         CsvEscape(dir),
         DoubleToString(sig.entry,2),
         DoubleToString(sig.sl,2),
         DoubleToString(sig.invalidation,2),
         CsvEscape(sig.invalidationRule),
         DoubleToString(sig.riskR,2),
         DoubleToString(sig.confidence,3),   // -1 = not calibrated
         IntegerToString(sig.expiryBars),    // -1 = no policy selected
         (sig.expiryTime>0?TimeToString(sig.expiryTime,TIME_DATE|TIME_MINUTES):""),
         CsvEscape(sig.evidence),
         CsvEscape(sig.pricedIn),
         CsvEscape(sig.newsRisk));
      FileFlush(m_h);
     }

   //--- deinit summary: makes "it never traded" legible --------------
   void PrintReport(void)
     {
      Print("==================== DECISION LOG ====================");
      PrintFormat("bars evaluated     : %s",IntegerToString(m_rows));
      PrintFormat("  NO TRADE         : %s",IntegerToString(m_noTrade));
      PrintFormat("  TRADE            : %s",IntegerToString(m_rows-m_noTrade));
      if(InpWriteDecisionLog)
         PrintFormat("written to         : %s",m_file);
      Print("A NO TRADE row with evaluation_ran=0 means the veto chain");
      Print("stopped the bar before any setup was evaluated. That is a");
      Print("known ordering gap, not a judgement that no setup qualified.");
      Print("======================================================");
     }
  };
#endif
