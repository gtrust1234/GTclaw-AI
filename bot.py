#!/usr/bin/env python3
"""
Personal AI Assistant Bot — Windows edition
Runs 24/7, communicates via Telegram, backed by Claude + SQLite.
"""
import asyncio
import json
import logging
import os
from datetime import datetime
from pathlib import Path

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from config_manager import get_config
from memory import MemoryManager
from claude_client import ClaudeClient
from briefing import generate_briefing
from terminal_executor import execute_command
from email_scanner import EmailScanner

# ── Bootstrap config (merges .env → config.json on first run) ────────────────
cfg = get_config()

LOG_DIR = Path(cfg.get_log_dir())
LOG_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
    handlers=[
        logging.FileHandler(LOG_DIR / "bot.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)

memory = MemoryManager()
claude = ClaudeClient()
scheduler = AsyncIOScheduler()
email_scanner = EmailScanner(memory.db, claude, cfg)

# ── User files folder ─────────────────────────────────────────────────────────
import ctypes.wintypes, ctypes
_buf = ctypes.create_unicode_buffer(ctypes.wintypes.MAX_PATH)
ctypes.windll.shell32.SHGetFolderPathW(0, 5, 0, 0, _buf)  # CSIDL_PERSONAL = 5
USER_FILES_DIR = Path(_buf.value) / "GTclaw Documents"
USER_FILES_DIR.mkdir(parents=True, exist_ok=True)
logger.info(f"User files folder: {USER_FILES_DIR}")


# ── Auth ──────────────────────────────────────────────────────────────────────

def is_authorised(update: Update) -> bool:
    return update.effective_user.id == cfg.get_telegram_user_id()


# ── Commands ──────────────────────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_authorised(update):
        return
    name = cfg.identity.get("assistant_name", "Claw")
    await update.message.reply_text(
        f"👋 Hey! I'm *{name}*, your personal AI assistant.\n\n"
        "Just talk to me naturally. I remember our conversations "
        "and can run Windows commands for you.\n\n"
        "*Commands:*\n"
        "/memory — show saved memories\n"
        "/remember <fact> — save a fact\n"
        "/forget <topic> — delete matching memories\n"
        "/facts — show structured user facts\n"
        "/reminders — list pending reminders\n"
        "/emails — scan inbox for bills & payment reminders\n"
        "/cmd <command> — run a Windows command\n"
        "/usage — API usage & cost summary\n"
        "/briefing — get your daily briefing\n"
        "/smart — next message uses Sonnet (smarter)\n"
        "/clear — clear conversation history\n\n"
        "💡 *Tip:* Just say _\"remind me in 10 minutes to check the oven\"_ and I'll set it automatically!",
        parse_mode="Markdown",
    )


async def remember_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_authorised(update):
        return
    if not context.args:
        await update.message.reply_text("Usage: /remember I prefer concise responses")
        return
    fact = " ".join(context.args)
    added = memory.add_memory(fact, category="user_stated")
    if added:
        await update.message.reply_text(f"✅ Got it, I'll remember: {fact}")
    else:
        await update.message.reply_text("I already have that memory.")


async def show_memory(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_authorised(update):
        return
    memories = memory.get_all_memories()
    if not memories:
        await update.message.reply_text("No saved memories yet.")
        return
    lines = [f"• {m['content']} _({m['date']})_" for m in memories[:30]]
    await update.message.reply_text(
        "🧠 *What I remember about you:*\n\n" + "\n".join(lines),
        parse_mode="Markdown",
    )


async def show_facts(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_authorised(update):
        return
    facts = memory.get_all_facts()
    if not facts:
        await update.message.reply_text("No user facts stored yet.")
        return
    lines = [f"• *{f['key']}*: {f['value']} _({f['source']})_" for f in facts[:30]]
    await update.message.reply_text(
        "📋 *User facts:*\n\n" + "\n".join(lines), parse_mode="Markdown"
    )


async def forget_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_authorised(update):
        return
    if not context.args:
        await update.message.reply_text("Usage: /forget coffee preferences")
        return
    topic = " ".join(context.args)
    deleted = memory.delete_memory(topic)
    if deleted:
        await update.message.reply_text(f"🗑️ Deleted memories about: {topic}")
    else:
        await update.message.reply_text(f"Couldn't find memories matching: {topic}")


async def clear_history(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_authorised(update):
        return
    memory.clear_conversation_history()
    await update.message.reply_text("✅ Conversation history cleared. Memories kept.")


async def smart_mode(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_authorised(update):
        return
    context.user_data["use_smart"] = True
    await update.message.reply_text(
        "🧠 Next message will use Claude Sonnet. Just send your message."
    )


async def briefing_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_authorised(update):
        return
    await update.message.reply_text("⏳ Generating your briefing...")
    text = await generate_briefing(memory, claude)
    await update.message.reply_text(text, parse_mode="Markdown")


async def cmd_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Manually execute a Windows command via /cmd <command>."""
    if not is_authorised(update):
        return
    if not context.args:
        await update.message.reply_text(
            "Usage: /cmd <command>\nExample: /cmd Get-Date"
        )
        return
    command = " ".join(context.args)
    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id, action="typing"
    )
    result = execute_command(command, shell="powershell", triggered_by="user")
    memory.db.log_command(
        command=command,
        output=result.output,
        exit_code=result.exit_code,
        shell="powershell",
        duration_ms=result.duration_ms,
        triggered_by="user",
    )
    if result.blocked:
        await update.message.reply_text(f"🚫 Blocked: {result.stderr}")
        return
    status = "✅" if result.success else "❌"
    reply = (
        f"{status} `{command}`\n"
        f"Exit: {result.exit_code} · {result.duration_ms}ms\n\n"
        f"```\n{result.output[:3000]}\n```"
    )
    await update.message.reply_text(reply, parse_mode="Markdown")


async def usage_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show API usage and cost summary."""
    if not is_authorised(update):
        return
    db = memory.db
    today = db.get_usage_summary("today")
    month = db.get_usage_summary("this_month")
    daily_limit = cfg.settings.get("budget_daily_usd", 1.0)
    monthly_limit = cfg.settings.get("budget_monthly_usd", 20.0)

    by_model = db.get_usage_by_model("this_month")
    model_lines = "\n".join(
        f"  • {r['model']}: {r['calls']} calls — ${r['cost_usd']:.4f}"
        for r in by_model
    ) or "  No data"

    text = (
        "📊 *API Usage Summary*\n\n"
        f"*Today*\n"
        f"  Calls: {today['calls']} · Tokens: {today['input_tokens']+today['output_tokens']:,}\n"
        f"  Cost: ${today['cost_usd']:.4f} / ${daily_limit:.2f} limit\n\n"
        f"*This month*\n"
        f"  Calls: {month['calls']} · Cost: ${month['cost_usd']:.4f} / ${monthly_limit:.2f}\n\n"
        f"*By model (month):*\n{model_lines}"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


# ── Reminder commands ─────────────────────────────────────────────────────────────

async def list_reminders(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_authorised(update):
        return
    pending = memory.get_pending_reminders()
    if not pending:
        await update.message.reply_text("No pending reminders.")
        return
    lines = []
    for r in pending:
        dt_str = r["remind_at"][:16].replace("T", " ")
        recur = f" 🔁 {r['recurring']}" if r.get("recurring") else ""
        lines.append(f"• {dt_str}{recur} — {r['message']}")
    await update.message.reply_text(
        "⏰ *Pending reminders:*\n\n" + "\n".join(lines), parse_mode="Markdown"
    )


# ── Email scan command & scheduled job ───────────────────────────────────────────

async def emails_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Manually trigger an inbox scan for bills and payment notices."""
    if not is_authorised(update):
        return
    if not cfg.config.get("email_address"):
        await update.message.reply_text(
            "📧 Email monitoring is not configured.\n"
            "Open the Dashboard → Settings → Email Monitoring and enter your IMAP details.",
        )
        return
    await update.message.reply_text("📬 Scanning your inbox for bills…")
    try:
        found = await email_scanner.scan()
        if found:
            lines = "\n".join(f"• {n}" for n in found)
            await update.message.reply_text(
                f"✅ Found {len(found)} bill(s). Reminders created:\n\n{lines}",
            )
        else:
            await update.message.reply_text("✅ No new bills found in the last 7 days.")
    except Exception as exc:
        logger.error("emails_command scan error: %s", exc)
        await update.message.reply_text(
            f"❌ Scan failed: {str(exc)[:200]}\n\n"
            "Check your IMAP server, address and password in Settings.",
        )


async def email_scan_job(app: Application) -> None:
    """Scheduled email scan — sends Telegram notifications for any new bills."""
    if not cfg.config.get("email_enabled", False):
        return
    if not cfg.config.get("email_address"):
        return
    try:
        found = await email_scanner.scan()
        for notif in found:
            await app.bot.send_message(
                chat_id=cfg.get_telegram_user_id(),
                text=f"📧 *Bill detected:* {notif}",
                parse_mode="Markdown",
            )
    except Exception as exc:
        logger.error("Scheduled email scan error: %s", exc)


# ── Background reminder checker ──────────────────────────────────────────────────

async def check_reminders(app: Application) -> None:
    """Fire any due reminders and deliver them via Telegram."""
    due = memory.get_due_reminders()
    for r in due:
        try:
            await app.bot.send_message(
                chat_id=cfg.get_telegram_user_id(),
                text=f"⏰ *Reminder:* {r['message']}",
                parse_mode="Markdown",
            )
            memory.mark_reminder_sent(r["id"])
            logger.info(f"Reminder fired: {r['message']}")
        except Exception as exc:
            logger.error(f"Failed to send reminder {r['id']}: {exc}")


# ── Message handler ────────────────────────────────────────────────────────────

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_authorised(update):
        return

    user_message = update.message.text
    use_smart = context.user_data.pop("use_smart", False)

    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id, action="typing"
    )

    memories = memory.get_all_memories()
    memory_context = ""
    if memories:
        memory_context = "Facts about the user:\n" + "\n".join(
            f"- {m['content']}" for m in memories
        )

    history = memory.get_conversation_history()

    response = await claude.chat(
        message=user_message,
        history=history,
        memory_context=memory_context,
        use_smart=use_smart,
    )

    memory.add_to_history("user", user_message)
    memory.add_to_history("assistant", response)

    await _maybe_extract_memory(user_message, response)
    await _check_budget_alert(update, context)

    await update.message.reply_text(response)


async def _maybe_extract_memory(user_msg: str, assistant_msg: str) -> None:
    """Ask Claude to extract memorable facts from every message exchange."""
    if not cfg.settings.get("auto_memory_extraction", True):
        return

    prompt = (
        "Review this conversation exchange and extract ANYTHING worth saving long-term.\n"
        "This includes:\n"
        "- Facts about the user (preferences, goals, life, work, habits)\n"
        "- Instructions the user gave about how the assistant should behave\n"
        "- Identity/personality traits the user wants the assistant to have\n"
        "- Important context the assistant should always remember\n\n"
        "Return ONLY a JSON array of short factual strings, or [] if nothing is worth saving.\n\n"
        f"User: {user_msg}\n"
        f"Assistant: {assistant_msg}\n\n"
        'Format: ["fact 1", "fact 2"] or []'
    )
    raw = await claude.quick_extract(prompt)
    # Strip markdown code fences if Claude wraps the JSON
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("```")[-2] if "```" in cleaned[3:] else cleaned
        cleaned = cleaned.lstrip("json").strip().strip("`").strip()
    try:
        facts = json.loads(cleaned)
        for fact in facts:
            if isinstance(fact, str) and len(fact) > 10:
                memory.add_memory(fact, category="auto_extracted")
                logger.info(f"Memory saved: {fact[:80]}")
    except Exception as e:
        logger.debug(f"Memory extraction parse failed: {e} | raw={raw[:200]}")


async def _check_budget_alert(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Notify user if they've hit a budget limit (once per session)."""
    db = memory.db
    alerts = db.get_budget_alerts(limit=5)
    if not alerts:
        return
    latest = alerts[0]
    # Only warn once per hour per alert type
    from datetime import timezone
    alert_time = datetime.fromisoformat(latest["timestamp"])
    age_minutes = (datetime.now() - alert_time).total_seconds() / 60
    if age_minutes < 2:
        await update.message.reply_text(
            f"⚠️ Budget alert: *{latest['alert_type']}* — "
            f"spent ${latest['actual_usd']:.4f} of ${latest['threshold_usd']:.2f} "
            f"({latest['period']})",
            parse_mode="Markdown",
        )


# ── Scheduled briefing ─────────────────────────────────────────────────────────

async def scheduled_briefing(app: Application) -> None:
    try:
        text = await generate_briefing(memory, claude)
        await app.bot.send_message(
            chat_id=cfg.get_telegram_user_id(),
            text=f"🌅 *Good morning! Here's your daily briefing:*\n\n{text}",
            parse_mode="Markdown",
        )
        logger.info("Daily briefing sent.")
    except Exception as exc:
        logger.error(f"Briefing failed: {exc}")


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    token = cfg.get_telegram_token()
    user_id = cfg.get_telegram_user_id()

    if not token:
        raise ValueError("telegram_token not set in config/config.json (or TELEGRAM_TOKEN in .env)")
    if not user_id:
        raise ValueError("telegram_user_id not set in config/config.json (or YOUR_TELEGRAM_ID in .env)")

    briefing_time = cfg.get_briefing_time()
    hour, minute = briefing_time.split(":")

    async def post_init(application) -> None:
        scheduler.add_job(
            scheduled_briefing, "cron",
            hour=int(hour), minute=int(minute),
            args=[application],
        )
        scheduler.add_job(
            check_reminders, "interval",
            seconds=60,
            args=[application],
        )
        # Email scan — only add job if credentials are present
        if cfg.config.get("email_address"):
            scan_hours = int(cfg.config.get("email_scan_interval_hours", 3))
            scheduler.add_job(
                email_scan_job, "interval",
                hours=scan_hours,
                args=[application],
            )
        scheduler.start()
        logger.info(f"Bot started. Daily briefing at {briefing_time}.")

    app = (
        Application.builder()
        .token(token)
        .post_init(post_init)
        .build()
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("remember", remember_command))
    app.add_handler(CommandHandler("memory", show_memory))
    app.add_handler(CommandHandler("facts", show_facts))
    app.add_handler(CommandHandler("forget", forget_command))
    app.add_handler(CommandHandler("clear", clear_history))
    app.add_handler(CommandHandler("smart", smart_mode))
    app.add_handler(CommandHandler("briefing", briefing_command))
    app.add_handler(CommandHandler("cmd", cmd_command))
    app.add_handler(CommandHandler("usage", usage_command))
    app.add_handler(CommandHandler("reminders", list_reminders))
    app.add_handler(CommandHandler("emails", emails_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    # Python 3.12+ removed implicit event loop creation — set one explicitly.
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    main()
