"""Known non-consensual intimate imagery (NCII) hash matching.

Mirrors the StopNCII.org model: a victim (or an admin acting on their
behalf) submits an image; the engine stores only perceptual hashes of it,
never the image itself. Every future ``/moderate_image`` and
``/moderate_video`` call perceptually hashes the incoming media and checks
it against the stored hashes — a close match (small Hamming distance) forces
a ``delete`` verdict regardless of what the ML classifiers scored it.

What a match survives:

* always — re-encodes / re-compression, resizes, greyscale conversion, EXIF
  rotation (images are canonicalised by :mod:`media` first), small crops
  (~5-10%), and added uniform borders (letterbox / pillarbox / padding,
  e.g. a photo turned into a 16:9 video), which are trimmed before hashing;
* with ``KNOWN_IMAGE_HASH_ROBUST_MATCHING`` — additionally mirrored copies
  and centre re-crops down to ~60% of each side (centre-crop hashes are
  stored at registration).

It does *not* survive heavy one-sided crops, 90° rotations of the pixels,
or the image embedded in a larger collage/screenshot.

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

import httpx
import imagehash
import structlog
from fastapi import APIRouter, Depends, HTTPException
from PIL import Image, ImageChops, ImageStat
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from database import get_session
from db_models import ProtectedImageHash
from gdpr import hash_id

logger = structlog.get_logger()

protected_images_router = APIRouter(prefix="/protected_images", tags=["protected_images"])


# ---------------------------------------------------------------------------
# Hashing / matching
# ---------------------------------------------------------------------------

#: Legacy rows: ``hash_hex`` is a single 64-bit phash (16 hex chars).
HASH_TYPE_SINGLE = "phash"
#: Current rows: ``hash_hex`` is up to four concatenated 16-hex-char phashes —
#: the full image first, then centre crops (see :data:`CROP_KEEP_RATIOS`).
#: Code that predates this type filters on ``hash_type == "phash"`` and so
#: simply ignores these rows instead of mis-parsing them.
HASH_TYPE_SET = "phash_set"
_HEX_LEN = 16

#: Centre-crop variants hashed at registration (fraction of each side kept).
#: A plain phash stops matching once roughly 10% is cropped off; with these
#: stored too, robust matching still catches centre re-crops down to ~60% of
#: each side.
CROP_KEEP_RATIOS = (0.88, 0.76, 0.64)

#: Hamming-distance ceiling. Unrelated images sit around 32 (half the bits),
#: so anything larger would start deleting arbitrary uploads.
MAX_THRESHOLD = 32
_WARN_THRESHOLD = 20

#: Images whose 32x32 greyscale thumbnail has less spread than this are
#: "low information" (blank, flat colour, a 1x1 pixel): their phash collapses
#: to ``8000000000000000`` regardless of colour, so a protected flat image
#: would match every other flat image and every blank video frame.
_MIN_THUMB_STDDEV = 2.0

#: Border trimming: a pixel is "border" if within this grey-level distance of
#: the top-left corner; trim only when what's left is still a substantial part
#: of the image, and only when it removes more than 2% of the area.
_BORDER_TOLERANCE = 16
_MIN_TRIM_KEEP = 0.25
_MIN_TRIM_GAIN = 0.02
_TRIM_ANALYSIS_SIDE = 256


def compute_phash(image: Image.Image) -> str:
    """Return the perceptual hash of *image* as a hex string."""
    return str(imagehash.phash(image))


def hamming_distance(hash_a: str, hash_b: str) -> int:
    """Return the Hamming distance between two hex-encoded phashes."""
    return imagehash.hex_to_hash(hash_a) - imagehash.hex_to_hash(hash_b)


def is_low_information(image: Image.Image) -> bool:
    """True when *image* is too flat for its perceptual hash to mean anything."""
    thumb = image.convert("L").resize((32, 32), Image.Resampling.LANCZOS)
    return bool(ImageStat.Stat(thumb).stddev[0] < _MIN_THUMB_STDDEV)


def _is_degenerate_hash(h: imagehash.ImageHash) -> bool:
    """A phash with (almost) no bits set, or all of them — a flat image's signature."""
    bits = int(h.hash.sum())
    return bits <= 2 or bits >= h.hash.size - 2


def trim_uniform_border(image: Image.Image) -> Image.Image | None:
    """Crop away a uniform border (letterbox / pillarbox / padding), if any.

    Re-shares commonly add bars — a portrait photo padded to 16:9 for a video
    or story, a screenshot's solid margin — which shift a phash well past the
    match threshold. Returns ``None`` when there's no meaningful border.
    """
    gray = image.convert("L")
    scale = max(gray.size) / _TRIM_ANALYSIS_SIDE
    if scale > 1:
        small = gray.resize((max(1, round(gray.width / scale)), max(1, round(gray.height / scale))))
    else:
        scale = 1.0
        small = gray
    corner = small.getpixel((0, 0))
    background = Image.new("L", small.size, corner)  # type: ignore[arg-type]
    mask = ImageChops.difference(small, background).point(
        lambda p: 255 if p > _BORDER_TOLERANCE else 0
    )
    bbox = mask.getbbox()
    if bbox is None:
        return None
    left, top, right, bottom = bbox
    kept_w = (right - left) / small.width
    kept_h = (bottom - top) / small.height
    if kept_w < _MIN_TRIM_KEEP or kept_h < _MIN_TRIM_KEEP:
        return None
    if kept_w * kept_h > 1.0 - _MIN_TRIM_GAIN:
        return None
    box = (
        int(left * scale),
        int(top * scale),
        min(image.width, round(right * scale)),
        min(image.height, round(bottom * scale)),
    )
    return image.crop(box)


def _centre_crop(image: Image.Image, keep: float) -> Image.Image:
    w, h = image.size
    cw, ch = max(1, int(w * keep)), max(1, int(h * keep))
    left, top = (w - cw) // 2, (h - ch) // 2
    return image.crop((left, top, left + cw, top + ch))


def compute_protected_hash_set(image: Image.Image) -> str:
    """Hash the full image plus its centre-crop variants, concatenated (64 hex chars)."""
    hashes = [compute_phash(image)]
    hashes += [compute_phash(_centre_crop(image, keep)) for keep in CROP_KEEP_RATIOS]
    return "".join(hashes)


def _stored_hashes(row: ProtectedImageHash, robust: bool) -> list[imagehash.ImageHash]:
    """Parse a row's hash(es): only the full-image hash unless *robust*.

    Unparseable, wrongly sized or degenerate hashes are skipped (and logged)
    rather than failing the moderation request.
    """
    hex_value = row.hash_hex or ""
    if row.hash_type == HASH_TYPE_SET:
        chunks = [hex_value[i:i + _HEX_LEN] for i in range(0, len(hex_value), _HEX_LEN)]
    else:
        chunks = [hex_value]
    if not robust:
        chunks = chunks[:1]

    parsed: list[imagehash.ImageHash] = []
    for chunk in chunks:
        try:
            h = imagehash.hex_to_hash(chunk)
        except (ValueError, TypeError):
            logger.warning("protected_hash_unparseable", protected_id=row.id)
            continue
        if h.hash.size != 64:
            logger.warning("protected_hash_wrong_size", protected_id=row.id)
            continue
        if _is_degenerate_hash(h):
            # Registered before low-information images were rejected: it
            # would match every blank frame, so it must never delete anything.
            logger.warning("protected_hash_degenerate_skipped", protected_id=row.id)
            continue
        parsed.append(h)
    return parsed


def candidate_hashes(images: list[Image.Image], robust: bool = False) -> list[imagehash.ImageHash]:
    """Hashes to look up for incoming media.

    Always: each image as-is, plus the image with any uniform border trimmed.
    With *robust*: the mirrored version of each of those too. Low-information
    images (blank / flat frames) contribute nothing — they can't be NCII and
    their degenerate hash would only produce false matches.
    """
    hashes: list[imagehash.ImageHash] = []
    seen: set[str] = set()
    for image in images:
        if is_low_information(image):
            continue
        variants = [image]
        trimmed = trim_uniform_border(image)
        if trimmed is not None and not is_low_information(trimmed):
            variants.append(trimmed)
        if robust:
            variants += [v.transpose(Image.Transpose.FLIP_LEFT_RIGHT) for v in list(variants)]
        for variant in variants:
            h = imagehash.phash(variant)
            key = str(h)
            if key not in seen and not _is_degenerate_hash(h):
                seen.add(key)
                hashes.append(h)
    return hashes


def effective_threshold(threshold: int) -> int:
    """Clamp a configured Hamming threshold to ``[0, MAX_THRESHOLD]``."""
    if threshold > MAX_THRESHOLD:
        logger.warning(
            "known_image_hash_threshold_clamped", configured=threshold, used=MAX_THRESHOLD
        )
        return MAX_THRESHOLD
    if threshold > _WARN_THRESHOLD:
        logger.warning("known_image_hash_threshold_high", configured=threshold)
    return max(0, threshold)


async def find_match_any(
    session: AsyncSession,
    images: list[Image.Image],
    threshold: int,
    *,
    robust: bool = False,
) -> ProtectedImageHash | None:
    """Return the closest stored protected hash within *threshold* of any image.

    Loads the protected list once for all *images* (e.g. every sampled video
    frame) rather than once per image. Compares O(rows x variants) — fine
    for the scale this feature targets (a group's/community's own
    protected-image list — tens to low hundreds of entries), not a web-scale
    hash index.
    """
    if not images:
        return None

    limit = effective_threshold(threshold)
    candidates = await run_in_threadpool(candidate_hashes, images, robust)
    if not candidates:
        return None

    rows = (
        await session.execute(
            select(ProtectedImageHash).where(
                ProtectedImageHash.hash_type.in_([HASH_TYPE_SINGLE, HASH_TYPE_SET])
            )
        )
    ).scalars().all()

    best: tuple[int, ProtectedImageHash] | None = None
    for row in rows:
        for stored in _stored_hashes(row, robust):
            for candidate in candidates:
                distance = candidate - stored
                if distance <= limit and (best is None or distance < best[0]):
                    best = (distance, row)
    if best is None:
        return None
    logger.info("known_ncii_hash_distance", protected_id=best[1].id, distance=best[0])
    return best[1]


async def find_match(
    session: AsyncSession, image: Image.Image, threshold: int, *, robust: bool = False
) -> ProtectedImageHash | None:
    """Return the closest stored protected hash within *threshold* of *image*, if any."""
    return await find_match_any(session, [image], threshold, robust=robust)


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

    Only perceptual hashes of the image are computed and stored — the image
    itself is discarded immediately after hashing and never persisted.
    """
    from media import MediaDecodeError, decode_base64, decode_image_bytes
    from routes import MediaFetchError, fetch_media_url

    if not body.image_base64 and not body.image_url:
        raise HTTPException(status_code=400, detail="Provide image_base64 or image_url")
    try:
        if body.image_base64:
            data = decode_base64(body.image_base64)
        else:
            assert body.image_url is not None
            # Same SSRF-checked, size-capped fetch as /moderate_image.
            data = await fetch_media_url(body.image_url, timeout=30)
        image = await run_in_threadpool(decode_image_bytes, data)
    except MediaFetchError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    except (MediaDecodeError, httpx.HTTPError) as exc:
        raise HTTPException(status_code=400, detail=f"Could not decode image: {exc}") from exc
    del data
    if is_low_information(image):
        # A blank / flat image's hash would match every other blank image and
        # blank video frame — refuse it rather than mass-delete later.
        raise HTTPException(
            status_code=400, detail="Image has too little detail to be matched reliably"
        )

    hash_hex = await run_in_threadpool(compute_protected_hash_set, image)
    del image  # only the hashes are kept — never the image

    submitter_hash = hash_id(body.platform, body.user_id)
    row = ProtectedImageHash(
        hash_hex=hash_hex,
        hash_type=HASH_TYPE_SET,
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
        # The algorithm is still phash; the row merely carries crop variants too.
        hash_type=HASH_TYPE_SINGLE,
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
