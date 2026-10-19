"""Lightweight classifier wrappers.

Each public function accepts raw content and returns a dict of category scores.
Text classification now routes through the i18n :class:`~i18n.registry.LanguageRegistry`
so that language-specific models and patterns are applied automatically.

Image decoding is delegated to :mod:`media` (hardened against malformed input,
EXIF-orientation aware, animation aware).
"""

from __future__ import annotations

import logging
import math
import threading
from typing import Any

from PIL import Image

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Lazy-loaded fallback pipeline (used when no language pack is available)
# ---------------------------------------------------------------------------

_fallback_text_classifier: Any = None
_image_classifier: Any = None
_violence_classifier: Any = None
# Guards the lazy image-model loads below: image/video analysis runs in a
# worker thread pool, and two concurrent first requests must not each load a
# multi-hundred-MB model.
_image_model_lock = threading.Lock()


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
        with _image_model_lock:
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
        with _image_model_lock:
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
                    logger.warning(
                        "Could not load violence classifier – violence scores will be 0.0"
                    )
    return _violence_classifier


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def decode_image(image_base64: str | None, image_url: str | None) -> Image.Image | None:
    """Decode a canonical RGB PIL Image from base64 data or a URL.

    Applies EXIF orientation and the other canonicalisation steps in
    :mod:`media`. For animated images this is the first frame only — use
    :func:`decode_image_frames` to analyse the whole animation.

    *image_url* is not fetched here (a synchronous fetch can't apply the
    SSRF checks): fetch it with the async ``routes.fetch_media_url`` and
    decode the bytes with :func:`media.load_image_frames`.

    Returns:
        The decoded image, or ``None`` when neither source is given.

    Raises:
        media.MediaDecodeError: The input is not a decodable image, or only
            *image_url* was given (a ``ValueError`` subclass; routes map it
            to HTTP 400).
    """
    frames = decode_image_frames(image_base64, image_url, max_frames=1)
    return frames[0] if frames else None


def decode_image_frames(
    image_base64: str | None, image_url: str | None, max_frames: int = 1
) -> list[Image.Image]:
    """Decode an image request into canonical RGB frames.

    A still image yields one frame; an animated GIF/WebP/APNG yields up to
    *max_frames* frames spread across the animation. Returns ``[]`` when
    neither source is given.

    Raises:
        media.MediaDecodeError: The input is not a decodable image.
    """
    from media import load_image_frames, read_image_source

    data = read_image_source(image_base64, image_url)
    if data is None:
        return []
    return load_image_frames(data, max_frames=max_frames)


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
    if image.mode != "RGB":
        from media import to_rgb

        image = to_rgb(image)

    # NSFW detection
    nsfw_score = 0.0
    clf = _get_image_classifier()
    if clf is not None:
        results = clf(image)
        label_scores: dict[str, float] = {r["label"].lower(): r["score"] for r in results}
        nsfw_score = _unit(label_scores.get("nsfw", 0.0))

    # Violence detection via CLIP zero-shot
    violence_score = 0.0
    v_clf = _get_violence_classifier()
    if v_clf is not None:
        try:
            v_results = v_clf(image, candidate_labels=_VIOLENCE_LABELS)
            v_scores: dict[str, float] = {r["label"]: r["score"] for r in v_results}
            violence_score = _unit(max(
                v_scores.get("violence", 0.0),
                v_scores.get("gore", 0.0),
                v_scores.get("fighting", 0.0),
            ))
        except Exception:
            logger.exception("Violence classification failed — violence score is 0.0")

    return {
        "violence": violence_score,
        "sexual_violence": nsfw_score * 0.5,  # Rough heuristic
        "nsfw": nsfw_score,
    }


def _unit(value: Any, default: float = 0.0) -> float:
    """Coerce a model output to a finite float in ``[0, 1]``.

    A NaN or out-of-range score would fail ``ModerationScores`` validation
    and turn the whole request into a 500.
    """
    try:
        f = float(value)
    except (TypeError, ValueError):
        return default
    if math.isnan(f):
        return default
    return min(max(f, 0.0), 1.0)


def score_deepfake_sexual_violence(nsfw_score: float, deepfake_score: float) -> float:
    """Combined signal for AI-generated non-consensual intimate imagery ("revenge porn").

    A sexualised image of a *deepfaked* face — a real person's likeness pasted
    into explicit content without consent — is more severe than either the
    NSFW or the deepfake signal alone. Multiplying the two keeps the score low
    unless both signals are elevated together, while letting a strong pairing
    (e.g. nsfw=0.9, deepfake=0.9 -> 0.81) clearly outscore the plain NSFW
    heuristic (nsfw * 0.5) used for ordinary sexual content.
    """
    return nsfw_score * deepfake_score


# ---------------------------------------------------------------------------
# Deepfake detection
# ---------------------------------------------------------------------------


def detect_deepfake_suspect(image: Image.Image) -> float:
    """Detect whether an image may be a deepfake.

    Pipeline:
      1. Extract faces from the image using MediaPipe (largest first).
      2. If no faces found, return 0.05 (no face = unlikely deepfake).
      3. Optionally keep only the ``DEEPFAKE_MAX_FACES`` largest faces.
      4. Run either the single legacy provider (``DEEPFAKE_PROVIDER``) or, if
         ``DEEPFAKE_LAYERS`` is set, every active detection layer — combining
         their scores per ``DEEPFAKE_LAYER_COMBINE``.
      5. Return the resulting score, clamped to ``[0, 1]``.

    A detector that *raises* is treated like one that failed to answer: the
    baseline 0.05 is used (legacy path) or the layer is dropped from the
    combination (multi-layer path), rather than failing the whole request.

    Args:
        image: A PIL RGB image.

    Returns:
        A float between 0.0 and 1.0 indicating deepfake likelihood.
    """
    from deepfake.face_extractor import extract_faces

    faces = extract_faces(image)
    if not faces:
        logger.debug("No faces detected — returning baseline deepfake score 0.05")
        return _BASELINE_DEEPFAKE

    from config import settings

    max_faces = getattr(settings, "deepfake_max_faces", 0)
    if isinstance(max_faces, int) and max_faces > 0 and len(faces) > max_faces:
        logger.info(
            "Scoring the %d largest of %d faces (DEEPFAKE_MAX_FACES)", max_faces, len(faces)
        )
        faces = faces[:max_faces]

    if settings.deepfake_layers:
        return _detect_deepfake_multi_layer(faces, settings.deepfake_layers)
    return _detect_deepfake_legacy(faces)


#: Mirrors :data:`deepfake.base.BASELINE_SCORE` (kept literal here so this
#: module doesn't import the provider package at load time).
_BASELINE_DEEPFAKE = 0.05


def _max_face_score(scores: list[float]) -> float | None:
    """Max of a detector's per-face scores, ignoring NaN; ``None`` if none usable."""
    usable = [_unit(s) for s in scores if not _is_nan(s)]
    return max(usable) if usable else None


def _is_nan(value: Any) -> bool:
    try:
        return math.isnan(float(value))
    except (TypeError, ValueError):
        return True


def _detect_deepfake_legacy(faces: list[Image.Image]) -> float:
    """Single-provider path: today's ``DEEPFAKE_PROVIDER`` behaviour."""
    from deepfake.factory import get_detector

    detector = get_detector()
    try:
        scores = detector.detect(faces)
    except Exception:
        logger.exception(
            "Deepfake provider '%s' raised — using baseline score",
            getattr(detector, "name", "?"),
        )
        return _BASELINE_DEEPFAKE

    result = _max_face_score(scores or [])
    if result is None:
        return _BASELINE_DEEPFAKE

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
        return _BASELINE_DEEPFAKE

    per_layer: dict[str, float] = {}
    for layer in layers:
        detector = DeepfakeLayerRegistry.get_detector_for(layer)
        if detector is None:
            continue
        try:
            scores = detector.detect(faces)
        except Exception:
            logger.exception(
                "Deepfake layer '%s' raised — excluding it from this combination",
                layer.layer_id,
            )
            continue
        score = _max_face_score(scores or [])
        if score is not None:
            per_layer[layer.layer_id] = score

    if not per_layer:
        logger.warning(
            "No active deepfake layer produced a usable score — returning baseline 0.05"
        )
        return _BASELINE_DEEPFAKE

    result = _unit(combine_scores(per_layer, layers, settings.deepfake_layer_combine))
    logger.info(
        "Deepfake detection (multi-layer): %d face(s), layers=%s, combined=%.3f",
        len(faces),
        per_layer,
        result,
    )
    return result
