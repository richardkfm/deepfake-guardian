"""Shared face extraction using MediaPipe FaceDetection.

Extracts face crops from images for downstream deepfake detection.

Two MediaPipe models are used: the short-range model (tuned for faces within
~2 m, i.e. selfies and portraits) runs first; when it finds nothing, the
full-range model (faces up to ~5 m) gets a second look. Without that second
pass, the smaller faces in full-body or group shots — exactly the framing of
most sexualised deepfakes — never reach the deepfake detector at all.
"""
from __future__ import annotations

import logging
import threading
from typing import Any

from PIL import Image

logger = logging.getLogger(__name__)

#: model_selection -> cached FaceDetection instance (None = failed to load)
_face_detectors: dict[int, Any] = {}
# MediaPipe graphs are not safe to call concurrently, and image/video analysis
# runs in a worker thread pool — serialise both loading and inference.
_detector_lock = threading.Lock()

SHORT_RANGE = 0
FULL_RANGE = 1

# Minimum face size relative to image dimensions (skip tiny/background faces)
MIN_FACE_RATIO = 0.03
# Padding around face bounding box (fraction of bbox size)
FACE_PADDING = 0.2


def _get_face_detector(model_selection: int = SHORT_RANGE) -> Any:
    """Return a cached MediaPipe FaceDetection instance for *model_selection*."""
    if model_selection in _face_detectors:
        return _face_detectors[model_selection]
    with _detector_lock:
        if model_selection not in _face_detectors:
            detector: Any = None
            try:
                import mediapipe as mp

                detector = mp.solutions.face_detection.FaceDetection(
                    model_selection=model_selection,  # 0 = short-range (<2m), 1 = full-range
                    min_detection_confidence=0.5,
                )
                logger.info("MediaPipe FaceDetection loaded (model_selection=%d)", model_selection)
            except Exception:
                logger.warning(
                    "Could not load MediaPipe FaceDetection (model_selection=%d)", model_selection
                )
            _face_detectors[model_selection] = detector
    return _face_detectors[model_selection]


def _detect(detector: Any, img_array: Any) -> list[Any]:
    """Run *detector* on *img_array*; never raises (a failure = no faces)."""
    try:
        with _detector_lock:
            results = detector.process(img_array)
    except Exception:
        logger.exception("MediaPipe face detection failed")
        return []
    return list(results.detections or [])


def extract_faces(image: Image.Image) -> list[Image.Image]:
    """Detect faces in an image and return cropped face images, largest first.

    Args:
        image: A PIL image (converted to RGB if needed).

    Returns:
        List of cropped face PIL images, ordered by area (largest first).
        Empty list if no faces found or if MediaPipe is unavailable.
    """
    import numpy as np

    detector = _get_face_detector(SHORT_RANGE)
    if detector is None:
        return []

    if image.mode != "RGB":
        image = image.convert("RGB")
    img_array = np.ascontiguousarray(np.asarray(image, dtype=np.uint8))
    h, w = img_array.shape[:2]
    if h == 0 or w == 0:
        return []
    min_face_pixels = min(h, w) * MIN_FACE_RATIO

    detections = _detect(detector, img_array)
    if not detections:
        fallback = _get_face_detector(FULL_RANGE)
        if fallback is not None:
            detections = _detect(fallback, img_array)
            if detections:
                logger.debug("Full-range face model found %d face(s)", len(detections))
    if not detections:
        return []

    crops: list[tuple[int, Image.Image]] = []
    for detection in detections:
        bbox = detection.location_data.relative_bounding_box

        # Convert relative coordinates to absolute pixels
        x = int(bbox.xmin * w)
        y = int(bbox.ymin * h)
        bw = int(bbox.width * w)
        bh = int(bbox.height * h)

        # Skip tiny faces
        if bw < min_face_pixels or bh < min_face_pixels:
            continue

        # Add padding
        pad_x = int(bw * FACE_PADDING)
        pad_y = int(bh * FACE_PADDING)
        x1 = max(0, x - pad_x)
        y1 = max(0, y - pad_y)
        x2 = min(w, x + bw + pad_x)
        y2 = min(h, y + bh + pad_y)

        # A box that lies (almost) entirely outside the frame would produce an
        # empty crop that every provider then fails to encode.
        if x2 - x1 < 2 or y2 - y1 < 2:
            continue

        crops.append(((x2 - x1) * (y2 - y1), image.crop((x1, y1, x2, y2))))

    crops.sort(key=lambda item: item[0], reverse=True)
    faces = [crop for _, crop in crops]
    logger.debug("Extracted %d face(s) from image (%dx%d)", len(faces), w, h)
    return faces


def reset_face_detectors() -> None:
    """Drop cached detectors (test helper)."""
    with _detector_lock:
        _face_detectors.clear()
