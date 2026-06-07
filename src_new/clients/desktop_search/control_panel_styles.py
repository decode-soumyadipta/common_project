from __future__ import annotations

from qtpy.QtGui import QColor
from qtpy.QtWidgets import QGraphicsDropShadowEffect


class ControlPanelStyleMixin:
    def _apply_panel_styles(self) -> None:
        self.setStyleSheet(
            """
            QWidget {
                background: #f5f5f5;
                color: #1a1a1a;
            }
            QToolBox {
                background: transparent;
                color: #1a1a1a;
            }
            QToolBox::tab {
                background: #e8e8e8;
                border: 1px solid #b0b0b0;
                border-radius: 3px;
                padding: 7px 12px;
                margin: 1px 1px;
                font-weight: 700;
                font-size: 12px;
                color: #1a1a1a;
                text-align: center;
            }
            QToolBox::tab:selected {
                background: #ffffff;
                color: #0044aa;
                border: 2px solid #0066cc;
                padding: 6px 11px;
                font-weight: 700;
            }
            QToolBox::tab:hover {
                background: #f5f5f5;
            }
            QFrame#clientCollapseSection {
                background: #ffffff;
                border: 1px solid #d8d8d8;
                border-radius: 4px;
            }
            QFrame#clientCollapseHeader {
                background: #f0f0f0;
                border: none;
                border-bottom: 1px solid #e2e2e2;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
            }
            QFrame#clientCollapseHeader:hover {
                background: #e8e8e8;
            }
            QLabel#clientCollapseTitle {
                color: #1a1a1a;
                font-weight: 700;
                font-size: 13px;
            }
            QLabel#clientCollapseArrow {
                color: #1a1a1a;
            }
            QGroupBox {
                background: #ffffff;
                border: 1px solid #e0e0e0;
                border-radius: 4px;
                margin-top: 10px;
                padding: 8px;
                font-weight: 700;
                font-size: 13px;
                color: #1a1a1a;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 8px;
                padding: 0 4px;
                color: #1a1a1a;
            }
            QFormLayout QLabel {
                font-weight: 600;
                color: #4a4a4a;
            }
            QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QTextEdit {
                background: #ffffff;
                border: 1px solid #d0d0d0;
                border-radius: 2px;
                min-height: 26px;
                padding: 2px 6px;
                font-size: 12px;
                color: #1a1a1a;
            }
            QLineEdit:disabled,
            QComboBox:disabled,
            QSpinBox:disabled,
            QDoubleSpinBox:disabled,
            QTextEdit:disabled {
                background: #efefef;
                color: #8f8f8f;
                border: 1px solid #d1d1d1;
            }
            QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {
                border: 2px solid #0066cc;
            }
            QPushButton {
                background: #eef2f7;
                color: #1a1a1a;
                border: 1px solid #c4ccd6;
                border-radius: 2px;
                padding: 2px 8px;
                font-weight: 600;
                font-size: 11px;
                min-height: 24px;
            }
            QPushButton:hover {
                background: #f7f9fc;
                border: 1px solid #aeb8c5;
            }
            QPushButton:pressed {
                background: #dde3eb;
                border: 1px solid #9ba7b6;
            }
            QPushButton:disabled {
                background: #dfe3e8;
                color: #7b8592;
                border: 1px solid #bcc5cf;
            }
            QPushButton#searchPrimaryButton {
                background: #0b66d6;
                color: #ffffff;
                border: 1px solid #0a57b8;
            }
            QPushButton#searchPrimaryButton:hover {
                background: #0f74ee;
                border: 1px solid #0d63cf;
            }
            QPushButton#searchPrimaryButton:pressed {
                background: #0956b7;
                border: 1px solid #084a9e;
            }
            QPushButton#searchVisibilityToggle {
                background: #eef2f7;
                color: #1a1a1a;
                border: 1px solid #b8c2cf;
                border-radius: 2px;
                padding: 0px;
                min-height: 20px;
                min-width: 24px;
                font-size: 12px;
                font-weight: 700;
            }
            QPushButton#searchVisibilityToggle:hover {
                background: #e2e8f0;
                border: 1px solid #9aa7b8;
            }
            QPushButton#searchVisibilityToggle:pressed {
                background: #d3dbe6;
                border: 1px solid #8895a8;
            }
            QSlider#moduleToggleSlider::groove:horizontal {
                border: 1px solid #c6cdd6;
                height: 8px;
                background: #d8dee6;
                border-radius: 4px;
            }
            QSlider#moduleToggleSlider::sub-page:horizontal {
                background: #0b66d6;
                border: 1px solid #0a57b8;
                border-radius: 4px;
            }
            QSlider#moduleToggleSlider::add-page:horizontal {
                background: #d8dee6;
                border: 1px solid #c6cdd6;
                border-radius: 4px;
            }
            QSlider#moduleToggleSlider::handle:horizontal {
                background: #ffffff;
                border: 1px solid #8d99aa;
                width: 16px;
                margin: -5px 0;
                border-radius: 8px;
            }
            QSlider::groove:horizontal {
                border: 1px solid #d0d0d0;
                height: 6px;
                background: #e8e8e8;
                border-radius: 3px;
            }
            QSlider::sub-page:horizontal {
                background: #0b66d6;
                border: 1px solid #0b66d6;
                border-radius: 3px;
            }
            QSlider::add-page:horizontal {
                background: #e8e8e8;
                border: 1px solid #d0d0d0;
                border-radius: 3px;
            }
            QSlider::handle:horizontal {
                background: #0066cc;
                width: 14px;
                margin: -4px 0;
                border-radius: 7px;
                border: 1px solid #0066cc;
            }
            QSlider::groove:horizontal:disabled {
                background: #ededed;
                border: 1px solid #d7d7d7;
            }
            QSlider::sub-page:horizontal:disabled,
            QSlider::add-page:horizontal:disabled {
                background: #d7d7d7;
                border: 1px solid #cccccc;
            }
            QSlider::handle:horizontal:disabled {
                background: #b9b9b9;
                border: 1px solid #aeaeae;
            }
            QProgressBar {
                border: 1px solid #d0d0d0;
                border-radius: 2px;
                background: #f0f0f0;
                text-align: center;
                font-size: 11px;
            }
            QProgressBar::chunk {
                background: #0066cc;
                border-radius: 3px;
            }
            QLabel {
                color: #1a1a1a;
                font-size: 12px;
            }
            QFormLayout {
                font-size: 12px;
            }
            """
        )

    def _apply_widget_shadows(self) -> None:
        # Apply subtle shadows to buttons for traditional desktop GUI look
        for button in (
            self.browse_files_btn,
            self.clear_selection_btn,
            self.ingest_btn,
            self.assets_refresh_btn,
            self.refresh_assets_btn,
            self.rotate_left_btn,
            self.rotate_right_btn,
        ):
            effect = QGraphicsDropShadowEffect(button)
            effect.setBlurRadius(1.0)
            effect.setOffset(0.0, 0.0)
            effect.setColor(QColor(0, 0, 0, 20))
            button.setGraphicsEffect(effect)
