#include "telemetry.h"
#include <math.h>
#include <string.h>
namespace {
uint32_t stepOf[4], pushedAt[4];
float curve(uint32_t step, int run) {
    return .2f + .9f*expf(-float(step)/60.f) + .008f*sinf(step*1.7f + run*2.f);
}
// Validation loss is logged less often (here every 6th bin) and sits a little above train loss.
void fillVal(TrainingRun &r, int run) {
    r.val.count = 0;
    for (size_t x=0; x<LossHistory; x+=6) {
        r.val.x[r.val.count] = uint8_t(x);
        r.val.v[r.val.count++] = curve(stepOf[run]-(LossHistory-1)+x, run) + .06f + .03f*(1.f-float(x)/LossHistory);
    }
}
void fillHistory(TrainingRun &r, int run, uint32_t step) {
    stepOf[run] = step; r.train.count = LossHistory;
    for (size_t k=0; k<LossHistory; ++k) { r.train.x[k] = uint8_t(k); r.train.v[k] = curve(step-(LossHistory-1)+k, run); }
    r.loss = r.train.v[LossHistory-1];
    if (run == 0) { fillVal(r, run); r.hasAcc = true; r.acc = 93.4f; }
}
}
void mockInit(Telemetry &s, uint32_t now) {
    memset(&s, 0, sizeof(s));   // not `= {}`: avoids a large temporary on the stack
    s.linked = true;
    const AgentSession sessions[] = {
        {"research", "Claude", "W", "time series model auto-research loop", SessionStatus::Working},
        {"hud", "Codex", "P", "VibeHUD physical display prototype", SessionStatus::NeedsUser},
        {"tests", "Claude", "P", "repair flaky integration tests", SessionStatus::Inactive},
        {"data", "Codex", "W", "clean dataset and validate feature pipeline", SessionStatus::Working},
        {"review", "Gemini", "W", "review checkpoint export", SessionStatus::NeedsUser},
        {"perf", "Codex", "P", "profile inference latency on edge device", SessionStatus::Working},
        {"docs", "Claude", "W", "document experiment results", SessionStatus::Inactive},
        {"api", "Other", "P", "design provider-neutral telemetry transport", SessionStatus::Working}
    };
    s.sessionCount = sizeof(sessions)/sizeof(sessions[0]);
    for (size_t i=0; i<s.sessionCount; ++i) s.sessions[i] = sessions[i];
    s.runCount = 4;
    // Run 0: everything present. Run 1: no progress/ETA/VRAM (unknown total). Run 2: finished. Run 3: queued.
    s.runs[0] = {"train-01", "time-series / run 042", RunState::Running,
        true,true,true,true,true,true, .63f,14.2f,.382f,96.f,12.8f,16.f,8040,now};
    s.runs[1] = {"train-02", "vision / run 017", RunState::Running,
        false,true,false,true,true,false, 0.f,6.8f,.9f,88.f,0.f,0.f,0,now};
    s.runs[2] = {"train-03", "tabular / run 009", RunState::Completed,
        true,true,true,true,true,true, 1.f,0.f,.121f,4.f,1.1f,16.f,0,now};
    s.runs[3] = {"queue-01", "ft_s1_ctrl_seed0", RunState::Queued,
        false,false,false,false,false,false, 0.f,0.f,0.f,0.f,0.f,0.f,0,now};
    fillHistory(s.runs[0], 0, 70);
    fillHistory(s.runs[1], 1, 110);
    fillHistory(s.runs[2], 2, 240);
    s.hourly = {true, true, 42.f, 8040};
    s.weekly = {true, true, 71.f, 273600};
}
void mockTick(Telemetry &s, uint32_t now) {
    // Demonstrate all three traffic-light states without shuffling the queue.
    uint32_t phase = now / 9000;
    for (size_t i=0; i<s.sessionCount; ++i)
        s.sessions[i].status = static_cast<SessionStatus>((i+phase)%3);
    for (size_t i=0; i<s.runCount; ++i) {
        TrainingRun &r = s.runs[i];
        if (r.state == RunState::Running) {
            if (uint32_t(now-pushedAt[i]) >= 5000) {
                pushedAt[i] = now;
                for (size_t k=1; k<LossHistory; ++k) r.train.v[k-1] = r.train.v[k];
                r.train.v[LossHistory-1] = curve(++stepOf[i], int(i));
                if (i == 0) fillVal(r, 0);
            }
            r.loss = r.train.v[LossHistory-1];
            if (i == 0) {
                r.progress = .63f + .08f * ((now/1000)%180)/180.f;
                r.etaSeconds = 8040 - ((now/1000)%180);
            }
            r.rate = (i ? 6.8f : 14.2f) + .6f*sinf(now/4000.f);
            r.gpu = (i ? 88.f : 96.f) + 2.f*sinf(now/3000.f);
            r.lastUpdateMs = now;
        } else if (r.state == RunState::Completed) {
            r.progress = 1.f;
        }
    }
    s.hourly.usedPct = 42.f + 10.f*((now/1000)%600)/600.f;
    s.hourly.resetSeconds = 8040 - (now/1000)%8000;
    s.weekly.resetSeconds = 273600 - (now/1000)%200000;
}
