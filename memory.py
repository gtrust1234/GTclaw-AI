"""
MemoryManager — thin façade over Database for backward compatibility.
All data is stored in the central SQLite database via database.py.
"""
from datetime import datetime
from typing import List, Dict, Optional

from database import Database

MAX_HISTORY_MESSAGES = 40


class MemoryManager:
    def __init__(self) -> None:
        self._db = Database()

    # ── Long-term memories ────────────────────────────────────────────────────

    def add_memory(self, content: str, category: str = "general") -> bool:
        return self._db.add_memory(content, category)

    def get_all_memories(self) -> List[Dict]:
        rows = self._db.get_all_memories()
        # Normalise 'date' key expected by existing callers
        for r in rows:
            r.setdefault("date", r.get("created_at", "")[:10])
        return rows

    def delete_memory(self, topic: str) -> bool:
        return self._db.delete_memory(topic) > 0

    # ── Conversation history ──────────────────────────────────────────────────

    def add_to_history(self, role: str, content: str, session_id: Optional[str] = None) -> None:
        self._db.add_message(role, content, session_id)

    def get_conversation_history(self, limit: int = MAX_HISTORY_MESSAGES) -> List[Dict]:
        return self._db.get_recent_history(limit)

    def clear_conversation_history(self) -> None:
        self._db.clear_conversation_history()

    # ── Reminders ─────────────────────────────────────────────────────────────

    def add_reminder(self, message: str, remind_at: datetime, recurring: Optional[str] = None) -> None:
        self._db.add_reminder(message, remind_at, recurring)

    def get_due_reminders(self) -> List[Dict]:
        return self._db.get_due_reminders()

    def get_pending_reminders(self) -> List[Dict]:
        return self._db.get_pending_reminders()

    def mark_reminder_sent(self, reminder_id: int) -> None:
        self._db.fire_reminder(reminder_id)

    # ── User facts ─────────────────────────────────────────────────────────────

    def set_fact(self, key: str, value: str, source: str = "manual") -> None:
        self._db.set_user_fact(key, value, source)

    def get_fact(self, key: str) -> Optional[str]:
        return self._db.get_user_fact(key)

    def get_all_facts(self) -> List[Dict]:
        return self._db.get_all_user_facts()

    # ── Passthrough to underlying DB (for dashboard / other modules) ──────────

    @property
    def db(self) -> Database:
        return self._db
