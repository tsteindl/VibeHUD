# Setup: GPU machine (steindl-tower) + laptop(s) over SSH

Layout: the board is plugged into a laptop (Windows now, a MacBook later). The laptop agent fetches the GPU
machine's data over `ssh` every 15 s. Nothing runs on the GPU machine except a one-shot
`python -m vibehud --json` that the laptop starts through ssh.

Status: agent, wheel, config parsing, Python 3.10 install and failure messages are tested on Windows. Checked on
your machine (read-only): passwordless `ssh steindl-tower` works, RTX 5080, `nvidia-smi` in PATH, miniconda with
many envs. Not tested yet: installing there, a real fetch, the macOS steps.

## What your existing SSH setup already gives you

`~/.ssh/config` on the laptop already has

```
Host steindl-tower
    HostName tsteindl-x870-taichi-creator      # Tailscale name: Tailscale must be connected on the laptop
    User tsteindl
```

and a key that logs in without a password (verified with `ssh -o BatchMode=yes steindl-tower echo ok`), which is
all the agent needs. No new user, key or ssh entry. If the board ever shows nothing from the tower, check
Tailscale is up first. The MacBook later needs the same `Host` block and its own key (`ssh-copy-id steindl-tower`).

## 1. Install the agent on the tower, once, in its own tiny environment

The agent only reads files, so it does not have to live in any training env, and your training envs stay
untouched. From the laptop, in the project folder:

```powershell
scp dist\vibehud-0.1.0-py3-none-any.whl steindl-tower:~/
ssh steindl-tower
```

On the tower:

```bash
source ~/miniconda3/etc/profile.d/conda.sh
conda create -n vibehud python=3.12 -y
~/miniconda3/envs/vibehud/bin/pip install ~/vibehud-0.1.0-py3-none-any.whl
~/miniconda3/envs/vibehud/bin/vibehud --once          # runs without errors; lists any runs/sessions it finds
```

## 2. Laptop: tell the agent about the tower

Create `C:\Users\tobia\.vibehud\config.toml`:

```toml
[[remote]]
host = "steindl-tower"
label = "tower"
python = "/home/tsteindl/miniconda3/envs/vibehud/bin/python"
args = "--tensorboard /home/tsteindl/runs"          # folder with your TensorBoard logs (searched recursively)
```

(`label` is what the screen prints: `Claude (tower)`, `tower: exp1 s1200`.) Then, on the laptop:

```powershell
vibehud --once      # waits ~8 s for the first fetch; an ssh problem prints its reason
vibehud             # run it; or: vibehud --install-autostart
```

If it fails, run what the agent runs, by hand:
`ssh -o BatchMode=yes steindl-tower "/home/tsteindl/miniconda3/envs/vibehud/bin/python -m vibehud --json"`

## 3. Your training script (in whichever conda env you train in)

No `vibehud` import is needed: GPU and VRAM come from the tower's `nvidia-smi`, automatically, for running
runs on that machine (one GPU, so no ambiguity). The script needs only TensorBoard logging:

```python
from torch.utils.tensorboard import SummaryWriter       # needs `pip install tensorboard` in that env
writer = SummaryWriter("/home/tsteindl/runs/exp1", flush_secs=5)   # default flush is 120 s: display would lag 2 min
writer.add_scalar("vibehud/total_steps", TOTAL_STEPS, 0)           # optional: progress % and ETA for this run

# in the loop, one step number for everything so the curves line up:
writer.add_scalar("train/loss", loss, step)
writer.add_scalar("val/loss", val_loss, step)           # blue line next to train loss
writer.add_scalar("val/acc", val_acc, step)             # shown as "val acc 93.4%" (0..1 or 0..100)
```

Of your envs only `jku_wad` has `tensorboard` installed (`pip install tensorboard`, or `tensorboardX`, in the
others). `jax` runs work the same way as long as they write TensorBoard event files.

Tag rules: a tag containing `loss` is train loss (prefer one with `train`); containing `loss` and
`val`/`test`/`eval` is validation loss; `acc` plus `val`/`test`/`eval` is validation accuracy. One run = one
directory with event files, so keep train and val in the same writer.

## 4. MacBook (later)

```bash
ssh-copy-id steindl-tower                         # after adding the same Host block to ~/.ssh/config
mkdir -p ~/.vibehud && python3 -m venv ~/.vibehud/venv        # Python 3.9+ (Xcode tools or `brew install python`)
scp steindl-tower:~/vibehud-0.1.0-py3-none-any.whl ~/
~/.vibehud/venv/bin/pip install ~/vibehud-0.1.0-py3-none-any.whl
```

Same `[[remote]]` block in `~/.vibehud/config.toml`, then `~/.vibehud/venv/bin/vibehud --once` and
`~/.vibehud/venv/bin/vibehud --install-autostart` (LaunchAgent; if nothing happens read `~/.vibehud/agent.log`).
Two laptops polling the tower is fine: the remote side is stateless and read-only.

## Notes and troubleshooting

- Claude limits: run `vibehud --install-claude-statusline` on every computer where you run Claude Code.
- GPU numbers via `nvidia-smi` are machine-wide: two runs on the tower's GPU show the same numbers.
- On a Slurm cluster later, compute nodes are not the login node, so `nvidia-smi` is not visible to the agent;
  there the in-script `vibehud.gpu.start_logging(writer)` is needed (install the wheel in the training env).

| Symptom | Check |
|---|---|
| ssh error text in `vibehud --once` | Tailscale connected? `ssh -o BatchMode=yes steindl-tower echo ok` |
| `No module named vibehud` | `python` in config must be the `vibehud` env's python (step 1) |
| Runs missing | `args` folder wrong, or no new events in 6 h: `ssh steindl-tower "find ~/runs -name 'events.out*'"` |
| Run shows STALE | no events for 150 s: `flush_secs` too high, or training paused |
| `GPU --` | `nvidia-smi` failing on the tower, or the run is not "running" |
| Board shows "waiting for host" | agent not running, or another program holds the serial port |

## Installing on another computer: summary

What exists per computer: (a) the agent, installed from the one wheel file `dist/vibehud-0.1.0-py3-none-any.whl`
(pure Python, any OS/CPU, Python 3.9+; rebuild with `python -m pip wheel --no-deps -w dist ./host`), (b) its own
`~/.vibehud/config.toml`, (c) for a computer the board is plugged into: autostart. The board itself is never
reflashed; it just needs a USB port. Settings are not stored on the board yet, so each computer has its own config.

| Computer | Needs |
|---|---|
| Board plugged in (laptop/MacBook) | wheel, config.toml, ssh access to remotes, `vibehud --install-autostart` |
| Remote you ssh into (tower, HPC login node) | wheel only; config lives on the laptop (`[[remote]]`) |
| Training environment | nothing, unless you want GPU numbers on a cluster (`import vibehud.gpu`) |

### Company MacBook

```bash
python3 --version                                   # 3.9+ (Xcode command line tools, or brew install python)
python3 -m venv ~/.vibehud/venv
~/.vibehud/venv/bin/pip install ~/vibehud-0.1.0-py3-none-any.whl     # file copied by scp/AirDrop/USB stick
```

Then ssh access (`~/.ssh/config` entry + `ssh-copy-id`), `~/.vibehud/config.toml` with your `[[remote]]` blocks,
`~/.vibehud/venv/bin/vibehud --once`, plug in the board, `~/.vibehud/venv/bin/vibehud --install-autostart`
(LaunchAgent; logs in `~/.vibehud/agent.log`). Check your company's rules first: Tailscale and private ssh keys
may be forbidden, MDM can block LaunchAgents/USB devices, and `--install-claude-statusline` edits Claude's
settings (possibly managed). Session titles go only to the board over USB; the only network traffic is your ssh.

### HPC cluster (board stays on your laptop)

The laptop agent logs into the login node over ssh and reads your log files on the shared filesystem.

1. Login node, once: a Python 3.9+ environment in your home and the wheel.
   ```bash
   module load python            # whatever your site calls it
   python3 -m venv ~/vibehud-env && ~/vibehud-env/bin/pip install ~/vibehud-0.1.0-py3-none-any.whl
   ```
   Non-interactive ssh does not run `module load`. If `~/vibehud-env/bin/python` fails when called through ssh
   (missing libraries), make `~/bin/vibehud-python`:
   `#!/bin/bash -l` / `module load python` / `exec ~/vibehud-env/bin/python "$@"` (chmod +x) and use that path.
2. Laptop `config.toml`:
   ```toml
   [[remote]]
   host = "hpc"                       # ~/.ssh/config entry (ProxyJump works)
   label = "hpc"
   python = "/home/USER/vibehud-env/bin/python"
   args = "--tensorboard /scratch/USER/runs"
   interval = 60                      # be gentle with login nodes
   ```
3. Training jobs: write TensorBoard logs under that folder with `flush_secs=5`, the `vibehud/total_steps` scalar,
   and, for GPU numbers, install the wheel in the training environment and add
   `import vibehud.gpu; vibehud.gpu.start_logging(writer)`. Compute nodes are not the login node, so the agent
   cannot see their GPU any other way.
4. Login with 2FA/OTP: the agent cannot type codes (`BatchMode`). On macOS/Linux open one long-lived master connection
   yourself and the agent reuses it: `ssh -f -N -o ControlMaster=yes -o ControlPath='~/.ssh/vibehud-%C' -o ControlPersist=8h hpc`.
   Windows ssh has no connection sharing, so 2FA clusters do not work from Windows. Untested.

Not built yet: Slurm queue state (pending/running/failed), and a time-limit based ETA. Check that your site allows
light periodic ssh polling and file reads (this is read-only and runs as you).
