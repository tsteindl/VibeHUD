"""Start the agent at login. A computer cannot be made to run code just by plugging a USB device in,
so this is the one-time setup per computer; afterwards the agent waits for the board, whenever it is
plugged in or unplugged.

  Windows  per-user Run registry key "VibeHUD" (no admin rights; Task Scheduler needs them), pythonw: no window
  Linux    systemd --user service `vibehud.service` (falls back to ~/.config/autostart/vibehud.desktop)
  macOS    LaunchAgent ~/Library/LaunchAgents/com.vibehud.agent.plist

Everything runs as you, with this Python (the one that has vibehud installed). Logs: ~/.vibehud/agent.log
"""
from __future__ import annotations
import os, plistlib, shlex, shutil, subprocess, sys
from pathlib import Path

LOG = Path.home() / ".vibehud" / "agent.log"
TASK = "VibeHUD"

def _python() -> str:
    exe = Path(sys.executable)
    if sys.platform == "win32":
        windowless = exe.with_name("pythonw.exe")
        if windowless.exists():
            return str(windowless)
    return str(exe)

def _agent_args(extra: str) -> list[str]:
    return ["-m", "vibehud", "--log", str(LOG), *shlex.split(extra, posix=sys.platform != "win32")]

class _Runner:
    def __init__(self, dry_run: bool):
        self.dry_run = dry_run

    def run(self, cmd: list[str], check: bool = True) -> int:
        print("  $ " + " ".join(shlex.quote(c) if " " in c else c for c in cmd))
        if self.dry_run:
            return 0
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode and check:
            print((result.stderr or result.stdout).strip(), file=sys.stderr)
        return result.returncode

    def write(self, path: Path, content: str | bytes):
        print(f"  write {path}")
        if self.dry_run:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content if isinstance(content, bytes) else content.encode("utf-8"))

    def delete(self, path: Path):
        print(f"  delete {path}")
        if not self.dry_run:
            path.unlink(missing_ok=True)

# ---- Windows --------------------------------------------------------------------------------

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"

def _windows(r: _Runner, remove: bool, extra: str) -> int:
    import winreg
    print("  registry HKCU\\" + RUN_KEY + "\\" + TASK)
    if remove:
        if not r.dry_run:
            try:
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
                    winreg.DeleteValue(key, TASK)
            except FileNotFoundError:
                print("  (was not installed)")
        print("Removed. A running agent keeps running until you stop it or log out.")
        return 0
    command = subprocess.list2cmdline([_python(), *_agent_args(extra)])
    print(f"  command {command}")
    if not r.dry_run:
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            winreg.SetValueEx(key, TASK, 0, winreg.REG_SZ, command)
        # Start it now as well, detached from this console, so no re-login is needed.
        subprocess.Popen([_python(), *_agent_args(extra)], creationflags=0x00000008 | 0x00000200, close_fds=True,
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        print("Installed and started. It will also start at every login.")
    return 0

# ---- Linux ----------------------------------------------------------------------------------

def _linux(r: _Runner, remove: bool, extra: str) -> int:
    unit = Path.home() / ".config/systemd/user/vibehud.service"
    desktop = Path.home() / ".config/autostart/vibehud.desktop"
    if remove:
        if shutil.which("systemctl"):
            r.run(["systemctl", "--user", "disable", "--now", "vibehud.service"], check=False)
        r.delete(unit); r.delete(desktop)
        if shutil.which("systemctl"):
            r.run(["systemctl", "--user", "daemon-reload"], check=False)
        return 0
    command = " ".join(shlex.quote(c) for c in [_python(), *_agent_args(extra)])
    try:
        groups = subprocess.run(["id", "-nG"], capture_output=True, text=True).stdout.split()
        if not {"dialout", "uucp"} & set(groups):
            print("Note: you are not in the 'dialout' group, so the board's serial port may not open.\n"
                  "      Fix once with:  sudo usermod -aG dialout $USER   (then log out and in)")
    except OSError:
        pass
    if shutil.which("systemctl"):
        r.write(unit, f"[Unit]\nDescription=VibeHUD agent\n\n[Service]\nExecStart={command}\nRestart=on-failure\nRestartSec=5\n\n"
                      "[Install]\nWantedBy=default.target\n")
        r.run(["systemctl", "--user", "daemon-reload"])
        return r.run(["systemctl", "--user", "enable", "--now", "vibehud.service"])
    r.write(desktop, f"[Desktop Entry]\nType=Application\nName=VibeHUD\nExec={command}\nX-GNOME-Autostart-enabled=true\n")
    print("No systemd found: installed an XDG autostart entry instead (starts at next login).")
    return 0

# ---- macOS ----------------------------------------------------------------------------------

def _macos(r: _Runner, remove: bool, extra: str) -> int:
    plist_path = Path.home() / "Library/LaunchAgents/com.vibehud.agent.plist"
    target = f"gui/{os.getuid()}"
    if remove:
        r.run(["launchctl", "bootout", target, str(plist_path)], check=False)
        r.delete(plist_path)
        return 0
    plist = {"Label": "com.vibehud.agent", "ProgramArguments": [_python(), *_agent_args(extra)],
             "RunAtLoad": True, "KeepAlive": True, "StandardOutPath": str(LOG), "StandardErrorPath": str(LOG)}
    r.write(plist_path, plistlib.dumps(plist))
    r.run(["launchctl", "bootout", target, str(plist_path)], check=False)    # replace a previous version
    return r.run(["launchctl", "bootstrap", target, str(plist_path)])

def run(remove: bool = False, dry_run: bool = False, extra_args: str = "") -> int:
    r = _Runner(dry_run)
    print(("Removing" if remove else "Installing") + " VibeHUD autostart" + (" (dry run, nothing changed)" if dry_run else ""))
    if sys.platform == "win32":
        return _windows(r, remove, extra_args)
    if sys.platform == "darwin":
        return _macos(r, remove, extra_args)
    return _linux(r, remove, extra_args)
