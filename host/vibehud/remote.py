"""Remote machines (HPC login nodes, servers, VS Code Remote-SSH hosts) as data sources.

Claude Code / Codex / training jobs that run on another computer leave their files THERE. Nothing is
installed on that machine: over plain `ssh` (your keys and ~/.ssh/config) the agent starts the remote's own
`python3` (3.9+) and sends it VibeHUD's source code on stdin, which runs from memory (its only write is
Claude's usage-limit cache, ~/.claude/vibehud-limits.json, see claude.py). That
process reads the remote's runs, queue, sessions and GPUs and prints one JSON snapshot every few seconds; it
ends when the ssh connection ends, so nothing is left behind.

If the connection drops (a laptop waking from sleep, say) the process exits and is started again.
"""
from __future__ import annotations
import base64, dataclasses, subprocess, sys, threading, time, zlib
from pathlib import Path
from ._proc import NO_WINDOW
from .model import Gpu, Limit, Run, Session, Snapshot, snapshot_from_json, snapshot_to_json

INTERVAL = 5.0          # seconds between snapshots from the remote
MAX_AGE = 60.0          # a snapshot older than this is not shown
SKIP = {"device", "autostart", "__main__"}      # modules a remote does not need

# Runs on the remote. SRC maps module names to source; the finder lets `import vibehud.x` read from it.
BOOT = '''
import importlib.abc, importlib.util, sys
SRC = {src!r}
class Finder(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    def find_spec(self, name, path=None, target=None):
        if name in SRC:
            return importlib.util.spec_from_loader(name, self, is_package=name == "vibehud")
    def create_module(self, spec):
        return None
    def exec_module(self, module):
        exec(compile(SRC[module.__name__], module.__name__, "exec"), module.__dict__)
sys.meta_path.insert(0, Finder())
from vibehud.remote import serve
serve({runs!r}, {interval!r})
'''

def serve(runs, interval: float = INTERVAL):
    """Remote side: print a snapshot every `interval` seconds until the ssh connection closes."""
    import os
    from .cli import gather
    from .config import local_collectors
    threading.Thread(target=lambda: (sys.stdin.read(), os._exit(0)), daemon=True).start()   # EOF = laptop is gone
    collectors = local_collectors(runs)
    while True:
        try:
            print(snapshot_to_json(gather(collectors)), flush=True)
        except OSError:
            os._exit(0)
        time.sleep(interval)

def _boot_line(runs) -> bytes:
    src = {("vibehud" if p.stem == "__init__" else f"vibehud.{p.stem}"): p.read_text("utf-8")
           for p in Path(__file__).parent.glob("*.py") if p.stem not in SKIP}
    code = BOOT.format(src=src, runs=list(runs), interval=INTERVAL)
    return base64.b64encode(zlib.compress(code.encode())) + b"\n"

class RemoteCollector:
    def __init__(self, host: str | None = None, label: str | None = None, python: str = "python3",
                 runs=("~/runs",), command: list[str] | None = None):
        self.label = label or (host or "remote")
        if command is None:
            options = ["-o", "BatchMode=yes", "-o", "ConnectTimeout=8",
                       "-o", "ServerAliveInterval=10", "-o", "ServerAliveCountMax=3"]    # dead link -> exit -> restart
            command = ["ssh", *options, host,
                       f'{python} -c "import sys,zlib,base64;exec(zlib.decompress(base64.b64decode(sys.stdin.readline())))"']
        self.command, self.roots = command, runs
        self._snapshot: Snapshot | None = None
        self._received = 0.0
        self.last_error: str | None = None
        self._lock = threading.Lock()
        threading.Thread(target=self._loop, name=f"vibehud-remote-{self.label}", daemon=True).start()

    def _loop(self):
        while True:
            problem = "no output"
            try:
                proc = subprocess.Popen(self.command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                        stderr=subprocess.STDOUT, text=False, **NO_WINDOW)
                proc.stdin.write(_boot_line(self.roots)); proc.stdin.flush()     # stdin stays open: closing it stops the remote
                for raw in proc.stdout:
                    line = raw.decode("utf-8", "replace").strip()
                    try:
                        snapshot = snapshot_from_json(line)
                    except Exception:
                        problem = line or problem                              # ssh or python error text
                        continue
                    with self._lock:
                        recovered = self.last_error is not None or self._snapshot is None
                        self._snapshot, self._received, self.last_error = snapshot, time.time(), None
                    if recovered:
                        print(f"[vibehud] remote '{self.label}': connected", flush=True)
                problem = f"{problem} (exit {proc.wait()})"
            except Exception as e:
                problem = str(e)
            with self._lock:
                changed = problem != self.last_error
                self.last_error = problem
            if changed:                                  # logged once per distinct problem
                print(f"[vibehud] remote '{self.label}': {problem}", flush=True)
            time.sleep(10)

    def _current(self) -> Snapshot | None:
        with self._lock:
            return self._snapshot if self._snapshot and time.time() - self._received <= MAX_AGE else None

    def collect(self, now: float | None = None) -> tuple[list[Session], tuple[Limit, Limit]]:
        snap = self._current()
        if not snap:
            return [], (Limit(), Limit())
        for s in snap.sessions:
            s.profile = self.label                      # the screen shows where it runs: "Claude (hpc)"
        return snap.sessions, (snap.hourly, snap.weekly)

    def gpus(self) -> list[Gpu]:
        snap = self._current()
        return [dataclasses.replace(g, machine=self.label) for g in snap.gpus] if snap else []

    def runs(self, now: float | None = None) -> list[Run]:
        snap = self._current()
        if not snap:
            return []
        # Copies: the cached snapshot is read every tick, so editing it in place would stack the prefix.
        return [dataclasses.replace(r, id=f"{self.label}-{r.id}") for r in snap.runs]
