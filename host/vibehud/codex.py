"""Codex collector. Reads <CODEX_HOME> only; never writes, never sends anything anywhere.

Sources (verified against Codex CLI/VS Code 0.162):
  session_index.jsonl             {"id", "thread_name", "updated_at"}  -> session titles
  sessions/Y/M/D/rollout-*.jsonl  first line session_meta (cwd); event_msg task_started /
                                  task_complete -> working vs idle; event_msg token_count carries
                                  rate_limits.primary (300 min) / .secondary (10080 min) with
                                  used_percent and resets_at (epoch seconds).
Rollout files reach tens of MB, so only the tail of each file is read, and results are cached
per (mtime, size).
"""
from __future__ import annotations
import base64, json, os, time
from pathlib import Path
from .model import Limit, Session, WORKING, IDLE

TAIL_BYTES = 512 * 1024
LIMIT_LOOKBACK = 8 * 24 * 3600     # limits stay meaningful for the weekly window
WORKING_MAX_SILENCE = 15 * 60      # a turn with no file activity for this long is treated as dead

def default_home() -> Path:
    return Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex")

def account_email(home: Path) -> str | None:
    """Email from the locally stored id_token (not verified); used only to label the account."""
    try:
        token = json.loads((home / "auth.json").read_text("utf-8"))["tokens"]["id_token"]
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        return json.loads(base64.urlsafe_b64decode(payload)).get("email")
    except Exception:
        return None

def _tail_lines(path: Path) -> list[str]:
    with path.open("rb") as f:
        f.seek(0, os.SEEK_END)
        end = f.tell()
        f.seek(max(0, end - TAIL_BYTES))
        data = f.read()
    lines = data.decode("utf-8", "replace").split("\n")
    return lines[1:] if end > TAIL_BYTES else lines   # a mid-file read starts with a partial line

def _first_json(path: Path) -> dict:
    with path.open("rb") as f:
        try:
            return json.loads(f.readline())
        except ValueError:
            return {}

class CodexCollector:
    def __init__(self, home: Path | None = None, label: str | None = None, max_age_h: float = 12):
        self.home = Path(home) if home else default_home()
        self.max_age = max_age_h * 3600
        if label is None:
            email = account_email(self.home)
            label = email[0].upper() if email else "-"
        self.label = label
        self._cache: dict[Path, tuple[float, int, dict]] = {}
        self._titles: dict[str, str] = {}
        self._titles_stamp = (0.0, 0)

    def _load_titles(self):
        index = self.home / "session_index.jsonl"
        try:
            st = index.stat()
        except OSError:
            return
        if (st.st_mtime, st.st_size) == self._titles_stamp:
            return
        titles = {}
        for line in index.read_text("utf-8", "replace").splitlines():
            try:
                d = json.loads(line)
                titles[d["id"]] = d.get("thread_name") or ""
            except (ValueError, KeyError):
                pass
        self._titles, self._titles_stamp = titles, (st.st_mtime, st.st_size)

    def _inspect(self, path: Path, st: os.stat_result) -> dict:
        cached = self._cache.get(path)
        if cached and cached[0] == st.st_mtime and cached[1] == st.st_size:
            return cached[2]
        info = {"cwd": _first_json(path).get("payload", {}).get("cwd", ""), "turn_open": False, "limits": {}}
        for line in _tail_lines(path):
            try:
                d = json.loads(line)
            except ValueError:
                continue
            if d.get("type") != "event_msg":
                continue
            p = d.get("payload", {})
            kind = p.get("type")
            if kind == "task_started":
                info["turn_open"] = True
            elif kind in ("task_complete", "turn_aborted"):
                info["turn_open"] = False
            elif kind == "token_count" and p.get("rate_limits"):
                # Events alternate between limit ids (e.g. "codex" and an empty "premium"): keep the latest of each.
                info["limits"][p["rate_limits"].get("limit_id")] = p["rate_limits"]
        self._cache[path] = (st.st_mtime, st.st_size, info)
        return info

    def collect(self, now: float | None = None) -> tuple[list[Session], tuple[Limit, Limit]]:
        now = now or time.time()
        self._load_titles()
        root = self.home / "sessions"
        found = []
        if root.is_dir():
            for path in root.rglob("rollout-*.jsonl"):
                try:
                    st = path.stat()
                except OSError:
                    continue
                if now - st.st_mtime <= LIMIT_LOOKBACK:
                    found.append((st.st_mtime, path, st))
        found.sort(key=lambda x: x[0], reverse=True)
        sessions, limit_source = [], None
        for mtime, path, st in found:
            recent = now - mtime <= self.max_age
            if not recent and limit_source is not None:
                break                      # older files only matter as a source for the usage limits
            try:
                info = self._inspect(path, st)
            except OSError:
                continue
            if limit_source is None and (usable := _usable_limits(info["limits"])):
                limit_source = usable             # newest file that has real limits wins
            if not recent:
                continue
            session_id = path.stem[-36:]
            title = self._titles.get(session_id) or Path(info["cwd"]).name or "untitled session"
            working = info["turn_open"] and now - mtime < WORKING_MAX_SILENCE
            sessions.append(Session("Codex", self.label, title, WORKING if working else IDLE, mtime))
        return sessions, _limits(limit_source, now)

def _usable_limits(by_id: dict) -> dict | None:
    if by_id.get("codex", {}).get("primary"):
        return by_id["codex"]
    return next((r for r in by_id.values() if r.get("primary") or r.get("secondary")), None)

def _limits(rate_limits: dict | None, now: float) -> tuple[Limit, Limit]:
    def one(window: dict | None) -> Limit:
        if not window:
            return Limit()
        resets_at = window.get("resets_at")
        if resets_at is not None and resets_at < now:
            return Limit(0.0, None)        # the window rolled over since the last event: nothing used yet
        return Limit(window.get("used_percent"), None if resets_at is None else int(resets_at - now))
    if not rate_limits:
        return Limit(), Limit()
    return one(rate_limits.get("primary")), one(rate_limits.get("secondary"))
