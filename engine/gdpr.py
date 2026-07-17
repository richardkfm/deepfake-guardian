"""GDPR compliance service.

Responsibilities
----------------
- ``hash_id(platform, raw_id)`` — pseudonymous SHA-256 + salt hashing so raw
  user/group identifiers are never stored.
- ``run_retention_cleanup(session)`` — delete ModerationEvents whose retention
  window has expired (Article 5(1)(e) — storage limitation).
- ``process_pending_deletions(session)`` — execute pending Article 17 erasure
  requests by removing all data for the requester.

API endpoints (mounted at ``/gdpr``)
-------------------------------------
POST /gdpr/export                     — Article 15 Right of Access
POST /gdpr/delete_request             — Article 17 Right to Erasure (submit)
GET  /gdpr/delete_request/{id}        — erasure request status
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from database import get_session
from db_models import ConsentRecord, DeletionRequest, ModerationEvent, ProtectedImageHash, UserWarning

logger = structlog.get_logger()

gdpr_router = APIRouter(prefix="/gdpr", tags=["gdpr"])


# ---------------------------------------------------------------------------
# Hashing
# ---------------------------------------------------------------------------


def hash_id(platform: str, raw_id: str | int) -> str:
    """Return SHA-256(GDPR_SALT + ":" + platform + ":" + raw_id).

    The secret salt prevents brute-force re-identification of stored hashes
    even if an attacker obtains the database.  The platform prefix ensures
    identical numeric IDs from different platforms produce distinct hashes.
    """
    value = f"{settings.gdpr_salt}:{platform}:{raw_id}"
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Retention cleanup  (Article 5(1)(e) — storage limitation)
# ---------------------------------------------------------------------------


async def run_retention_cleanup(session: AsyncSession) -> int:
    """Delete ModerationEvents whose retention window has expired.

    Returns the number of deleted rows.
    """
    now = datetime.now(tz=timezone.utc)
    result = await session.execute(
        delete(ModerationEvent)
        .where(
            ModerationEvent.expires_at.isnot(None),
            ModerationEvent.expires_at <= now,
        )
        .returning(ModerationEvent.id)
    )
    await session.commit()
    deleted_count = len(result.fetchall())
    if deleted_count:
        logger.info("gdpr_retention_cleanup", deleted_events=deleted_count)
    return deleted_count


# ---------------------------------------------------------------------------
# Pending deletion processor  (Article 17 — Right to Erasure)
# ---------------------------------------------------------------------------


async def process_pending_deletions(session: AsyncSession) -> int:
    """Execute all pending erasure requests.

    Deletes every stored record for the requester and marks the request
    ``completed``.  Returns the number of processed requests.
    """
    pending = (
        await session.execute(
            select(DeletionRequest).where(DeletionRequest.status == "pending")
        )
    ).scalars().all()

    processed = 0
    now = datetime.now(tz=timezone.utc)

    for req in pending:
        await session.execute(
            delete(ModerationEvent).where(ModerationEvent.user_id_hash == req.requester_hash)
        )
        await session.execute(
            delete(UserWarning).where(UserWarning.user_id_hash == req.requester_hash)
        )
        await session.execute(
            delete(ConsentRecord).where(ConsentRecord.user_id_hash == req.requester_hash)
        )
        await session.execute(
            delete(ProtectedImageHash).where(
                ProtectedImageHash.submitter_hash == req.requester_hash
            )
        )
        req.status = "completed"
        req.completed_date = now
        processed += 1

    if processed:
        await session.commit()
        logger.info("gdpr_deletions_processed", count=processed)

    return processed


# ---------------------------------------------------------------------------
# Helper: log a moderation event (called as background task from routes.py)
# ---------------------------------------------------------------------------


async def log_moderation_event(
    platform: str,
    user_id: str | None,
    group_id: str | None,
    content_type: str,
    verdict: str,
    reasons: list[str],
    scores: dict[str, float],
    language: str | None,
) -> None:
    """Persist a ModerationEvent with hashed identifiers.

    Runs as a background task; failures are swallowed so DB issues never
    block moderation responses.
    """
    from database import AsyncSessionLocal  # local import avoids circular dep at module level

    try:
        user_hash = hash_id(platform, user_id) if user_id else None
        group_hash = hash_id(platform, group_id) if group_id else None
        expires_at = datetime.now(tz=timezone.utc) + timedelta(days=settings.data_retention_days)

        event = ModerationEvent(
            platform=platform,
            group_id_hash=group_hash,
            user_id_hash=user_hash,
            content_type=content_type,
            verdict=verdict,
            reasons=json.dumps(reasons),
            score_violence=scores.get("violence", 0.0),
            score_sexual_violence=scores.get("sexual_violence", 0.0),
            score_nsfw=scores.get("nsfw", 0.0),
            score_deepfake=scores.get("deepfake_suspect", 0.0),
            score_cyberbullying=scores.get("cyberbullying", 0.0),
            language=language,
            expires_at=expires_at,
        )
        async with AsyncSessionLocal() as db:
            db.add(event)
            await db.commit()
    except Exception:
        logger.exception("db_event_logging_failed", content_type=content_type)


# ---------------------------------------------------------------------------
# Pydantic request / response models
# ---------------------------------------------------------------------------


class ExportRequest(BaseModel):
    user_id: str
    platform: str = "unknown"


class DeleteRequestBody(BaseModel):
    user_id: str
    platform: str = "unknown"
    notes: str | None = None


class DeleteRequestResponse(BaseModel):
    request_id: int
    status: str
    message: str


# ---------------------------------------------------------------------------
# API endpoints
# ---------------------------------------------------------------------------


@gdpr_router.post("/export")
async def data_export(
    body: ExportRequest,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Article 15 — Right of Access: export all stored data for a user.

    The raw ``user_id`` is hashed inside the engine; only the hash is ever
    stored or returned.
    """
    user_hash = hash_id(body.platform, body.user_id)

    events = (
        await session.execute(
            select(ModerationEvent).where(ModerationEvent.user_id_hash == user_hash)
        )
    ).scalars().all()

    user_warnings = (
        await session.execute(
            select(UserWarning).where(UserWarning.user_id_hash == user_hash)
        )
    ).scalars().all()

    deletion_requests = (
        await session.execute(
            select(DeletionRequest).where(DeletionRequest.requester_hash == user_hash)
        )
    ).scalars().all()

    return {
        "user_id_hash": user_hash,
        "moderation_events": [
            {
                "id": e.id,
                "timestamp": e.timestamp.isoformat() if e.timestamp else None,
                "platform": e.platform,
                "content_type": e.content_type,
                "verdict": e.verdict,
                "reasons": json.loads(e.reasons) if e.reasons else [],
                "language": e.language,
            }
            for e in events
        ],
        "warning_records": [
            {
                "id": w.id,
                "group_id_hash": w.group_id_hash,
                "warning_count": w.warning_count,
                "last_warning": w.last_warning.isoformat() if w.last_warning else None,
            }
            for w in user_warnings
        ],
        "deletion_requests": [
            {
                "id": d.id,
                "request_date": d.request_date.isoformat() if d.request_date else None,
                "status": d.status,
                "completed_date": d.completed_date.isoformat() if d.completed_date else None,
            }
            for d in deletion_requests
        ],
    }


@gdpr_router.post("/delete_request", response_model=DeleteRequestResponse)
async def submit_delete_request(
    body: DeleteRequestBody,
    session: AsyncSession = Depends(get_session),
) -> DeleteRequestResponse:
    """Article 17 — Right to Erasure: submit a data deletion request.

    The raw ``user_id`` is hashed before the request record is created.
    A startup job processes all pending requests automatically.
    """
    user_hash = hash_id(body.platform, body.user_id)

    existing = (
        await session.execute(
            select(DeletionRequest).where(
                DeletionRequest.requester_hash == user_hash,
                DeletionRequest.status == "pending",
            )
        )
    ).scalar_one_or_none()

    if existing:
        return DeleteRequestResponse(
            request_id=existing.id,
            status=existing.status,
            message="A deletion request is already pending. Data will be erased within 30 days.",
        )

    req = DeletionRequest(
        requester_hash=user_hash,
        platform=body.platform,
        notes=body.notes,
    )
    session.add(req)
    await session.commit()
    await session.refresh(req)

    logger.info("gdpr_delete_request_submitted", request_id=req.id, platform=body.platform)

    return DeleteRequestResponse(
        request_id=req.id,
        status=req.status,
        message="Deletion request submitted. Your data will be erased within 30 days.",
    )


@gdpr_router.get("/delete_request/{request_id}")
async def get_delete_request_status(
    request_id: int,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Check the status of an erasure request by ID."""
    req = (
        await session.execute(
            select(DeletionRequest).where(DeletionRequest.id == request_id)
        )
    ).scalar_one_or_none()

    if req is None:
        raise HTTPException(status_code=404, detail="Deletion request not found")

    return {
        "request_id": req.id,
        "status": req.status,
        "request_date": req.request_date.isoformat() if req.request_date else None,
        "completed_date": req.completed_date.isoformat() if req.completed_date else None,
    }
