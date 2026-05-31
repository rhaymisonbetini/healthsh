# Healthsh

> AI-powered Linux desktop system health monitor.
> Built with Python 3.11+ and PySide6 (Qt 6).

![status](https://img.shields.io/badge/status-pre--alpha-orange)
![license](https://img.shields.io/badge/license-MIT-blue)
![python](https://img.shields.io/badge/python-3.11%2B-brightgreen)

## What is Healthsh?

Healthsh is a desktop app that shows the real-time health of your Linux machine — CPU, RAM, disk, GPU, temperatures, journald logs, Docker containers, and top processes — all in one clean, native-feeling window.

**What sets it apart from `btop`, `htop`, `glances`, or `netdata`** is *not* the metrics — everyone shows those. It's the **AI layer that interprets**:

- predicts when your disk will fill up,
- detects containers that are leaking memory,
- groups repeated journald errors into actionable signals,
- answers natural-language questions like *"why did my PC freeze at 2 PM?"* by cross-referencing historical metrics with logs.

Everything runs locally. No backend. No telemetry. No analytics.

## Status

**Pre-alpha.** Development is tracked as GitHub [Issues](../../issues) grouped under [Milestones](../../milestones), one per sprint. Each issue carries its own scope, architecture context, design tokens, tasks, and acceptance criteria — open any issue to see what to build and how it fits in.

- **v0.1.0** ships at the end of Sprint 1 (Dashboard + tray, AppImage).
- **v0.2.0** ships at the end of Sprint 3 (Docker screen).
- **v0.5.0** ships at the end of Sprint 5 (AI diagnosis is live).
- **v1.0.0** ships at the end of Sprint 7 (`.deb` + AppImage release).

## Stack

| Layer | Tech |
|---|---|
| Language | Python 3.11+ |
| UI | PySide6 (Qt 6), PyQtGraph, QPainter |
| Metrics | psutil + direct `/proc`, `/sys` reads |
| GPU | `nvidia-smi` (NVIDIA first, AMD/Intel later) |
| Docker | docker-py |
| Logs | `journalctl` JSON output |
| Storage | SQLite (stdlib) |
| AI | Tool-calling agents over Ollama / Anthropic / OpenAI |
| Packaging | PyInstaller + AppImage (`.deb` later) |

Rationale per stack choice lives in the Sprint 0 issues.

## Architecture

Clean Architecture in layers. The dependency rule points inward: **UI depends on core; core never imports UI.**

```
healthsh/
├── domain/      # pure entities, no external deps
├── core/        # business rules (thresholds, analysis, formatting)
├── services/    # orchestration (collectors, history, AI)
├── infra/       # collectors, threads, DB
└── ui/          # PySide6 widgets and screens
```

A detailed `ARCHITECTURE.md` ships as part of [Sprint 7](../../milestones).

## Contributing

Work is tracked as GitHub Issues, grouped by Sprint Milestones. Pick an unblocked issue, branch from `main` as `feature/sX-<slug>`, and open a PR referencing `Closes #<n>`. Conventional Commits (`feat:`, `fix:`, `refactor:`, ...).

## License

MIT — see [LICENSE](./LICENSE).
