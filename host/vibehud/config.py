"""Optional ~/.vibehud/config.toml. Everything works without it; it only adds remote machines.

    runs = ["~/runs"]              # this computer's TensorBoard log folders (default), searched recursively

    [[remote]]                     # another machine, over your normal ssh (see remote.py)
    host = "hpc-login"             # a name from ~/.ssh/config, or user@host
    label = "hpc"                  # shown on screen in front of that machine's runs
    python = "python3"             # optional: the remote's python (3.9+)
    runs = ["~/runs"]              # optional: that machine's log folders (default)

Every machine, this one and the remotes, gets the same automatic sources: Claude Code and Codex sessions
in their default folders, planned runs listed in ~/.vibehud/queue/*.txt, and the GPU from nvidia-smi.
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
from .codex import CodexCollector, default_home as codex_home
from .queue import QueueCollector, DEFAULT_DIR
from .remote import RemoteCollector
from .tensorboard import TensorBoardCollector

DEFAULT_RUNS = ["~/runs"]

def config_path() -> Path:
    return Path.home() / ".vibehud" / "config.toml"

def local_collectors(runs, remote: bool = False):
    """Everything this computer can report. On a remote the agent only reads: no Claude usage polling."""
    collectors = [TensorBoardCollector(runs), QueueCollector([DEFAULT_DIR])]
    if (claude_home() / "sessions").is_dir():
        collectors.append(ClaudeCollector(poll_usage=not remote))
    if (codex_home() / "sessions").is_dir():
        collectors.append(CodexCollector())
    return collectors

def load_collectors(path: Path | None = None):
    path = path or config_path()
    if path.is_file() and tomllib is None:
        raise SystemExit("vibehud: reading ~/.vibehud/config.toml needs Python 3.11+ or `pip install tomli`")
    cfg = tomllib.loads(path.read_text("utf-8")) if path.is_file() else {}
    collectors = local_collectors(cfg.get("runs", DEFAULT_RUNS))
    collectors += [RemoteCollector(e["host"], e.get("label"), e.get("python", "python3"), e.get("runs", DEFAULT_RUNS))
                   for e in cfg.get("remote", [])]
    return collectors
