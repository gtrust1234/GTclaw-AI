"""
API Usage tab — daily breakdown, model breakdown, call log.
"""
import sys
from pathlib import Path

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QComboBox, QGroupBox, QHBoxLayout, QHeaderView,
    QLabel, QPushButton, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from database import Database
from config_manager import get_config


def _item(text: str, align: Qt.AlignmentFlag = Qt.AlignLeft) -> QTableWidgetItem:
    item = QTableWidgetItem(str(text))
    item.setTextAlignment(align | Qt.AlignVCenter)
    item.setFlags(item.flags() & ~Qt.ItemIsEditable)
    return item


class UsageTab(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self._db = Database()
        self._build_ui()
        self._refresh()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setSpacing(12)

        # ── Period selector ───────────────────────────────────────────────
        top = QHBoxLayout()
        top.addWidget(QLabel("Period:"))
        self._period_cb = QComboBox()
        self._period_cb.addItems(["today", "this_week", "this_month", "all_time"])
        self._period_cb.setCurrentText("this_month")
        self._period_cb.currentTextChanged.connect(self._refresh)
        top.addWidget(self._period_cb)
        top.addStretch()
        btn = QPushButton("🔄 Refresh")
        btn.clicked.connect(self._refresh)
        top.addWidget(btn)
        root.addLayout(top)

        # ── Summary cards ─────────────────────────────────────────────────
        summary_group = QGroupBox("Summary")
        summary_layout = QHBoxLayout(summary_group)
        self._sum_calls = QLabel("Calls: —")
        self._sum_tokens = QLabel("Tokens: —")
        self._sum_cost = QLabel("Cost: —")
        self._sum_avg_ms = QLabel("Avg latency: —")
        for lbl in (self._sum_calls, self._sum_tokens, self._sum_cost, self._sum_avg_ms):
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setStyleSheet("font-size: 13px; padding: 8px;")
            summary_layout.addWidget(lbl)
        root.addWidget(summary_group)

        # ── By model ──────────────────────────────────────────────────────
        model_group = QGroupBox("By Model (this month)")
        model_layout = QVBoxLayout(model_group)
        self._model_table = self._make_table(
            ["Model", "Calls", "Input tokens", "Output tokens", "Cost (USD)"]
        )
        model_layout.addWidget(self._model_table)
        root.addWidget(model_group)

        # ── Daily breakdown ────────────────────────────────────────────────
        daily_group = QGroupBox("Daily Breakdown (last 30 days)")
        daily_layout = QVBoxLayout(daily_group)
        self._daily_table = self._make_table(
            ["Date", "Calls", "Total tokens", "Cost (USD)"]
        )
        daily_layout.addWidget(self._daily_table)
        root.addWidget(daily_group)

    def _make_table(self, headers: list) -> QTableWidget:
        t = QTableWidget(0, len(headers))
        t.setHorizontalHeaderLabels(headers)
        t.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        t.setEditTriggers(QTableWidget.NoEditTriggers)
        t.setAlternatingRowColors(True)
        t.setSelectionBehavior(QTableWidget.SelectRows)
        return t

    def _refresh(self) -> None:
        period = self._period_cb.currentText()
        summary = self._db.get_usage_summary(period)
        total_tokens = summary["input_tokens"] + summary["output_tokens"]
        self._sum_calls.setText(f"Calls\n{summary['calls']}")
        self._sum_tokens.setText(f"Tokens\n{total_tokens:,}")
        self._sum_cost.setText(f"Cost\n${summary['cost_usd']:.4f}")
        self._sum_avg_ms.setText(f"Avg latency\n{summary['avg_response_ms']:.0f}ms")

        # By model
        rows = self._db.get_usage_by_model("this_month")
        self._model_table.setRowCount(len(rows))
        for r, row in enumerate(rows):
            self._model_table.setItem(r, 0, _item(row["model"]))
            self._model_table.setItem(r, 1, _item(row["calls"], Qt.AlignRight))
            self._model_table.setItem(r, 2, _item(f"{row['input_tokens']:,}", Qt.AlignRight))
            self._model_table.setItem(r, 3, _item(f"{row['output_tokens']:,}", Qt.AlignRight))
            self._model_table.setItem(r, 4, _item(f"${row['cost_usd']:.5f}", Qt.AlignRight))

        # Daily breakdown
        rows = self._db.get_daily_usage(30)
        cfg = get_config()
        daily_limit = float(cfg.settings.get("budget_daily_usd", 1.0))
        self._daily_table.setRowCount(len(rows))
        for r, row in enumerate(rows):
            cost = row["cost_usd"] or 0
            self._daily_table.setItem(r, 0, _item(row["date"]))
            self._daily_table.setItem(r, 1, _item(row["calls"], Qt.AlignRight))
            self._daily_table.setItem(r, 2, _item(f"{row['total_tokens']:,}", Qt.AlignRight))
            cost_item = _item(f"${cost:.5f}", Qt.AlignRight)
            if cost >= daily_limit:
                cost_item.setForeground(Qt.red)
            self._daily_table.setItem(r, 3, cost_item)
