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
            lang.strip()
            for lang in os.getenv("ENABLED_LANGUAGES", "en,de").split(",")
            if lang.strip()
        ]

        # Opt-in moderation categories — comma-separated list of skill ids
        # (e.g. "advertising,political_misinformation").  Core child-safety
        # categories are always on; these run only when listed here.
        self.enabled_categories: list[str] = [
            cat.strip()
            for cat in os.getenv("ENABLED_CATEGORIES", "").split(",")
            if cat.strip()
        ]

        # Moderation profile — sets default thresholds; individual env vars override
        self.moderation_profile: str = os.getenv("MODERATION_PROFILE", "default")

        from profiles import get_profile

        profile = get_profile(self.moderation_profile)

        self.threshold_violence: float = float(
            os.getenv("THRESHOLD_VIOLENCE", str(profile.violence))
        )
        self.threshold_sexual_violence: float = float(
            os.getenv("THRESHOLD_SEXUAL_VIOLENCE", str(profile.sexual_violence))
        )
        self.threshold_nsfw: float = float(
            os.getenv("THRESHOLD_NSFW", str(profile.nsfw))
        )
        self.threshold_deepfake: float = float(
            os.getenv("THRESHOLD_DEEPFAKE", str(profile.deepfake))
        )
        self.threshold_cyberbullying: float = float(
            os.getenv("THRESHOLD_CYBERBULLYING", str(profile.cyberbullying))
        )

        # Deepfake detection provider: openai | ollama | local | sightengine | api | stub
        self.deepfake_provider: str = os.getenv("DEEPFAKE_PROVIDER", "stub")
        self.deepfake_model_path: str = os.getenv("DEEPFAKE_MODEL_PATH", "")

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


settings = Settings()
