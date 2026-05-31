# Healthsh v0.1.0 — Dashboard preview

First public preview. Sprint 0 + Sprint 1 complete: a themed desktop window, a
live Dashboard fed by typed metric collectors on a dedicated worker thread,
multi-vendor GPU support, system-tray integration and a single-file AppImage.

## Install

Download `Healthsh-0.1.0-x86_64.AppImage` from this release, then:

```bash
chmod +x Healthsh-0.1.0-x86_64.AppImage
./Healthsh-0.1.0-x86_64.AppImage
```

The AppImage bundles Python 3.12 and PySide6, so there is nothing to install on
the host beyond a `libfuse2` package if your distribution does not provide it.

## What ships

### Chrome
- Tokyo Night theme (`HEALTHSH_ROADMAP §4` palette) applied through a single
  global QSS + a tiny QFont bootstrap (pixel sizing so the QSS and QFont
  agree).
- 44 px header with three decorative traffic lights, the section icon and
  title, a muted subtitle, and a 200 px right-side slot reserved for the
  Dashboard's `live · 1s` indicator.
- 48 px sidebar with six Tabler-outline icons (Dashboard, System, Docker,
  Logs, AI, Settings — pinned to the bottom). The active item paints in
  `accent.blue`, inactive in `text.muted`.
- Minimum window size enforced at 1100 × 680.

### Dashboard
- Four KPI gauges drawn with `QPainter`: CPU (blue), RAM (purple), Disk
  (blue → amber ≥ 75 %), and GPU when present. Each gauge auto-flips to
  `accent.amber` at the warning threshold (default 75 %) and to
  `accent.red` at the critical threshold (default 90 %).
- **Adaptive GPU slot.** A GPU gauge is added only when the GPU detection
  chain returns a real reading. After five consecutive "no GPU" snapshots
  the layout commits to three gauges for the rest of the run — no "n/a"
  placeholder ever paints.
- 60-second sliding sparkline (PyQtGraph) with two lines (CPU blue, RAM
  purple); strictly bounded `deque(maxlen=60)` memory.
- AI insight banner with a sparkles icon — placeholder copy for now; the
  Sprint 5 analysis pipeline ships in v0.5.0.
- Containers summary card (placeholder data wired in #17) and Top-memory
  process card with live data.

### Metrics layer
- `psutil`-backed CPU, RAM, and disk collectors returning frozen domain
  entities.
- **Multi-vendor GPU detection chain** in `healthsh/infra/collectors/gpu/`:
  - NVIDIA via `nvidia-smi` with a 2 s subprocess timeout and a CSV parser
    tolerant of `[N/A]` cells
  - AMD Radeon via `/sys/class/drm/card*/device/` (`gpu_busy_percent`,
    `mem_info_vram_used`, `mem_info_vram_total`) and the amdgpu hwmon
    temperature sensor
  - Intel iGPU via `gt_cur_freq_mhz / gt_RP0_freq_mhz` (no VRAM, no temp)
  - Returns `None` cleanly on machines with no GPU — no exceptions, no log
    spam
- `MetricsWorker(QThread)` ticks every 1 s, emits a typed
  `MetricsSnapshot`, isolates per-collector failures so a single bad
  reading does not kill the worker. Cooperative stop within 2 s — no
  `terminate()`.
- `CollectorService` owns the worker lifecycle and re-emits its signal so
  the UI never touches the worker directly.

### System tray
- `QSystemTrayIcon` wrapper with a `Show / hide window` + `Quit` menu.
- Closing the window hides to the tray when the platform exposes one
  (one-time toast tells the user the app is still running).
- `setQuitOnLastWindowClosed(False)` so the tray remains the persistent
  surface; the explicit Quit menu item stops the collector service before
  exit.

## Packaging

- `pyproject.toml` (PEP 621, hatchling backend, Python ≥ 3.11).
- `ruff` for lint + format (rule sets `E, F, I, UP, B, SIM`).
- `pytest` + `pytest-qt` (Qt API pinned to PySide6, headless runs use
  `QT_QPA_PLATFORM=offscreen`).
- `scripts/build_appimage.sh` runs PyInstaller and `appimagetool` end to
  end. The included `Healthsh-0.1.0-x86_64.AppImage` is the output of that
  script on this dev box.

## Tested on

- Ubuntu 24.04 LTS, kernel 6.8, AMD Radeon (verified end-to-end: the GPU
  gauge mounts with vendor=`amd`, util / VRAM / temp from sysfs).

## Known limitations (filed for later sprints)

- **No AI yet.** The Dashboard AI banner shows static placeholder copy.
  The agent layer (Ollama / Anthropic / OpenAI tool-calling) ships in
  Sprint 5 (v0.5.0).
- **No System / Docker / Logs / Settings screens yet.** The sidebar routes
  to placeholder screens for those — they ship in Sprints 2 → 6.
- **GPU support is read-only and per-machine first hit.** Multi-GPU
  listing is a follow-up.
- **Settings are not persisted yet.** Thresholds, intervals, and the
  hide-to-tray toggle hard-code their defaults; `QSettings` integration
  arrives in Sprint 6.
- **No `.deb` yet.** That ships with v1.0.0 in Sprint 7.

## Verification

- `176 passed, 1 expected skip` under `QT_QPA_PLATFORM=offscreen pytest`.
- `ruff check .` and `ruff format --check .` both clean.

## Thanks

This release was implemented entirely in a single session via the GitHub
issues for #1 → #12, one branch per issue, all merged into `main`. Read
the commit log for the per-issue detail.
