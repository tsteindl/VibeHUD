"""Optional ~/.vibehud/config.toml. Everything works without it; it only adds accounts and labels.

    [[claude]]
    label = "W"
    home = "~/.claude-work"        # that account's CLAUDE_CONFIG_DIR

    [[tensorboard]]
    root = "~/runs"                # searched recursively for events.out.tfevents.* files
    total_steps = 10000            # optional: enables progress % and ETA

    [[remote]]                     # another machine, over your normal ssh (see remote.py)
    host = "hpc-login"             # a name from ~/.ssh/config, or user@host
    label = "hpc"                  # shown on screen as "Claude (hpc)"
    args = "--tensorboard ~/runs --total-steps 10000"   # optional, passed to the remote vibehud

    [[codex]]
    label = "W"
    home = "~/.codex-work"         # that account's CODEX_HOME
    max_age_hours = 12             # optional
"""
from __future__ import annotations
try:
    import tomllib
except ImportError:                     # Python < 3.11
    try:
        import tomli as tomllib
    except ImportError:
        tomllib = None
from pathlib import Path
from .claude import ClaudeCollector, default_home as claude_home
from .remote import RemoteCollector
from .tensorboard import TensorBoardCollector
from .codex import CodexCollector, default_home as codex_home

def config_path() -> Path:
    return Path.home() / ".vibehud" / "config.toml"

def load_collectors(path: Path | None = None):
    """Accounts from the config file; otherwise whichever default homes exist on this computer."""
    path = path or config_path()
    if path.is_file() and tomllib is None:
        raise SystemExit("vibehud: reading ~/.vibehud/config.toml needs Python 3.11+ or `pip install tomli`")
    cfg = tomllib.loads(path.read_text("utf-8")) if path.is_file() else {}
    collectors = [ClaudeCollector(Path(e["home"]).expanduser(), e.get("label")) for e in cfg.get("claude", [])]
    collectors += [CodexCollector(Path(e["home"]).expanduser(), e.get("label"), e.get("max_age_hours", 12))
                   for e in cfg.get("codex", [])]
    collectors += [TensorBoardCollector([e["root"]], e.get("total_steps")) for e in cfg.get("tensorboard", [])]
    collectors += [RemoteCollector(e["host"], e.get("label"), e.get("python", "python3"), e.get("args", ""),
                                   e.get("interval", 15.0)) for e in cfg.get("remote", [])]
    if not any(isinstance(c, (ClaudeCollector, CodexCollector)) for c in collectors):
        if (claude_home() / "sessions").is_dir():
            collectors.append(ClaudeCollector())
        if (codex_home() / "sessions").is_dir():
            collectors.append(CodexCollector())
    return collectors
