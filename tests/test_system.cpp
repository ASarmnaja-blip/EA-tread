//===========================================================================
// System tests for Track 1.1 (schema v2) and Track 1.2 (decision log).
//
// These COMPILE AND RUN the production source. ZeroSignal, StampSignalContext,
// IsNewBar, LogBarDecision, the new-bar decision block and the whole of
// DecisionLog.mqh are extracted verbatim by tests/extract_source.py; only the
// leaves (EntryGatesPass, TryEnter, market context, broker) are stubs, so the
// control flow under test is the real one.
//===========================================================================
#include "build/Config.mqh"
#include "build/ctx_stub.h"
#include "build/DecisionLog.mqh"
#include "build/setups_extract.h"
#include "build/ea_stub.h"
#include "build/ea_extract.h"
#include <algorithm>
#include <cmath>

//--- terminal + input globals ----------------------------------------------
string          _Symbol = "XAUUSD";
ENUM_TIMEFRAMES _Period = PERIOD_M15;
bool   InpWriteDecisionLog = true;
string InpDecisionLogFile  = "XAUM15_decisions.csv";
double InpTrendZoneMin = 1.08, InpTrendZoneMax = 7.21;
int    InpTrendSmaPeriod = 200;

//--- EA globals -------------------------------------------------------------
datetime       g_lastEntryBarTime = 0;
datetime       g_lastBarTime      = 0;
datetime       g_fakeBarTime      = 0;
string         g_blockReason      = "";
TradeSignal    g_barCandidate;
CandidateAudit g_audit;
CDecisionLog   g_decisions;
CMarketContext g_ctx;
CBrokerStub    g_broker;

//--- the script a test hands to the stubbed leaves ---------------------------
enum Outcome { OUT_NO_SIGNAL, OUT_CANDIDATE_REJECTED, OUT_ORDER_REJECTED, OUT_ORDER_ACCEPTED };
struct Script {
    bool    gatePass = true;
    string  gateWhy  = "";
    Outcome outcome  = OUT_NO_SIGNAL;
    string  nastyRule = "";          // injected into invalidationRule
    string  nastyEvidence = "";
};
static Script g_script;

bool EntryGatesPass(const datetime, string &why) {
    why = g_script.gatePass ? "" : g_script.gateWhy;
    return g_script.gatePass;
}

// Mirrors only the OBSERVABLE effects of the real TryEnter on shared state.
void TryEnter(const datetime) {
    g_audit.evaluationRan = true;
    g_audit.enabled[SETUP_D] = true;
    g_audit.state = CAND_EVALUATED_NO_SIGNAL;
    if (g_script.outcome == OUT_NO_SIGNAL) { g_blockReason = "no qualifying setup"; return; }

    g_audit.produced[SETUP_D]++; g_audit.qualityAllowed[SETUP_D]++; g_audit.totalProduced++;
    g_barCandidate.valid = true;
    g_barCandidate.setup = SETUP_D;
    g_barCandidate.isLong = true;
    g_barCandidate.entry = 4200.50;
    g_barCandidate.sl = 4180.25;
    g_barCandidate.reason = "D:trend zone z=2.31";
    StampSignalContext(g_barCandidate, g_ctx, 1);
    g_barCandidate.invalidation = 4190.00;
    g_barCandidate.invalidationRule = g_script.nastyRule.empty()
        ? "z leaves the zone at the near edge" : g_script.nastyRule;
    g_barCandidate.evidence = g_script.nastyEvidence.empty()
        ? "z inside tested zone" : g_script.nastyEvidence;
    g_audit.state = CAND_CANDIDATE_SIGNAL;

    if (g_script.outcome == OUT_CANDIDATE_REJECTED) {
        g_blockReason = "min lot = 2.04% risk > 1.00% cap"; return;
    }
    g_audit.state = CAND_ORDER_ATTEMPTED;
    if (g_script.outcome == OUT_ORDER_REJECTED) {
        g_audit.state = CAND_ORDER_REJECTED;
        g_blockReason = "order rejected: invalid stops"; return;
    }
    g_audit.state = CAND_ORDER_ACCEPTED;
    g_lastEntryBarTime = g_lastBarTime;
    g_blockReason = "";
}

//===========================================================================
// tiny test framework
//===========================================================================
static int g_pass = 0, g_fail = 0;
static std::vector<std::string> g_failures;
static std::string g_section;

static void section(const char* s) { g_section = s; }
static void check(bool ok, const std::string& id, const std::string& what) {
    if (ok) { g_pass++; printf("  PASS  %-9s %s\n", id.c_str(), what.c_str()); }
    else { g_fail++; printf("  FAIL  %-9s %s\n", id.c_str(), what.c_str());
           g_failures.push_back(id + "  " + what); }
}

//--- CSV parsers: naive (what a plain split does) and RFC4180 ---------------
static std::vector<std::string> split_naive(const std::string& line) {
    std::vector<std::string> out; std::string cur;
    for (char c : line) { if (c == ',') { out.push_back(cur); cur.clear(); } else cur += c; }
    out.push_back(cur); return out;
}
static std::vector<std::string> split_rfc4180(const std::string& line) {
    std::vector<std::string> out; std::string cur; bool inq = false;
    for (size_t i = 0; i < line.size(); i++) {
        char c = line[i];
        if (inq) {
            if (c == '"') { if (i + 1 < line.size() && line[i+1] == '"') { cur += '"'; i++; } else inq = false; }
            else cur += c;
        } else if (c == '"') inq = true;
        else if (c == ',') { out.push_back(cur); cur.clear(); }
        else cur += c;
    }
    out.push_back(cur); return out;
}
static std::vector<std::string> lines_of(const std::string& name) {
    std::vector<std::string> out; std::string cur;
    auto it = mqlshim::disk().find(name);
    if (it == mqlshim::disk().end()) return out;
    for (char c : it->second) { if (c == '\n') { out.push_back(cur); cur.clear(); } else cur += c; }
    if (!cur.empty()) out.push_back(cur);
    return out;
}

//--- a fresh world for each test -------------------------------------------
static void fresh(bool logging = true) {
    mqlshim::reset();
    InpWriteDecisionLog = logging;
    g_decisions = CDecisionLog();
    g_audit.Reset();
    ZeroSignal(g_barCandidate);
    g_lastBarTime = 0; g_lastEntryBarTime = 0; g_fakeBarTime = 0;
    g_blockReason = "";
    g_script = Script();
    g_ctx.regime = REG_TREND_UP; g_ctx.zscore = 2.31; g_ctx.atrValue = 11.35;
    g_ctx.bars = 100;
    for (int i = 0; i < 100; i++) g_ctx.rates[i].time = 1700000000LL - i * 900;
    g_broker.spread = 0.75;
    g_decisions.Init(InpDecisionLogFile);
}

// a decision is (was TryEnter effective, block reason, audit state)
struct Decision { bool traded; string reason; int state; };
static bool operator!=(const Decision& a, const Decision& b) {
    return a.traded != b.traded || a.reason != b.reason || a.state != b.state;
}
static Decision drive_bar(datetime t, const Script& sc) {
    g_script = sc;
    g_lastBarTime = t;
    RunNewBarBlock(t);
    return { g_lastEntryBarTime == g_lastBarTime, g_blockReason, (int)g_audit.state };
}

//===========================================================================
int main() {
    printf("======================================================================\n");
    printf("SYSTEM TESTS - Track 1.1 / 1.2   (executable, real production source)\n");
    printf("======================================================================\n");

    //=====================================================================
    section("1");
    printf("\n[1] TradeSignal lifecycle\n");

    {   // T1.1 - ZeroSignal clears every field, checked by value at runtime
        TradeSignal s;
        s.valid=true; s.setup=SETUP_A; s.isLong=true; s.entry=1; s.sl=2;
        s.tp[0]=3; s.tp[1]=4; s.tp[2]=5; s.riskDistance=6; s.quality=Q_APLUS;
        s.reason="x"; s.atr=7; s.vwap=8; s.poc=9; s.vah=10; s.val=11;
        s.liqLevel=12; s.spread=13; s.sweepType=SWEEP_HIGH; s.mss=true;
        s.displacement=true; s.symbol="Z"; s.timeframe=PERIOD_H1;
        s.regime=REG_HIGH_VOL; s.regimeScore=14; s.confidence=0.9;
        s.invalidation=15; s.invalidationRule="r"; s.expiryBars=99;
        s.expiryTime=123; s.formedAt=456; s.riskR=2; s.evidence="e";
        s.pricedIn="p"; s.newsRisk="n"; s.decision="TRADE"; s.decisionReason="d";
        ZeroSignal(s);
        bool ok = !s.valid && s.setup==SETUP_NONE && !s.isLong && s.entry==0 &&
                  s.sl==0 && s.tp[0]==0 && s.tp[1]==0 && s.tp[2]==0 &&
                  s.riskDistance==0 && s.quality==Q_NONE && s.reason=="" &&
                  s.atr==0 && s.vwap==0 && s.poc==0 && s.vah==0 && s.val==0 &&
                  s.liqLevel==0 && s.spread==0 && s.sweepType==SWEEP_NONE &&
                  !s.mss && !s.displacement && s.symbol=="" &&
                  s.timeframe==PERIOD_CURRENT && s.regime==REG_NONE &&
                  s.regimeScore==0 && s.confidence==-1.0 && s.invalidation==0 &&
                  s.invalidationRule=="" && s.expiryBars==-1 && s.expiryTime==0 &&
                  s.formedAt==0 && s.riskR==0 && s.evidence=="" &&
                  s.pricedIn=="" && s.newsRisk=="" && s.decision=="" &&
                  s.decisionReason=="";
        check(ok, "T1.1", "ZeroSignal resets all 37 members to zero/sentinel");
    }

    {   // T1.2 - no carry-over between bars
        fresh();
        Script a; a.outcome = OUT_ORDER_ACCEPTED;
        drive_bar(1700000000LL, a);
        Script b; b.gatePass = false; b.gateWhy = "cooldown after trade";
        drive_bar(1700000900LL, b);
        bool clean = g_barCandidate.setup == SETUP_NONE &&
                     g_barCandidate.entry == 0 && g_barCandidate.sl == 0 &&
                     g_barCandidate.evidence == "" &&
                     g_barCandidate.invalidation == 0 &&
                     g_barCandidate.symbol == "";
        check(clean, "T1.2", "gate-blocked bar carries nothing from the traded bar");
    }

    {   // T1.3 - sentinels after a real StampSignalContext
        fresh();
        Script s; s.outcome = OUT_CANDIDATE_REJECTED;
        drive_bar(1700000000LL, s);
        bool ok = g_barCandidate.confidence == -1.0 &&
                  g_barCandidate.expiryBars == -1 &&
                  g_barCandidate.expiryTime == 0 &&
                  g_barCandidate.riskR == 1.0 &&
                  g_barCandidate.pricedIn.rfind("not assessed", 0) == 0 &&
                  g_barCandidate.newsRisk.rfind("not assessed", 0) == 0;
        check(ok, "T1.3", "unassessed fields hold their declared sentinels");
    }

    {   // T1.4 - confidence/expiry cannot move a decision
        std::vector<Decision> base, mutated;
        std::vector<Script> plan = {
            Script(), Script(), Script(), Script()
        };
        plan[0].outcome = OUT_NO_SIGNAL;
        plan[1].outcome = OUT_CANDIDATE_REJECTED;
        plan[2].outcome = OUT_ORDER_ACCEPTED;
        plan[3].gatePass = false; plan[3].gateWhy = "spread 1.50 > max 1.20";

        fresh();
        for (size_t i = 0; i < plan.size(); i++) base.push_back(drive_bar(1700000000LL + i*900, plan[i]));
        fresh();
        for (size_t i = 0; i < plan.size(); i++) {
            Decision d = drive_bar(1700000000LL + i*900, plan[i]);
            // poison the two fields AFTER the stamp, before the next bar
            g_barCandidate.confidence = 0.99;
            g_barCandidate.expiryBars = 7;
            g_barCandidate.expiryTime = 1700009999LL;
            mutated.push_back(d);
        }
        bool same = base.size() == mutated.size();
        for (size_t i = 0; same && i < base.size(); i++) if (base[i] != mutated[i]) same = false;
        check(same, "T1.4", "confidence/expiry values do not alter the decision sequence");
    }

    //=====================================================================
    section("2");
    printf("\n[2] Decision logging\n");

    {   // T2.1 - header and data row agree on column count
        fresh();
        Script s; s.outcome = OUT_ORDER_ACCEPTED;
        drive_bar(1700000000LL, s);
        auto L = lines_of(InpDecisionLogFile);
        bool ok = L.size() == 2 &&
                  split_rfc4180(L[0]).size() == split_rfc4180(L[1]).size();
        check(ok, "T2.1", "header column count == data row column count (" +
              std::to_string(L.empty()?0:split_rfc4180(L[0]).size()) + ")");
    }

    {   // T2.2 - separators inside strings must not break the row
        fresh();
        Script s; s.outcome = OUT_CANDIDATE_REJECTED;
        s.nastyRule = "premise is dead, regardless of the stop";
        s.nastyEvidence = "he said \"value\", then a newline\nhere";
        drive_bar(1700000000LL, s);
        auto L = lines_of(InpDecisionLogFile);
        size_t hdr = L.empty() ? 0 : split_rfc4180(L[0]).size();
        bool one_row = (L.size() == 2);
        bool cols_ok = one_row && split_rfc4180(L[1]).size() == hdr;
        check(one_row && cols_ok, "T2.2",
              "comma/quote/newline inside a field stay inside that field");
        if (!(one_row && cols_ok)) {
            printf("          evidence: header has %zu columns, file has %zu line(s)\n",
                   hdr, L.size());
            for (size_t i = 1; i < L.size() && i < 4; i++)
                printf("          line %zu parses as %zu columns: %.110s\n",
                       i, split_rfc4180(L[i]).size(), L[i].c_str());
        }
    }

    {   // T2.3 - a file that will not open must not change decisions
        std::vector<Decision> withFile, noFile;
        std::vector<Script> plan(3);
        plan[0].outcome = OUT_CANDIDATE_REJECTED;
        plan[1].outcome = OUT_ORDER_ACCEPTED;
        plan[2].gatePass = false; plan[2].gateWhy = "news: NFP";

        fresh();
        for (size_t i=0;i<plan.size();i++) withFile.push_back(drive_bar(1700000000LL+i*900, plan[i]));

        mqlshim::reset(); InpWriteDecisionLog = true;
        mqlshim::openShouldFail() = true;
        g_decisions = CDecisionLog(); g_audit.Reset(); ZeroSignal(g_barCandidate);
        g_lastBarTime=0; g_lastEntryBarTime=0; g_blockReason="";
        g_ctx.regime=REG_TREND_UP; g_ctx.zscore=2.31; g_ctx.atrValue=11.35; g_ctx.bars=100;
        g_broker.spread=0.75;
        g_decisions.Init(InpDecisionLogFile);          // fails
        for (size_t i=0;i<plan.size();i++) noFile.push_back(drive_bar(1700000000LL+i*900, plan[i]));

        bool same = withFile.size()==noFile.size();
        for (size_t i=0; same && i<withFile.size(); i++) if (withFile[i]!=noFile[i]) same=false;
        check(same, "T2.3", "FileOpen failure leaves the decision sequence identical");
    }

    {   // T2.4 - write failure mid-run must not change decisions or crash
        fresh();
        Script s; s.outcome = OUT_ORDER_ACCEPTED;
        drive_bar(1700000000LL, s);
        for (auto& f : mqlshim::files()) f.write_fails = true;
        Decision d = drive_bar(1700000900LL, s);
        check(d.traded && d.state == CAND_ORDER_ACCEPTED, "T2.4",
              "write failure does not change the decision or abort the bar");
    }

    {   // T2.5 - logging on vs off
        std::vector<Decision> on, off;
        std::vector<Script> plan(4);
        plan[0].outcome=OUT_NO_SIGNAL;
        plan[1].outcome=OUT_ORDER_REJECTED;
        plan[2].outcome=OUT_ORDER_ACCEPTED;
        plan[3].gatePass=false; plan[3].gateWhy="daily target +3.00% reached";
        fresh(true);
        for (size_t i=0;i<plan.size();i++) on.push_back(drive_bar(1700000000LL+i*900, plan[i]));
        fresh(false);
        for (size_t i=0;i<plan.size();i++) off.push_back(drive_bar(1700000000LL+i*900, plan[i]));
        bool same = on.size()==off.size();
        for (size_t i=0; same && i<on.size(); i++) if (on[i]!=off[i]) same=false;
        bool nofile = lines_of(InpDecisionLogFile).empty();
        check(same && nofile, "T2.5", "file writing on/off gives identical decisions; off writes nothing");
    }

    {   // T2.6 - the header is not counted as a data row
        fresh();
        Script s; s.outcome = OUT_NO_SIGNAL;
        drive_bar(1700000000LL, s);
        drive_bar(1700000900LL, s);
        auto L = lines_of(InpDecisionLogFile);
        check(g_decisions.Rows() == 2 && L.size() == 3, "T2.6",
              "Rows()=2 data rows while the file holds 3 lines incl. header");
    }

    //=====================================================================
    section("3");
    printf("\n[3] Gate behaviour\n");

    {   // T3.1 - same branch as the pre-Track-1 two-liner
        std::vector<std::pair<bool,string>> cases = {
            {true, ""}, {false, "cooldown after trade"}, {false, "news: CPI"}, {true, ""}
        };
        bool same = true;
        for (auto& c : cases) {
            // reference: the original lines, reproduced exactly
            string refReason = "";
            bool refCalled = false;
            { string why = c.second; if (c.first) refCalled = true; else refReason = why; }
            fresh();
            Script s; s.gatePass = c.first; s.gateWhy = c.second; s.outcome = OUT_NO_SIGNAL;
            drive_bar(1700000000LL, s);
            bool called = g_audit.evaluationRan;
            string reason = c.first ? "" : g_blockReason;
            if (called != refCalled || reason != refReason) same = false;
        }
        check(same, "T3.1", "gate pass/fail takes the same branch as the original logic");
    }

    {   // T3.2 - blocked bar is logged as not evaluated
        fresh();
        Script s; s.gatePass = false; s.gateWhy = "extreme volatility";
        drive_bar(1700000000LL, s);
        auto L = lines_of(InpDecisionLogFile);
        auto hdr = split_rfc4180(L[0]); auto row = split_rfc4180(L[1]);
        auto col = [&](const char* n) {
            for (size_t i=0;i<hdr.size();i++) if (hdr[i]==n) return row.size()>i?row[i]:string("");
            return string("<missing>"); };
        bool ok = col("evaluation_ran")=="0" && col("candidates_produced")=="0" &&
                  col("candidate_state")=="NOT_EVALUATED" &&
                  col("decision")=="NO_TRADE" &&
                  col("decision_reason").rfind("gate_blocked_before_evaluation",0)==0;
        check(ok, "T3.2", "gate-blocked bar records NOT_EVALUATED and says so in the reason");
    }

    {   // T3.3 - nothing invented when CollectSignal never ran
        fresh();
        Script s; s.gatePass = false; s.gateWhy = "spread 1.90 > max 1.20";
        drive_bar(1700000000LL, s);
        auto L = lines_of(InpDecisionLogFile);
        auto hdr = split_rfc4180(L[0]); auto row = split_rfc4180(L[1]);
        auto col = [&](const char* n) {
            for (size_t i=0;i<hdr.size();i++) if (hdr[i]==n) return row.size()>i?row[i]:string("");
            return string("<missing>"); };
        bool ok = col("setup")=="" && col("direction")=="" &&
                  std::stod(col("entry"))==0.0 && std::stod(col("sl"))==0.0 &&
                  col("evidence")=="" && col("invalidation_rule")=="";
        check(ok, "T3.3", "no setup, direction, price or evidence is fabricated");
    }

    //=====================================================================
    section("4");
    printf("\n[4] Candidate accounting\n");

    {   // T4.1 - the six observable states are reachable and distinct
        struct C { Script s; ENUM_CANDIDATE_STATE want; const char* name; };
        std::vector<C> cases(4);
        cases[0].s.gatePass=false; cases[0].s.gateWhy="x"; cases[0].want=CAND_NOT_EVALUATED; cases[0].name="NOT_EVALUATED";
        cases[1].s.outcome=OUT_NO_SIGNAL;          cases[1].want=CAND_EVALUATED_NO_SIGNAL; cases[1].name="EVALUATED_NO_SIGNAL";
        cases[2].s.outcome=OUT_CANDIDATE_REJECTED; cases[2].want=CAND_CANDIDATE_SIGNAL;    cases[2].name="CANDIDATE_SIGNAL";
        cases[3].s.outcome=OUT_ORDER_REJECTED;     cases[3].want=CAND_ORDER_REJECTED;      cases[3].name="ORDER_REJECTED";
        bool ok = true;
        for (auto& c : cases) { fresh(); drive_bar(1700000000LL, c.s); if (g_audit.state != c.want) ok = false; }
        fresh(); Script acc; acc.outcome=OUT_ORDER_ACCEPTED; drive_bar(1700000000LL, acc);
        if (g_audit.state != CAND_ORDER_ACCEPTED) ok = false;
        check(ok, "T4.1", "5 states reached exactly; ORDER_ATTEMPTED is a transient of the accept/reject pair");
    }

    {   // T4.2 - POSITION_OPENED must never be claimed
        bool everSet = false;
        std::vector<Script> plan(4);
        plan[0].outcome=OUT_NO_SIGNAL; plan[1].outcome=OUT_CANDIDATE_REJECTED;
        plan[2].outcome=OUT_ORDER_REJECTED; plan[3].outcome=OUT_ORDER_ACCEPTED;
        fresh();
        for (size_t i=0;i<plan.size();i++) {
            drive_bar(1700000000LL+i*900, plan[i]);
            if (g_audit.state == CAND_POSITION_OPENED) everSet = true;
        }
        check(!everSet, "T4.2", "POSITION_OPENED is never emitted (not observable in Track 1.2)");
    }

    //=====================================================================
    section("5");
    printf("\n[5] Boundary and error conditions\n");

    {   // T5.1 - Write before Init must not crash or corrupt
        mqlshim::reset(); InpWriteDecisionLog = true;
        g_decisions = CDecisionLog(); g_audit.Reset(); ZeroSignal(g_barCandidate);
        g_blockReason=""; g_lastBarTime=0; g_lastEntryBarTime=0;
        g_ctx.bars=100; g_ctx.atrValue=11.35; g_broker.spread=0.75;
        Script s; s.outcome = OUT_NO_SIGNAL;
        drive_bar(1700000000LL, s);                 // Init never called
        check(g_decisions.Rows()==1 && lines_of(InpDecisionLogFile).empty(),
              "T5.1", "Write before Init counts the bar but writes no file, no crash");
    }

    {   // T5.2 / T5.3 - indicator not ready, warm-up
        fresh(); g_ctx.atrValue = 0.0; g_ctx.bars = 0; g_ctx.zscore = 0.0;
        Script s; s.outcome = OUT_NO_SIGNAL;
        drive_bar(1700000000LL, s);
        auto L = lines_of(InpDecisionLogFile);
        check(L.size()==2 && split_rfc4180(L[1]).size()==split_rfc4180(L[0]).size(),
              "T5.2/3", "ATR=0 and bars=0 (warm-up) still produce one well-formed row");
    }

    {   // T5.4 - invalid price / ATR
        fresh(); g_ctx.atrValue = -1.0; g_broker.spread = std::nan("");
        Script s; s.outcome = OUT_CANDIDATE_REJECTED;
        drive_bar(1700000000LL, s);
        auto L = lines_of(InpDecisionLogFile);
        check(L.size()==2 && split_rfc4180(L[1]).size()==split_rfc4180(L[0]).size(),
              "T5.4", "negative ATR and NaN spread do not break the row shape");
    }

    {   // T5.5 - permission failure
        mqlshim::reset(); InpWriteDecisionLog = true; mqlshim::openShouldFail() = true;
        g_decisions = CDecisionLog();
        bool ret = g_decisions.Init(InpDecisionLogFile);
        bool logged = false;
        for (auto& p : mqlshim::printed()) if (p.find("cannot open") != std::string::npos) logged = true;
        check(!ret && logged, "T5.5", "open failure returns false and prints the error");
    }

    {   // T5.6 - duplicate timestamps
        fresh();
        Script s; s.outcome = OUT_NO_SIGNAL;
        drive_bar(1700000000LL, s);
        drive_bar(1700000000LL, s);
        check(g_decisions.Rows()==2 && lines_of(InpDecisionLogFile).size()==3,
              "T5.6", "two bars with the same timestamp produce two rows, no overwrite");
    }

    {   // T5.7 - IsNewBar, the real function
        fresh();
        g_fakeBarTime = 0;              bool a = IsNewBar();
        g_fakeBarTime = 1700000000LL;   bool b = IsNewBar();
        bool c = IsNewBar();
        g_fakeBarTime = 1700000900LL;   bool d = IsNewBar();
        check(!a && b && !c && d, "T5.7",
              "IsNewBar: 0 -> false, new time -> true, same time -> false, next -> true");
    }

    {   // T5.8 / T5.9 - restart mid-day onto an existing CSV
        fresh();
        Script s; s.outcome = OUT_NO_SIGNAL;
        drive_bar(1700000000LL, s);
        g_decisions.Close();
        size_t before = lines_of(InpDecisionLogFile).size();
        g_decisions = CDecisionLog();
        g_decisions.Init(InpDecisionLogFile);     // restart
        drive_bar(1700000900LL, s);
        g_decisions.Close();
        auto L = lines_of(InpDecisionLogFile);
        int headers = 0;
        for (auto& l : L) if (l.rfind("date,", 0) == 0) headers++;
        check(before==2 && L.size()==3 && headers==1, "T5.8/9",
              "restart appends to the existing CSV and writes no second header");
    }

    {   // T5.10 - empty and very long strings
        fresh();
        Script s; s.outcome = OUT_CANDIDATE_REJECTED;
        s.nastyRule = "";
        s.nastyEvidence = std::string(3000, 'x');
        drive_bar(1700000000LL, s);
        auto L = lines_of(InpDecisionLogFile);
        bool ok = L.size()==2 && split_rfc4180(L[1]).size()==split_rfc4180(L[0]).size();
        check(ok, "T5.10", "empty and 3000-char strings keep the row shape");
    }

    //=====================================================================
    section("6");
    printf("\n[6] Inertness A/B over a synthetic sequence\n");

    {
        std::vector<Script> plan;
        for (int i = 0; i < 40; i++) {
            Script s;
            int m = i % 5;
            if (m == 0) { s.gatePass = false; s.gateWhy = "cooldown after trade"; }
            else if (m == 1) s.outcome = OUT_NO_SIGNAL;
            else if (m == 2) s.outcome = OUT_CANDIDATE_REJECTED;
            else if (m == 3) s.outcome = OUT_ORDER_REJECTED;
            else s.outcome = OUT_ORDER_ACCEPTED;
            plan.push_back(s);
        }
        std::vector<Decision> on, off;
        fresh(true);
        for (size_t i=0;i<plan.size();i++) on.push_back(drive_bar(1700000000LL+i*900, plan[i]));
        fresh(false);
        for (size_t i=0;i<plan.size();i++) off.push_back(drive_bar(1700000000LL+i*900, plan[i]));
        size_t diff = 0;
        for (size_t i=0;i<on.size();i++) if (on[i]!=off[i]) diff++;
        check(diff==0, "T6.1", "40-bar decision sequence identical with file writing on and off");

        // T6.2 - the decisive one. The current block, logging and all, against
        // the block as it stood before Track 1 existed, pulled from git. Only
        // (traded, reason) are compared: the audit state is a Track 1.2 concept
        // the baseline has no opinion about.
        struct BD { bool traded; string reason; };
        std::vector<BD> cur, base_;
        fresh(true);
        for (size_t i=0;i<plan.size();i++) {
            g_script = plan[i]; g_lastBarTime = 1700000000LL + (datetime)i*900;
            RunNewBarBlock(g_lastBarTime);
            cur.push_back({ g_lastEntryBarTime == g_lastBarTime, g_blockReason });
        }
        fresh(true);
        for (size_t i=0;i<plan.size();i++) {
            g_script = plan[i]; g_lastBarTime = 1700000000LL + (datetime)i*900;
            ZeroSignal(g_barCandidate); g_audit.Reset();   // harness parity only
            RunNewBarBlockBaseline(g_lastBarTime);
            base_.push_back({ g_lastEntryBarTime == g_lastBarTime, g_blockReason });
        }
        size_t d2 = 0;
        for (size_t i=0;i<cur.size();i++)
            if (cur[i].traded != base_[i].traded || cur[i].reason != base_[i].reason) d2++;
        check(d2==0, "T6.2",
              "current block matches the pre-Track-1 block from git on all 40 bars");
    }

    //=====================================================================
    printf("\n----------------------------------------------------------------------\n");
    printf("passed %d, failed %d\n", g_pass, g_fail);
    for (auto& f : g_failures) printf("  FAILED: %s\n", f.c_str());
    return g_fail == 0 ? 0 : 1;
}
