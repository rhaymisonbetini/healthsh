# Healthsh v0.5.0 — Logs & AI

Sprint 4 + Sprint 5 close. Healthsh now reads journald, persists every
metric snapshot it sees, runs deterministic analysers over that history,
and (when wired with a real backend) talks to Ollama, Anthropic or
OpenAI via a tool-calling agent — visible tool-call chips and all.

## Install

```bash
git clone https://github.com/rhaymisonbetini/healthsh.git
cd healthsh
git checkout v0.5.0
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev,build]"
healthsh
```

## What ships

### Sprint 4 — Logs

- **journald collector** that shells out to `journalctl -o json`. Reads are
  *incremental*: the cursor remembers the last entry's timestamp so each
  3 s tick only fetches what is new. First call uses a configurable 2 h
  lookback; max 5 000 entries per call. Empty result and no journalctl on
  PATH both degrade cleanly — the UI shows a calm `"journald is
  unavailable on this system."` state instead of an exception.
- **`SlowWorker`** now emits `journal_ready(list[LogEntry])` alongside
  `docker_ready` on every 3 s tick.
- **`LogFilterBar` + `LogLine` widgets**: severity pills
  (`err`/`warn`/`info`/`debug`) filled when active, outlined when
  inactive; mono-typed timestamp + 3 px severity bar + blue-mono unit +
  elided message per row. Mono font detection cached
  (`JetBrains Mono` → `Fira Code` → `Cascadia Mono` → `DejaVu Sans
  Mono` → Qt fixed-style fallback).
- **Logs screen**: scrolling tail backed by a bounded
  `deque(maxlen=5000)`, auto-scroll-pause (`live` ↔ `paused` pill that
  jumps back to live on click), idempotent unit dropdown that doesn't
  flicker on each tick, and the `journald is unavailable` empty state
  when the host doesn't expose journalctl.

### Sprint 5 — AI (the differentiator)

- **`MetricsStore` + `HistoryService`** persist every snapshot into a WAL
  SQLite DB at `$XDG_DATA_HOME/healthsh/healthsh.db` (fallback
  `~/.local/share/healthsh/healthsh.db`). Single connection,
  thread-safe writes. Range queries + bucketed `query_aggregate`
  downsample for charts/forecasts. Daily retention vacuum via `QTimer`
  (default 7 days). A `process_samples` table backs the leak detector.
- **`AnalysisEngine`** runs three deterministic analysers, no LLM
  required:
  - `forecast_disk_full` — least-squares linear regression over
    `disk_used_b` history → ETA-to-full. Severity escalates
    `info` → `warning` (ETA < 7 d) → `critical` (ETA < 24 h). Suppressed
    when the disk is shrinking or ETA > 30 days. Requires ≥ 30 samples
    before trusting the fit.
- `detect_memory_leaks` — per-process memory series gated by three
    rules: window ≥ 10 min, slope ≥ 5 MB/min, total growth ≥ 50 MB.
    Tolerates tiny GC dips.
- `cluster_log_errors` — collapses messages to a signature (UUIDs,
    hex, IPs, paths and bare numbers replaced with placeholders), groups
    by `(unit, signature)`, returns any cluster ≥ 5 entries in the last
    2 h. Priorities > 4 ignored so info chatter doesn't trigger.
- **`AIService` + 4 tools + 3 backends** —
  *clean-room implementation of the "Blocksh agent base" pattern*
  (provenance noted in
  `healthsh/services/AGENT_BASE_LICENSE_AND_PROVENANCE.md`).
  `ToolRegistry` (name → handler + JSON-schema parameters + summariser),
  agent loop bounded at `MAX_TOOL_ROUNDS = 6`, four tools:
  `get_metrics` (`HistoryService` query), `get_logs`
  (`JournaldCollector` window), `get_containers` (`DockerCollector`
  with status passthrough on the non-ok kinds), `get_processes`
  (psutil top-N). Backends use the official SDKs lazy-imported so the
  hard dep surface stays minimal — `OllamaBackend` (httpx POST to
  `/api/chat`), `AnthropicBackend`, `OpenAIBackend`. `MockBackend` for
  tests. Tool failures don't kill the loop — they surface to the model
  + as a `name failed: msg` chip.
- **`InsightService`** ticks every 30 s, asks the engine for current
  insights, picks the most-severe one per target (`dashboard`,
  `docker`, `logs`) and emits per-target Qt signals so screens just
  subscribe.
- **AIBanner.set_insight** renders real insights with severity-coloured
  prefix (red = critical, amber = warning, blue = info) and a
  backtick-entity parser that wraps `` `like-this` `` in blue mono via
  rich text. `None` payload shows the calm `All looks healthy.`
  fallback in muted (no layout shift).
- **AI chat screen** composes `ChatBubble`s (user right, assistant
  left, both `bg.card` with `radius_card`), `ToolCallChip`s on
  assistant turns (📊 metrics, 📄 logs, 🐳 containers, 🧠
  processes), a backend selector, three suggestion chips
  (`Why is it slow?`, `Will the disk fill up?`, `Any container in
  trouble?`), and a `QLineEdit` input. `ask` runs on a `QThreadPool`
  worker so the UI never blocks on a model call. Streaming text deltas
  populate the assistant bubble live as events arrive.

## Verification

- `383 passed, 1 skipped` under `QT_QPA_PLATFORM=offscreen pytest`.
- `ruff check .` and `ruff format --check .` both clean.

## Known limitations (filed for later sprints)

- **No settings UI yet.** Thresholds, retention, lookback window and
  the active backend hard-code their defaults; `QSettings` integration
  arrives in Sprint 6 (#28 → #30).
- **No autostart toggle.** Landing in Sprint 6 (#30).
- **No `.deb` yet.** Final release pipeline lands with v1.0.0 in
  Sprint 7 (#32).
- **AIService backends are lazy-imported.** The `httpx` /
  `anthropic` / `openai` deps are not yet pinned in `pyproject.toml`
  — install them locally to use the matching backend until the
  Settings UI wires them in.
