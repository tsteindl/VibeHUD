# Data integration design

Goal: plug in the USB cable, run one command on the PC, see real sessions, limits and
training runs. No keys or Wi-Fi credentials on the device; no changes to user code.

## Architecture

```
Claude Code (N config dirs) ─┐
Codex       (N CODEX_HOMEs) ─┼─► vibehud-agent (PC, Python) ──USB CDC, JSON lines──► device
training runs (wrapper/TB)  ─┘      collectors + one snapshot/s
```

The device stays a dumb renderer. The agent owns everything provider-specific, so new
providers are host-side plugins and never need a reflash.

### Wire protocol (host → device, newline-delimited JSON, ~1 snapshot/s)

```json
{"v":1,"sessions":[{"p":"Claude","a":"P","title":"...","st":"working|needs|idle"}],
 "limits":{"h":{"pct":42,"reset_s":8040},"w":{"pct":71,"reset_s":273600}},
 "runs":[{"id":"r1","name":"run 042","st":"running","prog":0.63,"rate":14.2,"eta_s":8040,
          "gpu":96,"vram":[12.8,16],"loss":[0.5,0.48,...]}]}
```

Missing field = unknown (`--`). Device falls back to a "waiting for host" screen after
10 s of silence (and to mock data only in a debug build). Discovery: the agent scans COM
ports for VID 303A / PID 1001 and sends a hello; hot-plug just works.

## Accounts (Claude, Codex, multiple emails)

One config file, `~/.vibehud/config.toml`, plus auto-discovery of default locations:

```toml
[[account]]
label = "P"                 # shown on screen: "Claude (P)"
provider = "claude"
home = "~/.claude"          # CLAUDE_CONFIG_DIR of that account
[[account]]
label = "W"
provider = "claude"
home = "~/.claude-work"
[[account]]
label = "P"
provider = "codex"
home = "~/.codex"           # CODEX_HOME
```

`vibehud accounts add` scans for `~/.claude*`, `~/.codex*` and writes the file. Different
emails = different config dirs, which is how both CLIs already separate accounts.

### What each provider exposes today (verified on this machine)

| Need | Claude Code | Codex |
|---|---|---|
| Session list + working/idle | `<home>/sessions/<pid>.json`: `status` (`busy`...), `cwd`, `name`, `updatedAt`, live | `<home>/sessions/**/rollout-*.jsonl`, last event + mtime |
| Needs user input | Hooks (`Notification`, `Stop`) writing a marker file; sessions status as fallback | `notify` in `config.toml` (already used for `turn-ended`) |
| Title | `ai-title` entries in `<home>/projects/*/<session>.jsonl` | first user message / thread title in rollout |
| 5h + weekly limit | **not found in local files**; needs investigation (statusline JSON, `/usage`, or local token accounting as approximation) | `rate_limits.primary` (300 min) and `.secondary` (10080 min): `used_percent`, `resets_at` in every `token_count` event |

Codex limits are therefore exact and free. Claude limits are the open item; until solved the
gauge can show `--` or an estimate marked `~`.

## Plug into any computer

Two separate questions: where do the sessions run, and where is the board plugged in.

- **Local CLI sessions can only be seen locally.** Claude Code / Codex "working vs waiting for you"
  exists only in files and processes on the machine running them; no web API exposes it. So the
  board has to be plugged into the machine where the agents run, and the agent reads local files.
- **Web APIs are only useful for limits**, and none is official for subscription plans (Claude.ai and
  ChatGPT internal endpoints need session cookies/OAuth tokens, change without notice, and may break
  terms of use). Codex already writes exact limits locally, so no web access is needed there.
- **Internet over the USB cable is not practical.** The board's USB is serial/JTAG; networking over
  it (RNDIS/NCM) needs a different USB mode and the PC to share its connection. Wi-Fi is the board's
  real network path, but it needs one-time Wi-Fi credentials and then token storage on the device.
  Keep this as an optional later mode (e.g. for remote/cloud sessions), not the base design.
- **Zero-install fallback:** a web page using WebSerial (Chrome/Edge) can talk to the board and,
  with the File System Access API, read a folder you pick. No install, but a tab must stay open.

So: one small agent per computer (single executable, run once, autostart), stateless. Settings
(account labels, which sources to show) live **on the device**, so moving the board to another
computer just works; the agent discovers the local Claude/Codex homes and the account emails
itself (verified: Claude's email is in `~/.claude.json`, Codex's in the `id_token` of `auth.json`).
Later option: expose the board as a USB drive carrying the agent executable.

## Training runs: one run-file format, many writers

Requirements: works from a **shell, a Jupyter notebook and an HPC cluster (the most important case)**.
HPC jobs run on compute nodes that cannot reach a laptop's USB port and often have no outbound
internet, but they share a filesystem with the login node, and the user can already `ssh` to it.
So the design is built around files, not sockets:

```
 notebook / script / Slurm job ──writes──► run file (JSON lines, no network needed)
                                              │  local disk, or shared FS on the cluster
 laptop agent ──reads locally, or `ssh login-node` (one persistent connection)──► board
```

**Run file** (`$VIBEHUD_DIR` or `~/.vibehud/runs/<id>.jsonl`): one JSON object per line with
`t, step, total?, loss?, metrics{}, state`, plus a header with host, PID, `SLURM_JOB_ID`,
partition, time limit. Appended every few seconds; a missing line means unknown, never zero.

**Writers** (all produce the same file):
1. `pip install vibehud` (pure Python, no dependencies, works inside a cluster conda/venv):
   - Script: `vibehud.log(step, total=N, loss=...)` or `for batch in vibehud.track(loader):`.
   - **Jupyter:** `%load_ext vibehud` then `vibehud.track(...)`/`vibehud.log(...)` in a cell; also
     Lightning / HF Trainer / Keras callbacks. GPU util and VRAM are sampled in-process (NVML)
     in a background thread, so they are the job's own numbers on whatever node it runs.
   - Opt-in `import vibehud.autotqdm` makes unchanged `tqdm` / `tqdm.notebook` loops report.
2. **No code change:** TensorBoard event files (`events.out.tfevents.*`) are read by the agent
   (loss curve, step, rate). Total steps come from a hint (`vibehud.toml`, CLI args, or the Slurm
   time limit as an upper bound for ETA).
3. **Slurm itself, even for unmodified jobs:** `squeue`/`sacct` give PENDING (in queue), RUNNING,
   COMPLETING, FAILED/TIMEOUT, elapsed vs time limit, and the stdout path, whose tail can be
   parsed for tqdm lines. "Job is pending in the queue" is useful on an HPC screen.

**Cluster access:** a tiny helper script (`vibehud-remote`, pure Python, runs on the login node)
summarizes run files and `squeue` into one JSON document. The laptop agent runs it through the
user's own `ssh` (their keys/config; a `ControlMaster`/`ControlPersist` connection means one
login and a poll every ~15 s, which is gentle on login nodes and works with 2FA). No credentials
are stored by VibeHUD and nothing runs on compute nodes except the logging library.
Config: `[[cluster]] host = "hpc-login" user = "..." dir = "~/.vibehud/runs"`.

The same snapshot protocol already carries `RUN` lines, so the board side is done.

## Build order and status

1. DONE: firmware USB protocol parser, "waiting for host" screen; agent with device discovery and
   Codex sessions + exact 5h/weekly limits (`host/`, protocol in `firmware/VibeHUD/host_link.h`).
2. Run-file format + `vibehud` logging library (script, Jupyter magic, callbacks, NVML sampling).
3. Local run discovery (run files, TensorBoard event files) feeding `RUN` lines.
4. HPC: `vibehud-remote` helper + SSH collector + Slurm state.
5. Claude Code sessions (status files); Claude limits investigation.
