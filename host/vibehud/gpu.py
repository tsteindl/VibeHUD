"""GPU utilisation and VRAM of the machine this code runs on, from `nvidia-smi`.

Device-wide, not per run: everything on the GPU counts, and with several GPUs the busiest one's
utilisation and the summed memory are reported. On a machine without an NVIDIA GPU (a cluster login node)
there is simply no reading.
"""
from __future__ import annotations
import shutil, subprocess
from ._proc import NO_WINDOW

def sample() -> tuple[float, float, float] | None:
    """-> (utilisation %, VRAM used GB, VRAM total GB) or None when there is no usable NVIDIA GPU."""
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
