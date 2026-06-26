"""Pydantic models for API request / response schemas."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Request bodies
# ---------------------------------------------------------------------------

class TextRequest(BaseModel):
    text: str = Field(..., min_length=1, description="Plain text to moderate")
    language: str | None = Field(
        None, description="Optional language hint (ISO 639-1, e.g. 'en', 'de')"
    )
    # Optional audit context — hashed by the engine before storage (never persisted raw)
    user_id: str | None = Field(None, description="Platform user ID for audit logging")
    group_id: str | None = Field(None, description="Platform group/chat ID for audit logging")
    platform: str = Field("unknown", description="Platform identifier (e.g. 'telegram')")


class ImageRequest(BaseModel):
    image_base64: str | None = Field(None, description="Base64-encoded image data")
    image_url: str | None = Field(None, description="Public URL of the image")
    user_id: str | None = Field(None, description="Platform user ID for audit logging")
    group_id: str | None = Field(None, description="Platform group/chat ID for audit logging")
    platform: str = Field("unknown", description="Platform identifier (e.g. 'telegram')")


class VideoRequest(BaseModel):
    video_base64: str | None = Field(None, description="Base64-encoded video data")
    video_url: str | None = Field(None, description="Public URL of the video")
    user_id: str | None = Field(None, description="Platform user ID for audit logging")
    group_id: str | None = Field(None, description="Platform group/chat ID for audit logging")
    platform: str = Field("unknown", description="Platform identifier (e.g. 'telegram')")


# ---------------------------------------------------------------------------
# Response
# ---------------------------------------------------------------------------

class ModerationScores(BaseModel):
    violence: float = Field(0.0, ge=0.0, le=1.0)
    sexual_violence: float = Field(0.0, ge=0.0, le=1.0)
    nsfw: float = Field(0.0, ge=0.0, le=1.0)
    deepfake_suspect: float = Field(0.0, ge=0.0, le=1.0)
    cyberbullying: float = Field(0.0, ge=0.0, le=1.0)
    # Scores for opt-in moderation categories (e.g. advertising), keyed by
    # skill id.  Empty unless those categories are enabled via ENABLED_CATEGORIES.
    extra: dict[str, float] = Field(default_factory=dict)


class ModerationResult(BaseModel):
    verdict: Literal["allow", "delete", "flag"]
    reasons: list[str] = Field(default_factory=list)
    scores: ModerationScores = Field(default_factory=ModerationScores)  # type: ignore[arg-type]
    language: str | None = Field(None, description="Detected language code (ISO 639-1)")
