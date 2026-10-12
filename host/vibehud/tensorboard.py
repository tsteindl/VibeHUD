"""TensorBoard collector: turns `events.out.tfevents.*` files into training runs. Read-only.

An event file is a TFRecord stream: [u64 length][u32 crc][payload][u32 crc], payload = protobuf
`Event {double wall_time=1; int64 step=2; Summary summary=5}`, `Summary {repeated Value value=1}`,
`Value {string tag=1; float simple_value=2; TensorProto tensor=8}`. The training process appends
to it (buffered: PyTorch flushes every 120 s unless `flush_secs` is lowered). We remember how far
we have read and decode only new records, with no tensorboard/protobuf/torch dependency, so the
same code can run on a cluster login node.

What event files do NOT contain: total steps (so progress/ETA need `total_steps`), GPU data, or
whether the process is still alive (finished vs crashed vs hung is guessed from file age).
"""
from __future__ import annotations
import struct, time, zlib
from pathlib import Path
from . import gpu
from .model import Limit, Run, RUNNING, STALLED, DONE, MAX_LOSS

RECENT_HOURS = 6
STALL_AFTER = 150            # seconds without new events before a run counts as stalled
FINISHED_AFTER = 30 * 60     # seconds without new events before a run counts as finished
MAX_POINTS = 4000

# ---- minimal protobuf / TFRecord decoding -------------------------------------------------

def _varint(buf: bytes, i: int) -> tuple[int, int]:
    shift = result = 0
    while True:
        b = buf[i]; i += 1
        result |= (b & 0x7F) << shift
        if not b & 0x80:
            return result, i
        shift += 7

def _fields(buf: bytes):
    """Yield (field number, wire type, value) for one protobuf message."""
    i, n = 0, len(buf)
    while i < n:
        key, i = _varint(buf, i)
        field, wire = key >> 3, key & 7
        if wire == 0:
            value, i = _varint(buf, i)
        elif wire == 1:
            value, i = buf[i:i + 8], i + 8
        elif wire == 2:
            size, i = _varint(buf, i)
            value, i = buf[i:i + size], i + size
        elif wire == 5:
            value, i = buf[i:i + 4], i + 4
        else:
            return                      # groups are not used by TensorBoard
        yield field, wire, value

def _tensor_scalar(buf: bytes) -> float | None:
    dtype, content, floats, doubles = None, None, None, None
    for field, wire, value in _fields(buf):
        if field == 1:
            dtype = value
        elif field == 4:
            content = value
        elif field == 5:
            floats = value if wire == 2 else (floats or b"") + value
        elif field == 6:
            doubles = value if wire == 2 else (doubles or b"") + value
    if content:
        return struct.unpack("<f", content[:4])[0] if dtype == 1 else struct.unpack("<d", content[:8])[0] if dtype == 2 else None
    if floats:
        return struct.unpack("<f", floats[:4])[0]
    if doubles:
        return struct.unpack("<d", doubles[:8])[0]
    return None

def decode_event(data: bytes) -> tuple[float, int, list[tuple[str, float]]]:
    """-> (wall_time, step, [(tag, value)]) for scalar summaries; non-scalar values are ignored."""
    wall, step, scalars = 0.0, 0, []
    for field, wire, value in _fields(data):
        if field == 1 and wire == 1:
            wall = struct.unpack("<d", value)[0]
        elif field == 2 and wire == 0:
            step = value
        elif field == 5 and wire == 2:
            for f2, w2, summary_value in _fields(value):
                if f2 != 1 or w2 != 2:
                    continue
                tag, scalar = None, None
                for f3, w3, v3 in _fields(summary_value):
                    if f3 == 1 and w3 == 2:
                        tag = v3.decode("utf-8", "replace")
                    elif f3 == 2 and w3 == 5:
                        scalar = struct.unpack("<f", v3)[0]
                    elif f3 == 8 and w3 == 2 and scalar is None:
                        scalar = _tensor_scalar(v3)
                if tag is not None and scalar is not None:
                    scalars.append((tag, scalar))
    return wall, step, scalars

def read_new_records(path: Path, offset: int):
    """-> (records, new_offset). A half-written trailing record is left for the next call."""
    records = []
    with path.open("rb") as f:
        f.seek(offset)
        while True:
            header = f.read(12)
            if len(header) < 12:
                break
            length = struct.unpack("<Q", header[:8])[0]
            if length > 64 * 1024 * 1024:
                break                   # corrupt header; stop rather than allocate garbage
            data, footer = f.read(length), f.read(4)
            if len(data) < length or len(footer) < 4:
                break
            records.append(data)
            offset = f.tell()
    return records, offset

# ---- collector ----------------------------------------------------------------------------

class _Tracked:
    def __init__(self):
        self.offset = 0
        self.series: dict[str, list[tuple[int, float, float]]] = {}   # tag -> (step, wall, value)

    def add(self, tag: str, point: tuple[int, float, float]):
        points = self.series.setdefault(tag, [])
        points.append(point)
        if len(points) > MAX_POINTS:
            del points[::2]             # thin the history instead of growing without bound

VAL_WORDS = ("val", "test", "eval")

def pick_loss_tags(tags) -> tuple[str | None, str | None]:
    """-> (train loss tag, validation/test loss tag). Both are matched on the tag name containing "loss"."""
    losses = sorted(t for t in tags if "loss" in t.lower())
    val = next((t for t in losses if any(w in t.lower() for w in VAL_WORDS)), None)
    train = next((t for t in losses if "train" in t.lower() and t != val), None)         or next((t for t in losses if t != val), None)
    return train, val

def to_bins(points, lo_step: int, hi_step: int, bins: int = MAX_LOSS) -> list[list[float]]:
    """Average (step, wall, value) points into [bin, value] pairs over the step range [lo_step, hi_step]."""
    span = max(1, hi_step - lo_step)
    sums: dict[int, list[float]] = {}
    for step, _wall, value in points:
        b = min(bins - 1, max(0, int((step - lo_step) / span * (bins - 1) + 0.5)))
        entry = sums.setdefault(b, [0.0, 0])
        entry[0] += value; entry[1] += 1
    return [[b, total / n] for b, (total, n) in sorted(sums.items())]

class TensorBoardCollector:
    def __init__(self, roots, total_steps: int | None = None, recent_hours: float = RECENT_HOURS,
                 use_local_gpu: bool = True):
        self.use_local_gpu = use_local_gpu
        self._gpu_cache: tuple[float, tuple | None] = (0.0, None)
        self.roots = [Path(r).expanduser() for r in roots]
        self.total_steps = total_steps
        self.recent = recent_hours * 3600
        self._files: dict[Path, _Tracked] = {}

    def _local_gpu(self, now: float):
        if now - self._gpu_cache[0] > 3:               # nvidia-smi is a subprocess: sample every few seconds
            self._gpu_cache = (now, gpu.sample())
        return self._gpu_cache[1]

    def _event_files(self, now: float):
        newest: dict[Path, tuple[float, Path]] = {}      # one run per directory: its newest file
        for root in self.roots:
            for path in root.rglob("events.out.tfevents.*"):
                try:
                    mtime = path.stat().st_mtime
                except OSError:
                    continue
                if now - mtime <= self.recent and (path.parent not in newest or mtime > newest[path.parent][0]):
                    newest[path.parent] = (mtime, path)
        return [(d, m, p) for d, (m, p) in newest.items()]

    def collect(self, now: float | None = None):
        return [], (Limit(), Limit())          # no sessions or limits here, only runs()

    def runs(self, now: float | None = None) -> list[Run]:
        now = now or time.time()
        runs = []
        for directory, mtime, path in self._event_files(now):
            tracked = self._files.setdefault(path, _Tracked())
            try:
                if path.stat().st_size < tracked.offset:       # file was replaced/truncated
                    tracked.__init__()
                records, tracked.offset = read_new_records(path, tracked.offset)
            except OSError:
                continue
            for record in records:
                try:
                    wall, step, scalars = decode_event(record)
                except (struct.error, IndexError):
                    continue
                for tag, value in scalars:
                    tracked.add(tag, (step, wall, value))
            if not tracked.series:
                continue
            runs.append((mtime, self._to_run(directory, mtime, tracked, now)))
        runs.sort(key=lambda t: (t[1].state != RUNNING, -t[0]))      # running first, then the most recently active
        return [run for _, run in runs]

    def _to_run(self, directory: Path, mtime: float, tracked: _Tracked, now: float) -> Run:
        training = {t: v for t, v in tracked.series.items() if not t.startswith("vibehud/")}
        if not training:
            training = tracked.series
        loss_tag, val_tag = pick_loss_tags(training)
        main = training[loss_tag] if loss_tag else max(training.values(), key=len)
        step, last_wall = main[-1][0], main[-1][1]
        # Rate from the most recent points of the main series (wall times are the writer's).
        window = main[-20:]
        rate = None
        if len(window) >= 2 and window[-1][1] > window[0][1] and window[-1][0] > window[0][0]:
            rate = (window[-1][0] - window[0][0]) / (window[-1][1] - window[0][1])
        age = now - mtime
        declared = tracked.series.get(gpu.TAG_TOTAL_STEPS)       # logged by vibehud.gpu.start_logging(total_steps=N)
        total = int(declared[-1][2]) if declared else self.total_steps
        state = RUNNING if age <= STALL_AFTER else STALLED if age <= FINISHED_AFTER else DONE
        if total and step >= total:
            state = DONE
        try:
            name = str(directory.relative_to(next(r for r in self.roots if directory.is_relative_to(r)))) or directory.name
        except StopIteration:
            name = directory.name
        if name in ("", "."):
            name = directory.name
        parts = name.split("/")
        if len(parts) > 1 and parts[-1].lower() in ("tb", "tensorboard"):
            name = "/".join(parts[:-1])                      # <run>/tb: the run is the folder above
        run = Run(id=f"{zlib.crc32(str(directory).encode()):08x}", name=f"{name} s{step}", state=state, rate=rate)
        if total:
            run.progress = min(1.0, step / total)
            if rate and state == RUNNING:
                run.eta_s = int(max(0, total - step) / rate)
        def latest(tag):
            points = tracked.series.get(tag)
            return points[-1][2] if points else None
        run.gpu, run.vram_used, run.vram_total = latest(gpu.TAG_UTIL), latest(gpu.TAG_USED), latest(gpu.TAG_TOTAL)
        if run.gpu is None and state == RUNNING and self.use_local_gpu:
            # The script did not log GPU tags: use this machine's GPU (right for local single-job use).
            reading = self._local_gpu(now)
            if reading:
                run.gpu, run.vram_used, run.vram_total = reading
        accuracy = [t for t in training if "acc" in t.lower() and any(w in t.lower() for w in VAL_WORDS)]
        if accuracy:
            value = training[sorted(accuracy)[0]][-1][2]
            run.val_acc = value * 100 if value <= 1.0 else value     # fractions (0..1) and percentages both occur
        if loss_tag:
            curves = [tracked.series[t] for t in (loss_tag, val_tag) if t]
            lo = min(c[0][0] for c in curves)
            hi = max(c[-1][0] for c in curves)
            run.loss = to_bins(tracked.series[loss_tag], lo, hi)
            if val_tag:
                run.val_loss = to_bins(tracked.series[val_tag], lo, hi)
        return run
