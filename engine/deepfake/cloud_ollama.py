"""Ollama Vision API deepfake detector.

Uses a local Ollama instance with a vision-capable model (e.g. ``llava``,
``bakllava``) to analyse face crops for deepfake indicators.

Privacy-friendly: data stays on your network when Ollama runs locally.
"""
from __future__ import annotations

import base64
import io
import logging

from PIL import Image

from deepfake.base import DeepfakeDetector

logger = logging.getLogger(__name__)

_PROMPT = (
    "You are an image-forensics expert.  Given this photograph of a human "
    "face, estimate the probability that the image is a deepfake or has been "
    "AI-generated/manipulated.  Respond with ONLY a single floating-point "
    "number between 0.0 (certainly real) and 1.0 (certainly fake).  "
    "Do not include any other text."
)


class OllamaDetector(DeepfakeDetector):
    """Deepfake detector that calls a local Ollama vision model."""

    name = "ollama"

    def __init__(self, *, prompt: str | None = None) -> None:
        from config import settings

        self._base_url: str = getattr(settings, "ollama_base_url", "http://localhost:11434")
        self._model: str = getattr(settings, "ollama_model", "llava")
        self._prompt: str = prompt if prompt is not None else _PROMPT

        if self.is_available():
            logger.info(
                "Ollama deepfake provider active (model=%s, url=%s)",
                self._model,
                self._base_url,
            )

    def detect(self, face_images: list[Image.Image]) -> list[float]:
        """Send each face crop to Ollama and parse the score."""
        import httpx

        scores: list[float] = []
        for face in face_images:
            try:
                buf = io.BytesIO()
                face.save(buf, format="JPEG", quality=90)
                b64 = base64.b64encode(buf.getvalue()).decode()

                resp = httpx.post(
                    f"{self._base_url}/api/generate",
                    json={
                        "model": self._model,
                        "prompt": self._prompt,
                        "images": [b64],
                        "stream": False,
                    },
                    timeout=60,
                )
                resp.raise_for_status()
                data = resp.json()

                raw = data.get("response", "").strip()
                score = float(raw)
                scores.append(min(max(score, 0.0), 1.0))
            except (ValueError, KeyError):
                logger.warning("Could not parse Ollama deepfake score from response")
                scores.append(0.0)
            except Exception:
                logger.exception("Ollama deepfake API call failed")
                scores.append(0.0)

        return scores

    def is_available(self) -> bool:
        """Available when the Ollama base URL is configured (non-empty)."""
        return bool(self._base_url)
