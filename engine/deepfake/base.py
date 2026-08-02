"""Abstract base class for deepfake detection providers."""
from __future__ import annotations

import re
from abc import ABC, abstractmethod

from PIL import Image

#: Score used when a detector cannot produce a real answer — an API error, an
#: unreadable response, a missing score field.  It matches the "no face
#: detected" baseline in :func:`classifiers.detect_deepfake_suspect` on
#: purpose: a failed check must never look *more* innocent than an ordinary
#: faceless photo.  Providers must keep returning a genuine ``0.0`` when the
#: backend really did score the face 0.0.
BASELINE_SCORE = 0.05

_FLOAT_RE = re.compile(r"[-+]?\d*\.?\d+")


def parse_llm_score(raw: str) -> float | None:
    """Extract a deepfake probability from a vision model's text reply.

    LLM providers are asked for a bare number, but they routinely answer
    ``"Probability: 0.7"`` or ``"0.7 (likely manipulated)"``.  A plain
    ``float(raw)`` raises on those and the caller then falls back to the
    baseline, discarding a perfectly good score.

    Args:
        raw: The model's reply text.

    Returns:
        The first float found in *raw*, or ``None`` when it contains no
        number at all (e.g. ``"I cannot determine this."``).  Clamping is
        left to the caller.
    """
    match = _FLOAT_RE.search(raw)
    if match is None:
        return None
    try:
        return float(match.group())
    except ValueError:  # pragma: no cover — regex guarantees a valid float
        return None


class DeepfakeDetector(ABC):
    """Abstract base for deepfake detection providers.

    Each provider receives pre-cropped face images and returns a score
    per face indicating the likelihood of being a deepfake (0.0–1.0).
    """

    name: str

    @abstractmethod
    def detect(self, face_images: list[Image.Image]) -> list[float]:
        """Score each face crop for deepfake likelihood.

        Args:
            face_images: List of cropped face PIL images (RGB).

        Returns:
            List of floats 0.0–1.0, one per face.
        """
        ...

    @abstractmethod
    def is_available(self) -> bool:
        """Check if this detector is properly configured and ready."""
        ...
