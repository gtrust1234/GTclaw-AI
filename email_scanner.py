"""email_scanner.py - IMAP email scanner for bill/invoice/payment and ADHD-related email detection.

Connects to any IMAP server, scans recent emails, uses Claude (Haiku) to
identify bills/invoices and ADHD-related emails needing action,
and creates reminders in the database.

Usage:
    scanner = EmailScanner(db, claude, cfg)
    notifications = await scanner.scan()
"""

import email
import imaplib
import json
import logging
from datetime import datetime, timedelta
from email.header import decode_header as _decode_hdr

logger = logging.getLogger(__name__)

# Quick subject-line filter — skip Claude call if none of these match
_BILL_KEYWORDS = [
    "invoice", "payment due", "bill ", "billing", "statement",
    "amount due", "receipt", "overdue", "direct debit",
    "subscription", "renewal", "charged", "debit notice",
    "upcoming payment", "order confirmation", "your account",
    "account summary", "reminder:", "final notice",
]

# ADHD / mental-health / medical keywords
_ADHD_KEYWORDS = [
    "adhd", "adderall", "ritalin", "concerta", "vyvanse", "strattera",
    "dexamphetamine", "methylphenidate", "lisdexamfetamine",
    "psychiatr", "therapist", "counsell", "counselor",
    "mental health", "adhd coach", "adhd support",
    "appointment", "telehealth", "upcoming visit", "follow-up", "follow up",
    "prescription", "refill", "medication review", "med check",
    "assessment", "diagnosis", "clinic", "referral",
]


def _decode_str(value: str) -> str:
    """Decode an RFC 2047 encoded email header string."""
    parts = _decode_hdr(value or "")
    result = []
    for part, charset in parts:
        if isinstance(part, bytes):
            result.append(part.decode(charset or "utf-8", errors="replace"))
        else:
            result.append(str(part))
    return " ".join(result).strip()


def _extract_text(msg: email.message.Message) -> str:
    """Return plain-text body (first 3 000 chars)."""
    chunks = []
    if msg.is_multipart():
        for part in msg.walk():
            if (
                part.get_content_type() == "text/plain"
                and "attachment" not in str(part.get("Content-Disposition", ""))
            ):
                try:
                    charset = part.get_content_charset() or "utf-8"
                    chunks.append(
                        part.get_payload(decode=True).decode(charset, errors="replace")
                    )
                except Exception:
                    pass
    else:
        try:
            charset = msg.get_content_charset() or "utf-8"
            chunks.append(
                msg.get_payload(decode=True).decode(charset, errors="replace")
            )
        except Exception:
            pass
    return "\n".join(chunks)[:3000]


class EmailScanner:
    """IMAP-based email scanner with Claude bill extraction."""

    def __init__(self, db, claude, cfg):
        self._db = db
        self._claude = claude
        self._cfg = cfg
        self._ensure_table()

    # ── DB helpers ────────────────────────────────────────────────────────────

    def _ensure_table(self):
        with self._db._get_conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS email_scan_log (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    uid        TEXT    NOT NULL,
                    account    TEXT    NOT NULL,
                    subject    TEXT,
                    scanned_at TEXT    NOT NULL,
                    action     TEXT    DEFAULT 'ignored',
                    UNIQUE(uid, account)
                )
            """)
            conn.commit()

    def _is_processed(self, uid: str, account: str) -> bool:
        with self._db._get_conn() as conn:
            row = conn.execute(
                "SELECT id FROM email_scan_log WHERE uid=? AND account=?",
                (uid, account),
            ).fetchone()
        return row is not None

    def _mark_processed(self, uid: str, account: str, subject: str, action: str):
        with self._db._get_conn() as conn:
            conn.execute(
                """INSERT OR IGNORE INTO email_scan_log
                       (uid, account, subject, scanned_at, action)
                   VALUES (?, ?, ?, ?, ?)""",
                (uid, account, subject, datetime.now().isoformat(), action),
            )
            conn.commit()

    def _add_reminder(self, message: str, remind_at: datetime):
        with self._db._get_conn() as conn:
            conn.execute(
                "INSERT INTO reminders (message, remind_at, sent, created_at) VALUES (?, ?, 0, ?)",
                (message, remind_at.isoformat(), datetime.now().isoformat()),
            )
            conn.commit()

    # ── Main scan ─────────────────────────────────────────────────────────────

    async def scan(self, query: str | None = None, days_back: int = 14) -> list[str]:
        """
        Connect via IMAP, scan emails from the last `days_back` days (default 7).
        If query is provided, uses IMAP TEXT search and a general-purpose extractor.
        Otherwise runs the default bill + ADHD keyword scan.
        Returns a list of notification strings for each item found.
        """
        cfg = self._cfg.config
        imap_server = cfg.get("email_imap_server", "").strip()
        email_addr  = cfg.get("email_address",    "").strip()
        email_pass  = cfg.get("email_password",   "").strip()

        if not imap_server or not email_addr or not email_pass:
            logger.debug("Email scan skipped — credentials not configured.")
            return []

        notifications: list[str] = []
        mail = None
        try:
            mail = imaplib.IMAP4_SSL(imap_server, 993)
            mail.login(email_addr, email_pass)
            mail.select("INBOX")

            since_date = (datetime.now() - timedelta(days=days_back)).strftime("%d-%b-%Y")

            if query:
                # Server-side search — let IMAP filter by text so we only fetch relevant emails
                safe_query = query.replace('"', '')  # strip quotes to avoid IMAP injection
                search_criteria = f'SINCE "{since_date}" TEXT "{safe_query}"'
            else:
                search_criteria = f'SINCE "{since_date}"'

            _, data = mail.search(None, search_criteria)
            uids = data[0].split() if data[0] else []
            logger.info("Email scan: %d messages in last %d days", len(uids), days_back)

            for uid in uids[-50:]:          # cap at 50 most recent
                uid_str = uid.decode()
                # Skip dedup only for automatic scans; always re-examine for explicit queries
                if not query and self._is_processed(uid_str, email_addr):
                    continue

                try:
                    _, msg_data = mail.fetch(uid, "(RFC822)")
                except Exception as e:
                    logger.warning("Fetch failed for uid %s: %s", uid_str, e)
                    continue

                if not msg_data or not msg_data[0]:
                    continue

                msg     = email.message_from_bytes(msg_data[0][1])
                subject = _decode_str(msg.get("Subject", ""))
                sender  = _decode_str(msg.get("From",    ""))
                subject_lower = subject.lower()

                if query:
                    # Custom search: send every matched email through the general extractor
                    body = _extract_text(msg)
                    result = await self._extract_general_info(subject, sender, body, query)
                    if result:
                        reminder_msg, remind_at = result
                        self._add_reminder(reminder_msg, remind_at)
                        notifications.append(reminder_msg)
                        action = "general_reminder_created"
                        logger.info("General reminder created: %s", reminder_msg)
                    else:
                        action = "not_relevant"
                    self._mark_processed(uid_str, email_addr, subject, action)
                    continue

                is_bill_match = any(kw in subject_lower for kw in _BILL_KEYWORDS)
                is_adhd_match = any(kw in subject_lower for kw in _ADHD_KEYWORDS)

                # Quick keyword check before spending a Claude call
                if not is_bill_match and not is_adhd_match:
                    self._mark_processed(uid_str, email_addr, subject, "ignored")
                    continue

                body = _extract_text(msg)
                action = "not_relevant"

                if is_bill_match:
                    result = await self._extract_bill_info(subject, sender, body)
                    if result:
                        reminder_msg, remind_at = result
                        self._add_reminder(reminder_msg, remind_at)
                        notifications.append(reminder_msg)
                        action = "bill_reminder_created"
                        logger.info("Bill reminder created: %s", reminder_msg)

                if is_adhd_match:
                    result = await self._extract_adhd_info(subject, sender, body)
                    if result:
                        reminder_msg, remind_at = result
                        self._add_reminder(reminder_msg, remind_at)
                        notifications.append(reminder_msg)
                        action = "adhd_reminder_created"
                        logger.info("ADHD reminder created: %s", reminder_msg)

                self._mark_processed(uid_str, email_addr, subject, action)

        except imaplib.IMAP4.error as e:
            logger.error("IMAP error during email scan: %s", e)
            raise
        except Exception as e:
            logger.error("Email scan failed: %s", e)
            raise
        finally:
            if mail:
                try:
                    mail.logout()
                except Exception:
                    pass

        return notifications

    # ── Claude extraction ─────────────────────────────────────────────────────

    async def _extract_bill_info(
        self, subject: str, sender: str, body: str
    ) -> tuple[str, datetime] | None:
        """
        Ask Claude Haiku to detect bill details.
        Returns (reminder_message, remind_at) or None.
        """
        today = datetime.now().strftime("%Y-%m-%d")
        prompt = f"""Today is {today}. Analyse the email below and decide if it is a bill,
invoice, payment notice, subscription renewal, or similar financial obligation.

Subject: {subject}
From: {sender}
Body:
{body[:1500]}

If this IS a financial obligation, reply with a single JSON object (no other text):
{{"is_bill": true, "description": "short label max 80 chars including amount if known", "amount": "$0.00 or null", "due_date": "YYYY-MM-DD or null", "days_before_reminder": 3}}

If it is NOT a financial obligation, reply with:
{{"is_bill": false}}

Rules:
- If due_date is unknown, use 7 days from today.
- days_before_reminder default is 3 (remind 3 days before due).
- Include the dollar amount in description when visible.
- Reply ONLY with the JSON object."""

        raw = await self._claude.quick_extract(prompt)

        # Strip markdown code fences if present
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            cleaned = "\n".join(cleaned.split("\n")[1:])
        if cleaned.endswith("```"):
            cleaned = "\n".join(cleaned.split("\n")[:-1])
        cleaned = cleaned.strip()

        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError:
            logger.debug("Bill extraction JSON parse failed: %s", raw[:200])
            return None

        if not data.get("is_bill"):
            return None

        desc        = data.get("description") or subject[:80]
        due_str     = data.get("due_date") or ""
        days_before = max(0, int(data.get("days_before_reminder") or 3))

        try:
            due_date = datetime.strptime(due_str, "%Y-%m-%d")
        except Exception:
            due_date = datetime.now() + timedelta(days=7)

        remind_at = due_date - timedelta(days=days_before)
        if remind_at < datetime.now():
            remind_at = datetime.now() + timedelta(hours=2)

        reminder_msg = f"💰 Bill due: {desc}"
        return reminder_msg, remind_at

    async def _extract_general_info(
        self, subject: str, sender: str, body: str, query: str
    ) -> tuple[str, datetime] | None:
        """
        General-purpose extractor for user-specified search queries.
        Returns (reminder_message, remind_at) or None if no action needed.
        """
        today = datetime.now().strftime("%Y-%m-%d")
        prompt = f"""Today is {today}. The user searched their inbox for: "{query}"

Email details:
Subject: {subject}
From: {sender}
Body:
{body[:1500]}

Decide if this email is relevant to the search and needs the user's attention or a reminder.

If it IS relevant and needs action or attention, reply with a single JSON object (no other text):
{{"relevant": true, "description": "short summary max 80 chars of what needs attention",
  "action_date": "YYYY-MM-DD or null", "days_before_reminder": 1,
  "type": "reply_needed|appointment|payment|information|other"}}

If it does NOT need action (already handled, automated notification, irrelevant), reply with:
{{"relevant": false}}

Rules:
- reply_needed: someone is waiting for a reply \u2192 remind in 6 hours
- appointment: has a date \u2192 remind 1 day before
- payment: bill or invoice \u2192 remind 3 days before due
- information/other: useful info \u2192 set action_date to today+1
- If action_date is unknown use today+1.
- Reply ONLY with the JSON object."""

        raw = await self._claude.quick_extract(prompt)

        cleaned = raw.strip()
        if cleaned.startswith("```"):
            cleaned = "\n".join(cleaned.split("\n")[1:])
        if cleaned.endswith("```"):
            cleaned = "\n".join(cleaned.split("\n")[:-1])
        cleaned = cleaned.strip()

        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError:
            logger.debug("General extraction JSON parse failed: %s", raw[:200])
            return None

        if not data.get("relevant"):
            return None

        desc        = data.get("description") or subject[:80]
        action_type = data.get("type", "other")
        date_str    = data.get("action_date") or ""
        days_before = max(0, int(data.get("days_before_reminder") or 1))

        try:
            action_date = datetime.strptime(date_str, "%Y-%m-%d")
        except Exception:
            action_date = datetime.now() + timedelta(days=1)

        if action_type == "reply_needed":
            remind_at = datetime.now() + timedelta(hours=6)
        else:
            remind_at = action_date - timedelta(days=days_before)
            if remind_at < datetime.now():
                remind_at = datetime.now() + timedelta(hours=2)

        icons = {"reply_needed": "📬", "appointment": "📅", "payment": "💰", "information": "📋", "other": "📧"}
        icon = icons.get(action_type, "📧")
        reminder_msg = f"{icon} {desc}"
        return reminder_msg, remind_at

    async def _extract_adhd_info(
        self, subject: str, sender: str, body: str
    ) -> tuple[str, datetime] | None:
        """
        Ask Claude Haiku to detect ADHD-related emails needing action or reply.
        Returns (reminder_message, remind_at) or None.
        """
        today = datetime.now().strftime("%Y-%m-%d")
        prompt = f"""Today is {today}. Analyse the email below and decide if it relates to ADHD,
mental health, psychiatry, therapy, ADHD coaching, medication, or medical appointments.

Subject: {subject}
From: {sender}
Body:
{body[:1500]}

If this IS an ADHD/mental-health related email that needs action or a reply, reply with a single
JSON object (no other text):
{{"is_adhd": true, "type": "appointment|medication|reply_needed|information",
  "description": "short label max 80 chars",
  "action_date": "YYYY-MM-DD or null", "days_before_reminder": 1}}

If it does NOT need action (newsletters, automated notifications you can safely ignore), reply with:
{{"is_adhd": false}}

Rules:
- appointment: has a date/time for a visit or telehealth session → remind 1 day before
- medication: prescription ready, refill due, med review → remind on action_date or today+1
- reply_needed: someone is waiting for a response → remind in 6 hours (action_date = today)
- information: useful info but no immediate action needed → is_adhd: false
- If action_date is unknown, use today for reply_needed, else today+2.
- Reply ONLY with the JSON object."""

        raw = await self._claude.quick_extract(prompt)

        cleaned = raw.strip()
        if cleaned.startswith("```"):
            cleaned = "\n".join(cleaned.split("\n")[1:])
        if cleaned.endswith("```"):
            cleaned = "\n".join(cleaned.split("\n")[:-1])
        cleaned = cleaned.strip()

        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError:
            logger.debug("ADHD extraction JSON parse failed: %s", raw[:200])
            return None

        if not data.get("is_adhd"):
            return None

        desc        = data.get("description") or subject[:80]
        action_type = data.get("type", "reply_needed")
        date_str    = data.get("action_date") or ""
        days_before = max(0, int(data.get("days_before_reminder") or 1))

        try:
            action_date = datetime.strptime(date_str, "%Y-%m-%d")
        except Exception:
            action_date = datetime.now() + timedelta(days=2)

        if action_type == "reply_needed":
            remind_at = datetime.now() + timedelta(hours=6)
        else:
            remind_at = action_date - timedelta(days=days_before)
            if remind_at < datetime.now():
                remind_at = datetime.now() + timedelta(hours=2)

        icons = {"appointment": "📅", "medication": "💊", "reply_needed": "📬", "information": "📋"}
        icon = icons.get(action_type, "🧠")
        reminder_msg = f"{icon} ADHD: {desc}"
        return reminder_msg, remind_at
