import sys
from qtpy.QtWidgets import QApplication
from client_desktop.backend.main_window import MainWindow
from client_desktop.backend.app_mode import DesktopAppMode

def main():
    """Launcher for the Search & Visualization App (Client B)."""
    app = QApplication(sys.argv)
    
    # Initialize in CLIENT mode (Search, Viz, Analysis)
    window = MainWindow(app_mode=DesktopAppMode.CLIENT)
    window.setWindowTitle("Distributed GIS - Search & Visualization Node")
    window.show()
    
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
