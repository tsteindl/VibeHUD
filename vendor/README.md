# Waveshare board support

`lcd-demo/` is the unmodified Arduino `07_LVGL_V8_Test` from the official
[ESP32-S3-LCD-3.16 demo archive](https://files.waveshare.com/wiki/ESP32-S3-LCD-3.16/ESP32-S3-LCD-3.16-Demo.zip)
(archive Last-Modified: 2025-06-27).
Documentation: https://www.waveshare.com/wiki/ESP32-S3-LCD-3.16
Schematic: https://files.waveshare.com/wiki/ESP32-S3-LCD-3.16/ESP32-S3-LCD-3.16-Schematic.pdf

The HUD retains this exact ST7701 initialization sequence, RGB pin mapping,
18 MHz pixel clock, porch timings, and GPIO6 backlight setup. Its display port
adds landscape rotation, removes the widgets demo and exposes a mutex. It
enables the driver's supported IO multiplex option (with command mirroring
disabled) to release GPIO0 after LCD initialization for the BOOT button.
The bundled LVGL8 rotation implementation rounds chunk heights down to even;
odd redraw regions can leave a zero-height final chunk and hang the renderer.
The HUD's display rounder callback rounds both axes to even boundaries, including
the initial square-rotation case. The vendor library itself stays unchanged.
BOOT is active low on GPIO0 in the official schematic. RST resets the device.
Board revision is not identifiable from USB; this configuration is from the
official demo and must be visually verified on the attached unit.

Upstream Espressif source files retain their Apache-2.0 SPDX notices.
LVGL is installed locally by setup.ps1 and is MIT licensed.
