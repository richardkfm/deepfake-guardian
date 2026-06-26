# Changelog

All notable changes to Deepfake Guardian are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and [Semantic Versioning](https://semver.org/) (`MAJOR.MINOR.PATCH`).

- `PATCH` bump (0.0.x) — docs, wording, renames, translations, minor fixes; nothing in the running system changes.
- `MINOR` bump (0.x.0) — new feature or capability added.
- `MAJOR` bump (x.0.0) — breaking change to API or behaviour.

---

## [Unreleased]

### Added
- `CLAUDE.md` — full technical orientation for Claude and contributors: architecture,
  file-level descriptions, current limitations, roadmap summary, env variable reference,
  code conventions, and security notes.
- `CHANGELOG.md` — this file.

---

## [0.6.0] — 2026-06-26 — Moderation Skills: pluggable, human-editable categories

### Added

**Engine — Moderation skill system (`engine/moderation/`):**
- `engine/moderation/skill.py` — `ModerationSkill` dataclass: thresholds (per
  profile), regex patterns, label maps, educational messages, and per-category
  threshold/flag resolution.
- `engine/moderation/loader.py` — parses a human-editable markdown skill file
  (YAML frontmatter + `## Patterns (en)` / `## Labels (en)` / `## Educational
  message (en)` sections) into a `ModerationSkill`.
- `engine/moderation/registry.py` — auto-discovers every `skills/*.md` file
  (mirrors `i18n.registry.LanguageRegistry`); serves core vs. opt-in skills,
  aggregates patterns/labels/messages per language, and scores opt-in text
  categories.
- `engine/moderation/skills/*.md` — the five core child-safety categories
  (violence, sexual_violence, nsfw, deepfake, cyberbullying) plus two new
  **opt-in** categories: **advertising/spam** and **political_misinformation**.
  These markdown files are now the single, human-editable source of truth for
  thresholds, patterns, label maps, and educational messages.
- New `ENABLED_CATEGORIES` env var (comma-separated skill ids) turns opt-in
  categories on; each honours a `THRESHOLD_<ID>` override. Core categories stay
  always-on.
- `ModerationScores.extra: dict[str, float]` carries opt-in category scores in
  the API response.
- Tests: `test_skill_loader.py`, `test_moderation_registry.py`,
  `test_advertising.py`, `test_political_misinformation.py`, plus opt-in cases
  in `test_verdict.py`.

### Changed
- `engine/profiles.py` — threshold values now sourced from the core skill files
  (`get_profile()` assembles a `ThresholdProfile` from the registry, with a
  defensive fallback). Profile names and the public `ThresholdProfile` API are
  unchanged.
- `engine/verdict.py` — `decide()` is now generic: it evaluates the core
  categories plus any enabled opt-in categories, instead of a hardcoded list.
- `engine/i18n/packs/{en,de}.py` — `get_patterns()`, `get_labels()`, and
  `get_educational_messages()` now delegate to the skill registry (single source
  of truth); `detect()`, `get_classifier()`, and `get_helplines()` unchanged.
- `engine/routes.py` — `/moderate_text` populates `scores.extra` from enabled
  opt-in text categories; audit logging includes them.
- `engine/requirements.txt` — added `PyYAML` for skill-file parsing.

> Note: the bots require **no changes** — they already treat moderation
> `reasons` as an opaque list of strings.

### Changed
- `engine/profiles.py` — rebalanced `default` profile thresholds by detection
  priority: violence and sexual violence at `0.5` (highest — deleted at lowest
  confidence); cyberbullying at `0.65`; deepfake at `0.7`; NSFW at `0.8` (lowest
  priority — only deleted at high confidence).
- `README.md` — rewritten in English as the primary repository language; added
  moderation category status table, known limitations section, target audience
  section, contributing guidance, and security & privacy notes.
- `ROADMAP.md` — translated from German to English; all section headings, descriptions,
  design principles, verification criteria, and commentary are now in English.

---

## [0.5.0] — 2026-03-23 — Phase 4: Deepfake Detection & Video Analysis

### Added

**Engine — Deepfake Detection Provider System (`engine/deepfake/`):**
- `engine/deepfake/base.py` — `DeepfakeDetector` ABC with `detect(face_images) -> list[float]`
  and `is_available() -> bool` interface.
- `engine/deepfake/factory.py` — factory function returning cached singleton detector.
  Reads `DEEPFAKE_PROVIDER` env var (`local` | `sightengine` | `api` | `stub`).
  Falls back to stub with warning when chosen provider is unavailable.
  `StubDetector` built in for CI/testing (returns 0.05).
- `engine/deepfake/face_extractor.py` — shared face extraction using MediaPipe
  `FaceDetection`. Returns list of cropped face PIL images with configurable
  minimum face size and padding.
- `engine/deepfake/local_detector.py` — `LocalOnnxDetector`: runs EfficientNet-B0
  ONNX model (~20 MB) on CPU via `onnxruntime`. Privacy-first default — face
  images never leave the server. ImageNet normalisation, sigmoid output.
- `engine/deepfake/cloud_sightengine.py` — `SightEngineDetector`: calls SightEngine
  deepfake API. GDPR warning logged on startup. Requires `SIGHTENGINE_API_USER`
  and `SIGHTENGINE_API_SECRET`.
- `engine/deepfake/cloud_generic.py` — `GenericApiDetector`: sends face crops as
  base64 to a user-configured HTTP endpoint. Supports custom score path extraction.

**Engine — Video Processing (`engine/video_processing.py`):**
- `decode_video(video_base64, video_url)` — decode/download video data.
- `extract_frames(video_data)` — OpenCV-based frame sampling: 1 frame every
  `FRAME_INTERVAL` seconds (default 2.0), capped at `MAX_FRAMES` (default 10),
  rejects videos longer than `MAX_VIDEO_DURATION` (default 300s). Temp files
  cleaned up in `finally` block.
- `moderate_video_frames(frames)` — runs `classify_image` + `detect_deepfake_suspect`
  on each frame, aggregates via max per category.

**Engine — Image Violence Detection:**
- `_get_violence_classifier()` — CLIP zero-shot classifier (`openai/clip-vit-base-patch32`)
  with violence/gore/fighting labels. `classify_image()` now returns non-zero
  violence scores.

**Engine — Tests:**
- `engine/tests/test_deepfake_factory.py` — factory provider selection, fallback to stub,
  caching, unknown provider handling.
- `engine/tests/test_face_extractor.py` — face detection with mocked MediaPipe, no-face
  returns empty, tiny face skipping.
- `engine/tests/test_local_detector.py` — ONNX preprocessing shape, sigmoid, mocked
  session, unavailable fallback.
- `engine/tests/test_cloud_detector.py` — SightEngine + generic API: response parsing,
  error handling, availability checks.
- `engine/tests/test_video_processing.py` — frame extraction, max frames cap, score
  aggregation, empty frames handling.

### Changed
- `engine/classifiers.py` — `detect_deepfake_suspect()` rewired from stub to real
  pipeline: extract faces → run provider → return max score. `classify_image()`
  now includes violence detection via CLIP zero-shot.
- `engine/config.py` — new settings: `deepfake_provider`, `deepfake_model_path`,
  `sightengine_api_user`, `sightengine_api_secret`, `deepfake_api_url`,
  `deepfake_api_key`, `deepfake_api_score_path`, `frame_interval`, `max_frames`,
  `max_video_duration`.
- `engine/routes.py` — `/moderate_video` replaced: decode → extract frames →
  classify + deepfake → aggregate → verdict. No longer a stub.
- `engine/requirements.txt` — added `onnxruntime==1.17.0`,
  `opencv-python-headless==4.9.0.80`, `mediapipe==0.10.11`.
- `engine/Dockerfile` — added `ffmpeg` to apt-get install.
- `engine/.env.example` — added deepfake provider and video processing env vars
  with GDPR privacy warnings for cloud providers.
- `docker-compose.yml` — added `onnx-models` volume for ONNX model caching.
- `engine/tests/conftest.py` — mocks for deepfake factory and face extractor
  added to `client` and `client_with_key` fixtures.
- `engine/tests/test_classifiers.py` — updated deepfake and violence tests for
  new provider-based implementation.
- `engine/tests/test_routes.py` — updated video moderation tests for real pipeline.
- `ROADMAP.md` — Phase 4 marked ✅ complete.

---

## [0.4.0] — 2026-03-23 — Phase 3: GDPR Compliance, Database & Warning System

### Added

**Engine — Database:**
- `engine/database.py` — async SQLAlchemy engine (`aiosqlite` for SQLite default,
  `asyncpg` for PostgreSQL).  `init_db()` creates tables on startup (idempotent).
  `get_session()` FastAPI dependency yields a scoped async session.
- `engine/db_models.py` — four ORM models:
  - `ModerationEvent` — audit log per moderation decision: verdict, scores, hashed
    user/group IDs, content type, language, expiry timestamp.  No message content.
  - `UserWarning` — running violation counter per (user, group) pair with escalation level.
  - `ConsentRecord` — tracks whether a user has been shown the privacy notice.
  - `DeletionRequest` — Article 17 erasure requests (pending → completed lifecycle).

**Engine — GDPR Service (`engine/gdpr.py`):**
- `hash_id(platform, raw_id)` — SHA-256(GDPR_SALT + platform + id): pseudonymises
  user/group identifiers before storage; brute-force resistant with the secret salt.
- `run_retention_cleanup(session)` — deletes ModerationEvents past their `expires_at`
  timestamp (Article 5(1)(e) storage limitation).
- `process_pending_deletions(session)` — executes all pending Article 17 requests by
  erasing ModerationEvents, UserWarnings, and ConsentRecords for the requester.
- `log_moderation_event(...)` — background-task helper called from routes; failures
  are swallowed so DB errors never block moderation responses.
- `POST /gdpr/export` — Article 15 Right of Access: returns all stored data for a user.
- `POST /gdpr/delete_request` — Article 17 Right to Erasure: submit erasure request.
- `GET /gdpr/delete_request/{id}` — check erasure request status.

**Engine — Warning & Escalation System (`engine/warn.py`):**
- `escalation_action(count)` — maps violation count to action:
  `1 → notice`, `2 → admin_notification`, `≥3 → supervisor_escalation`.
- `POST /warnings/record` — record a violation for a (user, group) pair; returns
  updated count and escalation action.
- `GET /warnings/{user_id_hash}` — fetch all warning records for a user.

**Engine — Tests:**
- `engine/tests/test_gdpr.py` — 11 tests: hash determinism, export empty/populated,
  delete request submission, deduplication, status check, 404 on unknown request.
- `engine/tests/test_warnings.py` — 10 tests: escalation logic, sequential violations,
  group independence, hash determinism, unknown user returns empty list.

**Telegram Bot — GDPR commands:**
- `/privacy` — sends the privacy notice in the configured bot language.
- `/delete_my_data` — submits an Article 17 erasure request via the engine API;
  confirms submission with the request ID.
- `engine_client.gdpr_delete_request(user_id)` — calls `POST /gdpr/delete_request`.
- `engine_client.gdpr_export(user_id)` — calls `POST /gdpr/export`.
- `engine_client.record_warning(user_id, group_id, reasons)` — calls `POST /warnings/record`.

**Telegram Bot — Warning integration:**
- `_handle_warning()` in `telegram-bot/main.py` — called after every `delete` or
  `flag` verdict; records the violation and posts the appropriate escalation message:
  notice (first offence), admin notification (second), supervisor escalation (third+).
- Moderation calls now forward `user_id` and `group_id` to the engine for audit logging.

**i18n:**
- `telegram-bot/i18n/en.json` + `de.json` — nine new message keys:
  `warning_notice`, `warning_admin_notification`, `warning_admin_notification_no_admins`,
  `warning_supervisor_escalation`, `warning_supervisor_escalation_no_admins`,
  `privacy_notice`, `delete_my_data_submitted`, `delete_my_data_already_pending`,
  `delete_my_data_error`.

**Privacy policy template:**
- `engine/privacy_policy.md` — deployable GDPR privacy policy template covering
  data categories, legal basis, pseudonymisation, retention, and user rights.

### Changed
- `engine/config.py` — three new settings: `database_url` (SQLite default),
  `gdpr_salt` (SHA-256 salt), `data_retention_days` (default 30).
- `engine/models.py` — `TextRequest`, `ImageRequest`, `VideoRequest` gain optional
  `user_id`, `group_id`, `platform` fields for audit context (backward compatible).
- `engine/routes.py` — all three moderation handlers accept `BackgroundTasks` and
  schedule `log_moderation_event()` when user/group context is provided.
- `engine/main.py` — FastAPI lifespan added: runs `init_db()`, `run_retention_cleanup()`,
  and `process_pending_deletions()` on startup; mounts `gdpr_router` and `warnings_router`.
  Version bumped to `0.4.0`.
- `engine/requirements.txt` — added `sqlalchemy==2.0.36`, `aiosqlite==0.20.0`.
- `engine/.env.example` — added `DATABASE_URL`, `GDPR_SALT`, `DATA_RETENTION_DAYS`.
- `engine/tests/conftest.py` — sets `DATABASE_URL` and `GDPR_SALT` env vars for tests;
  cleans up test DB file before and after the test session.
- `docker-compose.yml` — `engine` service gains `engine-db` volume mounted at
  `/app/data`; `DATABASE_URL` overridden to point inside the volume.
- `README.md` — new GDPR & Privacy section with config table, user rights table,
  warning escalation table, and API endpoint reference.
- `ROADMAP.md` — Phase 3 marked ✅ complete.

---

## [0.3.0] — 2026-03-22 — Phase 2: i18n Architecture, Cyberbullying & Language Packs

### Added

**Engine — i18n Architecture:**
- `engine/i18n/` package — language-agnostic moderation framework:
  - `engine/i18n/base.py` — abstract `LanguagePack` base class with `detect()`,
    `get_classifier()`, `get_labels()`, `get_patterns()`, `get_educational_messages()`,
    `get_helplines()` interface.  `HarmPattern` and `Helpline` dataclasses.
  - `engine/i18n/registry.py` — `LanguageRegistry` with auto-discovery: imports all
    modules in `engine/i18n/packs/` at startup and registers every `LanguagePack`
    subclass by its `lang_code`.  Adding a new language = one new file.
  - `engine/i18n/detector.py` — `detect_language(text)` iterates enabled packs,
    picks the highest-confidence match, falls back to `"en"`.
- `engine/i18n/packs/en.py` — **English language pack** (`EnglishPack`):
  - Migrates existing `facebook/bart-large-mnli` zero-shot classifier.
  - English cyberbullying patterns: death threats, targeted insults, exclusion
    language, extortion.
  - Helplines: Crisis Text Line, Cyberbullying Research Center, StopBullying.gov.
- `engine/i18n/packs/de.py` — **German language pack** (`GermanPack`):
  - Uses `ml6team/distilbert-base-german-cased-toxic-comments` (~260 MB, CPU-compatible).
  - German cyberbullying patterns: Todesdrohungen, Ausgrenzung, gezielte Beleidigungen,
    Erpressung, Doxxing indicators.
  - Helplines: Nummer gegen Kummer (116 111), Telefonseelsorge (0800 111 0 111),
    Jugendnotmail, Klicksafe.

**Engine — Cyberbullying Detection:**
- `engine/cyberbullying.py` — `score_cyberbullying(text, lang_pack)`: combines
  language-specific `HarmPattern` matches with cross-language structural patterns
  (pile-on @mentions, repeated insults, all-caps shouting).
- `ModerationScores` gains `cyberbullying: float` field (default `0.0` — fully
  backward compatible).
- `ModerationResult` gains `language: str | None` field (detected language code).
- `TextRequest` gains optional `language: str | None` hint to bypass auto-detection.
- New env var `THRESHOLD_CYBERBULLYING=0.6` (delete threshold for cyberbullying).
- `verdict.py` updated to check cyberbullying threshold and include `"cyberbullying"`
  / `"elevated_cyberbullying"` in reasons.

**Engine — Threshold Profiles:**
- `engine/profiles.py` — `ThresholdProfile` dataclass + three built-in profiles:
  - `minors_strict` (violence=0.5, sexual_violence=0.3, nsfw=0.4, deepfake=0.6, cyberbullying=0.4)
  - `default` (unchanged Phase 1 values + cyberbullying=0.6)
  - `permissive` (higher thresholds for adult communities)
- New env var `MODERATION_PROFILE=default` selects the active profile.  Individual
  `THRESHOLD_*` env vars still override individual profile values.
- `config.py` converted to `__init__`-based `Settings` to support profile-as-default
  pattern.

**Engine — Tests:**
- `engine/tests/test_i18n.py` — 18 tests covering registry discovery, pack interface,
  language detection with mocked `langdetect`.
- `engine/tests/test_cyberbullying.py` — 11 tests covering English and German patterns,
  structural patterns, graceful error handling.
- `engine/tests/test_verdict.py` — 3 new tests for cyberbullying threshold, flag path,
  and backward compatibility.
- `engine/tests/test_classifiers.py` — updated for new `classify_text` signature and
  return shape (includes `cyberbullying` and `lang_code` keys).

**Telegram Bot — i18n:**
- `telegram-bot/i18n/en.json` + `telegram-bot/i18n/de.json` — admin notification
  message templates in English and German.
- `telegram-bot/i18n/loader.py` — `get_message(key, lang, **kwargs)`: loads JSON
  templates, falls back to English, formats with `str.format_map`.
- `telegram-bot/main.py` — `_notify_admins()` now accepts a `language` parameter
  and uses `get_message()` to send localised notifications.  Language is taken from
  the engine's `ModerationResult.language` field (text moderation) or the
  `BOT_LANGUAGE` env var fallback (image/video moderation).

### Changed
- `engine/classifiers.py` — `classify_text()` refactored to route through the
  language registry; falls back to the legacy BART pipeline when no pack is found.
- `engine/config.py` — converted to `__init__`-based `Settings`; new fields:
  `enabled_languages`, `moderation_profile`, `threshold_cyberbullying`.
- `engine/.env.example` — added `ENABLED_LANGUAGES`, `MODERATION_PROFILE`,
  `THRESHOLD_CYBERBULLYING`.
- `engine/requirements.txt` — added `langdetect==1.0.9`.
- `telegram-bot/config.py` — added `bot_language` setting.
- `telegram-bot/.env.example` — added `BOT_LANGUAGE=en`.

---

## [0.2.0] — 2026-03-22 — Phase 1: Tests, CI/CD, API Auth, Resilience

### Added

**Engine — API Key Authentication & Rate Limiting:**
- `X-API-Key` middleware in `engine/main.py` — all moderation endpoints require a
  valid key when `API_KEY` env var is set; `/health` is always public.
- Per-IP rate limiting on `/moderate_text`, `/moderate_image`, `/moderate_video`
  via [slowapi](https://github.com/laurentS/slowapi) (default: `60/minute`,
  configurable via `RATE_LIMIT` env var).
- `API_KEY` and `RATE_LIMIT` added to `engine/config.py` and `engine/.env.example`.

**Engine — Test Suite:**
- `engine/tests/conftest.py` — shared pytest fixtures: `TestClient` with mocked
  ML classifiers (no GPU/download required), small test image helper.
- `engine/tests/test_verdict.py` — 12 unit tests covering allow/flag/delete
  threshold logic across all four score categories.
- `engine/tests/test_routes.py` — 16 integration tests for all four endpoints
  including API key authentication and error cases.
- `engine/tests/test_classifiers.py` — 12 unit tests for `decode_image`,
  `classify_text`, `classify_image`, and `detect_deepfake_suspect` with mocked
  pipelines.
- `engine/pyproject.toml` — pytest, ruff, and mypy configuration.

**Telegram Bot — Resilience & API Key:**
- `engine_client.py` rewritten with exponential-backoff retry logic: up to 3
  retries on network errors and 5xx responses (waits: 1s → 2s → 4s).
- `X-API-Key` header forwarded when `ENGINE_API_KEY` env var is set.
- `ENGINE_API_KEY` added to `telegram-bot/config.py` and `telegram-bot/.env.example`.
- `telegram-bot/tests/test_engine_client.py` — tests covering successful calls,
  retry on transport error, retry on 5xx, max-retry exhaustion, API key header.
- `telegram-bot/pyproject.toml` — pytest and ruff configuration.

**WhatsApp Bot — Resilience & API Key:**
- `src/engine-client.ts` rewritten with built-in retry loop (up to 3 retries,
  exponential backoff, retries on network errors and 5xx status codes).
- `X-API-Key` header forwarded when `ENGINE_API_KEY` env var is set.
- `ENGINE_API_KEY` added to `src/config.ts` and `whatsapp-bot/.env.example`.

**CI/CD — GitHub Actions:**
- `.github/workflows/ci.yml` — runs on every push/PR:
  - `engine` job: ruff lint, mypy type-check, pytest.
  - `telegram-bot` job: ruff lint, pytest.
  - `whatsapp-bot` job: TypeScript build (`tsc`).
- `.github/workflows/docker.yml` — builds all three Docker images on pushes/PRs
  to `master`/`main`.

### Changed
- `engine/requirements.txt` — added `slowapi==0.1.9`, `pytest==8.3.4`,
  `pytest-asyncio==0.24.0`.
- `telegram-bot/requirements.txt` — added `pytest==8.3.4`, `pytest-asyncio==0.24.0`.
- `engine/main.py` — version bumped to `0.2.0`; slowapi wired to app.
- `engine/routes.py` — all three POST handlers now accept `request: Request` as
  required by slowapi; shared `limiter` instance exported for `main.py`.
- `README.md` — updated status banner, added API auth/rate-limit config table,
  added "Running Tests" section, updated roadmap status.

---

## [0.0.3] — 2025-01-xx — Neutral Role Terminology in Roadmap

### Changed
- `ROADMAP.md` — replaced school-specific terminology with platform-neutral roles:
  Admin (group manager), Member (participant), Supervisor (higher-level oversight).
  Broadens the target audience beyond schools to any organisation running group chats.
  No behaviour change → patch bump.

---

## [0.2.0] — 2025-01-xx — Development Roadmap

### Added
- `ROADMAP.md` — six-phase development plan covering:
  - Phase 1: Tests, CI/CD, API auth, error handling
  - Phase 2: i18n architecture, cyberbullying detection, German + English language packs
  - Phase 3: GDPR compliance, database, warning/escalation system
  - Phase 4: Real deepfake model, video frame extraction
  - Phase 5: Admin dashboard, admin bot commands, educational feedback
  - Phase 6: WhatsApp parity, Signal/Discord bots, community language packs
- i18n architecture design: `LanguagePack` abstract base class, plugin registry,
  language detector/router. Adding a new language = one Python file.
- Internationalisation strategy as competitive differentiator (vs. English-only tools).

---

## [0.1.0] — 2025-01-xx — Initial Prototype

### Added

**Engine (`engine/`)** — FastAPI content classification service:
- `POST /moderate_text` — classifies plain text using `facebook/bart-large-mnli`
  zero-shot classifier; categories: violence, sexual_violence, nsfw.
- `POST /moderate_image` — classifies images using CLIP zero-shot; also calls
  deepfake stub.
- `POST /moderate_video` — stub endpoint (always returns `"allow"`); wired and
  ready for real frame extraction.
- `GET /health` — liveness check.
- `verdict.py` — threshold-based decision engine: scores → `"allow"` / `"flag"` /
  `"delete"`.
- `models.py` — Pydantic v2 schemas (`ModerationResult`, `ModerationScores`,
  `TextRequest`, `ImageRequest`, `VideoRequest`).
- `config.py` — all configuration from env vars with defaults
  (`THRESHOLD_VIOLENCE=0.7`, `THRESHOLD_SEXUAL_VIOLENCE=0.5`, `THRESHOLD_NSFW=0.6`,
  `THRESHOLD_DEEPFAKE=0.8`).
- Structured logging via `structlog`.
- `Dockerfile` + `.env.example`.

**Telegram Bot (`telegram-bot/`)** — python-telegram-bot group listener:
- Handles text messages, photos, and videos in group chats (ignores private chats
  and commands).
- `engine_client.py` — async HTTP client for the engine API.
- Verdict actions: delete message (if bot is admin) or @-mention group admins.
- Structured logging via `structlog`.
- `Dockerfile` + `.env.example`.

**WhatsApp Bot (`whatsapp-bot/`)** — TypeScript/Node.js bot using Baileys:
- Mirrors Telegram bot behaviour for WhatsApp groups.
- `Dockerfile` + `.env.example`.

**Infrastructure:**
- `docker-compose.yml` — orchestrates all three services; ML model cache via
  Docker volume.
- `LICENSE` (MIT).

### Known limitations at this stage
- Deepfake detection is a **stub** — `detect_deepfake_suspect()` always returns `0.05`.
- Video moderation is a **stub** — `moderate_video` always returns `"allow"`.
- Image violence score always returns `0.0`.
- No tests, no CI/CD.
- No API authentication on the engine.
- No database or GDPR features.
- English-only; i18n not yet implemented.
- No cyberbullying detection.

---

[Unreleased]: https://github.com/alcoolio/deepfake-guardian/compare/HEAD...HEAD
