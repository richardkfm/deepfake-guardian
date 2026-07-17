"""Lightweight classifier wrappers.

Each public function accepts raw content and returns a dict of category scores.
Text classification now routes through the i18n :class:`~i18n.registry.LanguageRegistry`
so that language-specific models and patterns are applied automatically.

The image and deepfake classifiers are unchanged from Phase 1.
"""

from __future__ import annotations

import base64
import io
import logging
from typing import Any

from PIL import Image

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Lazy-loaded fallback pipeline (used when no language pack is available)
# ---------------------------------------------------------------------------

_fallback_text_classifier: Any = None
_image_classifier: Any = None
_violence_classifier: Any = None


def _get_fallback_text_classifier() -> Any:
    """Return the legacy BART zero-shot classifier (fallback only)."""
    global _fallback_text_classifier
    if _fallback_text_classifier is None:
        try:
            from transformers import pipeline

            _fallback_text_classifier = pipeline(
                "zero-shot-classification",
                model="facebook/bart-large-mnli",
                device=-1,
            )
            logger.info("Fallback text classifier loaded: facebook/bart-large-mnli")
        except Exception:
            logger.warning("Could not load fallback text classifier – using stub scores")
    return _fallback_text_classifier


def _get_image_classifier() -> Any:
    """Return an image classification pipeline for NSFW/violence (cached)."""
    global _image_classifier
    if _image_classifier is None:
        try:
            from transformers import pipeline

            _image_classifier = pipeline(
                "image-classification",
                model="Falconsai/nsfw_image_detection",
                device=-1,
            )
            logger.info("Image classifier loaded: Falconsai/nsfw_image_detection")
        except Exception:
            logger.warning("Could not load image classifier – using stub scores")
    return _image_classifier


def _get_violence_classifier() -> Any:
    """Return a CLIP zero-shot classifier for image violence detection (cached)."""
    global _violence_classifier
    if _violence_classifier is None:
        try:
            from transformers import pipeline

            _violence_classifier = pipeline(
                "zero-shot-image-classification",
                model="openai/clip-vit-base-patch32",
                device=-1,
            )
            logger.info("Violence classifier loaded: openai/clip-vit-base-patch32")
        except Exception:
            logger.warning("Could not load violence classifier – violence scores will be 0.0")
    return _violence_classifier


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def decode_image(image_base64: str | None, image_url: str | None) -> Image.Image | None:
    """Decode a PIL Image from base64 data or fetch from URL."""
    if image_base64:
        data = base64.b64decode(image_base64)
        return Image.open(io.BytesIO(data)).convert("RGB")
    if image_url:
        import httpx

        resp = httpx.get(image_url, timeout=30, follow_redirects=True)
        resp.raise_for_status()
        return Image.open(io.BytesIO(resp.content)).convert("RGB")
    return None


# ---------------------------------------------------------------------------
# Text classification (language-aware)
# ---------------------------------------------------------------------------

# Labels used when falling back to the legacy BART classifier
_FALLBACK_LABELS = ["hate speech", "sexual content", "violence", "harassment", "safe"]

# Labels used for zero-shot packs (e.g. EnglishPack with BART)
_ZERO_SHOT_LABELS = [
    "hate speech",
    "sexual content",
    "violence",
    "harassment",
    "cyberbullying",
    "safe",
]


def _scores_from_zero_shot(clf: Any, text: str, label_map: dict[str, str]) -> dict[str, float]:
    """Run a zero-shot pipeline and map labels to internal categories."""
    result = clf(text, candidate_labels=_ZERO_SHOT_LABELS, multi_label=True)
    raw: dict[str, float] = dict(zip(result["labels"], result["scores"]))

    violence = float(raw.get("violence", 0.0))
    sexual = float(raw.get("sexual content", 0.0))
    hate = float(raw.get("hate speech", 0.0))
    harassment = float(raw.get("harassment", 0.0))
    cyber = float(raw.get("cyberbullying", 0.0))

    return {
        "violence": violence,
        "sexual_violence": sexual,
        "nsfw": float(max(sexual, hate)),
        "cyberbullying": float(max(harassment, cyber)),
    }


def _scores_from_multilabel(clf: Any, text: str, label_map: dict[str, str]) -> dict[str, float]:
    """Run a multi-label text-classification pipeline and map labels."""
    # top_k=None returns list of {label, score} dicts for every class
    raw_list: list[dict[str, Any]] = clf(text)
    raw: dict[str, float] = {item["label"]: item["score"] for item in raw_list}

    scores: dict[str, float] = {
        "violence": 0.0,
        "sexual_violence": 0.0,
        "nsfw": 0.0,
        "cyberbullying": 0.0,
    }

    for model_label, internal_cat in label_map.items():
        value = float(raw.get(model_label, 0.0))
        if internal_cat == "safe":
            continue
        if internal_cat in scores:
            scores[internal_cat] = max(scores[internal_cat], value)
        elif internal_cat == "nsfw":
            scores["nsfw"] = max(scores["nsfw"], value)

    return scores


def classify_text(text: str, language: str | None = None) -> dict[str, Any]:
    """Classify text and return normalised scores.

    Routes through the i18n :class:`~i18n.registry.LanguageRegistry`.  Falls
    back to the legacy BART pipeline when no pack is available.

    Args:
        text: The message text to classify.
        language: ISO 639-1 language code.  When ``None`` the language is
            auto-detected.

    Returns:
        Dict with keys: ``violence``, ``sexual_violence``, ``nsfw``,
        ``cyberbullying``, ``lang_code``.
    """
    from cyberbullying import score_cyberbullying
    from i18n.detector import detect_language
    from i18n.registry import LanguageRegistry

    # 1. Detect language
    lang_code = language or detect_language(text)
    pack = LanguageRegistry.get(lang_code)

    # 2. Run ML classification
    ml_scores: dict[str, Any] = {
        "violence": 0.0, "sexual_violence": 0.0, "nsfw": 0.0, "cyberbullying": 0.0
    }

    if pack is not None:
        clf = pack.get_classifier()
        label_map = pack.get_labels()
        if clf is not None:
            try:
                # Detect pipeline type: zero-shot vs multi-label classification
                pipe_task = getattr(clf, "task", "")
                if pipe_task == "zero-shot-classification":
                    ml_scores = _scores_from_zero_shot(clf, text, label_map)
                else:
                    ml_scores = _scores_from_multilabel(clf, text, label_map)
            except Exception:
                logger.warning("Classification failed for pack '%s'", lang_code)
    else:
        # Fallback: use legacy BART classifier
        clf = _get_fallback_text_classifier()
        if clf is not None:
            try:
                result = clf(text, candidate_labels=_FALLBACK_LABELS, multi_label=True)
                raw: dict[str, float] = dict(zip(result["labels"], result["scores"]))
                ml_scores = {
                    "violence": float(raw.get("violence", 0.0)),
                    "sexual_violence": float(raw.get("sexual content", 0.0)),
                    "nsfw": float(max(raw.get("sexual content", 0.0), raw.get("hate speech", 0.0))),
                    "cyberbullying": float(raw.get("harassment", 0.0)),
                }
            except Exception:
                logger.warning("Fallback text classification failed")

    # 3. Boost cyberbullying score with pattern-based detection
    pattern_score = score_cyberbullying(text, pack)
    ml_scores["cyberbullying"] = max(ml_scores["cyberbullying"], pattern_score)

    ml_scores["lang_code"] = lang_code
    return ml_scores


# ---------------------------------------------------------------------------
# Image classification
# ---------------------------------------------------------------------------


_VIOLENCE_LABELS = ["violence", "gore", "fighting", "safe", "peaceful"]


def classify_image(image: Image.Image) -> dict[str, float]:
    """Classify an image and return normalised scores.

    Returns dict with keys: violence, sexual_violence, nsfw.
    """
    # NSFW detection
    nsfw_score = 0.0
    clf = _get_image_classifier()
    if clf is not None:
        results = clf(image)
        label_scores: dict[str, float] = {r["label"].lower(): r["score"] for r in results}
        nsfw_score = float(label_scores.get("nsfw", 0.0))

    # Violence detection via CLIP zero-shot
    violence_score = 0.0
    v_clf = _get_violence_classifier()
    if v_clf is not None:
        try:
            v_results = v_clf(image, candidate_labels=_VIOLENCE_LABELS)
            v_scores: dict[str, float] = {r["label"]: r["score"] for r in v_results}
            violence_score = float(max(
                v_scores.get("violence", 0.0),
                v_scores.get("gore", 0.0),
                v_scores.get("fighting", 0.0),
            ))
        except Exception:
            logger.warning("Violence classification failed")

    return {
        "violence": violence_score,
        "sexual_violence": nsfw_score * 0.5,  # Rough heuristic
        "nsfw": nsfw_score,
    }


# ---------------------------------------------------------------------------
# Deepfake detection
# ---------------------------------------------------------------------------


def detect_deepfake_suspect(image: Image.Image) -> float:
    """Detect whether an image may be a deepfake.

    Pipeline:
      1. Extract faces from the image using MediaPipe.
      2. If no faces found, return 0.05 (no face = unlikely deepfake).
      3. Run either the single legacy provider (``DEEPFAKE_PROVIDER``) or, if
         ``DEEPFAKE_LAYERS`` is set, every active detection layer — combining
         their scores per ``DEEPFAKE_LAYER_COMBINE``.
      4. Return the resulting score.

    Args:
        image: A PIL RGB image.

    Returns:
        A float between 0.0 and 1.0 indicating deepfake likelihood.
    """
    from deepfake.face_extractor import extract_faces

    faces = extract_faces(image)
    if not faces:
        logger.debug("No faces detected — returning baseline deepfake score 0.05")
        return 0.05

    from config import settings

    if settings.deepfake_layers:
        return _detect_deepfake_multi_layer(faces, settings.deepfake_layers)
    return _detect_deepfake_legacy(faces)


def _detect_deepfake_legacy(faces: list[Image.Image]) -> float:
    """Single-provider path: today's ``DEEPFAKE_PROVIDER`` behaviour, unchanged."""
    from deepfake.factory import get_detector

    detector = get_detector()
    scores = detector.detect(faces)

    if not scores:
        return 0.05

    result = max(scores)
    logger.info(
        "Deepfake detection: %d face(s), max score=%.3f (provider=%s)",
        len(faces),
        result,
        detector.name,
    )
    return result


def _detect_deepfake_multi_layer(faces: list[Image.Image], enabled_ids: list[str]) -> float:
    """Multi-layer path: run every active layer and combine their scores.

    A layer id in ``DEEPFAKE_LAYERS`` with no matching manifest, or an
    unavailable/broken layer, does NOT fall back to the legacy single-provider
    path — it's simply excluded from the combination (or, if none are usable,
    the baseline 0.05 is returned). Falling back silently would turn a typo in
    ``DEEPFAKE_LAYERS`` into a hard-to-notice behaviour change.
    """
    from config import settings
    from deepfake.combine import combine_scores
    from deepfake.layer_registry import DeepfakeLayerRegistry

    layers = DeepfakeLayerRegistry.active_layers(enabled_ids)
    if not layers:
        logger.warning(
            "DEEPFAKE_LAYERS=%s matched no known deepfake layers — returning baseline 0.05",
            enabled_ids,
        )
        return 0.05

    per_layer: dict[str, float] = {}
    for layer in layers:
        detector = DeepfakeLayerRegistry.get_detector_for(layer)
        if detector is None:
            continue
        scores = detector.detect(faces)
        if scores:
            per_layer[layer.layer_id] = max(scores)

    if not per_layer:
        logger.warning(
            "No active deepfake layer produced a usable detector — returning baseline 0.05"
        )
        return 0.05

    result = combine_scores(per_layer, layers, settings.deepfake_layer_combine)
    logger.info(
        "Deepfake detection (multi-layer): %d face(s), layers=%s, combined=%.3f",
        len(faces),
        per_layer,
        result,
    )
    return result
