import sys
from PyQt6.QtWidgets import QApplication
from src.ui.main_window import MainWindow
from src.core.config_manager import ConfigManager

def main():
    app = QApplication(sys.argv)
    
    # Initialize Core
    config_manager = ConfigManager()
    
    # Initialize UI
    window = MainWindow(config_manager)
    window.show()
    
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
