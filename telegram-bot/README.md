# Telegram Moderation Bot

Monitors group chats for harmful content using the moderation engine API.

## Features

- Moderates group messages: text, captions, photos, videos, GIFs/animations,
  video notes, stickers and images/videos sent as files — **including edited
  messages** (posting something harmless and editing it later does not bypass
  moderation)
- Deletes harmful content if the bot is an admin with the *Delete messages* right
- Otherwise asks the group admins to remove it; `flag` verdicts ask admins to review
- Records every violation with the engine and escalates repeat offenders
  (notice → admin notification → supervisor escalation)
- Posts at most one notice per moderated message; admin @-mentions are
  rate-limited per chat (`ADMIN_MENTION_COOLDOWN_SECONDS`)
- Media larger than `MAX_MEDIA_MB` (the Bot API cannot download more than
  20 MB) is moderated via its thumbnail instead
- **Fail-open:** if the engine is unreachable the message is left alone and an
  `engine_unavailable_fail_open` warning is logged
- Logs carry metadata only (chat/message IDs, verdicts, reasons) — never
  message text, media or raw user IDs

### Commands (GDPR)

| Command | Where | Purpose |
|---------|-------|---------|
| `/privacy` | group or private | Show the privacy notice |
| `/my_data` | private chat only | Summary of what is stored about you (Art. 15) |
| `/delete_my_data` | group or private | Submit an erasure request (Art. 17) |

Command replies use the user's Telegram language if a message file exists for
it (`i18n/*.json`), otherwise `BOT_LANGUAGE`.

## Setup

1. Create a bot via [@BotFather](https://t.me/BotFather)
2. **Let the bot see group messages:** either make it a group admin, or disable
   privacy mode in BotFather (`/setprivacy` → *Disable*). With privacy mode on,
   a non-admin bot only receives commands and never sees normal messages.
3. Copy `.env.example` to `.env` and fill in your bot token
4. Add the bot to your group and make it an admin with the *Delete messages*
   right (for auto-deletion)

```bash
cd telegram-bot
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# edit .env with your bot token
python main.py
```

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `TELEGRAM_BOT_TOKEN` | — | **Required.** Token from @BotFather |
| `ENGINE_URL` | `http://localhost:8000` | Engine base URL (`http://engine:8000` in Docker) |
| `ENGINE_API_KEY` | *(empty)* | Must match the engine's `API_KEY` |
| `ENGINE_TIMEOUT_SECONDS` | `60` | Per-request engine timeout |
| `BOT_LANGUAGE` | `en` | Language for group notices when the engine reports none |
| `MAX_MEDIA_MB` | `20` | Larger media is moderated via its thumbnail; `0` = no limit (local Bot API server) |
| `ADMIN_MENTION_COOLDOWN_SECONDS` | `60` | Min. seconds between admin @-mentions per chat; `0` = always mention |
| `LOG_LEVEL` | `info` | Logging verbosity |

## Tests

```bash
pip install -r requirements.txt ruff
ruff check . && pytest
```
