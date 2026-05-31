# CLAUDE.md — Healthsh

Guidance for AI coding agents and humans contributing to Healthsh. Read this end-to-end before opening a PR.

## Project mission

Healthsh is an open-source Linux desktop system health monitor built on PySide6 / Qt 6 and Python 3.11+. Unlike conventional monitors that only plot metrics, Healthsh runs an AI layer that **interprets and predicts** system state — surfacing root causes, anomalies, and likely near-future failures in human-readable form. The UX target is a calm, glanceable dashboard that feels like a co-pilot for your machine, not a wall of graphs.

Detailed scope, sprint plan, and per-screen specs live in `HEALTHSH_ROADMAP.md` (local-only, not committed).

## Architecture (clean / layered)

Layers, from innermost to outermost:

1. `healthsh.domain` — pure types, value objects, business rules. **No cross-imports between domain modules.** No I/O, no Qt, no psutil.
2. `healthsh.core` — business rules and analysis (thresholds, formatting, deterministic insight derivation). **May import only from `domain`.**
3. `healthsh.services` — orchestration glue (history service, AI service, collector coordination). May import from `core` and `domain`. **Does not own worker threads** — those live in `infra/threads/` per the roadmap.
4. `healthsh.infra` — adapters to the OS (collectors), Docker, journald, filesystem, SQLite, and the worker threads that drive the cadence. **Leaf layer: never imported by `domain` or `core`.** `services` and `ui` consume it via interfaces declared in `core`.
5. `healthsh.ui` — PySide6 widgets, screens, theming. **UI depends inward only**: `ui → services / core / domain / infra`. Reverse imports are forbidden.

Dependency rule: imports always point inward. If you need an outer-layer capability in an inner layer, define an interface in `core` and inject the implementation from `infra` at composition time (`healthsh.app`).

The canonical folder tree lives in `HEALTHSH_ROADMAP.md` §3 and is created in issue #2.

## Design system

The visual language is defined in **`HEALTHSH_ROADMAP.md` §4** (Tokyo Night palette). That section is **normative** — treat it like a spec, not a suggestion.

- All colors, spacing, radii, and typography tokens live in `healthsh.ui.theme.palette` (and sibling token modules).
- Widgets **must** pull from those tokens. **Never hardcode hex values, rgb tuples, or pixel sizes in widget code.**
- If a token is missing, add it to `theme` first, then consume it.

## Threading & cadence

The UI thread **never blocks**. All sampling and inference runs on workers that live under `healthsh.infra.threads`:

- **Fast metrics worker** (`metrics_worker.py`) — 1s tick (CPU, RAM, disk, GPU).
- **Slow worker** (`slow_worker.py`) — 3s tick (Docker, journald, AI interpretation passes).

Workers communicate to the UI via Qt signals only. No direct widget mutation from a worker thread. Any operation > 5 ms goes off the UI thread.

## Testing

- Framework: **pytest** + **pytest-qt**.
- Qt API pinned to PySide6 via `pyproject.toml` (`qt_api = "pyside6"`).
- Headless / CI runs must export `QT_QPA_PLATFORM=offscreen` before invoking pytest.
- Tests live in `tests/`, mirroring the package layout. Unit tests for `domain` / `core` must not import Qt.

Quick run:

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/pytest
```

## Code style

- Formatter & linter: **ruff** (format + check). Run `ruff format .` and `ruff check .` before committing.
- Line length: 100.
- Enabled rule sets: `E, F, I, UP, B, SIM`.
- **Type hints required** on all function signatures (parameters and return types).
- **Docstrings required** on all public API (anything not prefixed with `_`).
- Soft size limits — refactor when exceeded:
  - Functions: ~50 lines.
  - Files: ~200 lines.
- No `print` in library code; use the project logger.

## Library-first principle

Prefer well-maintained libraries over hand-rolled code. Custom code is a liability — justify it in the PR description.

- Use **`psutil`** for process and system metrics. Do **not** parse `/proc` by hand.
- Use **`pyqtgraph`** for plots. Do **not** roll custom QPainter charts (gauges are an exception — see issue #7).
- When Docker support lands (issue #17), use **`docker` (docker-py)** — do not shell out to the `docker` CLI.
- When structured AI I/O lands, prefer **`pydantic`** schemas over ad-hoc dicts.

Dependencies are introduced when the issue that needs them is opened, not preemptively. The current runtime deps are `PySide6`, `pyqtgraph`, `psutil` (see `pyproject.toml`).

## Commits — Conventional Commits

Format: `<type>(<scope>): <subject>`

Allowed types: `feat`, `fix`, `refactor`, `chore`, `docs`, `test`, `build`.

Examples:

- `feat(ui): add cpu sparkline widget`
- `fix(services): debounce slow-worker on suspend/resume`
- `chore: bump ruff to 0.6`

Subject in imperative mood, no trailing period, < 72 chars.

## Branches

Pattern: `feature/s<sprint>-<slug>`

Examples: `feature/s0-pyproject`, `feature/s1-metrics-worker`, `feature/s3-docker-collector`.

Bug fixes use `fix/<slug>`; chores use `chore/<slug>`.

## Pull requests

- **One PR per issue.**
- PR body must include `Closes #N` so the issue auto-closes on merge.
- Title mirrors the primary commit subject (Conventional Commits format).
- PR description states: what changed, why, and how it was tested (link to the test files or describe manual steps).
- CI must be green (`ruff check`, `ruff format --check`, `pytest`) before merge.
- Merge to `main` with `--no-ff` to preserve the feature branch history.

## Onboarding — fresh clone runbook

```bash
git clone https://github.com/rhaymisonbetini/healthsh.git
cd healthsh
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -e ".[dev]"
ruff check .
ruff format --check .
QT_QPA_PLATFORM=offscreen pytest
healthsh        # runs the app (stub until issue #4 ships)
```

## Project metadata

- Package name: `healthsh`
- Build backend: **hatchling** (PEP 517).
- License: MIT.
- Python: `>=3.11` (do not raise this floor without an issue — dev boxes on 3.12 are fine, but the spec is 3.11).
- Entry point: `healthsh = "healthsh.app:main"` (declared in `pyproject.toml` since issue #1; the real `QApplication` bootstrap lands in issue #4).
- Upstream: https://github.com/rhaymisonbetini/healthsh
