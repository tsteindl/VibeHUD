"""Remote machines (HPC login nodes, servers, VS Code Remote-SSH hosts) as data sources.

Claude Code / Codex / training jobs that run on another computer leave their files THERE, not on the
laptop the board is plugged into. So the same agent code runs on the remote as a one-shot
`python3 -m vibehud --json`, which prints that machine's snapshot (its own sessions, limits and
TensorBoard runs, using the remote's own ~/.vibehud/config.toml). The agent on the laptop fetches it
over plain `ssh` (your keys and ~/.ssh/config, nothing stored by VibeHUD) every `interval` seconds
in a background thread, so a slow or dead connection never stalls the 1 Hz display loop.

Remote requirements: Python 3.11+ and `pip install --user vibehud` (pure Python; pyserial is only
imported when a board is attached). On Linux/macOS the SSH connection is multiplexed
(ControlMaster/ControlPersist), so there is one login and many cheap polls; Windows' OpenSSH has
no multiplexing, so key-based login (or an agent) is needed there.
"""
from __future__ import annotations
import dataclasses, shlex, subprocess, sys, threading, time
from ._proc import NO_WINDOW
from .model import Limit, Run, Session, Snapshot, snapshot_from_json

class RemoteCollector:
    def __init__(self, host: str | None = None, label: str | None = None, python: str = "python3",
                 args: str = "", interval: float = 15.0, command: list[str] | None = None, max_age: float = 90.0):
        self.label = label or (host or "remote")
        self.interval, self.max_age = interval, max_age
        if command is None:
            options = ["-o", "BatchMode=yes", "-o", "ConnectTimeout=8"]
            if sys.platform != "win32":
                options += ["-o", "ControlMaster=auto", "-o", "ControlPath=~/.ssh/vibehud-%C", "-o", "ControlPersist=10m"]
            command = ["ssh", *options, host, f"{python} -m vibehud --json {args}".strip()]
        self.command = command
        self._snapshot: Snapshot | None = None
        self._fetched = 0.0
        self.last_error: str | None = None
        self._lock = threading.Lock()
        threading.Thread(target=self._loop, name=f"vibehud-remote-{self.label}", daemon=True).start()

    def _loop(self):
        while True:
            started = time.time()
            try:
                out = subprocess.run(self.command, capture_output=True, text=True, timeout=45, stdin=subprocess.DEVNULL, **NO_WINDOW)
                if out.returncode != 0:
                    raise RuntimeError((out.stderr.strip().splitlines() or [f"exit {out.returncode}"])[-1])
                snapshot = snapshot_from_json(out.stdout)
                with self._lock:
                    recovered = self.last_error is not None or self._snapshot is None
                    self._snapshot, self._fetched, self.last_error = snapshot, time.time(), None
                if recovered:
                    print(f"[vibehud] remote '{self.label}': connected", flush=True)
            except Exception as e:                      # keep polling; the last good snapshot ages out
                with self._lock:
                    changed = str(e) != self.last_error
                    self.last_error = str(e)
                if changed:                             # logged once per distinct problem, not every poll
                    print(f"[vibehud] remote '{self.label}': {e}", flush=True)
            time.sleep(max(1.0, self.interval - (time.time() - started)))

    def _current(self) -> Snapshot | None:
        with self._lock:
            return self._snapshot if self._snapshot and time.time() - self._fetched <= self.max_age else None

    def collect(self, now: float | None = None) -> tuple[list[Session], tuple[Limit, Limit]]:
        snap = self._current()
        if not snap:
            return [], (Limit(), Limit())
        for s in snap.sessions:
            s.profile = self.label                      # the screen shows where it runs: "Claude (hpc)"
        return snap.sessions, (snap.hourly, snap.weekly)

    def runs(self, now: float | None = None) -> list[Run]:
        snap = self._current()
        if not snap:
            return []
        # Copies: the cached snapshot is read every tick, so editing it in place would stack the prefix.
        return [dataclasses.replace(r, id=f"{self.label}-{r.id}") for r in snap.runs]
