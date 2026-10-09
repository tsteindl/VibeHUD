"""Child-process options shared by everything that shells out (ssh, nvidia-smi)."""
import sys

# The agent normally runs windowless (pythonw). A console program started from it, such as ssh.exe,
# would otherwise open and close a console window on every poll.
NO_WINDOW = {"creationflags": 0x08000000} if sys.platform == "win32" else {}      # CREATE_NO_WINDOW
