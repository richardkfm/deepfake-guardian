"""Engine configuration loaded from environment variables.

Moderation thresholds are initialised from the active
:data:`~profiles.PROFILES` entry so that ``MODERATION_PROFILE=minors_strict``
changes all thresholds at once.  Individual env vars (``THRESHOLD_VIOLENCE``
etc.) can still override a single threshold within a profile.
"""

from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()


def _env_float(name: str, default: float) -> float:
    """Read a float env var; unset or blank (``NAME=``) means *default*."""
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    return float(raw)


class Settings:
    """Central settings — all values come from env vars with sane defaults."""

    def __init__(self) -> None:
        self.host: str = os.getenv("HOST", "0.0.0.0")
        self.port: int = int(os.getenv("PORT", "8000"))
        self.log_level: str = os.getenv("LOG_LEVEL", "info")

        # API authentication — leave empty to disable (dev/local only)
        self.api_key: str = os.getenv("API_KEY", "")

        # Rate limiting (requests per minute per IP on moderation endpoints)
        self.rate_limit: str = os.getenv("RATE_LIMIT", "60/minute")

        # i18n — comma-separated list of enabled language codes
        self.enabled_languages: list[str] = [
            lang.strip().lower()
            for lang in os.getenv("ENABLED_LANGUAGES", "en,de").split(",")
            if lang.strip()
        ]

        # Opt-in moderation categories — comma-separated list of skill ids
        # (e.g. "advertising,political_misinformation").  Core child-safety
        # categories are always on; these run only when listed here.
        # Skill ids are lowercase, so normalise case to avoid silently ignoring
        # e.g. "Advertising".
        self.enabled_categories: list[str] = [
            cat.strip().lower()
            for cat in os.getenv("ENABLED_CATEGORIES", "").split(",")
            if cat.strip()
        ]

        # Moderation profile — sets default thresholds; individual env vars override
        from profiles import get_profile, normalise_profile_name

        self.moderation_profile: str = normalise_profile_name(
            os.getenv("MODERATION_PROFILE", "default")
        )

        profile = get_profile(self.moderation_profile)

        self.threshold_violence: float = _env_float("THRESHOLD_VIOLENCE", profile.violence)
        self.threshold_sexual_violence: float = _env_float(
            "THRESHOLD_SEXUAL_VIOLENCE", profile.sexual_violence
        )
        self.threshold_nsfw: float = _env_float("THRESHOLD_NSFW", profile.nsfw)
        self.threshold_deepfake: float = _env_float("THRESHOLD_DEEPFAKE", profile.deepfake)
        self.threshold_cyberbullying: float = _env_float(
            "THRESHOLD_CYBERBULLYING", profile.cyberbullying
        )

        # Deepfake detection provider: openai | ollama | local | sightengine | api | stub
        self.deepfake_provider: str = os.getenv("DEEPFAKE_PROVIDER", "stub")
        self.deepfake_model_path: str = os.getenv("DEEPFAKE_MODEL_PATH", "")

        # Refuse to start when the configured deepfake provider is unavailable
        # instead of silently degrading to the stub detector (which scores every
        # face 0.05, i.e. detection is off while the engine looks healthy).
        # Default false to preserve existing behaviour; turn on for
        # child-safety deployments that must not run blind.
        self.deepfake_require_provider: bool = os.getenv(
            "DEEPFAKE_REQUIRE_PROVIDER", "false"
        ).strip().lower() in ("1", "true", "yes")

        # Pluggable deepfake detection layers (engine/deepfake/layers/*.md).
        # Comma-separated list of layer ids to activate; OVERRIDES each layer
        # manifest's own `enabled:` default when set. Empty/unset = 100%
        # legacy single-provider behaviour driven by DEEPFAKE_PROVIDER above
        # (the default, fully backward compatible).
        self.deepfake_layers: list[str] = [
            layer.strip()
            for layer in os.getenv("DEEPFAKE_LAYERS", "").split(",")
            if layer.strip()
        ]
        # How multiple active layers' scores combine: max | mean | weighted_mean
        self.deepfake_layer_combine: str = os.getenv("DEEPFAKE_LAYER_COMBINE", "max")
        # Only the N largest faces in an image/frame are sent to the deepfake
        # detector(s). 0 (default) = score every detected face. Bounds the
        # latency/cost of crowd photos with remote providers, which make one
        # API call per face.
        self.deepfake_max_faces: int = int(os.getenv("DEEPFAKE_MAX_FACES", "0"))

        # OpenAI provider (DEEPFAKE_PROVIDER=openai)
        self.openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
        self.openai_model: str = os.getenv("OPENAI_MODEL", "gpt-4o")
        self.openai_api_base: str = os.getenv("OPENAI_API_BASE", "https://api.openai.com/v1")

        # Ollama provider (DEEPFAKE_PROVIDER=ollama)
        self.ollama_base_url: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        self.ollama_model: str = os.getenv("OLLAMA_MODEL", "llava")

        # Cloud credentials (only needed for cloud providers)
        self.sightengine_api_user: str = os.getenv("SIGHTENGINE_API_USER", "")
        self.sightengine_api_secret: str = os.getenv("SIGHTENGINE_API_SECRET", "")
        self.deepfake_api_url: str = os.getenv("DEEPFAKE_API_URL", "")
        self.deepfake_api_key: str = os.getenv("DEEPFAKE_API_KEY", "")
        self.deepfake_api_score_path: str = os.getenv("DEEPFAKE_API_SCORE_PATH", "score")

        # Video processing
        self.frame_interval: float = float(os.getenv("FRAME_INTERVAL", "2.0"))
        self.max_frames: int = int(os.getenv("MAX_FRAMES", "10"))
        self.max_video_duration: int = int(os.getenv("MAX_VIDEO_DURATION", "300"))

        # image_url / video_url fetching (routes.fetch_media_url).  URLs that
        # resolve to private, loopback, link-local or otherwise reserved
        # addresses are refused (SSRF protection) unless explicitly allowed,
        # e.g. for a trusted internal media store.
        self.media_url_allow_private: bool = os.getenv(
            "MEDIA_URL_ALLOW_PRIVATE", "false"
        ).strip().lower() in ("1", "true", "yes")
        # Maximum bytes downloaded from a media URL (default 50 MiB)
        self.max_media_bytes: int = int(os.getenv("MAX_MEDIA_BYTES", str(50 * 1024 * 1024)))

        # Known non-consensual intimate imagery (NCII) hash matching — opt-in.
        # When enabled, incoming images/video frames are perceptually hashed
        # and compared against victim/admin-submitted protected hashes (see
        # known_content.py); a match forces a "delete" verdict regardless of
        # the ML scores. Off by default: it adds a dependency (ImageHash) and
        # requires operators to have actually populated the protected list.
        self.known_image_hash_matching: bool = os.getenv(
            "KNOWN_IMAGE_HASH_MATCHING", "false"
        ).strip().lower() in ("1", "true", "yes")
        # Max Hamming distance (out of 64 bits for phash) still considered a
        # match. Lower = stricter (fewer false positives, more false
        # negatives on cropped/re-encoded re-uploads). 10 is a common
        # near-duplicate-detection default.
        self.known_image_hash_threshold: int = int(
            os.getenv("KNOWN_IMAGE_HASH_THRESHOLD", "10")
        )

        # GDPR / persistence
        self.database_url: str = os.getenv(
            "DATABASE_URL", "sqlite+aiosqlite:///./deepfake_guardian.db"
        )
        # Secret salt for SHA-256 ID hashing — change in production
        self.gdpr_salt: str = os.getenv("GDPR_SALT", "change-me-in-production")
        # How many days moderation events are kept before automatic deletion
        self.data_retention_days: int = int(os.getenv("DATA_RETENTION_DAYS", "30"))
        # How often (minutes) retention cleanup and pending Article 17 erasure
        # requests run while the engine is up (they also run at startup).
        self.gdpr_cleanup_interval_minutes: float = float(
            os.getenv("GDPR_CLEANUP_INTERVAL_MINUTES", "60")
        )


settings = Settings()
