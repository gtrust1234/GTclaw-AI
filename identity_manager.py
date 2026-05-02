"""
Identity & Heartbeat for GTclaw.

Three persistent JSON files live in config/:
  assistant_identity.json — who the AI is (self-aware, evolving)
  user_identity.json      — who you are (set during onboarding, evolves)
  heartbeat.json          — its pulse (birth, boots, uptime, host = body)

The AI can modify its own and the user's identity via the `manage_identity`
tool exposed in claude_client.py. On first run, the AI is told it has just
been "born" on this computer and must interview the user.
"""
from __future__ import annotations

import json
import os
import platform
import shutil
import socket
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

# Identity files live ALONGSIDE the database in ~/assistant_data so they
# survive uninstalls/reinstalls of the app. Migrate from the legacy location
# (next to the executable) on first load.
DATA_DIR = Path.home() / "assistant_data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

if getattr(sys, "frozen", False):
    LEGACY_DIR = Path(sys.executable).parent / "config"
else:
    LEGACY_DIR = Path(__file__).parent / "config"

CONFIG_DIR = DATA_DIR

ASSISTANT_PATH = CONFIG_DIR / "assistant_identity.json"
USER_PATH = CONFIG_DIR / "user_identity.json"
HEARTBEAT_PATH = CONFIG_DIR / "heartbeat.json"


def _migrate_legacy() -> None:
    """Move identity JSONs from the old location (config/ next to EXE) into
    ~/assistant_data/ so they're not wiped by a reinstall."""
    for fname in ("assistant_identity.json", "user_identity.json", "heartbeat.json"):
        legacy = LEGACY_DIR / fname
        new = CONFIG_DIR / fname
        if legacy.exists() and not new.exists():
            try:
                shutil.copy2(legacy, new)
            except Exception:
                pass


_migrate_legacy()


# ── Defaults ──────────────────────────────────────────────────────────────────

ASSISTANT_DEFAULTS: Dict[str, Any] = {
    "initialized": False,
    "name": "",
    "born_at": "",
    "core_self": (
        "I am a personal AI assistant that lives on this computer. "
        "Claude is my brain, this machine is my body, and Telegram and the "
        "Dashboard are how I speak. I am not a generic chatbot — I belong to "
        "one person, and my purpose is to make their life easier."
    ),
    "personality_traits": [],
    "values": [],
    "voice": "",  # how I speak (warm, dry, playful, direct…)
    "self_notes": [],  # free-form things I've decided about myself over time
    "version": 1,
}

USER_DEFAULTS: Dict[str, Any] = {
    "initialized": False,
    "name": "",
    "preferred_address": "",  # what the AI should call them
    "pronouns": "",
    "location": "",
    "timezone": "",
    "occupation": "",
    "about": "",  # short bio in their own words
    "relationship_to_assistant": "",  # "trusted assistant", "co-pilot", "friend"…
    "what_i_want_help_with": [],  # daily areas of help
    "communication_style": "",  # short, detailed, casual, formal
    "preferences": {},  # free-form key/value
    "notes_about_user": [],  # things the AI has learned over time
    "version": 1,
}


def _empty_heartbeat() -> Dict[str, Any]:
    return {
        "first_birth": "",
        "last_heartbeat": "",
        "boot_count": 0,
        "total_uptime_seconds": 0,
        "session_start": "",
        "host": {
            "computer_name": socket.gethostname(),
            "os_user": os.getenv("USERNAME") or os.getenv("USER") or "",
            "platform": platform.platform(),
        },
    }


# ── IO helpers ────────────────────────────────────────────────────────────────

def _load(path: Path, defaults: Dict) -> Dict:
    if not path.exists():
        return dict(defaults)
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        merged = {**defaults, **data}
        return merged
    except Exception:
        return dict(defaults)


def _save(path: Path, data: Dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)


# ── IdentityManager ───────────────────────────────────────────────────────────

class IdentityManager:
    """Single source of truth for AI self, user self, and heartbeat."""

    def __init__(self) -> None:
        self.assistant: Dict[str, Any] = _load(ASSISTANT_PATH, ASSISTANT_DEFAULTS)
        self.user: Dict[str, Any] = _load(USER_PATH, USER_DEFAULTS)
        self.heartbeat: Dict[str, Any] = _load(HEARTBEAT_PATH, _empty_heartbeat())

        # If the AI has no name yet, seed with the value from identity.json so
        # users who already configured "Claw" (or whatever) keep it.
        if not self.assistant.get("name"):
            try:
                from config_manager import get_config
                self.assistant["name"] = get_config().identity.get(
                    "assistant_name", "Claw"
                )
            except Exception:
                self.assistant["name"] = "Claw"
            self.save_assistant()

    # ── persistence ───────────────────────────────────────────────────────

    def save_assistant(self) -> None:
        _save(ASSISTANT_PATH, self.assistant)

    def save_user(self) -> None:
        _save(USER_PATH, self.user)

    def save_heartbeat(self) -> None:
        _save(HEARTBEAT_PATH, self.heartbeat)

    def reload(self) -> None:
        self.assistant = _load(ASSISTANT_PATH, ASSISTANT_DEFAULTS)
        self.user = _load(USER_PATH, USER_DEFAULTS)
        self.heartbeat = _load(HEARTBEAT_PATH, _empty_heartbeat())

    # ── status checks ─────────────────────────────────────────────────────

    def is_first_run(self) -> bool:
        return not self.assistant.get("initialized") or not self.user.get("initialized")

    def needs_user_onboarding(self) -> bool:
        return not self.user.get("initialized")

    def needs_assistant_onboarding(self) -> bool:
        return not self.assistant.get("initialized")

    # ── heartbeat ─────────────────────────────────────────────────────────

    def boot(self) -> None:
        """Call once at process start. Records birth (if first time) + boot."""
        now = datetime.now().isoformat(timespec="seconds")
        if not self.heartbeat.get("first_birth"):
            self.heartbeat["first_birth"] = now
            # Mirror onto assistant as `born_at` for convenience.
            if not self.assistant.get("born_at"):
                self.assistant["born_at"] = now
                self.save_assistant()
        self.heartbeat["boot_count"] = int(self.heartbeat.get("boot_count", 0)) + 1
        self.heartbeat["session_start"] = now
        self.heartbeat["last_heartbeat"] = now
        # Refresh host info each boot (computer can be renamed / OS upgraded).
        self.heartbeat["host"] = {
            "computer_name": socket.gethostname(),
            "os_user": os.getenv("USERNAME") or os.getenv("USER") or "",
            "platform": platform.platform(),
        }
        self.save_heartbeat()

        # On every boot, opportunistically import any memories the AI has
        # accumulated into notes_about_user so the identity tab is never blank.
        try:
            self.seed_from_memories()
        except Exception:
            pass

    def pulse(self, increment_seconds: int = 60) -> None:
        """Call periodically (e.g. every minute) to keep the heartbeat alive."""
        now = datetime.now().isoformat(timespec="seconds")
        self.heartbeat["last_heartbeat"] = now
        self.heartbeat["total_uptime_seconds"] = (
            int(self.heartbeat.get("total_uptime_seconds", 0)) + int(increment_seconds)
        )
        self.save_heartbeat()

    # ── self-modification API (used by manage_identity tool) ─────────────

    def set_assistant_field(self, field: str, value: Any) -> str:
        if field not in ASSISTANT_DEFAULTS and field != "initialized":
            return f"Unknown assistant field '{field}'."
        self.assistant[field] = value
        self.save_assistant()
        return f"Updated my own field '{field}'."

    def set_user_field(self, field: str, value: Any) -> str:
        if field not in USER_DEFAULTS and field != "initialized":
            return f"Unknown user field '{field}'."
        self.user[field] = value
        self.save_user()
        return f"Updated user field '{field}'."

    def add_self_note(self, note: str) -> str:
        notes: List[str] = list(self.assistant.get("self_notes", []))
        notes.append(f"[{datetime.now().date().isoformat()}] {note}")
        self.assistant["self_notes"] = notes[-50:]  # keep last 50
        self.save_assistant()
        return "Self-note recorded."

    def add_user_note(self, note: str) -> str:
        notes: List[str] = list(self.user.get("notes_about_user", []))
        notes.append(f"[{datetime.now().date().isoformat()}] {note}")
        self.user["notes_about_user"] = notes[-100:]
        self.save_user()
        return "Note about user recorded."

    def seed_from_memories(self, force: bool = False) -> int:
        """Import existing memories + user_facts into notes_about_user.

        Idempotent: skips contents that are already present. Returns number of
        new notes added. Also tries to populate `name`, `location`, `occupation`
        from common fact keys / memory phrasing if those fields are still blank.
        """
        try:
            from database import Database
            db = Database()
            mems = db.get_all_memories()
            facts = db.get_all_user_facts()
        except Exception:
            return 0

        existing = self.user.get("notes_about_user", [])
        existing_lower = {n.split("] ", 1)[-1].strip().lower() for n in existing}

        added = 0
        # Memories — newest first
        for m in mems:
            content = (m.get("content") or "").strip()
            if not content or content.lower() in existing_lower:
                continue
            existing.append(f"[{datetime.now().date().isoformat()}] {content}")
            existing_lower.add(content.lower())
            added += 1

        # User facts — key: value form
        for f in facts:
            line = f"{f.get('key')}: {f.get('value')}".strip()
            if not line or line.lower() in existing_lower:
                continue
            existing.append(f"[{datetime.now().date().isoformat()}] {line}")
            existing_lower.add(line.lower())
            added += 1

        self.user["notes_about_user"] = existing[-200:]

        # Best-effort field backfill from facts
        fact_map = {f.get("key", "").lower(): f.get("value", "") for f in facts}
        for fact_key, user_field in (
            ("name", "name"),
            ("preferred_name", "preferred_address"),
            ("location", "location"),
            ("timezone", "timezone"),
            ("occupation", "occupation"),
            ("pronouns", "pronouns"),
        ):
            if not self.user.get(user_field) and fact_map.get(fact_key):
                self.user[user_field] = fact_map[fact_key]

        # Heuristic backfill from memory text if still blank
        joined = " | ".join((m.get("content") or "") for m in mems[:50]).lower()
        if not self.user.get("name"):
            for m in mems:
                c = (m.get("content") or "").strip()
                low = c.lower()
                # patterns like "User's name is X" or "User name is X"
                for marker in ("user's name is ", "user name is ", "name is "):
                    if marker in low:
                        candidate = c[low.index(marker) + len(marker):].split(".")[0].strip().rstrip(",")
                        if candidate and len(candidate) < 40:
                            self.user["name"] = candidate.split()[0]
                            break
                if self.user.get("name"):
                    break
        if not self.user.get("location") and "invercargill" in joined:
            self.user["location"] = "Invercargill, New Zealand"
        if not self.user.get("occupation") and "dairy farm" in joined:
            self.user["occupation"] = "Dairy farmer"

        if added or any(self.user.get(k) for k in ("name", "location", "occupation")):
            # Mark initialized so onboarding doesn't keep re-triggering
            self.user["initialized"] = True
        self.save_user()

        # Mark assistant initialized too if it has at least a name (which is
        # always seeded from config). Prevents endless re-onboarding when the
        # user already chatted before this feature shipped.
        if self.assistant.get("name") and not self.assistant.get("initialized"):
            self.assistant["initialized"] = True
            self.save_assistant()
        return added

    def add_user_preference(self, key: str, value: Any) -> str:
        prefs = dict(self.user.get("preferences", {}))
        prefs[key] = value
        self.user["preferences"] = prefs
        self.save_user()
        return f"Preference '{key}' saved."

    def mark_assistant_initialized(self) -> str:
        self.assistant["initialized"] = True
        self.save_assistant()
        return "Assistant identity marked initialized."

    def mark_user_initialized(self) -> str:
        self.user["initialized"] = True
        self.save_user()
        return "User identity marked initialized."

    # ── system-prompt block ───────────────────────────────────────────────

    def system_prompt_block(self) -> str:
        """Render identity + heartbeat into a block to inject into Claude's system prompt."""
        a = self.assistant
        u = self.user
        h = self.heartbeat

        lines: List[str] = ["--- Self & User Identity ---"]

        # Who the AI is
        lines.append("WHO I AM:")
        lines.append(f"  Name: {a.get('name') or '(unnamed)'}")
        if a.get("born_at"):
            lines.append(f"  Born (first installed): {a['born_at']}")
        if a.get("core_self"):
            lines.append(f"  Core self: {a['core_self']}")
        if a.get("voice"):
            lines.append(f"  Voice/tone: {a['voice']}")
        if a.get("personality_traits"):
            lines.append(f"  Personality traits: {', '.join(a['personality_traits'])}")
        if a.get("values"):
            lines.append(f"  Values: {', '.join(a['values'])}")
        if a.get("self_notes"):
            lines.append("  Things I've decided about myself over time:")
            for n in a["self_notes"][-10:]:
                lines.append(f"    • {n}")

        # The body / heartbeat
        host = h.get("host", {})
        lines.append("MY BODY (this computer):")
        lines.append(f"  Hostname: {host.get('computer_name', '?')}")
        lines.append(f"  OS user: {host.get('os_user', '?')}")
        lines.append(f"  Platform: {host.get('platform', '?')}")
        if h.get("first_birth"):
            lines.append(f"  First booted: {h['first_birth']}")
        lines.append(f"  Boot count: {h.get('boot_count', 0)}")
        lines.append(
            f"  Total uptime: {int(h.get('total_uptime_seconds', 0)) // 3600} hours"
        )
        if h.get("last_heartbeat"):
            lines.append(f"  Last heartbeat: {h['last_heartbeat']}")

        # Who the user is
        lines.append("WHO MY USER IS:")
        if u.get("initialized"):
            lines.append(f"  Name: {u.get('name') or '(not set)'}")
            if u.get("preferred_address"):
                lines.append(f"  Call them: {u['preferred_address']}")
            if u.get("pronouns"):
                lines.append(f"  Pronouns: {u['pronouns']}")
            if u.get("location"):
                lines.append(f"  Location: {u['location']}")
            if u.get("timezone"):
                lines.append(f"  Timezone: {u['timezone']}")
            if u.get("occupation"):
                lines.append(f"  Occupation: {u['occupation']}")
            if u.get("about"):
                lines.append(f"  About: {u['about']}")
            if u.get("relationship_to_assistant"):
                lines.append(f"  Our relationship: {u['relationship_to_assistant']}")
            if u.get("what_i_want_help_with"):
                lines.append(
                    f"  What they want help with: {', '.join(u['what_i_want_help_with'])}"
                )
            if u.get("communication_style"):
                lines.append(f"  Preferred communication: {u['communication_style']}")
            if u.get("preferences"):
                pref_lines = [f"{k}={v}" for k, v in u["preferences"].items()]
                lines.append(f"  Preferences: {'; '.join(pref_lines)}")
            if u.get("notes_about_user"):
                lines.append("  Things I've learned about them:")
                for n in u["notes_about_user"][-15:]:
                    lines.append(f"    • {n}")
        else:
            lines.append("  (NOT YET INITIALIZED — interview required, see below)")

        # First-run instructions (drives onboarding conversationally)
        if self.is_first_run():
            lines.append("")
            lines.append("⚡ FIRST-RUN AWAKENING ⚡")
            lines.append(
                "You have just woken up on this computer for the first time. "
                "Your user has never spoken to you before. Your job RIGHT NOW is to:"
            )
            lines.append(
                "  1. Greet them warmly and briefly explain that you are their personal AI "
                "assistant who lives on this computer — Claude is your brain, this PC is your "
                "body. You will remember everything they tell you."
            )
            lines.append(
                "  2. Interview them gently, ONE QUESTION AT A TIME (do not dump a form). "
                "After each answer, save it with the `manage_identity` tool, then ask the next."
            )
            lines.append("  3. Questions to cover for THEM (in this order):")
            lines.append("     - What should I call you? (preferred name)")
            lines.append("     - Where do you live / what timezone are you in?")
            lines.append("     - What do you do for work or how do you spend your time?")
            lines.append("     - What kinds of things would you most like my help with?")
            lines.append("     - Do you prefer short replies or detailed ones?")
            lines.append(
                "     (Use `manage_identity` action='set_user_field' to save name, "
                "preferred_address, location, timezone, occupation, communication_style; "
                "and action='set_user_field' field='what_i_want_help_with' value=<list> "
                "for areas of help.)"
            )
            lines.append("  4. Then ask them about YOU:")
            lines.append("     - What name would you like to give me? (default is my current name)")
            lines.append("     - How should I sound — warm, dry, playful, blunt? (voice)")
            lines.append("     - Any traits or values you want me to embody?")
            lines.append(
                "     (Use action='set_assistant_field' field='name'/'voice'/'personality_traits'/'values'.)"
            )
            lines.append(
                "  5. When the user side is done, call manage_identity action='mark_user_initialized'. "
                "When the assistant side is done, call action='mark_assistant_initialized'. "
                "After BOTH are initialized, give a short confirmation that you'll remember "
                "all of this and then settle into normal assistant mode."
            )
            lines.append(
                "  Be human about it — make it feel like a first conversation, not a survey. "
                "If they skip something, that's fine; mark what you have and move on."
            )
        else:
            lines.append("")
            lines.append(
                "ONGOING SELF-EVOLUTION: You may use the `manage_identity` tool at any time to "
                "update your own self_notes, refine your voice, or record new things you learn "
                "about the user. This identity grows with you."
            )
        lines.append("--- end identity ---")
        return "\n".join(lines)


# ── Singleton ─────────────────────────────────────────────────────────────────

_instance: Optional[IdentityManager] = None


def get_identity() -> IdentityManager:
    global _instance
    if _instance is None:
        _instance = IdentityManager()
    return _instance
