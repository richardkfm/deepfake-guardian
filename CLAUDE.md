# CLAUDE.md — Deepfake Guardian

This file gives Claude (and contributors) a complete orientation to the codebase.

---

## Project Purpose

Deepfake Guardian is an open-source, GDPR-first content moderation system for
group chats. It protects communities — especially those with minors (schools,
youth organisations, sports clubs) — from harmful content: violence, NSFW
material, sexual violence, and deepfakes.

**Primary target audience:** chat groups with minors
**Secondary:** community groups, organisations, companies

**Role terminology (platform-neutral):**
- **Admin** — group manager (teacher, coach, moderator)
- **Member** — group participant (student, attendee)
- **Supervisor** — higher-level oversight (principal, board member)

---

## Repository Layout

```
deepfake-guardian/
├── engine/             # Python 3.11 · FastAPI — content classification API
├── telegram-bot/       # Python · python-telegram-bot — Telegram group listener
├── whatsapp-bot/       # Node.js · TypeScript · Baileys — WhatsApp group listener
├── docker-compose.yml  # Orchestrates all three services
├── ROADMAP.md          # Phase-by-phase development plan
├── CHANGELOG.md        # Release history
└── CLAUDE.md           # This file
```

---

## Services

### `engine/` — Moderation Engine (FastAPI)

The central brain. All bots call this API to get moderation decisions.

| File | Purpose |
|------|---------|
| `main.py` | FastAPI app factory, mounts router, configures structlog |
| `routes.py` | Three POST endpoints: `/moderate_text`, `/moderate_image`, `/moderate_video` |
| `classifiers.py` | ML classifiers: text (BART zero-shot), image (CLIP zero-shot + violence), deepfake (provider-based) |
| `verdict.py` | `decide(scores)` → `"allow"` / `"flag"` / `"delete"`; evaluates core + enabled opt-in categories |
| `profiles.py` | Named threshold profiles (`minors_strict`, `default`, `permissive`) — values now sourced from the skill files |
| `moderation/` | **Moderation skills** — markdown-defined categories (`skill.py`, `loader.py`, `registry.py`, `skills/*.md`) |
| `models.py` | Pydantic request/response schemas (`ModerationResult`, `ModerationScores`) |
| `config.py` | `Settings` class — all config from env vars with sane defaults |
| `requirements.txt` | Python dependencies |
| `Dockerfile` | Container image |

**API endpoints:**
```
POST /moderate_text   {"text": "..."}
POST /moderate_image  {"image_base64": "..." | "image_url": "..."}
POST /moderate_video  {"video_base64": "..." | "video_url": "..."}
GET  /health          (health check)
```

**Response shape** (`ModerationResult`):
```json
{
  "verdict": "allow" | "flag" | "delete",
  "reasons": ["violence", "nsfw", ...],
  "scores": {
    "violence": 0.0,
    "sexual_violence": 0.0,
    "nsfw": 0.0,
    "deepfake_suspect": 0.0,
    "cyberbullying": 0.0,
    "extra": {}
  }
}
```

`scores.extra` holds scores for any enabled **opt-in** categories (see
*Moderation Skills* below); it is empty unless `ENABLED_CATEGORIES` is set.

**Verdict logic** (`verdict.py`):
- Score ≥ threshold → `"delete"` (reason added to list)
- Any score ≥ 0.4 but below threshold → `"flag"`
- Otherwise → `"allow"`

`decide()` is generic: it evaluates the five core categories plus any enabled
opt-in categories, reading each category's threshold from its skill.

**Threshold profiles** (`engine/profiles.py`):

| Profile | violence | sexual_violence | nsfw | deepfake | cyberbullying |
|---------|----------|-----------------|------|----------|---------------|
| `minors_strict` | 0.5 | 0.3 | 0.4 | 0.6 | 0.4 |
| `default` *(active)* | 0.5 | 0.5 | 0.8 | 0.7 | 0.65 |
| `permissive` | 0.85 | 0.7 | 0.75 | 0.9 | 0.8 |

Select a profile via `MODERATION_PROFILE=default` (env var). Individual
`THRESHOLD_*` env vars override a single value within the chosen profile. The
**threshold values themselves now live in the skill files**
(`engine/moderation/skills/*.md`) — `profiles.py` reads them from there. Test
thresholds are derived from the registry, so there is no longer a manual
"keep in sync" rule.

### Moderation Skills (`engine/moderation/`)

Every moderation category is a **human-editable markdown file** in
`engine/moderation/skills/<category_id>.md`. A loader parses each file into a
`ModerationSkill`, and a registry auto-discovers them (mirroring the i18n
language-pack pattern). To add or tune a category, edit/add one markdown file —
no Python changes required.

- **Core categories** (`core: true`) — always on: `violence`, `sexual_violence`,
  `nsfw`, `deepfake_suspect`, `cyberbullying`.
- **Opt-in categories** (`core: false`) — off by default, enabled per
  deployment via `ENABLED_CATEGORIES`: `advertising`, `scams`,
  `political_misinformation`, `hate_speech`, `self_harm`.

Skill file format:

```markdown
---
category_id: advertising
display_name: Advertising / Spam
core: false                 # true = always-on; false = opt-in
modalities: [text]
thresholds: { minors_strict: 0.7, default: 0.85, permissive: 0.9 }
flag_threshold: 0.4
---

## Description
What this category detects.

## Patterns (en)            # per-language; "## Patterns (de)" etc.
- weight: 0.8  `(?i)\b(buy now|use code)\b`

## Structural patterns      # language-neutral
- weight: 0.5  `(https?://\S+\s*){3,}`

## Labels (en)              # ML model-label -> internal category (ML categories)
- "hate speech" -> nsfw

## Educational message (en)
This message looks like advertising.
```

Enable opt-in categories with `ENABLED_CATEGORIES=advertising,political_misinformation`.
Each opt-in category honours a `THRESHOLD_<ID>` env override (e.g.
`THRESHOLD_ADVERTISING=0.85`). Opt-in text scores are returned in `scores.extra`.

> **Note:** `political_misinformation` ships disabled and intentionally
> conservative — "misinformation" is contested, so it only matches a small set
> of widely-debunked claims/manipulation framing and is tuned to *flag for
> human review* rather than auto-delete. Tune the patterns for your community.

### `telegram-bot/`

| File | Purpose |
|------|---------|
| `main.py` | Registers handlers for text/photo/video in group chats; acts on verdicts |
| `engine_client.py` | Async HTTP client that calls the engine API |
| `config.py` | Settings loaded from env (`TELEGRAM_BOT_TOKEN`, `ENGINE_URL`) |

Bot behaviour:
- Ignores private chats and commands (only group messages)
- `"delete"` verdict: deletes message if bot is admin, otherwise @-mentions admins
- `"flag"` verdict: always @-mentions admins

### `whatsapp-bot/`

TypeScript/Node.js bot using the Baileys library. Mirrors telegram-bot behaviour.
Lives in `src/`. See its own `README.md` for setup details.

---

## Current Limitations (Prototype State)

> These are known stubs — do **not** treat them as bugs to silently fix without
> tracking in the roadmap.

| Area | Status |
|------|--------|
| Deepfake detection | ✅ Provider-based: `openai`, `ollama`, `local` (ONNX), `sightengine`, `api`, `stub`. Default: `stub` — set a provider + API key to enable. See `engine/deepfake/` |
| Video moderation | ✅ OpenCV frame extraction + per-frame analysis. See `engine/video_processing.py` |
| Image violence score | ✅ CLIP zero-shot classifier. See `engine/classifiers.py:_get_violence_classifier()` |
| Tests | ✅ pytest suite with mocked ML models |
| CI/CD | ✅ GitHub Actions |
| API authentication | ✅ `API_KEY` middleware |
| GDPR / data persistence | ✅ Async SQLAlchemy + GDPR service |
| i18n | ✅ Language pack architecture (EN, DE) |
| Cyberbullying detection | ✅ Pattern + ML hybrid |
| Pluggable moderation categories | ✅ Markdown "skills" in `engine/moderation/skills/`; toggle via `ENABLED_CATEGORIES` |
| Advertising / spam detection | ✅ Opt-in skill — supplements, insurance, sexual services, crypto, get-rich-quick |
| Scams / phishing detection | ✅ Opt-in skill — fake prizes, advance-fee, account phishing, gift-card/crypto-wallet theft |
| Political misinformation detection | ✅ Opt-in skill (conservative, flag-leaning) — conspiracy theories + fake news; messages link fact-checkers |
| Hate speech / incitement detection | ✅ Opt-in skill — racism, dehumanising generalisations, calls for violence |
| Self-harm / ED promotion detection | ✅ Opt-in skill (flag-leaning) — messages link crisis helplines |
| Admin dashboard | Not implemented — Phase 5 |
| WhatsApp GDPR commands | Not implemented — Phase 6 |

---

## Development Roadmap

The full plan is in `ROADMAP.md`. Summary:

| Phase | Focus | Depends on |
|-------|-------|------------|
| 1 | Tests, CI/CD, API auth, resilience | — |
| 2 | i18n architecture, German + English language packs, cyberbullying | Phase 1 |
| 3 | GDPR, database, warning/escalation system | Phase 1 |
| 4 | Real deepfake detection, video frame extraction | Phase 1 |
| 5 | Admin dashboard, bot commands, educational feedback | Phase 2 + 3 |
| 6 | WhatsApp parity, Signal, Discord, community language packs | Phase 5 |

Phases 2, 3, and 4 can be developed **partially in parallel** (independent code paths).

---

## Running the Project

### With Docker (recommended)

```bash
cp engine/.env.example engine/.env
cp telegram-bot/.env.example telegram-bot/.env
cp whatsapp-bot/.env.example whatsapp-bot/.env
# Edit the .env files — at minimum set TELEGRAM_BOT_TOKEN
docker compose up --build
```

First run downloads ML models (~1.5 GB). Subsequent runs use the Docker volume cache.

### Without Docker

```bash
# Terminal 1 — Engine
cd engine && pip install -r requirements.txt && python main.py

# Terminal 2 — Telegram bot
cd telegram-bot && pip install -r requirements.txt && python main.py

# Terminal 3 — WhatsApp bot
cd whatsapp-bot && npm install && npm run build && npm start
```

### Manual engine test

```bash
curl -X POST http://localhost:8000/moderate_text \
  -H "Content-Type: application/json" \
  -d '{"text": "hello world"}'
```

---

## Environment Variables

### Engine (`engine/.env`)

| Variable | Default | Description |
|----------|---------|-------------|
| `HOST` | `0.0.0.0` | Bind address |
| `PORT` | `8000` | Listen port |
| `LOG_LEVEL` | `info` | Logging verbosity |
| `MODERATION_PROFILE` | `default` | Threshold profile (`minors_strict` / `default` / `permissive`) |
| `THRESHOLD_VIOLENCE` | `0.5` | Override delete threshold for violence (0–1) |
| `THRESHOLD_SEXUAL_VIOLENCE` | `0.5` | Override delete threshold for sexual violence |
| `THRESHOLD_NSFW` | `0.8` | Override delete threshold for NSFW |
| `THRESHOLD_DEEPFAKE` | `0.7` | Override delete threshold for deepfake |
| `THRESHOLD_CYBERBULLYING` | `0.65` | Override delete threshold for cyberbullying |
| `ENABLED_CATEGORIES` | *(empty)* | Comma-separated opt-in moderation skills (e.g. `advertising,political_misinformation`) |
| `THRESHOLD_<ID>` | *(skill default)* | Override delete threshold for an opt-in category (e.g. `THRESHOLD_ADVERTISING`) |

### Telegram bot (`telegram-bot/.env`)

| Variable | Default | Description |
|----------|---------|-------------|
| `TELEGRAM_BOT_TOKEN` | — | **Required.** Token from @BotFather |
| `ENGINE_URL` | `http://engine:8000` | Engine base URL |

### WhatsApp bot (`whatsapp-bot/.env`)

| Variable | Default | Description |
|----------|---------|-------------|
| `ENGINE_URL` | `http://engine:8000` | Engine base URL |

---

## Code Conventions

- **Python:** `from __future__ import annotations` at the top of every file; Pydantic v2 models; structlog for structured logging; async handlers where IO is involved.
- **TypeScript:** strict mode, ESM modules.
- **Secrets:** never commit `.env` files — only `.env.example` templates.
- **No message content stored** — the engine only processes and returns scores; nothing is persisted (until Phase 3 adds GDPR-compliant audit logs, which store *metadata* only, never message text).

---

## Key Architectural Decisions

1. **Engine is the single source of truth** for moderation logic. Bots are thin clients — they only forward content and act on verdicts.
2. **Skill-defined categories & thresholds**: each moderation category is a human-editable markdown file in `engine/moderation/skills/*.md` (thresholds, patterns, label maps, messages). A registry auto-discovers them. Three named profiles (`minors_strict`, `default`, `permissive`) select which threshold column applies via `MODERATION_PROFILE`; `THRESHOLD_*` env vars override individual values. Core categories are always on; opt-in categories are enabled via `ENABLED_CATEGORIES`. Tests derive thresholds from the registry, so no manual sync is needed.
3. **i18n-first architecture** (Phase 2): language detection → language pack → language-specific ML model + patterns + support resources. Adding a new language = one new Python file.
4. **GDPR-first** (Phase 3): user IDs are hashed before storage; message content is never persisted; auto-deletion after 30 days; full Article 17 (right to erasure) support.
5. **Telegram has higher priority** than WhatsApp — it uses the official Bot API and is simpler to develop against.

---

## Contributing a Language Pack (planned — Phase 2+)

Once the i18n architecture is in place, adding a language pack requires only:

```python
# engine/i18n/packs/fr.py
from engine.i18n.base import LanguagePack

class FrenchPack(LanguagePack):
    lang_code = "fr"
    lang_name = "Français"

    def detect(self, text: str) -> float: ...
    def get_classifier(self): ...
    def get_patterns(self) -> list: ...
    def get_labels(self) -> dict: ...
    def get_educational_messages(self) -> dict: ...
    def get_helplines(self) -> list: ...
```

The registry auto-discovers all `LanguagePack` subclasses. Enable via `ENABLED_LANGUAGES=de,en,fr`.

---

## Versioning & Changelog Guidelines

This project uses [Semantic Versioning](https://semver.org/) (`MAJOR.MINOR.PATCH`).

| Change type | Version bump | Examples |
|-------------|-------------|---------|
| Breaking API or behaviour change | `MAJOR` (1.0.0 → 2.0.0) | Removing an endpoint, changing response schema |
| New feature or capability | `MINOR` (0.1.0 → 0.2.0) | New moderation category, new bot command, new phase shipped |
| Docs, wording, refactors, renames, minor fixes | `PATCH` (0.0.1 → 0.0.2) | Translating docs, renaming terminology, fixing a typo, adjusting a threshold default |

**Rule of thumb:** if nothing in the running system behaves differently, it is a
`PATCH`. Neutral role terminology changes, README rewrites, roadmap updates, and
translation-only commits are all `PATCH` bumps — not `MINOR`.

---

## Security Notes

- The engine currently has **no authentication**. Phase 1 adds an `API_KEY` middleware.
- Do not expose the engine port (8000) publicly without auth.
- The WhatsApp bot uses an unofficial API (Baileys) — account bans are possible with aggressive usage.
- Content sent to the engine is processed in-memory and not logged (only metadata: verdict, reasons, text preview capped at 80 chars).
