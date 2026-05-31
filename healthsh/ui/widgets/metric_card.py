"""Reusable titled card shell shared by all metric widgets."""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from healthsh.ui.icons import get_icon_pixmap

# Title icon size (px) — matches HEADER_ICON_SIZE for visual coherence.
_TITLE_ICON_SIZE: int = 16


class MetricCard(QFrame):
    """Card with an icon + title bar at the top and a vertical content area.

    Subclasses populate the content area via :meth:`content_layout` and update
    the rows via their own typed setters; this base class only owns the
    chrome (background, border, radius, title icon).
    """

    def __init__(
        self,
        *,
        title: str,
        icon_name: str,
        icon_color: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setProperty("role", "card")
        self.setFrameShape(QFrame.Shape.NoFrame)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 10, 12, 12)
        outer.setSpacing(8)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(8)

        icon_label = QLabel()
        icon_label.setFixedSize(_TITLE_ICON_SIZE, _TITLE_ICON_SIZE)
        icon_label.setPixmap(get_icon_pixmap(icon_name, icon_color, _TITLE_ICON_SIZE))
        header.addWidget(icon_label, alignment=Qt.AlignmentFlag.AlignVCenter)

        title_label = QLabel(title)
        title_label.setProperty("role", "section-title")
        header.addWidget(title_label, alignment=Qt.AlignmentFlag.AlignVCenter)
        header.addStretch(1)
        outer.addLayout(header)

        self._content_layout = QVBoxLayout()
        self._content_layout.setContentsMargins(0, 0, 0, 0)
        self._content_layout.setSpacing(6)
        outer.addLayout(self._content_layout, stretch=1)

    def content_layout(self) -> QVBoxLayout:
        """Return the vertical layout subclasses populate with rows."""
        return self._content_layout

    def clear_content(self) -> None:
        """Remove every widget in the content area (used before each refresh)."""
        while self._content_layout.count():
            item = self._content_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()

    def sizeHint(self) -> QSize:  # noqa: D401 — Qt callback name
        """Use the default size hint but keep a sensible minimum."""
        hint = super().sizeHint()
        return QSize(max(hint.width(), 280), max(hint.height(), 160))
