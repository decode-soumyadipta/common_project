"""Login dialog for the Offline GIS desktop applications.

Provides a PySide6 QDialog for user authentication before accessing
the ingestion or search client. Reads service URLs from the centralized
config so no hardcoded values appear in UI code.

Requirements: 7.6, 12.4
"""
from __future__ import annotations

import logging

from qtpy.QtCore import Qt
from qtpy.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QVBoxLayout,
    QWidget,
)

from src_new.shared.config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Application metadata (read from config; no hardcoded strings)
# ---------------------------------------------------------------------------
_APP_TITLE = "Offline 3D GIS"


class LoginDialog(QDialog):
    """Modal login dialog shown at application startup.

    Collects a username and password from the user. The dialog does not
    perform authentication itself — callers should validate credentials
    against the appropriate service after ``exec()`` returns ``Accepted``.

    Attributes:
        username_edit: QLineEdit for the username field.
        password_edit: QLineEdit for the password field (echo mode: Password).

    Example::

        dialog = LoginDialog(parent=main_window)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            username, password = dialog.credentials()
            # validate against auth service …
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"{_APP_TITLE} — Login")
        self.setModal(True)
        self.setMinimumWidth(360)
        self.setWindowFlags(
            self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint
        )

        self._build_ui()
        logger.debug(
            "LoginDialog initialised; service endpoint: %s",
            settings.ingestion_service_url,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def credentials(self) -> tuple[str, str]:
        """Return the entered (username, password) tuple.

        Returns:
            A 2-tuple of (username, password) strings. Both may be empty
            if the user has not typed anything.
        """
        return (
            self.username_edit.text().strip(),
            self.password_edit.text(),
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        """Construct and lay out all child widgets."""
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(24, 24, 24, 16)
        root_layout.setSpacing(16)

        # ── Header ────────────────────────────────────────────────────
        header = QLabel(f"<b>{_APP_TITLE}</b>")
        header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header.setStyleSheet("font-size: 18px; color: #1a2a3a;")
        root_layout.addWidget(header)

        subtitle = QLabel("Sign in to continue")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setStyleSheet("font-size: 12px; color: #6b7a8d;")
        root_layout.addWidget(subtitle)

        # ── Form ──────────────────────────────────────────────────────
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setSpacing(10)

        self.username_edit = QLineEdit()
        self.username_edit.setPlaceholderText("Enter your username")
        self.username_edit.setMinimumHeight(32)
        form.addRow("Username:", self.username_edit)

        self.password_edit = QLineEdit()
        self.password_edit.setPlaceholderText("Enter your password")
        self.password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_edit.setMinimumHeight(32)
        form.addRow("Password:", self.password_edit)

        root_layout.addLayout(form)

        # ── Service info (read from config — no hardcoded URL) ────────
        service_label = QLabel(
            f"<small>Service: {settings.ingestion_service_url}</small>"
        )
        service_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        service_label.setStyleSheet("color: #9aa5b4;")
        root_layout.addWidget(service_label)

        # ── Buttons ───────────────────────────────────────────────────
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        root_layout.addWidget(buttons)

        # Allow pressing Enter in the password field to submit
        self.password_edit.returnPressed.connect(self._on_accept)

    def _on_accept(self) -> None:
        """Validate that username is non-empty before accepting."""
        username, _ = self.credentials()
        if not username:
            self.username_edit.setFocus()
            self.username_edit.setStyleSheet("border: 1px solid #e53e3e;")
            return
        self.username_edit.setStyleSheet("")
        logger.info("Login attempted for user: %s", username)
        self.accept()


__all__ = ["LoginDialog"]
