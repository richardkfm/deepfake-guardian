# Deepfake Guardian

**Open-source content moderation for group chats.** Protects communities — especially those with minors — from violence, NSFW content, sexual violence, cyberbullying, and deepfakes.

Works with **Telegram** and **WhatsApp**. More platforms planned.

---

## Table of Contents

- [What It Does](#what-it-does)
- [Quick Start](#quick-start)
- [Deepfake Detection Setup](#deepfake-detection-setup)
- [How It Works (Under the Hood)](#how-it-works-under-the-hood)
- [Configuration Reference](#configuration-reference)
- [API Reference](#api-reference)
- [GDPR & Privacy](#gdpr--privacy)
- [Running Tests](#running-tests)
- [Roadmap](#roadmap)
- [Contributing](#contributing)
- [License](#license)

---

## What It Does

A bot sits in your group chat. When someone sends a message, image, or video,
the bot checks it using **ML models** and returns one of three verdicts:

| Verdict | What happens |
|---------|-------------|
| **allow** | Nothing — content is safe |
| **flag** | Admins get notified for review |
| **delete** | Message is removed (or admins are pinged if bot lacks permissions) |

> **What are ML models?** ML (machine learning) models are pre-trained programs
> that can understand content — like recognising violent images or toxic
> language. Deepfake Guardian downloads these models automatically the first
> time they're needed. They run locally on your server, so no message content
> is sent to external services (unless you choose a cloud-based deepfake
> provider).

**Categories detected:** violence, sexual violence, NSFW, cyberbullying, deepfakes

**Who is this for?**
- Schools and class chats
- Youth organisations and sports clubs
- Companies and teams
- Any community group that needs moderation

> Use `MODERATION_PROFILE=minors_strict` for groups with children — it lowers
> all thresholds automatically.

---

## Quick Start

### What you need

- **Docker** (recommended) — or Python 3.11+ and Node.js 18+
- A **Telegram bot token** from [@BotFather](https://t.me/BotFather)
- ~4 GB disk and ~4 GB RAM (models are downloaded on demand, see below)

### 3 steps to running

```bash
# 1. Clone and copy config files
git clone https://github.com/richardkfm/deepfake-guardian.git
cd deepfake-guardian
cp engine/.env.example engine/.env
cp telegram-bot/.env.example telegram-bot/.env

# 2. Set your Telegram bot token
#    Open telegram-bot/.env and paste your token:
#    TELEGRAM_BOT_TOKEN=123456:ABC-DEF...

# 3. Start everything
docker compose up --build
```

**That's it.** Add the bot to a Telegram group, give it admin rights, and it
starts moderating.

> Without admin rights the bot will @-mention admins instead of deleting
> messages.

### About model downloads

The engine **starts immediately** — no upfront download required. ML models are
downloaded **on demand** when the first message of each type arrives:

| What triggers it | Model downloaded | Size |
|-----------------|-----------------|------|
| First **English text** message | BART language model | ~1.6 GB |
| First **German text** message | German toxic-comments model | ~500 MB |
| First **image** | NSFW detector + CLIP violence model | ~750 MB |
| Deepfake detection (if enabled) | Depends on provider | 0–50 MB |

After the first download, models are cached. Docker volumes persist the cache
across container restarts, so subsequent starts are instant.

> **Tip:** To pre-download all models before going live, send one test request
> per type after starting the engine:
> ```bash
> # Pre-download text models
> curl -X POST http://localhost:8000/moderate_text \
>   -H "Content-Type: application/json" -d '{"text": "test"}'
>
> # Pre-download image models
> curl -X POST http://localhost:8000/moderate_image \
>   -H "Content-Type: application/json" -d '{"image_url": "https://placehold.co/10x10.png"}'
> ```

### Only need one language?

Set `ENABLED_LANGUAGES=en` (or `=de`) in `engine/.env` to skip loading the
other language model entirely — saves ~500 MB–1.6 GB of RAM and disk.

### Running without Docker

```bash
# Terminal 1 — Engine
cd engine && pip install -r requirements.txt && python main.py

# Terminal 2 — Telegram bot
cd telegram-bot && pip install -r requirements.txt && python main.py

# Terminal 3 — WhatsApp bot (optional)
cd whatsapp-bot && npm install && npm run build && npm start
```

Bare-metal also needs `ffmpeg` installed (`apt install ffmpeg` or
`brew install ffmpeg`).

---

## Deepfake Detection Setup

Deepfake detection is **off by default** (`stub` mode — no models downloaded,
no API calls). To enable it, pick a provider and set the config in
`engine/.env`.

### Option A: OpenAI (easiest)

```env
DEEPFAKE_PROVIDER=openai
OPENAI_API_KEY=sk-your-key-here
```

Get a key at [platform.openai.com/api-keys](https://platform.openai.com/api-keys).
Uses GPT-4o vision. No local model download needed. Face images are sent to
OpenAI — consider GDPR implications for groups with minors.

### Option B: Ollama (free, private)

```env
DEEPFAKE_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llava
```

Install [Ollama](https://ollama.com), then `ollama pull llava`. All data stays
on your machine. No additional downloads by the engine itself.

### Option C: Local ONNX model (advanced, max privacy)

```env
DEEPFAKE_PROVIDER=local
```

Runs an EfficientNet-B0 model on CPU. Downloads a ~50 MB ONNX model on first
use. Needs ~500 MB extra RAM and the `onnxruntime`, `mediapipe`,
`opencv-python-headless` packages (already included in `requirements.txt`).
Nothing leaves the server.

### Option D: SightEngine or custom API

```env
# SightEngine
DEEPFAKE_PROVIDER=sightengine
SIGHTENGINE_API_USER=your-user
SIGHTENGINE_API_SECRET=your-secret

# Or any HTTP endpoint
DEEPFAKE_PROVIDER=api
DEEPFAKE_API_URL=https://your-api.com/detect
DEEPFAKE_API_KEY=your-key
```

---

## How It Works (Under the Hood)

### Architecture

```
┌─────────────┐                    ┌────────────────────┐
│ Telegram Bot │──── HTTP/JSON ───▶│                    │
└─────────────┘                    │  Moderation Engine │
┌──────────────┐                   │     (FastAPI)      │
│ WhatsApp Bot │──── HTTP/JSON ───▶│                    │
└──────────────┘                    └────────────────────┘
```

| Directory | Stack | Role |
|-----------|-------|------|
| `engine/` | Python 3.11, FastAPI | ML classification + verdict logic |
| `telegram-bot/` | Python, python-telegram-bot | Listens to Telegram groups |
| `whatsapp-bot/` | Node.js, TypeScript, Baileys | Listens to WhatsApp groups |

The engine is the brain. Bots are thin clients — they forward content, get a
verdict, and act on it.

### Moderation flow

1. Bot receives a message (text / image / video) in a group chat
2. Forwards content to the engine API
3. Engine auto-detects language, runs ML classifiers + pattern matchers
4. Engine returns verdict + confidence scores
5. Bot deletes, flags, or allows the message

### What models are used

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

### Language support

Auto-detects language per message. Each language has its own ML model, patterns,
and educational messages.

| Language | Pack | Model |
|----------|------|-------|
| English | `en` | `facebook/bart-large-mnli` + EN patterns |
| German | `de` | `ml6team/distilbert-base-german-cased-toxic-comments` + DE patterns |

Add a new language by creating one file in `engine/i18n/packs/`. Enable with
`ENABLED_LANGUAGES=en,de,fr`.

---

## Configuration Reference

All config lives in `.env` files. Copy from `.env.example` and edit.

### Moderation profiles

Set all thresholds at once with `MODERATION_PROFILE`:

| Profile | Violence | Sexual V. | NSFW | Deepfake | Cyberbullying | Best for |
|---------|----------|-----------|------|----------|---------------|----------|
| `minors_strict` | 0.5 | 0.3 | 0.4 | 0.6 | 0.4 | Schools, youth groups |
| `default` | 0.5 | 0.5 | 0.8 | 0.7 | 0.65 | General communities |
| `permissive` | 0.85 | 0.7 | 0.75 | 0.9 | 0.8 | Adult groups |

> **How thresholds work:** each threshold is the minimum confidence score that
> triggers an automatic deletion. A **lower value means stricter** — the engine
> deletes at lower model confidence, catching the category earlier and more
> aggressively. A higher value means the model must be very confident before
> acting, reducing false positives.

Individual `THRESHOLD_*` vars override specific values within the profile.

### Opt-in moderation categories (skills)

Beyond the always-on child-safety categories, Deepfake Guardian ships extra
**opt-in** categories defined as human-editable markdown "skills" in
`engine/moderation/skills/*.md`. They are **off by default**; enable them per
deployment:

```bash
ENABLED_CATEGORIES=advertising,political_misinformation
```

| Skill id | Detects | Notes |
|----------|---------|-------|
| `advertising` | Promotional spam, affiliate links, crypto shilling | Pattern-based |
| `political_misinformation` | Well-known hoaxes & manipulation framing | Conservative, flag-leaning; "misinformation" is contested — tune for your community |

Add or tune a category by editing/adding one markdown file — no code changes.
Each category honours a `THRESHOLD_<ID>` override (e.g. `THRESHOLD_ADVERTISING`).

### Engine — all variables

| Variable | Default | Description |
|----------|---------|-------------|
| `HOST` | `0.0.0.0` | Bind address |
| `PORT` | `8000` | Listen port |
| `LOG_LEVEL` | `info` | Logging verbosity |
| `API_KEY` | _(empty)_ | Auth key for `X-API-Key` header; empty = no auth (dev only) |
| `RATE_LIMIT` | `60/minute` | Rate limit per IP on moderation endpoints |
| `ENABLED_LANGUAGES` | `en,de` | Active language packs (controls which text models load) |
| `MODERATION_PROFILE` | `default` | Threshold profile (see above) |
| `THRESHOLD_VIOLENCE` | _from profile_ | Override violence threshold (0–1) |
| `THRESHOLD_SEXUAL_VIOLENCE` | _from profile_ | Override sexual violence threshold |
| `THRESHOLD_NSFW` | _from profile_ | Override NSFW threshold |
| `THRESHOLD_DEEPFAKE` | _from profile_ | Override deepfake threshold |
| `THRESHOLD_CYBERBULLYING` | _from profile_ | Override cyberbullying threshold |
| `ENABLED_CATEGORIES` | _(empty)_ | Opt-in moderation skills, comma-separated (e.g. `advertising,political_misinformation`) |
| `DEEPFAKE_PROVIDER` | `stub` | `openai` \| `ollama` \| `local` \| `sightengine` \| `api` \| `stub` |
| `OPENAI_API_KEY` | _(empty)_ | OpenAI key (for `openai` provider) |
| `OPENAI_MODEL` | `gpt-4o` | OpenAI vision model |
| `OPENAI_API_BASE` | `https://api.openai.com/v1` | OpenAI-compatible base URL (works with Azure, LiteLLM) |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama server (for `ollama` provider) |
| `OLLAMA_MODEL` | `llava` | Ollama vision model |
| `DEEPFAKE_MODEL_PATH` | _(auto)_ | ONNX model path (for `local` provider) |
| `SIGHTENGINE_API_USER` | _(empty)_ | SightEngine user (for `sightengine` provider) |
| `SIGHTENGINE_API_SECRET` | _(empty)_ | SightEngine secret |
| `DEEPFAKE_API_URL` | _(empty)_ | Custom endpoint (for `api` provider) |
| `DEEPFAKE_API_KEY` | _(empty)_ | Bearer token for custom API |
| `FRAME_INTERVAL` | `2.0` | Seconds between sampled video frames |
| `MAX_FRAMES` | `10` | Max frames per video |
| `MAX_VIDEO_DURATION` | `300` | Max video length in seconds |
| `DATABASE_URL` | `sqlite+aiosqlite:///./deepfake_guardian.db` | Database URL |
| `GDPR_SALT` | _(change me)_ | Secret salt for hashing user IDs |
| `DATA_RETENTION_DAYS` | `30` | Days before auto-deletion of moderation events |

### Telegram bot

| Variable | Required | Description |
|----------|----------|-------------|
| `TELEGRAM_BOT_TOKEN` | Yes | Token from @BotFather |
| `ENGINE_URL` | No | Engine URL (default: `http://engine:8000`) |
| `ENGINE_API_KEY` | No | Must match engine's `API_KEY` |
| `BOT_LANGUAGE` | No | Admin notification language: `en` or `de` |

### WhatsApp bot

| Variable | Default | Description |
|----------|---------|-------------|
| `ENGINE_URL` | `http://engine:8000` | Engine URL |

---

## API Reference

### Endpoints

```
POST /moderate_text    {"text": "...", "language": "en"}
POST /moderate_image   {"image_base64": "..." | "image_url": "..."}
POST /moderate_video   {"video_base64": "..." | "video_url": "..."}
GET  /health
```

### Response format

```json
{
  "verdict": "allow",
  "reasons": [],
  "scores": {
    "violence": 0.02,
    "sexual_violence": 0.01,
    "nsfw": 0.01,
    "deepfake_suspect": 0.0,
    "cyberbullying": 0.01
  },
  "language": "en"
}
```

### Try it

```bash
curl -s -X POST http://localhost:8000/moderate_text \
  -H "Content-Type: application/json" \
  -d '{"text": "hello world"}' | python3 -m json.tool
```

### GDPR endpoints

```
POST /gdpr/export              — export all data for a user (Article 15)
POST /gdpr/delete_request      — submit erasure request (Article 17)
GET  /gdpr/delete_request/{id} — check erasure status
```

### Warning system

```
POST /warnings/record          — record a violation, returns escalation action
GET  /warnings/{user_id_hash}  — fetch warning history
```

Escalation: 1st = educational notice, 2nd = admin notification, 3rd+ =
supervisor escalation.

---

## GDPR & Privacy

| Data | Stored? | Details |
|------|---------|---------|
| Message text / images / video | **Never** | Processed in memory, not persisted |
| Moderation verdicts + scores | Yes (metadata) | Auto-deleted after `DATA_RETENTION_DAYS` |
| User/group IDs | Yes (hashed) | SHA-256 with secret salt — not reversible |
| Warning counts | Yes | Deleted on erasure request |

**Telegram bot commands:**
- `/privacy` — shows privacy notice in the group
- `/delete_my_data` — submits an Article 17 erasure request

**Privacy notes:**
- Content is **never stored** — only an 80-char preview in debug logs (never in DB)
- User IDs are hashed before storage
- `DEEPFAKE_PROVIDER=ollama` or `local` keeps all data on your server
- `DEEPFAKE_PROVIDER=openai`, `sightengine`, or `api` sends face crops externally

---

## Running Tests

```bash
cd engine && pip install -r requirements.txt && pytest
cd telegram-bot && pip install -r requirements.txt && pytest
```

---

## Roadmap

| Phase | Focus | Status |
|-------|-------|--------|
| 1 | Tests, CI/CD, API auth, resilience | Done |
| 2 | i18n, language packs, cyberbullying | Done |
| 3 | GDPR compliance, warnings, escalation | Done |
| 4 | Deepfake detection, video analysis | Done |
| 5 | Admin dashboard, bot commands | Planned |
| 6 | WhatsApp parity, Signal, Discord | Planned |

See [ROADMAP.md](ROADMAP.md) for full details.

---

## Contributing

Contributions welcome. Open an issue before starting large changes.

**Help needed with:**
- Language packs (French, Spanish, Turkish, Arabic)
- Tests and documentation
- WhatsApp bot features

See [CLAUDE.md](CLAUDE.md) for a detailed technical guide to the codebase.

---

## License

MIT — see [LICENSE](LICENSE).
