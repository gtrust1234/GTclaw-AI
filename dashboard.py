"""
GTclaw Dashboard — Real-time monitoring and control panel for the Personal AI Assistant.
Run:   python dashboard.py
Build: .\build_dashboard.ps1
"""
import sys
import os
import subprocess
from pathlib import Path
from datetime import datetime, timedelta

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTabWidget, QLabel, QPushButton, QTableWidget, QTableWidgetItem,
    QHeaderView, QFrame, QSplitter, QGroupBox, QScrollArea,
    QFormLayout, QLineEdit, QSpinBox, QDoubleSpinBox, QCheckBox,
    QComboBox, QTextEdit, QMessageBox, QSizePolicy,
    QDialog, QDialogButtonBox, QTextBrowser, QProgressBar,
)
from PyQt5.QtCore import Qt, QTimer, QThread, pyqtSignal
from PyQt5.QtGui import QFont, QColor, QIcon

# ── Add project root so we can import project modules ─────────────────────────
# When frozen by PyInstaller, __file__ is in a temp dir — use the EXE's directory.
_HERE = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).parent
sys.path.insert(0, str(_HERE))
from database import Database
from config_manager import ConfigManager

# ── Colour palette (GitHub-dark inspired) ─────────────────────────────────────
BG      = "#0d1117"
CARD    = "#161b22"
BORDER  = "#30363d"
GREEN   = "#3fb950"
RED     = "#f85149"
YELLOW  = "#d29922"
BLUE    = "#58a6ff"
TEXT    = "#e6edf3"
MUTED   = "#8b949e"
ACCENT  = "#1f6feb"

STYLESHEET = f"""
QMainWindow, QWidget {{
    background-color: {BG};
    color: {TEXT};
    font-family: 'Segoe UI', Arial, sans-serif;
    font-size: 13px;
}}
QTabWidget::pane {{
    border: 1px solid {BORDER};
    background-color: {CARD};
}}
QTabBar::tab {{
    background-color: {BG};
    color: {MUTED};
    padding: 8px 22px;
    border: none;
    border-bottom: 2px solid transparent;
    font-size: 13px;
}}
QTabBar::tab:selected {{
    color: {TEXT};
    border-bottom: 2px solid {BLUE};
    background-color: {CARD};
}}
QTabBar::tab:hover {{
    color: {TEXT};
    background-color: {CARD};
}}
QPushButton {{
    background-color: {ACCENT};
    color: white;
    border: none;
    border-radius: 6px;
    padding: 6px 14px;
    font-size: 13px;
    font-weight: 600;
}}
QPushButton:hover  {{ background-color: #388bfd; }}
QPushButton:pressed {{ background-color: #1158c7; }}
QPushButton:disabled {{ background-color: #21262d; color: {MUTED}; }}
QPushButton[danger="true"]         {{ background-color: #b62324; }}
QPushButton[danger="true"]:hover   {{ background-color: {RED}; }}
QPushButton[success="true"]        {{ background-color: #238636; }}
QPushButton[success="true"]:hover  {{ background-color: {GREEN}; }}
QTableWidget {{
    background-color: {CARD};
    color: {TEXT};
    gridline-color: {BORDER};
    border: 1px solid {BORDER};
    border-radius: 6px;
    selection-background-color: {ACCENT};
    alternate-background-color: #1c2128;
}}
QTableWidget::item {{ padding: 5px 8px; border: none; }}
QHeaderView::section {{
    background-color: {BG};
    color: {MUTED};
    padding: 8px;
    border: none;
    border-bottom: 1px solid {BORDER};
    font-weight: 600;
    font-size: 11px;
    text-transform: uppercase;
}}
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QTextEdit {{
    background-color: {BG};
    color: {TEXT};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 6px 10px;
}}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{
    border: 1px solid {BLUE};
}}
QComboBox QAbstractItemView {{
    background-color: {CARD};
    color: {TEXT};
    selection-background-color: {ACCENT};
    border: 1px solid {BORDER};
}}
QScrollBar:vertical {{
    background: {BG}; width: 8px;
}}
QScrollBar::handle:vertical {{
    background: {BORDER}; border-radius: 4px; min-height: 20px;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QGroupBox {{
    border: 1px solid {BORDER};
    border-radius: 8px;
    margin-top: 14px;
    padding-top: 6px;
    color: {MUTED};
    font-size: 11px;
    font-weight: 600;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 6px;
}}
QCheckBox {{ color: {TEXT}; spacing: 8px; }}
QCheckBox::indicator {{
    width: 16px; height: 16px;
    border: 1px solid {BORDER};
    border-radius: 3px;
    background-color: {BG};
}}
QCheckBox::indicator:checked {{
    background-color: {ACCENT};
    border-color: {ACCENT};
}}
QMessageBox {{ background-color: {CARD}; color: {TEXT}; }}
QMessageBox QPushButton {{ min-width: 70px; }}
QScrollArea {{ border: none; }}
"""


# ── Helpers ───────────────────────────────────────────────────────────────────

def get_bot_pid() -> int | None:
    """Return PID of the running bot service (GTclawService.exe or service.py), or None."""
    try:
        # Check for installed EXE first
        result = subprocess.run(
            ["wmic", "process", "where", "name='GTclawService.exe'",
             "get", "ProcessId", "/FORMAT:CSV"],
            capture_output=True, text=True, timeout=5,
            creationflags=0x08000000,
        )
        for line in result.stdout.splitlines():
            line = line.strip()
            if line and not line.startswith("Node"):
                parts = [p.strip() for p in line.split(",")]
                try:
                    pid = int(parts[-1])
                    if pid > 0:
                        return pid
                except ValueError:
                    pass
        # Fall back to python.exe running service.py (dev mode)
        result = subprocess.run(
            ["wmic", "process", "where", "name='python.exe'",
             "get", "ProcessId,CommandLine", "/FORMAT:CSV"],
            capture_output=True, text=True, timeout=5,
            creationflags=0x08000000,
        )
        for line in result.stdout.splitlines():
            if ("service.py" in line or "bot.py" in line) and "dashboard" not in line:
                parts = [p.strip() for p in line.split(",")]
                try:
                    return int(parts[-1])
                except ValueError:
                    pass
    except Exception:
        pass
    return None


def fmt_cost(usd: float) -> str:
    if usd == 0:
        return "$0.00"
    if usd < 0.01:
        return f"${usd * 100:.3f}¢"
    return f"${usd:.4f}"


def fmt_dt(iso: str) -> str:
    if not iso:
        return ""
    try:
        dt = datetime.fromisoformat(iso[:19])
        now = datetime.now()
        if dt.date() == now.date():
            return f"Today {dt.strftime('%H:%M')}"
        if dt.date() == (now - timedelta(days=1)).date():
            return f"Yesterday {dt.strftime('%H:%M')}"
        return dt.strftime("%d %b %H:%M")
    except Exception:
        return iso[:16]


# ── Stat card ─────────────────────────────────────────────────────────────────

class StatCard(QFrame):
    def __init__(self, title: str, value: str = "—", color: str = TEXT, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"""
            QFrame {{
                background-color: {CARD};
                border: 1px solid {BORDER};
                border-radius: 10px;
            }}
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 14, 18, 14)
        layout.setSpacing(6)

        self._title_lbl = QLabel(title.upper())
        self._title_lbl.setStyleSheet(
            f"color:{MUTED}; font-size:11px; font-weight:600;"
            "border:none; background:transparent;"
        )
        self._value_lbl = QLabel(value)
        self._value_lbl.setStyleSheet(
            f"color:{color}; font-size:24px; font-weight:700;"
            "border:none; background:transparent;"
        )
        layout.addWidget(self._title_lbl)
        layout.addWidget(self._value_lbl)

    def set_value(self, value: str, color: str = TEXT):
        self._value_lbl.setText(value)
        self._value_lbl.setStyleSheet(
            f"color:{color}; font-size:24px; font-weight:700;"
            "border:none; background:transparent;"
        )


# ── Background chat worker ────────────────────────────────────────────────────

class _ChatWorker(QThread):
    """Calls ClaudeClient.chat() in a background thread so the UI stays responsive."""
    response_ready = pyqtSignal(str)
    error_occurred = pyqtSignal(str)

    def __init__(self, message: str, history: list, use_smart: bool = False):
        super().__init__()
        self._message   = message
        self._history   = list(history)
        self._use_smart = use_smart

    def run(self):
        import asyncio, json
        try:
            from claude_client import ClaudeClient
            from memory import MemoryManager
            from config_manager import ConfigManager

            cfg = ConfigManager()
            mem = MemoryManager()
            client = ClaudeClient()

            # Inject memories — same as the Telegram bot does
            memories = mem.get_all_memories()
            memory_context = ""
            if memories:
                memory_context = "Facts about the user:\n" + "\n".join(
                    f"- {m['content']}" for m in memories
                )

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            result = loop.run_until_complete(
                client.chat(
                    self._message,
                    self._history,
                    memory_context=memory_context,
                    use_smart=self._use_smart,
                    session_id="dashboard",
                )
            )

            # Persist both turns to conversation history
            mem.add_to_history("user",      self._message, session_id="dashboard")
            mem.add_to_history("assistant", result,        session_id="dashboard")

            # Auto memory extraction (mirrors bot.py behaviour)
            if cfg.settings.get("auto_memory_extraction", True):
                try:
                    prompt = (
                        "Review this conversation exchange and extract ANYTHING worth saving long-term.\n"
                        "This includes facts about the user, preferences, instructions, or important context.\n"
                        "Return ONLY a JSON array of short factual strings, or [] if nothing is worth saving.\n\n"
                        f"User: {self._message}\n"
                        f"Assistant: {result}\n\n"
                        "JSON array:"
                    )
                    raw = loop.run_until_complete(client.quick_extract(prompt))
                    facts = json.loads(raw)
                    for fact in facts:
                        if isinstance(fact, str) and fact.strip():
                            mem.add_memory(fact.strip())
                except Exception:
                    pass

            loop.close()
            self.response_ready.emit(result)
        except Exception as exc:
            self.error_occurred.emit(str(exc))


# ── Telegram Setup Wizard ─────────────────────────────────────────────────────

class TelegramSetupDialog(QDialog):
    """Step-by-step guide to create a Telegram bot and configure it."""

    def __init__(self, cfg, parent=None):
        super().__init__(parent)
        self._cfg = cfg
        self.setWindowTitle("Telegram Bot Setup")
        self.setMinimumSize(560, 480)
        self.setStyleSheet(parent.styleSheet() if parent else "")

        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 20, 24, 20)
        lay.setSpacing(14)

        title = QLabel("🤖  Telegram Bot Setup Wizard")
        title.setStyleSheet(f"font-size:16px; font-weight:700; color:{TEXT};")
        lay.addWidget(title)

        steps_html = f"""
<html><body style="font-family:'Segoe UI',Arial; font-size:13px; color:{TEXT}; background:transparent;">
<b style="color:{BLUE};">Step 1 — Create your bot</b><br>
Open Telegram and message <a href="https://t.me/BotFather" style="color:{BLUE};">@BotFather</a><br>
Send: <code style="color:{GREEN};">/newbot</code> &nbsp;→ follow the prompts → copy the token it gives you.<br><br>
<b style="color:{BLUE};">Step 2 — Paste your token below</b><br><br>
<b style="color:{BLUE};">Step 3 — Find your Telegram user ID</b><br>
Message <a href="https://t.me/userinfobot" style="color:{BLUE};">@userinfobot</a> on Telegram — it will reply with your numeric user ID.<br>
Paste it in the field below.<br><br>
<b style="color:{BLUE};">Step 4 — Save &amp; test</b><br>
Click <b>Save &amp; Test</b>. The bot will send you a test message via Telegram to confirm everything works.
</body></html>"""

        instructions = QTextBrowser()
        instructions.setHtml(steps_html)
        instructions.setOpenExternalLinks(True)
        instructions.setMaximumHeight(200)
        instructions.setStyleSheet(
            f"background:{CARD}; border:1px solid {BORDER}; border-radius:6px; padding:8px;"
        )
        lay.addWidget(instructions)

        form = QFormLayout()
        form.setSpacing(10)

        self._token_edit = QLineEdit()
        self._token_edit.setEchoMode(QLineEdit.Password)
        self._token_edit.setPlaceholderText("1234567890:AAHdqTcvCH1vGWJxfSeofSAs0K5PALDsaw")
        self._token_edit.setText(cfg.config.get("telegram_token", ""))

        self._uid_edit = QLineEdit()
        self._uid_edit.setPlaceholderText("123456789")
        uid = cfg.config.get("telegram_user_id", 0)
        if uid:
            self._uid_edit.setText(str(uid))

        form.addRow("Bot Token:", self._token_edit)
        form.addRow("Your User ID:", self._uid_edit)
        lay.addLayout(form)

        self._status_lbl = QLabel("")
        self._status_lbl.setWordWrap(True)
        self._status_lbl.setStyleSheet(f"color:{MUTED}; font-size:12px;")
        lay.addWidget(self._status_lbl)

        btns = QDialogButtonBox()
        self._test_btn = btns.addButton("Save && Test", QDialogButtonBox.AcceptRole)
        self._skip_btn = btns.addButton("Save Only",    QDialogButtonBox.ApplyRole)
        btns.addButton("Cancel", QDialogButtonBox.RejectRole)
        btns.accepted.connect(self._save_and_test)
        btns.button(QDialogButtonBox.Apply) if False else None
        # wire Apply
        self._skip_btn.clicked.connect(self._save_only)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)

    def _get_values(self):
        token = self._token_edit.text().strip()
        try:
            uid = int(self._uid_edit.text().strip())
        except ValueError:
            uid = 0
        return token, uid

    def _save_only(self):
        token, uid = self._get_values()
        if not token:
            self._status_lbl.setStyleSheet(f"color:{RED};")
            self._status_lbl.setText("Please enter a bot token.")
            return
        self._cfg.config["telegram_token"] = token
        self._cfg.config["telegram_user_id"] = uid
        self._cfg.save_config()
        self._status_lbl.setStyleSheet(f"color:{GREEN};")
        self._status_lbl.setText("✅ Saved!")

    def _save_and_test(self):
        token, uid = self._get_values()
        if not token:
            self._status_lbl.setStyleSheet(f"color:{RED};")
            self._status_lbl.setText("Please enter a bot token.")
            return
        self._cfg.config["telegram_token"] = token
        self._cfg.config["telegram_user_id"] = uid
        self._cfg.save_config()
        self._status_lbl.setStyleSheet(f"color:{MUTED};")
        self._status_lbl.setText("Testing connection…")
        QTimer.singleShot(100, self._do_test)

    def _do_test(self):
        import urllib.request, json as _json
        token, uid = self._get_values()
        try:
            url = f"https://api.telegram.org/bot{token}/sendMessage"
            payload = _json.dumps({"chat_id": uid, "text": "✅ GTclaw bot connected successfully!"}).encode()
            req = urllib.request.Request(url, data=payload,
                                         headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=8) as resp:
                result = _json.loads(resp.read())
            if result.get("ok"):
                self._status_lbl.setStyleSheet(f"color:{GREEN};")
                self._status_lbl.setText("✅ Test message sent! Check your Telegram.")
            else:
                self._status_lbl.setStyleSheet(f"color:{RED};")
                self._status_lbl.setText(f"⚠️ Telegram error: {result.get('description', 'unknown')}")
        except Exception as exc:
            self._status_lbl.setStyleSheet(f"color:{RED};")
            self._status_lbl.setText(f"⚠️ Connection failed: {str(exc)[:120]}")


# ── Main window ───────────────────────────────────────────────────────────────

class Dashboard(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("GTclaw Dashboard")
        self.resize(1280, 820)
        self.setMinimumSize(900, 600)

        self._cfg = ConfigManager()
        self._db  = Database(self._cfg.get_db_path())
        self._cmd_rows_data: list[dict] = []
        self._settings_loaded = False
        self._chat_history: list[dict] = []   # in-memory conversation for the Chat tab
        self._chat_worker: _ChatWorker | None = None

        self._setup_ui()
        self.setStyleSheet(STYLESHEET)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._refresh_all)
        self._timer.start(5000)
        self._refresh_all()

    # ─────────────────────────────────────────────────────────────────────────
    # UI construction
    # ─────────────────────────────────────────────────────────────────────────

    def _setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_header())

        self._tabs = QTabWidget()
        self._tabs.setDocumentMode(True)
        root.addWidget(self._tabs)

        self._build_overview_tab()
        self._build_chat_tab()
        self._build_usage_tab()
        self._build_tasks_tab()
        self._build_farm_tab()
        self._build_reminders_tab()
        self._build_memories_tab()
        self._build_commands_tab()
        self._build_conversations_tab()
        self._build_settings_tab()

    def _build_header(self) -> QFrame:
        bar = QFrame()
        bar.setFixedHeight(58)
        bar.setStyleSheet(f"background-color:{CARD}; border-bottom:1px solid {BORDER};")
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(20, 0, 20, 0)

        title = QLabel("⚡  GTclaw Dashboard")
        title.setStyleSheet(
            f"color:{TEXT}; font-size:16px; font-weight:700;"
            "background:transparent; border:none;"
        )
        lay.addWidget(title)
        lay.addStretch()

        self._status_dot   = QLabel("●")
        self._status_label = QLabel("Checking…")
        for w in (self._status_dot, self._status_label):
            w.setStyleSheet(f"color:{MUTED}; font-size:13px; background:transparent; border:none;")
        lay.addWidget(self._status_dot)
        lay.addWidget(self._status_label)
        lay.addSpacing(24)

        self._btn_start   = QPushButton("▶  Start")
        self._btn_start.setProperty("success", "true")
        self._btn_stop    = QPushButton("■  Stop")
        self._btn_stop.setProperty("danger", "true")
        self._btn_restart = QPushButton("↺  Restart")
        self._btn_refresh = QPushButton("⟳")
        self._btn_refresh.setFixedSize(34, 34)
        self._btn_refresh.setToolTip("Refresh now")

        for btn in (self._btn_start, self._btn_stop, self._btn_restart):
            btn.setFixedHeight(34)
            lay.addWidget(btn)
            lay.addSpacing(6)
        lay.addWidget(self._btn_refresh)

        self._btn_start.clicked.connect(self._start_bot)
        self._btn_stop.clicked.connect(self._stop_bot)
        self._btn_restart.clicked.connect(self._restart_bot)
        self._btn_refresh.clicked.connect(self._refresh_all)

        lay.addSpacing(16)
        self._refresh_label = QLabel("")
        self._refresh_label.setStyleSheet(
            f"color:{MUTED}; font-size:11px; background:transparent; border:none;"
        )
        lay.addWidget(self._refresh_label)

        return bar

    # ── Overview ──────────────────────────────────────────────────────────────

    def _build_overview_tab(self):
        tab = QWidget()
        lay = QVBoxLayout(tab)
        lay.setContentsMargins(20, 20, 20, 20)
        lay.setSpacing(16)

        cards = QHBoxLayout()
        cards.setSpacing(12)
        self._ov_messages  = StatCard("Messages Today",    "—", BLUE)
        self._ov_cost_day  = StatCard("API Cost Today",    "—", GREEN)
        self._ov_tasks     = StatCard("Pending Tasks",     "—", YELLOW)
        self._ov_reminders = StatCard("Pending Reminders", "—", TEXT)
        self._ov_memories  = StatCard("Memories",          "—", TEXT)
        self._ov_searches  = StatCard("Searches Today",    "—", BLUE)
        self._ov_farm      = StatCard("Farm Records",      "—", TEXT)
        for c in (self._ov_messages, self._ov_cost_day, self._ov_tasks,
                  self._ov_reminders, self._ov_memories, self._ov_searches, self._ov_farm):
            cards.addWidget(c)
        lay.addLayout(cards)

        grp = QGroupBox("Recent Activity")
        g = QVBoxLayout(grp)
        g.setContentsMargins(12, 16, 12, 12)
        self._ov_table = self._make_table(["Time", "Type", "Details"])
        self._ov_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        g.addWidget(self._ov_table)
        lay.addWidget(grp)

        self._tabs.addTab(tab, "Overview")

    # ── Chat ──────────────────────────────────────────────────────────────────

    def _build_chat_tab(self):
        tab = QWidget()
        lay = QVBoxLayout(tab)
        lay.setContentsMargins(20, 16, 20, 16)
        lay.setSpacing(10)

        # Chat history display
        self._chat_display = QTextBrowser()
        self._chat_display.setOpenExternalLinks(True)
        self._chat_display.setFont(QFont("Segoe UI", 12))
        self._chat_display.setStyleSheet(
            f"background:{CARD}; color:{TEXT}; border:1px solid {BORDER};"
            "border-radius:8px; padding:12px;"
        )
        lay.addWidget(self._chat_display, stretch=1)

        # Thinking indicator
        self._chat_thinking = QLabel("⏳  Thinking…")
        self._chat_thinking.setStyleSheet(f"color:{MUTED}; font-size:12px;")
        self._chat_thinking.setVisible(False)
        lay.addWidget(self._chat_thinking)

        # Input row
        input_row = QHBoxLayout()
        input_row.setSpacing(8)

        self._chat_input = QLineEdit()
        self._chat_input.setPlaceholderText("Type a message and press Enter…")
        self._chat_input.setFixedHeight(38)
        self._chat_input.returnPressed.connect(self._chat_send)

        self._chat_smart_cb = QCheckBox("Smart")
        self._chat_smart_cb.setToolTip("Use the smarter (Sonnet) model instead of Haiku")
        self._chat_smart_cb.setStyleSheet(f"color:{MUTED}; font-size:12px;")

        btn_send = QPushButton("Send ↵")
        btn_send.setFixedHeight(38)
        btn_send.setFixedWidth(90)
        btn_send.clicked.connect(self._chat_send)

        btn_clear = QPushButton("Clear")
        btn_clear.setFixedHeight(38)
        btn_clear.setFixedWidth(70)
        btn_clear.setStyleSheet(
            f"background:{CARD}; color:{MUTED}; border:1px solid {BORDER}; border-radius:6px;"
        )
        btn_clear.clicked.connect(self._chat_clear)

        input_row.addWidget(self._chat_input, stretch=1)
        input_row.addWidget(self._chat_smart_cb)
        input_row.addWidget(btn_send)
        input_row.addWidget(btn_clear)
        lay.addLayout(input_row)

        hint = QLabel(
            "Chat directly with the AI · Replies use the same Claude tools as Telegram · "
            "History is per-session only"
        )
        hint.setStyleSheet(f"color:{MUTED}; font-size:11px;")
        lay.addWidget(hint)

        self._tabs.addTab(tab, "💬 Chat")

    def _build_usage_tab(self):
        tab = QWidget()
        lay = QVBoxLayout(tab)
        lay.setContentsMargins(20, 20, 20, 20)
        lay.setSpacing(16)

        cards = QHBoxLayout()
        cards.setSpacing(12)
        self._u_today  = StatCard("Cost Today",      "—", GREEN)
        self._u_week   = StatCard("Cost This Week",  "—", YELLOW)
        self._u_month  = StatCard("Cost This Month", "—", YELLOW)
        self._u_total  = StatCard("Total Cost",      "—", RED)
        self._u_calls  = StatCard("Total API Calls", "—", BLUE)
        for c in (self._u_today, self._u_week, self._u_month, self._u_total, self._u_calls):
            cards.addWidget(c)
        lay.addLayout(cards)

        grp = QGroupBox("API Call Log (last 100)")
        g = QVBoxLayout(grp)
        g.setContentsMargins(12, 16, 12, 12)
        self._usage_table = self._make_table(
            ["Time", "Model", "Purpose", "In Tokens", "Out Tokens", "Cost", "Response ms"]
        )
        self._usage_table.setColumnWidth(0, 140)
        self._usage_table.setColumnWidth(2, 90)
        self._usage_table.setColumnWidth(3, 90)
        self._usage_table.setColumnWidth(4, 90)
        self._usage_table.setColumnWidth(5, 90)
        self._usage_table.setColumnWidth(6, 100)
        self._usage_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        g.addWidget(self._usage_table)
        lay.addWidget(grp)

        grp2 = QGroupBox("Breakdown by Purpose / Model")
        g2 = QVBoxLayout(grp2)
        g2.setContentsMargins(12, 16, 12, 12)
        self._usage_breakdown_table = self._make_table(
            ["Purpose / Model", "Calls", "Total Tokens", "Cost"]
        )
        self._usage_breakdown_table.setMaximumHeight(180)
        self._usage_breakdown_table.setColumnWidth(1, 70)
        self._usage_breakdown_table.setColumnWidth(2, 110)
        self._usage_breakdown_table.setColumnWidth(3, 90)
        self._usage_breakdown_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        g2.addWidget(self._usage_breakdown_table)
        lay.addWidget(grp2)

        self._tabs.addTab(tab, "API Usage")

    # ── Reminders ─────────────────────────────────────────────────────────────

    def _build_reminders_tab(self):
        tab = QWidget()
        lay = QVBoxLayout(tab)
        lay.setContentsMargins(20, 20, 20, 20)
        lay.setSpacing(12)

        btn_row = QHBoxLayout()
        btn_del = QPushButton("🗑  Delete Selected")
        btn_del.setProperty("danger", "true")
        btn_del.clicked.connect(self._delete_reminder)
        btn_row.addWidget(btn_del)
        btn_row.addStretch()
        lay.addLayout(btn_row)

        self._rem_table = self._make_table(["ID", "Fire At", "Recurring", "Message", "Status"])
        self._rem_table.setColumnWidth(0, 50)
        self._rem_table.setColumnWidth(1, 150)
        self._rem_table.setColumnWidth(2, 100)
        self._rem_table.setColumnWidth(4, 100)
        self._rem_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        lay.addWidget(self._rem_table)

        self._tabs.addTab(tab, "Reminders")

    # ── Memories ──────────────────────────────────────────────────────────────

    def _build_memories_tab(self):
        tab = QWidget()
        lay = QVBoxLayout(tab)
        lay.setContentsMargins(20, 20, 20, 20)
        lay.setSpacing(0)

        splitter = QSplitter(Qt.Vertical)

        # Memories
        mem_w = QWidget()
        mem_l = QVBoxLayout(mem_w)
        mem_l.setContentsMargins(0, 0, 0, 8)
        grp_m = QGroupBox("Memories")
        gm = QVBoxLayout(grp_m)
        gm.setContentsMargins(12, 16, 12, 12)
        brow = QHBoxLayout()
        b = QPushButton("🗑  Delete Selected Memory")
        b.setProperty("danger", "true")
        b.clicked.connect(self._delete_memory)
        brow.addWidget(b)
        brow.addStretch()
        gm.addLayout(brow)
        self._mem_table = self._make_table(["ID", "Category", "Content", "Created"])
        self._mem_table.setColumnWidth(0, 50)
        self._mem_table.setColumnWidth(1, 100)
        self._mem_table.setColumnWidth(3, 140)
        self._mem_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        gm.addWidget(self._mem_table)
        mem_l.addWidget(grp_m)

        # Facts
        fct_w = QWidget()
        fct_l = QVBoxLayout(fct_w)
        fct_l.setContentsMargins(0, 0, 0, 0)
        grp_f = QGroupBox("User Facts")
        gf = QVBoxLayout(grp_f)
        gf.setContentsMargins(12, 16, 12, 12)
        brow2 = QHBoxLayout()
        b2 = QPushButton("🗑  Delete Selected Fact")
        b2.setProperty("danger", "true")
        b2.clicked.connect(self._delete_fact)
        brow2.addWidget(b2)
        brow2.addStretch()
        gf.addLayout(brow2)
        self._facts_table = self._make_table(["ID", "Key", "Value", "Source", "Updated"])
        self._facts_table.setColumnWidth(0, 50)
        self._facts_table.setColumnWidth(1, 150)
        self._facts_table.setColumnWidth(3, 80)
        self._facts_table.setColumnWidth(4, 140)
        self._facts_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        gf.addWidget(self._facts_table)
        fct_l.addWidget(grp_f)

        splitter.addWidget(mem_w)
        splitter.addWidget(fct_w)
        splitter.setSizes([450, 300])
        lay.addWidget(splitter)

        self._tabs.addTab(tab, "Memories")

    # ── Commands ──────────────────────────────────────────────────────────────

    def _build_commands_tab(self):
        tab = QWidget()
        lay = QVBoxLayout(tab)
        lay.setContentsMargins(20, 20, 20, 20)
        lay.setSpacing(0)

        splitter = QSplitter(Qt.Vertical)

        tbl_w = QWidget()
        tbl_l = QVBoxLayout(tbl_w)
        tbl_l.setContentsMargins(0, 0, 0, 8)
        self._cmd_table = self._make_table(
            ["Time", "Shell", "Exit", "Duration", "By", "Command"]
        )
        self._cmd_table.setColumnWidth(0, 140)
        self._cmd_table.setColumnWidth(1, 80)
        self._cmd_table.setColumnWidth(2, 50)
        self._cmd_table.setColumnWidth(3, 90)
        self._cmd_table.setColumnWidth(4, 80)
        self._cmd_table.horizontalHeader().setSectionResizeMode(5, QHeaderView.Stretch)
        self._cmd_table.selectionModel().selectionChanged.connect(self._show_cmd_output)
        tbl_l.addWidget(self._cmd_table)

        out_w = QWidget()
        out_l = QVBoxLayout(out_w)
        out_l.setContentsMargins(0, 0, 0, 0)
        out_lbl = QLabel("Output")
        out_lbl.setStyleSheet(f"color:{MUTED}; font-size:11px; font-weight:600;")
        self._cmd_output = QTextEdit()
        self._cmd_output.setReadOnly(True)
        self._cmd_output.setFont(QFont("Consolas", 11))
        self._cmd_output.setStyleSheet(
            f"background-color:{BG}; color:{GREEN};"
            f"border:1px solid {BORDER}; border-radius:6px; padding:8px;"
        )
        out_l.addWidget(out_lbl)
        out_l.addWidget(self._cmd_output)

        splitter.addWidget(tbl_w)
        splitter.addWidget(out_w)
        splitter.setSizes([500, 250])
        lay.addWidget(splitter)

        self._tabs.addTab(tab, "Commands")

    # ── Conversations ─────────────────────────────────────────────────────────

    def _build_conversations_tab(self):
        tab = QWidget()
        lay = QVBoxLayout(tab)
        lay.setContentsMargins(20, 20, 20, 20)
        lay.setSpacing(12)

        self._conv_table = self._make_table(["Time", "Session", "Role", "Content"])
        self._conv_table.setColumnWidth(0, 140)
        self._conv_table.setColumnWidth(1, 110)
        self._conv_table.setColumnWidth(2, 80)
        self._conv_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        lay.addWidget(self._conv_table)

        self._tabs.addTab(tab, "Conversations")

    # ── Tasks ─────────────────────────────────────────────────────────────

    def _build_tasks_tab(self):
        tab = QWidget()
        lay = QVBoxLayout(tab)
        lay.setContentsMargins(20, 20, 20, 20)
        lay.setSpacing(12)

        btn_row = QHBoxLayout()
        btn_done = QPushButton("✓  Mark Done")
        btn_done.setProperty("success", "true")
        btn_done.clicked.connect(self._complete_task)
        btn_del = QPushButton("🗑  Delete")
        btn_del.setProperty("danger", "true")
        btn_del.clicked.connect(self._delete_task)
        btn_row.addWidget(btn_done)
        btn_row.addSpacing(8)
        btn_row.addWidget(btn_del)
        btn_row.addStretch()
        lay.addLayout(btn_row)

        self._task_table = self._make_table(["ID", "Priority", "Status", "Due", "Title", "Description"])
        self._task_table.setColumnWidth(0, 45)
        self._task_table.setColumnWidth(1, 80)
        self._task_table.setColumnWidth(2, 90)
        self._task_table.setColumnWidth(3, 140)
        self._task_table.setColumnWidth(4, 220)
        self._task_table.horizontalHeader().setSectionResizeMode(5, QHeaderView.Stretch)
        lay.addWidget(self._task_table)

        self._tabs.addTab(tab, "Tasks")

    # ── Farm Data ───────────────────────────────────────────────────────

    def _build_farm_tab(self):
        tab = QWidget()
        lay = QVBoxLayout(tab)
        lay.setContentsMargins(20, 20, 20, 20)
        lay.setSpacing(0)

        splitter = QSplitter(Qt.Vertical)

        pad_w = QWidget()
        pad_l = QVBoxLayout(pad_w)
        pad_l.setContentsMargins(0, 0, 0, 8)
        grp_p = QGroupBox("Paddock Records")
        gp = QVBoxLayout(grp_p)
        gp.setContentsMargins(12, 16, 12, 12)
        self._paddock_table = self._make_table(
            ["ID", "Paddock", "Date", "Type", "Value", "Unit", "Notes"]
        )
        self._paddock_table.setColumnWidth(0, 45)
        self._paddock_table.setColumnWidth(1, 130)
        self._paddock_table.setColumnWidth(2, 100)
        self._paddock_table.setColumnWidth(3, 110)
        self._paddock_table.setColumnWidth(4, 90)
        self._paddock_table.setColumnWidth(5, 65)
        self._paddock_table.horizontalHeader().setSectionResizeMode(6, QHeaderView.Stretch)
        gp.addWidget(self._paddock_table)
        pad_l.addWidget(grp_p)

        hrd_w = QWidget()
        hrd_l = QVBoxLayout(hrd_w)
        hrd_l.setContentsMargins(0, 0, 0, 0)
        grp_h = QGroupBox("Herd Records")
        gh = QVBoxLayout(grp_h)
        gh.setContentsMargins(12, 16, 12, 12)
        self._herd_table = self._make_table(
            ["ID", "Date", "Metric", "Value", "Unit", "Notes"]
        )
        self._herd_table.setColumnWidth(0, 45)
        self._herd_table.setColumnWidth(1, 100)
        self._herd_table.setColumnWidth(2, 140)
        self._herd_table.setColumnWidth(3, 100)
        self._herd_table.setColumnWidth(4, 70)
        self._herd_table.horizontalHeader().setSectionResizeMode(5, QHeaderView.Stretch)
        gh.addWidget(self._herd_table)
        hrd_l.addWidget(grp_h)

        splitter.addWidget(pad_w)
        splitter.addWidget(hrd_w)
        splitter.setSizes([420, 280])
        lay.addWidget(splitter)

        self._tabs.addTab(tab, "Farm Data")

    # ── Chat actions ──────────────────────────────────────────────────────────

    def _chat_append(self, role: str, text: str):
        """Append a message bubble to the chat display."""
        if role == "user":
            color, label = BLUE, "You"
        elif role == "assistant":
            color, label = GREEN, self._cfg.identity.get("assistant_name", "Claw")
        else:
            color, label = MUTED, role
        # Escape HTML, preserve newlines
        import html as _html
        safe = _html.escape(text).replace("\n", "<br>")
        bubble = (
            f'<div style="margin-bottom:10px;">'
            f'<span style="color:{color}; font-weight:700; font-size:12px;">{label}</span>'
            f'<div style="color:{TEXT}; margin-top:3px; line-height:1.5;">{safe}</div>'
            f'</div>'
        )
        self._chat_display.append(bubble)
        # Scroll to bottom
        sb = self._chat_display.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _chat_send(self):
        if self._chat_worker and self._chat_worker.isRunning():
            return   # already waiting for a reply
        text = self._chat_input.text().strip()
        if not text:
            return
        self._chat_input.clear()

        # Check API key is configured
        if not self._cfg.config.get("anthropic_api_key"):
            QMessageBox.warning(
                self, "API Key Missing",
                "Please set your Anthropic API key in Settings → API Keys first.",
            )
            return

        self._chat_append("user", text)
        self._chat_thinking.setVisible(True)
        self._chat_input.setEnabled(False)

        self._chat_worker = _ChatWorker(
            text, self._chat_history, self._chat_smart_cb.isChecked()
        )
        self._chat_worker.response_ready.connect(self._chat_on_response)
        self._chat_worker.error_occurred.connect(self._chat_on_error)
        self._chat_worker.start()

    def _chat_on_response(self, reply: str):
        user_msg = self._chat_worker._message if self._chat_worker else ""
        self._chat_history.append({"role": "user",      "content": user_msg})
        self._chat_history.append({"role": "assistant", "content": reply})
        # Trim to last 40 messages
        if len(self._chat_history) > 40:
            self._chat_history = self._chat_history[-40:]
        self._chat_append("assistant", reply)
        self._chat_thinking.setVisible(False)
        self._chat_input.setEnabled(True)
        self._chat_input.setFocus()

    def _chat_on_error(self, err: str):
        self._chat_append("system", f"⚠️ Error: {err}")
        self._chat_thinking.setVisible(False)
        self._chat_input.setEnabled(True)

    def _chat_clear(self):
        self._chat_history.clear()
        self._chat_display.clear()

    # ── Settings ──────────────────────────────────────────────────────────────

    def _build_settings_tab(self):
        inner = QWidget()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(inner)

        lay = QVBoxLayout(inner)
        lay.setContentsMargins(30, 24, 30, 24)
        lay.setSpacing(20)

        # ── API Keys ──────────────────────────────────────────────────────────
        grp_api = QGroupBox("API Keys")
        f_api = QFormLayout(grp_api)
        f_api.setContentsMargins(16, 20, 16, 16)
        f_api.setSpacing(12)

        def _link(url: str, label: str) -> QLabel:
            lbl = QLabel(f'<a href="{url}" style="color:{BLUE};">{label}</a>')
            lbl.setOpenExternalLinks(True)
            lbl.setStyleSheet("background:transparent; border:none; font-size:11px;")
            return lbl

        self._s_anthropic_key = QLineEdit()
        self._s_anthropic_key.setEchoMode(QLineEdit.Password)
        self._s_anthropic_key.setPlaceholderText("sk-ant-...")
        anthropic_link = _link(
            "https://console.anthropic.com/settings/keys",
            "→ Get your key at console.anthropic.com/settings/keys"
        )

        self._s_tg_token = QLineEdit()
        self._s_tg_token.setEchoMode(QLineEdit.Password)
        self._s_tg_token.setPlaceholderText("123456789:AAH...")
        tg_token_link = _link(
            "https://t.me/BotFather",
            "→ Create a bot via @BotFather on Telegram (click to open)"
        )

        self._s_tg_uid = QLineEdit()
        self._s_tg_uid.setPlaceholderText("Your Telegram numeric user ID")
        tg_uid_link = _link(
            "https://t.me/userinfobot",
            "→ Get your user ID from @userinfobot on Telegram (click to open)"
        )

        tg_row = QHBoxLayout()
        tg_row.setSpacing(8)
        tg_row.addWidget(self._s_tg_token, stretch=1)
        tg_wizard_btn = QPushButton("🤖 Wizard")
        tg_wizard_btn.setFixedHeight(30)
        tg_wizard_btn.setToolTip("Step-by-step Telegram bot setup")
        tg_wizard_btn.clicked.connect(self._open_telegram_wizard)
        tg_row.addWidget(tg_wizard_btn)
        tg_widget = QWidget()
        tg_widget.setLayout(tg_row)

        f_api.addRow("Anthropic API Key:", self._s_anthropic_key)
        f_api.addRow("", anthropic_link)
        f_api.addRow("Telegram Bot Token:", tg_widget)
        f_api.addRow("", tg_token_link)
        f_api.addRow("Telegram User ID:", self._s_tg_uid)
        f_api.addRow("", tg_uid_link)
        lay.addWidget(grp_api)

        # ── Identity ──────────────────────────────────────────────────────────
        grp = QGroupBox("Bot Identity")
        f = QFormLayout(grp)
        f.setContentsMargins(16, 20, 16, 16)
        f.setSpacing(12)
        self._s_name     = QLineEdit()
        self._s_briefing = QLineEdit()
        self._s_briefing.setPlaceholderText("HH:MM  e.g. 08:00")
        f.addRow("Assistant Name:", self._s_name)
        f.addRow("Daily Briefing Time:", self._s_briefing)
        lay.addWidget(grp)

        # Models
        MODELS = [
            "claude-haiku-4-5-20251001",
            "claude-haiku-4-5",
            "claude-sonnet-4-6",
            "claude-sonnet-4-5",
            "claude-opus-4-5",
        ]
        grp2 = QGroupBox("Models")
        f2 = QFormLayout(grp2)
        f2.setContentsMargins(16, 20, 16, 16)
        f2.setSpacing(12)
        self._s_cheap = QComboBox()
        self._s_cheap.addItems(MODELS)
        self._s_smart = QComboBox()
        self._s_smart.addItems(MODELS)
        f2.addRow("Default Model (fast):", self._s_cheap)
        f2.addRow("Smart Model (/smart):", self._s_smart)
        lay.addWidget(grp2)

        # Budget
        grp3 = QGroupBox("Budget Limits")
        f3 = QFormLayout(grp3)
        f3.setContentsMargins(16, 20, 16, 16)
        f3.setSpacing(12)
        self._s_daily   = QDoubleSpinBox()
        self._s_daily.setRange(0.01, 100.0)
        self._s_daily.setSingleStep(0.25)
        self._s_daily.setPrefix("$")
        self._s_monthly = QDoubleSpinBox()
        self._s_monthly.setRange(0.01, 500.0)
        self._s_monthly.setSingleStep(1.0)
        self._s_monthly.setPrefix("$")
        self._s_alerts  = QCheckBox("Enable budget alerts")
        f3.addRow("Daily Limit:", self._s_daily)
        f3.addRow("Monthly Limit:", self._s_monthly)
        f3.addRow("", self._s_alerts)
        lay.addWidget(grp3)

        # Behaviour
        grp4 = QGroupBox("Behaviour")
        f4 = QFormLayout(grp4)
        f4.setContentsMargins(16, 20, 16, 16)
        f4.setSpacing(12)
        self._s_cmd_on   = QCheckBox("Enable command execution")
        self._s_auto_mem = QCheckBox("Auto-extract memories from conversation")
        self._s_max_hist = QSpinBox()
        self._s_max_hist.setRange(5, 200)
        self._s_max_tok  = QSpinBox()
        self._s_max_tok.setRange(256, 8192)
        f4.addRow("", self._s_cmd_on)
        f4.addRow("", self._s_auto_mem)
        f4.addRow("Max History Messages:", self._s_max_hist)
        f4.addRow("Max Response Tokens:", self._s_max_tok)
        lay.addWidget(grp4)

        btn_save = QPushButton("💾   Save Settings")
        btn_save.setFixedHeight(42)
        btn_save.setProperty("success", "true")
        btn_save.clicked.connect(self._save_settings)
        lay.addWidget(btn_save)

        # Farm Location
        grp5 = QGroupBox("Farm Location (for weather)")
        f5 = QFormLayout(grp5)
        f5.setContentsMargins(16, 20, 16, 16)
        f5.setSpacing(12)
        self._s_farm_lat = QDoubleSpinBox()
        self._s_farm_lat.setRange(-90.0, 90.0)
        self._s_farm_lat.setDecimals(6)
        self._s_farm_lat.setSingleStep(0.001)
        self._s_farm_lon = QDoubleSpinBox()
        self._s_farm_lon.setRange(-180.0, 180.0)
        self._s_farm_lon.setDecimals(6)
        self._s_farm_lon.setSingleStep(0.001)
        lat_hint = QLabel("Decimal degrees, e.g. -37.780000  (right-click farm on Google Maps → copy coordinates)")
        lat_hint.setStyleSheet(f"color:{MUTED}; font-size:11px; background:transparent; border:none;")
        f5.addRow("Latitude:", self._s_farm_lat)
        f5.addRow("Longitude:", self._s_farm_lon)
        f5.addRow("", lat_hint)
        lay.addWidget(grp5)

        # Tavily
        grp6 = QGroupBox("Tavily Search API")
        f6 = QFormLayout(grp6)
        f6.setContentsMargins(16, 20, 16, 16)
        f6.setSpacing(12)
        self._s_tavily_key = QLineEdit()
        self._s_tavily_key.setEchoMode(QLineEdit.Password)
        self._s_tavily_key.setPlaceholderText("tvly-...")
        tavily_link = QLabel(
            f'<a href="https://app.tavily.com/home" style="color:{BLUE};">'
            '→ Sign up / get your key at app.tavily.com/home</a>'
        )
        tavily_link.setOpenExternalLinks(True)
        tavily_link.setStyleSheet("background:transparent; border:none; font-size:11px;")
        f6.addRow("API Key:", self._s_tavily_key)
        f6.addRow("", tavily_link)
        lay.addWidget(grp6)

        lay.addStretch()

        self._tabs.addTab(scroll, "Settings")

    # ─────────────────────────────────────────────────────────────────────────
    # Table factory
    # ─────────────────────────────────────────────────────────────────────────

    def _make_table(self, headers: list) -> QTableWidget:
        t = QTableWidget(0, len(headers))
        t.setHorizontalHeaderLabels(headers)
        t.verticalHeader().setVisible(False)
        t.setSelectionBehavior(QTableWidget.SelectRows)
        t.setEditTriggers(QTableWidget.NoEditTriggers)
        t.setAlternatingRowColors(True)
        t.setShowGrid(True)
        t.setWordWrap(False)
        t.verticalHeader().setDefaultSectionSize(30)
        return t

    def _fill_row(self, table: QTableWidget, row: int, values: list,
                  colors: list | None = None):
        for col, val in enumerate(values):
            item = QTableWidgetItem(str(val) if val is not None else "")
            item.setToolTip(str(val) if val is not None else "")
            if colors and col < len(colors) and colors[col]:
                item.setForeground(QColor(colors[col]))
            table.setItem(row, col, item)

    # ─────────────────────────────────────────────────────────────────────────
    # Refresh
    # ─────────────────────────────────────────────────────────────────────────

    def _refresh_all(self):
        self._refresh_status()
        self._refresh_overview()
        self._refresh_usage()
        self._refresh_tasks()
        self._refresh_farm()
        self._refresh_reminders()
        self._refresh_memories()
        self._refresh_commands()
        self._refresh_conversations()
        if not self._settings_loaded:
            self._load_settings_fields()
            self._settings_loaded = True
        self._refresh_label.setText(f"Updated {datetime.now().strftime('%H:%M:%S')}")

    def _refresh_status(self):
        pid = get_bot_pid()
        if pid:
            for w in (self._status_dot, self._status_label):
                w.setStyleSheet(
                    f"color:{GREEN}; font-size:13px; background:transparent; border:none;"
                )
            self._status_dot.setStyleSheet(
                f"color:{GREEN}; font-size:18px; background:transparent; border:none;"
            )
            self._status_label.setText(f"Bot running  (PID {pid})")
            self._btn_start.setEnabled(False)
            self._btn_stop.setEnabled(True)
            self._btn_restart.setEnabled(True)
        else:
            for w in (self._status_dot, self._status_label):
                w.setStyleSheet(
                    f"color:{RED}; font-size:13px; background:transparent; border:none;"
                )
            self._status_dot.setStyleSheet(
                f"color:{RED}; font-size:18px; background:transparent; border:none;"
            )
            self._status_label.setText("Bot stopped")
            self._btn_start.setEnabled(True)
            self._btn_stop.setEnabled(False)
            self._btn_restart.setEnabled(False)

    def _refresh_overview(self):
        try:
            today = datetime.now().replace(
                hour=0, minute=0, second=0, microsecond=0
            ).isoformat()
            with self._db._get_conn() as conn:
                msgs  = conn.execute(
                    "SELECT COUNT(*) FROM conversation_history WHERE created_at>=? AND role='user'",
                    (today,),
                ).fetchone()[0]
                c_day = conn.execute(
                    "SELECT COALESCE(SUM(cost_usd),0) FROM api_usage WHERE timestamp>=?",
                    (today,),
                ).fetchone()[0]
                c_all = conn.execute(
                    "SELECT COALESCE(SUM(cost_usd),0) FROM api_usage"
                ).fetchone()[0]
                rems  = conn.execute(
                    "SELECT COUNT(*) FROM reminders WHERE sent=0"
                ).fetchone()[0]
                mems  = conn.execute(
                    "SELECT COUNT(*) FROM memories"
                ).fetchone()[0]
                tasks = conn.execute(
                    "SELECT COUNT(*) FROM tasks WHERE status NOT IN ('done','cancelled')"
                ).fetchone()[0]
                searches_today = conn.execute(
                    "SELECT COUNT(*) FROM api_usage WHERE timestamp>=? AND purpose='web_search'",
                    (today,),
                ).fetchone()[0]
                farm_recs = conn.execute(
                    "SELECT (SELECT COUNT(*) FROM paddock_records) + (SELECT COUNT(*) FROM herd_records)"
                ).fetchone()[0]
                recent = conn.execute("""
                    SELECT ts, kind, detail FROM (
                        SELECT created_at AS ts, 'Message' AS kind,
                               role || ': ' || SUBSTR(content,1,80) AS detail
                        FROM conversation_history
                        UNION ALL
                        SELECT timestamp, 'API Call',
                               model || '  ' || ROUND(cost_usd*1000,3) || 'm$'
                        FROM api_usage
                        UNION ALL
                        SELECT timestamp, 'Command',
                               SUBSTR(command,1,80)
                        FROM command_history
                    ) ORDER BY ts DESC LIMIT 40
                """).fetchall()

            self._ov_messages.set_value(str(msgs), BLUE)
            self._ov_cost_day.set_value(fmt_cost(c_day),
                                        GREEN if c_day < 0.5 else YELLOW)
            self._ov_tasks.set_value(str(tasks), YELLOW if tasks > 0 else TEXT)
            self._ov_reminders.set_value(str(rems), YELLOW if rems else TEXT)
            self._ov_memories.set_value(str(mems), TEXT)
            self._ov_searches.set_value(str(searches_today), BLUE if searches_today > 0 else TEXT)
            self._ov_farm.set_value(str(farm_recs), TEXT)

            self._ov_table.setRowCount(len(recent))
            kind_colors = {"Message": BLUE, "API Call": GREEN, "Command": YELLOW}
            for r, row in enumerate(recent):
                self._fill_row(self._ov_table, r,
                               [fmt_dt(row[0]), row[1], row[2]],
                               [MUTED, kind_colors.get(row[1], TEXT), None])
        except Exception:
            pass

    def _refresh_usage(self):
        try:
            now   = datetime.now()
            today = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
            week  = (now - timedelta(days=7)).isoformat()
            month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()

            with self._db._get_conn() as conn:
                def cost(where, *args):
                    return conn.execute(
                        f"SELECT COALESCE(SUM(cost_usd),0) FROM api_usage{where}", args
                    ).fetchone()[0]
                c_today = cost(" WHERE timestamp>=?", today)
                c_week  = cost(" WHERE timestamp>=?", week)
                c_month = cost(" WHERE timestamp>=?", month)
                c_total = cost("",)
                n_calls = conn.execute("SELECT COUNT(*) FROM api_usage").fetchone()[0]
                rows    = conn.execute("""
                    SELECT timestamp, model, purpose,
                           input_tokens, output_tokens, cost_usd, response_time_ms
                    FROM api_usage ORDER BY timestamp DESC LIMIT 100
                """).fetchall()

            self._u_today.set_value(fmt_cost(c_today), GREEN if c_today < 0.5 else YELLOW)
            self._u_week.set_value(fmt_cost(c_week),   YELLOW if c_week > 1 else TEXT)
            self._u_month.set_value(fmt_cost(c_month), RED if c_month > 10 else YELLOW)
            self._u_total.set_value(fmt_cost(c_total), RED if c_total > 20 else TEXT)
            self._u_calls.set_value(f"{n_calls:,}", BLUE)

            self._usage_table.setRowCount(len(rows))
            for r, row in enumerate(rows):
                cc = GREEN if row[5] < 0.001 else YELLOW if row[5] < 0.01 else RED
                self._fill_row(self._usage_table, r, [
                    fmt_dt(row[0]), row[1], row[2] or "chat",
                    f"{row[3]:,}", f"{row[4]:,}",
                    fmt_cost(row[5]), f"{row[6] or 0}ms",
                ], colors=[MUTED, BLUE, MUTED, None, None, cc, MUTED])

            # Breakdown by purpose/model
            breakdown = conn.execute("""
                SELECT COALESCE(purpose,'chat') || '  /  ' || model AS label,
                       COUNT(*) AS calls,
                       COALESCE(SUM(input_tokens+output_tokens),0) AS total_tokens,
                       COALESCE(SUM(cost_usd),0) AS cost
                FROM api_usage
                GROUP BY COALESCE(purpose,'chat'), model
                ORDER BY cost DESC
            """).fetchall()
            self._usage_breakdown_table.setRowCount(len(breakdown))
            for r, row in enumerate(breakdown):
                cc = GREEN if row[3] < 0.001 else YELLOW if row[3] < 0.01 else RED
                self._fill_row(self._usage_breakdown_table, r, [
                    row[0], f"{row[1]:,}", f"{row[2]:,}", fmt_cost(row[3]),
                ], colors=[BLUE, None, None, cc])
        except Exception:
            pass

    def _refresh_reminders(self):
        try:
            with self._db._get_conn() as conn:
                rows = conn.execute(
                    "SELECT id, remind_at, recurring, message, sent"
                    " FROM reminders ORDER BY sent ASC, remind_at ASC LIMIT 100"
                ).fetchall()
            self._rem_table.setRowCount(len(rows))
            for r, row in enumerate(rows):
                status = "✅ Sent" if row[4] else "⏳ Pending"
                sc = MUTED if row[4] else GREEN
                self._fill_row(self._rem_table, r, [
                    row[0], fmt_dt(row[1]), row[2] or "once", row[3], status,
                ], colors=[MUTED, YELLOW if not row[4] else MUTED, BLUE, None, sc])
        except Exception:
            pass

    def _refresh_memories(self):
        try:
            with self._db._get_conn() as conn:
                mems  = conn.execute(
                    "SELECT id, category, content, created_at"
                    " FROM memories ORDER BY created_at DESC LIMIT 100"
                ).fetchall()
                facts = conn.execute(
                    "SELECT id, key, value, source, updated_at"
                    " FROM user_facts ORDER BY updated_at DESC LIMIT 100"
                ).fetchall()
            self._mem_table.setRowCount(len(mems))
            for r, row in enumerate(mems):
                self._fill_row(self._mem_table, r,
                               [row[0], row[1], row[2], fmt_dt(row[3])],
                               [MUTED, BLUE, None, MUTED])
            self._facts_table.setRowCount(len(facts))
            for r, row in enumerate(facts):
                self._fill_row(self._facts_table, r,
                               [row[0], row[1], row[2], row[3], fmt_dt(row[4])],
                               [MUTED, BLUE, None, MUTED, MUTED])
        except Exception:
            pass

    def _refresh_commands(self):
        try:
            with self._db._get_conn() as conn:
                rows = conn.execute(
                    "SELECT timestamp, shell, exit_code, duration_ms,"
                    " triggered_by, command, output"
                    " FROM command_history ORDER BY timestamp DESC LIMIT 100"
                ).fetchall()
            self._cmd_rows_data = [dict(r) for r in rows]
            self._cmd_table.setRowCount(len(rows))
            for r, row in enumerate(rows):
                ec = row[2]
                ec_col = GREEN if ec == 0 else RED if ec else MUTED
                self._fill_row(self._cmd_table, r, [
                    fmt_dt(row[0]), row[1] or "ps",
                    str(ec) if ec is not None else "?",
                    f"{row[3]}ms" if row[3] else "—",
                    row[4] or "user", row[5],
                ], colors=[MUTED, MUTED, ec_col, MUTED, BLUE, None])
        except Exception:
            pass

    def _refresh_conversations(self):
        try:
            with self._db._get_conn() as conn:
                rows = conn.execute(
                    "SELECT created_at, session_id, role, content"
                    " FROM conversation_history ORDER BY created_at DESC LIMIT 200"
                ).fetchall()
            self._conv_table.setRowCount(len(rows))
            for r, row in enumerate(rows):
                rc = BLUE if row[2] == "user" else GREEN
                self._fill_row(self._conv_table, r, [
                    fmt_dt(row[0]), (row[1] or "")[:12], row[2],
                    (row[3] or "")[:300],
                ], colors=[MUTED, MUTED, rc, None])
        except Exception:
            pass

    def _refresh_tasks(self):
        try:
            with self._db._get_conn() as conn:
                rows = conn.execute(
                    "SELECT id, priority, status, due_date, title, description"
                    " FROM tasks ORDER BY"
                    " CASE priority WHEN 'urgent' THEN 1 WHEN 'high' THEN 2"
                    " WHEN 'medium' THEN 3 ELSE 4 END, due_date ASC LIMIT 100"
                ).fetchall()
            self._task_table.setRowCount(len(rows))
            priority_colors = {"urgent": RED, "high": YELLOW, "medium": BLUE, "low": MUTED}
            status_colors = {"pending": TEXT, "in_progress": YELLOW, "done": GREEN, "cancelled": MUTED}
            for r, row in enumerate(rows):
                pc = priority_colors.get(row[1] or "medium", TEXT)
                sc = status_colors.get(row[2] or "pending", TEXT)
                self._fill_row(self._task_table, r, [
                    row[0], (row[1] or "medium").upper(),
                    row[2] or "pending",
                    fmt_dt(row[3]) if row[3] else "—",
                    row[4] or "", row[5] or "",
                ], colors=[MUTED, pc, sc, MUTED, None, MUTED])
        except Exception:
            pass

    def _refresh_farm(self):
        try:
            with self._db._get_conn() as conn:
                prows = conn.execute(
                    "SELECT id, paddock_name, date, record_type, value, unit, notes"
                    " FROM paddock_records ORDER BY date DESC, id DESC LIMIT 100"
                ).fetchall()
                hrows = conn.execute(
                    "SELECT id, date, metric, value, unit, notes"
                    " FROM herd_records ORDER BY date DESC, id DESC LIMIT 100"
                ).fetchall()
            self._paddock_table.setRowCount(len(prows))
            for r, row in enumerate(prows):
                self._fill_row(self._paddock_table, r, [
                    row[0], row[1], row[2], row[3],
                    row[4] or "—", row[5] or "", row[6] or "",
                ], colors=[MUTED, BLUE, MUTED, TEXT, None, MUTED, MUTED])
            self._herd_table.setRowCount(len(hrows))
            for r, row in enumerate(hrows):
                self._fill_row(self._herd_table, r, [
                    row[0], row[1], row[2],
                    row[3] or "—", row[4] or "", row[5] or "",
                ], colors=[MUTED, MUTED, BLUE, None, MUTED, MUTED])
        except Exception:
            pass

    def _load_settings_fields(self):
        self._cfg.reload()
        # API Keys
        self._s_anthropic_key.setText(self._cfg.config.get("anthropic_api_key", ""))
        self._s_tg_token.setText(self._cfg.config.get("telegram_token", ""))
        uid = self._cfg.config.get("telegram_user_id", 0)
        self._s_tg_uid.setText(str(uid) if uid else "")
        # Identity
        self._s_name.setText(self._cfg.identity.get("assistant_name", "Claw"))
        self._s_briefing.setText(self._cfg.identity.get("briefing_time", "08:00"))

        for combo, key, default in (
            (self._s_cheap, "cheap_model", "claude-haiku-4-5-20251001"),
            (self._s_smart, "smart_model", "claude-sonnet-4-6"),
        ):
            val = self._cfg.settings.get(key, default)
            idx = combo.findText(val)
            if idx >= 0:
                combo.setCurrentIndex(idx)

        self._s_daily.setValue(self._cfg.settings.get("budget_daily_usd", 1.0))
        self._s_monthly.setValue(self._cfg.settings.get("budget_monthly_usd", 20.0))
        self._s_alerts.setChecked(self._cfg.settings.get("budget_alerts_enabled", True))
        self._s_cmd_on.setChecked(self._cfg.settings.get("command_execution_enabled", True))
        self._s_auto_mem.setChecked(self._cfg.settings.get("auto_memory_extraction", True))
        self._s_max_hist.setValue(self._cfg.settings.get("max_history_messages", 40))
        self._s_max_tok.setValue(self._cfg.settings.get("max_tokens_response", 1024))
        self._s_farm_lat.setValue(float(self._cfg.settings.get("farm_lat", -37.78)))
        self._s_farm_lon.setValue(float(self._cfg.settings.get("farm_lon", 175.28)))
        self._s_tavily_key.setText(self._cfg.config.get("tavily_api_key", ""))

    # ─────────────────────────────────────────────────────────────────────────
    # Bot control
    # ─────────────────────────────────────────────────────────────────────────

    def _start_bot(self):
        app_dir = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).parent
        service_exe = app_dir / "GTclawService.exe"
        if service_exe.exists():
            # Running from installed EXE — launch bundled service
            subprocess.Popen(
                [str(service_exe), "debug"],
                cwd=str(app_dir),
                creationflags=subprocess.CREATE_NEW_CONSOLE,
            )
        else:
            # Running from source — use venv python
            python = str(app_dir / ".venv" / "Scripts" / "python.exe")
            subprocess.Popen(
                [python, "service.py", "debug"],
                cwd=str(app_dir),
                creationflags=subprocess.CREATE_NEW_CONSOLE,
            )
        QTimer.singleShot(2500, self._refresh_status)

    def _stop_bot(self):
        pid = get_bot_pid()
        if pid:
            subprocess.run(
                ["taskkill", "/PID", str(pid), "/F"],
                creationflags=0x08000000,
            )
            QTimer.singleShot(1500, self._refresh_status)

    def _restart_bot(self):
        self._stop_bot()
        QTimer.singleShot(3000, self._start_bot)

    # ─────────────────────────────────────────────────────────────────────────
    # Delete actions
    # ─────────────────────────────────────────────────────────────────────────

    def _delete_reminder(self):
        row = self._rem_table.currentRow()
        if row < 0:
            return
        item = self._rem_table.item(row, 0)
        if not item:
            return
        rid = int(item.text())
        if QMessageBox.question(
            self, "Delete Reminder", f"Delete reminder #{rid}?",
            QMessageBox.Yes | QMessageBox.No,
        ) == QMessageBox.Yes:
            with self._db._get_conn() as conn:
                conn.execute("DELETE FROM reminders WHERE id=?", (rid,))
                conn.commit()
            self._refresh_reminders()

    def _delete_memory(self):
        row = self._mem_table.currentRow()
        if row < 0:
            return
        item = self._mem_table.item(row, 0)
        if not item:
            return
        mid = int(item.text())
        if QMessageBox.question(
            self, "Delete Memory", f"Delete memory #{mid}?",
            QMessageBox.Yes | QMessageBox.No,
        ) == QMessageBox.Yes:
            with self._db._get_conn() as conn:
                conn.execute("DELETE FROM memories WHERE id=?", (mid,))
                conn.commit()
            self._refresh_memories()

    def _delete_fact(self):
        row = self._facts_table.currentRow()
        if row < 0:
            return
        item = self._facts_table.item(row, 0)
        if not item:
            return
        fid = int(item.text())
        if QMessageBox.question(
            self, "Delete Fact", f"Delete fact #{fid}?",
            QMessageBox.Yes | QMessageBox.No,
        ) == QMessageBox.Yes:
            with self._db._get_conn() as conn:
                conn.execute("DELETE FROM user_facts WHERE id=?", (fid,))
                conn.commit()
            self._refresh_memories()

    def _show_cmd_output(self):
        row = self._cmd_table.currentRow()
        if 0 <= row < len(self._cmd_rows_data):
            output = self._cmd_rows_data[row].get("output") or "(no output)"
            self._cmd_output.setPlainText(output)

    def _complete_task(self):
        row = self._task_table.currentRow()
        if row < 0:
            return
        item = self._task_table.item(row, 0)
        if not item:
            return
        tid = int(item.text())
        now = datetime.now().isoformat()
        with self._db._get_conn() as conn:
            conn.execute("UPDATE tasks SET status='done', updated_at=? WHERE id=?", (now, tid))
            conn.commit()
        self._refresh_tasks()

    def _delete_task(self):
        row = self._task_table.currentRow()
        if row < 0:
            return
        item = self._task_table.item(row, 0)
        if not item:
            return
        tid = int(item.text())
        if QMessageBox.question(
            self, "Delete Task", f"Delete task #{tid}?",
            QMessageBox.Yes | QMessageBox.No,
        ) == QMessageBox.Yes:
            with self._db._get_conn() as conn:
                conn.execute("DELETE FROM tasks WHERE id=?", (tid,))
                conn.commit()
            self._refresh_tasks()

    def _save_settings(self):
        # API Keys
        anthropic_key = self._s_anthropic_key.text().strip()
        if anthropic_key:
            self._cfg.config["anthropic_api_key"] = anthropic_key
        tg_token = self._s_tg_token.text().strip()
        if tg_token:
            self._cfg.config["telegram_token"] = tg_token
        try:
            uid = int(self._s_tg_uid.text().strip())
            self._cfg.config["telegram_user_id"] = uid
        except ValueError:
            pass
        self._cfg.identity["assistant_name"] = self._s_name.text().strip()
        self._cfg.identity["briefing_time"]  = self._s_briefing.text().strip()
        self._cfg.settings["cheap_model"]               = self._s_cheap.currentText()
        self._cfg.settings["smart_model"]               = self._s_smart.currentText()
        self._cfg.settings["budget_daily_usd"]          = self._s_daily.value()
        self._cfg.settings["budget_monthly_usd"]        = self._s_monthly.value()
        self._cfg.settings["budget_alerts_enabled"]     = self._s_alerts.isChecked()
        self._cfg.settings["command_execution_enabled"] = self._s_cmd_on.isChecked()
        self._cfg.settings["auto_memory_extraction"]    = self._s_auto_mem.isChecked()
        self._cfg.settings["max_history_messages"]      = self._s_max_hist.value()
        self._cfg.settings["max_tokens_response"]       = self._s_max_tok.value()
        self._cfg.settings["farm_lat"]                  = self._s_farm_lat.value()
        self._cfg.settings["farm_lon"]                  = self._s_farm_lon.value()
        self._cfg.save_identity()
        self._cfg.save_settings()
        # Save all config changes (API keys + Tavily)
        tavily = self._s_tavily_key.text().strip()
        if tavily:
            self._cfg.config["tavily_api_key"] = tavily
        self._cfg.save_config()

        # Auto-restart the bot so it picks up the new keys/settings immediately
        pid = get_bot_pid()
        if pid:
            # Stop existing process
            subprocess.run(
                ["taskkill", "/PID", str(pid), "/F"],
                creationflags=0x08000000,
            )
            # Start fresh after a short delay
            QTimer.singleShot(2000, self._start_bot)
            QMessageBox.information(
                self, "Saved & Restarting",
                "Settings saved.\nThe bot is restarting to apply your changes…",
            )
        else:
            QMessageBox.information(
                self, "Saved",
                "Settings saved.\nClick ▶ Start to launch the bot.",
            )

    def _open_telegram_wizard(self):
        dlg = TelegramSetupDialog(self._cfg, parent=self)
        dlg.exec_()
        # Reload token field in case wizard saved it
        self._s_tg_token.setText(self._cfg.config.get("telegram_token", ""))
        uid = self._cfg.config.get("telegram_user_id", 0)
        self._s_tg_uid.setText(str(uid) if uid else "")


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # Tell Windows this is a distinct app so the taskbar uses the EXE icon
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("GTclaw.Dashboard.1")
    except Exception:
        pass

    app = QApplication(sys.argv)
    app.setApplicationName("GTclaw Dashboard")

    # When frozen, bundled files land in sys._MEIPASS (temp dir), not next to the EXE.
    # Also check next to the EXE in case the installer placed a copy there.
    _icon_candidates = []
    if getattr(sys, "frozen", False):
        _icon_candidates.append(Path(sys._MEIPASS) / "logo.ico")
    _icon_candidates.append(_HERE / "logo.ico")

    _app_icon = QIcon()
    for _c in _icon_candidates:
        if _c.exists():
            _app_icon = QIcon(str(_c))
            break
    if not _app_icon.isNull():
        app.setWindowIcon(_app_icon)

    window = Dashboard()
    if not _app_icon.isNull():
        window.setWindowIcon(_app_icon)
    window.show()
    sys.exit(app.exec_())
