"""Telegram bot configuration."""

from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()


def _float_env(name: str, default: float) -> float:
    """Read a non-negative float from the environment, falling back on bad input."""
    raw = os.getenv(name, "")
    if not raw.strip():
        return default
    try:
        value = float(raw)
    except ValueError:
        return default
    return value if value >= 0 else default


class Settings:
    bot_token: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    engine_url: str = os.getenv("ENGINE_URL", "http://localhost:8000")
    engine_api_key: str = os.getenv("ENGINE_API_KEY", "")
    log_level: str = os.getenv("LOG_LEVEL", "info")
    # Language for admin notification messages ("en" or "de")
    bot_language: str = os.getenv("BOT_LANGUAGE", "en")
    # Per-request timeout for engine calls. Video moderation is the slow path.
    engine_timeout_seconds: float = _float_env("ENGINE_TIMEOUT_SECONDS", 60.0)
    # Media larger than this is not downloaded (the Telegram Bot API cannot
    # download files over 20 MB anyway); its thumbnail is moderated instead.
    max_media_mb: float = _float_env("MAX_MEDIA_MB", 20.0)
    # Minimum seconds between two @-mentions of the admins in the same chat.
    # Notices are still posted during the cooldown, just without pinging every
    # admin again. Supervisor escalations always mention. 0 disables.
    admin_mention_cooldown_seconds: float = _float_env("ADMIN_MENTION_COOLDOWN_SECONDS", 60.0)


settings = Settings()
