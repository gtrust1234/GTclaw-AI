# GTclaw AI Assistant

A 24/7 personal AI assistant powered by **Claude AI** (Anthropic), running on your Windows PC. Chat via **Telegram** or the built-in **Dashboard GUI** — no browser, no cloud subscription needed beyond your own API keys.

---

## Features

- **Telegram integration** — chat from your phone anywhere, any time
- **Dashboard GUI** — full Windows desktop app with dark theme
  - Live chat with the same AI (conversations saved, memories shared with Telegram)
  - API usage tracking and cost monitoring
  - Task manager
  - Farm/paddock data logging (cattle, pasture records)
  - Reminder system
  - Long-term memory browser
  - Command history viewer
  - Full conversation history
  - Settings panel with API key management and Telegram setup wizard
- **7 AI tools** Claude can use automatically:
  - Run Windows shell commands
  - Set reminders
  - Manage tasks
  - Log & query farm/paddock data
  - Get live weather (Open-Meteo, no API key needed)
  - Web search (Tavily)
  - Create files to a dedicated Documents folder
- **Auto memory extraction** — Claude remembers facts about you across all sessions
- **Smart mode** — `/smart` in Telegram or checkbox in Dashboard switches to Claude Sonnet
- **No Python required** on the installed machine — fully self-contained EXEs

---

## Installation

### Quick install (recommended)

1. Download **`GTclawAI_Setup_1.1.0.exe`** from the [Releases](../../releases) page
2. Run the installer — no admin rights needed, installs to `%LocalAppData%\GTclawAI`
3. The **Dashboard** opens automatically after install
4. Go to **Settings → API Keys** and enter:
   - **Anthropic API key** — [console.anthropic.com/settings/keys](https://console.anthropic.com/settings/keys)
   - **Telegram bot token** — create a bot via [@BotFather](https://t.me/BotFather) on Telegram
   - **Your Telegram user ID** — get it from [@userinfobot](https://t.me/userinfobot)
   - **Tavily Search key** *(optional)* — [app.tavily.com](https://app.tavily.com/home)
5. Click **Save Settings** — the bot starts automatically
6. Send `/start` to your Telegram bot to confirm it's running

The Telegram **Setup Wizard** button in Settings walks you through creating a bot step-by-step if you haven't done it before.

---

## Running from source

```powershell
# Clone the repo
git clone https://github.com/gtrust1234/GTclaw-AI.git
cd GTclaw-AI

# Create venv and install dependencies
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt

# Copy and fill in your config
copy config\config.json.example config\config.json
# Edit config\config.json with your API keys

# Start the dashboard
.\.venv\Scripts\python.exe dashboard.py

# Or start just the bot service
.\.venv\Scripts\python.exe service.py debug
```

---

## Building the installer yourself

Requires Python 3.11+, PyInstaller, and [Inno Setup 6](https://jrsoftware.org/isinfo.php).

```powershell
.\build.ps1 -Installer
```

Output: `installer_output\GTclawAI_Setup_1.1.0.exe`

---

## Project structure

```
dashboard.py        # PyQt5 desktop GUI
service.py          # Telegram bot service entry point
bot.py              # Telegram message handlers
claude_client.py    # Anthropic API client with tool-use loop
memory.py           # Memory manager façade
database.py         # SQLite database (conversations, memories, tasks, farm data)
config_manager.py   # Config/settings/identity JSON management
briefing.py         # Daily briefing scheduler
build.ps1           # Build script (PyInstaller + Inno Setup)
installer.iss       # Inno Setup installer script
config/
  config.json       # API keys and paths (NOT committed — add your own)
  identity.json     # AI personality and system prompt
  settings.json     # Feature flags, budget limits, models
```

---

## Configuration files

| File | Purpose |
|------|---------|
| `config/config.json` | API keys, database path — **fill this in after install** |
| `config/identity.json` | Assistant name, personality, system prompt |
| `config/settings.json` | Models, budget limits, behaviour toggles, farm location |

---

## Requirements

- Windows 10/11 (64-bit)
- Anthropic API key ([claude.ai](https://www.anthropic.com))
- Telegram account + bot token (optional but recommended)
- Tavily API key for web search (optional, free tier available)

---

## License

MIT License — free to use, modify, and distribute.
