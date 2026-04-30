"""
Conversations tab — browse, search, and export message history.
"""
import csv
import sys
from pathlib import Path

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QFileDialog, QGroupBox, QHBoxLayout, QHeaderView,
    QLabel, QLineEdit, QPushButton, QTableWidget,
    QTableWidgetItem, QTextEdit, QVBoxLayout, QWidget,
)

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from database import Database


def _item(text: str) -> QTableWidgetItem:
    it = QTableWidgetItem(str(text))
    it.setFlags(it.flags() & ~Qt.ItemIsEditable)
    return it


class ConversationsTab(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self._db = Database()
        self._rows: list = []
        self._build_ui()
        self._load()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setSpacing(8)

        # ── Search bar ─────────────────────────────────────────────────────
        bar = QHBoxLayout()
        bar.addWidget(QLabel("Search:"))
        self._search = QLineEdit()
        self._search.setPlaceholderText("Type to search…")
        self._search.returnPressed.connect(self._search_msgs)
        bar.addWidget(self._search)
        search_btn = QPushButton("Search")
        search_btn.clicked.connect(self._search_msgs)
        bar.addWidget(search_btn)
        clear_btn = QPushButton("Clear")
        clear_btn.clicked.connect(self._load)
        bar.addWidget(clear_btn)
        export_btn = QPushButton("Export CSV")
        export_btn.clicked.connect(self._export_csv)
        bar.addWidget(export_btn)
        root.addLayout(bar)

        # ── Message table ──────────────────────────────────────────────────
        self._table = QTableWidget(0, 4)
        self._table.setHorizontalHeaderLabels(["Timestamp", "Role", "Preview", "Session"])
        hdr = self._table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(2, QHeaderView.Stretch)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self._table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._table.setAlternatingRowColors(True)
        self._table.setSelectionBehavior(QTableWidget.SelectRows)
        self._table.itemSelectionChanged.connect(self._on_select)
        root.addWidget(self._table)

        # ── Detail pane ────────────────────────────────────────────────────
        detail_group = QGroupBox("Message content")
        detail_layout = QVBoxLayout(detail_group)
        self._detail = QTextEdit()
        self._detail.setReadOnly(True)
        self._detail.setMaximumHeight(150)
        self._detail.setStyleSheet("font-size: 12px;")
        detail_layout.addWidget(self._detail)
        root.addWidget(detail_group)

    def _load(self) -> None:
        self._search.clear()
        self._rows = self._db.get_all_conversations(limit=300)
        self._populate(self._rows)

    def _search_msgs(self) -> None:
        q = self._search.text().strip()
        if not q:
            self._load()
            return
        self._rows = self._db.search_conversations(q)
        self._populate(self._rows)

    def _populate(self, rows: list) -> None:
        self._table.setRowCount(len(rows))
        for r, row in enumerate(rows):
            ts = str(row.get("created_at", ""))[:19].replace("T", " ")
            role = str(row.get("role", ""))
            preview = str(row.get("content", ""))[:120].replace("\n", " ")
            session = str(row.get("session_id") or "")[:8]
            self._table.setItem(r, 0, _item(ts))
            role_item = _item(role)
            role_item.setForeground(
                Qt.blue if role == "user" else Qt.darkGreen
            )
            self._table.setItem(r, 1, role_item)
            self._table.setItem(r, 2, _item(preview))
            self._table.setItem(r, 3, _item(session))

    def _on_select(self) -> None:
        rows = self._table.selectedItems()
        if not rows:
            return
        row_idx = self._table.currentRow()
        if 0 <= row_idx < len(self._rows):
            self._detail.setPlainText(str(self._rows[row_idx].get("content", "")))

    def _export_csv(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Export conversations", "conversations.csv", "CSV files (*.csv)"
        )
        if not path:
            return
        rows = self._db.get_all_conversations(limit=10_000)
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["id", "role", "content", "session_id", "created_at"])
            writer.writeheader()
            writer.writerows(rows)
