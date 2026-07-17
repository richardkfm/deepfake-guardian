"""Unit tests for classifier helpers in classifiers.py."""

from __future__ import annotations

import base64
import io
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

from classifiers import classify_image, classify_text, decode_image, detect_deepfake_suspect


def _make_image(width: int = 10, height: int = 10) -> Image.Image:
    return Image.new("RGB", (width, height), color=(128, 64, 32))


class TestDecodeImage:
    def test_decode_from_base64(self):
        img = _make_image()
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        b64 = base64.b64encode(buf.getvalue()).decode()
        result = decode_image(b64, None)
        assert result is not None
        assert result.mode == "RGB"

    def test_decode_returns_none_when_no_input(self):
        result = decode_image(None, None)
        assert result is None

    def test_decode_converts_to_rgb(self):
        # RGBA image should be converted to RGB
        img = Image.new("RGBA", (10, 10), color=(255, 0, 0, 128))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        b64 = base64.b64encode(buf.getvalue()).decode()
        result = decode_image(b64, None)
        assert result is not None
        assert result.mode == "RGB"


class TestClassifyText:
    def test_returns_zeros_when_classifier_unavailable(self):
        """When no pack and no fallback, classify_text returns all zeros."""
        with (
            patch("classifiers._get_fallback_text_classifier", return_value=None),
            patch("i18n.registry.LanguageRegistry.get", return_value=None),
            patch("i18n.detector.detect_language", return_value="en"),
        ):
            result = classify_text("hello world")
        assert result["violence"] == pytest.approx(0.0)
        assert result["sexual_violence"] == pytest.approx(0.0)
        assert result["nsfw"] == pytest.approx(0.0)
        assert result["cyberbullying"] == pytest.approx(0.0)

    def test_maps_labels_to_scores_via_fallback(self):
        """Fallback BART path maps raw labels to category scores correctly."""
        mock_clf = MagicMock(
            return_value={
                "labels": [
                    "violence",
                    "sexual content",
                    "hate speech",
                    "harassment",
                    "cyberbullying",
                    "safe",
                ],
                "scores": [0.8, 0.6, 0.3, 0.1, 0.05, 0.02],
            }
        )
        # Simulate pipeline with task attribute for zero-shot path
        mock_clf.task = "zero-shot-classification"

        with (
            patch("i18n.registry.LanguageRegistry.get", return_value=None),
            patch("i18n.detector.detect_language", return_value="en"),
            patch("classifiers._get_fallback_text_classifier", return_value=mock_clf),
        ):
            result = classify_text("some text")
        assert result["violence"] == pytest.approx(0.8)
        assert result["sexual_violence"] == pytest.approx(0.6)
        # nsfw = max(sexual_content=0.6, hate_speech=0.3)
        assert result["nsfw"] == pytest.approx(0.6)
        assert "cyberbullying" in result

    def test_nsfw_uses_max_of_sexual_and_hate(self):
        """nsfw score should be max(sexual content, hate speech)."""
        mock_clf = MagicMock(
            return_value={
                "labels": [
                    "violence",
                    "sexual content",
                    "hate speech",
                    "harassment",
                    "cyberbullying",
                    "safe",
                ],
                "scores": [0.1, 0.2, 0.9, 0.1, 0.05, 0.1],
            }
        )
        mock_clf.task = "zero-shot-classification"

        with (
            patch("i18n.registry.LanguageRegistry.get", return_value=None),
            patch("i18n.detector.detect_language", return_value="en"),
            patch("classifiers._get_fallback_text_classifier", return_value=mock_clf),
        ):
            result = classify_text("hateful text")
        # hate speech score (0.9) > sexual content (0.2)
        assert result["nsfw"] == pytest.approx(0.9)

    def test_result_includes_lang_code(self):
        """classify_text result always includes lang_code key."""
        with (
            patch("i18n.registry.LanguageRegistry.get", return_value=None),
            patch("i18n.detector.detect_language", return_value="de"),
            patch("classifiers._get_fallback_text_classifier", return_value=None),
        ):
            result = classify_text("Hallo Welt", language="de")
        assert result.get("lang_code") == "de"

    def test_language_hint_respected(self):
        """Explicit language hint bypasses detection and is reflected in lang_code."""
        with (
            patch("i18n.registry.LanguageRegistry.get", return_value=None),
            patch("i18n.detector.detect_language") as mock_detect,
            patch("classifiers._get_fallback_text_classifier", return_value=None),
        ):
            result = classify_text("hello", language="de")
        # detect_language should NOT have been called since language hint was given
        mock_detect.assert_not_called()
        assert result["lang_code"] == "de"


class TestClassifyImage:
    def test_returns_zeros_when_classifiers_unavailable(self):
        with (
            patch("classifiers._get_image_classifier", return_value=None),
            patch("classifiers._get_violence_classifier", return_value=None),
        ):
            result = classify_image(_make_image())
        assert result == {"violence": 0.0, "sexual_violence": 0.0, "nsfw": 0.0}

    def test_extracts_nsfw_score(self):
        mock_clf = MagicMock(
            return_value=[{"label": "nsfw", "score": 0.7}, {"label": "normal", "score": 0.3}]
        )
        with (
            patch("classifiers._get_image_classifier", return_value=mock_clf),
            patch("classifiers._get_violence_classifier", return_value=None),
        ):
            result = classify_image(_make_image())
        assert result["nsfw"] == pytest.approx(0.7)
        assert result["sexual_violence"] == pytest.approx(0.35)  # nsfw * 0.5
        assert result["violence"] == 0.0

    def test_violence_from_clip_classifier(self):
        """Violence classifier returns a non-zero score from CLIP zero-shot."""
        mock_nsfw = MagicMock(return_value=[{"label": "normal", "score": 1.0}])
        mock_violence = MagicMock(
            return_value=[
                {"label": "violence", "score": 0.8},
                {"label": "gore", "score": 0.3},
                {"label": "fighting", "score": 0.1},
                {"label": "safe", "score": 0.05},
                {"label": "peaceful", "score": 0.02},
            ]
        )
        with (
            patch("classifiers._get_image_classifier", return_value=mock_nsfw),
            patch("classifiers._get_violence_classifier", return_value=mock_violence),
        ):
            result = classify_image(_make_image())
        assert result["violence"] == pytest.approx(0.8)


class TestDetectDeepfakeSuspect:
    def test_no_faces_returns_005(self):
        """When no faces are detected, returns baseline 0.05."""
        with patch("deepfake.face_extractor.extract_faces", return_value=[]):
            score = detect_deepfake_suspect(_make_image())
        assert score == pytest.approx(0.05)

    def test_returns_max_of_face_scores(self):
        """When faces detected, returns max score from detector."""
        face1 = _make_image(50, 50)
        face2 = _make_image(50, 50)

        mock_detector = MagicMock()
        mock_detector.detect.return_value = [0.3, 0.9]
        mock_detector.name = "mock"

        with (
            patch("deepfake.face_extractor.extract_faces", return_value=[face1, face2]),
            patch("deepfake.factory.get_detector", return_value=mock_detector),
        ):
            score = detect_deepfake_suspect(_make_image())
        assert score == pytest.approx(0.9)

    def test_accepts_any_pil_image(self):
        with patch("deepfake.face_extractor.extract_faces", return_value=[]):
            for size in [(1, 1), (100, 100), (640, 480)]:
                img = _make_image(*size)
                score = detect_deepfake_suspect(img)
                assert 0.0 <= score <= 1.0


class TestDetectDeepfakeSuspectBackwardCompat:
    """When DEEPFAKE_LAYERS is unset, behaviour must be identical to legacy."""

    def test_legacy_path_used_when_layers_unset(self):
        face = _make_image(50, 50)
        mock_detector = MagicMock()
        mock_detector.detect.return_value = [0.4]
        mock_detector.name = "mock"

        with (
            patch("deepfake.face_extractor.extract_faces", return_value=[face]),
            patch("config.settings") as mock_settings,
            patch("deepfake.factory.get_detector", return_value=mock_detector) as mock_get_detector,
        ):
            mock_settings.deepfake_layers = []
            score = detect_deepfake_suspect(_make_image())

        mock_get_detector.assert_called_once()
        assert score == pytest.approx(0.4)


class TestDetectDeepfakeSuspectMultiLayer:
    def _make_layer(self, layer_id: str, weight: float = 1.0):
        from deepfake.layer import DeepfakeLayer

        return DeepfakeLayer(layer_id=layer_id, display_name=layer_id, provider="stub", weight=weight)

    def test_max_strategy_picks_higher_layer_score(self):
        face = _make_image(50, 50)
        layer_a = self._make_layer("a")
        layer_b = self._make_layer("b")

        det_a = MagicMock()
        det_a.detect.return_value = [0.2]
        det_b = MagicMock()
        det_b.detect.return_value = [0.9]

        def _get_detector_for(layer):
            return {"a": det_a, "b": det_b}[layer.layer_id]

        with (
            patch("deepfake.face_extractor.extract_faces", return_value=[face]),
            patch("config.settings") as mock_settings,
            patch(
                "deepfake.layer_registry.DeepfakeLayerRegistry.active_layers",
                return_value=[layer_a, layer_b],
            ),
            patch(
                "deepfake.layer_registry.DeepfakeLayerRegistry.get_detector_for",
                side_effect=_get_detector_for,
            ),
        ):
            mock_settings.deepfake_layers = ["a", "b"]
            mock_settings.deepfake_layer_combine = "max"
            score = detect_deepfake_suspect(_make_image())

        assert score == pytest.approx(0.9)

    def test_mean_strategy_averages_layer_scores(self):
        face = _make_image(50, 50)
        layer_a = self._make_layer("a")
        layer_b = self._make_layer("b")

        det_a = MagicMock()
        det_a.detect.return_value = [0.2]
        det_b = MagicMock()
        det_b.detect.return_value = [0.8]

        def _get_detector_for(layer):
            return {"a": det_a, "b": det_b}[layer.layer_id]

        with (
            patch("deepfake.face_extractor.extract_faces", return_value=[face]),
            patch("config.settings") as mock_settings,
            patch(
                "deepfake.layer_registry.DeepfakeLayerRegistry.active_layers",
                return_value=[layer_a, layer_b],
            ),
            patch(
                "deepfake.layer_registry.DeepfakeLayerRegistry.get_detector_for",
                side_effect=_get_detector_for,
            ),
        ):
            mock_settings.deepfake_layers = ["a", "b"]
            mock_settings.deepfake_layer_combine = "mean"
            score = detect_deepfake_suspect(_make_image())

        assert score == pytest.approx(0.5)

    def test_weighted_mean_respects_layer_weight(self):
        face = _make_image(50, 50)
        layer_a = self._make_layer("a", weight=1.0)
        layer_b = self._make_layer("b", weight=3.0)

        det_a = MagicMock()
        det_a.detect.return_value = [0.2]
        det_b = MagicMock()
        det_b.detect.return_value = [0.8]

        def _get_detector_for(layer):
            return {"a": det_a, "b": det_b}[layer.layer_id]

        with (
            patch("deepfake.face_extractor.extract_faces", return_value=[face]),
            patch("config.settings") as mock_settings,
            patch(
                "deepfake.layer_registry.DeepfakeLayerRegistry.active_layers",
                return_value=[layer_a, layer_b],
            ),
            patch(
                "deepfake.layer_registry.DeepfakeLayerRegistry.get_detector_for",
                side_effect=_get_detector_for,
            ),
        ):
            mock_settings.deepfake_layers = ["a", "b"]
            mock_settings.deepfake_layer_combine = "weighted_mean"
            score = detect_deepfake_suspect(_make_image())

        assert score == pytest.approx(0.65)

    def test_no_matching_layers_returns_baseline_and_does_not_fall_back(self):
        face = _make_image(50, 50)

        with (
            patch("deepfake.face_extractor.extract_faces", return_value=[face]),
            patch("config.settings") as mock_settings,
            patch(
                "deepfake.layer_registry.DeepfakeLayerRegistry.active_layers",
                return_value=[],
            ),
            patch("deepfake.factory.get_detector") as mock_get_detector,
        ):
            mock_settings.deepfake_layers = ["typo_layer"]
            score = detect_deepfake_suspect(_make_image())

        assert score == pytest.approx(0.05)
        mock_get_detector.assert_not_called()

    def test_unavailable_layer_dropped_others_still_combine(self):
        face = _make_image(50, 50)
        layer_a = self._make_layer("a")
        layer_b = self._make_layer("b")

        det_b = MagicMock()
        det_b.detect.return_value = [0.7]

        def _get_detector_for(layer):
            return {"a": None, "b": det_b}[layer.layer_id]

        with (
            patch("deepfake.face_extractor.extract_faces", return_value=[face]),
            patch("config.settings") as mock_settings,
            patch(
                "deepfake.layer_registry.DeepfakeLayerRegistry.active_layers",
                return_value=[layer_a, layer_b],
            ),
            patch(
                "deepfake.layer_registry.DeepfakeLayerRegistry.get_detector_for",
                side_effect=_get_detector_for,
            ),
        ):
            mock_settings.deepfake_layers = ["a", "b"]
            mock_settings.deepfake_layer_combine = "max"
            score = detect_deepfake_suspect(_make_image())

        assert score == pytest.approx(0.7)

    def test_all_layers_unavailable_returns_baseline(self):
        face = _make_image(50, 50)
        layer_a = self._make_layer("a")

        with (
            patch("deepfake.face_extractor.extract_faces", return_value=[face]),
            patch("config.settings") as mock_settings,
            patch(
                "deepfake.layer_registry.DeepfakeLayerRegistry.active_layers",
                return_value=[layer_a],
            ),
            patch(
                "deepfake.layer_registry.DeepfakeLayerRegistry.get_detector_for",
                return_value=None,
            ),
        ):
            mock_settings.deepfake_layers = ["a"]
            score = detect_deepfake_suspect(_make_image())

        assert score == pytest.approx(0.05)
