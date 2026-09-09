//+------------------------------------------------------------------+
//| SessionFilter.mqh - MODULE 1                                      |
//| Answers WHEN. All windows in BROKER SERVER TIME + DST offset.     |
//+------------------------------------------------------------------+
#ifndef XAUM15_SESSION_MQH
#define XAUM15_SESSION_MQH
#include "Config.mqh"

class CSessionFilter
  {
private:
   int  Shift(const int h) const
     {
      int v=(h+InpDSTOffsetHours)%24;
      if(v<0) v+=24;
      return v;
     }
   //--- windows may wrap past midnight (e.g. 22 -> 6)
   bool InWindow(const int hour,const int startH,const int endH) const
     {
      int s=Shift(startH), e=Shift(endH);
      if(s==e)  return false;
      if(s<e)   return (hour>=s && hour<e);
      return (hour>=s || hour<e);          // wrapped
     }

public:
   MqlDateTime dt;

   void Refresh(const datetime now) { TimeToStruct(now,dt); }

   bool IsAsian   (const datetime t) { MqlDateTime d; TimeToStruct(t,d); return InWindow(d.hour,InpAsianStartHour,InpAsianEndHour); }
   bool IsLondon  (const datetime t) { MqlDateTime d; TimeToStruct(t,d); return InWindow(d.hour,InpLondonStartHour,InpLondonEndHour); }
   bool IsNewYork (const datetime t) { MqlDateTime d; TimeToStruct(t,d); return InWindow(d.hour,InpNewYorkStartHour,InpNewYorkEndHour); }
   bool IsOverlap (const datetime t) { return IsLondon(t) && IsNewYork(t); }

   string Name(const datetime t)
     {
      if(IsOverlap(t)) return "LDN+NY";
      if(IsLondon(t))  return "LONDON";
      if(IsNewYork(t)) return "NEWYORK";
      if(IsAsian(t))   return "ASIAN";
      return "OFF";
     }

   //--- start of today's Asian window, used to bound the Asian range
   datetime AsianStart(const datetime now) const
     {
      MqlDateTime d; TimeToStruct(now,d);
      d.hour=Shift(InpAsianStartHour); d.min=0; d.sec=0;
      datetime s=StructToTime(d);
      if(s>now) s-=86400;                 // window began yesterday
      return s;
     }
   datetime AsianEnd(const datetime now) const
     {
      datetime s=AsianStart(now);
      int len=Shift(InpAsianEndHour)-Shift(InpAsianStartHour);
      if(len<=0) len+=24;
      return s+len*3600;
     }

   datetime SessionOpen(const datetime now,const int startHour) const
     {
      MqlDateTime d; TimeToStruct(now,d);
      d.hour=Shift(startHour); d.min=0; d.sec=0;
      datetime s=StructToTime(d);
      if(s>now) s-=86400;
      return s;
     }

   //--- Spec 3: entries only inside the tradeable windows ------------
   bool EntryAllowed(const datetime t,string &why)
     {
      if(!InpUseSessionFilter || !InpAblSession) return true;

      if(InpBlockAsianEntries && IsAsian(t) && !IsLondon(t) && !IsNewYork(t))
        { why="asian session blocked"; return false; }

      bool ldn=IsLondon(t), ny=IsNewYork(t);
      if(InpTradeOverlapOnly)
        {
         if(!(ldn&&ny)) { why="outside LDN/NY overlap"; return false; }
         return true;
        }
      if(ldn && InpTradeLondon)  { if(WithinEntryWindow(t,InpLondonStartHour))  return true; }
      if(ny  && InpTradeNewYork) { if(WithinEntryWindow(t,InpNewYorkStartHour)) return true; }

      why = (ldn||ny) ? "past entry window" : "outside trading session";
      return false;
     }

   //--- Spec 3: only the first N minutes after an open are prime -----
   bool WithinEntryWindow(const datetime t,const int sessionStartHour) const
     {
      if(InpEntryWindowMinutes<=0) return true;
      datetime open=SessionOpen(t,sessionStartHour);
      long mins=(long)(t-open)/60;
      return (mins>=0 && mins<=InpEntryWindowMinutes);
     }
  };
#endif
