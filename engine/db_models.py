"""SQLAlchemy ORM models for GDPR-compliant audit storage.

Design principles (Article 5 GDPR):
- No raw message content is ever stored — only metadata and category scores.
- User/group identifiers are stored as SHA-256 hashes (pseudonymisation).
- Every ModerationEvent carries an ``expires_at`` timestamp; a startup job
  deletes rows past their retention window (default 30 days).
"""
from __future__ import annotations

import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class ModerationEvent(Base):
    """Audit log for a single moderation decision.

    Content is *never* stored — only the verdict, category scores, and
    hashed context identifiers.  ``expires_at`` enables automatic deletion.
    """

    __tablename__ = "moderation_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    platform: Mapped[str] = mapped_column(String(32), nullable=False, default="unknown")
    group_id_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    user_id_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    content_type: Mapped[str] = mapped_column(String(16), nullable=False)  # text | image | video
    verdict: Mapped[str] = mapped_column(String(16), nullable=False)       # allow | flag | delete
    reasons: Mapped[str] = mapped_column(Text, nullable=False, default="[]")  # JSON-encoded list
    score_violence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    score_sexual_violence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    score_nsfw: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    score_deepfake: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    score_cyberbullying: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    language: Mapped[Optional[str]] = mapped_column(String(8), nullable=True)
    expires_at: Mapped[Optional[datetime.datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )


class UserWarning(Base):
    """Running violation counter for a (user, group) pair.

    One row per user–group combination.  ``warning_count`` increments on
    every violation.  ``level`` mirrors the current escalation tier
    (1 = notice, 2 = admin notification, 3+ = supervisor escalation).
    """

    __tablename__ = "user_warnings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    group_id_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    platform: Mapped[str] = mapped_column(String(32), nullable=False, default="unknown")
    warning_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_warning: Mapped[Optional[datetime.datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    level: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class ConsentRecord(Base):
    """GDPR consent tracking (Article 6 — lawful basis for processing).

    Created when a user acknowledges the bot's privacy notice.
    The absence of a record means the user has not yet been shown the notice.
    """

    __tablename__ = "consent_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    group_id_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    platform: Mapped[str] = mapped_column(String(32), nullable=False, default="unknown")
    consent_given: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    consent_date: Mapped[Optional[datetime.datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    consent_scope: Mapped[str] = mapped_column(
        Text, nullable=False, default="moderation_logging"
    )


class ProtectedImageHash(Base):
    """A perceptual hash of an image a victim/admin wants proactively blocked.

    Mirrors the StopNCII.org model for non-consensual intimate imagery
    (NCII): only a perceptual hash of the image is stored, never the image
    itself, so a matching upload can be detected and deleted without the
    engine ever holding the sensitive content. Rows persist until the
    submitter deletes them (or exercises Article 17 erasure) — unlike
    :class:`ModerationEvent`, this is protective data the submitter opted
    into keeping, not an audit log subject to the retention window.
    """

    __tablename__ = "protected_image_hashes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    hash_hex: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    hash_type: Mapped[str] = mapped_column(String(16), nullable=False, default="phash")
    submitter_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    platform: Mapped[str] = mapped_column(String(32), nullable=False, default="unknown")
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class DeletionRequest(Base):
    """Article 17 — Right to Erasure request.

    Submitted via ``/delete_my_data`` (bot command) or ``POST /gdpr/delete_request``.
    A startup background job processes ``pending`` requests and marks them
    ``completed`` after erasing all stored data for the requester.
    """

    __tablename__ = "deletion_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    requester_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    platform: Mapped[str] = mapped_column(String(32), nullable=False, default="unknown")
    request_date: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="pending"
    )  # pending | completed
    completed_date: Mapped[Optional[datetime.datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
