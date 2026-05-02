"""
Identity & Heartbeat tab — view and edit who the AI is, who you are, and watch
its pulse. Mirrors the JSON files in config/ written by identity_manager.py.
"""
import json
import sys
from pathlib import Path

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import (
    QFormLayout, QGroupBox, QHBoxLayout, QInputDialog, QLabel, QLineEdit,
    QListWidget, QMessageBox, QPlainTextEdit, QPushButton, QScrollArea,
    QVBoxLayout, QWidget,
)

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from identity_manager import get_identity


def _h(text: str) -> QLabel:
    lbl = QLabel(text)
    f = QFont()
    f.setBold(True)
    lbl.setFont(f)
    return lbl


class IdentityTab(QWidget):
    """Live view of assistant identity, user identity, and heartbeat."""

    def __init__(self) -> None:
        super().__init__()
        self._ident = get_identity()
        self._build_ui()
        self._load_into_ui()

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._refresh_heartbeat)
        self._timer.start(5_000)  # heartbeat refresh every 5 s

    # ── UI ────────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 8, 8, 8)

        # Scrollable body
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        body = QWidget()
        scroll.setWidget(body)
        outer.addWidget(scroll)

        layout = QVBoxLayout(body)
        layout.setSpacing(14)

        # ── Heartbeat ─────────────────────────────────────────────────────
        hb_group = QGroupBox("💓 Heartbeat (this PC = the AI's body)")
        hb_form = QFormLayout(hb_group)
        self._hb_host = QLabel("…")
        self._hb_user = QLabel("…")
        self._hb_platform = QLabel("…")
        self._hb_birth = QLabel("…")
        self._hb_boots = QLabel("…")
        self._hb_uptime = QLabel("…")
        self._hb_last = QLabel("…")
        for lbl in (self._hb_host, self._hb_user, self._hb_platform,
                    self._hb_birth, self._hb_boots, self._hb_uptime, self._hb_last):
            lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
        hb_form.addRow("Hostname:", self._hb_host)
        hb_form.addRow("OS user:", self._hb_user)
        hb_form.addRow("Platform:", self._hb_platform)
        hb_form.addRow("First born:", self._hb_birth)
        hb_form.addRow("Boot count:", self._hb_boots)
        hb_form.addRow("Total uptime:", self._hb_uptime)
        hb_form.addRow("Last heartbeat:", self._hb_last)
        layout.addWidget(hb_group)

        # ── Assistant identity ────────────────────────────────────────────
        a_group = QGroupBox("🤖 Who the AI is (assistant_identity.json)")
        a_form = QFormLayout(a_group)

        self._a_name = QLineEdit()
        self._a_voice = QLineEdit()
        self._a_voice.setPlaceholderText("warm / dry / playful / blunt …")
        self._a_traits = QLineEdit()
        self._a_traits.setPlaceholderText("comma-separated, e.g. concise, proactive, honest")
        self._a_values = QLineEdit()
        self._a_values.setPlaceholderText("comma-separated, e.g. helpfulness, honesty")
        self._a_core = QPlainTextEdit()
        self._a_core.setFixedHeight(70)
        self._a_initialized = QLabel()

        a_form.addRow("Name:", self._a_name)
        a_form.addRow("Voice / tone:", self._a_voice)
        a_form.addRow("Traits:", self._a_traits)
        a_form.addRow("Values:", self._a_values)
        a_form.addRow("Core self:", self._a_core)
        a_form.addRow("Initialized:", self._a_initialized)

        a_form.addRow(_h("Self-notes (the AI's evolving notes about itself):"))
        self._a_notes = QListWidget()
        self._a_notes.setMaximumHeight(140)
        a_form.addRow(self._a_notes)

        a_btn_row = QHBoxLayout()
        save_a = QPushButton("💾 Save assistant identity")
        save_a.clicked.connect(self._save_assistant)
        add_self_note = QPushButton("+ Add self-note")
        add_self_note.clicked.connect(self._add_self_note)
        a_btn_row.addWidget(save_a)
        a_btn_row.addWidget(add_self_note)
        a_btn_row.addStretch()
        a_form.addRow(a_btn_row)

        layout.addWidget(a_group)

        # ── User identity ─────────────────────────────────────────────────
        u_group = QGroupBox("🧑 Who you are (user_identity.json)")
        u_form = QFormLayout(u_group)

        self._u_name = QLineEdit()
        self._u_addr = QLineEdit()
        self._u_addr.setPlaceholderText("What should I call you?")
        self._u_pronouns = QLineEdit()
        self._u_location = QLineEdit()
        self._u_tz = QLineEdit()
        self._u_tz.setPlaceholderText("e.g. Pacific/Auckland")
        self._u_occupation = QLineEdit()
        self._u_about = QPlainTextEdit()
        self._u_about.setFixedHeight(60)
        self._u_relationship = QLineEdit()
        self._u_relationship.setPlaceholderText("trusted assistant / co-pilot / friend …")
        self._u_help = QLineEdit()
        self._u_help.setPlaceholderText("comma-separated, e.g. farm logging, daily briefings")
        self._u_style = QLineEdit()
        self._u_style.setPlaceholderText("short / detailed / casual / formal")
        self._u_initialized = QLabel()

        u_form.addRow("Name:", self._u_name)
        u_form.addRow("Call you:", self._u_addr)
        u_form.addRow("Pronouns:", self._u_pronouns)
        u_form.addRow("Location:", self._u_location)
        u_form.addRow("Timezone:", self._u_tz)
        u_form.addRow("Occupation:", self._u_occupation)
        u_form.addRow("About:", self._u_about)
        u_form.addRow("Our relationship:", self._u_relationship)
        u_form.addRow("Help me with:", self._u_help)
        u_form.addRow("Comm. style:", self._u_style)
        u_form.addRow("Initialized:", self._u_initialized)

        u_form.addRow(_h("Notes the AI has learned about you:"))
        self._u_notes = QListWidget()
        self._u_notes.setMaximumHeight(160)
        u_form.addRow(self._u_notes)

        u_btn_row = QHBoxLayout()
        save_u = QPushButton("💾 Save user identity")
        save_u.clicked.connect(self._save_user)
        add_user_note = QPushButton("+ Add note about user")
        add_user_note.clicked.connect(self._add_user_note)
        u_btn_row.addWidget(save_u)
        u_btn_row.addWidget(add_user_note)
        u_btn_row.addStretch()
        u_form.addRow(u_btn_row)

        layout.addWidget(u_group)

        # ── Footer actions ────────────────────────────────────────────────
        footer = QHBoxLayout()
        reload_btn = QPushButton("🔄 Reload from disk")
        reload_btn.clicked.connect(self._reload_from_disk)
        seed_btn = QPushButton("📥 Seed from memories")
        seed_btn.setToolTip(
            "Pull every memory and user-fact the bot has accumulated into "
            "'notes about user'. Also fills in name / location / occupation if blank."
        )
        seed_btn.clicked.connect(self._seed_from_memories)
        reset_btn = QPushButton("🆕 Re-run first-time onboarding")
        reset_btn.setToolTip(
            "Marks both identities as un-initialized. Next time you message the bot, "
            "it will conduct the awakening interview again. Existing data is kept."
        )
        reset_btn.clicked.connect(self._reset_onboarding)
        footer.addWidget(reload_btn)
        footer.addWidget(seed_btn)
        footer.addWidget(reset_btn)
        footer.addStretch()
        layout.addLayout(footer)

    # ── Load / save ───────────────────────────────────────────────────────

    def _load_into_ui(self) -> None:
        self._ident.reload()
        a = self._ident.assistant
        u = self._ident.user

        self._a_name.setText(str(a.get("name") or ""))
        self._a_voice.setText(str(a.get("voice") or ""))
        self._a_traits.setText(", ".join(a.get("personality_traits") or []))
        self._a_values.setText(", ".join(a.get("values") or []))
        self._a_core.setPlainText(str(a.get("core_self") or ""))
        self._a_initialized.setText("✅ yes" if a.get("initialized") else "❌ no")
        self._a_notes.clear()
        for n in (a.get("self_notes") or [])[-25:][::-1]:
            self._a_notes.addItem(n)

        self._u_name.setText(str(u.get("name") or ""))
        self._u_addr.setText(str(u.get("preferred_address") or ""))
        self._u_pronouns.setText(str(u.get("pronouns") or ""))
        self._u_location.setText(str(u.get("location") or ""))
        self._u_tz.setText(str(u.get("timezone") or ""))
        self._u_occupation.setText(str(u.get("occupation") or ""))
        self._u_about.setPlainText(str(u.get("about") or ""))
        self._u_relationship.setText(str(u.get("relationship_to_assistant") or ""))
        self._u_help.setText(", ".join(u.get("what_i_want_help_with") or []))
        self._u_style.setText(str(u.get("communication_style") or ""))
        self._u_initialized.setText("✅ yes" if u.get("initialized") else "❌ no")
        self._u_notes.clear()
        for n in (u.get("notes_about_user") or [])[-50:][::-1]:
            self._u_notes.addItem(n)

        self._refresh_heartbeat()

    def _refresh_heartbeat(self) -> None:
        self._ident.reload()
        h = self._ident.heartbeat
        host = h.get("host") or {}
        self._hb_host.setText(host.get("computer_name") or "?")
        self._hb_user.setText(host.get("os_user") or "?")
        self._hb_platform.setText(host.get("platform") or "?")
        self._hb_birth.setText(h.get("first_birth") or "(not yet)")
        self._hb_boots.setText(str(h.get("boot_count", 0)))
        secs = int(h.get("total_uptime_seconds") or 0)
        days, rem = divmod(secs, 86_400)
        hours, rem = divmod(rem, 3_600)
        mins = rem // 60
        if days:
            self._hb_uptime.setText(f"{days}d {hours}h {mins}m")
        elif hours:
            self._hb_uptime.setText(f"{hours}h {mins}m")
        else:
            self._hb_uptime.setText(f"{mins}m")
        self._hb_last.setText(h.get("last_heartbeat") or "(not yet)")

    def _save_assistant(self) -> None:
        a = self._ident.assistant
        a["name"] = self._a_name.text().strip()
        a["voice"] = self._a_voice.text().strip()
        a["personality_traits"] = [
            t.strip() for t in self._a_traits.text().split(",") if t.strip()
        ]
        a["values"] = [v.strip() for v in self._a_values.text().split(",") if v.strip()]
        a["core_self"] = self._a_core.toPlainText().strip()
        # Saving anything from the dashboard implies initialized.
        a["initialized"] = True
        self._ident.save_assistant()
        self._a_initialized.setText("✅ yes")
        QMessageBox.information(self, "Saved", "Assistant identity saved.")

    def _save_user(self) -> None:
        u = self._ident.user
        u["name"] = self._u_name.text().strip()
        u["preferred_address"] = self._u_addr.text().strip()
        u["pronouns"] = self._u_pronouns.text().strip()
        u["location"] = self._u_location.text().strip()
        u["timezone"] = self._u_tz.text().strip()
        u["occupation"] = self._u_occupation.text().strip()
        u["about"] = self._u_about.toPlainText().strip()
        u["relationship_to_assistant"] = self._u_relationship.text().strip()
        u["what_i_want_help_with"] = [
            h.strip() for h in self._u_help.text().split(",") if h.strip()
        ]
        u["communication_style"] = self._u_style.text().strip()
        u["initialized"] = True
        self._ident.save_user()
        self._u_initialized.setText("✅ yes")
        QMessageBox.information(self, "Saved", "User identity saved.")

    def _add_self_note(self) -> None:
        text, ok = QInputDialog.getText(
            self, "Add Self-Note", "Something the AI has decided about itself:"
        )
        if ok and text.strip():
            self._ident.add_self_note(text.strip())
            self._load_into_ui()

    def _add_user_note(self) -> None:
        text, ok = QInputDialog.getText(
            self, "Add Note About User", "Something to remember about the user:"
        )
        if ok and text.strip():
            self._ident.add_user_note(text.strip())
            self._load_into_ui()

    def _reload_from_disk(self) -> None:
        self._load_into_ui()

    def _seed_from_memories(self) -> None:
        added = self._ident.seed_from_memories()
        self._load_into_ui()
        QMessageBox.information(
            self, "Seeded",
            f"Imported {added} new note(s) from memories and user-facts.\n\n"
            "Blank identity fields (name, location, occupation) were also "
            "auto-filled where possible.",
        )

    def _reset_onboarding(self) -> None:
        reply = QMessageBox.question(
            self, "Re-run onboarding?",
            "This marks both identity files as un-initialized so the next chat "
            "with the bot will trigger the first-run interview again.\n\n"
            "Your existing identity data is kept — only the 'initialized' flag flips.\n\n"
            "Continue?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        self._ident.assistant["initialized"] = False
        self._ident.user["initialized"] = False
        self._ident.save_assistant()
        self._ident.save_user()
        self._load_into_ui()
        QMessageBox.information(
            self, "Done",
            "Onboarding reset. Send any message to the bot to start the awakening.",
        )
