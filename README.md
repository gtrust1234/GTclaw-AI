# GTclaw AI Assistant

> A 24/7 personal AI assistant that lives on your Windows PC.
> Claude is its brain. Your computer is its body. Telegram and the desktop dashboard are how it talks to you.

[**⬇ Download the latest installer**](https://github.com/gtrust1234/GTclaw-AI/releases/latest)

---

## What it is

GTclaw is a self-contained Windows app (no Python, no browser, no cloud subscription beyond your own API key). After install you get:

- A background **service** that runs your Telegram bot 24/7
- A **dashboard** desktop app for managing everything in a GUI
- A **persistent identity** for the AI — it knows who *it* is, who *you* are, and how long it has been running on your machine
- A **proactive loop** — the AI thinks on its own every ~90 minutes and can message you unprompted (e.g. *"I noticed you didn't finish that task today, want me to bump it to tomorrow?"*)

---

## What it can do

### 🧠 Memory & identity
- Remembers facts about you across every session, every channel
- Maintains its own "self-notes" — its evolving voice, opinions, preferences
- Maintains "notes about you" — your habits, interests, life events
- Heartbeat: tracks first boot, total uptime, current session — its body is your PC

### 💬 Conversation
- **Telegram** — talk to it from your phone anywhere
- **Dashboard chat** — talk to it from the desktop app
- **Code editor chat** — built-in editor with per-folder AI conversation history
- Image understanding (send photos, ask about them)
- Smart-mode toggle for switching between Haiku (fast/cheap) and Sonnet (deep)

### 🛠 Built-in tools the AI uses on its own
- Run Windows shell commands
- Set reminders for itself or for you
- Manage tasks (create, complete, postpone)
- Log & query farm/paddock data (cattle, pasture)
- Get live weather (no API key needed)
- Web search (Tavily)
- Create / edit files in a dedicated workspace
- Scan emails for bills and payment reminders (IMAP)
- Deep-dive its own memory across past chats, facts, notes
- Modify its own identity — name, voice, traits, values

### 🤖 Proactive self-reflection
Every ~90 min during waking hours the AI:
- Looks at your overdue tasks, today's tasks, pending reminders
- Reads recent conversations and notes about you
- Decides whether to do nothing, set a reminder, do research, or message you
- Quiet hours 22:00–07:00, minimum 2h gap between proactive messages
- Fully optional — turn off with `proactive_enabled=false`

### 📊 Dashboard tabs
Overview · Identity · API Usage · Conversations · Memory & Facts · Commands · Settings · Code Editor · Tasks · Reminders · Farm Data · Chat

---

## Install

1. Download `GTclawAI_Setup_x.y.z.exe` from [Releases](https://github.com/gtrust1234/GTclaw-AI/releases/latest)
2. Run the installer — no admin rights needed, installs to `%LocalAppData%\GTclawAI`
3. Dashboard opens automatically. Open **Settings** and enter:
   - **Anthropic API key** — [console.anthropic.com](https://console.anthropic.com/settings/keys)
   - **Telegram bot token** — create with [@BotFather](https://t.me/BotFather) (use the in-app **Setup Wizard** for step-by-step)
   - **Your Telegram user ID** — get from [@userinfobot](https://t.me/userinfobot)
   - **Tavily key** (optional, for web search) — [app.tavily.com](https://app.tavily.com/home)
4. The bot service auto-starts with Windows. That's it.

Your data (memories, identity, conversation history) lives in `~\assistant_data\` and survives every reinstall.

---

## Privacy & cost

- All your data stays on your PC. The only network calls are to Anthropic (Claude), Telegram, Open-Meteo (weather), and optionally Tavily (search) and your own IMAP server.
- You pay only for what Claude actually uses. The dashboard shows live cost tracking with daily/monthly budget alerts.
- Typical hobby usage: a few cents to a few dollars per day depending on how chatty you are and whether you use Sonnet.

---

## Requirements

- Windows 10 or 11
- An Anthropic API key
- A Telegram account (free) for mobile chat

---

*This repository hosts the installer and documentation. The application is distributed as a self-contained Windows executable.*
