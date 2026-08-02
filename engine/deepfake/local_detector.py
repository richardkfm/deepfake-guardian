"""Local ONNX-based deepfake detector.

Runs an EfficientNet-B0 model (trained on FaceForensics++) locally on CPU.
Privacy-first: face images never leave the server.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from deepfake.base import BASELINE_SCORE, DeepfakeDetector

logger = logging.getLogger(__name__)

# Where the model file is looked up when DEEPFAKE_MODEL_PATH is unset.  The
# engine does not download it — the operator has to put it there.
_DEFAULT_MODEL_DIR = Path.home() / ".cache" / "deepfake_guardian"
_MODEL_FILENAME = "efficientnet_b0_deepfake.onnx"

# ImageNet normalisation stats
_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
_STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)

INPUT_SIZE = 224


def _preprocess(face: Image.Image) -> np.ndarray:
    """Resize, normalise, and convert a face crop to NCHW tensor.

    Returns:
        numpy array of shape (1, 3, 224, 224) float32.
    """
    face_resized = face.resize((INPUT_SIZE, INPUT_SIZE), Image.Resampling.BILINEAR)
    arr = np.array(face_resized, dtype=np.float32) / 255.0
    arr = (arr - _MEAN) / _STD
    # HWC -> CHW -> NCHW
    arr = arr.transpose(2, 0, 1)[np.newaxis, ...]
    return arr


def _sigmoid(x: float) -> float:
    """Numerically stable sigmoid."""
    if x >= 0:
        return 1.0 / (1.0 + np.exp(-x))
    exp_x = np.exp(x)
    return exp_x / (1.0 + exp_x)


class LocalOnnxDetector(DeepfakeDetector):
    """Deepfake detector using a local ONNX model (CPU inference)."""

    name = "local"

    def __init__(self) -> None:
        self._session: Any = None
        self._model_path = self._resolve_model_path()

    def _resolve_model_path(self) -> str:
        """Determine the ONNX model file path from config or default."""
        from config import settings

        custom = getattr(settings, "deepfake_model_path", "")
        if custom:
            return custom

        return str(_DEFAULT_MODEL_DIR / _MODEL_FILENAME)

    def _get_session(self) -> Any:
        """Lazy-load the ONNX runtime inference session."""
        if self._session is not None:
            return self._session

        try:
            import onnxruntime as ort

            self._session = ort.InferenceSession(
                self._model_path,
                providers=["CPUExecutionProvider"],
            )
            logger.info("ONNX deepfake model loaded from %s", self._model_path)
        except Exception:
            logger.exception("Failed to load ONNX deepfake model from %s", self._model_path)
        return self._session

    def detect(self, face_images: list[Image.Image]) -> list[float]:
        """Run deepfake detection on each face crop.

        Returns a score per face (0.0 = real, 1.0 = deepfake).
        """
        session = self._get_session()
        if session is None:
            logger.warning("ONNX session unavailable — returning baseline scores")
            return [BASELINE_SCORE] * len(face_images)

        input_name = session.get_inputs()[0].name
        scores: list[float] = []

        for face in face_images:
            tensor = _preprocess(face)
            outputs = session.run(None, {input_name: tensor})
            logit = float(outputs[0].flatten()[0])
            score = _sigmoid(logit)
            scores.append(score)

        return scores

    def is_available(self) -> bool:
        """Check if the ONNX model file exists.

        The model is **not** downloaded automatically — it has to be supplied
        by the operator via ``DEEPFAKE_MODEL_PATH``.  Log the path that was
        checked, otherwise the only symptom is a generic "provider not
        available" from the factory and a silent fall back to the stub.
        """
        if os.path.isfile(self._model_path):
            return True

        logger.warning(
            "Local ONNX deepfake model not found at '%s' — the engine does not "
            "download it; provide the file and set DEEPFAKE_MODEL_PATH. This "
            "provider is unavailable until then.",
            self._model_path or "<unset>",
        )
        return False
