"""FastAPI route handlers for the moderation engine."""
from __future__ import annotations

import asyncio
import io
import ipaddress
import socket

import httpx
import structlog
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from PIL import Image
from sqlalchemy.ext.asyncio import AsyncSession

from classifiers import (
    classify_image,
    classify_text,
    decode_image,
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
# Helper: SSRF-safe media URL fetching
# ---------------------------------------------------------------------------

_MAX_REDIRECTS = 5
# Overridable in tests (httpx.MockTransport); None = real network transport.
_media_transport: httpx.AsyncBaseTransport | None = None


class MediaFetchError(Exception):
    """A client-supplied media URL could not (or must not) be fetched."""

    def __init__(self, detail: str, status_code: int = 400) -> None:
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code


async def _resolve_host(host: str, port: int) -> list[str]:
    """Return every IP address *host* resolves to (IP literals map to themselves)."""
    infos = await asyncio.get_running_loop().getaddrinfo(
        host, port, type=socket.SOCK_STREAM
    )
    return [str(info[4][0]) for info in infos]


def _is_public_address(raw: str) -> bool:
    addr: ipaddress.IPv4Address | ipaddress.IPv6Address = ipaddress.ip_address(raw)
    if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped is not None:
        addr = addr.ipv4_mapped
    return addr.is_global and not addr.is_multicast


async def _validate_media_url(url: httpx.URL) -> None:
    """Reject non-HTTP(S) URLs and URLs whose host resolves to a non-public IP.

    Prevents ``image_url`` / ``video_url`` from being used to probe or read
    internal services (cloud metadata endpoints, a local Ollama, the Docker
    network, …).  Every redirect hop is re-validated by the caller.  Note:
    httpx resolves the name again when connecting, so a DNS-rebinding
    attacker with a very short TTL is not fully excluded.
    """
    from config import settings

    if url.scheme not in ("http", "https"):
        raise MediaFetchError(f"Media URL scheme '{url.scheme}' is not allowed")
    host = url.host
    if not host:
        raise MediaFetchError("Media URL has no host and is not allowed")
    if settings.media_url_allow_private:
        return
    port = url.port or (443 if url.scheme == "https" else 80)
    try:
        addresses = await _resolve_host(host, port)
    except OSError as exc:
        raise MediaFetchError(f"Could not resolve media URL host: {exc}") from exc
    if not addresses or not all(_is_public_address(a) for a in addresses):
        raise MediaFetchError(
            "Media URL points to a private or reserved address, which is not allowed"
        )


async def fetch_media_url(url: str, timeout: float) -> bytes:
    """Download *url* with SSRF checks on every hop and a size cap.

    Raises :class:`MediaFetchError` for disallowed/oversized/failed fetches.
    """
    from config import settings

    max_bytes = settings.max_media_bytes
    try:
        current = httpx.URL(url)
    except httpx.InvalidURL as exc:
        raise MediaFetchError(f"Invalid media URL: {exc}") from exc

    async with httpx.AsyncClient(
        timeout=timeout, follow_redirects=False, transport=_media_transport
    ) as client:
        for _ in range(_MAX_REDIRECTS + 1):
            await _validate_media_url(current)
            async with client.stream("GET", current) as resp:
                if resp.is_redirect:
                    location = resp.headers.get("location")
                    if not location:
                        raise MediaFetchError("Media URL redirect without a Location header")
                    current = current.join(location)
                    continue
                if resp.status_code >= 400:
                    raise MediaFetchError(
                        f"Fetching media URL failed with HTTP {resp.status_code}"
                    )
                too_large = MediaFetchError(
                    f"Media exceeds the {max_bytes}-byte download limit", status_code=413
                )
                declared = resp.headers.get("content-length", "")
                if declared.isdigit() and int(declared) > max_bytes:
                    raise too_large
                buf = bytearray()
                async for chunk in resp.aiter_bytes():
                    buf.extend(chunk)
                    if len(buf) > max_bytes:
                        raise too_large
                return bytes(buf)
    raise MediaFetchError("Media URL redirected too many times")


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
    """Classify an image and return a moderation verdict."""
    try:
        if req.image_base64:
            image = decode_image(req.image_base64, None)
        elif req.image_url:
            data = await fetch_media_url(req.image_url, timeout=30)
            image = Image.open(io.BytesIO(data)).convert("RGB")
        else:
            image = None
    except MediaFetchError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    except Exception as exc:
        # Malformed base64, non-image bytes or an unreachable URL are client
        # errors — mirror /moderate_video instead of surfacing a 500.
        raise HTTPException(status_code=400, detail=f"Could not decode image: {exc}") from exc
    if image is None:
        raise HTTPException(status_code=400, detail="Provide image_base64 or image_url")

    img_scores = classify_image(image)
    deepfake_score = detect_deepfake_suspect(image)
    sexual_violence_score = max(
        img_scores["sexual_violence"],
        score_deepfake_sexual_violence(img_scores["nsfw"], deepfake_score),
    )

    scores = ModerationScores(
        violence=img_scores["violence"],
        sexual_violence=sexual_violence_score,
        nsfw=img_scores["nsfw"],
        deepfake_suspect=deepfake_score,
        cyberbullying=0.0,
    )
    result = decide(scores)
    result = await _apply_known_hash_override(session, [image], result)
    logger.info(
        "image_moderation",
        verdict=result.verdict,
        reasons=result.reasons,
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
        if req.video_base64:
            video_data = decode_video(req.video_base64, None)
        else:
            assert req.video_url is not None
            video_data = await fetch_media_url(req.video_url, timeout=60)
    except MediaFetchError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Could not decode video: {exc}") from exc

    frames = extract_frames(video_data)

    if not frames:
        logger.warning("video_moderation: no frames extracted — returning allow")
        frame_scores = {
            "violence": 0.0,
            "sexual_violence": 0.0,
            "nsfw": 0.0,
            "deepfake_suspect": 0.0,
        }
    else:
        frame_scores = moderate_video_frames(frames)

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
