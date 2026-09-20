// Test scaffold: the EA globals the extracted functions reference, plus
// scriptable stands-in for the two functions that need the whole EA.
#pragma once
#include "Config.mqh"
#include "DecisionLog.mqh"
#include "ctx_stub.h"

class CBrokerStub { public: double spread = 0.0; double Spread(void) const { return spread; } };

extern datetime       g_lastEntryBarTime;
extern datetime       g_lastBarTime;
extern string         g_blockReason;
extern TradeSignal    g_barCandidate;
extern CandidateAudit g_audit;
extern CDecisionLog   g_decisions;
extern CMarketContext g_ctx;
extern CBrokerStub    g_broker;

// iTime for the extracted IsNewBar
extern datetime g_fakeBarTime;
inline datetime iTime(const string, ENUM_TIMEFRAMES, int) { return g_fakeBarTime; }

// Scripted by each test. The extracted block decides WHEN to call them; the
// test decides what they return, so the control flow under test is the real
// one and only the leaves are stubs.
bool EntryGatesPass(const datetime now, string &why);
void TryEnter(const datetime now);
