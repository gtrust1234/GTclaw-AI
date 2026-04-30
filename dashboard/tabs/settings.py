"""
Settings tab — edit config.json, identity.json, settings.json via UI forms.
"""
import sys
from pathlib import Path

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QCheckBox, QDoubleSpinBox, QFormLayout, QGroupBox,
    QLabel, QLineEdit, QMessageBox, QPushButton,
    QScrollArea, QSpinBox, QTextEdit, QVBoxLayout, QWidget,
)

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from config_manager import get_config


class SettingsTab(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self._build_ui()
        self._load()

    def _build_ui(self) -> None:
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        content = QWidget()
        scroll.setWidget(content)
        root = QVBoxLayout(self)
        root.addWidget(scroll)

        inner = QVBoxLayout(content)
        inner.setSpacing(14)

        # ── API / Connection ──────────────────────────────────────────────
        conn_group = QGroupBox("Connection (config.json)")
        conn_form = QFormLayout(conn_group)

        self._anthropic_key = QLineEdit()
        self._anthropic_key.setEchoMode(QLineEdit.Password)
        self._anthropic_key.setPlaceholderText("sk-ant-…")
        conn_form.addRow("Anthropic API Key:", self._anthropic_key)

        self._telegram_token = QLineEdit()
        self._telegram_token.setEchoMode(QLineEdit.Password)
        conn_form.addRow("Telegram Bot Token:", self._telegram_token)

        self._telegram_user_id = QLineEdit()
        conn_form.addRow("Your Telegram User ID:", self._telegram_user_id)

        self._db_path = QLineEdit()
        conn_form.addRow("Database Path:", self._db_path)

        self._log_dir = QLineEdit()
        conn_form.addRow("Log Directory:", self._log_dir)
        inner.addWidget(conn_group)

        # ── Identity ──────────────────────────────────────────────────────
        id_group = QGroupBox("Identity (identity.json)")
        id_form = QFormLayout(id_group)

        self._name = QLineEdit()
        id_form.addRow("Assistant Name:", self._name)

        self._briefing_time = QLineEdit()
        self._briefing_time.setPlaceholderText("HH:MM (24h)")
        id_form.addRow("Daily Briefing Time:", self._briefing_time)

        self._system_prompt = QTextEdit()
        self._system_prompt.setFixedHeight(180)
        id_form.addRow("System Prompt:", self._system_prompt)
        inner.addWidget(id_group)

        # ── Budget ────────────────────────────────────────────────────────
        budget_group = QGroupBox("Budget & Alerts (settings.json)")
        budget_form = QFormLayout(budget_group)

        self._daily_budget = QDoubleSpinBox()
        self._daily_budget.setRange(0, 1000)
        self._daily_budget.setDecimals(2)
        self._daily_budget.setPrefix("$")
        budget_form.addRow("Daily Budget:", self._daily_budget)

        self._monthly_budget = QDoubleSpinBox()
        self._monthly_budget.setRange(0, 10000)
        self._monthly_budget.setDecimals(2)
        self._monthly_budget.setPrefix("$")
        budget_form.addRow("Monthly Budget:", self._monthly_budget)

        self._budget_alerts = QCheckBox("Enable budget alerts")
        budget_form.addRow("", self._budget_alerts)
        inner.addWidget(budget_group)

        # ── Models ────────────────────────────────────────────────────────
        model_group = QGroupBox("Model Settings (settings.json)")
        model_form = QFormLayout(model_group)

        self._cheap_model = QLineEdit()
        model_form.addRow("Default (cheap) model:", self._cheap_model)

        self._smart_model = QLineEdit()
        model_form.addRow("Smart model:", self._smart_model)

        self._max_tokens = QSpinBox()
        self._max_tokens.setRange(64, 8192)
        model_form.addRow("Max response tokens:", self._max_tokens)
        inner.addWidget(model_group)

        # ── Commands ──────────────────────────────────────────────────────
        cmd_group = QGroupBox("Command Execution (settings.json)")
        cmd_form = QFormLayout(cmd_group)

        self._cmd_enabled = QCheckBox("Enable command execution")
        cmd_form.addRow("", self._cmd_enabled)

        self._cmd_timeout = QSpinBox()
        self._cmd_timeout.setRange(5, 300)
        self._cmd_timeout.setSuffix(" s")
        cmd_form.addRow("Command timeout:", self._cmd_timeout)
        inner.addWidget(cmd_group)

        # ── Memory ────────────────────────────────────────────────────────
        mem_group = QGroupBox("Memory (settings.json)")
        mem_form = QFormLayout(mem_group)

        self._auto_extract = QCheckBox("Auto-extract memories from conversations")
        mem_form.addRow("", self._auto_extract)

        self._extract_interval = QSpinBox()
        self._extract_interval.setRange(1, 50)
        self._extract_interval.setSuffix(" messages")
        mem_form.addRow("Extraction interval:", self._extract_interval)

        self._max_history = QSpinBox()
        self._max_history.setRange(10, 200)
        self._max_history.setSuffix(" messages")
        mem_form.addRow("Max conversation history:", self._max_history)
        inner.addWidget(mem_group)

        # ── Save / Reload buttons ─────────────────────────────────────────
        btn_layout = QVBoxLayout()
        save_btn = QPushButton("💾 Save All Settings")
        save_btn.setStyleSheet("font-size: 14px; padding: 8px;")
        save_btn.clicked.connect(self._save)
        reload_btn = QPushButton("↺ Reload from files")
        reload_btn.clicked.connect(self._load)
        btn_layout.addWidget(save_btn)
        btn_layout.addWidget(reload_btn)
        inner.addLayout(btn_layout)

    def _load(self) -> None:
        cfg = get_config()
        cfg.reload()

        self._anthropic_key.setText(cfg.config.get("anthropic_api_key", ""))
        self._telegram_token.setText(cfg.config.get("telegram_token", ""))
        self._telegram_user_id.setText(str(cfg.config.get("telegram_user_id", "")))
        self._db_path.setText(cfg.config.get("db_path", ""))
        self._log_dir.setText(cfg.config.get("log_dir", ""))

        self._name.setText(cfg.identity.get("assistant_name", "Claw"))
        self._briefing_time.setText(cfg.identity.get("briefing_time", "08:00"))
        self._system_prompt.setPlainText(cfg.identity.get("system_prompt", ""))

        self._daily_budget.setValue(float(cfg.settings.get("budget_daily_usd", 1.0)))
        self._monthly_budget.setValue(float(cfg.settings.get("budget_monthly_usd", 20.0)))
        self._budget_alerts.setChecked(bool(cfg.settings.get("budget_alerts_enabled", True)))

        self._cheap_model.setText(cfg.settings.get("cheap_model", ""))
        self._smart_model.setText(cfg.settings.get("smart_model", ""))
        self._max_tokens.setValue(int(cfg.settings.get("max_tokens_response", 1024)))

        self._cmd_enabled.setChecked(bool(cfg.settings.get("command_execution_enabled", True)))
        self._cmd_timeout.setValue(int(cfg.settings.get("command_timeout_seconds", 30)))

        self._auto_extract.setChecked(bool(cfg.settings.get("auto_memory_extraction", True)))
        self._extract_interval.setValue(int(cfg.settings.get("memory_extraction_interval", 5)))
        self._max_history.setValue(int(cfg.settings.get("max_history_messages", 40)))

    def _save(self) -> None:
        cfg = get_config()

        cfg.config["anthropic_api_key"] = self._anthropic_key.text().strip()
        cfg.config["telegram_token"] = self._telegram_token.text().strip()
        try:
            cfg.config["telegram_user_id"] = int(self._telegram_user_id.text().strip() or "0")
        except ValueError:
            pass
        cfg.config["db_path"] = self._db_path.text().strip()
        cfg.config["log_dir"] = self._log_dir.text().strip()

        cfg.identity["assistant_name"] = self._name.text().strip()
        cfg.identity["briefing_time"] = self._briefing_time.text().strip()
        cfg.identity["system_prompt"] = self._system_prompt.toPlainText().strip()

        cfg.settings["budget_daily_usd"] = self._daily_budget.value()
        cfg.settings["budget_monthly_usd"] = self._monthly_budget.value()
        cfg.settings["budget_alerts_enabled"] = self._budget_alerts.isChecked()
        cfg.settings["cheap_model"] = self._cheap_model.text().strip()
        cfg.settings["smart_model"] = self._smart_model.text().strip()
        cfg.settings["max_tokens_response"] = self._max_tokens.value()
        cfg.settings["command_execution_enabled"] = self._cmd_enabled.isChecked()
        cfg.settings["command_timeout_seconds"] = self._cmd_timeout.value()
        cfg.settings["auto_memory_extraction"] = self._auto_extract.isChecked()
        cfg.settings["memory_extraction_interval"] = self._extract_interval.value()
        cfg.settings["max_history_messages"] = self._max_history.value()

        cfg.save_all()
        QMessageBox.information(self, "Saved", "Settings saved successfully.\nRestart the bot service for changes to take effect.")
