"""Busy overlay widget with loading spinner and message."""

from __future__ import annotations

from qtpy.QtCore import Qt
from qtpy.QtGui import QFontMetrics
from qtpy.QtWidgets import (
    QLabel,
    QProgressBar,
    QVBoxLayout,
    QWidget,
)


class BusyOverlay(QWidget):
    """Semi-transparent overlay with a loading spinner and message."""

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        # Block mouse events while busy
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        
        self.layout = QVBoxLayout(self)
        self.layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        self.container = QWidget()
        self.container.setFixedSize(420, 112)
        self.container.setObjectName("busyContainer")
        self.container.setStyleSheet("""
            QWidget#busyContainer {
                background: rgba(248, 252, 255, 0.97);
                border: 1px solid #0b67c2;
                border-radius: 0px;
            }
            QLabel#busyStatus {
                color: #0b67c2;
                font-size: 13px;
                font-weight: 600;
                letter-spacing: 0.4px;
            }
            QLabel#busyFile {
                color: #1f2a36;
                font-size: 15px;
                font-weight: 600;
            }
        """)
        
        self.inner_layout = QVBoxLayout(self.container)
        self.inner_layout.setContentsMargins(18, 16, 18, 16)
        self.inner_layout.setSpacing(8)
        
        self.status = QLabel("LOADING")
        self.status.setObjectName("busyStatus")
        self.status.setAlignment(Qt.AlignmentFlag.AlignLeft)
        
        self.file_message = QLabel("Preparing layer...")
        self.file_message.setObjectName("busyFile")
        self.file_message.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self.file_message.setWordWrap(False)
        
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(6)
        self.progress.setStyleSheet("""
            QProgressBar {
                background: #d9e7f7;
                border: none;
                border-radius: 0px;
            }
            QProgressBar::chunk {
                background: #0b67c2;
                border-radius: 0px;
            }
        """)
        
        self.inner_layout.addWidget(self.status)
        self.inner_layout.addWidget(self.file_message)
        self.inner_layout.addWidget(self.progress)
        
        self.layout.addWidget(self.container)
        self.hide()

    def show_with_message(self, message: str):
        clean_message = (message or "Loading...").strip()
        file_text = clean_message
        if clean_message.lower().startswith("loading "):
            file_text = clean_message[8:]
        if file_text.endswith("..."):
            file_text = file_text[:-3].strip()
        if not file_text:
            file_text = "Preparing layer"

        # Keep filenames readable without wrapping; trim with ellipsis if needed.
        metrics = QFontMetrics(self.file_message.font())
        max_width = max(120, self.container.width() - 40)
        file_text = metrics.elidedText(file_text, Qt.TextElideMode.ElideMiddle, max_width)

        self.file_message.setText(file_text)
        self.raise_()
        self.show()


__all__ = ["BusyOverlay"]
