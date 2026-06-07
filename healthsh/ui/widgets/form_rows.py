"""Small labelled form-row widgets used to compose the Settings screen.

Every row is a ``label · control`` pair that exposes a uniform contract:

* a ``changed`` Qt signal carrying the new typed value (emitted on *user*
  edits only — programmatic :meth:`set_value` is silent),
* ``value()`` / ``set_value()`` accessors.

Keeping the rows tiny and uniform lets :class:`SettingsCard` and
:class:`~healthsh.ui.screens.settings_screen.SettingsScreen` wire each one to a
single ``settings_service.set(key, row.value())`` call.
"""

from __future__ import annotations

from collections.abc import Iterable

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSlider,
    QSpinBox,
    QWidget,
)

# Fixed width for the leading label column so controls line up across rows.
_LABEL_WIDTH: int = 220


def _row_label(text: str) -> QLabel:
    """Build the leading label for a row."""
    label = QLabel(text)
    label.setProperty("role", "primary")
    label.setFixedWidth(_LABEL_WIDTH)
    return label


class _BaseRow(QWidget):
    """Common ``[label][stretch][control]`` scaffold for the concrete rows."""

    def __init__(self, label: str, *, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._label = _row_label(label)
        self._box = QHBoxLayout(self)
        self._box.setContentsMargins(0, 4, 0, 4)
        self._box.setSpacing(10)
        self._box.addWidget(self._label, alignment=Qt.AlignmentFlag.AlignVCenter)
        self._box.addStretch(1)

    def set_label(self, text: str) -> None:
        """Update the leading label text."""
        self._label.setText(text)


class IntRow(_BaseRow):
    """Integer spinner row (range + step enforce validation)."""

    changed = Signal(int)

    def __init__(
        self,
        label: str,
        *,
        minimum: int,
        maximum: int,
        step: int = 1,
        suffix: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(label, parent=parent)
        self._spin = QSpinBox()
        self._spin.setRange(minimum, maximum)
        self._spin.setSingleStep(step)
        if suffix:
            self._spin.setSuffix(suffix)
        self._spin.valueChanged.connect(self.changed)
        self._box.addWidget(self._spin)

    def value(self) -> int:
        """Return the current integer value."""
        return self._spin.value()

    def set_value(self, value: int) -> None:
        """Set the value without emitting :pyattr:`changed`."""
        self._spin.blockSignals(True)
        self._spin.setValue(int(value))
        self._spin.blockSignals(False)


class ToggleRow(_BaseRow):
    """Boolean checkbox row."""

    changed = Signal(bool)

    def __init__(self, label: str, *, parent: QWidget | None = None) -> None:
        super().__init__(label, parent=parent)
        self._check = QCheckBox()
        self._check.toggled.connect(self.changed)
        self._box.addWidget(self._check)

    def value(self) -> bool:
        """Return whether the toggle is checked."""
        return self._check.isChecked()

    def set_value(self, value: bool) -> None:
        """Set the checked state without emitting :pyattr:`changed`."""
        self._check.blockSignals(True)
        self._check.setChecked(bool(value))
        self._check.blockSignals(False)


class DropdownRow(_BaseRow):
    """Single-choice combo-box row."""

    changed = Signal(str)

    def __init__(
        self,
        label: str,
        *,
        options: Iterable[str],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(label, parent=parent)
        self._combo = QComboBox()
        for option in options:
            self._combo.addItem(option)
        self._combo.currentTextChanged.connect(self.changed)
        self._box.addWidget(self._combo)

    def value(self) -> str:
        """Return the selected option text."""
        return self._combo.currentText()

    def set_value(self, value: str) -> None:
        """Select ``value`` without emitting :pyattr:`changed`."""
        self._combo.blockSignals(True)
        self._combo.setCurrentText(str(value))
        self._combo.blockSignals(False)


class TextRow(_BaseRow):
    """Free-text row; ``password`` masks input behind an eye reveal button.

    Edits commit on ``editingFinished`` (Enter / focus-out) rather than on each
    keystroke, so subscribers are not spammed while the user types an API key.
    """

    changed = Signal(str)

    def __init__(
        self,
        label: str,
        *,
        password: bool = False,
        placeholder: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(label, parent=parent)
        self._edit = QLineEdit()
        self._edit.setPlaceholderText(placeholder)
        self._edit.setMinimumWidth(260)
        self._password = password
        if password:
            self._edit.setEchoMode(QLineEdit.EchoMode.Password)
        self._edit.editingFinished.connect(lambda: self.changed.emit(self._edit.text()))
        self._box.addWidget(self._edit)

        self._eye = QPushButton("show")
        self._eye.setProperty("role", "ghost")
        self._eye.setCheckable(True)
        self._eye.setVisible(password)
        self._eye.toggled.connect(self._on_reveal_toggled)
        self._box.addWidget(self._eye)

    def value(self) -> str:
        """Return the current text."""
        return self._edit.text()

    def set_value(self, value: str) -> None:
        """Set the text without emitting :pyattr:`changed`."""
        self._edit.blockSignals(True)
        self._edit.setText(str(value))
        self._edit.blockSignals(False)

    def set_password(self, password: bool) -> None:
        """Switch between masked (API key) and plain (endpoint) modes."""
        self._password = password
        self._eye.setVisible(password)
        if password and not self._eye.isChecked():
            self._edit.setEchoMode(QLineEdit.EchoMode.Password)
        else:
            self._edit.setEchoMode(QLineEdit.EchoMode.Normal)

    def is_masked(self) -> bool:
        """Return whether the text is currently hidden behind the mask."""
        return self._edit.echoMode() == QLineEdit.EchoMode.Password

    def _on_reveal_toggled(self, revealed: bool) -> None:
        self._edit.setEchoMode(
            QLineEdit.EchoMode.Normal if revealed else QLineEdit.EchoMode.Password
        )
        self._eye.setText("hide" if revealed else "show")


class SliderRow(_BaseRow):
    """Horizontal slider row with a live numeric readout."""

    changed = Signal(int)

    def __init__(
        self,
        label: str,
        *,
        minimum: int = 0,
        maximum: int = 100,
        suffix: str = "%",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(label, parent=parent)
        self._suffix = suffix
        self._slider = QSlider(Qt.Orientation.Horizontal)
        self._slider.setRange(minimum, maximum)
        self._slider.setMinimumWidth(160)
        self._readout = QLabel()
        self._readout.setProperty("role", "muted")
        self._readout.setFixedWidth(48)
        self._slider.valueChanged.connect(self._on_slider)
        self._box.addWidget(self._slider)
        self._box.addWidget(self._readout)
        self._update_readout(self._slider.value())

    def value(self) -> int:
        """Return the current slider value."""
        return self._slider.value()

    def set_value(self, value: int) -> None:
        """Set the slider without emitting :pyattr:`changed`."""
        self._slider.blockSignals(True)
        self._slider.setValue(int(value))
        self._slider.blockSignals(False)
        self._update_readout(int(value))

    def _on_slider(self, value: int) -> None:
        self._update_readout(value)
        self.changed.emit(value)

    def _update_readout(self, value: int) -> None:
        self._readout.setText(f"{value}{self._suffix}")
