# WhatsApp Moderation Bot

Monitors WhatsApp group chats for harmful content using the moderation engine API.
Behaviour mirrors the Telegram bot.

## Features

- Connects via QR code (Baileys multi-device); reconnects with backoff
- Moderates group messages: text, captions, images, videos/GIFs, round
  videos, stickers and images/videos sent as documents — including
  **view-once** and **disappearing** messages and **edits** (editing a harmless
  message into a harmful one does not bypass moderation)
- Deletes harmful content if the bot account is a group admin; otherwise asks
  the admins to remove it. `flag` verdicts ask admins to review
- Records every violation with the engine and escalates repeat offenders
  (notice → admin notification → supervisor escalation)
- Posts at most one notice per moderated message, in the language the engine
  detected (`en`/`de`, falling back to `BOT_LANGUAGE`); admin @-mentions are
  rate-limited per group (`ADMIN_MENTION_COOLDOWN_SECONDS`)
- Media larger than `MAX_MEDIA_MB` is moderated via its embedded thumbnail
- **Fail-open:** if the engine is unreachable the message is left alone and an
  `engine_unavailable_fail_open` warning is logged
- Logs carry metadata only — never message text, media, the API key or user
  phone numbers

### Commands (GDPR)

Send the command as the whole message (`/` or `!` prefix):

| Command | Where | Purpose |
|---------|-------|---------|
| `/privacy` | group or private | Show the privacy notice |
| `/my_data` | private chat only | Summary of what is stored about you (Art. 15) |
| `/delete_my_data` | group or private | Submit an erasure request (Art. 17) |

## Setup

1. Install dependencies:
   ```bash
   cd whatsapp-bot
   npm install
   ```
2. Copy `.env.example` to `.env` and configure:
   ```bash
   cp .env.example .env
   ```
3. Build and start:
   ```bash
   npm run build
   npm start
   ```
4. Scan the QR code displayed in the terminal with WhatsApp
5. Make the bot account a group admin so it can delete messages

> **Note:** The WhatsApp account used becomes the bot. Use a dedicated number.

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `ENGINE_URL` | `http://localhost:8000` | Engine base URL (`http://engine:8000` in Docker) |
| `ENGINE_API_KEY` | *(empty)* | Must match the engine's `API_KEY` |
| `ENGINE_TIMEOUT_SECONDS` | `60` | Per-request engine timeout |
| `BOT_LANGUAGE` | `en` | Language for notices when the engine reports none, and for commands |
| `MAX_MEDIA_MB` | `20` | Larger media is moderated via its thumbnail; `0` = no limit |
| `ADMIN_MENTION_COOLDOWN_SECONDS` | `60` | Min. seconds between admin @-mentions per group; `0` = always mention |
| `SESSION_DATA_PATH` | `./auth_info` | Where the Baileys session is stored |
| `LOG_LEVEL` | `info` | Logging verbosity |

## Development

The bot is an ES module (TypeScript `NodeNext`), required by Baileys 6.7+.

```bash
npm run build   # type-check + compile to dist/
npm test        # compile tests to dist-test/ and run them with node:test
```
