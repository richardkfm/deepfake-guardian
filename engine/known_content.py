"""Known non-consensual intimate imagery (NCII) hash matching.

Mirrors the StopNCII.org model: a victim (or an admin acting on their
behalf) submits an image; the engine stores only a perceptual hash of it,
never the image itself. Every future ``/moderate_image`` and
``/moderate_video`` call perceptually hashes the incoming media and checks
it against the stored hashes — a close match (small Hamming distance, so it
still catches re-crops/re-encodes/re-compressions of the same photo) forces
a ``delete`` verdict regardless of what the ML classifiers scored it.

This is opt-in (``KNOWN_IMAGE_HASH_MATCHING``) because it only does anything
useful once operators have actually populated the protected-hash list, and
it adds a dependency (``ImageHash``).

API endpoints (mounted at ``/protected_images``)
-------------------------------------------------
POST   /protected_images        — submit an image to protect (hash-only storage)
DELETE /protected_images/{id}   — remove a protected hash (submitter-only)
"""
from __future__ import annotations

from typing import Any

import imagehash
import structlog
from fastapi import APIRouter, Depends, HTTPException
from PIL import Image
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_session
from db_models import ProtectedImageHash
from gdpr import hash_id

logger = structlog.get_logger()

protected_images_router = APIRouter(prefix="/protected_images", tags=["protected_images"])


# ---------------------------------------------------------------------------
# Hashing / matching
# ---------------------------------------------------------------------------


def compute_phash(image: Image.Image) -> str:
    """Return the perceptual hash of *image* as a hex string."""
    return str(imagehash.phash(image))


def hamming_distance(hash_a: str, hash_b: str) -> int:
    """Return the Hamming distance between two hex-encoded phashes."""
    return imagehash.hex_to_hash(hash_a) - imagehash.hex_to_hash(hash_b)


async def find_match(
    session: AsyncSession, image: Image.Image, threshold: int
) -> ProtectedImageHash | None:
    """Return the first stored protected hash within *threshold* of *image*, if any.

    Compares against every stored ``phash`` row. Fine for the scale this
    feature targets (a group's/community's own protected-image list — tens
    to low hundreds of entries), not a web-scale hash index.
    """
    candidate = imagehash.phash(image)
    rows = (
        await session.execute(
            select(ProtectedImageHash).where(ProtectedImageHash.hash_type == "phash")
        )
    ).scalars().all()

    for row in rows:
        distance = candidate - imagehash.hex_to_hash(row.hash_hex)
        if distance <= threshold:
            return row
    return None


# ---------------------------------------------------------------------------
# Pydantic request / response models
# ---------------------------------------------------------------------------


class SubmitProtectedImageRequest(BaseModel):
    image_base64: str | None = Field(None, description="Base64-encoded image data")
    image_url: str | None = Field(None, description="Public URL of the image")
    user_id: str = Field(..., description="Submitter's platform user ID (hashed before storage)")
    platform: str = Field("unknown", description="Platform identifier (e.g. 'telegram')")
    note: str | None = Field(None, description="Optional free-text note (never the image itself)")


class ProtectedImageResponse(BaseModel):
    id: int
    hash_type: str
    message: str


class DeleteProtectedImageRequest(BaseModel):
    user_id: str = Field(..., description="Must match the original submitter")
    platform: str = Field("unknown")


# ---------------------------------------------------------------------------
# API endpoints
# ---------------------------------------------------------------------------


@protected_images_router.post("", response_model=ProtectedImageResponse)
async def submit_protected_image(
    body: SubmitProtectedImageRequest,
    session: AsyncSession = Depends(get_session),
) -> ProtectedImageResponse:
    """Register an image for proactive NCII protection.

    Only a perceptual hash of the image is computed and stored — the image
    itself is discarded immediately after hashing and never persisted.
    """
    from classifiers import decode_image

    image = decode_image(body.image_base64, body.image_url)
    if image is None:
        raise HTTPException(status_code=400, detail="Provide image_base64 or image_url")

    submitter_hash = hash_id(body.platform, body.user_id)
    row = ProtectedImageHash(
        hash_hex=compute_phash(image),
        hash_type="phash",
        submitter_hash=submitter_hash,
        platform=body.platform,
        note=body.note,
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)

    logger.info(
        "protected_image_registered",
        id=row.id,
        submitter_hash=submitter_hash[:8] + "…",
        platform=body.platform,
    )

    return ProtectedImageResponse(
        id=row.id,
        hash_type=row.hash_type,
        message="Image registered for protection. Future uploads matching it will be deleted automatically.",
    )


@protected_images_router.delete("/{protected_id}")
async def delete_protected_image(
    protected_id: int,
    body: DeleteProtectedImageRequest,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Remove a protected hash. Only the original submitter may delete it."""
    submitter_hash = hash_id(body.platform, body.user_id)

    row = (
        await session.execute(
            select(ProtectedImageHash).where(
                ProtectedImageHash.id == protected_id,
                ProtectedImageHash.submitter_hash == submitter_hash,
            )
        )
    ).scalar_one_or_none()

    if row is None:
        # Don't distinguish "not found" from "not yours" — avoid leaking existence.
        raise HTTPException(status_code=404, detail="Protected image not found")

    await session.delete(row)
    await session.commit()

    logger.info("protected_image_deleted", id=protected_id)

    return {"id": protected_id, "status": "deleted"}
