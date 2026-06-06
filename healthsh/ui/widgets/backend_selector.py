"""``BackendSelector(QComboBox)`` — backend chooser used by the AI screen."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QComboBox, QWidget

# Backends the dropdown exposes (matches AIService.BackendName values minus 'mock').
SUPPORTED_BACKENDS: tuple[str, ...] = ("ollama", "anthropic", "openai")


class BackendSelector(QComboBox):
    """Combo box emitting ``backend_changed(str)`` whenever the user picks one."""

    backend_changed = Signal(str)

    def __init__(self, *, current: str = "ollama", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        for name in SUPPORTED_BACKENDS:
            self.addItem(name)
        if current in SUPPORTED_BACKENDS:
            self.setCurrentText(current)
        self.currentTextChanged.connect(self.backend_changed)

    def set_backend(self, name: str) -> None:
        """Programmatically pick a backend without emitting twice."""
        if name not in SUPPORTED_BACKENDS:
            raise ValueError(f"unknown backend: {name!r}")
        if self.currentText() == name:
            return
        self.setCurrentText(name)
