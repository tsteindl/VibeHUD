#pragma once
#include <Arduino.h>
enum class ButtonEvent : uint8_t { None, NextPage, NextMode };
class HudButton {
    // Official Waveshare schematic: BOOT0/GP0, normally high, button to GND.
    static constexpr uint8_t Pin = 0;
    bool raw = true, stable = true, longSent = false;
    uint32_t changedAt = 0, pressedAt = 0;
    volatile uint8_t pending = 0;
    ButtonEvent poll(uint32_t now) {
        bool sample = digitalRead(Pin);
        if (sample != raw) { raw = sample; changedAt = now; }
        if (raw != stable && uint32_t(now-changedAt) >= 25) {
            stable = raw;
            if (!stable) { pressedAt = now; longSent = false; }
            else if (!longSent) return ButtonEvent::NextPage;
        }
        if (!stable && !longSent && uint32_t(now-pressedAt) >= 900) {
            longSent = true;
            return ButtonEvent::NextMode;
        }
        return ButtonEvent::None;
    }
    // Sampled from its own high-priority task: the Arduino loop can be blocked
    // for 100+ ms waiting on the LVGL mutex while a rotated frame renders, which
    // used to swallow short presses.
    static void task(void *self) {
        auto *b = static_cast<HudButton*>(self);
        for (;;) {
            ButtonEvent e = b->poll(millis());
            if (e != ButtonEvent::None) b->pending = uint8_t(e);
            vTaskDelay(pdMS_TO_TICKS(2));
        }
    }
public:
    void begin() {
        pinMode(Pin, INPUT_PULLUP); raw = stable = digitalRead(Pin);
        xTaskCreatePinnedToCore(task, "button", 2048, this, 6, nullptr, 0);
    }
    ButtonEvent take() { ButtonEvent e = ButtonEvent(pending); pending = 0; return e; }
};
