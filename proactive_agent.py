"""
Proactive self-reflection loop.

Every N hours the assistant pauses on its own, looks at:
  • pending tasks (especially overdue ones)
  • upcoming + due reminders
  • recent conversations
  • identity notes about the user
  • how long since the last proactive ping

…then decides — without being prompted — whether to:
  • message the user (e.g. "I noticed you didn't finish X today, moved it to tomorrow")
  • set a reminder for itself or the user
  • do a web-search and save what it learned as a self-note
  • do a memory_dive
  • or stay silent

Implemented as a single async function `reflect_and_act(app)` that the bot's
APScheduler calls. All tool execution happens inside `claude.chat()`'s normal
agentic loop — the only new contract is the response format:

    Either the literal token  NO_ACTION
    or a Telegram-ready message to send to the user.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from telegram.ext import Application

logger = logging.getLogger("proactive")

_LAST_PROACTIVE: datetime | None = None
_MIN_GAP_BETWEEN_MESSAGES = timedelta(hours=2)


def _in_quiet_hours(now: datetime, start: int, end: int) -> bool:
    """True when current hour falls inside the quiet window (handles wrap)."""
    h = now.hour
    if start == end:
        return False
    if start < end:
        return start <= h < end
    return h >= start or h < end  # wraps midnight (e.g. 22 → 7)


def _build_reflection_context(memory_mod, identity) -> str:
    """Render everything the AI should consider when deciding what to do."""
    db = memory_mod.db
    now = datetime.now()
    today = now.date()

    parts: list[str] = [
        f"It is now {now.strftime('%A %Y-%m-%d %H:%M')}.",
        "",
        "You are alone with your thoughts — the user has NOT messaged you. "
        "You are doing a periodic self-reflection. Decide if anything proactive "
        "is worth doing right now. Most of the time the right answer is to do "
        "nothing — only act when there is genuine value.",
        "",
    ]

    # Pending + overdue tasks
    try:
        pending = db.get_tasks(status="pending", limit=20) or []
    except Exception:
        pending = []
    overdue = []
    today_tasks = []
    upcoming = []
    for t in pending:
        due = t.get("due_at")
        if not due:
            upcoming.append(t)
            continue
        try:
            due_dt = datetime.fromisoformat(due)
        except Exception:
            upcoming.append(t)
            continue
        if due_dt.date() < today:
            overdue.append((t, due_dt))
        elif due_dt.date() == today:
            today_tasks.append((t, due_dt))
        else:
            upcoming.append(t)

    if overdue:
        parts.append(f"⚠ OVERDUE TASKS ({len(overdue)}):")
        for t, due_dt in overdue[:10]:
            days = (today - due_dt.date()).days
            parts.append(f"  • #{t['id']} {t.get('title','')} — {days}d overdue")
    if today_tasks:
        parts.append(f"📅 DUE TODAY ({len(today_tasks)}):")
        for t, due_dt in today_tasks[:10]:
            parts.append(f"  • #{t['id']} {t.get('title','')} (due {due_dt.strftime('%H:%M')})")
    if upcoming:
        parts.append(f"🗓 UPCOMING (no specific date or future) ({len(upcoming)}):")
        for t in upcoming[:5]:
            parts.append(f"  • #{t['id']} {t.get('title','')}")
    if not (overdue or today_tasks or upcoming):
        parts.append("Tasks: (none pending)")

    # Pending reminders
    try:
        rems = db.get_pending_reminders() or []
    except Exception:
        rems = []
    if rems:
        parts.append("")
        parts.append(f"⏰ Pending reminders ({len(rems)}):")
        for r in rems[:10]:
            parts.append(f"  • {r.get('remind_at','?')} — {r.get('message','')}")

    # Recent conversation snippets (last 8 turns)
    try:
        history = memory_mod.get_conversation_history()[-12:]
    except Exception:
        history = []
    if history:
        parts.append("")
        parts.append("Recent conversation (last few turns):")
        for m in history[-12:]:
            content = str(m.get("content", ""))
            if isinstance(m.get("content"), list):
                # multimodal – flatten for context
                content = " ".join(
                    b.get("text", "[image]") if isinstance(b, dict) else str(b)
                    for b in m["content"]
                )
            snippet = content[:240].replace("\n", " ")
            parts.append(f"  {m.get('role','?')}: {snippet}")

    # Identity — who the user is and recent things you've learned
    try:
        u = identity.user
        a = identity.assistant
        parts.append("")
        parts.append(f"You are {a.get('name','the assistant')}. "
                     f"Your user is {u.get('name') or 'unnamed'}"
                     f"{(' (' + u.get('preferred_address') + ')') if u.get('preferred_address') else ''}.")
        notes = (u.get("notes_about_user") or [])[-15:]
        if notes:
            parts.append("Things you know about them recently:")
            for n in notes:
                parts.append(f"  • {n}")
        self_notes = (a.get("self_notes") or [])[-10:]
        if self_notes:
            parts.append("Your own recent self-notes:")
            for n in self_notes:
                parts.append(f"  • {n}")
    except Exception:
        pass

    # Time since last proactive
    if _LAST_PROACTIVE:
        ago = now - _LAST_PROACTIVE
        hours = int(ago.total_seconds() // 3600)
        parts.append("")
        parts.append(f"You last spoke proactively {hours}h ago.")
    else:
        parts.append("")
        parts.append("You have never spoken proactively before.")

    parts.append("")
    parts.append("--- DECISION ---")
    parts.append(
        "Decide ONE of the following:"
    )
    parts.append(
        "  A) Do nothing right now → respond with the single token: NO_ACTION"
    )
    parts.append(
        "  B) Send the user a short, useful, human message via Telegram. "
        "If so, reply with the EXACT text to send (no preamble, no NO_ACTION). "
        "Keep it short. Be the assistant they know."
    )
    parts.append(
        "You may freely call tools FIRST (set_reminder, manage_task, web_search, "
        "manage_identity, memory_dive) before deciding. For example: if a task is "
        "overdue you could call manage_task to push it to tomorrow, then message the "
        "user about it. If they mentioned they have ADHD, you could web_search for "
        "tips and add_self_note about how to support them."
    )
    parts.append(
        "Be conservative — only message if there is clear value. A good rule: "
        "if you wouldn't text a close friend about it right now, choose NO_ACTION."
    )
    return "\n".join(parts)


async def reflect_and_act(app) -> None:
    """Single proactive tick. Safe to schedule on an interval."""
    global _LAST_PROACTIVE
    # Lazy imports to avoid circulars at module load.
    from config_manager import get_config
    import bot as _bot  # noqa: WPS433 — bot owns the singletons we need

    cfg = get_config()
    if not cfg.settings.get("proactive_enabled", True):
        return

    now = datetime.now()
    quiet_start = int(cfg.settings.get("proactive_quiet_hour_start", 22))
    quiet_end = int(cfg.settings.get("proactive_quiet_hour_end", 7))
    if _in_quiet_hours(now, quiet_start, quiet_end):
        logger.debug("Proactive reflection skipped (quiet hours).")
        return

    if _LAST_PROACTIVE and (now - _LAST_PROACTIVE) < _MIN_GAP_BETWEEN_MESSAGES:
        logger.debug("Proactive reflection skipped (too soon since last).")
        return

    user_id = cfg.get_telegram_user_id()
    if not user_id:
        return

    try:
        ctx_text = _build_reflection_context(_bot.memory, _bot.identity)
    except Exception as exc:
        logger.error("Failed to build reflection context: %s", exc)
        return

    try:
        reply = await _bot.claude.chat(
            message=ctx_text,
            history=[],
            memory_context="",
            use_smart=False,
            session_id="proactive",
        )
    except Exception as exc:
        logger.error("Proactive chat call failed: %s", exc)
        return

    reply = (reply or "").strip()
    if not reply or reply.upper().startswith("NO_ACTION"):
        logger.info("Proactive tick: NO_ACTION")
        return
    if len(reply) < 4:
        return

    # Send to user via Telegram
    try:
        await app.bot.send_message(chat_id=user_id, text=reply)
        _LAST_PROACTIVE = now
        logger.info("Proactive message sent: %s", reply[:100])
        # Record what we just did so it appears in conversation history.
        try:
            _bot.memory.add_to_history("assistant", f"[proactive] {reply}")
        except Exception:
            pass
        try:
            _bot.identity.add_self_note(
                f"Reached out proactively at {now.strftime('%H:%M')}: {reply[:120]}"
            )
        except Exception:
            pass
    except Exception as exc:
        logger.error("Failed to deliver proactive message: %s", exc)
