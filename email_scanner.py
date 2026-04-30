"""
email_scanner.py — IMAP email scanner for bill/invoice/payment detection.

Connects to any IMAP server, scans recent emails, uses Claude (Haiku) to
identify bills/invoices, and creates reminders in the database.

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

    async def scan(self) -> list[str]:
        """
        Connect via IMAP, scan emails from the last 7 days, detect bills.
        Returns a list of notification strings for each bill found.
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

            since_date = (datetime.now() - timedelta(days=7)).strftime("%d-%b-%Y")
            _, data = mail.search(None, f'SINCE "{since_date}"')
            uids = data[0].split() if data[0] else []
            logger.info("Email scan: %d messages in last 7 days", len(uids))

            for uid in uids[-50:]:          # cap at 50 most recent
                uid_str = uid.decode()
                if self._is_processed(uid_str, email_addr):
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

                # Quick keyword check before spending a Claude call
                if not any(kw in subject.lower() for kw in _BILL_KEYWORDS):
                    self._mark_processed(uid_str, email_addr, subject, "ignored")
                    continue

                body   = _extract_text(msg)
                result = await self._extract_bill_info(subject, sender, body)

                if result:
                    reminder_msg, remind_at = result
                    self._add_reminder(reminder_msg, remind_at)
                    notifications.append(reminder_msg)
                    self._mark_processed(uid_str, email_addr, subject, "reminder_created")
                    logger.info("Bill reminder created: %s", reminder_msg)
                else:
                    self._mark_processed(uid_str, email_addr, subject, "not_a_bill")

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
