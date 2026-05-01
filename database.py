"""
Central SQLite database layer for Personal AI Assistant.
All persistent data lives in a single file — memories, conversations,
API usage logs, command history, reminders, and budget alerts.
"""
import sqlite3
import os
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from config_manager import get_db_path


# Token cost table (USD per million tokens)
_MODEL_COSTS: Dict[str, Dict[str, float]] = {
    "claude-haiku-4-5-20251001": {"input": 0.80, "output": 4.00},
    "claude-haiku-4-5": {"input": 0.80, "output": 4.00},
    "claude-sonnet-4-6": {"input": 3.00, "output": 15.00},
    "claude-sonnet-4-5": {"input": 3.00, "output": 15.00},
    "claude-opus-4-5": {"input": 15.00, "output": 75.00},
}

_DEFAULT_COST = {"input": 3.00, "output": 15.00}


def calculate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    costs = _MODEL_COSTS.get(model, _DEFAULT_COST)
    return (input_tokens * costs["input"] + output_tokens * costs["output"]) / 1_000_000


# ── Database class ────────────────────────────────────────────────────────────


class Database:
    def __init__(self, db_path: Optional[str] = None) -> None:
        self.db_path = db_path or get_db_path()
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _init_db(self) -> None:
        with self._get_conn() as conn:
            conn.executescript("""
                -- Long-term memories (free-text facts)
                CREATE TABLE IF NOT EXISTS memories (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    content     TEXT    NOT NULL,
                    category    TEXT    DEFAULT 'general',
                    created_at  TEXT    NOT NULL,
                    updated_at  TEXT    NOT NULL
                );

                -- Structured user facts (key-value)
                CREATE TABLE IF NOT EXISTS user_facts (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    key         TEXT    NOT NULL,
                    value       TEXT    NOT NULL,
                    source      TEXT    DEFAULT 'manual',
                    confidence  REAL    DEFAULT 1.0,
                    created_at  TEXT    NOT NULL,
                    updated_at  TEXT    NOT NULL,
                    UNIQUE(key)
                );

                -- Individual conversation messages
                CREATE TABLE IF NOT EXISTS conversation_history (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id  TEXT,
                    role        TEXT    NOT NULL,
                    content     TEXT    NOT NULL,
                    created_at  TEXT    NOT NULL
                );

                -- Scheduled reminders
                CREATE TABLE IF NOT EXISTS reminders (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    message     TEXT    NOT NULL,
                    remind_at   TEXT    NOT NULL,
                    sent        INTEGER DEFAULT 0,
                    created_at  TEXT    NOT NULL
                );

                -- API call log (tokens + cost)
                CREATE TABLE IF NOT EXISTS api_usage (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp       TEXT    NOT NULL,
                    model           TEXT    NOT NULL,
                    endpoint        TEXT    DEFAULT 'messages',
                    input_tokens    INTEGER NOT NULL,
                    output_tokens   INTEGER NOT NULL,
                    cost_usd        REAL    NOT NULL,
                    response_time_ms INTEGER DEFAULT 0,
                    session_id      TEXT,
                    purpose         TEXT    DEFAULT 'chat'
                );

                -- Terminal command history
                CREATE TABLE IF NOT EXISTS command_history (
                    id           INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp    TEXT    NOT NULL,
                    command      TEXT    NOT NULL,
                    shell        TEXT    DEFAULT 'powershell',
                    output       TEXT,
                    exit_code    INTEGER,
                    success      INTEGER DEFAULT 1,
                    duration_ms  INTEGER DEFAULT 0,
                    triggered_by TEXT    DEFAULT 'user'
                );

                -- Budget alert log
                CREATE TABLE IF NOT EXISTS budget_alerts (
                    id             INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp      TEXT    NOT NULL,
                    alert_type     TEXT    NOT NULL,
                    threshold_usd  REAL    NOT NULL,
                    actual_usd     REAL    NOT NULL,
                    period         TEXT    NOT NULL
                );

                -- Task / to-do tracking
                CREATE TABLE IF NOT EXISTS tasks (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    title       TEXT    NOT NULL,
                    description TEXT,
                    priority    TEXT    DEFAULT 'medium',
                    status      TEXT    DEFAULT 'pending',
                    due_date    TEXT,
                    created_at  TEXT    NOT NULL,
                    updated_at  TEXT    NOT NULL
                );

                -- Paddock / field records (fertilizer, yield, soil, spray)
                CREATE TABLE IF NOT EXISTS paddock_records (
                    id            INTEGER PRIMARY KEY AUTOINCREMENT,
                    paddock_name  TEXT    NOT NULL,
                    date          TEXT    NOT NULL,
                    record_type   TEXT    NOT NULL,
                    value         TEXT,
                    unit          TEXT,
                    notes         TEXT,
                    created_at    TEXT    NOT NULL
                );

                -- Herd health records (milk yield, SCC, vet notes, treatments)
                CREATE TABLE IF NOT EXISTS herd_records (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    date       TEXT    NOT NULL,
                    metric     TEXT    NOT NULL,
                    value      TEXT,
                    unit       TEXT,
                    notes      TEXT,
                    created_at TEXT    NOT NULL
                );
            """)
            conn.commit()

        # ── Schema migrations (add columns that may be missing in older DBs) ──
        with self._get_conn() as conn:
            existing = {row[1] for row in conn.execute("PRAGMA table_info(conversation_history)")}
            if "session_id" not in existing:
                conn.execute("ALTER TABLE conversation_history ADD COLUMN session_id TEXT")
                conn.commit()
            existing_api = {row[1] for row in conn.execute("PRAGMA table_info(api_usage)")}
            if "session_id" not in existing_api:
                conn.execute("ALTER TABLE api_usage ADD COLUMN session_id TEXT")
                conn.commit()
            existing_rem = {row[1] for row in conn.execute("PRAGMA table_info(reminders)")}
            if "recurring" not in existing_rem:
                conn.execute("ALTER TABLE reminders ADD COLUMN recurring TEXT DEFAULT NULL")
                conn.commit()

    # ── Memories ──────────────────────────────────────────────────────────────

    def add_memory(self, content: str, category: str = "general") -> bool:
        """Add a memory, silently skipping exact duplicates. Returns True if added."""
        existing = self.get_all_memories()
        if any(m["content"].lower() == content.lower() for m in existing):
            return False
        now = datetime.now().isoformat()
        with self._get_conn() as conn:
            conn.execute(
                "INSERT INTO memories (content, category, created_at, updated_at) VALUES (?,?,?,?)",
                (content, category, now, now),
            )
            conn.commit()
        return True

    def get_all_memories(self) -> List[Dict]:
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT id, content, category, created_at FROM memories ORDER BY created_at DESC"
            ).fetchall()
        return [dict(r) for r in rows]

    def delete_memory(self, topic: str) -> int:
        """Delete memories containing topic string. Returns deleted count."""
        with self._get_conn() as conn:
            result = conn.execute(
                "DELETE FROM memories WHERE LOWER(content) LIKE ?",
                (f"%{topic.lower()}%",),
            )
            conn.commit()
            return result.rowcount

    def delete_memory_by_id(self, memory_id: int) -> bool:
        with self._get_conn() as conn:
            result = conn.execute("DELETE FROM memories WHERE id=?", (memory_id,))
            conn.commit()
            return result.rowcount > 0

    # ── User Facts ────────────────────────────────────────────────────────────

    def set_user_fact(
        self, key: str, value: str, source: str = "manual", confidence: float = 1.0
    ) -> None:
        now = datetime.now().isoformat()
        with self._get_conn() as conn:
            conn.execute(
                """INSERT INTO user_facts (key, value, source, confidence, created_at, updated_at)
                   VALUES (?,?,?,?,?,?)
                   ON CONFLICT(key) DO UPDATE SET
                       value=excluded.value, source=excluded.source,
                       confidence=excluded.confidence, updated_at=excluded.updated_at""",
                (key, value, source, confidence, now, now),
            )
            conn.commit()

    def get_user_fact(self, key: str) -> Optional[str]:
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT value FROM user_facts WHERE key=?", (key,)
            ).fetchone()
        return row["value"] if row else None

    def get_all_user_facts(self) -> List[Dict]:
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT id, key, value, source, confidence, created_at, updated_at "
                "FROM user_facts ORDER BY updated_at DESC"
            ).fetchall()
        return [dict(r) for r in rows]

    def delete_user_fact(self, fact_id: int) -> bool:
        with self._get_conn() as conn:
            result = conn.execute("DELETE FROM user_facts WHERE id=?", (fact_id,))
            conn.commit()
            return result.rowcount > 0

    # ── Conversation History ──────────────────────────────────────────────────

    def add_message(
        self, role: str, content: str, session_id: Optional[str] = None
    ) -> None:
        now = datetime.now().isoformat()
        with self._get_conn() as conn:
            conn.execute(
                "INSERT INTO conversation_history (session_id, role, content, created_at) VALUES (?,?,?,?)",
                (session_id, role, content, now),
            )
            conn.commit()
        self._trim_history()

    def get_recent_history(self, limit: int = 40) -> List[Dict]:
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT role, content FROM conversation_history ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]

    def get_all_conversations(self, limit: int = 200, offset: int = 0) -> List[Dict]:
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT id, role, content, session_id, created_at "
                "FROM conversation_history ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (limit, offset),
            ).fetchall()
        return [dict(r) for r in rows]

    def search_conversations(self, query: str) -> List[Dict]:
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT id, role, content, session_id, created_at FROM conversation_history "
                "WHERE LOWER(content) LIKE ? ORDER BY created_at DESC LIMIT 200",
                (f"%{query.lower()}%",),
            ).fetchall()
        return [dict(r) for r in rows]

    def clear_conversation_history(self) -> None:
        with self._get_conn() as conn:
            conn.execute("DELETE FROM conversation_history")
            conn.commit()

    def _trim_history(self, keep: int = 100) -> None:
        with self._get_conn() as conn:
            count = conn.execute(
                "SELECT COUNT(*) FROM conversation_history"
            ).fetchone()[0]
            if count > keep:
                conn.execute(
                    "DELETE FROM conversation_history WHERE id IN "
                    "(SELECT id FROM conversation_history ORDER BY created_at ASC LIMIT ?)",
                    (count - keep,),
                )
                conn.commit()

    # ── Reminders ─────────────────────────────────────────────────────────────

    def add_reminder(self, message: str, remind_at: datetime, recurring: Optional[str] = None) -> None:
        now = datetime.now().isoformat()
        with self._get_conn() as conn:
            conn.execute(
                "INSERT INTO reminders (message, remind_at, recurring, created_at) VALUES (?,?,?,?)",
                (message, remind_at.isoformat(), recurring, now),
            )
            conn.commit()

    def get_due_reminders(self) -> List[Dict]:
        now = datetime.now().isoformat()
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT id, message, recurring, remind_at FROM reminders WHERE remind_at <= ? AND sent=0",
                (now,),
            ).fetchall()
            # Atomically mark them as sent so concurrent callers can't pick up the same rows
            if rows:
                ids = [r["id"] for r in rows]
                conn.execute(
                    f"UPDATE reminders SET sent=1 WHERE id IN ({','.join('?' for _ in ids)}) AND sent=0",
                    ids,
                )
                conn.commit()
                # Only return rows we actually claimed (sent was still 0 when we updated)
        return [dict(r) for r in rows]

    def get_pending_reminders(self) -> List[Dict]:
        """All future (unsent) reminders, for display."""
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT id, message, remind_at, recurring FROM reminders WHERE sent=0 ORDER BY remind_at ASC LIMIT 30"
            ).fetchall()
        return [dict(r) for r in rows]

    def fire_reminder(self, reminder_id: int) -> None:
        """For recurring reminders: reschedule to next occurrence.
        For one-time reminders: no-op (already marked sent by get_due_reminders)."""
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT recurring, remind_at FROM reminders WHERE id=?", (reminder_id,)
            ).fetchone()
            if not row:
                return
            if row["recurring"]:
                next_at = self._next_occurrence(row["remind_at"], row["recurring"])
                conn.execute(
                    "UPDATE reminders SET remind_at=?, sent=0 WHERE id=?",
                    (next_at, reminder_id),
                )
                conn.commit()
            # one-time: sent=1 was already set in get_due_reminders — nothing to do

    def _next_occurrence(self, last_at_str: str, recurring: str) -> str:
        from datetime import timedelta
        last_at = datetime.fromisoformat(last_at_str)
        if recurring == "daily":
            next_at = last_at + timedelta(days=1)
        elif recurring == "weekly":
            next_at = last_at + timedelta(weeks=1)
        elif recurring == "hourly":
            next_at = last_at + timedelta(hours=1)
        elif recurring.startswith("minutes:"):
            mins = int(recurring.split(":")[1])
            next_at = last_at + timedelta(minutes=mins)
        else:
            next_at = last_at + timedelta(days=1)
        return next_at.isoformat()

    def mark_reminder_sent(self, reminder_id: int) -> None:
        """Legacy alias — use fire_reminder for new code."""
        self.fire_reminder(reminder_id)

    # ── Tasks ─────────────────────────────────────────────────────────────────

    def create_task(
        self,
        title: str,
        description: str = None,
        priority: str = "medium",
        due_date: str = None,
    ) -> int:
        now = datetime.now().isoformat()
        with self._get_conn() as conn:
            cur = conn.execute(
                "INSERT INTO tasks (title, description, priority, status, due_date, created_at, updated_at) "
                "VALUES (?,?,?,?,?,?,?)",
                (title, description, priority, "pending", due_date, now, now),
            )
            conn.commit()
            return cur.lastrowid

    def get_tasks(self, status: str = "pending", limit: int = 20) -> List[Dict]:
        with self._get_conn() as conn:
            if status == "all":
                rows = conn.execute(
                    "SELECT * FROM tasks ORDER BY "
                    "CASE priority WHEN 'urgent' THEN 1 WHEN 'high' THEN 2 WHEN 'medium' THEN 3 ELSE 4 END, "
                    "due_date ASC LIMIT ?",
                    (limit,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM tasks WHERE status=? ORDER BY "
                    "CASE priority WHEN 'urgent' THEN 1 WHEN 'high' THEN 2 WHEN 'medium' THEN 3 ELSE 4 END, "
                    "due_date ASC LIMIT ?",
                    (status, limit),
                ).fetchall()
        return [dict(r) for r in rows]

    def update_task(self, task_id: int, **kwargs) -> bool:
        now = datetime.now().isoformat()
        allowed = {"title", "description", "priority", "status", "due_date"}
        updates = {k: v for k, v in kwargs.items() if k in allowed and v is not None}
        if not updates:
            return False
        updates["updated_at"] = now
        sets = ", ".join(f"{k}=?" for k in updates)
        vals = list(updates.values()) + [task_id]
        with self._get_conn() as conn:
            result = conn.execute(f"UPDATE tasks SET {sets} WHERE id=?", vals)
            conn.commit()
            return result.rowcount > 0

    # ── Paddock Records ───────────────────────────────────────────────────────

    def log_paddock(
        self,
        paddock_name: str,
        record_type: str,
        date: str = None,
        value: str = None,
        unit: str = None,
        notes: str = None,
    ) -> int:
        now = datetime.now().isoformat()
        date = date or datetime.now().date().isoformat()
        with self._get_conn() as conn:
            cur = conn.execute(
                "INSERT INTO paddock_records (paddock_name, date, record_type, value, unit, notes, created_at) "
                "VALUES (?,?,?,?,?,?,?)",
                (paddock_name, date, record_type, value, unit, notes, now),
            )
            conn.commit()
            return cur.lastrowid

    def get_paddock_records(
        self,
        paddock_name: str = None,
        record_type: str = None,
        days_back: int = 30,
        limit: int = 20,
    ) -> List[Dict]:
        clauses = [f"date >= '{(datetime.now() - timedelta(days=days_back)).date().isoformat()}'"]
        params: List[Any] = []
        if paddock_name:
            clauses.append("LOWER(paddock_name) LIKE ?")
            params.append(f"%{paddock_name.lower()}%")
        if record_type:
            clauses.append("record_type=?")
            params.append(record_type)
        params.append(limit)
        where = "WHERE " + " AND ".join(clauses)
        with self._get_conn() as conn:
            rows = conn.execute(
                f"SELECT * FROM paddock_records {where} ORDER BY date DESC LIMIT ?", params
            ).fetchall()
        return [dict(r) for r in rows]

    # ── Herd Records ──────────────────────────────────────────────────────────

    def log_herd(
        self,
        metric: str,
        date: str = None,
        value: str = None,
        unit: str = None,
        notes: str = None,
    ) -> int:
        now = datetime.now().isoformat()
        date = date or datetime.now().date().isoformat()
        with self._get_conn() as conn:
            cur = conn.execute(
                "INSERT INTO herd_records (date, metric, value, unit, notes, created_at) "
                "VALUES (?,?,?,?,?,?)",
                (date, metric, value, unit, notes, now),
            )
            conn.commit()
            return cur.lastrowid

    def get_herd_records(
        self,
        metric: str = None,
        days_back: int = 30,
        limit: int = 20,
    ) -> List[Dict]:
        clauses = [f"date >= '{(datetime.now() - timedelta(days=days_back)).date().isoformat()}'"]
        params: List[Any] = []
        if metric:
            clauses.append("metric=?")
            params.append(metric)
        params.append(limit)
        where = "WHERE " + " AND ".join(clauses)
        with self._get_conn() as conn:
            rows = conn.execute(
                f"SELECT * FROM herd_records {where} ORDER BY date DESC LIMIT ?", params
            ).fetchall()
        return [dict(r) for r in rows]

    # ── API Usage ─────────────────────────────────────────────────────────────

    def log_api_call(
        self,
        model: str,
        input_tokens: int,
        output_tokens: int,
        cost_usd: float,
        response_time_ms: int = 0,
        purpose: str = "chat",
        session_id: Optional[str] = None,
    ) -> None:
        now = datetime.now().isoformat()
        with self._get_conn() as conn:
            conn.execute(
                """INSERT INTO api_usage
                   (timestamp, model, input_tokens, output_tokens, cost_usd,
                    response_time_ms, session_id, purpose)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (now, model, input_tokens, output_tokens, cost_usd,
                 response_time_ms, session_id, purpose),
            )
            conn.commit()

    def get_usage_summary(self, period: str = "today") -> Dict:
        now = datetime.now()
        if period == "today":
            start = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
        elif period == "this_week":
            start = (now - timedelta(days=now.weekday())).replace(
                hour=0, minute=0, second=0, microsecond=0
            ).isoformat()
        elif period == "this_month":
            start = now.replace(
                day=1, hour=0, minute=0, second=0, microsecond=0
            ).isoformat()
        else:
            start = "2000-01-01"

        with self._get_conn() as conn:
            row = conn.execute(
                """SELECT COUNT(*) as calls,
                          COALESCE(SUM(input_tokens), 0)  as input_tokens,
                          COALESCE(SUM(output_tokens), 0) as output_tokens,
                          COALESCE(SUM(cost_usd), 0)      as cost_usd,
                          COALESCE(AVG(response_time_ms), 0) as avg_response_ms
                   FROM api_usage WHERE timestamp >= ?""",
                (start,),
            ).fetchone()
        return {
            "period": period,
            "calls": row["calls"],
            "input_tokens": row["input_tokens"],
            "output_tokens": row["output_tokens"],
            "cost_usd": round(row["cost_usd"], 6),
            "avg_response_ms": round(row["avg_response_ms"]),
        }

    def get_usage_by_model(self, period: str = "this_month") -> List[Dict]:
        now = datetime.now()
        start = (
            now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()
            if period == "this_month"
            else "2000-01-01"
        )
        with self._get_conn() as conn:
            rows = conn.execute(
                """SELECT model, COUNT(*) as calls,
                          SUM(input_tokens) as input_tokens,
                          SUM(output_tokens) as output_tokens,
                          SUM(cost_usd) as cost_usd
                   FROM api_usage WHERE timestamp >= ?
                   GROUP BY model ORDER BY cost_usd DESC""",
                (start,),
            ).fetchall()
        return [dict(r) for r in rows]

    def get_daily_usage(self, days: int = 30) -> List[Dict]:
        since = (datetime.now() - timedelta(days=days)).isoformat()
        with self._get_conn() as conn:
            rows = conn.execute(
                """SELECT DATE(timestamp) as date,
                          COUNT(*) as calls,
                          SUM(input_tokens + output_tokens) as total_tokens,
                          SUM(cost_usd) as cost_usd
                   FROM api_usage WHERE timestamp >= ?
                   GROUP BY DATE(timestamp) ORDER BY date ASC""",
                (since,),
            ).fetchall()
        return [dict(r) for r in rows]

    def get_recent_api_calls(self, limit: int = 100) -> List[Dict]:
        with self._get_conn() as conn:
            rows = conn.execute(
                """SELECT timestamp, model, input_tokens, output_tokens,
                          cost_usd, response_time_ms, purpose
                   FROM api_usage ORDER BY timestamp DESC LIMIT ?""",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    # ── Command History ───────────────────────────────────────────────────────

    def log_command(
        self,
        command: str,
        output: str,
        exit_code: int,
        shell: str = "powershell",
        duration_ms: int = 0,
        triggered_by: str = "user",
    ) -> int:
        now = datetime.now().isoformat()
        success = 1 if exit_code == 0 else 0
        with self._get_conn() as conn:
            cur = conn.execute(
                """INSERT INTO command_history
                   (timestamp, command, shell, output, exit_code, success, duration_ms, triggered_by)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (now, command, shell, output[:10000], exit_code, success, duration_ms, triggered_by),
            )
            conn.commit()
            return cur.lastrowid

    def get_command_history(self, limit: int = 100) -> List[Dict]:
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM command_history ORDER BY timestamp DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    def search_commands(self, query: str) -> List[Dict]:
        with self._get_conn() as conn:
            rows = conn.execute(
                """SELECT * FROM command_history
                   WHERE LOWER(command) LIKE ? OR LOWER(output) LIKE ?
                   ORDER BY timestamp DESC LIMIT 100""",
                (f"%{query.lower()}%", f"%{query.lower()}%"),
            ).fetchall()
        return [dict(r) for r in rows]

    # ── Budget alerts ─────────────────────────────────────────────────────────

    def log_budget_alert(
        self,
        alert_type: str,
        threshold_usd: float,
        actual_usd: float,
        period: str,
    ) -> None:
        now = datetime.now().isoformat()
        with self._get_conn() as conn:
            conn.execute(
                """INSERT INTO budget_alerts
                   (timestamp, alert_type, threshold_usd, actual_usd, period)
                   VALUES (?,?,?,?,?)""",
                (now, alert_type, threshold_usd, actual_usd, period),
            )
            conn.commit()

    def get_budget_alerts(self, limit: int = 50) -> List[Dict]:
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM budget_alerts ORDER BY timestamp DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]
