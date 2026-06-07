"""Autostart infra tests — toggle the .desktop entry under a temp XDG dir."""

from __future__ import annotations

from pathlib import Path

import pytest

from healthsh import app
from healthsh.infra import autostart


@pytest.fixture
def xdg_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point XDG_CONFIG_HOME at a temp dir so we never touch the real config."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    return tmp_path


def test_disabled_by_default(xdg_config: Path) -> None:
    assert autostart.is_enabled() is False


def test_enable_writes_desktop_file(xdg_config: Path) -> None:
    path = autostart.enable_autostart("/opt/healthsh/healthsh")
    assert path == xdg_config / "autostart" / "healthsh.desktop"
    assert autostart.is_enabled() is True
    body = path.read_text(encoding="utf-8")
    assert "[Desktop Entry]" in body
    assert "Exec=/opt/healthsh/healthsh --tray" in body
    assert "Type=Application" in body
    assert "X-GNOME-Autostart-enabled=true" in body


def test_disable_removes_file(xdg_config: Path) -> None:
    autostart.enable_autostart("/usr/bin/healthsh")
    assert autostart.is_enabled() is True
    autostart.disable_autostart()
    assert autostart.is_enabled() is False


def test_disable_when_absent_is_noop(xdg_config: Path) -> None:
    # Must not raise even though there is nothing to remove.
    autostart.disable_autostart()
    assert autostart.is_enabled() is False


def test_resolve_prefers_appimage(xdg_config: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APPIMAGE", "/home/u/Apps/Healthsh-x86_64.AppImage")
    assert autostart.resolve_executable() == "/home/u/Apps/Healthsh-x86_64.AppImage"


def test_resolve_falls_back_to_which(xdg_config: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("APPIMAGE", raising=False)
    monkeypatch.setattr(autostart.shutil, "which", lambda _name: "/usr/local/bin/healthsh")
    assert autostart.resolve_executable() == "/usr/local/bin/healthsh"


def test_apply_enable_uses_explicit_path(xdg_config: Path) -> None:
    ok = autostart.apply_autostart(True, executable_path="/srv/healthsh")
    assert ok is True
    assert "Exec=/srv/healthsh --tray" in autostart.autostart_file_path().read_text()


def test_apply_disable(xdg_config: Path) -> None:
    autostart.enable_autostart("/srv/healthsh")
    assert autostart.apply_autostart(False) is True
    assert autostart.is_enabled() is False


def test_apply_enable_without_resolvable_executable(
    xdg_config: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("APPIMAGE", raising=False)
    monkeypatch.setattr(autostart.shutil, "which", lambda _name: None)
    monkeypatch.setattr(autostart.sys, "executable", "")
    ok = autostart.apply_autostart(True)
    assert ok is False
    assert autostart.is_enabled() is False


def test_tray_mode_flag_parsing() -> None:
    assert app.tray_mode_requested(["healthsh", "--tray"]) is True
    assert app.tray_mode_requested(["healthsh"]) is False
