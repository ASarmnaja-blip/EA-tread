//+------------------------------------------------------------------+
//| Config.mqh                                                        |
//| XAU M15 Institutional Adaptive EA - inputs, enums, shared types    |
//+------------------------------------------------------------------+
#ifndef XAUM15_CONFIG_MQH
#define XAUM15_CONFIG_MQH

#define XAUM15_VERSION "1.00"

//--- enums ---------------------------------------------------------
enum ENUM_SESSION_MODE { SESS_ASIAN, SESS_LONDON, SESS_NEWYORK, SESS_LDN_NY };
enum ENUM_REGIME       { REG_NONE, REG_TREND_UP, REG_TREND_DOWN, REG_RANGE,
                         REG_HIGH_VOL, REG_LOW_VOL, REG_EXTREME_VOL };
enum ENUM_AMD_PHASE    { AMD_NONE, AMD_ACCUMULATION, AMD_MANIPULATION, AMD_DISTRIBUTION };
enum ENUM_VOLUME_SRC   { VOL_BROKER_TICK, VOL_EXTERNAL, VOL_AUTO };
enum ENUM_ENTRY_MODE   { ENTRY_MARKET, ENTRY_RETEST, ENTRY_LIMIT, ENTRY_BREAKOUT };
enum ENUM_SETUP_ID     { SETUP_NONE=0, SETUP_A=1, SETUP_B=2, SETUP_C=3, SETUP_D=4 };
enum ENUM_SL_MODE      { SL_STRUCTURE_ATR, SL_FIXED_ATR };
enum ENUM_EXIT_MODE    { EXIT_TP_LADDER,        // 3 legs at 1R/2R/3R
                         EXIT_TIME_STOP_ONLY,   // no target at all
                         EXIT_SINGLE_TARGET,    // 1 leg at InpTargetR + time stop
                         EXIT_PARTIAL_RUNNER };
enum ENUM_QUALITY      { Q_NONE=0, Q_C=1, Q_B=2, Q_A=3, Q_APLUS=4 };
enum ENUM_DAILY_LOSS_ACTION { DL_STOP_NEW_TRADES, DL_CLOSE_ALL };
enum ENUM_DD_ACTION    { DD_NOTHING, DD_STOP_NEW, DD_CLOSE_ALL_AND_STOP };
enum ENUM_BE_MODE      { BE_ENTRY, BE_SPREAD, BE_BUFFER, BE_ATR };
enum ENUM_LOTFIT_MODE  { LOTFIT_REJECT, LOTFIT_REDUCE_POSITIONS, LOTFIT_ALLOW_OVER };
enum ENUM_SWEEP_SIDE   { SWEEP_NONE, SWEEP_HIGH, SWEEP_LOW };
enum ENUM_LIQ_TYPE     { LQ_PDH, LQ_PDL, LQ_ASIA_H, LQ_ASIA_L, LQ_LDN_H, LQ_LDN_L,
                         LQ_PWH, LQ_PWL, LQ_SWING_H, LQ_SWING_L, LQ_EQH, LQ_EQL };

//====================================================================
// GENERAL
//====================================================================
input group "=== GENERAL ==="
input long   InpMagicBase          = 8150000;  // Magic number base
input string InpTradeComment       = "XAUM15"; // Order comment prefix
input bool   InpEnableTrading      = true;     // Master trading switch
input bool   InpVerboseLog         = false;    // Verbose journal logging

//====================================================================
// MODULE 1 - SESSION FILTER  (all times = BROKER SERVER TIME)
//====================================================================
input group "=== M1 SESSION ==="
input bool   InpUseSessionFilter   = true;
input int    InpAsianStartHour     = 0;    // Asian session start (server hour)
input int    InpAsianEndHour       = 7;    // Asian session end
input int    InpLondonStartHour    = 8;    // London start
input int    InpLondonEndHour      = 16;   // London end
input int    InpNewYorkStartHour   = 13;   // New York start
input int    InpNewYorkEndHour     = 21;   // New York end
input bool   InpTradeLondon        = true;
input bool   InpTradeNewYork       = true;
input bool   InpTradeOverlapOnly   = false; // Trade only London/NY overlap
input bool   InpBlockAsianEntries  = true;  // No entries mid-Asian session
input int    InpDSTOffsetHours     = 0;     // Manual DST shift applied to all windows
input int    InpEntryWindowMinutes = 180;   // Minutes after session open that allow entry

//====================================================================
// MODULE 2 - NEWS FILTER
//====================================================================
input group "=== M2 NEWS ==="
input bool   InpNewsFilter         = true;
input int    InpMinutesBeforeNews  = 15;
input int    InpMinutesAfterNews   = 15;
input bool   InpUseCalendarAPI     = true;  // MQL5 economic calendar
input string InpNewsCurrencies     = "USD,XAU";
input bool   InpHighImpactOnly     = true;
// Manual fallback schedule: "YYYY.MM.DD HH:MM;YYYY.MM.DD HH:MM;..." server time
input string InpManualNewsTimes    = "";

//====================================================================
// MODULE 3 - MARKET REGIME
//====================================================================
input group "=== M3 REGIME ==="
input int    InpEmaFast            = 50;
input int    InpEmaSlow            = 200;
input int    InpEmaSlopeBars       = 5;     // Bars used to measure EMA50 slope
input double InpEmaSlopeMinATR     = 0.05;  // Min slope per bar as fraction of ATR
input int    InpAtrPeriod          = 14;
input int    InpAtrRegimeLookback  = 100;   // Bars for ATR percentile ranking
input double InpLowVolPercentile   = 25.0;
input double InpHighVolPercentile  = 75.0;
input double InpExtremeVolPct      = 95.0;
input bool   InpBlockExtremeVol    = true;
input double InpRangeCompressATR   = 0.6;   // |EMA50-EMA200| < x*ATR => compression

//====================================================================
// MODULE 4 - LIQUIDITY
//====================================================================
input group "=== M4 LIQUIDITY ==="
input int    InpSwingLookback      = 3;     // Fractal wing size
input int    InpLiquidityMaxAgeBars= 480;   // Discard levels older than this
input double InpEqualLevelATR      = 0.15;  // Tolerance for equal highs/lows (x ATR)
input int    InpLiquidityMaxLevels = 64;
input bool   InpDrawLiquidity      = true;

//====================================================================
// MODULE 5 - AMD
//====================================================================
input group "=== M5 AMD ==="
input bool   InpUseAMD             = true;
input double InpAsianRangeMinATR   = 0.8;   // Asian range must be >= x*ATR to be valid
input double InpAsianRangeMaxATR   = 6.0;   // and <= x*ATR (else no clean accumulation)

//====================================================================
// MODULE 6/9 - VOLUME PROFILE
//====================================================================
input group "=== M6 VOLUME PROFILE ==="
input bool   InpUseVolumeProfile   = true;
input ENUM_VOLUME_SRC InpVolumeSource = VOL_BROKER_TICK;
input double InpValueAreaPercent   = 70.0;
input int    InpVPBins             = 60;
input int    InpVPLookbackBars     = 96;    // 96 M15 bars = 24h
input double InpVPTouchATR         = 0.25;  // Proximity tolerance to POC/VAH/VAL

//====================================================================
// MODULE 7 - VWAP
//====================================================================
input group "=== M7 VWAP ==="
input bool   InpUseVWAP            = true;
input bool   InpVWAPHardFilter     = false; // false = context only (recommended)

//====================================================================
// MODULE 8 - STRUCTURE
//====================================================================
input group "=== M8 STRUCTURE ==="
input double InpMinBreakATR        = 0.10;  // Min break distance beyond swing (x ATR)
input int    InpStructureLookback  = 40;    // Bars scanned for swings
input bool   InpRequireCloseBreak  = true;  // Break must be by candle close

//====================================================================
// MODULE 9 - SWEEP
//====================================================================
input group "=== M9 SWEEP ==="
input double InpSweepMinPenATR     = 0.08;  // Min penetration beyond level (x ATR)
input double InpSweepMaxPenATR     = 1.50;  // Max penetration (beyond = real break)
input int    InpSweepReclaimBars   = 3;     // Bars allowed to close back inside
input int    InpSweepValidBars     = 8;     // Sweep stays actionable this many bars

//====================================================================
// MODULE 10 - DISPLACEMENT
//====================================================================
input group "=== M10 DISPLACEMENT ==="
input double InpMinBodyATR         = 0.60;  // Body size / ATR
input double InpMinCloseLocation   = 0.65;  // Close position within bar range
input int    InpDisplacementLookback = 5;

//====================================================================
// MODULE 11 - ENTRY / SETUPS
//====================================================================
input group "=== M11 ENTRY ==="
input ENUM_ENTRY_MODE InpEntryMode = ENTRY_RETEST;
input int    InpRetestMaxBars      = 6;     // Bars to wait for retest before void
input double InpRetestZoneATR      = 0.35;  // Retest tolerance around trigger level
input bool   InpEnableSetupA       = false;  // sweep-reversal: no edge found (n=43,353)
input bool   InpEnableSetupB       = false;  // unvalidated
input bool   InpEnableSetupC       = false;  // unvalidated
input int    InpORMinutes          = 30;    // Opening range length (Setup C)
input double InpORMinExpansionATR  = 0.8;   // Required expansion beyond OR


//====================================================================
// SETUP D - TREND ZONE  (survived gold-only testing; FAILED cross-asset)
//====================================================================
// Evidence, from the 16-round research log on 15 years of XAUUSD
// minute data (5,250,134 bars):
//   (Close - SMA200) / ATR inside [+1.08, +7.21] survived a permutation
//   test at p=0.0005 on both the 1.5R and 2.5R targets, an in-zone vs
//   out-of-zone contrast (t=+9.33 long), and a market-drift-adjusted
//   retest (t=+5.08 long, +2.65 short).
//
// VALIDATION HAS NOW BEEN RUN, AND IT FAILED.
// The note that used to sit here said the zone was found on the FULL
// gold sample with no held-out half, that cross-asset confirmation had
// never been run, and that "if it does not reproduce there, this is
// gold overfit." research/setup_d_crossasset.py ran it on nine markets
// at H1, with the 30-hour time stop matched in wall-clock hours:
//
//   drift-adjusted skill positive on 0 of 9 markets, on BOTH sides.
//   long  mean skill -0.1322 (across-market t -2.97)
//   short mean skill -0.1226 (across-market t -3.51)
//
// Gold itself is in the failing set (H1 long E -0.0994, skill -0.1055).
// Only USDJPY long showed positive raw E (+0.0557) and its skill was
// -0.0535 - the market rose, counted twice. The implementation was
// verified before the nine-market run: on gold M15 it reproduces
// +0.1788R at zero cost against the documented +0.2312R (README's own
// table costs that figure at the $0.26 terminal quote), and the same
// book at real measured bid/ask is +0.0439R - so the shortfall is the
// spread, not a coding error.
//
// Two separate problems, either one fatal on its own:
//   1. The zone does not carry across assets. That is the condition
//      this comment itself named for calling it gold overfit.
//   2. The side this config trades is the wrong one. README's drift
//      table shows longs in zone at skill -0.0494 (t -4.14) and shorts
//      at +0.1092 (t +7.56) ON GOLD - yet InpTrendZoneLong=true and
//      InpTrendZoneShort=false. The long edge is gold's uptrend being
//      measured twice; the side with measured skill is switched off.
//
// The permutation test and the in-zone contrast above are not wrong,
// they are just answering a narrower question than they appear to:
// both compare the zone against gold's own history, where the drift is
// already in both arms. Do not trade this on the strength of the
// evidence block above without reading this one.
//
// Measured character: win rate ~23.8%, profit concentrated in a long
// right tail, longest REAL losing streak 19 trades, theoretical
// expectation ~29. Anything that trims the tail - partial closes,
// tight time stops, cooldowns - destroyed the edge in testing.
//====================================================================
input group "=== M11 SETUP D (TREND ZONE) ==="
input bool   InpEnableSetupD       = true;
input int    InpTrendSmaPeriod     = 200;   // SMA, not EMA - matches the research
input double InpTrendZoneMin       = 1.08;  // lower edge of the zone, in ATR
input double InpTrendZoneMax       = 7.21;  // upper edge
// DIRECTION: read the drift decomposition before changing these.
// Gold rose for the whole sample, so raw long numbers contain that drift.
// Subtracting it minute by minute:
//                      RAW E      t   |  SKILL (raw-drift)      t
//   longs in zone     +0.0569  +4.45  |        -0.0494      -4.14
//   shorts in zone    +0.0102  +0.75  |        +0.1092      +7.56
//   longs in - out    +0.0862  +5.24  |        +0.0781      +5.08
//   shorts in - out   +0.0490  +2.83  |        +0.0492      +2.65
// The zone does real timing work on BOTH sides (the in-minus-out rows are
// what t=+5.08 and +2.65 refer to). But in ABSOLUTE terms the long side is
// negative once drift is removed: longs made money because gold went up.
// The short side is where the measured skill is.
// Long-only is therefore a bet that gold keeps trending up, plus the zone.
// It is not the side with the cleaner evidence.
input bool   InpTrendZoneLong      = true;  // profitable historically, via drift
input bool   InpTrendZoneShort     = false; // the side with positive SKILL
input double InpTrendSLATR         = 1.8;   // flat stop, the winning config
input bool   InpTrendRequireEntry  = true;  // fire on ENTERING the zone only

//====================================================================
// MODULE 12 - RISK
//====================================================================
input group "=== M12 RISK ==="
input double InpRiskPercent        = 0.50;  // Risk % of equity per SETUP (research baseline)
input double InpMaxRiskPercent     = 1.00;  // Hard cap per setup
input int    InpPositionsPerSetup  = 1;     // 1 for Setup D; 3 = the 1R/2R/3R ladder
input ENUM_LOTFIT_MODE InpLotFitMode = LOTFIT_REDUCE_POSITIONS;
input ENUM_SL_MODE   InpSLMode     = SL_FIXED_ATR;   // FIXED_ATR = Setup D; STRUCTURE = A/B/C
input ENUM_EXIT_MODE InpExitMode   = EXIT_SINGLE_TARGET; // see the R scan below
// The notebook's target scan on zone entries (mean ATR $2.58, spread $0.26)
// is monotone all the way out - expectancy and Sharpe both keep rising:
//     R      long E      net       Sharpe
//   1.5     +0.0569   +0.0008        0.02
//   2.5     +0.0891   +0.0330        0.91
//   4.0     +0.1455   +0.0894        2.46
//   6.0     +0.2351   +0.1791        4.93
//   8.0     +0.2873   +0.2312        6.36   <- best
// The 30-hour hold is the BACKSTOP behind that target, not the exit plan.
// An earlier revision of this repository placed no target at all; that was a
// misreading of the summary and left the whole right tail uncaptured.
input double InpTargetR            = 8.0;   // EXIT_SINGLE_TARGET / runner leg
input double InpPartialR           = 1.5;   // EXIT_PARTIAL_RUNNER first leg
// Partial exits are NOT settled. Both of these clear the DD<35% bar:
//   no partial, 8R      -> CAGR 20.2%, maxDD 28.2%   (wins on CAGR)
//   50% at 1.5R, rest 8R-> CAGR 12.3%, maxDD 24.5%   (wins on Sharpe)
// The notebook's "best survivor" line names the second because it ranks by
// Sharpe. Choose deliberately; do not assume one is correct.
input double InpSLBufferATR        = 0.35;  // ATR buffer added beyond structure
input double InpMinSLATR           = 0.50;  // Floor for SL distance
input double InpMaxSLATR           = 3.00;  // Ceiling; wider setups are rejected

//====================================================================
// MODULE 13 - TRADE MANAGEMENT
//====================================================================
input group "=== M13 TRADE MGMT ==="
input double InpTP1R               = 1.0;
input double InpTP2R               = 2.0;
input double InpTP3R               = 3.0;
input ENUM_BE_MODE InpBEMode       = BE_SPREAD;
input double InpBEBufferPoints     = 20;    // Extra buffer in points for BE_BUFFER
input double InpBEBufferATR        = 0.05;  // For BE_ATR
input bool   InpMoveBEOnTP1        = true;
input bool   InpUseTimeStop        = true;
input int    InpTimeStopBars       = 120;   // 120 = 30h - the tested Setup D hold

//====================================================================
// MODULE 14 - DAILY RISK
//====================================================================
input group "=== M14 DAILY RISK ==="
// A -2.5% daily stop is incompatible with a 23.8% win-rate system risking
// ~2% per trade: one loss halts the day, every day. Keep the limits ON only
// when risk-per-trade is small relative to the limit (see the OnInit report).
input bool   InpUseDailyLimits     = true;  // master switch for the two below
input double InpDailyProfitTarget  = 3.0;   // % - stop opening new trades
input double InpDailyLossLimit     = 2.5;   // %
input ENUM_DAILY_LOSS_ACTION InpDailyLossAction = DL_STOP_NEW_TRADES;
input int    InpMaxTradesPerDay    = 3;     // Setups per day (30h holds rarely reach this)
input int    InpMaxConcurrentSetups= 1;
input int    InpCooldownBarsLoss   = 0;     // long losing streaks are normal here
input int    InpCooldownBarsWin    = 0;

//====================================================================
// MODULE 15 - DRAWDOWN
//====================================================================
input group "=== M15 DRAWDOWN ==="
input double InpDD_Level1          = 20.0;
input double InpDD_Level2          = 25.0;
input double InpDD_Level3          = 30.0;
input double InpDD_Preferred       = 35.0;  // Hard stop
input double InpDD_Emergency       = 40.0;  // Absolute emergency
input ENUM_DD_ACTION InpDDAction1  = DD_NOTHING;
input ENUM_DD_ACTION InpDDAction2  = DD_NOTHING;
input ENUM_DD_ACTION InpDDAction3  = DD_NOTHING;
input ENUM_DD_ACTION InpDDActionPreferred = DD_STOP_NEW;
input ENUM_DD_ACTION InpDDActionEmergency = DD_CLOSE_ALL_AND_STOP;

//====================================================================
// MODULE 25/26 - EXECUTION
//====================================================================
input group "=== M25 EXECUTION ==="
// MEASURED, not assumed. OANDA quoted spread on XAUUSD:
//   2012-2026 mean : $0.4824
//   2023-2026 mean : $0.7525   <- the regime you are actually trading in
//   terminal quote : $0.26     <- what every backtest above was costed with
// At a 1.8xATR stop on the 15-year mean ATR that is 0.056R vs 0.162R, which
// takes net expectancy at 8R from +0.2312R to +0.1253R - a 46% haircut, not
// the 17% an earlier summary claimed. Measure yours before trusting anything.
input double InpMaxSpread          = 1.20;  // Max spread in price units ($)
input double InpSpreadBuffer       = 0.05;
input int    InpSlippagePoints     = 30;
input int    InpMaxOrderRetries    = 3;
input int    InpRetryDelayMs       = 250;

//====================================================================
// MODULE 28 - QUALITY
//====================================================================
input group "=== M28 QUALITY ==="
input bool   InpAllowAPlus         = true;
input bool   InpAllowA             = true;
input bool   InpAllowBSetup        = false;
input bool   InpAllowCSetup        = false;
input double InpMinRR              = 2.0;   // Minimum RR to TP3 leg

//====================================================================
// MODULE 29 - MACRO (optional, soft)
//====================================================================
input group "=== M29 MACRO ==="
input bool   InpUseMacro           = false;
input string InpDXYSymbol          = "";
input string InpUS10YSymbol        = "";

//====================================================================
// MODULE 16/17 - UI + STATS
//====================================================================
input group "=== M16 UI / M17 STATS ==="
input bool   InpShowDashboard      = true;
input int    InpDashX              = 12;
input int    InpDashY              = 22;
input int    InpDashFontSize       = 9;
input bool   InpWriteTradeLog      = true;
input string InpTradeLogFile       = "XAUM15_trades.csv";
input bool   InpPrintStatsOnDeinit = true;

//====================================================================
// MODULE 32 - ABLATION SWITCHES (all default ON = full system)
//====================================================================
input group "=== M32 ABLATION ==="
input bool   InpAblSession         = true;
input bool   InpAblNews            = true;
input bool   InpAblRegime          = true;
input bool   InpAblLiquidity       = true;
input bool   InpAblAMD             = true;
input bool   InpAblVolumeProfile   = true;
input bool   InpAblVWAP            = true;
input bool   InpAblDisplacement    = true;
input bool   InpAblQuality         = true;

//--- shared runtime structures -------------------------------------
struct LiquidityLevel
  {
   double         price;
   ENUM_LIQ_TYPE  type;
   datetime       created;
   int            ageBars;
   int            strength;    // touches / confluence count
   bool           swept;
  };

struct SweepEvent
  {
   bool           valid;
   ENUM_SWEEP_SIDE side;
   double         level;       // liquidity price swept
   double         extreme;     // wick extreme reached
   datetime       time;
   int            barIndex;
   ENUM_LIQ_TYPE  liqType;
  };

struct StructureEvent
  {
   bool           valid;
   bool           bullish;
   double         brokenLevel;
   datetime       time;
   int            barIndex;
  };

struct TradeSignal
  {
   bool           valid;
   ENUM_SETUP_ID  setup;
   bool           isLong;
   double         entry;
   double         sl;
   double         tp[3];
   double         riskDistance;
   ENUM_QUALITY   quality;
   string         reason;
   // context snapshot for logging (spec 36)
   double         atr, vwap, poc, vah, val, liqLevel, spread;
   ENUM_SWEEP_SIDE sweepType;
   bool           mss, displacement;
  };

#endif // XAUM15_CONFIG_MQH
