"""Busy overlay widget with loading spinner and message."""

from __future__ import annotations

from qtpy.QtCore import Qt
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
        self.container.setFixedSize(280, 120)
        self.container.setObjectName("busyContainer")
        self.container.setStyleSheet("""
            QWidget#busyContainer {
                background: rgba(255, 255, 255, 0.95);
                border: 1px solid #0078d4;
                border-radius: 12px;
            }
            QLabel#busyTitle {
                color: #0078d4;
                font-size: 16px;
                font-weight: 700;
            }
            QLabel#busyMessage {
                color: #444444;
                font-size: 13px;
            }
        """)
        
        self.inner_layout = QVBoxLayout(self.container)
        self.inner_layout.setContentsMargins(20, 20, 20, 20)
        self.inner_layout.setSpacing(10)
        
        self.title = QLabel("ResGIS Engine")
        self.title.setObjectName("busyTitle")
        self.title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        self.message = QLabel("Loading data...")
        self.message.setObjectName("busyMessage")
        self.message.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.message.setWordWrap(True)
        
        # Simple CSS-based pulse animation simulation via QProgressBar
        self.progress = QProgressBar()
        self.progress.setRange(0, 0) # Indeterminate
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(4)
        self.progress.setStyleSheet("""
            QProgressBar {
                background: #f0f0f0;
                border: none;
                border-radius: 2px;
            }
            QProgressBar::chunk {
                background: #0078d4;
                border-radius: 2px;
            }
        """)
        
        self.inner_layout.addWidget(self.title)
        self.inner_layout.addWidget(self.progress)
        self.inner_layout.addWidget(self.message)
        
        self.layout.addWidget(self.container)
        self.hide()

    def show_with_message(self, message: str):
        self.message.setText(message)
        self.raise_()
        self.show()


__all__ = ["BusyOverlay"]
