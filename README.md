# Deepfake Guardian

**Open-source content moderation for group chats.** Protects communities —
especially those with minors — from violence, NSFW content, sexual violence,
cyberbullying, and deepfakes. Works with **Telegram** and **WhatsApp**.

**Contents:**
[What it does](#what-it-does) ·
[Quick start](#quick-start) ·
[Documentation](#documentation) ·
[Privacy](#privacy) ·
[Roadmap](#roadmap) ·
[Contributing](#contributing) ·
[License](#license)

## What it does

A bot sits in your group chat. When someone sends a message, image, or video,
the engine checks it with locally-run ML models and returns a verdict:

| Verdict | What happens |
|---------|-------------|
| **allow** | Nothing — content is safe |
| **flag** | Admins get notified for review |
| **delete** | Message is removed (or admins are pinged if the bot lacks permission) |

**Detected:** violence · sexual violence · NSFW · cyberbullying · deepfakes —
plus opt-in categories (advertising/spam, political misinformation). Each
category is a [human-editable markdown skill](docs/configuration.md#moderation-categories-skills).

**Who it's for:** schools and class chats, youth organisations and sports clubs,
companies and teams, and any community group that needs moderation. Use
`MODERATION_PROFILE=minors_strict` for groups with children to lower all
thresholds at once.

Models run **locally on your server** — no message content leaves the machine
unless you opt into a cloud-based deepfake provider.

## Quick start

You need **Docker** (or Python 3.11+ and Node.js 18+), a **Telegram bot token**
from [@BotFather](https://t.me/BotFather), and ~4 GB disk / ~4 GB RAM.

```bash
# 1. Clone and copy config files
git clone https://github.com/richardkfm/deepfake-guardian.git
cd deepfake-guardian
cp engine/.env.example engine/.env
cp telegram-bot/.env.example telegram-bot/.env

# 2. Set your token in telegram-bot/.env
#    TELEGRAM_BOT_TOKEN=123456:ABC-DEF...

# 3. Start everything
docker compose up --build
```

Add the bot to a Telegram group and give it admin rights — it starts moderating.
Without admin rights it @-mentions admins instead of deleting.

The engine starts immediately; ML models download on demand on first use and are
then cached. See [Architecture → model downloads](docs/architecture.md#model-downloads)
for pre-downloading and running without Docker.

## Documentation

| Guide | What's inside |
|-------|---------------|
| [Configuration](docs/configuration.md) | Profiles, opt-in skills, and every env var |
| [Deepfake detection](docs/deepfake-detection.md) | Enabling OpenAI / Ollama / local / API providers |
| [API reference](docs/api.md) | Moderation, GDPR, and warning endpoints |
| [Architecture](docs/architecture.md) | How it works, models, language support |
| [Privacy & GDPR](docs/privacy.md) | What's stored, retention, erasure |
| [CLAUDE.md](CLAUDE.md) | Full technical guide to the codebase |
| [ROADMAP.md](ROADMAP.md) | Phase-by-phase development plan |

## Privacy

Message content is **never stored** — only verdict metadata (auto-deleted after
`DATA_RETENTION_DAYS`) and hashed user IDs. Telegram users can run `/privacy` and
`/delete_my_data` (GDPR Article 17). Full details in
[Privacy & GDPR](docs/privacy.md).

## Roadmap

| Phase | Focus | Status |
|-------|-------|--------|
| 1 | Tests, CI/CD, API auth, resilience | Done |
| 2 | i18n, language packs, cyberbullying | Done |
| 3 | GDPR compliance, warnings, escalation | Done |
| 4 | Deepfake detection, video analysis | Done |
| 4.5 | Pluggable moderation skills (markdown categories) | Done |
| 5 | Admin dashboard, bot commands | Planned |
| 6 | WhatsApp parity, Signal, Discord | Planned |

See [ROADMAP.md](ROADMAP.md) for full details.

## Contributing

Contributions welcome — open an issue before starting large changes. Help is
especially wanted with language packs (French, Spanish, Turkish, Arabic), tests
and documentation, and WhatsApp bot features. See [CLAUDE.md](CLAUDE.md) for a
technical tour of the codebase.

Run the tests:

```bash
cd engine && pip install -r requirements.txt && pytest
cd telegram-bot && pip install -r requirements.txt && pytest
```

## License

MIT — see [LICENSE](LICENSE).
