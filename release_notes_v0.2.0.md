# Healthsh v0.2.0 — System & Docker

Second public release. Sprints 2 + 3 close: the **System** screen surfaces
per-core CPU, sensors, swap, load and a live process table; the **Docker**
screen lists running and stopped containers with start / stop / restart /
logs actions; and the no-Docker UX is a first-class informational state — no
red, no exception screams, just helpful copy and a *Re-check now* button.

## Install

Build from source for v0.2.0:

```bash
git clone https://github.com/rhaymisonbetini/healthsh.git
cd healthsh
git checkout v0.2.0
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev,build]"
healthsh
```

(The v0.1.0 AppImage from the previous release still loads the System and
Docker screens — those modules are pure-Python additions — but a fresh
v0.2.0 AppImage will follow if the build pipeline regenerates one in the
upcoming v0.5.0 release.)

## What ships

### System / Processes screen (Sprint 2)

- **System collector** (`infra/collectors/system_collector.py`) aggregating
  per-chip temperatures (Intel `coretemp` → Package id 0, AMD
  `k10temp` → Tctl/Tdie, generic fallback), swap, load average and
  uptime. Empty sensors dict on VMs does not raise.
- **`CoreBars` widget** — lazy 4-column grid of mini-bars, one per logical
  core. Each bar flips from `accent.blue` to `accent.amber` at ≥ 85 %.
  Cells are reused across the 1 Hz refresh — no flicker.
- **`ProcessTable` widget** — `QTableView` over a custom
  `QAbstractTableModel`. Five columns (`PID`, `Name`, `CPU%`, `MEM`,
  `User`) with per-column foreground colours via `Qt.ForegroundRole` (no
  delegate needed). CPU% paints amber at ≥ 75 %. The header's sort
  toggle cycles between `memory` and `cpu`; sorting happens in Python,
  not via the view's in-place sort, so the 1 Hz refresh cannot fight it.
  Scroll position is captured before every reset and restored after.
- **System screen** with `By core` label + `CoreBars`, three small stat
  cards (`Temp CPU` — amber at ≥ 70 °C, `Swap` — `no swap` when absent,
  `Processes` count), and the `ProcessTable` taking the remaining space.
  Header subtitle: `N cores · load X.XX / Y.YY / Z.ZZ · up Nd Nh`.

### Docker screen (Sprint 3)

- **`DockerCollector`** with the typed five-state detection chain:
  `ok`, `not_installed`, `daemon_down`, `permission_denied`,
  `unknown`. Status caches; when not ok it re-probes every 60 s
  (the UI recovers within a minute of you fixing things) without log
  spam. `force_recheck()` backs the *Re-check now* button.
- **`SlowWorker(QThread)`** — 3 s cadence, cooperative stop, single
  wake event + flags, restartable. Per-container stats fetch is
  parallelised over a 4-worker `ThreadPoolExecutor` so the tick stays
  well under budget even with 20+ containers.
- **`CollectorService`** now owns both the fast metrics worker and the
  slow Docker worker, exposes `docker_ready` alongside `metrics_ready`,
  and surfaces `docker_recheck()`.
- **`ContainerCard` widget** with running / stopped variants: status
  dot, name, image:tag, `up Nd`, CPU % / MEM / ports row, and four
  action buttons (`pause`, `restart`, `logs` for running; `play` for
  stopped). Stopped cards render `card-inactive` with 0.7 opacity.
  Memory amber rule: ≥ 1 GiB OR ≥ 80 % of `mem_limit`. Restart and
  stop go through a confirmation dialog; pause / start do not. Logs
  open in a modal `QPlainTextEdit` with the last 200 lines in a mono
  font.
- **`DockerScreen`** composes a `QStackedWidget` of two views: the
  cards view (`QScrollArea` reconciling cards in place per 3 s tick,
  running first by name, then stopped by name) and the empty-state
  view (`DockerEmptyState`). Mode flips on every `docker_ready`
  emission with no flicker. The AI banner placeholder sits at the
  bottom of the cards view; it is hidden in empty-state mode so the
  informational message stands on its own.
- **Empty-state UX (`DockerEmptyState`)** — one card per `kind`, never
  a red accent. `not_installed` → friendly copy + an `Install Docker
  →` button (`QDesktopServices.openUrl`). `daemon_down` → mono
  snippet `sudo systemctl start docker` + a `Re-check now` button.
  `permission_denied` → click-to-copy mono `sudo usermod -aG docker
  $USER` with a "copied" toast. `unknown` → body includes the
  upstream error detail + `Re-check now`.
- Docker actions (`start` / `stop` / `restart`) dispatch through a
  `QThreadPool` `QRunnable` so the UI thread never blocks on a docker-py
  HTTP round-trip.

### Library-first

- `docker` (docker-py) added to runtime deps; we never shell out to the
  Docker CLI.
- `psutil.sensors_temperatures` for temps; `os.getloadavg` for load;
  `psutil.swap_memory` + `psutil.boot_time` for the rest.
- Five new Tabler outline icons bundled (`player-pause`, `player-play`,
  `refresh`, `copy`, `external-link`).

## Verification

- `259 passed, 1 skipped` under `QT_QPA_PLATFORM=offscreen pytest`.
- `ruff check .` and `ruff format --check .` both clean.

## Known limitations (filed for later sprints)

- **No AI yet.** The Docker AI banner shows static placeholder copy. The
  agent layer ships in Sprint 5 (v0.5.0).
- **No journald yet.** The Logs screen is still a placeholder. Sprint 4
  (`#20`–`#22`) wires it.
- **Pause action maps to stop.** docker-py distinguishes them but the v0.2
  Docker screen treats both as "halt this for now". Real pause support is
  a tiny follow-up — currently filed in #18.
- **No multi-machine support.** Healthsh observes the local host's daemon
  only; remote daemons land post-1.0.
