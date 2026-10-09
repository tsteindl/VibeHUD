# Roadmap

## MVP (current target): real sessions and limits on the board

- [x] USB protocol, "waiting for host" screen, agent with board auto-discovery
- [x] Codex: sessions, exact 5 h / weekly limits
- [x] Claude Code: live sessions (status, title), multiple config dirs via `~/.vibehud/config.toml`
- [x] Claude 5 h / weekly limits via the status-line hook (installer written and tested on a temp config; needs `--install-claude-statusline` on the real one, then verify the real payload)
- [ ] Verify Claude `waiting` / `requires_action` states appear in `sessions/<pid>.json` (taken from the
      extension source, not yet observed in files) and that "needs you" lights up
- [x] Agent autostart on login: `--install-autostart` (a computer cannot be made to run code by plugging in a USB device; one-time install per computer). Windows tested; Linux/macOS written but untested
- [ ] Agent autostart on login (Windows startup entry) and a one-command installer
- [ ] Settings stored on the board so it works unchanged on another computer

## Deferred until the MVP works (do not forget)

Training-run data, all of which the protocol (`RUN` lines) and the UI already support with mock data:

- [x] GPU utilisation and VRAM per run: `vibehud.gpu.start_logging(writer)` (nvidia-smi, torch fallback), local nvidia-smi fallback; untested on a real NVIDIA GPU
- [x] Remote machines over ssh (`[[remote]]`, `vibehud --json`); tested with a local stand-in for ssh, not yet against a real host
- [ ] Loss curve, progress %, rate, ETA from real runs
- [ ] `vibehud` logging library: script, Jupyter (`%load_ext vibehud`), Lightning/HF/Keras callbacks
- [x] TensorBoard event-file reader (dependency-free) + dummy example; limits: no total steps, no GPU, finished/crashed is guessed
- [ ] Run-file format and discovery of run files (the precise alternative to TensorBoard files)
- [ ] HPC: `vibehud-remote` helper over SSH + Slurm state (queued / running / failed, time limit)
- [ ] Opt-in `tqdm` auto-reporting

## Polish ideas

- Accuracy: show the latest val accuracy as a number next to the loss (not a second curve); optionally a page that plots it
- Publish `vibehud` on PyPI so remote install is `pip install vibehud` instead of copying the folder

- Dino running animation tuning on the real panel; check physical readability at laptop distance
- Optional Wi-Fi mode for sessions running elsewhere (cloud / remote machines)
- Codex "needs your input" (via its `notify` hook, since the files do not show it)
