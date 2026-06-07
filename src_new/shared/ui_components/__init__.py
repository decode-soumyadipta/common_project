"""Shared PySide6 UI components for the Offline GIS desktop applications.

All desktop clients (desktop_ingestion, desktop_search) import their
common dialogs from this package rather than duplicating code.

Requirements: 7.6, 12.4

Usage::

    from src_new.shared.ui_components import LoginDialog, SettingsDialog, AboutDialog

    login = LoginDialog(parent=main_window)
    if login.exec() == LoginDialog.DialogCode.Accepted:
        username, password = login.credentials()
"""
from __future__ import annotations

from src_new.shared.ui_components.about_dialog import AboutDialog
from src_new.shared.ui_components.login_dialog import LoginDialog
from src_new.shared.ui_components.settings_dialog import SettingsDialog

__all__ = [
    "LoginDialog",
    "SettingsDialog",
    "AboutDialog",
]
