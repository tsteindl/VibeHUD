#pragma once
#include <stdint.h>
#include <stddef.h>
enum class SessionStatus { Working, NeedsUser, Inactive };
// Fixed buffers so a snapshot received over USB owns its text.
struct AgentSession {
    char id[16], provider[16], profile[8], title[96];
    SessionStatus status;
};
enum class RunState { Running, Stalled, Completed, Error, Queued };   // Queued: planned, not started yet
constexpr size_t LossHistory = 48;
// One page per run. A TrainingRun is ~600 bytes and two Telemetry copies exist (live + receive stage).
constexpr size_t MaxRuns = 24;
// A curve sampled onto a shared x axis (0..LossHistory-1) so series logged at different rates
// (train loss every step, validation loss every epoch) can be drawn in one plot.
struct LossSeries {
    uint8_t count;
    uint8_t x[LossHistory];
    float v[LossHistory];
};
struct TrainingRun {
    char id[16], name[64];
    RunState state;
    // Presence flags distinguish missing metrics from legitimate zero values.
    bool hasProgress, hasRate, hasEta, hasLoss, hasGpu, hasVram;
    float progress, rate, loss, gpu, vramUsed, vramTotal;
    uint32_t etaSeconds, lastUpdateMs;
    LossSeries train, val;   // val.count == 0 when there is no validation/test loss
    bool hasAcc; float acc;  // latest validation accuracy, percent
};
// GPUs of the machines the host reads (device-wide, nvidia-smi) and the processes using them.
constexpr size_t MaxGpus = 4, MaxProcs = 40;
struct GpuInfo {
    char machine[16], name[32];
    bool hasUtil, hasVram;
    float util, used, total;   // percent, GB, GB
};
struct GpuProc {
    uint8_t gpu;               // index into Telemetry::gpus
    char type;                 // 'C' compute, 'G' graphics
    bool hasUsed; float used;  // GB
    char user[16], command[64];
};
// Subscription usage window (e.g. 5 hour and weekly limits).
struct Limit {
    bool has;        // usedPct is known
    bool hasReset;   // resetSeconds is known
    float usedPct;
    uint32_t resetSeconds;
};
struct Telemetry {
    bool linked;   // a host (or the demo source) is supplying data
    AgentSession sessions[8];
    size_t sessionCount;
    TrainingRun runs[MaxRuns];
    size_t runCount;
    GpuInfo gpus[MaxGpus];
    size_t gpuCount;
    GpuProc procs[MaxProcs];   // largest first within each GPU
    size_t procCount;
    Limit hourly, weekly;
};
void mockInit(Telemetry &state, uint32_t now);
void mockTick(Telemetry &state, uint32_t now);
