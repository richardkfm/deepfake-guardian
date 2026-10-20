"""Robustness tests for the deepfake path: detector failures, bad scores,
face extraction edge cases, the local ONNX output contract, layer combination
and /health reporting in layer mode."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from PIL import Image

from classifiers import classify_image, detect_deepfake_suspect


def _img(w: int = 50, h: int = 50, mode: str = "RGB") -> Image.Image:
    return Image.new(mode, (w, h))


def _layer(layer_id: str, weight: float = 1.0):
    from deepfake.layer import DeepfakeLayer

    return DeepfakeLayer(layer_id=layer_id, display_name=layer_id, provider="stub", weight=weight)


# ---------------------------------------------------------------------------
# classifiers.detect_deepfake_suspect
# ---------------------------------------------------------------------------


class TestLegacyPathFailures:
    def _run(self, detector, faces=None):
        with (
            patch("deepfake.face_extractor.extract_faces", return_value=faces or [_img()]),
            patch("deepfake.factory.get_detector", return_value=detector),
        ):
            return detect_deepfake_suspect(_img(200, 200))

    def test_detector_exception_returns_baseline_not_500(self):
        det = MagicMock()
        det.name = "custom"
        det.detect.side_effect = RuntimeError("model exploded")
        assert self._run(det) == pytest.approx(0.05)

    def test_nan_scores_ignored(self):
        det = MagicMock()
        det.name = "custom"
        det.detect.return_value = [float("nan"), 0.4]
        assert self._run(det, faces=[_img(), _img()]) == pytest.approx(0.4)

    def test_all_nan_returns_baseline(self):
        det = MagicMock()
        det.name = "custom"
        det.detect.return_value = [float("nan")]
        assert self._run(det) == pytest.approx(0.05)

    def test_out_of_range_scores_clamped(self):
        """>1 would fail ModerationScores validation and 500 the request."""
        det = MagicMock()
        det.name = "custom"
        det.detect.return_value = [1.7]
        assert self._run(det) == pytest.approx(1.0)


class TestMaxFaces:
    def test_only_largest_faces_scored(self):
        faces = [_img(90, 90), _img(60, 60), _img(30, 30)]  # largest first
        det = MagicMock()
        det.name = "mock"
        det.detect.side_effect = lambda fs: [0.1] * len(fs)

        with (
            patch("deepfake.face_extractor.extract_faces", return_value=faces),
            patch("deepfake.factory.get_detector", return_value=det),
            patch("config.settings") as mock_settings,
        ):
            mock_settings.deepfake_layers = []
            mock_settings.deepfake_max_faces = 2
            detect_deepfake_suspect(_img(200, 200))

        sent = det.detect.call_args[0][0]
        assert [f.size for f in sent] == [(90, 90), (60, 60)]

    def test_zero_means_unlimited(self):
        faces = [_img(), _img(), _img()]
        det = MagicMock()
        det.name = "mock"
        det.detect.side_effect = lambda fs: [0.1] * len(fs)

        with (
            patch("deepfake.face_extractor.extract_faces", return_value=faces),
            patch("deepfake.factory.get_detector", return_value=det),
            patch("config.settings") as mock_settings,
        ):
            mock_settings.deepfake_layers = []
            mock_settings.deepfake_max_faces = 0
            detect_deepfake_suspect(_img(200, 200))

        assert len(det.detect.call_args[0][0]) == 3


class TestMultiLayerFailures:
    def test_raising_layer_dropped_others_still_combine(self):
        det_a = MagicMock()
        det_a.detect.side_effect = RuntimeError("timeout")
        det_b = MagicMock()
        det_b.detect.return_value = [0.6]

        with (
            patch("deepfake.face_extractor.extract_faces", return_value=[_img()]),
            patch("config.settings") as mock_settings,
            patch(
                "deepfake.layer_registry.DeepfakeLayerRegistry.active_layers",
                return_value=[_layer("a"), _layer("b")],
            ),
            patch(
                "deepfake.layer_registry.DeepfakeLayerRegistry.get_detector_for",
                side_effect=lambda layer: {"a": det_a, "b": det_b}[layer.layer_id],
            ),
        ):
            mock_settings.deepfake_layers = ["a", "b"]
            mock_settings.deepfake_layer_combine = "mean"
            mock_settings.deepfake_max_faces = 0
            score = detect_deepfake_suspect(_img(200, 200))

        # mean over the surviving layer only — not dragged down by a fake 0.
        assert score == pytest.approx(0.6)


class TestClassifyImageSanitising:
    def test_nan_nsfw_score_becomes_zero(self):
        clf = MagicMock(return_value=[{"label": "nsfw", "score": float("nan")}])
        with (
            patch("classifiers._get_image_classifier", return_value=clf),
            patch("classifiers._get_violence_classifier", return_value=None),
        ):
            result = classify_image(_img())
        assert result["nsfw"] == 0.0

    def test_non_rgb_input_converted(self):
        clf = MagicMock(return_value=[{"label": "nsfw", "score": 0.3}])
        with (
            patch("classifiers._get_image_classifier", return_value=clf),
            patch("classifiers._get_violence_classifier", return_value=None),
        ):
            classify_image(_img(mode="RGBA"))
        assert clf.call_args[0][0].mode == "RGB"


# ---------------------------------------------------------------------------
# Face extraction
# ---------------------------------------------------------------------------


def _detection(xmin, ymin, width, height):
    bbox = MagicMock()
    bbox.xmin, bbox.ymin, bbox.width, bbox.height = xmin, ymin, width, height
    det = MagicMock()
    det.location_data.relative_bounding_box = bbox
    return det


def _detector(detections):
    det = MagicMock()
    det.process.return_value = MagicMock(detections=detections)
    return det


class TestFaceExtractorRobustness:
    def test_full_range_model_used_when_short_range_finds_nothing(self):
        from deepfake.face_extractor import FULL_RANGE, SHORT_RANGE, extract_faces

        short = _detector(None)
        full = _detector([_detection(0.4, 0.1, 0.1, 0.1)])  # small, distant face
        models = {SHORT_RANGE: short, FULL_RANGE: full}

        with patch(
            "deepfake.face_extractor._get_face_detector",
            side_effect=lambda sel=SHORT_RANGE: models[sel],
        ):
            faces = extract_faces(_img(400, 400))

        assert len(faces) == 1
        assert full.process.called

    def test_full_range_not_run_when_short_range_succeeds(self):
        from deepfake.face_extractor import FULL_RANGE, SHORT_RANGE, extract_faces

        short = _detector([_detection(0.2, 0.2, 0.5, 0.5)])
        full = _detector([])
        models = {SHORT_RANGE: short, FULL_RANGE: full}

        with patch(
            "deepfake.face_extractor._get_face_detector",
            side_effect=lambda sel=SHORT_RANGE: models[sel],
        ):
            extract_faces(_img(200, 200))

        assert not full.process.called

    def test_faces_sorted_largest_first(self):
        from deepfake.face_extractor import extract_faces

        det = _detector([_detection(0.0, 0.0, 0.1, 0.1), _detection(0.5, 0.5, 0.4, 0.4)])
        with patch("deepfake.face_extractor._get_face_detector", return_value=det):
            faces = extract_faces(_img(400, 400))
        areas = [f.width * f.height for f in faces]
        assert areas == sorted(areas, reverse=True)

    def test_box_outside_frame_skipped(self):
        from deepfake.face_extractor import extract_faces

        det = _detector([_detection(1.5, 1.5, 0.3, 0.3)])
        with patch("deepfake.face_extractor._get_face_detector", return_value=det):
            assert extract_faces(_img(200, 200)) == []

    def test_non_rgb_input_converted_before_detection(self):
        from deepfake.face_extractor import extract_faces

        det = _detector(None)
        with patch("deepfake.face_extractor._get_face_detector", return_value=det):
            extract_faces(_img(64, 64, mode="RGBA"))
        arr = det.process.call_args[0][0]
        assert arr.shape == (64, 64, 3)
        assert arr.dtype == np.uint8

    def test_detector_exception_means_no_faces(self):
        from deepfake.face_extractor import extract_faces

        det = MagicMock()
        det.process.side_effect = RuntimeError("graph error")
        with patch("deepfake.face_extractor._get_face_detector", return_value=det):
            assert extract_faces(_img(100, 100)) == []


# ---------------------------------------------------------------------------
# Local ONNX detector
# ---------------------------------------------------------------------------


class TestLocalOnnxOutputs:
    def _detector_with(self, run):
        from deepfake.local_detector import LocalOnnxDetector

        session = MagicMock()
        session.get_inputs.return_value = [MagicMock()]
        session.get_inputs.return_value[0].name = "input"
        session.run.side_effect = run
        det = LocalOnnxDetector()
        det._session = session
        return det

    def test_two_class_output_uses_fake_class_softmax(self):
        """[real, fake] logits: element 0 is the *real* logit — sigmoid-ing it
        would invert the score."""
        det = self._detector_with(lambda *_: [np.array([[3.0, -3.0]])])  # confidently real
        score = det.detect([_img()])[0]
        assert score < 0.01

        det = self._detector_with(lambda *_: [np.array([[-3.0, 3.0]])])  # confidently fake
        assert det.detect([_img()])[0] > 0.99

    def test_inference_error_costs_only_that_face(self):
        calls = {"n": 0}

        def _run(*_):
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError("shape mismatch")
            return [np.array([[2.0]])]

        det = self._detector_with(_run)
        scores = det.detect([_img(), _img()])
        assert scores[0] == pytest.approx(0.05)
        assert scores[1] == pytest.approx(0.8808, abs=1e-3)

    def test_rgba_face_preprocessed(self):
        from deepfake.local_detector import INPUT_SIZE, _preprocess

        assert _preprocess(_img(mode="RGBA")).shape == (1, 3, INPUT_SIZE, INPUT_SIZE)


# ---------------------------------------------------------------------------
# Combination + registry + /health
# ---------------------------------------------------------------------------


class TestCombineClamping:
    def test_negative_weight_cannot_push_score_out_of_range(self):
        from deepfake.combine import combine_scores

        layers = [_layer("a", weight=-5.0), _layer("b", weight=1.0)]
        score = combine_scores({"a": 0.9, "b": 0.2}, layers, "weighted_mean")
        assert 0.0 <= score <= 1.0
        assert score == pytest.approx(0.2)  # the negative-weight layer counts as 0


class TestLayerRegistryAvailability:
    def setup_method(self):
        from deepfake.layer_registry import DeepfakeLayerRegistry

        DeepfakeLayerRegistry.reset()

    def teardown_method(self):
        from deepfake.layer_registry import DeepfakeLayerRegistry

        DeepfakeLayerRegistry.reset()

    def test_provider_constructor_crash_returns_none(self):
        from deepfake.layer_registry import DeepfakeLayerRegistry

        with patch("deepfake.factory.build_provider", side_effect=RuntimeError("bad init")):
            assert DeepfakeLayerRegistry.get_detector_for(_layer("boom")) is None
        assert DeepfakeLayerRegistry.availability() == {"boom": False}

    def test_availability_recorded(self):
        from deepfake.layer_registry import DeepfakeLayerRegistry

        DeepfakeLayerRegistry.get_detector_for(_layer("stubby"))
        assert DeepfakeLayerRegistry.availability() == {"stubby": True}


class TestHealthLayerMode:
    def setup_method(self):
        from deepfake.layer_registry import DeepfakeLayerRegistry

        DeepfakeLayerRegistry.reset()

    def teardown_method(self):
        from deepfake.layer_registry import DeepfakeLayerRegistry

        DeepfakeLayerRegistry.reset()

    def _status(self, layers):
        import config as config_module
        from deepfake.factory import active_detector_status

        old = config_module.settings.deepfake_layers
        config_module.settings.deepfake_layers = layers
        try:
            return active_detector_status()
        finally:
            config_module.settings.deepfake_layers = old

    def test_all_resolved_layers_unavailable_is_degraded(self):
        """DEEPFAKE_LAYERS=openai without OPENAI_API_KEY: every face silently
        gets 0.05 — /health must say so once a request has tried it."""
        from deepfake.layer_registry import DeepfakeLayerRegistry

        openai_layer = DeepfakeLayerRegistry.get("openai")
        assert openai_layer is not None
        unavailable = MagicMock()
        unavailable.is_available.return_value = False
        with patch("deepfake.factory.build_provider", return_value=unavailable):
            DeepfakeLayerRegistry.get_detector_for(openai_layer)

        status = self._status(["openai"])
        assert status["resolved"] == ["openai"]
        assert status["unavailable"] == ["openai"]
        assert status["available"] == []
        assert status["degraded"] is True

    def test_untried_layers_not_reported_degraded(self):
        status = self._status(["openai"])
        assert status["degraded"] is False
        assert status["available"] == [] and status["unavailable"] == []

    def test_working_layer_reported_available(self):
        from deepfake.layer_registry import DeepfakeLayerRegistry

        DeepfakeLayerRegistry.get_detector_for(DeepfakeLayerRegistry.get("stub"))
        status = self._status(["stub"])
        assert status["available"] == ["stub"]
        assert status["degraded"] is False
