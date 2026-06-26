# How It Works

## Architecture

```
┌──────────────┐                    ┌────────────────────┐
│ Telegram Bot │──── HTTP/JSON ───▶ │                    │
└──────────────┘                    │  Moderation Engine │
┌──────────────┐                    │     (FastAPI)      │
│ WhatsApp Bot │──── HTTP/JSON ───▶ │                    │
└──────────────┘                    └────────────────────┘
```

| Directory | Stack | Role |
|-----------|-------|------|
| `engine/` | Python 3.11, FastAPI | ML classification + verdict logic |
| `telegram-bot/` | Python, python-telegram-bot | Listens to Telegram groups |
| `whatsapp-bot/` | Node.js, TypeScript, Baileys | Listens to WhatsApp groups |

The engine is the brain. Bots are thin clients — they forward content, get a
verdict, and act on it.

## Moderation flow

1. Bot receives a message (text / image / video) in a group chat.
2. Forwards content to the engine API.
3. Engine auto-detects language, runs ML classifiers + pattern matchers.
4. Engine returns a verdict + confidence scores.
5. Bot deletes, flags, or allows the message.

## Models used

| Category | Model | Downloads on demand |
|----------|-------|---------------------|
| Violence (EN) | BART zero-shot | ~1.6 GB (shared with other EN categories) |
| Violence (DE) | German toxic model | ~500 MB (shared with other DE categories) |
| Sexual violence | Same as above | (shared) |
| NSFW (text) | Same as above | (shared) |
| NSFW (images) | Falconsai/nsfw_image_detection | ~400 MB |
| Violence (images) | CLIP zero-shot | ~350 MB |
| Cyberbullying | Language-specific patterns + ML | (shared with text model) |
| Deepfake | Depends on `DEEPFAKE_PROVIDER` | 0 MB (API) to ~50 MB (local) |
| Video | Frame extraction + above models | No extra download |

### Model downloads

The engine **starts immediately** — no upfront download. ML models download on
demand when the first message of each type arrives, then are cached (Docker
volumes persist the cache across restarts).

To pre-download before going live, send one test request per type:

```bash
# Text models
curl -X POST http://localhost:8000/moderate_text \
  -H "Content-Type: application/json" -d '{"text": "test"}'

# Image models
curl -X POST http://localhost:8000/moderate_image \
  -H "Content-Type: application/json" -d '{"image_url": "https://placehold.co/10x10.png"}'
```

Set `ENABLED_LANGUAGES=en` (or `=de`) to skip loading the other language model
entirely — saves ~500 MB–1.6 GB of RAM and disk.

## Language support

Auto-detects language per message. Each language has its own ML model, patterns,
and educational messages.

| Language | Pack | Model |
|----------|------|-------|
| English | `en` | `facebook/bart-large-mnli` + EN patterns |
| German | `de` | `ml6team/distilbert-base-german-cased-toxic-comments` + DE patterns |

Add a language by creating one file in `engine/i18n/packs/`. Enable with
`ENABLED_LANGUAGES=en,de,fr`.

## Moderation categories (skills)

Each category is a human-editable markdown file in
`engine/moderation/skills/*.md`, auto-discovered by a registry. Core
child-safety categories are always on; opt-in categories (advertising,
political misinformation) are enabled via `ENABLED_CATEGORIES`. See
[Configuration](configuration.md#moderation-categories-skills) and
[CLAUDE.md](../CLAUDE.md) for details.
