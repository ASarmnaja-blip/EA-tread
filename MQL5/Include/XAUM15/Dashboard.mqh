//+------------------------------------------------------------------+
//| Dashboard.mqh - MODULE 16 / spec 35                               |
//+------------------------------------------------------------------+
#ifndef XAUM15_DASH_MQH
#define XAUM15_DASH_MQH
#include "Config.mqh"

class CDashboard
  {
private:
   string m_prefix;
   int    m_row;

   void Line(const string key,const string text,const color clr)
     {
      string name=m_prefix+key;
      if(ObjectFind(0,name)<0)
        {
         ObjectCreate(0,name,OBJ_LABEL,0,0,0);
         ObjectSetInteger(0,name,OBJPROP_CORNER,CORNER_LEFT_UPPER);
         ObjectSetInteger(0,name,OBJPROP_SELECTABLE,false);
         ObjectSetInteger(0,name,OBJPROP_HIDDEN,true);
         ObjectSetString (0,name,OBJPROP_FONT,"Consolas");
         ObjectSetInteger(0,name,OBJPROP_FONTSIZE,InpDashFontSize);
        }
      ObjectSetInteger(0,name,OBJPROP_XDISTANCE,InpDashX);
      ObjectSetInteger(0,name,OBJPROP_YDISTANCE,InpDashY+m_row*(InpDashFontSize+6));
      ObjectSetInteger(0,name,OBJPROP_COLOR,clr);
      ObjectSetString (0,name,OBJPROP_TEXT,text);
      m_row++;
     }

   color PLColor(const double v) const
     { return v>0.0?clrLimeGreen:(v<0.0?clrTomato:clrSilver); }

public:
   CDashboard(void): m_prefix("XAUM15_DASH_"), m_row(0) {}

   void Destroy(void) { ObjectsDeleteAll(0,m_prefix); }

   void Render(const string status,const string session,const string regime,
               const string amdPhase,const double price,const double spread,
               const double atr,const double vwap,const double poc,
               const double vah,const double val,const double asianH,
               const double asianL,const double pdh,const double pdl,
               const string bias,const string activeSetup,const string quality,
               const double entry,const double sl,const double tp1,
               const double tp2,const double tp3,const double riskPct,
               const double dailyPL,const double dailyDD,const double totalDD,
               const double winRate,const double pf,const double expectancy,
               const double avgR,const int totalTrades,const string volSource)
     {
      if(!InpShowDashboard) return;
      m_row=0;

      Line("00","== XAU M15 INSTITUTIONAL ADAPTIVE v"+XAUM15_VERSION+" ==",clrGold);
      Line("01","Status      : "+status, status=="TRADING"?clrLimeGreen:clrOrange);
      Line("02","Session     : "+session,clrWhite);
      Line("03","Regime      : "+regime,clrWhite);
      Line("04","AMD phase   : "+amdPhase,clrWhite);
      Line("05","",clrSilver);

      Line("10",StringFormat("Price       : %.2f",price),clrWhite);
      Line("11",StringFormat("Spread      : %.2f  %s",spread,
                             spread>InpMaxSpread?"(BLOCKED)":""),
                             spread>InpMaxSpread?clrTomato:clrSilver);
      Line("12",StringFormat("ATR(%d)      : %.2f",InpAtrPeriod,atr),clrSilver);
      Line("13",StringFormat("VWAP        : %.2f",vwap),clrDeepSkyBlue);
      Line("14",StringFormat("POC/VAH/VAL : %.2f / %.2f / %.2f",poc,vah,val),clrMediumPurple);
      Line("15",StringFormat("Vol source  : %s",volSource),clrGray);
      Line("16",StringFormat("Asian H/L   : %.2f / %.2f",asianH,asianL),clrSandyBrown);
      Line("17",StringFormat("PrevDay H/L : %.2f / %.2f",pdh,pdl),clrSandyBrown);
      Line("18","",clrSilver);

      Line("20","Bias        : "+bias,clrWhite);
      Line("21","Active setup: "+activeSetup,clrWhite);
      Line("22","Quality     : "+quality,clrWhite);
      Line("23",StringFormat("Entry       : %.2f",entry),clrWhite);
      Line("24",StringFormat("SL          : %.2f",sl),clrTomato);
      Line("25",StringFormat("TP1/2/3     : %.2f / %.2f / %.2f",tp1,tp2,tp3),clrLimeGreen);
      Line("26",StringFormat("Risk        : %.3f%%",riskPct),clrWhite);
      Line("27","",clrSilver);

      Line("30",StringFormat("Daily P/L   : %+.2f%%  (target %+.1f%% / limit %-.1f%%)",
                             dailyPL,InpDailyProfitTarget,-InpDailyLossLimit),PLColor(dailyPL));
      Line("31",StringFormat("Daily DD    : %.2f%%",dailyDD),clrSilver);
      Line("32",StringFormat("Total DD    : %.2f%%  (stop %.0f%% / max %.0f%%)",
                             totalDD,InpDD_Preferred,InpDD_Emergency),
                             totalDD>=InpDD_Level3?clrTomato:clrSilver);
      Line("33","",clrSilver);

      Line("40",StringFormat("Trades      : %d",totalTrades),clrWhite);
      Line("41",StringFormat("Win rate    : %.2f%%",winRate),clrWhite);
      Line("42",StringFormat("Profit fact : %.3f",pf),pf>=1.30?clrLimeGreen:clrOrange);
      Line("43",StringFormat("Expectancy  : %+.4fR",expectancy),PLColor(expectancy));
      Line("44",StringFormat("Average R   : %+.4f",avgR),PLColor(avgR));

      ChartRedraw(0);
     }
  };
#endif
