# Configuration Reference

All config lives in `.env` files. Copy each `.env.example` to `.env` and edit.

## Moderation profiles

Set all thresholds at once with `MODERATION_PROFILE`:

| Profile | Violence | Sexual V. | NSFW | Deepfake | Cyberbullying | Best for |
|---------|----------|-----------|------|----------|---------------|----------|
| `minors_strict` | 0.5 | 0.3 | 0.4 | 0.6 | 0.4 | Schools, youth groups |
| `default` | 0.5 | 0.5 | 0.8 | 0.7 | 0.65 | General communities |
| `permissive` | 0.85 | 0.7 | 0.75 | 0.9 | 0.8 | Adult groups |

> **How thresholds work:** each threshold is the minimum confidence score that
> triggers an automatic deletion. A **lower value means stricter** — the engine
> deletes at lower model confidence, catching the category earlier. A higher
> value means the model must be very confident before acting, reducing false
> positives.

Threshold values live in the per-category skill files
(`engine/moderation/skills/*.md`); `MODERATION_PROFILE` selects which column
applies. Individual `THRESHOLD_*` vars override specific values.

## Moderation categories (skills)

Every category is a human-editable markdown "skill" in
`engine/moderation/skills/*.md` (thresholds, regex patterns, label maps, and
educational messages). Add or tune a category by editing/adding one file — no
code changes.

**Core categories** are always on: `violence`, `sexual_violence`, `nsfw`,
`deepfake_suspect`, `cyberbullying`.

**Opt-in categories** are off by default — enable per deployment:

```bash
ENABLED_CATEGORIES=advertising,political_misinformation
```

| Skill id | Detects | Notes |
|----------|---------|-------|
| `advertising` | Promotional spam, affiliate links, crypto shilling | Pattern-based |
| `political_misinformation` | Well-known hoaxes & manipulation framing | Conservative, flag-leaning; "misinformation" is contested — tune for your community |

Each category honours a `THRESHOLD_<ID>` override (e.g. `THRESHOLD_ADVERTISING`).
Opt-in scores are returned under `scores.extra` in the API response.

## Engine — all variables

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
| `ENABLED_CATEGORIES` | _(empty)_ | Opt-in moderation skills, comma-separated |
| `THRESHOLD_<ID>` | _from skill_ | Override an opt-in category threshold (e.g. `THRESHOLD_ADVERTISING`) |
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

## Telegram bot

| Variable | Required | Description |
|----------|----------|-------------|
| `TELEGRAM_BOT_TOKEN` | Yes | Token from @BotFather |
| `ENGINE_URL` | No | Engine URL (default: `http://engine:8000`) |
| `ENGINE_API_KEY` | No | Must match engine's `API_KEY` |
| `BOT_LANGUAGE` | No | Admin notification language: `en` or `de` |

## WhatsApp bot

| Variable | Default | Description |
|----------|---------|-------------|
| `ENGINE_URL` | `http://engine:8000` | Engine URL |
