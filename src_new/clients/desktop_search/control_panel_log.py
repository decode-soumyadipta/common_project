from __future__ import annotations

from qtpy.QtCore import Qt, QTimer
from qtpy.QtWidgets import QApplication, QListWidgetItem, QProgressDialog, QWidget


class ControlPanelLogMixin:
    def log(self, message: str) -> None:
        """Append a message to the Activity Log in a compact, readable format."""
        import html as _html
        from datetime import datetime as _dt
        ts = _dt.now().strftime("%H:%M:%S")
        msg_lower = message.lower()
        safe_msg = _html.escape(message)
        if "error" in msg_lower or "failed" in msg_lower or "exception" in msg_lower:
            accent = "#cc2936"
            badge = "ERROR"
            message_color = "#5f2124"
            background = "#fff5f5"
        elif "warn" in msg_lower:
            accent = "#b47d00"
            badge = "WARN"
            message_color = "#5c4a15"
            background = "#fffaf0"
        else:
            accent = "#6b7280"
            badge = "INFO"
            message_color = "#1f2937"
            background = "#f8fafc"
        line = (
            f'<div style="margin:0 0 4px 0;padding:4px 8px;border-left:3px solid {accent};'
            f'background:{background};border-radius:4px;line-height:1.35;">'
            f'<span style="color:#6b7280">[{ts}]</span> '
            f'<span style="color:{accent};font-weight:600;">{badge}</span> '
            f'<span style="color:{message_color}">{safe_msg}</span>'
            f'</div>'
        )
        self.status_box.append(line)
        # Auto-scroll to bottom
        sb = self.status_box.verticalScrollBar()
        sb.setValue(sb.maximum())

    def add_measurement_result_entry(self, message: str) -> None:
        item = QListWidgetItem(message)
        self.measurement_results_list.addItem(item)
        self.measurement_results_list.setCurrentItem(item)
        self.measurement_results_list.scrollToItem(item)

    def selected_measurement_result_row(self) -> int:
        return int(self.measurement_results_list.currentRow())

    def remove_measurement_result_row(self, row: int) -> None:
        if 0 <= row < self.measurement_results_list.count():
            self.measurement_results_list.takeItem(row)

    def clear_measurement_result_entries(self) -> None:
        self.measurement_results_list.clear()

    def set_search_busy(
        self, active: bool, message: str = "Searching...", progress: int | None = None
    ) -> None:
        if active:
            if self._search_busy_dialog is None:
                import time

                parent_widget = (
                    self.window() if isinstance(self.window(), QWidget) else self
                )
                dialog = QProgressDialog(message, "", 0, 100, parent_widget)
                dialog.setWindowTitle("Please wait")
                dialog.setCancelButton(None)
                dialog.setMinimumDuration(0)
                dialog.setAutoClose(False)
                dialog.setAutoReset(False)
                dialog.setWindowModality(Qt.WindowModality.ApplicationModal)
                dialog.setWindowFlag(Qt.WindowType.WindowCloseButtonHint, False)
                dialog.setWindowFlag(Qt.WindowType.WindowContextHelpButtonHint, False)
                dialog.setStyleSheet(
                    """
                    QProgressDialog {
                        background: #ffffff;
                        border: 1px solid #d0d0d0;
                        border-radius: 6px;
                    }
                    QProgressDialog QLabel {
                        color: #1a1a1a;
                        font-weight: 600;
                        font-size: 13px;
                    }
                    """
                )
                self._search_busy_dialog = dialog
                self._search_busy_start_time = time.time()
                self._search_busy_value = 5
                if self._search_busy_timer is None:
                    self._search_busy_timer = QTimer(self)
                    self._search_busy_timer.timeout.connect(
                        self._update_search_busy_timer
                    )
                self._search_busy_timer.start(100)

            dialog = self._search_busy_dialog
            if dialog is None:
                return
            self._search_busy_message = str(message or "Searching...")
            if progress is not None:
                self._search_busy_value = max(1, min(100, int(progress)))
            elif self._search_busy_value <= 0:
                self._search_busy_value = 5
            dialog.setValue(self._search_busy_value)
            if self._search_busy_start_time is not None:
                import time

                elapsed = time.time() - self._search_busy_start_time
                dialog.setLabelText(f"{self._search_busy_message} {elapsed:.1f}s")
            else:
                dialog.setLabelText(self._search_busy_message)
            dialog.show()
            self._center_search_busy_dialog()
            QApplication.processEvents()
            return

        if self._search_busy_dialog is not None:
            if self._search_busy_timer is not None:
                self._search_busy_timer.stop()
            self._search_busy_dialog.setValue(100)
            self._search_busy_dialog.hide()
            self._search_busy_dialog.reset()
            self._search_busy_start_time = None
            self._search_busy_message = "Searching..."
            self._search_busy_value = 0
            QApplication.processEvents()

    def _update_search_busy_timer(self) -> None:
        if self._search_busy_dialog is None or self._search_busy_start_time is None:
            return
        import time

        elapsed = time.time() - self._search_busy_start_time
        # Keep a visibly moving bar while backend search is running.
        self._search_busy_value = min(94, max(self._search_busy_value + 1, 5))
        self._search_busy_dialog.setValue(self._search_busy_value)
        self._search_busy_dialog.setLabelText(
            f"{self._search_busy_message} {elapsed:.1f}s"
        )

    def _center_search_busy_dialog(self) -> None:
        if self._search_busy_dialog is None:
            return
        parent_widget = self.window() if isinstance(self.window(), QWidget) else self
        if parent_widget is None:
            return
        parent_rect = parent_widget.frameGeometry()
        dialog_rect = self._search_busy_dialog.frameGeometry()
        target_x = parent_rect.center().x() - dialog_rect.width() // 2
        target_y = parent_rect.center().y() - dialog_rect.height() // 2
        self._search_busy_dialog.move(max(0, target_x), max(0, target_y))
