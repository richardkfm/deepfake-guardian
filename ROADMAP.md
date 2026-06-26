# Deepfake Guardian — Development Roadmap

## Context

The monorepo contains three services (engine, telegram-bot, whatsapp-bot) as a
functional prototype. Primary target audience: **chat groups with minors** (e.g.
schools, youth organisations, sports clubs). Further audiences: community groups,
organisations, companies. The current state has critical gaps: no tests, no GDPR
concept, deepfake detection is a stub, no German language support, no cyberbullying
detection, no dashboard.

**Role terminology (platform-neutral, not school-specific):**
- **Admin** = group manager (teachers, coaches, moderators, etc.)
- **Member** = group participant (students, attendees, etc.)
- **Supervisor** = higher-level oversight (principal, board member, etc.)

**Key decisions:**
- Telegram has higher priority (official API, simpler)
- Simple web dashboard for admins
- Full GDPR compliance (minors = highest protection level)

---

## Phase 1: Foundation & Production Readiness ✅

**Goal:** Make the existing code testable, secure, and deployable.

### 1.1 Tests & Linting
- **New files:**
  - `engine/tests/test_routes.py` — pytest tests for all 3 endpoints + /health
  - `engine/tests/test_verdict.py` — unit tests for threshold logic
  - `engine/tests/test_classifiers.py` — tests with mocked pipelines
  - `engine/tests/conftest.py` — fixtures (FastAPI TestClient, mock images)
  - `telegram-bot/tests/test_handlers.py` — tests with mocked engine client
  - `engine/pyproject.toml` — pytest, black, ruff, mypy configuration
- **Modified files:**
  - `engine/requirements.txt` — add pytest, httpx[test], pytest-asyncio
  - `telegram-bot/requirements.txt` — add pytest

### 1.2 CI/CD Pipeline
- **New files:**
  - `.github/workflows/ci.yml` — lint + test + type-check for engine & telegram-bot
  - `.github/workflows/docker.yml` — Docker build validation

### 1.3 Engine API Security
- **Modified files:**
  - `engine/config.py` — load `API_KEY` from .env
  - `engine/main.py` — FastAPI middleware for API key validation + rate limiting
  - `engine/requirements.txt` — add `slowapi` for rate limiting
  - `engine/.env.example` — add `API_KEY` field
  - `telegram-bot/engine_client.py` — send API key header
  - `telegram-bot/.env.example` — `ENGINE_API_KEY` field
  - `whatsapp-bot/src/engine-client.ts` — API key header
  - `whatsapp-bot/.env.example` — `ENGINE_API_KEY` field

### 1.4 Error Handling & Resilience
- **Modified files:**
  - `telegram-bot/engine_client.py` — retry logic with exponential backoff (tenacity)
  - `telegram-bot/main.py` — graceful handling when engine is unreachable
  - `whatsapp-bot/src/engine-client.ts` — add axios-retry

**Effort:** M | **Result:** Testable, secured prototype with CI/CD

---

## Phase 2: i18n Architecture, Cyberbullying Detection & Language Packs ✅

**Goal:** Build a language-agnostic moderation architecture. Implement German as
the first language pack. Every additional language + culture-specific rules should
be addable without code changes.

### 2.1 i18n Core Architecture (Engine)
- **New files:**
  - `engine/i18n/` — i18n framework:
    - `engine/i18n/__init__.py` — language registry, auto-discovery of language packs
    - `engine/i18n/base.py` — abstract base class `LanguagePack`:
      - `detect(text) -> float` — confidence that text belongs to this language
      - `get_classifier() -> TextClassifier` — language-specific ML model
      - `get_patterns() -> list[HarmPattern]` — regex/keyword-based patterns
      - `get_labels() -> dict[str, str]` — localised category names
      - `get_educational_messages() -> dict[str, str]` — educational feedback texts
      - `get_helplines() -> list[Helpline]` — local support and counselling resources
    - `engine/i18n/registry.py` — plugin registry: auto-loads all `LanguagePack` subclasses
    - `engine/i18n/detector.py` — language router: detects language → selects matching pack
  - `engine/i18n/packs/` — language pack directory:
    - `engine/i18n/packs/__init__.py`
    - `engine/i18n/packs/de.py` — **German language pack** (first implementation, see 2.2)
    - `engine/i18n/packs/en.py` — **English language pack** (migrates existing BART classifier)

- **Design principles:**
  - Each language pack is a single Python module in `engine/i18n/packs/`
  - New pack = new file + class inheriting `LanguagePack` → done
  - No code in `engine/classifiers.py` or `routes.py` needs to change
  - Language packs can be enabled/disabled via config
  - Community can develop packs as separate repos (future: pip-installable)

- **Modified files:**
  - `engine/classifiers.py` — `classify_text()` refactored to call i18n router
  - `engine/config.py` — `ENABLED_LANGUAGES=de,en` (comma-separated)
  - `engine/requirements.txt` — add `langdetect` or `lingua-language-detector`

### 2.2 German Language Pack (first `LanguagePack`)
- **File:** `engine/i18n/packs/de.py`
  - **ML model:** `ml6team/distilbert-base-german-cased-toxic-comments` or equivalent (CPU-compatible, ~260 MB)
  - **Categories:** insult, threat, sexualised language, hate speech, cyberbullying
  - **Culture-specific patterns (regex/keywords):**
    - German slurs and youth slang
    - Exclusion language ("you don't belong here", "nobody likes you")
    - Extortion patterns ("I'll show everyone", "if you don't...")
    - Doxxing indicators (German address formats, phone numbers)
  - **Educational messages:** age-appropriate explanations in German (configurable)
  - **Support resources:** Nummer gegen Kummer, Jugendnotmail, Telefonseelsorge, etc.

### 2.3 English Language Pack (Migration)
- **File:** `engine/i18n/packs/en.py`
  - Migrates existing `facebook/bart-large-mnli` zero-shot classifier
  - English patterns and support resources
  - Ensures existing functionality remains intact

### 2.4 Cyberbullying as a Moderation Category
- **New files:**
  - `engine/cyberbullying.py` — cross-language cyberbullying detector:
    - Structural patterns (language-agnostic): e.g. @mention + negative emotion
    - Repetition patterns: same user → same target multiple times
    - Context analysis: group dynamics (is one person always being attacked?)
    - Uses language-specific patterns from the respective `LanguagePack`
- **Modified files:**
  - `engine/models.py` — extend `ModerationScores` with `cyberbullying: float`
  - `engine/verdict.py` — add cyberbullying threshold
  - `engine/config.py` — `THRESHOLD_CYBERBULLYING=0.5`

### 2.5 Threshold Profiles
- **New files:**
  - `engine/profiles.py` — predefined threshold sets:
    - `minors_strict` (lower thresholds, stricter moderation — for groups with minors)
    - `minors_standard` (standard for groups with minors)
    - `default` (current values, for general groups)
    - `permissive` (higher thresholds, fewer interventions — for adult communities)
    - Profiles are JSON-serialisable → can later be configured via dashboard
- **Modified files:**
  - `engine/config.py` — `MODERATION_PROFILE=default`
  - `engine/verdict.py` — use profile-based thresholds

### 2.6 Bot Message i18n
- **New files:**
  - `telegram-bot/i18n/` — bot UI texts (separate from engine i18n):
    - `telegram-bot/i18n/de.json` — German bot messages ("Message was removed because...")
    - `telegram-bot/i18n/en.json` — English bot messages
  - `telegram-bot/i18n/loader.py` — loads JSON, falls back to English
- **Modified files:**
  - `telegram-bot/main.py` — replace all hardcoded strings with i18n lookups
  - `telegram-bot/config.py` — `BOT_LANGUAGE=de` setting

**Effort:** L–XL | **Result:** Language-agnostic architecture with German + English. New languages = one new file in `packs/`. Bot UI localised.

> **Why this is a competitive advantage:** Most content moderation tools are
> English-only. An i18n-first architecture + GDPR compliance makes Deepfake Guardian
> attractive for organisations worldwide — not just DACH.

---

## Phase 3: GDPR Compliance & Persistence ✅

**Goal:** Full GDPR compliance for minor data. Audit logging with automatic deletion schedules.

### 3.1 Database Setup
- **New files:**
  - `engine/database.py` — SQLAlchemy setup (SQLite default, PostgreSQL optional)
  - `engine/db_models.py` — ORM models:
    - `ModerationEvent`: timestamp, group_id (hashed), verdict, reasons, scores, content_type (no message content!)
    - `UserWarning`: user_id_hash, group_id_hash, warning_count, last_warning, reason
    - `ConsentRecord`: user_id_hash, consent_given, consent_date, consent_scope
    - `DeletionRequest`: requester_hash, request_date, status, completed_date
  - `engine/alembic/` — database migrations
- **Modified files:**
  - `engine/requirements.txt` — add sqlalchemy, alembic, aiosqlite
  - `engine/routes.py` — log ModerationEvents after every decision
  - `docker-compose.yml` — volume for SQLite database

### 3.2 GDPR Core Features
- **New files:**
  - `engine/gdpr.py` — GDPR service:
    - Automatic deletion after configurable retention period (default: 30 days)
    - Right of access: API endpoint `/gdpr/data_export/{user_hash}`
    - Right to erasure: API endpoint `/gdpr/delete_request`
    - All user IDs are hashed before storage (SHA-256 + salt)
    - No message content stored — only metadata + scores
  - `engine/privacy_policy.md` — privacy policy (template)
- **Modified files:**
  - `engine/routes.py` — mount GDPR router
  - `engine/config.py` — `DATA_RETENTION_DAYS=30`, `GDPR_SALT` (secret)
  - `engine/.env.example` — GDPR configuration

### 3.3 Consent Management
- **Modified files:**
  - `telegram-bot/main.py` — on first contact: send privacy notice, request consent
  - `telegram-bot/main.py` — `/privacy` command: show privacy information
  - `telegram-bot/main.py` — `/delete_my_data` command: submit deletion request

### 3.4 Warning & Escalation System
- **New files:**
  - `engine/warnings.py` — warning service:
    - 1st violation: educational notice (DM to user)
    - 2nd violation: warning + admin notification
    - 3rd violation: automatic report to supervisor (configurable)
    - Counter per member+group, configurable escalation levels
- **Modified files:**
  - `engine/routes.py` — `/warnings/{user_hash}` endpoints
  - `telegram-bot/main.py` — integrate warning logic into `_handle_verdict()`

**Effort:** XL | **Result:** GDPR-compliant moderation with audit trail and configurable escalation system

---

## Phase 4: Deepfake Detection & Video Analysis ✅

**Goal:** Replace the deepfake stub with a real model. Implement video frame extraction.

### 4.1 Deepfake Detection Provider System
- **New files:**
  - `engine/deepfake/` — provider abstraction package:
    - `engine/deepfake/base.py` — `DeepfakeDetector` ABC: `detect(face_images) -> list[float]`, `is_available() -> bool`
    - `engine/deepfake/factory.py` — factory with cached singleton: reads `DEEPFAKE_PROVIDER` env var, falls back to stub
    - `engine/deepfake/face_extractor.py` — shared face extraction using MediaPipe `FaceDetection`
    - `engine/deepfake/local_detector.py` — `LocalOnnxDetector`: EfficientNet-B0 ONNX model (~20 MB, CPU)
    - `engine/deepfake/cloud_sightengine.py` — `SightEngineDetector`: SightEngine cloud API
    - `engine/deepfake/cloud_generic.py` — `GenericApiDetector`: user-configured HTTP endpoint
- **Modified files:**
  - `engine/classifiers.py` — `detect_deepfake_suspect()` rewired: extract faces → run provider → return max score
  - `engine/config.py` — new settings: `DEEPFAKE_PROVIDER`, `DEEPFAKE_MODEL_PATH`, cloud credentials, video processing params
  - `engine/requirements.txt` — added `onnxruntime`, `mediapipe`

### 4.2 Video Frame Extraction
- **New files:**
  - `engine/video_processing.py` — OpenCV-based frame extraction:
    - Samples 1 frame every `FRAME_INTERVAL` seconds (default 2.0)
    - Capped at `MAX_FRAMES` (default 10), rejects videos > `MAX_VIDEO_DURATION` (default 300s)
    - Aggregation: max score across all frames per category
- **Modified files:**
  - `engine/routes.py` — `/moderate_video` replaced: decode → extract frames → classify + deepfake → aggregate → verdict
  - `engine/requirements.txt` — added `opencv-python-headless`
  - `engine/Dockerfile` — added `ffmpeg`
  - `docker-compose.yml` — added `onnx-models` volume

### 4.3 Image Violence Detection
- **Modified files:**
  - `engine/classifiers.py` — `classify_image()` extended with CLIP zero-shot violence classifier
    (`openai/clip-vit-base-patch32` with violence/gore/fighting labels); `violence` score no longer hardcoded `0.0`

### 4.4 Tests
- **New files:**
  - `engine/tests/test_deepfake_factory.py` — factory provider selection, fallback, caching
  - `engine/tests/test_face_extractor.py` — face detection with mocked MediaPipe
  - `engine/tests/test_local_detector.py` — ONNX preprocessing, sigmoid, session mocking
  - `engine/tests/test_cloud_detector.py` — SightEngine + generic API mocked calls
  - `engine/tests/test_video_processing.py` — frame extraction, score aggregation
- **Modified files:**
  - `engine/tests/conftest.py` — mocks for deepfake factory and face extractor
  - `engine/tests/test_classifiers.py` — updated deepfake and violence tests
  - `engine/tests/test_routes.py` — updated video moderation tests

**Effort:** L | **Result:** Real deepfake detection + working video moderation + image violence detection

---

## Phase 4.5: Pluggable Moderation Skills ✅

**Goal:** Turn moderation categories into human-editable markdown "skills" so
new use cases can be added or tuned without code, and let operators extend
Deepfake Guardian beyond child-safety to other audiences (e.g. anti-advertising,
anti-political-misinformation) via a per-deployment switch.

### 4.5.1 Skill system (Engine)
- **New files:**
  - `engine/moderation/skill.py` — `ModerationSkill` dataclass + threshold/score resolution
  - `engine/moderation/loader.py` — markdown (YAML frontmatter + sections) → `ModerationSkill`
  - `engine/moderation/registry.py` — auto-discovers `skills/*.md` (mirrors `i18n.registry`)
  - `engine/moderation/skills/*.md` — five core categories + opt-in `advertising`,
    `political_misinformation`
- **Modified files:**
  - `engine/profiles.py` — threshold values sourced from the skill files
  - `engine/verdict.py` — generic over core + enabled opt-in categories
  - `engine/models.py` — `ModerationScores.extra` for opt-in scores
  - `engine/config.py` — `ENABLED_CATEGORIES`
  - `engine/i18n/packs/{en,de}.py` — patterns/labels/messages delegate to the registry
  - `engine/routes.py` — `/moderate_text` populates `scores.extra`
  - `engine/requirements.txt` — added `PyYAML`

### 4.5.2 Tests
- `test_skill_loader.py`, `test_moderation_registry.py`, `test_advertising.py`,
  `test_political_misinformation.py`, plus opt-in cases in `test_verdict.py`

**Effort:** M | **Result:** Categories are markdown files; new use cases added by
editing/adding one file; opt-in categories toggled via `ENABLED_CATEGORIES`.
Bots unchanged.

---

## Phase 5: Admin Dashboard & Moderation Tools

**Goal:** Simple web dashboard for admins: moderation overview, statistics, configuration.

### 5.1 Dashboard Backend (Engine extension)
- **New files:**
  - `engine/dashboard_routes.py` — API endpoints:
    - `GET /dashboard/stats` — moderation statistics (last 7/30 days)
    - `GET /dashboard/events` — paginated event list (filtered by group, time period, verdict)
    - `GET /dashboard/warnings` — active warnings
    - `POST /dashboard/config` — change group configuration
    - `GET /dashboard/digest` — weekly summary report
  - `engine/auth.py` — dashboard authentication (JWT-based, login via token)

### 5.2 Dashboard Frontend
- **New files:**
  - `dashboard/` — new directory in the monorepo:
    - React (Vite) with TypeScript
    - Minimal UI: Tailwind CSS
    - Pages: Login, Overview, Events, Warnings, Configuration
    - Charts: moderation events over time (Chart.js or recharts)
  - `dashboard/Dockerfile` — nginx serving static build
- **Modified files:**
  - `docker-compose.yml` — add dashboard service (port 3000)

### 5.3 Admin Bot Commands
- **Modified files:**
  - `telegram-bot/main.py` — admin commands:
    - `/stats` — brief statistics for the last 7 days
    - `/config` — view/change current thresholds
    - `/warnings @user` — warning history of a user
    - `/digest` — request weekly report
    - `/help_mod` — help for all moderation commands

### 5.4 Educational Feedback Messages
- Uses `get_educational_messages()` and `get_helplines()` from LanguagePacks (Phase 2)
- No new file needed — the i18n architecture already delivers language-specific content
- **Modified files:**
  - `telegram-bot/main.py` — on warn/delete: send educational feedback DM to member (in the group's language)

**Effort:** XL | **Result:** Admins have a dashboard + bot commands + members receive educational feedback in their language

---

## Phase 6: Scaling & Ecosystem

**Goal:** Additional messengers, scaling, plugin system.

### 6.1 Complete WhatsApp Bot
- Feature parity with the Telegram bot (warning system, commands, GDPR)
- Port all features from Phases 2–5

### 6.2 Additional Platforms
- **New directories:**
  - `signal-bot/` — Signal messenger bot (signal-cli or libsignal)
  - `discord-bot/` — Discord bot (discord.js) — relevant for gaming communities and youth groups

### 6.3 Kubernetes & Scaling
- **New files:**
  - `k8s/` — Kubernetes manifests (Deployment, Service, Ingress, PVC)
  - `engine/Dockerfile.gpu` — GPU-optimised image for larger deployments

### 6.4 Plugin System & Community Language Packs
- Engine plugins for custom classifiers (organisations can add their own rules)
- `pip install deepfake-guardian-lang-fr` → French language pack as a separate package
- Community contributions: language packs as separate repos with the standardised `LanguagePack` interface
- Documentation: "How to create a Language Pack" guide

### 6.5 Additional Language Packs (community-driven)
- Prioritised languages based on demand:
  - `fr` — French (France, Belgium, Switzerland, Canada)
  - `es` — Spanish (Spain, Latin America)
  - `tr` — Turkish (large diaspora in DACH)
  - `ar` — Arabic (growing demand)
  - `it` — Italian (Switzerland, Italy)
- Each pack includes: ML model, culture-specific patterns, support resources, educational messages

**Effort:** XL | **Result:** Multi-platform, multilingual, scalable, extensible

---

## Phase Summary

| Phase | Focus | Effort | Depends on |
|-------|-------|--------|------------|
| 1 | Tests, CI/CD, API auth, resilience | M | — |
| 2 | i18n architecture, cyberbullying, DE+EN language packs | L–XL | Phase 1 |
| 3 | GDPR, database, warning system, consent | XL | Phase 1 | ✅ |
| 4 | Real deepfake detection, video analysis | L | Phase 1 | ✅ |
| 4.5 | Pluggable moderation skills (markdown categories) | M | Phase 2 | ✅ |
| 5 | Dashboard, admin tools, educational feedback | XL | Phase 2+3 |
| 6 | WhatsApp parity, Signal, Discord, community languages | XL | Phase 5 |

Phases 2, 3, and 4 can be developed **partially in parallel** (independent code
paths). Phase 5 requires the database from Phase 3 and the i18n architecture from
Phase 2.

---

## Verification Criteria per Phase

- **Phase 1:** `pytest` passes green, CI pipeline green, engine rejects requests without API key
- **Phase 2:** `engine/i18n/packs/de.py` detects "Du bist so hässlich" as cyberbullying. New language pack = 1 new file. Bot responds in German. `minors_strict` profile active.
- **Phase 3:** Moderation events visible in DB, `/delete_my_data` command works, auto-deletion after 30 days ✅
- **Phase 4:** Known deepfake image detected with score >0.7, video frames are extracted ✅
- **Phase 5:** Dashboard shows statistics, admin can use `/stats` in chat, educational feedback is language-specific
- **Phase 6:** Signal bot responds, Kubernetes deployment running, `pip install deepfake-guardian-lang-fr` works

---

## i18n Architecture (cross-cutting across all phases)

```
engine/i18n/
├── __init__.py          # Language registry
├── base.py              # LanguagePack ABC
├── registry.py          # Auto-discovery & plugin loading
├── detector.py          # Language detection → pack routing
└── packs/
    ├── __init__.py
    ├── de.py            # Phase 2: German (ML model + patterns + support resources)
    ├── en.py            # Phase 2: English (migrates BART)
    ├── fr.py            # Phase 6: French (community)
    └── ...              # Further languages

telegram-bot/i18n/
├── loader.py            # JSON loader with fallback
├── de.json              # Bot UI texts German
├── en.json              # Bot UI texts English
└── ...

whatsapp-bot/src/i18n/
├── loader.ts            # i18n loader
├── de.json              # Bot UI texts German
├── en.json              # Bot UI texts English
└── ...
```

**LanguagePack interface:**
```python
class LanguagePack(ABC):
    lang_code: str                    # "de", "en", "fr", ...
    lang_name: str                    # "Deutsch", "English", ...

    def detect(text) -> float         # Language confidence 0.0–1.0
    def get_classifier() -> Callable  # Language-specific ML model
    def get_patterns() -> list        # Regex/keyword patterns
    def get_labels() -> dict          # Localised category names
    def get_educational_messages()    # Educational feedback messages
    def get_helplines() -> list       # Local support resources
```

**Adding a new language pack = 1 file:**
```python
# engine/i18n/packs/fr.py
class FrenchPack(LanguagePack):
    lang_code = "fr"
    lang_name = "Français"
    # ... implement methods
```
→ Automatically discovered and activated by the registry (if listed in `ENABLED_LANGUAGES`).

---

## Most-Modified Files (across all phases)

- `engine/classifiers.py` — core of classification → delegates to i18n router (Phase 2, 4)
- `engine/i18n/` — language packs and registry (Phase 2, 6)
- `engine/routes.py` — API endpoints (every phase)
- `engine/models.py` — data models (Phase 2, 3)
- `engine/config.py` — configuration (every phase)
- `engine/verdict.py` — decision logic (Phase 2, 3)
- `telegram-bot/main.py` — bot logic (Phase 2, 3, 5)
- `docker-compose.yml` — service orchestration (Phase 3, 5)

---

## Internationalisation Strategy as a USP

| Aspect | Deepfake Guardian | Typical competition |
|--------|-------------------|---------------------|
| Languages | Plugin system, community-extensible | English-only or manually added |
| Cultural context | Per language: patterns, support resources, local laws | One-size-fits-all model |
| Privacy | GDPR-first (highest standard worldwide) | Often US-centric, minimal |
| New language | 1 Python file + 1 JSON | Weeks or months of development |
| Target audience | From minors to enterprises (strictest protection as default) | Generic |

> **The high level of data protection will be a major advantage in other countries** —
> GDPR compliance for minors is the strictest standard worldwide. Meeting it
> automatically covers COPPA (USA), PIPEDA (Canada), LGPD (Brazil), etc.
> Companies and organisations also benefit from this level of data protection.
