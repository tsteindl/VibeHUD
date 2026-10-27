"""GPUs of the machine this code runs on, from `nvidia-smi -q -x`, and the processes using them.

Device-wide, not per run: everything on the GPU counts. Processes include graphics ones (a desktop's
gnome-shell, Xwayland), not only compute jobs. On a machine without an NVIDIA GPU (a cluster login node)
there is simply no reading.
"""
from __future__ import annotations
import os, shutil, subprocess, time
import xml.etree.ElementTree as ET
from ._proc import NO_WINDOW
from .model import Gpu, Limit

MAX_PROCS = 10          # per GPU, largest VRAM first
_cache: tuple[float, list[Gpu]] = (0.0, [])

def _gb(text: str | None) -> float | None:
    try:
        return float(text.split()[0]) / 1024          # "4626 MiB"
    except (AttributeError, ValueError, IndexError):
        return None                                   # "N/A"

def _describe(pid: str, fallback: str) -> tuple[str, str]:
    """-> (user, command line). /proc is Linux-only and may hide other users' processes; then the driver's name."""
    try:
        import pwd
        user = pwd.getpwuid(os.stat(f"/proc/{pid}").st_uid).pw_name
        args = open(f"/proc/{pid}/cmdline", "rb").read().split(b"\0")
        args = [a.decode("utf-8", "replace") for a in args if a]
        command = " ".join([os.path.basename(args[0])] + args[1:]) if args else os.path.basename(fallback)
        return user, command
    except (OSError, KeyError, ImportError):
        return "", os.path.basename(fallback)

def _query() -> list[Gpu]:
    exe = shutil.which("nvidia-smi")
    if not exe:
        return []
    try:
        out = subprocess.run([exe, "-q", "-x"], capture_output=True, text=True, timeout=5, **NO_WINDOW).stdout
        root = ET.fromstring(out)
    except (OSError, ET.ParseError, subprocess.SubprocessError):
        return []
    gpus = []
    for g in root.findall("gpu"):
        util = (g.findtext("utilization/gpu_util") or "").split()
        procs = []
        for p in g.findall("processes/process_info"):
            user, command = _describe(p.findtext("pid") or "", p.findtext("process_name") or "?")
            procs.append([p.findtext("type") or "?", user, command, _gb(p.findtext("used_memory"))])
        procs.sort(key=lambda p: -(p[3] or 0))
        gpus.append(Gpu(machine="", name=g.findtext("product_name") or "GPU",
                        util=float(util[0]) if util and util[0].isdigit() else None,
                        used=_gb(g.findtext("fb_memory_usage/used")), total=_gb(g.findtext("fb_memory_usage/total")),
                        procs=procs[:MAX_PROCS]))
    return gpus

def devices() -> list[Gpu]:
    """This machine's GPUs; nvidia-smi is a subprocess, so it runs at most every few seconds."""
    global _cache
    if time.time() - _cache[0] > 3:
        _cache = (time.time(), _query())
    return _cache[1]

def sample() -> tuple[float, float, float] | None:
    """-> (utilisation %, VRAM used GB, VRAM total GB): the busiest GPU's utilisation, summed memory."""
    gpus = [g for g in devices() if g.util is not None and g.used is not None and g.total is not None]
    if not gpus:
        return None
    return max(g.util for g in gpus), sum(g.used for g in gpus), sum(g.total for g in gpus)

class GpuCollector:
    def collect(self, now: float | None = None):
        return [], (Limit(), Limit())          # no sessions or limits here, only gpus()

    def gpus(self) -> list[Gpu]:
        return devices()
