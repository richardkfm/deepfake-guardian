"""OpenAI Vision API deepfake detector.

Uses GPT-4o (or a configurable model) to analyse face crops for deepfake
indicators.  Requires an ``OPENAI_API_KEY`` environment variable.

.. warning::

    Face images are sent to OpenAI's servers.  For GDPR-sensitive
    deployments (especially with minors), consider the privacy implications.
"""
from __future__ import annotations

import base64
import io
import logging

from PIL import Image

from deepfake.base import DeepfakeDetector

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = (
    "You are an image-forensics expert.  Given a photograph of a human face, "
    "estimate the probability that the image is a deepfake or has been "
    "AI-generated/manipulated.  Respond with ONLY a single floating-point "
    "number between 0.0 (certainly real) and 1.0 (certainly fake).  "
    "Do not include any other text."
)


class OpenAIDetector(DeepfakeDetector):
    """Deepfake detector that calls the OpenAI Vision API."""

    name = "openai"

    def __init__(self, *, prompt: str | None = None) -> None:
        from config import settings

        self._api_key: str = getattr(settings, "openai_api_key", "")
        self._model: str = getattr(settings, "openai_model", "gpt-4o")
        self._api_base: str = getattr(settings, "openai_api_base", "https://api.openai.com/v1")
        self._system_prompt: str = prompt if prompt is not None else _SYSTEM_PROMPT

        if self.is_available():
            logger.warning(
                "GDPR notice: OpenAI deepfake provider is active (model=%s, base=%s). "
                "Face images will be sent to OpenAI's servers.",
                self._model,
                self._api_base,
            )

    def detect(self, face_images: list[Image.Image]) -> list[float]:
        """Send each face crop to OpenAI Vision and parse the score."""
        import httpx

        scores: list[float] = []
        for face in face_images:
            try:
                buf = io.BytesIO()
                face.save(buf, format="JPEG", quality=90)
                b64 = base64.b64encode(buf.getvalue()).decode()

                resp = httpx.post(
                    f"{self._api_base}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self._api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": self._model,
                        "messages": [
                            {"role": "system", "content": self._system_prompt},
                            {
                                "role": "user",
                                "content": [
                                    {
                                        "type": "image_url",
                                        "image_url": {
                                            "url": f"data:image/jpeg;base64,{b64}",
                                            "detail": "low",
                                        },
                                    },
                                ],
                            },
                        ],
                        "max_tokens": 10,
                        "temperature": 0.0,
                    },
                    timeout=30,
                )
                resp.raise_for_status()
                data = resp.json()

                raw = data["choices"][0]["message"]["content"].strip()
                score = float(raw)
                scores.append(min(max(score, 0.0), 1.0))
            except (ValueError, KeyError, IndexError):
                logger.warning("Could not parse OpenAI deepfake score from response")
                scores.append(0.0)
            except Exception:
                logger.exception("OpenAI deepfake API call failed")
                scores.append(0.0)

        return scores

    def is_available(self) -> bool:
        """Available when an API key is configured."""
        return bool(self._api_key)
