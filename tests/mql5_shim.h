//===========================================================================
// mql5_shim.h - enough of the MQL5 runtime to compile and RUN the real
// XAUM15 sources under g++, so behaviour can be tested in a container that
// has no MetaTrader 5.
//
// This is a test scaffold. It is never compiled into the EA.
//===========================================================================
#pragma once
#include <string>
#include <cstdio>
#include <cstring>
#include <cstdlib>
#include <ctime>
#include <vector>
#include <map>
#include <iostream>

typedef std::string string;
typedef long long   datetime;
typedef unsigned char uchar;

//--- enums the EA sources rely on ------------------------------------------
enum ENUM_TIMEFRAMES { PERIOD_CURRENT=0, PERIOD_M1=1, PERIOD_M5=5, PERIOD_M15=15,
                       PERIOD_H1=60, PERIOD_H4=240 };

//--- file API --------------------------------------------------------------
#define INVALID_HANDLE (-1)
#define FILE_WRITE  0x0002
#define FILE_READ   0x0001
#define FILE_CSV    0x0008
#define FILE_ANSI   0x0020
#define SEEK_SET 0
#define SEEK_CUR 1
#define SEEK_END 2

namespace mqlshim {

struct FakeFile {
    std::string name;
    std::string buf;
    char sep = ',';
    bool open = false;
    bool write_fails = false;      // injectable I/O failure
};

inline std::vector<FakeFile>& files() { static std::vector<FakeFile> f; return f; }
inline int& lastError() { static int e = 0; return e; }
inline bool& openShouldFail() { static bool b = false; return b; }
inline std::map<std::string,std::string>& disk() {   // survives "restart"
    static std::map<std::string,std::string> d; return d; }
inline std::vector<std::string>& printed() { static std::vector<std::string> p; return p; }

inline void reset() {
    files().clear(); lastError()=0; openShouldFail()=false;
    disk().clear(); printed().clear();
}
} // namespace mqlshim

inline int FileOpen(const string name, int flags, char sep=',') {
    if (mqlshim::openShouldFail()) { mqlshim::lastError() = 5004; return INVALID_HANDLE; }
    mqlshim::FakeFile f;
    f.name = name; f.sep = sep; f.open = true;
    // FILE_READ|FILE_WRITE on an existing file keeps the content (append mode
    // is reached by the FileSeek(SEEK_END) the caller does next).
    if ((flags & FILE_READ) && mqlshim::disk().count(name))
        f.buf = mqlshim::disk()[name];
    mqlshim::files().push_back(f);
    return (int)mqlshim::files().size() - 1;
}
inline void FileClose(int h) {
    if (h < 0 || h >= (int)mqlshim::files().size()) return;
    mqlshim::files()[h].open = false;
    mqlshim::disk()[mqlshim::files()[h].name] = mqlshim::files()[h].buf;
}
inline void FileSeek(int, long, int) { /* append semantics modelled by buf */ }
inline long FileTell(int h) {
    if (h < 0 || h >= (int)mqlshim::files().size()) return 0;
    return (long)mqlshim::files()[h].buf.size();
}
inline void FileFlush(int h) {
    if (h < 0 || h >= (int)mqlshim::files().size()) return;
    mqlshim::disk()[mqlshim::files()[h].name] = mqlshim::files()[h].buf;
}
inline int GetLastError() { return mqlshim::lastError(); }

//--- FileWrite: MQL5 joins the arguments with the separator and appends a
//    newline. It does NOT quote or escape anything. That behaviour is
//    reproduced exactly, because the CSV-safety tests depend on it.
inline void fw_emit(int h, const std::string& s) {
    if (h < 0 || h >= (int)mqlshim::files().size()) return;
    if (mqlshim::files()[h].write_fails) { mqlshim::lastError() = 5004; return; }
    mqlshim::files()[h].buf += s;
}
inline std::string fw_str(const std::string& s) { return s; }
inline std::string fw_str(const char* s) { return std::string(s); }
inline std::string fw_str(int v) { return std::to_string(v); }
inline std::string fw_str(long v) { return std::to_string(v); }
inline std::string fw_str(long long v) { return std::to_string(v); }
inline std::string fw_str(double v) { char b[64]; snprintf(b,64,"%g",v); return b; }

template <typename T>
inline void fw_rec(int h, bool& first, T v) {
    if (!first) fw_emit(h, std::string(1, mqlshim::files()[h].sep));
    fw_emit(h, fw_str(v)); first = false;
}
template <typename T, typename... R>
inline void fw_rec(int h, bool& first, T v, R... rest) {
    fw_rec(h, first, v); fw_rec(h, first, rest...);
}
template <typename... A>
inline void FileWrite(int h, A... args) {
    if (h < 0 || h >= (int)mqlshim::files().size()) return;
    bool first = true;
    fw_rec(h, first, args...);
    fw_emit(h, "\n");
}

//--- string helpers --------------------------------------------------------
inline const char* fmt_arg(const std::string& s) { return s.c_str(); }
inline const char* fmt_arg(const char* s)        { return s; }
template <typename T> inline T fmt_arg(T v)      { return v; }

template <typename... A>
inline string StringFormat(const string f, A... args) {
    char buf[4096];
    snprintf(buf, sizeof(buf), f.c_str(), fmt_arg(args)...);
    return string(buf);
}
inline int StringFind(const string s, const string what, int start=0) {
    size_t p = s.find(what, (size_t)start);
    return p == std::string::npos ? -1 : (int)p;
}
inline int StringLen(const string s) { return (int)s.size(); }
inline string StringSubstr(const string s, int start, int count=-1) {
    if (start >= (int)s.size()) return "";
    return count < 0 ? s.substr(start) : s.substr(start, count);
}
inline int StringReplace(string& s, const string from, const string to) {
    if (from.empty()) return 0;
    int n = 0; size_t p = 0;
    while ((p = s.find(from, p)) != std::string::npos) {
        s.replace(p, from.size(), to); p += to.size(); n++;
    }
    return n;
}

inline string DoubleToString(double v, int digits=8) {
    char b[64]; snprintf(b, 64, "%.*f", digits, v); return b;
}
inline string IntegerToString(long long v, int=0, char=' ') { return std::to_string(v); }

#define TIME_DATE    1
#define TIME_MINUTES 2
#define TIME_SECONDS 4
inline string TimeToString(datetime t, int mode = TIME_DATE|TIME_MINUTES) {
    time_t tt = (time_t)t; struct tm g; gmtime_r(&tt, &g);
    char b[64];
    if (mode == TIME_DATE) strftime(b, 64, "%Y.%m.%d", &g);
    else if (mode == TIME_MINUTES) strftime(b, 64, "%H:%M", &g);
    else strftime(b, 64, "%Y.%m.%d %H:%M", &g);
    return b;
}
inline string EnumToString(ENUM_TIMEFRAMES p) {
    switch (p) { case PERIOD_M1: return "PERIOD_M1"; case PERIOD_M5: return "PERIOD_M5";
                 case PERIOD_M15: return "PERIOD_M15"; case PERIOD_H1: return "PERIOD_H1";
                 case PERIOD_H4: return "PERIOD_H4"; default: return "PERIOD_CURRENT"; }
}

inline void Print(const string s) { mqlshim::printed().push_back(s); }
template <typename... A>
inline void PrintFormat(const string f, A... args) { Print(StringFormat(f, args...)); }

//--- terminal globals ------------------------------------------------------
extern string          _Symbol;
extern ENUM_TIMEFRAMES _Period;
