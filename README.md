# VibeHUD physical prototype

Waveshare **ESP32-S3-LCD-3.16**, 820 × 320 landscape. Mock telemetry only.
PlatformIO + Espressif Arduino **3.3.11**, vendor ST7701 RGB driver, vendor LVGL
**8.4.0** (the supplied configuration's comment says 8.3.11; source version is 8.4.0).
The original Arduino CLI workflow remains available. Both use the exact vendor LCD setup.
No AI-agent, GPU, training-framework, or Wi-Fi integration is started.

Verified on COM7: vendor demo visible and stable (physical confirmation), final
HUD flash hashes, 820 × 320 device captures, page wrapping, both idle layouts,
all training states, two distinct running animation frames, and over one minute
of runtime with constant free heap and no LCD errors or resets. Physical HUD
readability and short/long BOOT presses still await user confirmation.
See [device-rendered previews](docs/previews); these are framebuffer captures,
not photographs of the panel.

## PlatformIO in VS Code (recommended)

Open this **VibeHUD folder** in VS Code. PlatformIO IDE is already installed on
this computer. `platformio.ini` defines the `vibehud` environment and pins
[pioarduino 55.03.311](https://github.com/pioarduino/platform-espressif32/releases/tag/55.03.311)
to match the working Arduino 3.3.11 core. The generic ESP32-S3 board definition
is overridden for this board's 16 MB flash and OPI PSRAM; LCD pins and timings
still come from Waveshare's code, not the generic board definition.

1. If the PlatformIO sidebar does not recognize the new configuration, use
   **Ctrl+Shift+P → Developer: Reload Window**.
2. Click the PlatformIO icon in the left sidebar. Under **Project Tasks →
   vibehud → General**, choose **Build**, then **Upload**. The bottom toolbar's
   checkmark and right arrow are shortcuts for these actions.
3. Choose **Monitor** to see the USB heartbeat. Stop the monitor before using
   `scripts/serial_hud.py`, since only one application can own COM7.

The first build downloads the pinned platform, compiler and framework. Subsequent
builds reuse them. The current project already has the local vendor dependency.
On a fresh checkout, run `scripts/setup.ps1` once before building. No new-project
wizard or replacement firmware sketch is needed.

In a **PlatformIO Core CLI** terminal (available from the PlatformIO sidebar):

```powershell
pio run -e vibehud
pio run -e vibehud -t upload
pio device monitor -e vibehud
```

If `pio` is unavailable in an ordinary PowerShell terminal, use
`& "$env:USERPROFILE\.platformio\penv\Scripts\platformio.exe"` in place of `pio`.
COM7 is configured for upload and monitoring. Update `upload_port` and
`monitor_port` in `platformio.ini` if Windows assigns another port.

## Original Arduino CLI workflow (PowerShell, project root)

```powershell
# First checkout only: downloads the official archive and installs local LVGL.
powershell -ExecutionPolicy Bypass -File .\scripts\setup.ps1

# Build; add -Flash to build and flash the connected board.
powershell -ExecutionPolicy Bypass -File .\scripts\build.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\build.ps1 -Flash -Port COM7

# Reproduce the vendor widgets baseline.
powershell -ExecutionPolicy Bypass -File .\scripts\build.ps1 -Demo -Flash -Port COM7
```

The script finds Arduino CLI on PATH or in the standard Windows Arduino IDE
installation. Install `esp32:esp32@3.3.11` with Arduino's board manager if needed.
Settings: ESP32S3 Dev Module; 240 MHz; QIO 80 MHz flash; 16 MB flash;
OPI PSRAM; hardware USB CDC/JTAG; USB CDC on boot enabled;
`app3M_fat9M_16MB` partitions. No full-chip erase is required.

Detected USB device: **COM7**, `VID_303A / PID_1001`, ESP32-S3 revision v0.2,
8 MB embedded PSRAM, 16 MB quad flash, MAC `28:84:85:91:ba:e0`.
Port numbering may change after reconnecting. Close serial tools before flashing.
If automatic download entry fails, hold BOOT, tap RST, release BOOT, then flash.
Holding BOOT during reset enters the ROM loader; use it after startup for UI input.

## On-device controls and layout

- Short BOOT press: next page. One page index drives both lists, so session page N
  and training run N advance together (total pages = max of the two counts).
- Hold BOOT 900 ms: toggle the 5-row sessions view; hold again to return to the
  automatic layout (training if any runs exist, otherwise the sleeping footer).
- BOOT is sampled in its own high-priority task, so presses are not lost while
  LVGL holds the display mutex during a redraw.
- Training mode: three 60 px session rows; below, per run: name, progress bar,
  rate/ETA, GPU/VRAM, a 48-point loss curve with latest loss; right: 5-hour and
  weekly usage-limit gauges (bar, percent, time to reset; amber 70%, red 90%).
- Idle layouts: five 57 px rows plus a footer with the dino and both limit gauges;
  the 5-row view has a limits-only footer. The dino runs while any run is training.
- Text is LVGL's anti-aliased Montserrat at native size (16/20/24/28 px), not
  replicated bitmap pixels. Titles are static and truncated with an ellipsis.
- Display work is sparse by design: data text refreshes at 1 Hz, the dino steps
  at 3 Hz (hop plus leg swap, from a 32x36 Scale2x-smoothed sprite), nothing else animates.
- Traffic light: red top, amber middle, green bottom. Color and position indicate
  inactive / needs input / working. Mock states change every 9 seconds.
- Running dino, resting stale dino, happy completion, and red failure states.
  A real future source with no update for 5 seconds is treated as stale.
- Missing training metrics show `--`; unknown progress shows an empty bar and `--%`.

The small sleeping footer is the default idle design choice: it keeps the same
five-session capacity and uses 34 px. Physical readability still needs assessment
at normal laptop viewing distance; framebuffer captures cannot establish that.

## USB inspection / mock controls

```powershell
py -3.12 -m venv .tools\venv
.\.tools\venv\Scripts\python.exe -m pip install pyserial pillow
.\.tools\venv\Scripts\python.exe .\scripts\serial_hud.py --seconds 10
.\.tools\venv\Scripts\python.exe .\scripts\serial_hud.py --command p
.\.tools\venv\Scripts\python.exe .\scripts\serial_hud.py --command s --capture build\sleeping.png
.\.tools\venv\Scripts\python.exe .\scripts\serial_hud.py --command t --capture build\training.png
```

Single-character commands: `p` page; `m` cycle layout; `t/s/f` training/sleep/full;
`a` auto layout; `r/h/d/e` set the shown run to running/stalled/done/error; `c` framebuffer capture. These are prototype
inspection commands, not the future telemetry transport. USB logs include
heartbeat, page, mode, run state, and free heap. Page events identify `BOOT` or
`serial`, making a real button press distinguishable from a host command.

## Small code boundaries

`telemetry.h/.cpp`: provider-independent data and mock source, optional metric flags.
`ui.h/.cpp`: reusable session rows, pagination, title reveal and training rendering.
`input.h`: debounced button events. `VibeHUD.ino`: orchestration and USB diagnostics.
`lvgl_port.c`, `user_config.h`, backlight and `src/`: adapted vendor board support.
LVGL access is serialized through the vendor display mutex.

See [vendor provenance](vendor/README.md) for exact pin/config sources. GPIO0 is
both BOOT and the demo's LCD initialization chip-select. The HUD enables the
vendor driver's IO-release mechanism and disables command mirroring before
reconfiguring GPIO0 as input. GPIO6 drives backlight PWM. The RST button is reset,
not a second UI input. No pin map was inferred from a different board.
The supplied LVGL8 software-rotation routine requires even redraw dimensions;
the HUD rounds invalidation regions to even pixel boundaries to prevent an
odd final chunk from becoming a zero-height redraw loop.

## Host agent and USB protocol (real data)

The board shows "waiting for host..." until a PC agent feeds it; it returns to that state
10 s after the last snapshot. The agent (`host/`, Python 3.9+, only dependency pyserial)
finds the board by USB ID 303A:1001, reads Codex's local files (read-only) and sends one
snapshot per second.

```powershell
.\.toolsenv\Scripts\python.exe -m pip install -e host      # once
.\.toolsenv\Scripts\python.exe -m vibehud --once            # print what it sees, no board needed
.\.toolsenv\Scripts\python.exe -m vibehud                   # feed the board (close other COM7 users)
```

No configuration is needed for one Codex account (`CODEX_HOME` or `~/.codex`; the account label is
the first letter of its email). More accounts/labels: `~/.vibehud/config.toml`
(`[[codex]] label = "W"  home = "~/.codex-work"`). Codex limits (5 h and weekly) come from the
`rate_limits` in its session logs; when a window has rolled over since the last event it shows 0%.
Codex "needs your input" is not detectable from its files yet, so sessions show working or idle.

Protocol (tab-separated, `VH1 BEGIN` ... `END`, applied atomically) is documented in
`firmware/VibeHUD/host_link.h`. Debug serial commands remain single lowercase letters; `o` toggles
built-in demo data. `x` + `scripts/panel_dump.py` dump the real panel framebuffer.
See [docs/integration.md](docs/integration.md) for the design (Claude, training runs, Jupyter, HPC).

### TensorBoard runs

```powershell
# terminal 1: any script that writes TensorBoard events (this one is a dummy)
.\.toolsenv\Scripts\python.exe examples	ensorboard_dummy.py --logdir build	b\dummy-1 --steps 3000 --sps 15
# terminal 2: the agent watches a folder recursively; --total-steps enables % and ETA
.\.toolsenv\Scriptsibehud.exe --tensorboard build	b --total-steps 3000
```

In your own code only one thing matters: `SummaryWriter(logdir, flush_secs=...)`. PyTorch buffers
events for 120 s by default, which delays the display equally. Permanent setup: `[[tensorboard]]` in
`~/.vibehud/config.toml` (`root`, optional `total_steps`). One run per directory that contains
event files (a newest file wins); the loss is the tag containing "loss" (preferring "train").
Running = events in the last 150 s, stalled = up to 30 min, then done (file age is a guess:
event files do not say whether the process is alive). GPU/VRAM are not in event files (deferred).

### Claude limits (5 h / weekly)

Claude Code passes `rate_limits` to its status-line command (documented in its changelog). One command
installs a small hook that records them; it keeps any status line you already have and makes a backup:

```powershell
.\.toolsenv\Scriptsibehud.exe --install-claude-statusline     # undo: --remove-claude-statusline
```

The numbers update whenever a Claude session is active, so they are as fresh as your last Claude activity.
After the reset time passes they read 0%. Without the hook, Claude contributes no limits.

### GPU and VRAM

Event files carry no GPU data, so the training script adds one line (needs no torch/jax, just an NVIDIA driver):

```python
import vibehud.gpu
vibehud.gpu.start_logging(writer)     # writer = your SummaryWriter; logs vibehud/gpu_util, vram_used_gb, vram_total_gb
```

This works on a cluster compute node too, because the numbers travel inside the event file. If a run on the
agent's own machine did not log them, the agent asks the local `nvidia-smi` instead.
`examples/tensorboard_dummy.py --fake-gpu` logs synthetic values for machines without a GPU.

### Remote machines (ssh, HPC, VS Code Remote-SSH)

Claude/Codex/training that run on another computer leave their files there. Install vibehud on that machine
(`pip install --user`, pure Python) and add to the laptop's `~/.vibehud/config.toml`:

```toml
[[remote]]
host = "hpc-login"            # from ~/.ssh/config
label = "hpc"                 # shown as "Claude (hpc)"
args = "--tensorboard ~/runs --total-steps 10000"
```

The laptop agent runs `ssh host python3 -m vibehud --json` every 15 s in the background and merges the result.

### Train and validation loss

The loss plot draws train loss (light) and validation/test loss (blue) on one scale, with matching
`loss` / `val` numbers underneath. Tags are matched by name: a tag containing "loss" is train loss
(preferring "train"), a loss tag containing "val", "test" or "eval" is validation. Both are resampled onto
a shared step axis, so validation logged once per epoch lines up with train loss logged every step.
Accuracy is not plotted (different scale and direction): the latest validation accuracy (tag with "acc" and
"val"/"test"/"eval", fraction or percent) is shown as `val acc 93.4%` above the plot.

### Start at login (Windows, Ubuntu/Linux, macOS)

```powershell
vibehud --install-autostart          # remove: --remove-autostart;  preview: add --dry-run
vibehud --install-autostart --autostart-args "--tensorboard ~/runs --total-steps 10000"
```

Windows: per-user `Run` registry entry (no admin) using `pythonw`, started immediately. Linux: `systemd --user`
service (XDG autostart if there is no systemd; add yourself to the `dialout` group so the serial port opens).
macOS: LaunchAgent. Output goes to `~/.vibehud/agent.log`. Only the Windows path is tested so far.
Use `~/.vibehud/config.toml` instead of `--autostart-args` for anything permanent.

### Installing on a remote machine

```bash
scp -r host user@gpu-box:~/vibehud-host && ssh user@gpu-box "pip install --user ~/vibehud-host"
```

### Real GPU machine over ssh

Step-by-step (Ubuntu GPU box, Windows laptop, later a MacBook): [docs/setup-gpu-machine.md](docs/setup-gpu-machine.md).
The installable file is built with `.toolsenv\Scripts\python.exe -m pip wheel --no-deps -w dist ./host`.
In a training script, `vibehud.gpu.start_logging(writer, total_steps=N)` also gives progress % and ETA per run.
