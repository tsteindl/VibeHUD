"""Provider-neutral snapshot, and its wire encoding (protocol VH1, see firmware/VibeHUD/host_link.h)."""
from __future__ import annotations
import unicodedata
from dataclasses import asdict, dataclass, field

WORKING, NEEDS_USER, IDLE = 0, 1, 2
RUNNING, STALLED, DONE, FAILED = 0, 1, 2, 3
MAX_SESSIONS, MAX_RUNS, MAX_LOSS = 8, 4, 48

@dataclass
class Session:
    provider: str
    profile: str
    title: str
    status: int
    updated: float = 0.0          # epoch seconds, used for ordering only

@dataclass
class Limit:
    used_pct: float | None = None
    reset_s: int | None = None

@dataclass
class Run:
    id: str
    name: str
    state: int
    progress: float | None = None
    rate: float | None = None
    eta_s: int | None = None
    gpu: float | None = None
    vram_used: float | None = None
    vram_total: float | None = None
    # Loss curves as [bin, value] pairs on a shared 0..MAX_LOSS-1 axis (train is dense, validation sparse).
    loss: list = field(default_factory=list)
    val_loss: list = field(default_factory=list)
    val_acc: float | None = None      # latest validation accuracy, percent

@dataclass
class Snapshot:
    sessions: list[Session] = field(default_factory=list)
    hourly: Limit = field(default_factory=Limit)
    weekly: Limit = field(default_factory=Limit)
    runs: list[Run] = field(default_factory=list)

def snapshot_to_json(snapshot: Snapshot) -> str:
    """Exchange format between a remote `vibehud --json` and the agent that owns the board."""
    import json
    return json.dumps(asdict(snapshot))

def snapshot_from_json(text: str) -> Snapshot:
    import json
    d = json.loads(text)
    return Snapshot(
        sessions=[Session(**x) for x in d.get("sessions", [])],
        hourly=Limit(**d.get("hourly", {})), weekly=Limit(**d.get("weekly", {})),
        runs=[Run(**x) for x in d.get("runs", [])])

_TRANSLIT = {"ä": "ae", "ö": "oe", "ü": "ue", "Ä": "Ae", "Ö": "Oe", "Ü": "Ue", "ß": "ss",
             "–": "-", "—": "-", "…": "...", "’": "'", "“": '"', "”": '"'}

def ascii_text(text: str, limit: int) -> str:
    """The display font is ASCII only: transliterate, drop control characters and tabs, truncate."""
    for src, dst in _TRANSLIT.items():
        text = text.replace(src, dst)
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    text = "".join(c if c >= " " else " " for c in text)
    return " ".join(text.split())[:limit]

def _num(value, fmt="{:g}") -> str:
    return "-" if value is None else fmt.format(value)

def encode(snapshot: Snapshot) -> bytes:
    lines = ["VH1 BEGIN"]
    for s in snapshot.sessions[:MAX_SESSIONS]:
        lines.append("\t".join(["SESSION", ascii_text(s.provider, 15), ascii_text(s.profile, 7),
                                str(s.status), ascii_text(s.title, 95)]))
    for key, limit in (("h", snapshot.hourly), ("w", snapshot.weekly)):
        lines.append("\t".join(["LIMIT", key, _num(limit.used_pct, "{:.1f}"), _num(limit.reset_s, "{:d}")]))
    for r in snapshot.runs[:MAX_RUNS]:
        def series(points):
            return ",".join(f"{int(x)}:{v:.4g}" for x, v in points[-MAX_LOSS:]) or "-"
        lines.append("\t".join(["RUN", ascii_text(r.id, 15), ascii_text(r.name, 39), str(r.state),
                                _num(r.progress, "{:.4f}"), _num(r.rate, "{:.2f}"), _num(r.eta_s, "{:d}"),
                                _num(r.gpu, "{:.0f}"), _num(r.vram_used, "{:.1f}"), _num(r.vram_total, "{:.1f}"), series(r.loss), series(r.val_loss), _num(r.val_acc, "{:.2f}")]))
    lines.append("END")
    return ("\n".join(lines) + "\n").encode("ascii")
