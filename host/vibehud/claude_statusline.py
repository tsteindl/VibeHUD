"""Claude Code status-line hook that records the 5 h / 7 day usage windows for VibeHUD.

Claude Code runs the configured `statusLine` command and pipes a JSON document to its stdin. Since
Claude Code added `rate_limits` there (see the Claude Code changelog: "Added `rate_limits` field to
statusline scripts ... 5-hour and 7-day windows with `used_percentage` and `resets_at`"), that
document is the supported way to read the numbers that /usage and the VS Code panel show.

This hook stores the `rate_limits` object next to the session files (<config dir>/vibehud-limits.json)
and prints nothing, so Claude's status line stays empty. If you already had a status line, the installer
saves its command in <config dir>/vibehud-then.txt; the same stdin is then passed to it and its output
is printed, so your existing status line keeps working.

It only fires while a Claude session is active, so the stored numbers are as fresh as your last
Claude activity; the collector resets a window to 0% once its reset time has passed.
"""
from __future__ import annotations
import json, os, subprocess, sys, time
from pathlib import Path

def config_dir() -> Path:
    return Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude")

def limits_path(home: Path) -> Path:
    return home / "vibehud-limits.json"

def main() -> int:
    raw = sys.stdin.read()
    then = None
    try:
        limits = json.loads(raw).get("rate_limits")
        if limits:
            home = config_dir()
            target = limits_path(home)
            tmp = target.with_suffix(".tmp")
            tmp.write_text(json.dumps({"updated": time.time(), "rate_limits": limits}), "utf-8")
            os.replace(tmp, target)
    except Exception:
        pass                                    # a status line must never break Claude Code
    try:
        then = (config_dir() / "vibehud-then.txt").read_text("utf-8").strip() or None
    except OSError:
        pass
    if then:
        out = subprocess.run(then, input=raw, capture_output=True, text=True, shell=True)
        sys.stdout.write(out.stdout)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
