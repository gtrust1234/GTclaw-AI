# Personal AI Assistant — Setup Guide

## What This Is
A lightweight personal assistant that:
- Runs 24/7 on your Mac Mini
- You talk to via Telegram
- Remembers you persistently (SQLite, stored locally)
- Sends you a daily briefing
- Uses Claude Haiku by default (~$1-5/month), Sonnet on demand

---

## Step 1 — Get Your Telegram Bot Token

1. Open Telegram, search for **@BotFather**
2. Send `/newbot`
3. Follow the prompts (give it a name and username)
4. Copy the token it gives you — looks like `123456789:ABCdef...`

## Step 2 — Get Your Telegram User ID

1. Message **@userinfobot** on Telegram
2. It will reply with your user ID (a number like `987654321`)
3. Copy this — it's used to make sure only YOU can talk to your bot

## Step 3 — Get Your Anthropic API Key

1. Go to https://console.anthropic.com
2. Go to API Keys → Create Key
3. Copy the key (starts with `sk-ant-`)
4. Add some credit to your account (start with $5 — it'll last a long time with Haiku)

---

## Step 4 — Set Up the Project in VS Code

Open Terminal in VS Code and run these commands:

```bash
# Create the project folder in your home directory
mkdir ~/assistant
cd ~/assistant

# Copy all the project files here
# (or open this folder directly in VS Code and save files there)

# Create a virtual environment
python3 -m venv venv

# Activate it
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

## Step 5 — Configure Your .env File

```bash
# Copy the example file
cp .env.example .env

# Open it in VS Code
code .env
```

Fill in your three values:
```
TELEGRAM_TOKEN=your_token_from_botfather
YOUR_TELEGRAM_ID=your_number_from_userinfobot
ANTHROPIC_API_KEY=sk-ant-your-key
BRIEFING_TIME=08:00
```

---

## Step 6 — Test It

```bash
# Make sure your venv is active
source ~/assistant/venv/bin/activate

# Run the bot
python bot.py
```

Open Telegram and message your bot `/start` — you should get a response.

Press `Ctrl+C` to stop it for now.

---

## Step 7 — Make It Run 24/7 on Startup (launchd)

This makes your Mac Mini start the bot automatically on boot and restart it if it crashes.

```bash
# Edit the plist file first — replace YOUR_USERNAME with your actual Mac username
# Find your username with:
whoami

# Open the plist in VS Code
code ~/assistant/com.personalassistant.bot.plist
```

Replace all three instances of `YOUR_USERNAME` with your actual username, then:

```bash
# Copy the plist to the LaunchAgents folder
cp ~/assistant/com.personalassistant.bot.plist ~/Library/LaunchAgents/

# Load it (starts it now and on every login)
launchctl load ~/Library/LaunchAgents/com.personalassistant.bot.plist

# Check it's running
launchctl list | grep personalassistant
```

You should see it listed. Your bot is now running 24/7.

---

## Useful Commands

```bash
# View live logs
tail -f ~/assistant_logs/bot.log

# Stop the bot
launchctl unload ~/Library/LaunchAgents/com.personalassistant.bot.plist

# Start it again
launchctl load ~/Library/LaunchAgents/com.personalassistant.bot.plist

# Restart after making code changes
launchctl unload ~/Library/LaunchAgents/com.personalassistant.bot.plist
launchctl load ~/Library/LaunchAgents/com.personalassistant.bot.plist
```

---

## Telegram Commands

| Command | What It Does |
|---------|-------------|
| `/start` | Show help |
| `/remember I prefer short answers` | Save a fact about yourself |
| `/memory` | Show everything it remembers about you |
| `/forget coffee` | Delete memories containing "coffee" |
| `/briefing` | Get your daily briefing right now |
| `/smart` | Next message uses Sonnet (smarter) |
| `/clear` | Clear conversation history (keeps memories) |

Just talk to it naturally for everything else.

---

## Cost Estimate

- **Haiku** (default): ~$0.25 per million input tokens
- Typical personal use: 50-200 messages/day = roughly **$1-5/month**
- Daily briefing: ~$0.01 per briefing
- `/smart` (Sonnet): ~$3 per million tokens — use sparingly

To keep costs visible, check https://console.anthropic.com/usage weekly.

---

## Project Structure

```
~/assistant/
├── bot.py              # Main bot — Telegram handlers, scheduler
├── memory.py           # SQLite memory manager
├── claude_client.py    # Claude API with model routing
├── briefing.py         # Daily briefing generator
├── requirements.txt    # Python dependencies
├── .env                # Your secrets (never share this)
└── venv/               # Python virtual environment

~/assistant_data/
└── memory.db           # Your memories database (auto-created)

~/assistant_logs/
├── bot.log             # Application logs
├── stdout.log          # launchd stdout
└── stderr.log          # launchd stderr
```

---

## Adding Features Later

The system is designed to be extended. Some ideas:
- Add a `/remind me at 3pm to call John` command using the reminder system in memory.py
- Connect to your calendar via AppleScript
- Add a web search tool using the Brave Search API (free tier available)
- Route different types of questions to different models

Each feature is just a new command handler in bot.py + a new method in memory.py or a new file.
