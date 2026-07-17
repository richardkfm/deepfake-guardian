"""Video frame extraction and moderation pipeline.

Extracts key frames from videos and runs image classification + deepfake
detection on each frame, aggregating scores via max per category.
"""
from __future__ import annotations

import base64
import logging
import os
import tempfile

from PIL import Image

logger = logging.getLogger(__name__)


def decode_video(video_base64: str | None, video_url: str | None) -> bytes:
    """Decode video bytes from base64 data or download from URL.

    Args:
        video_base64: Base64-encoded video data.
        video_url: URL to download the video from.

    Returns:
        Raw video bytes.

    Raises:
        ValueError: If neither source is provided.
    """
    if video_base64:
        return base64.b64decode(video_base64)
    if video_url:
        import httpx

        resp = httpx.get(video_url, timeout=60, follow_redirects=True)
        resp.raise_for_status()
        return resp.content
    raise ValueError("Provide video_base64 or video_url")


def extract_frames(video_data: bytes) -> list[Image.Image]:
    """Extract key frames from video bytes using OpenCV.

    Samples one frame every ``FRAME_INTERVAL`` seconds, capped at
    ``MAX_FRAMES``. Rejects videos longer than ``MAX_VIDEO_DURATION``.

    Returns:
        List of PIL RGB images (one per sampled frame).
    """
    import cv2

    from config import settings

    frame_interval: float = getattr(settings, "frame_interval", 2.0)
    max_frames: int = getattr(settings, "max_frames", 10)
    max_duration: int = getattr(settings, "max_video_duration", 300)

    # Write to temp file (OpenCV VideoCapture needs a file path)
    tmp_fd, tmp_path = tempfile.mkstemp(suffix=".mp4")
    try:
        os.write(tmp_fd, video_data)
        os.close(tmp_fd)

        cap = cv2.VideoCapture(tmp_path)
        if not cap.isOpened():
            logger.warning("Could not open video file")
            return []

        fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        duration = total_frames / fps if fps > 0 else 0

        if duration > max_duration:
            logger.warning(
                "Video duration (%.0fs) exceeds MAX_VIDEO_DURATION (%ds) — truncating",
                duration,
                max_duration,
            )
            duration = max_duration

        # Calculate which frame indices to sample
        frame_step = int(fps * frame_interval)
        if frame_step < 1:
            frame_step = 1

        max_frame_idx = int(duration * fps)
        sample_indices = list(range(0, max_frame_idx, frame_step))[:max_frames]

        frames: list[Image.Image] = []
        for idx in sample_indices:
            cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
            ret, frame = cap.read()
            if not ret:
                continue
            # BGR -> RGB
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            frames.append(Image.fromarray(rgb))

        cap.release()
        logger.info(
            "Extracted %d frame(s) from video (%.1fs, %.1f fps)",
            len(frames),
            duration,
            fps,
        )
        return frames
    finally:
        # Clean up temp file
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
