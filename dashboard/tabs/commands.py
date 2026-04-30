"""
Commands tab — view terminal command history, search, re-run.
"""
import sys
from pathlib import Path

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QGroupBox, QHBoxLayout, QHeaderView, QLabel,
    QLineEdit, QPushButton, QTableWidget,
    QTableWidgetItem, QTextEdit, QVBoxLayout, QWidget,
)

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from database import Database
from terminal_executor import execute_command


def _item(text: str, align: Qt.AlignmentFlag = Qt.AlignLeft) -> QTableWidgetItem:
    it = QTableWidgetItem(str(text))
    it.setTextAlignment(align | Qt.AlignVCenter)
    it.setFlags(it.flags() & ~Qt.ItemIsEditable)
    return it


class CommandsTab(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self._db = Database()
        self._rows: list = []
        self._build_ui()
        self._refresh()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setSpacing(8)

        # ── Toolbar ────────────────────────────────────────────────────────
        bar = QHBoxLayout()
        bar.addWidget(QLabel("Search:"))
        self._search = QLineEdit()
        self._search.setPlaceholderText("Filter by command or output…")
        self._search.returnPressed.connect(self._do_search)
        bar.addWidget(self._search)
        bar.addWidget(QPushButton("Search", clicked=self._do_search))
        bar.addWidget(QPushButton("Clear", clicked=self._refresh))
        bar.addStretch()
        run_btn = QPushButton("▶ Run selected again")
        run_btn.clicked.connect(self._rerun)
        bar.addWidget(run_btn)
        root.addLayout(bar)

        # ── Command table ──────────────────────────────────────────────────
        self._table = QTableWidget(0, 6)
        self._table.setHorizontalHeaderLabels(
            ["Timestamp", "Shell", "Exit", "Duration", "Triggered by", "Command"]
        )
        hdr = self._table.horizontalHeader()
        for col, mode in enumerate([
            QHeaderView.ResizeToContents, QHeaderView.ResizeToContents,
            QHeaderView.ResizeToContents, QHeaderView.ResizeToContents,
            QHeaderView.ResizeToContents, QHeaderView.Stretch,
        ]):
            hdr.setSectionResizeMode(col, mode)
        self._table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._table.setAlternatingRowColors(True)
        self._table.setSelectionBehavior(QTableWidget.SelectRows)
        self._table.itemSelectionChanged.connect(self._on_select)
        root.addWidget(self._table)

        # ── Output pane ────────────────────────────────────────────────────
        out_group = QGroupBox("Output")
        out_layout = QVBoxLayout(out_group)
        self._output = QTextEdit()
        self._output.setReadOnly(True)
        self._output.setMaximumHeight(180)
        self._output.setStyleSheet("font-family: Consolas, monospace; font-size: 11px;")
        out_layout.addWidget(self._output)
        root.addWidget(out_group)

        # ── Manual run ─────────────────────────────────────────────────────
        manual_group = QGroupBox("Run a command")
        manual_layout = QHBoxLayout(manual_group)
        self._manual_cmd = QLineEdit()
        self._manual_cmd.setPlaceholderText("PowerShell command…")
        self._manual_cmd.returnPressed.connect(self._run_manual)
        manual_layout.addWidget(self._manual_cmd)
        manual_layout.addWidget(QPushButton("Run", clicked=self._run_manual))
        root.addWidget(manual_group)

    def _refresh(self) -> None:
        self._search.clear()
        self._rows = self._db.get_command_history(limit=200)
        self._populate(self._rows)

    def _do_search(self) -> None:
        q = self._search.text().strip()
        self._rows = self._db.search_commands(q) if q else self._db.get_command_history(200)
        self._populate(self._rows)

    def _populate(self, rows: list) -> None:
        self._table.setRowCount(len(rows))
        for r, row in enumerate(rows):
            ts = str(row.get("timestamp", ""))[:19].replace("T", " ")
            exit_code = row.get("exit_code", "?")
            self._table.setItem(r, 0, _item(ts))
            self._table.setItem(r, 1, _item(row.get("shell", "ps")))
            exit_item = _item(str(exit_code), Qt.AlignCenter)
            if exit_code != 0:
                exit_item.setForeground(Qt.red)
            self._table.setItem(r, 2, exit_item)
            self._table.setItem(r, 3, _item(f"{row.get('duration_ms', 0)}ms", Qt.AlignRight))
            self._table.setItem(r, 4, _item(row.get("triggered_by", "")))
            self._table.setItem(r, 5, _item(row.get("command", "")))

    def _on_select(self) -> None:
        idx = self._table.currentRow()
        if 0 <= idx < len(self._rows):
            self._output.setPlainText(str(self._rows[idx].get("output", "")))

    def _rerun(self) -> None:
        idx = self._table.currentRow()
        if not (0 <= idx < len(self._rows)):
            return
        row = self._rows[idx]
        result = execute_command(
            row["command"], shell=row.get("shell", "powershell"), triggered_by="dashboard"
        )
        self._db.log_command(
            command=row["command"], output=result.output, exit_code=result.exit_code,
            shell=row.get("shell", "powershell"), duration_ms=result.duration_ms,
            triggered_by="dashboard",
        )
        self._output.setPlainText(result.output)
        self._refresh()

    def _run_manual(self) -> None:
        cmd = self._manual_cmd.text().strip()
        if not cmd:
            return
        result = execute_command(cmd, shell="powershell", triggered_by="dashboard")
        self._db.log_command(
            command=cmd, output=result.output, exit_code=result.exit_code,
            shell="powershell", duration_ms=result.duration_ms, triggered_by="dashboard",
        )
        self._output.setPlainText(result.output)
        self._manual_cmd.clear()
        self._refresh()
