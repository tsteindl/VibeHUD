"""Global queue of planned runs, whatever system queued them. Read-only: it never touches the queues.

A source is a text file (or a directory of *.txt files) with one planned run per line: the run's name,
then anything (usually its command). Blank lines and lines starting with # are ignored; the order of
the lines is the order of the queue. ~/.vibehud/queue/ is always read, so any queue system can join by
putting or linking a file there, e.g. a symlink to spectral-tirex's queue/jobs.txt, or entries written
by tirex-actions' queue_mark.sh. A run that starts leaves the file and shows up as a TensorBoard run.
"""
from __future__ import annotations
import zlib
from pathlib import Path
from .model import Limit, Run, QUEUED

DEFAULT_DIR = Path.home() / ".vibehud" / "queue"

class QueueCollector:
    def __init__(self, sources):
        self.sources = [Path(s).expanduser() for s in sources]

    def collect(self, now: float | None = None):
        return [], (Limit(), Limit())          # no sessions or limits here, only runs()

    def runs(self, now: float | None = None) -> list[Run]:
        runs, seen = [], set()
        for source in self.sources:
            files = sorted(source.glob("*.txt")) if source.is_dir() else [source]
            for path in files:
                try:
                    lines = path.read_text("utf-8").splitlines()
                except OSError:
                    continue
                for line in lines:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    name = line.split()[0]
                    if name not in seen:
                        seen.add(name)
                        runs.append(Run(id=f"q{zlib.crc32(name.encode()):08x}", name=name, state=QUEUED))
        return runs
