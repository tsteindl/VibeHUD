#pragma once
#include "telemetry.h"
// Receives tab-separated snapshots from the PC agent over USB serial.
//
//   VH1 BEGIN
//   SESSION <provider> <profile> <status 0 working|1 needs you|2 idle> <title>
//   LIMIT   <h|w> <used pct | -> <reset seconds | ->
//   RUN     <id> <name> <state 0 run|1 stalled|2 done|3 error|4 queued> <progress 0..1|-> <rate|-> <eta s|->
//           <gpu %|-> <vram used GB|-> <vram total GB|-> <loss,loss,... (oldest first)|->
//   END
//
// Fields are separated by TAB. A snapshot only replaces the live data on END, so a
// half-received snapshot is never shown. Lines starting with a lowercase letter are
// not protocol; feed() hands them back as single-character debug commands.
class HostLink {
    char line[768];
    size_t length = 0;
    bool overflow = false;
    Telemetry stage;
    uint32_t lastSnapshotMs = 0;
    bool everLinked = false;
    void handleLine(char *text, Telemetry &live, uint32_t now);
public:
    // Returns 0 when the byte was consumed as protocol, otherwise the command character.
    char feed(int c, Telemetry &live, uint32_t now);
    // Drops back to the "waiting for host" state when snapshots stop arriving.
    bool expire(Telemetry &live, uint32_t now, uint32_t timeoutMs = 10000);
    bool receivedAny() const { return everLinked; }
};
