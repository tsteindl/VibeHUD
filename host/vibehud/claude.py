"""Claude Code collector. Reads <CLAUDE_CONFIG_DIR or ~/.claude> only; never writes or sends anything.

Sources (verified against Claude Code 2.1.29x on Windows, VS Code extension and terminal):
  sessions/<pid>.json           one file per LIVE session, removed on exit: sessionId, cwd, name,
                                status, updatedAt (ms), entrypoint. Status values seen: "busy".
                                The extension source also knows "idle", "waiting" and
                                "requires_action" (waiting for your permission/input); those two
                                are mapped to "needs you" but not yet observed in files.
  projects/<cwd>/<sessionId>.jsonl  transcript; its {"type":"ai-title","aiTitle":...} line is the
                                session title shown in the UI.
  ../.claude.json (oauthAccount.emailAddress)  account email, used only for the default label.
Claude's 5 h / weekly limits are not in these files. They come from the status-line hook
(`vibehud --install-claude-statusline`, see claude_statusline.py), which stores them in
<config dir>/vibehud-limits.json; without the hook this collector reports no limits.
"""
from __future__ import annotations
import json, os, time
from pathlib import Path
from .model import Session, Limit, WORKING, NEEDS_USER, IDLE
from .claude_statusline import limits_path

TAIL_BYTES = 512 * 1024
HEAD_BYTES = 128 * 1024
STALE_AFTER = 12 * 3600          # a session file this old with no updates is ignored

def default_home() -> Path:
    return Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude")

def account_email(home: Path) -> str | None:
    # The default install keeps ~/.claude.json next to ~/.claude; a custom config dir keeps it inside.
    for candidate in (home / ".claude.json", home.parent / ".claude.json"):
        try:
            return json.loads(candidate.read_text("utf-8")).get("oauthAccount", {}).get("emailAddress")
        except (OSError, ValueError, AttributeError):
            continue
    return None

def pid_alive(pid: int) -> bool:
    if os.name == "nt":
        import ctypes
        k32 = ctypes.windll.kernel32
        handle = k32.OpenProcess(0x1000, False, pid)        # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            return False
        code = ctypes.c_ulong()
        ok = k32.GetExitCodeProcess(handle, ctypes.byref(code))
        k32.CloseHandle(handle)
        return bool(ok) and code.value == 259               # STILL_ACTIVE
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True

def _map_status(status: str | None) -> int:
    if status == "busy":
        return WORKING
    if status in ("waiting", "requires_action"):
        return NEEDS_USER
    return IDLE

def _find_title(path: Path) -> str | None:
    """Last ai-title in the transcript: look at the tail first, then the head."""
    with path.open("rb") as f:
        f.seek(0, os.SEEK_END)
        end = f.tell()
        regions = [(max(0, end - TAIL_BYTES), end), (0, min(end, HEAD_BYTES))]
        for start, stop in regions:
            f.seek(start)
            title = None
            for line in f.read(stop - start).decode("utf-8", "replace").split("\n"):
                if '"ai-title"' in line:
                    try:
                        d = json.loads(line)
                    except ValueError:
                        continue
                    if d.get("type") == "ai-title" and d.get("aiTitle"):
                        title = d["aiTitle"]
            if title:
                return title
    return None

class ClaudeCollector:
    def __init__(self, home: Path | None = None, label: str | None = None):
        self.home = Path(home) if home else default_home()
        if label is None:
            email = account_email(self.home)
            label = email[0].upper() if email else "-"
        self.label = label
        self._transcripts: dict[str, Path | None] = {}
        self._titles: dict[Path, tuple[float, int, str | None]] = {}

    def _transcript(self, session_id: str) -> Path | None:
        path = self._transcripts.get(session_id)
        if path is None or not path.exists():
            path = next(iter((self.home / "projects").glob(f"*/{session_id}.jsonl")), None)
            self._transcripts[session_id] = path
        return path

    def _title(self, session_id: str) -> str | None:
        path = self._transcript(session_id)
        if not path:
            return None
        try:
            st = path.stat()
        except OSError:
            return None
        cached = self._titles.get(path)
        if cached and cached[0] == st.st_mtime and cached[1] == st.st_size:
            return cached[2]
        title = _find_title(path)
        self._titles[path] = (st.st_mtime, st.st_size, title)
        return title

    def collect(self, now: float | None = None) -> tuple[list[Session], tuple[Limit, Limit]]:
        now = now or time.time()
        sessions = []
        for path in (self.home / "sessions").glob("*.json"):
            try:
                d = json.loads(path.read_text("utf-8"))
                updated = d["updatedAt"] / 1000
                if now - updated > STALE_AFTER or not pid_alive(int(d["pid"])):
                    continue
                session_id = d["sessionId"]
            except (OSError, ValueError, KeyError, TypeError):
                continue
            title = self._title(session_id) or d.get("name") or Path(d.get("cwd", "")).name or "session"
            sessions.append(Session("Claude", self.label, title, _map_status(d.get("status")), updated))
        return sessions, self._limits(now)

    def _limits(self, now: float) -> tuple[Limit, Limit]:
        try:
            rate_limits = json.loads(limits_path(self.home).read_text("utf-8"))["rate_limits"]
        except (OSError, ValueError, KeyError):
            return Limit(), Limit()
        return _window(rate_limits.get("five_hour"), now), _window(rate_limits.get("seven_day"), now)


def _epoch(value) -> float | None:
    """resets_at as epoch seconds; tolerate milliseconds and ISO-8601 strings."""
    if isinstance(value, (int, float)):
        return value / 1000 if value > 1e12 else float(value)
    if isinstance(value, str):
        try:
            from datetime import datetime
            return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
        except ValueError:
            return None
    return None

def _window(window: dict | None, now: float) -> Limit:
    if not isinstance(window, dict) or window.get("used_percentage") is None:
        return Limit()
    resets_at = _epoch(window.get("resets_at"))
    if resets_at is not None and resets_at <= now:
        return Limit(0.0, None)            # the window rolled over since the hook last ran
    return Limit(float(window["used_percentage"]), None if resets_at is None else int(resets_at - now))
