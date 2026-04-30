"""
Memory & Facts tab — view/add/delete long-term memories and user facts.
"""
import sys
from pathlib import Path

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QGroupBox, QHBoxLayout, QHeaderView, QInputDialog,
    QLabel, QLineEdit, QMessageBox, QPushButton,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from database import Database


def _item(text: str) -> QTableWidgetItem:
    it = QTableWidgetItem(str(text))
    it.setFlags(it.flags() & ~Qt.ItemIsEditable)
    return it


class MemoryTab(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self._db = Database()
        self._build_ui()
        self._refresh()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setSpacing(12)

        # ── Memories section ──────────────────────────────────────────────
        mem_group = QGroupBox("Long-term Memories")
        mem_layout = QVBoxLayout(mem_group)

        mem_bar = QHBoxLayout()
        self._mem_search = QLineEdit()
        self._mem_search.setPlaceholderText("Filter memories…")
        self._mem_search.textChanged.connect(self._filter_memories)
        mem_bar.addWidget(self._mem_search)
        add_mem_btn = QPushButton("+ Add")
        add_mem_btn.clicked.connect(self._add_memory)
        del_mem_btn = QPushButton("🗑 Delete")
        del_mem_btn.clicked.connect(self._delete_memory)
        mem_bar.addWidget(add_mem_btn)
        mem_bar.addWidget(del_mem_btn)
        mem_layout.addLayout(mem_bar)

        self._mem_table = QTableWidget(0, 4)
        self._mem_table.setHorizontalHeaderLabels(["ID", "Content", "Category", "Date"])
        hdr = self._mem_table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(1, QHeaderView.Stretch)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self._mem_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._mem_table.setAlternatingRowColors(True)
        self._mem_table.setSelectionBehavior(QTableWidget.SelectRows)
        mem_layout.addWidget(self._mem_table)
        root.addWidget(mem_group)

        # ── User facts section ────────────────────────────────────────────
        facts_group = QGroupBox("Structured User Facts")
        facts_layout = QVBoxLayout(facts_group)

        facts_bar = QHBoxLayout()
        add_fact_btn = QPushButton("+ Add Fact")
        add_fact_btn.clicked.connect(self._add_fact)
        del_fact_btn = QPushButton("🗑 Delete Fact")
        del_fact_btn.clicked.connect(self._delete_fact)
        facts_bar.addWidget(add_fact_btn)
        facts_bar.addWidget(del_fact_btn)
        facts_bar.addStretch()
        facts_layout.addLayout(facts_bar)

        self._fact_table = QTableWidget(0, 5)
        self._fact_table.setHorizontalHeaderLabels(
            ["ID", "Key", "Value", "Source", "Updated"]
        )
        fhdr = self._fact_table.horizontalHeader()
        fhdr.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        fhdr.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        fhdr.setSectionResizeMode(2, QHeaderView.Stretch)
        fhdr.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        fhdr.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self._fact_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._fact_table.setAlternatingRowColors(True)
        self._fact_table.setSelectionBehavior(QTableWidget.SelectRows)
        facts_layout.addWidget(self._fact_table)
        root.addWidget(facts_group)

        refresh_btn = QPushButton("🔄 Refresh")
        refresh_btn.clicked.connect(self._refresh)
        root.addWidget(refresh_btn, alignment=Qt.AlignRight)

    # ── Memories ──────────────────────────────────────────────────────────────

    def _refresh(self) -> None:
        self._all_memories = self._db.get_all_memories()
        self._populate_memories(self._all_memories)
        self._populate_facts(self._db.get_all_user_facts())

    def _filter_memories(self, text: str) -> None:
        q = text.lower()
        filtered = [m for m in self._all_memories if q in m["content"].lower()]
        self._populate_memories(filtered)

    def _populate_memories(self, rows: list) -> None:
        self._mem_table.setRowCount(len(rows))
        for r, row in enumerate(rows):
            self._mem_table.setItem(r, 0, _item(row["id"]))
            self._mem_table.setItem(r, 1, _item(row["content"]))
            self._mem_table.setItem(r, 2, _item(row.get("category", "")))
            self._mem_table.setItem(r, 3, _item(str(row.get("created_at", ""))[:10]))

    def _add_memory(self) -> None:
        text, ok = QInputDialog.getText(self, "Add Memory", "Memory content:")
        if ok and text.strip():
            self._db.add_memory(text.strip())
            self._refresh()

    def _delete_memory(self) -> None:
        row = self._mem_table.currentRow()
        if row < 0:
            return
        mem_id = int(self._mem_table.item(row, 0).text())
        reply = QMessageBox.question(
            self, "Delete Memory", "Delete this memory?",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self._db.delete_memory_by_id(mem_id)
            self._refresh()

    # ── User facts ────────────────────────────────────────────────────────────

    def _populate_facts(self, rows: list) -> None:
        self._fact_table.setRowCount(len(rows))
        for r, row in enumerate(rows):
            self._fact_table.setItem(r, 0, _item(row["id"]))
            self._fact_table.setItem(r, 1, _item(row["key"]))
            self._fact_table.setItem(r, 2, _item(row["value"]))
            self._fact_table.setItem(r, 3, _item(row.get("source", "")))
            self._fact_table.setItem(r, 4, _item(str(row.get("updated_at", ""))[:10]))

    def _add_fact(self) -> None:
        key, ok1 = QInputDialog.getText(self, "Add Fact", "Key (e.g. name, city, job):")
        if not (ok1 and key.strip()):
            return
        val, ok2 = QInputDialog.getText(self, "Add Fact", f"Value for '{key}':")
        if ok2 and val.strip():
            self._db.set_user_fact(key.strip(), val.strip(), source="manual")
            self._refresh()

    def _delete_fact(self) -> None:
        row = self._fact_table.currentRow()
        if row < 0:
            return
        fact_id = int(self._fact_table.item(row, 0).text())
        reply = QMessageBox.question(
            self, "Delete Fact", "Delete this fact?",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self._db.delete_user_fact(fact_id)
            self._refresh()
