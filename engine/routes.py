"""FastAPI route handlers for the moderation engine."""
from __future__ import annotations

import structlog
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from PIL import Image
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from classifiers import (
    classify_image,
    classify_text,
    decode_image_frames,
    detect_deepfake_suspect,
    score_deepfake_sexual_violence,
)
from database import get_session
from gdpr import log_moderation_event
from models import (
    ImageRequest,
    ModerationResult,
    ModerationScores,
    TextRequest,
    VideoRequest,
)
from verdict import decide

logger = structlog.get_logger()
router = APIRouter()


# ---------------------------------------------------------------------------
# Helper: known-NCII-hash override
# ---------------------------------------------------------------------------


async def _apply_known_hash_override(
    session: AsyncSession, images: list[Image.Image], result: ModerationResult
) -> ModerationResult:
    """Force a "delete" verdict if any image matches a protected NCII hash.

    No-op unless ``KNOWN_IMAGE_HASH_MATCHING`` is enabled — see config.py.
    A match is a strong, victim/admin-confirmed signal, so it overrides the
    ML-derived verdict rather than merely nudging a score.
    """
    from config import settings

    if not settings.known_image_hash_matching:
        return result

    from known_content import find_match

    for image in images:
        match = await find_match(session, image, settings.known_image_hash_threshold)
        if match is not None:
            logger.info("known_ncii_hash_match", protected_id=match.id)
            reasons = list(dict.fromkeys([*result.reasons, "known_ncii_match"]))
            return result.model_copy(update={"verdict": "delete", "reasons": reasons})
    return result


# ---------------------------------------------------------------------------
# Helper: per-image visual analysis (runs in a worker thread)
# ---------------------------------------------------------------------------


def _analyse_still_image(image: Image.Image) -> dict[str, float]:
    """Classify one image and score deepfake-sexual-violence (CPU / blocking IO)."""
    img_scores = classify_image(image)
    deepfake_score = detect_deepfake_suspect(image)
    return {
        "violence": img_scores["violence"],
        "sexual_violence": max(
            img_scores["sexual_violence"],
            score_deepfake_sexual_violence(img_scores["nsfw"], deepfake_score),
        ),
        "nsfw": img_scores["nsfw"],
        "deepfake_suspect": deepfake_score,
    }


def _analyse_image_frames(frames: list[Image.Image]) -> dict[str, float]:
    """Analyse a still image, or every sampled frame of an animated one."""
    if len(frames) == 1:
        return _analyse_still_image(frames[0])
    from video_processing import moderate_video_frames

    return moderate_video_frames(frames)


# ---------------------------------------------------------------------------
# Helper: build score dict for audit logging
# ---------------------------------------------------------------------------


def _score_dict(scores: ModerationScores) -> dict[str, float]:
    return {
        "violence": scores.violence,
        "sexual_violence": scores.sexual_violence,
        "nsfw": scores.nsfw,
        "deepfake_suspect": scores.deepfake_suspect,
        "cyberbullying": scores.cyberbullying,
        **scores.extra,
    }


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/moderate_text", response_model=ModerationResult)
async def moderate_text(
    request: Request, req: TextRequest, background_tasks: BackgroundTasks
) -> ModerationResult:
    """Classify plain text and return a moderation verdict."""
    from config import settings
    from i18n.detector import detect_language
    from moderation.registry import ModerationRegistry

    lang_code = req.language or detect_language(req.text)
    text_scores = classify_text(req.text, lang_code)

    # Opt-in categories (advertising, political misinformation, …) — empty
    # unless enabled via ENABLED_CATEGORIES.
    extra = ModerationRegistry.score_text_categories(
        req.text, lang_code, settings.enabled_categories
    )

    scores = ModerationScores(
        violence=text_scores["violence"],
        sexual_violence=text_scores["sexual_violence"],
        nsfw=text_scores["nsfw"],
        deepfake_suspect=0.0,
        cyberbullying=text_scores.get("cyberbullying", 0.0),
        extra=extra,
    )
    result = decide(scores)
    result = result.model_copy(update={"language": lang_code})
    logger.info(
        "text_moderation",
        verdict=result.verdict,
        reasons=result.reasons,
        language=lang_code,
        text_preview=req.text[:80],
    )

    if req.user_id or req.group_id:
        background_tasks.add_task(
            log_moderation_event,
            req.platform,
            req.user_id,
            req.group_id,
            "text",
            result.verdict,
            result.reasons,
            _score_dict(scores),
            lang_code,
        )

    return result


@router.post("/moderate_image", response_model=ModerationResult)
async def moderate_image(
    request: Request,
    req: ImageRequest,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
) -> ModerationResult:
    """Classify an image and return a moderation verdict.

    Animated images (GIF / WebP / APNG) are analysed frame by frame, like a
    video, so harmful content can't hide behind an innocuous first frame.
    """
    from config import settings
    from media import MediaDecodeError

    if not req.image_base64 and not req.image_url:
        raise HTTPException(status_code=400, detail="Provide image_base64 or image_url")

    try:
        # Decoding (and any URL download) and the ML models are blocking:
        # keep them off the event loop so one slow image or remote deepfake
        # provider call doesn't stall every other request.
        frames = await run_in_threadpool(
            decode_image_frames, req.image_base64, req.image_url, settings.max_frames
        )
    except MediaDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"Could not decode image: {exc}") from exc
    if not frames:
        raise HTTPException(status_code=400, detail="Provide image_base64 or image_url")

    frame_scores = await run_in_threadpool(_analyse_image_frames, frames)

    scores = ModerationScores(
        violence=frame_scores["violence"],
        sexual_violence=frame_scores["sexual_violence"],
        nsfw=frame_scores["nsfw"],
        deepfake_suspect=frame_scores["deepfake_suspect"],
        cyberbullying=0.0,
    )
    result = decide(scores)
    result = await _apply_known_hash_override(session, frames, result)
    logger.info(
        "image_moderation",
        verdict=result.verdict,
        reasons=result.reasons,
        frames_analysed=len(frames),
    )

    if req.user_id or req.group_id:
        background_tasks.add_task(
            log_moderation_event,
            req.platform,
            req.user_id,
            req.group_id,
            "image",
            result.verdict,
            result.reasons,
            _score_dict(scores),
            None,
        )

    return result


@router.post("/moderate_video", response_model=ModerationResult)
async def moderate_video(
    request: Request,
    req: VideoRequest,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
) -> ModerationResult:
    """Classify a video by sampling frames and aggregating scores."""
    if not req.video_base64 and not req.video_url:
        raise HTTPException(status_code=400, detail="Provide video_base64 or video_url")

    from video_processing import decode_video, extract_frames, moderate_video_frames

    try:
        video_data = await run_in_threadpool(decode_video, req.video_base64, req.video_url)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Could not decode video: {exc}") from exc

    frames = await run_in_threadpool(extract_frames, video_data)
    del video_data  # don't keep the raw upload alive for the rest of the request

    if not frames:
        logger.warning("video_moderation: no frames extracted — returning allow")
        frame_scores = {
            "violence": 0.0,
            "sexual_violence": 0.0,
            "nsfw": 0.0,
            "deepfake_suspect": 0.0,
        }
    else:
        frame_scores = await run_in_threadpool(moderate_video_frames, frames)

    scores = ModerationScores(
        violence=frame_scores["violence"],
        sexual_violence=frame_scores["sexual_violence"],
        nsfw=frame_scores["nsfw"],
        deepfake_suspect=frame_scores["deepfake_suspect"],
        cyberbullying=0.0,
    )
    result = decide(scores)
    result = await _apply_known_hash_override(session, frames, result)
    logger.info(
        "video_moderation",
        verdict=result.verdict,
        reasons=result.reasons,
        frames_analysed=len(frames),
    )

    if req.user_id or req.group_id:
        background_tasks.add_task(
            log_moderation_event,
            req.platform,
            req.user_id,
            req.group_id,
            "video",
            result.verdict,
            result.reasons,
            _score_dict(scores),
            None,
        )

    return result
