#include "host_link.h"
#include <Arduino.h>
#include <stdlib.h>
#include <string.h>
namespace {
constexpr int MaxFields = 13;
int split(char *text, char **fields) {
    int n = 0; fields[n++] = text;
    for (char *p = text; *p && n < MaxFields; ++p) if (*p == '\t') { *p = 0; fields[n++] = p + 1; }
    return n;
}
void copy(char *dst, size_t size, const char *src) { strncpy(dst, src, size - 1); dst[size - 1] = 0; }
bool unknown(const char *f) { return !f || !*f || !strcmp(f, "-"); }
// "x:value,x:value,..." with x in 0..LossHistory-1, ascending.
void parseSeries(char *text, LossSeries &series) {
    series = {};
    for (char *p = text; *p && series.count < LossHistory; ) {
        char *end; long x = strtol(p, &end, 10);
        if (end == p || *end != ':') break;
        p = end + 1;
        float v = strtof(p, &end);
        if (end == p) break;
        series.x[series.count] = uint8_t(constrain(x, 0, long(LossHistory) - 1)); series.v[series.count++] = v;
        p = *end == ',' ? end + 1 : end;
    }
}
void setLimit(Limit &l, char **f, int n) {
    l = {};
    if (n < 4 || unknown(f[2])) return;
    l.has = true; l.usedPct = strtof(f[2], nullptr);
    if (!unknown(f[3])) { l.hasReset = true; l.resetSeconds = strtoul(f[3], nullptr, 10); }
}
}
void HostLink::handleLine(char *text, Telemetry &live, uint32_t now) {
    if (!strcmp(text, "VH1 BEGIN")) { stage = {}; stage.linked = true; return; }
    if (!stage.linked) return;   // ignore lines outside BEGIN..END
    char *f[MaxFields]; int n = split(text, f);
    if (!strcmp(f[0], "SESSION") && n >= 5 && stage.sessionCount < 8) {
        AgentSession &s = stage.sessions[stage.sessionCount++];
        s = {}; copy(s.provider, sizeof(s.provider), f[1]); copy(s.profile, sizeof(s.profile), f[2]);
        int status = atoi(f[3]); s.status = status == 0 ? SessionStatus::Working : status == 1 ? SessionStatus::NeedsUser : SessionStatus::Inactive;
        copy(s.title, sizeof(s.title), f[4]);
    } else if (!strcmp(f[0], "LIMIT") && n >= 3) {
        if (f[1][0] == 'h') setLimit(stage.hourly, f, n); else if (f[1][0] == 'w') setLimit(stage.weekly, f, n);
    } else if (!strcmp(f[0], "RUN") && n >= 11 && stage.runCount < 4) {
        TrainingRun &r = stage.runs[stage.runCount++];
        r = {}; copy(r.id, sizeof(r.id), f[1]); copy(r.name, sizeof(r.name), f[2]);
        r.state = RunState(constrain(atoi(f[3]), 0, 3));
        if (!unknown(f[4])) { r.hasProgress = true; r.progress = strtof(f[4], nullptr); }
        if (!unknown(f[5])) { r.hasRate = true; r.rate = strtof(f[5], nullptr); }
        if (!unknown(f[6])) { r.hasEta = true; r.etaSeconds = strtoul(f[6], nullptr, 10); }
        if (!unknown(f[7])) { r.hasGpu = true; r.gpu = strtof(f[7], nullptr); }
        if (!unknown(f[8]) && !unknown(f[9])) { r.hasVram = true; r.vramUsed = strtof(f[8], nullptr); r.vramTotal = strtof(f[9], nullptr); }
        if (!unknown(f[10])) {
            parseSeries(f[10], r.train);
            r.hasLoss = r.train.count > 0;
            if (r.hasLoss) r.loss = r.train.v[r.train.count - 1];
        }
        if (n >= 12 && !unknown(f[11])) parseSeries(f[11], r.val);
        if (n >= 13 && !unknown(f[12])) { r.hasAcc = true; r.acc = strtof(f[12], nullptr); }
        r.lastUpdateMs = now;
    } else if (!strcmp(f[0], "END")) {
        live = stage; stage.linked = false;
        lastSnapshotMs = now; everLinked = true;
    }
}
char HostLink::feed(int c, Telemetry &live, uint32_t now) {
    if (length == 0 && !overflow) {
        if (c == '\r' || c == '\n') return 0;
        if (c >= 'a' && c <= 'z') return char(c);   // debug command, not protocol
    }
    if (c == '\n') {
        if (!overflow) { line[length] = 0; handleLine(line, live, now); }
        length = 0; overflow = false;
    } else if (c != '\r') {
        if (length + 1 < sizeof(line)) line[length++] = char(c); else overflow = true;
    }
    return 0;
}
bool HostLink::expire(Telemetry &live, uint32_t now, uint32_t timeoutMs) {
    if (!live.linked || !everLinked || uint32_t(now - lastSnapshotMs) < timeoutMs) return false;
    live = {};   // linked=false: the UI shows "waiting for host"
    everLinked = false;
    return true;
}
