"""Desktop Search Client - Main Entry Point

This module provides the main entry point for the desktop search client application.
It initializes the Qt application and launches the main window with full features
from the original implementation.

Usage:
    python -m src_new.clients.desktop_search.main
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

# CRITICAL: Import QtWebEngineWidgets FIRST before QApplication This is required for proper OpenGL context sharing
from qtpy import QtWebEngineWidgets  # noqa: F401
from qtpy.QtCore import Qt
from qtpy.QtGui import QIcon
from qtpy.QtWidgets import QApplication

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)-8s | %(name)s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

logger = logging.getLogger(__name__)


def global_excepthook(exctype, value, tb):
    """Global exception handler to capture and log uncaught exceptions, and show a dialog."""
    import traceback
    tb_text = "".join(traceback.format_exception(exctype, value, tb))
    logger.critical(f"Uncaught exception: {value}\n{tb_text}")

    # Access current active QApplication
    app = QApplication.instance()
    if app is not None:
        from qtpy.QtCore import QThread
        # Only show GUI popups if we are on the main (GUI) thread
        if QThread.currentThread() == app.thread():
            from qtpy.QtWidgets import QMessageBox
            msg_box = QMessageBox()
            msg_box.setIcon(QMessageBox.Icon.Critical)
            msg_box.setWindowTitle("Application Error")
            msg_box.setText("An unexpected error occurred in the application.")
            msg_box.setInformativeText(str(value))
            msg_box.setDetailedText(tb_text)
            msg_box.exec()
    else:
        # Fallback if Qt app is not yet running
        sys.__excepthook__(exctype, value, tb)


def main() -> int:
    """Main entry point for the desktop search client.
    
    Returns:
        Exit code (0 for success, non-zero for error)
    """
    sys.excepthook = global_excepthook

    try:
        import os
        import platform
        
        # Force discrete GPU on dual-GPU Windows systems
        os.environ["SHIM_MCCOMPAT"] = "1"
        
        flags = [
            "--ignore-gpu-blocklist",
            "--enable-gpu-rasterization",
            "--enable-oop-rasterization",
            "--force-high-performance-gpu",
            "--enable-webgl",
            "--enable-webgl2-compute-context",
            "--enable-accelerated-2d-canvas",
        ]
        
        if platform.system() == "Windows":
            # Direct Chromium to use the high-performance desktop GL driver on Windows (NVIDIA/Quadro nvoglv64.dll)
            flags.append("--use-gl=desktop")
            
        # Set environment variable for QtWebEngine
        existing_flags = os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", "")
        os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = f"{existing_flags} {' '.join(flags)}".strip()
        
        # Also append to sys.argv so QApplication is initialized with these flags
        for f in flags:
            if f not in sys.argv:
                sys.argv.append(f)

        # Set Qt attribute BEFORE creating QApplication
        QApplication.setAttribute(Qt.AA_ShareOpenGLContexts)
        
        # Create Qt application
        app = QApplication(sys.argv)
        app.setApplicationName("resGIS")
        app.setOrganizationName("NTRO, Gov. of India")

        # ── macOS: override the Dock/taskbar name ──────────────────────────
        # By default macOS shows the Python interpreter name ("python3.11").
        # Setting NSBundle's CFBundleName and NSProcessInfo.processName makes
        # the Dock, Force-Quit list, and menu bar show "resGIS" instead.
        if platform.system() == "Darwin":
            try:
                from Foundation import NSBundle, NSProcessInfo  # type: ignore[import]
                bundle_info = NSBundle.mainBundle().infoDictionary()
                if bundle_info is not None:
                    bundle_info["CFBundleName"]       = "resGIS"
                    bundle_info["CFBundleDisplayName"] = "resGIS"
                NSProcessInfo.processInfo().setValue_forKey_("resGIS", "processName")
            except Exception:
                pass  # PyObjC not available — graceful degradation

        # Set application icon (taskbar, window title bar, dock/taskbar icon)
        _logo_path = Path(__file__).resolve().parent.parent.parent / "assets" / "resGIS_logo.png"
        if _logo_path.exists():
            app.setWindowIcon(QIcon(str(_logo_path)))
        
        logger.info("Starting Desktop Search Client...")
        
        # Import after QApplication is created
        from src_new.clients.desktop_search.app_mode import DesktopAppMode
        from src_new.clients.desktop_search.main_window import MainWindow
        
        # Create main window in CLIENT mode (Search, Viz, Analysis)
        window = MainWindow(app_mode=DesktopAppMode.CLIENT)
        window.setWindowTitle("untitled - resGIS (developed by NTRO, Gov. of India)")
        window.show()
        
        logger.info("Desktop Search Client started successfully")
        
        # Run event loop
        return app.exec()
        
    except Exception as e:
        logger.error(f"Failed to start Desktop Search Client: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
