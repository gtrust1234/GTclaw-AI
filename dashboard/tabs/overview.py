"""
Overview tab — service status, quick stats, recent activity.
"""
import subprocess
import sys
from pathlib import Path

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import (
    QGroupBox, QHBoxLayout, QLabel, QPushButton,
    QTextEdit, QVBoxLayout, QWidget,
)

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from database import Database
from config_manager import get_config

SERVICE_NAME = "PersonalAIAssistant"

_ROOT = Path(__file__).parent.parent.parent
_PYTHON_EXE = str(_ROOT / ".venv" / "Scripts" / "python.exe")
_BOT_SCRIPT = str(_ROOT / "bot.py")

# Shared process handle for direct (non-service) mode
_direct_proc: subprocess.Popen | None = None


def _service_installed() -> bool:
    try:
        result = subprocess.run(
            ["sc", "query", SERVICE_NAME],
            capture_output=True, text=True, timeout=5
        )
        return "RUNNING" in result.stdout or "STOPPED" in result.stdout
    except Exception:
        return False


def _service_status() -> str:
    try:
        result = subprocess.run(
            ["sc", "query", SERVICE_NAME],
            capture_output=True, text=True, timeout=5
        )
        if "RUNNING" in result.stdout:
            return "RUNNING"
        if "STOPPED" in result.stdout:
            return "STOPPED"
        return "NOT INSTALLED"
    except Exception:
        return "UNKNOWN"


def _direct_status() -> str:
    global _direct_proc
    if _direct_proc is None:
        return "STOPPED"
    if _direct_proc.poll() is None:
        return "RUNNING"
    _direct_proc = None
    return "STOPPED"


class OverviewTab(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self._db = Database()
        self._build_ui()
        self._refresh()

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._refresh)
        self._timer.start(15_000)  # refresh every 15 s

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setSpacing(12)

        # ── Service control ───────────────────────────────────────────────
        svc_group = QGroupBox("Bot Service")
        svc_layout = QHBoxLayout(svc_group)

        self._status_lbl = QLabel("…")
        self._status_lbl.setStyleSheet("font-weight: bold; font-size: 14px;")
        svc_layout.addWidget(self._status_lbl)
        svc_layout.addStretch()

        for label, slot in [("▶ Start", self._start_svc),
                             ("■ Stop", self._stop_svc),
                             ("↺ Restart", self._restart_svc)]:
            btn = QPushButton(label)
            btn.setFixedWidth(100)
            btn.clicked.connect(slot)
            svc_layout.addWidget(btn)

        root.addWidget(svc_group)

        # ── Usage summary ─────────────────────────────────────────────────
        stats_group = QGroupBox("Today's Usage")
        stats_layout = QHBoxLayout(stats_group)

        self._calls_lbl = QLabel("Calls: —")
        self._tokens_lbl = QLabel("Tokens: —")
        self._cost_lbl = QLabel("Cost: —")
        self._budget_lbl = QLabel("Budget: —")

        for lbl in (self._calls_lbl, self._tokens_lbl,
                    self._cost_lbl, self._budget_lbl):
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setStyleSheet("font-size: 13px; padding: 8px;")
            stats_layout.addWidget(lbl)

        root.addWidget(stats_group)

        # ── Recent activity ───────────────────────────────────────────────
        activity_group = QGroupBox("Recent API Calls")
        activity_layout = QVBoxLayout(activity_group)
        self._activity_log = QTextEdit()
        self._activity_log.setReadOnly(True)
        self._activity_log.setMaximumHeight(280)
        self._activity_log.setStyleSheet("font-family: Consolas, monospace; font-size: 11px;")
        activity_layout.addWidget(self._activity_log)
        root.addWidget(activity_group)

        refresh_btn = QPushButton("🔄 Refresh")
        refresh_btn.clicked.connect(self._refresh)
        root.addWidget(refresh_btn, alignment=Qt.AlignRight)

    def _refresh(self) -> None:
        # Service status
        if _service_installed():
            status = _service_status()
            mode_suffix = " (service)"
        else:
            status = _direct_status()
            mode_suffix = " (direct)"
        colors = {"RUNNING": "#2ecc71", "STOPPED": "#e74c3c",
                  "NOT INSTALLED": "#f39c12", "UNKNOWN": "#95a5a6"}
        self._status_lbl.setText(f"Status: {status}{mode_suffix}")
        self._status_lbl.setStyleSheet(
            f"font-weight: bold; font-size: 14px; color: {colors.get(status, '#fff')};"
        )

        # Stats
        cfg = get_config()
        today = self._db.get_usage_summary("today")
        daily_limit = float(cfg.settings.get("budget_daily_usd", 1.0))
        total_tokens = today["input_tokens"] + today["output_tokens"]
        self._calls_lbl.setText(f"API Calls\n{today['calls']}")
        self._tokens_lbl.setText(f"Tokens\n{total_tokens:,}")
        self._cost_lbl.setText(f"Cost (today)\n${today['cost_usd']:.4f}")
        pct = (today['cost_usd'] / daily_limit * 100) if daily_limit else 0
        self._budget_lbl.setText(f"Budget used\n{pct:.1f}%")

        # Recent calls
        calls = self._db.get_recent_api_calls(limit=20)
        lines = []
        for c in calls:
            ts = c["timestamp"][:19].replace("T", " ")
            lines.append(
                f"{ts}  {c['model']:<32}  in:{c['input_tokens']:>5}  "
                f"out:{c['output_tokens']:>5}  ${c['cost_usd']:.5f}  {c['purpose']}"
            )
        self._activity_log.setPlainText("\n".join(lines) or "No API calls yet.")

    # ── Service / direct control ──────────────────────────────────────────────

    def _svc_cmd(self, action: str) -> None:
        try:
            subprocess.run(["sc", action, SERVICE_NAME], timeout=10)
        except Exception:
            pass
        self._refresh()

    def _start_svc(self) -> None:
        global _direct_proc
        if _service_installed():
            self._svc_cmd("start")
        else:
            if _direct_proc is None or _direct_proc.poll() is not None:
                _direct_proc = subprocess.Popen(
                    [_PYTHON_EXE, _BOT_SCRIPT],
                    cwd=str(_ROOT),
                )
            self._refresh()

    def _stop_svc(self) -> None:
        global _direct_proc
        if _service_installed():
            self._svc_cmd("stop")
        else:
            if _direct_proc is not None and _direct_proc.poll() is None:
                _direct_proc.terminate()
                try:
                    _direct_proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    _direct_proc.kill()
            _direct_proc = None
            self._refresh()

    def _restart_svc(self) -> None:
        self._stop_svc()
        self._start_svc()
