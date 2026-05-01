"""
Daily briefing generator.
Generates a personalised morning briefing based on your memories,
any pending reminders, and a general summary.
"""

from datetime import datetime


async def generate_briefing(memory, claude) -> str:
    """Generate a personalised daily briefing."""

    now = datetime.now()
    date_str = now.strftime("%A, %B %d %Y")
    time_str = now.strftime("%H:%M")

    # Get memories and due reminders
    memories = memory.get_all_memories()
    due_reminders = memory.get_due_reminders()

    # Mark reminders as sent BEFORE building the briefing so check_reminders
    # can't fire the same ones again while the briefing is being generated
    for r in due_reminders:
        try:
            memory.mark_reminder_sent(r["id"])
        except Exception:
            pass

    # Build context for Claude
    memory_summary = ""
    if memories:
        memory_summary = "What you know about the user:\n" + "\n".join(
            f"- {m['content']}" for m in memories[:20]  # Cap at 20 to save tokens
        )

    reminders_text = ""
    if due_reminders:
        reminders_text = "\nPending reminders for today:\n" + "\n".join(
            f"- {r['message']}" for r in due_reminders
        )

    prompt = f"""Generate a concise, friendly morning briefing for {date_str} at {time_str}.

{memory_summary}
{reminders_text}

The briefing should:
- Start with a brief friendly greeting
- Mention any due reminders (if any)
- Include 1-2 sentences of personalised context based on what you know about them
- End with a short motivating or useful thought for the day
- Be concise — aim for under 150 words
- Use light Telegram markdown (*bold*, _italic_)

If you don't know much about the user yet, keep it general and friendly."""

    briefing = await claude.generate_text(prompt, max_tokens=300)
    return briefing
