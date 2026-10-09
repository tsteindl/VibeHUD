"""GPU utilisation and VRAM, for the machine this code runs on.

Two ways to use it:

* In your training script (recommended, and the only way that works on an HPC compute node, where the
  agent cannot see the GPU): one line next to your TensorBoard writer

      import vibehud.gpu
      vibehud.gpu.start_logging(writer)          # background thread, every 5 s

  Pass `total_steps=N` too and the display shows progress % and ETA for that run.
  It writes `vibehud/gpu_util`, `vibehud/vram_used_gb` and `vibehud/vram_total_gb` scalars into the same
  event file, so they travel to the board exactly like the loss does. No dependency on torch or jax:
  it asks the NVIDIA driver (`nvidia-smi`), and falls back to torch.cuda when that is missing.
* The agent calls `sample()` itself for runs on its own machine that did not log GPU tags.

Values are device-wide (everything on that GPU), and the first visible GPU only (the busiest of all
visible GPUs for utilisation, summed memory). Inside a Slurm job `CUDA_VISIBLE_DEVICES`/cgroups already
restrict what the driver reports to the job's own GPUs.
"""
from __future__ import annotations
import shutil, subprocess, threading, time
from ._proc import NO_WINDOW

TAG_UTIL, TAG_USED, TAG_TOTAL = "vibehud/gpu_util", "vibehud/vram_used_gb", "vibehud/vram_total_gb"
TAG_TOTAL_STEPS = "vibehud/total_steps"

def _from_nvidia_smi() -> tuple[float, float, float] | None:
    exe = shutil.which("nvidia-smi")
    if not exe:
        return None
    try:
        out = subprocess.run([exe, "--query-gpu=utilization.gpu,memory.used,memory.total",
                              "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=5, **NO_WINDOW).stdout
        rows = [[float(x) for x in line.split(",")] for line in out.strip().splitlines() if line.strip()]
    except (OSError, ValueError, subprocess.SubprocessError):
        return None
    if not rows:
        return None
    return max(r[0] for r in rows), sum(r[1] for r in rows) / 1024, sum(r[2] for r in rows) / 1024

def _from_torch() -> tuple[float, float, float] | None:
    try:
        import torch
        if not torch.cuda.is_available():
            return None
        free, total = torch.cuda.mem_get_info()
        try:
            util = float(torch.cuda.utilization())       # needs pynvml
        except Exception:
            return None                                  # memory without utilisation is not worth showing
        return util, (total - free) / 2**30, total / 2**30
    except Exception:
        return None

def sample() -> tuple[float, float, float] | None:
    """-> (utilisation %, VRAM used GB, VRAM total GB) or None when there is no usable NVIDIA GPU."""
    return _from_nvidia_smi() or _from_torch()

def start_logging(writer, interval: float = 5.0, step_fn=None, total_steps: int | None = None) -> threading.Thread:
    """Log GPU scalars to a TensorBoard writer (torch.utils.tensorboard or tensorboardX) in a daemon thread.

    The x-axis is wall-clock seconds since start unless `step_fn()` returns the training step; the
    VibeHUD agent only uses the latest value, so either is fine."""
    started = time.time()
    if total_steps:                       # lets the agent show progress % and ETA without any per-run configuration
        writer.add_scalar(TAG_TOTAL_STEPS, float(total_steps), 0)
    def loop():
        while True:
            reading = sample()
            if reading:
                step = step_fn() if step_fn else int(time.time() - started)
                for tag, value in zip((TAG_UTIL, TAG_USED, TAG_TOTAL), reading):
                    writer.add_scalar(tag, value, step)
            time.sleep(interval)
    thread = threading.Thread(target=loop, name="vibehud-gpu", daemon=True)
    thread.start()
    return thread
