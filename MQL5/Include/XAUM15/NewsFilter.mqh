//+------------------------------------------------------------------+
//| NewsFilter.mqh - MODULE 2                                         |
//| Calendar API with a manual schedule fallback (spec 4).            |
//+------------------------------------------------------------------+
#ifndef XAUM15_NEWS_MQH
#define XAUM15_NEWS_MQH
#include "Config.mqh"

class CNewsFilter
  {
private:
   datetime m_manual[];
   string   m_currencies[];
   datetime m_cacheDay;
   datetime m_events[];
   string   m_names[];
   bool     m_calendarOk;

   void ParseCurrencies(void)
     {
      StringSplit(InpNewsCurrencies,',',m_currencies);
      for(int i=0;i<ArraySize(m_currencies);i++)
        {
         StringTrimLeft(m_currencies[i]);
         StringTrimRight(m_currencies[i]);
        }
     }
   bool CurrencyWatched(const string c) const
     {
      for(int i=0;i<ArraySize(m_currencies);i++)
         if(m_currencies[i]==c) return true;
      return false;
     }

public:
   string lastBlockingEvent;

   CNewsFilter(void): m_cacheDay(0), m_calendarOk(false), lastBlockingEvent("") {}

   void Init(void)
     {
      ParseCurrencies();
      // Manual schedule: "YYYY.MM.DD HH:MM;YYYY.MM.DD HH:MM"
      string parts[];
      int n=StringSplit(InpManualNewsTimes,';',parts);
      ArrayResize(m_manual,0);
      for(int i=0;i<n;i++)
        {
         string s=parts[i];
         StringTrimLeft(s); StringTrimRight(s);
         if(StringLen(s)<10) continue;
         datetime t=StringToTime(s);
         if(t>0) { int k=ArraySize(m_manual); ArrayResize(m_manual,k+1); m_manual[k]=t; }
        }
     }

   //--- refresh once per day; calendar calls are expensive -----------
   void RefreshCalendar(const datetime now)
     {
      if(!InpUseCalendarAPI) return;
      datetime day = now - (now % 86400);
      if(day==m_cacheDay) return;
      m_cacheDay=day;
      ArrayResize(m_events,0);
      ArrayResize(m_names,0);

      MqlCalendarValue values[];
      // Window covers yesterday..tomorrow so overnight events are seen.
      if(CalendarValueHistory(values,day-86400,day+2*86400,NULL,NULL)<=0)
        { m_calendarOk=false; return; }
      m_calendarOk=true;

      for(int i=0;i<ArraySize(values);i++)
        {
         MqlCalendarEvent ev;
         if(!CalendarEventById(values[i].event_id,ev)) continue;
         if(InpHighImpactOnly && ev.importance!=CALENDAR_IMPORTANCE_HIGH) continue;

         MqlCalendarCountry cty;
         if(!CalendarCountryById(ev.country_id,cty)) continue;
         if(ArraySize(m_currencies)>0 && !CurrencyWatched(cty.currency)) continue;

         int k=ArraySize(m_events);
         ArrayResize(m_events,k+1); ArrayResize(m_names,k+1);
         m_events[k]=values[i].time;
         m_names[k] =ev.name;
        }
     }

   bool CalendarAvailable(void) const { return m_calendarOk; }

   //--- true when trading must be suspended --------------------------
   bool IsBlocked(const datetime now)
     {
      lastBlockingEvent="";
      if(!InpNewsFilter || !InpAblNews) return false;

      long before=(long)InpMinutesBeforeNews*60;
      long after =(long)InpMinutesAfterNews*60;

      for(int i=0;i<ArraySize(m_events);i++)
         if(now >= m_events[i]-before && now <= m_events[i]+after)
           { lastBlockingEvent=m_names[i]; return true; }

      for(int i=0;i<ArraySize(m_manual);i++)
         if(now >= m_manual[i]-before && now <= m_manual[i]+after)
           { lastBlockingEvent="manual schedule"; return true; }

      return false;
     }
  };
#endif
