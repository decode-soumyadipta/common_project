from __future__ import annotations

from qtpy.QtCore import Qt, Signal
from qtpy.QtGui import QColor
from qtpy.QtWidgets import (
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QStyle,
    QVBoxLayout,
    QWidget,
)


class ClientCollapsibleSection(QFrame):
    """Client-only collapsible section wrapper with a full-width header."""

    class _HeaderBar(QFrame):
        """Clickable header with title on left and arrow on right."""

        toggled = Signal(bool)

        def __init__(self, title: str, expanded: bool, parent: QWidget | None = None):
            super().__init__(parent)
            self.setObjectName("clientCollapseHeader")
            self.setCursor(Qt.CursorShape.PointingHandCursor)
            self._expanded = expanded

            self._title_label = QLabel(title, self)
            self._title_label.setObjectName("clientCollapseTitle")
            self._title_label.setCursor(Qt.CursorShape.PointingHandCursor)

            self._arrow_label = QLabel(self)
            self._arrow_label.setObjectName("clientCollapseArrow")
            self._arrow_label.setCursor(Qt.CursorShape.PointingHandCursor)
            self._arrow_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._arrow_label.setFixedSize(16, 16)

            layout = QHBoxLayout(self)
            layout.setContentsMargins(10, 6, 10, 6)
            layout.setSpacing(8)
            layout.addWidget(self._title_label, 1)
            layout.addWidget(self._arrow_label, 0)

            self.setMinimumHeight(34)
            self._apply_state()

        def set_expanded(self, expanded: bool) -> None:
            self._expanded = expanded
            self._apply_state()

        def _apply_state(self) -> None:
            arrow_icon = self.style().standardIcon(
                QStyle.StandardPixmap.SP_ArrowDown
                if self._expanded
                else QStyle.StandardPixmap.SP_ArrowRight
            )
            self._arrow_label.setPixmap(arrow_icon.pixmap(14, 14))

        def mousePressEvent(self, event) -> None:  # type: ignore[override]
            if event.button() == Qt.MouseButton.LeftButton:
                self._expanded = not self._expanded
                self._apply_state()
                self.toggled.emit(self._expanded)
                event.accept()
                return
            super().mousePressEvent(event)

    def __init__(
        self,
        title: str,
        content: QWidget,
        expanded: bool = True,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.setObjectName("clientCollapseSection")
        self._content = content
        self._expanded = expanded

        self._header = self._HeaderBar(title, expanded, self)
        self._header.toggled.connect(self._on_toggled)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._header)
        layout.addWidget(self._content)

        self._apply_shadow()
        self._apply_state(expanded)

    def _apply_shadow(self) -> None:
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(3.0)
        shadow.setOffset(0.0, 1.0)
        shadow.setColor(QColor(0, 0, 0, 28))
        self.setGraphicsEffect(shadow)

    def _apply_state(self, expanded: bool) -> None:
        self._expanded = expanded
        self._header.set_expanded(expanded)
        self._content.setVisible(expanded)

    def set_expanded(self, expanded: bool) -> None:
        self._apply_state(expanded)

    def _on_toggled(self, checked: bool) -> None:
        self._apply_state(checked)
