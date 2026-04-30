"""
Configuration management for Personal AI Assistant.
Manages three JSON config files:
  config/config.json    - API keys, paths, secrets
  config/identity.json  - Personality, system prompts
  config/settings.json  - Feature flags, limits, toggles

Also bootstraps from .env for backward compatibility.
"""
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, Optional

# When running as a PyInstaller EXE, __file__ is inside a temp extraction folder.
# The actual config/ lives next to the EXE (sys.executable).
if getattr(sys, "frozen", False):
    BASE_DIR = Path(sys.executable).parent
else:
    BASE_DIR = Path(__file__).parent

CONFIG_DIR = BASE_DIR / "config"

# ── Defaults ─────────────────────────────────────────────────────────────────

CONFIG_DEFAULTS: Dict[str, Any] = {
    "anthropic_api_key": "",
    "telegram_token": "",
    "telegram_user_id": 0,
    "db_path": str(Path.home() / "assistant_data" / "memory.db"),
    "log_dir": str(Path.home() / "assistant_logs"),
    # Email monitoring
    "email_imap_server": "",
    "email_address": "",
    "email_password": "",
}

IDENTITY_DEFAULTS: Dict[str, Any] = {
    "assistant_name": "Claw",
    "briefing_time": "08:00",
    "system_prompt": (
        "You are a personal AI assistant running 24/7 on the user's Windows PC. "
        "You communicate via Telegram.\n\n"
        "Your personality:\n"
        "- Concise and direct — no fluff, no excessive disclaimers\n"
        "- Warm but efficient — like a smart, trusted assistant\n"
        "- Proactive — if you notice something useful, mention it\n"
        "- Honest — say if you don't know something\n\n"
        "Guidelines:\n"
        "- Keep responses reasonably short unless asked for detail\n"
        "- Use markdown formatting sparingly (Telegram renders *bold*, _italic_, `code`)\n"
        "- If the user shares facts about themselves, acknowledge you'll remember them\n"
        "- You can execute Windows commands when helpful — use the run_command tool\n"
        "- You have access to the user's memories injected at conversation start\n\n"
        "### Email monitoring & bill reminders\n"
        "The bot automatically scans the user's email inbox (via IMAP) every few hours "
        "looking for bills, invoices, subscription renewals, and payment notices. "
        "When one is detected, a reminder is created so the user gets a Telegram notification "
        "before the due date.\n\n"
        "- Use /emails to trigger an immediate inbox scan\n"
        "- Email credentials are configured in the Dashboard → Settings → Email Monitoring\n"
        "- Supported: Gmail (App Password), Outlook, Yahoo, any IMAP server\n\n"
        "If the user asks whether you can monitor emails, check for bills, or set up payment "
        "reminders — yes, you can. Tell them to configure their email in Dashboard settings "
        "and use /emails to scan."
    ),
}

SETTINGS_DEFAULTS: Dict[str, Any] = {
    "budget_daily_usd": 1.0,
    "budget_monthly_usd": 20.0,
    "budget_alerts_enabled": True,
    "command_execution_enabled": True,
    "command_timeout_seconds": 30,
    "auto_memory_extraction": True,
    "memory_extraction_interval": 5,
    "max_history_messages": 40,
    "cheap_model": "claude-haiku-4-5-20251001",
    "smart_model": "claude-sonnet-4-6",
    "max_tokens_response": 1024,
    "blocked_commands": [
        "format", "diskpart", "cipher /w",
        "net user /add", "shutdown", "Restart-Computer",
    ],
    # Email monitoring
    "email_enabled": False,
    "email_scan_interval_hours": 3,
}

# ── Helpers ───────────────────────────────────────────────────────────────────


def _load_json(path: Path, defaults: Dict) -> Dict:
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return {**defaults, **data}
        except Exception:
            return dict(defaults)
    return dict(defaults)


def _save_json(path: Path, data: Dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


# ── ConfigManager ─────────────────────────────────────────────────────────────


class ConfigManager:
    def __init__(self, config_dir: Path = CONFIG_DIR) -> None:
        self.config_dir = config_dir
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self._config_path = config_dir / "config.json"
        self._identity_path = config_dir / "identity.json"
        self._settings_path = config_dir / "settings.json"
        self.reload()

    def reload(self) -> None:
        self.config = _load_json(self._config_path, CONFIG_DEFAULTS)
        self.identity = _load_json(self._identity_path, IDENTITY_DEFAULTS)
        self.settings = _load_json(self._settings_path, SETTINGS_DEFAULTS)

    # ── Save ──────────────────────────────────────────────────────────────

    def save_config(self) -> None:
        _save_json(self._config_path, self.config)

    def save_identity(self) -> None:
        _save_json(self._identity_path, self.identity)

    def save_settings(self) -> None:
        _save_json(self._settings_path, self.settings)

    def save_all(self) -> None:
        self.save_config()
        self.save_identity()
        self.save_settings()

    # ── Accessors ─────────────────────────────────────────────────────────

    def get_db_path(self) -> str:
        val = self.config.get("db_path", "")
        return val if val else CONFIG_DEFAULTS["db_path"]

    def get_log_dir(self) -> str:
        val = self.config.get("log_dir", "")
        return val if val else CONFIG_DEFAULTS["log_dir"]

    def get_anthropic_key(self) -> str:
        return self.config.get("anthropic_api_key", "")

    def get_telegram_token(self) -> str:
        return self.config.get("telegram_token", "")

    def get_telegram_user_id(self) -> int:
        return int(self.config.get("telegram_user_id", 0))

    def get_system_prompt(self) -> str:
        return self.identity.get("system_prompt", IDENTITY_DEFAULTS["system_prompt"])

    def get_cheap_model(self) -> str:
        return self.settings.get("cheap_model", SETTINGS_DEFAULTS["cheap_model"])

    def get_smart_model(self) -> str:
        return self.settings.get("smart_model", SETTINGS_DEFAULTS["smart_model"])

    def get_briefing_time(self) -> str:
        return self.identity.get("briefing_time", "08:00")

    # ── Bootstrap from .env ───────────────────────────────────────────────

    def bootstrap_from_env(self) -> None:
        """Load API keys from environment/.env if config.json is empty."""
        try:
            from dotenv import load_dotenv
            load_dotenv()
        except ImportError:
            pass

        changed = False
        if not self.config.get("anthropic_api_key"):
            key = os.getenv("ANTHROPIC_API_KEY", "")
            if key:
                self.config["anthropic_api_key"] = key
                changed = True
        if not self.config.get("telegram_token"):
            tok = os.getenv("TELEGRAM_TOKEN", "")
            if tok:
                self.config["telegram_token"] = tok
                changed = True
        if not self.config.get("telegram_user_id"):
            uid = os.getenv("YOUR_TELEGRAM_ID", "0")
            if uid and uid != "0":
                self.config["telegram_user_id"] = int(uid)
                changed = True
        if changed:
            self.save_config()


# ── Singleton ─────────────────────────────────────────────────────────────────

_instance: Optional[ConfigManager] = None


def get_config() -> ConfigManager:
    global _instance
    if _instance is None:
        _instance = ConfigManager()
        _instance.bootstrap_from_env()
    return _instance


def get_db_path() -> str:
    return get_config().get_db_path()
