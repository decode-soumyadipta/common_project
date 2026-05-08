import sys
from qtpy.QtWidgets import QApplication
from client_desktop.backend.main_window import MainWindow
from client_desktop.backend.app_mode import DesktopAppMode

def main():
    """Launcher for the Dedicated Ingestion App (Client A)."""
    app = QApplication(sys.argv)
    
    # Initialize in SERVER mode (which we use for the Ingest UI)
    window = MainWindow(app_mode=DesktopAppMode.SERVER)
    window.setWindowTitle("Distributed GIS - Ingestion Control Node")
    window.show()
    
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
