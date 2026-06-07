# Healthsh v0.6.0 — Settings & polish

Sprint 6 closes. Healthsh now has a real home for configuration: a typed,
persistent settings store and a five-section Settings screen whose changes
apply **live at runtime** — change a cadence and the workers retune, drag a
threshold and the gauges flip colour on the next paint, flip "Start at login"
and an XDG autostart entry appears.

## Install

```bash
git clone https://github.com/rhaymisonbetini/healthsh.git
cd healthsh
git checkout v0.6.0
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev,build]"
healthsh
```

## What ships

### Settings persistence (#28)

- **`SettingsStore`** (`infra/settings_store.py`) wraps `QSettings`
  (`NativeFormat`/`UserScope`) and persists to
  `~/.config/Healthsh/Healthsh.conf` on Linux. Because the INI backend
  round-trips every value as text, reads are coerced back to the type of the
  supplied default (`bool` before `int`, since `bool` is an `int` subclass). A
  `path=` shortcut lets tests point it at a temp file.
- **`SettingsService`** (`services/settings_service.py`) exposes typed
  `get`/`set`, a `snapshot()` returning a frozen `Settings` dataclass, and a
  `setting_changed(key)` signal for live reconfiguration. The `Settings`
  dataclass is the **single source of truth** for the schema + defaults;
  `DEFAULTS` is derived from it so the two can never drift. Dotted keys map to
  attributes by replacing the first `.` with `_`.

### Autostart (#30)

- **`infra/autostart.py`** (stdlib only) manages a single
  `~/.config/autostart/healthsh.desktop` entry: `enable_autostart` /
  `disable_autostart` / `is_enabled`, plus `resolve_executable()` (prefers
  `$APPIMAGE`, then `which healthsh`, then the interpreter) and
  `apply_autostart(enabled)` which returns `False` when enabling but no
  executable resolves — the friendly-error hook the Settings screen surfaces.
- **`--tray` flag** in `app.py` boots the app hidden into the system tray and
  starts the collectors immediately, so autostart gives always-on monitoring
  without popping the window.

### Live-applying Settings screen (#29)

- **Form-row widgets** (`ui/widgets/form_rows.py`): `IntRow`, `ToggleRow`,
  `DropdownRow`, `TextRow`, `SliderRow` — a uniform `changed` signal that fires
  on *user* edits only (silent on programmatic `set_value`). `TextRow` masks
  API keys behind a `show/hide` eye and commits on `editingFinished` so
  subscribers aren't spammed mid-typing.
- **`SettingsCard`** — a titled section card pulling `role="card"` from the
  design tokens (no hardcoded hex).
- **Settings screen** (`ui/screens/settings_screen.py`): five sections —
  Collection, AI, Alerts/thresholds, Appearance, System — in a `QScrollArea`.
  The single AI field repoints between **endpoint** (Ollama, plain) and **API
  key** (Anthropic/OpenAI, masked) as the backend dropdown changes; thresholds
  carry a live `amber at X %, red at Y %` preview.
- **`SettingsController`** (`services/settings_controller.py`) is the decoupled
  subscriber that turns writes into runtime effects: `collection.*` →
  `set_interval_ms` on both workers; `thresholds.*` →
  `DashboardScreen.apply_thresholds()` recolours gauges on the next paint;
  `system.minimize_to_tray` → `MainWindow.set_minimize_to_tray`;
  `system.start_at_login` → `autostart.apply_autostart`; `ai.*` →
  `AIService.set_backend(backend_from_settings(...))`. `MainWindow` composes the
  service + controller and applies the persisted snapshot at startup.

## Verification

- `422 passed, 1 skipped` under `QT_QPA_PLATFORM=offscreen pytest`.
- `ruff check .` and `ruff format --check .` both clean.

## Known limitations (filed for later sprints)

- **Appearance accent is data-only.** The dropdown stores the value; colour
  swatches and runtime accent re-theming are cosmetic polish, deferred.
- **AI-backend live swap is wired through the controller**, but `MainWindow`
  does not yet own an `AIService` (the AI screen owns its own), so that wire
  activates once app composition is unified.
- **No `.deb` / AppImage release pipeline yet.** Final packaging + CI lands
  with v1.0.0 in Sprint 7 (#32).
