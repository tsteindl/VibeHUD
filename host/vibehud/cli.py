from __future__ import annotations
import argparse, json, shutil, sys, time
from pathlib import Path
from .config import load_collectors
from .claude import default_home as claude_home
from .model import Limit, Snapshot, encode, snapshot_to_json, MAX_SESSIONS, MAX_RUNS
from .tensorboard import TensorBoardCollector

def gather(collectors) -> Snapshot:
    snap = Snapshot()
    for c in collectors:
        try:
            sessions, (hourly, weekly) = c.collect()
            runs = c.runs() if hasattr(c, "runs") else []
        except Exception as e:                       # one broken source must not blank the display
            print(f"[vibehud] {type(c).__name__} failed: {e}", file=sys.stderr)
            continue
        snap.sessions += sessions
        snap.runs += runs
        # Several accounts: show the most used window, which is the one that will bite first.
        for attr, new in (("hourly", hourly), ("weekly", weekly)):
            cur: Limit = getattr(snap, attr)
            if new.used_pct is not None and (cur.used_pct is None or new.used_pct > cur.used_pct):
                setattr(snap, attr, new)
    # Needs-you first (it is waiting on a human), then working, then idle; newest first within each.
    snap.sessions.sort(key=lambda s: ({1: 0, 0: 1, 2: 2}[s.status], -s.updated))
    snap.sessions = snap.sessions[:MAX_SESSIONS]
    snap.runs.sort(key=lambda r: r.state)            # running first
    snap.runs = snap.runs[:MAX_RUNS]
    return snap

def describe(snap: Snapshot) -> str:
    names = {0: "working", 1: "needs you", 2: "idle"}
    out = [f"  {s.provider} ({s.profile}) [{names[s.status]}] {s.title}" for s in snap.sessions] or ["  (no recent sessions)"]
    states = {0: "running", 1: "stalled", 2: "done", 3: "error"}
    for r in snap.runs:
        gpu = f" gpu {r.gpu:.0f}% vram {r.vram_used:.1f}/{r.vram_total:.0f}G" if r.gpu is not None and r.vram_used is not None else ""
        out.append(f"  run {r.name} [{states[r.state]}] " + (f"{r.progress:.0%} " if r.progress is not None else "")
                   + (f"{r.rate:.1f}/s " if r.rate else "") + (f"loss {r.loss[-1][1]:.3f}" if r.loss else "") + (f" val {r.val_loss[-1][1]:.3f}" if r.val_loss else "") + gpu)
    for key, l in (("5h", snap.hourly), ("week", snap.weekly)):
        if l.used_pct is None:
            out.append(f"  limit {key}: unknown")
        else:
            out.append(f"  limit {key}: {l.used_pct:.0f}% used" + (f", reset in {l.reset_s}s" if l.reset_s is not None else ""))
    return "\n".join(out)

# ---- Claude status-line hook (limits) ---------------------------------------------------------

def _hook_command() -> str:
    return f'"{Path(sys.executable).as_posix()}" -m vibehud.claude_statusline'

def install_statusline(home: Path, remove: bool) -> int:
    settings_path, then_path = home / "settings.json", home / "vibehud-then.txt"
    try:
        settings = json.loads(settings_path.read_text("utf-8")) if settings_path.exists() else {}
    except ValueError:
        print(f"{settings_path} is not valid JSON; not touching it.", file=sys.stderr)
        return 1
    existing = settings.get("statusLine") or {}
    ours = "vibehud.claude_statusline" in str(existing.get("command", ""))
    if remove:
        if not ours:
            print("No VibeHUD status line is installed.")
            return 0
        previous = then_path.read_text("utf-8").strip() if then_path.exists() else ""
        if previous:
            settings["statusLine"] = {**existing, "command": previous}
        else:
            del settings["statusLine"]
        then_path.unlink(missing_ok=True)
        print("Removed the VibeHUD status line" + (f"; restored: {previous}" if previous else "."))
    else:
        if ours:
            print("Already installed.")
            return 0
        if existing.get("command"):
            then_path.write_text(existing["command"], "utf-8")
            print(f"Keeping your existing status line: {existing['command']}")
        settings["statusLine"] = {**existing, "type": "command", "command": _hook_command()}
        print(f"Installed. Claude Code now runs: {settings['statusLine']['command']}")
    if settings_path.exists():
        shutil.copy2(settings_path, settings_path.with_name("settings.json.vibehud-backup"))
    settings_path.write_text(json.dumps(settings, indent=2), "utf-8")
    print(f"Edited {settings_path} (backup: settings.json.vibehud-backup).")
    return 0

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="vibehud", description="Feed the VibeHUD USB display.")
    ap.add_argument("--port", help="serial port (default: auto-detect the ESP32-S3 USB device)")
    ap.add_argument("--interval", type=float, default=1.0, help="seconds between snapshots")
    ap.add_argument("--tensorboard", action="append", default=[], metavar="DIR",
                    help="also watch TensorBoard logs under DIR (repeatable)")
    ap.add_argument("--total-steps", type=int, help="total training steps for --tensorboard runs (enables progress and ETA)")
    ap.add_argument("--once", action="store_true", help="print one snapshot and exit (no device needed)")
    ap.add_argument("--json", action="store_true", help="print this machine's snapshot as JSON and exit (used for remote machines)")
    ap.add_argument("--install-autostart", action="store_true", help="start the agent at login (Windows, Linux, macOS)")
    ap.add_argument("--remove-autostart", action="store_true", help="undo --install-autostart")
    ap.add_argument("--autostart-args", default="", metavar="ARGS", help='extra agent arguments for autostart, e.g. "--tensorboard ~/runs"')
    ap.add_argument("--dry-run", action="store_true", help="with --install/--remove-autostart: show what would be done")
    ap.add_argument("--log", metavar="FILE", help="append output to FILE instead of the console")
    ap.add_argument("--install-claude-statusline", action="store_true", help="enable Claude 5h/weekly limits (edits Claude's settings.json, with backup)")
    ap.add_argument("--remove-claude-statusline", action="store_true", help="undo --install-claude-statusline")
    args = ap.parse_args(argv)
    if args.log or sys.stdout is None:               # pythonw / services have no console
        log_path = Path(args.log or Path.home() / ".vibehud" / "agent.log").expanduser()
        log_path.parent.mkdir(parents=True, exist_ok=True)
        sys.stdout = sys.stderr = open(log_path, "a", buffering=1, encoding="utf-8")
    if args.install_autostart or args.remove_autostart:
        from . import autostart
        return autostart.run(remove=args.remove_autostart, dry_run=args.dry_run, extra_args=args.autostart_args)
    if args.install_claude_statusline or args.remove_claude_statusline:
        return install_statusline(claude_home(), remove=args.remove_claude_statusline)
    collectors = load_collectors()
    collectors += [TensorBoardCollector([d], args.total_steps) for d in args.tensorboard]
    if args.json or args.once:
        if any(hasattr(c, "last_error") for c in collectors):
            time.sleep(8)                            # give remote threads a moment to fetch
        snap = gather(collectors)
        print(snapshot_to_json(snap) if args.json else describe(snap))
        for c in collectors:                         # say why a remote is empty instead of staying silent
            if getattr(c, "last_error", None) or (hasattr(c, "last_error") and c._snapshot is None):
                print(f"  remote '{c.label}': {c.last_error or 'no answer yet'}", file=sys.stderr)
        return 0
    from .device import Device                       # pyserial is only needed where a board is attached
    device, waiting = Device(args.port), False
    print("vibehud: running; plug in the board (Ctrl+C to stop)")
    try:
        while True:
            started = time.monotonic()
            if not device.connected():
                if device.connect():
                    print(f"vibehud: connected to {device.serial.port}")
                    waiting = False
                elif not waiting:
                    print("vibehud: waiting for the board...")
                    waiting = True
            if device.connected() and not device.send(encode(gather(collectors))):
                print("vibehud: board disconnected")
            time.sleep(max(0.0, args.interval - (time.monotonic() - started)))
    except KeyboardInterrupt:
        device.close()
        return 0

if __name__ == "__main__":
    raise SystemExit(main())
