"""
Personal AI Assistant — Admin Dashboard
PyQt5-based management UI.
"""
import sys
from pathlib import Path

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont, QIcon
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QStatusBar, QTabWidget, QVBoxLayout, QWidget,
)

# Make sure parent dir is on path when run directly
sys.path.insert(0, str(Path(__file__).parent.parent))

from dashboard.tabs.overview import OverviewTab
from dashboard.tabs.usage import UsageTab
from dashboard.tabs.conversations import ConversationsTab
from dashboard.tabs.memory import MemoryTab
from dashboard.tabs.commands import CommandsTab
from dashboard.tabs.settings import SettingsTab
from dashboard.tabs.code_editor import CodeEditorTab
from dashboard.tabs.identity import IdentityTab
from config_manager import get_config


class DashboardWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        cfg = get_config()
        name = cfg.identity.get("assistant_name", "Claw")
        self.setWindowTitle(f"{name} — Admin Dashboard")
        self.resize(1100, 750)
        self.setMinimumSize(800, 600)

        # Central widget
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(8, 8, 8, 4)

        # Tab widget
        tabs = QTabWidget()
        tabs.setDocumentMode(True)
        tabs.addTab(OverviewTab(), "📊 Overview")
        tabs.addTab(IdentityTab(), "💓 Identity")
        tabs.addTab(UsageTab(), "💰 API Usage")
        tabs.addTab(ConversationsTab(), "💬 Conversations")
        tabs.addTab(MemoryTab(), "🧠 Memory & Facts")
        tabs.addTab(CommandsTab(), "⌨ Commands")
        tabs.addTab(SettingsTab(), "⚙ Settings")
        tabs.addTab(CodeEditorTab(), "🖊 Code Editor")
        layout.addWidget(tabs)

        # Status bar
        self._status = QStatusBar()
        self.setStatusBar(self._status)
        self._status.showMessage("Dashboard ready — connecting to local database…")

    def showEvent(self, event) -> None:
        super().showEvent(event)
        cfg = get_config()
        db_path = cfg.get_db_path()
        self._status.showMessage(f"Database: {db_path}")


def main() -> None:
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    # Slightly dark palette for a modern look
    from PyQt5.QtGui import QPalette, QColor
    palette = QPalette()
    palette.setColor(QPalette.Window, QColor(45, 45, 45))
    palette.setColor(QPalette.WindowText, QColor(220, 220, 220))
    palette.setColor(QPalette.Base, QColor(35, 35, 35))
    palette.setColor(QPalette.AlternateBase, QColor(53, 53, 53))
    palette.setColor(QPalette.ToolTipBase, QColor(0, 0, 0))
    palette.setColor(QPalette.ToolTipText, QColor(220, 220, 220))
    palette.setColor(QPalette.Text, QColor(220, 220, 220))
    palette.setColor(QPalette.Button, QColor(53, 53, 53))
    palette.setColor(QPalette.ButtonText, QColor(220, 220, 220))
    palette.setColor(QPalette.BrightText, QColor(255, 80, 80))
    palette.setColor(QPalette.Highlight, QColor(42, 130, 218))
    palette.setColor(QPalette.HighlightedText, QColor(0, 0, 0))
    app.setPalette(palette)

    font = QFont("Segoe UI", 10)
    app.setFont(font)

    window = DashboardWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
