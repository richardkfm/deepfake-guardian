"""Video frame extraction and moderation pipeline.

Extracts key frames from videos and runs image classification + deepfake
detection on each frame, aggregating scores via max per category. The same
per-frame aggregation is used for animated images (GIF / WebP / APNG).
"""
from __future__ import annotations

import logging
import math
import os
import tempfile
from typing import Any

from PIL import Image

logger = logging.getLogger(__name__)


def decode_video(video_base64: str | None, video_url: str | None) -> bytes:
    """Decode video bytes from base64 data or download from URL.

    Args:
        video_base64: Base64-encoded video data (a ``data:`` URI prefix is
            tolerated).
        video_url: URL to download the video from (capped at
            ``MAX_MEDIA_DOWNLOAD_BYTES``).

    Returns:
        Raw video bytes.

    Raises:
        ValueError: If neither source is provided, or the payload is not
            valid base64 / can't be downloaded (``media.MediaDecodeError``).
    """
    from media import decode_base64, fetch_url_bytes

    if video_base64:
        return decode_base64(video_base64)
    if video_url:
        return fetch_url_bytes(video_url, timeout=60)
    raise ValueError("Provide video_base64 or video_url")


#: FPS values outside this range are container metadata garbage (some WebM /
#: variable-frame-rate files report 0, NaN or 90000) — fall back to 25.
_MAX_SANE_FPS = 240.0
_DEFAULT_FPS = 25.0


def _sane_fps(raw: float) -> float:
    if not math.isfinite(raw) or raw <= 0 or raw > _MAX_SANE_FPS:
        logger.info("Video reports implausible FPS (%r) — assuming %.0f", raw, _DEFAULT_FPS)
        return _DEFAULT_FPS
    return raw


def plan_sample_indices(
    total_frames: int,
    fps: float,
    frame_interval: float,
    max_frames: int,
    max_duration: float,
) -> list[int]:
    """Choose which frame indices to analyse.

    Short videos keep the original behaviour: one frame every
    *frame_interval* seconds from the start. When that would need more than
    *max_frames* frames, the budget is instead spread **evenly across the
    whole (duration-capped) video** — previously sampling simply stopped
    after ``max_frames * frame_interval`` seconds (20 s with the defaults),
    so anything harmful after a short innocuous intro was never looked at.
    """
    max_frames = max(1, max_frames)
    limit = total_frames
    if max_duration > 0:
        limit = min(limit, max(1, int(max_duration * fps)))
    if limit <= 0:
        return []

    frame_step = max(1, int(fps * frame_interval))
    interval_indices = list(range(0, limit, frame_step))
    if len(interval_indices) <= max_frames:
        return interval_indices

    # Midpoints of max_frames equal segments (avoids the often-black very
    # first frame while still covering the start).
    return sorted({min(limit - 1, int((i + 0.5) * limit / max_frames)) for i in range(max_frames)})


def _to_pil(frame: Any) -> Image.Image:
    import cv2

    from media import limit_size

    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    return limit_size(Image.fromarray(rgb))


def _read_by_seeking(cap: Any, indices: list[int]) -> list[Image.Image]:
    import cv2

    frames: list[Image.Image] = []
    for idx in indices:
        cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
        ret, frame = cap.read()
        if not ret or frame is None:
            continue
        frames.append(_to_pil(frame))
    return frames


def _read_sequentially(
    cap: Any, fps: float, frame_interval: float, max_frames: int, max_duration: float
) -> list[Image.Image]:
    """Decode front-to-back, keeping an evenly spread sample of <= *max_frames*.

    Used when the container doesn't report a frame count (common for WebM /
    streamed MP4) or doesn't support seeking. Previously such videos yielded
    zero frames and were returned as ``"allow"`` without being analysed.

    Every kept frame index is a multiple of ``step``; whenever more than
    *max_frames* are held, ``step`` doubles and the kept set is thinned, so
    coverage stays spread over everything decoded with bounded memory.
    """
    max_frames = max(1, max_frames)
    step = max(1, int(fps * frame_interval))
    limit = int(max_duration * fps) if max_duration > 0 else None
    kept: list[tuple[int, Any]] = []
    idx = 0
    while limit is None or idx < limit:
        if not cap.grab():
            break
        if idx % step == 0:
            ok, frame = cap.retrieve()
            if ok and frame is not None:
                kept.append((idx, frame))
                if len(kept) > max_frames:
                    step *= 2
                    kept = [(i, f) for i, f in kept if i % step == 0]
        idx += 1
    return [_to_pil(frame) for _, frame in kept]


def extract_frames(video_data: bytes) -> list[Image.Image]:
    """Extract key frames from video bytes using OpenCV.

    Samples one frame every ``FRAME_INTERVAL`` seconds; when that would
    exceed ``MAX_FRAMES``, the ``MAX_FRAMES`` budget is spread evenly over
    the whole video instead. Only the first ``MAX_VIDEO_DURATION`` seconds
    are considered. Videos without a usable frame count, or that can't be
    seeked, are decoded sequentially instead of being skipped.

    Returns:
        List of PIL RGB images (one per sampled frame). Empty if the video
        can't be opened or decoded.
    """
    import cv2

    from config import settings

    frame_interval: float = getattr(settings, "frame_interval", 2.0)
    max_frames: int = getattr(settings, "max_frames", 10)
    max_duration: int = getattr(settings, "max_video_duration", 300)

    # Write to temp file (OpenCV VideoCapture needs a file path)
    tmp_fd, tmp_path = tempfile.mkstemp(suffix=".mp4")
    cap: Any = None
    try:
        with os.fdopen(tmp_fd, "wb") as fh:
            fh.write(video_data)

        cap = cv2.VideoCapture(tmp_path)
        if not cap.isOpened():
            logger.warning("Could not open video file")
            return []

        fps = _sane_fps(float(cap.get(cv2.CAP_PROP_FPS) or 0.0))
        raw_count = cap.get(cv2.CAP_PROP_FRAME_COUNT)
        total_frames = int(raw_count) if raw_count and math.isfinite(raw_count) else 0
        duration = total_frames / fps if total_frames > 0 else 0.0

        if duration > max_duration:
            logger.warning(
                "Video duration (%.0fs) exceeds MAX_VIDEO_DURATION (%ds) — only the "
                "first %ds are analysed",
                duration,
                max_duration,
                max_duration,
            )

        frames: list[Image.Image] = []
        mode = "seek"
        if total_frames > 0:
            indices = plan_sample_indices(
                total_frames, fps, frame_interval, max_frames, max_duration
            )
            frames = _read_by_seeking(cap, indices)

        if not frames:
            # Unknown frame count, or every seek failed — decode front-to-back.
            mode = "sequential"
            cap.release()
            cap = cv2.VideoCapture(tmp_path)
            if cap.isOpened():
                frames = _read_sequentially(cap, fps, frame_interval, max_frames, max_duration)

        logger.info(
            "Extracted %d frame(s) from video (%.1fs, %.1f fps, mode=%s)",
            len(frames),
            min(duration, float(max_duration)) if duration else 0.0,
            fps,
            mode,
        )
        return frames
    finally:
        if cap is not None:
            try:
                cap.release()
            except Exception:
                pass
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


def moderate_video_frames(frames: list[Image.Image]) -> dict[str, float]:
    """Run image classification + deepfake detection on each frame.

    Aggregation: takes the MAX score across all frames for each category.

    Returns:
        Dict with keys: violence, sexual_violence, nsfw, deepfake_suspect.
    """
    from classifiers import classify_image, detect_deepfake_suspect, score_deepfake_sexual_violence

    aggregate: dict[str, float] = {
        "violence": 0.0,
        "sexual_violence": 0.0,
        "nsfw": 0.0,
        "deepfake_suspect": 0.0,
    }

    for frame in frames:
        img_scores = classify_image(frame)
        df_score = detect_deepfake_suspect(frame)
        nsfw_score = img_scores.get("nsfw", 0.0)
        frame_sexual_violence = max(
            img_scores.get("sexual_violence", 0.0),
            score_deepfake_sexual_violence(nsfw_score, df_score),
        )

        aggregate["violence"] = max(aggregate["violence"], img_scores.get("violence", 0.0))
        aggregate["sexual_violence"] = max(aggregate["sexual_violence"], frame_sexual_violence)
        aggregate["nsfw"] = max(aggregate["nsfw"], nsfw_score)
        aggregate["deepfake_suspect"] = max(aggregate["deepfake_suspect"], df_score)

    return aggregate
