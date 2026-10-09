#pragma once
#include "telemetry.h"
enum class LayoutMode { Training, SleepingFooter, FullSessions };
void uiInit(const Telemetry &s, uint32_t now);
void uiTick(const Telemetry &s, uint32_t now);
// One page index drives both lists: session page N and training run N advance together.
void uiNextPage(const Telemetry &s, uint32_t now);
// Force a layout; uiAuto returns to choosing Training/SleepingFooter from the data.
void uiSetMode(LayoutMode mode, const Telemetry &s, uint32_t now);
void uiAuto(const Telemetry &s, uint32_t now);
unsigned uiPage();
unsigned uiPageCount(const Telemetry &s);
unsigned uiRun(const Telemetry &s);
bool uiForced();
LayoutMode uiMode();
