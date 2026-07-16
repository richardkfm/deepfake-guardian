"""Generic HTTP API deepfake detector.

Sends face crops to a user-configured endpoint for deepfake analysis.
Useful for self-hosted models or alternative cloud services.
"""
from __future__ import annotations

import base64
import io
import logging

from PIL import Image

from deepfake.base import DeepfakeDetector

logger = logging.getLogger(__name__)


def _extract_nested(data: dict, path: str) -> float:
    """Extract a value from nested dict using dot-separated path.

    Example: ``_extract_nested({"result": {"score": 0.9}}, "result.score")``
    returns ``0.9``.
    """
    keys = path.split(".")
    current = data
    for key in keys:
        if isinstance(current, dict):
            current = current.get(key, 0.0)
        else:
            return 0.0
    if isinstance(current, dict):
        return 0.0
    return float(current)


class GenericApiDetector(DeepfakeDetector):
    """Deepfake detector that calls a user-configured HTTP endpoint."""

    name = "api"

    def __init__(self) -> None:
        from config import settings

        self._api_url = getattr(settings, "deepfake_api_url", "")
        self._api_key = getattr(settings, "deepfake_api_key", "")
        # Dot-separated path to extract the score from the JSON response
        self._score_path = getattr(settings, "deepfake_api_score_path", "score")

        if self.is_available():
            logger.warning(
                "GDPR notice: generic API deepfake provider is active (url=%s). "
                "Face images will be sent to this endpoint.",
                self._api_url,
            )

    def detect(self, face_images: list[Image.Image]) -> list[float]:
        """Send each face crop to the configured API and return scores."""
        import httpx

        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        scores: list[float] = []
        for face in face_images:
            try:
                buf = io.BytesIO()
                face.save(buf, format="JPEG", quality=90)
                b64 = base64.b64encode(buf.getvalue()).decode()

                resp = httpx.post(
                    self._api_url,
                    json={"image_base64": b64},
                    headers=headers,
                    timeout=30,
                )
                resp.raise_for_status()
                data = resp.json()

                score = _extract_nested(data, self._score_path)
                scores.append(min(max(score, 0.0), 1.0))
            except Exception:
                logger.exception("Generic deepfake API call failed for face crop")
                scores.append(0.0)

        return scores

    def is_available(self) -> bool:
        """Available when the API URL is configured."""
        return bool(self._api_url)
