"""Tests for deepfake per-layer score combination strategies."""

from __future__ import annotations

import pytest

from deepfake.combine import combine_scores
from deepfake.layer import DeepfakeLayer


def _layer(layer_id: str, weight: float = 1.0) -> DeepfakeLayer:
    return DeepfakeLayer(layer_id=layer_id, display_name=layer_id, provider="stub", weight=weight)


class TestCombineScores:
    def test_max_default(self):
        scores = {"a": 0.2, "b": 0.8, "c": 0.5}
        layers = [_layer("a"), _layer("b"), _layer("c")]
        assert combine_scores(scores, layers, "max") == pytest.approx(0.8)

    def test_max_is_default_strategy(self):
        scores = {"a": 0.2, "b": 0.8}
        layers = [_layer("a"), _layer("b")]
        assert combine_scores(scores, layers) == pytest.approx(0.8)

    def test_mean(self):
        scores = {"a": 0.2, "b": 0.8}
        layers = [_layer("a"), _layer("b")]
        assert combine_scores(scores, layers, "mean") == pytest.approx(0.5)

    def test_weighted_mean(self):
        scores = {"a": 0.2, "b": 0.8}
        layers = [_layer("a", weight=1.0), _layer("b", weight=3.0)]
        # (1*0.2 + 3*0.8) / 4 = 0.65
        assert combine_scores(scores, layers, "weighted_mean") == pytest.approx(0.65)

    def test_weighted_mean_missing_layer_defaults_to_weight_one(self):
        scores = {"a": 0.4, "unknown": 0.8}
        layers = [_layer("a", weight=1.0)]
        # (1*0.4 + 1*0.8) / 2 = 0.6
        assert combine_scores(scores, layers, "weighted_mean") == pytest.approx(0.6)

    def test_weighted_mean_zero_total_weight_falls_back_to_max(self):
        scores = {"a": 0.3, "b": 0.9}
        layers = [_layer("a", weight=0.0), _layer("b", weight=0.0)]
        assert combine_scores(scores, layers, "weighted_mean") == pytest.approx(0.9)

    def test_empty_scores_returns_zero(self):
        assert combine_scores({}, [], "max") == pytest.approx(0.0)

    def test_unknown_strategy_falls_back_to_max(self):
        scores = {"a": 0.2, "b": 0.8}
        layers = [_layer("a"), _layer("b")]
        assert combine_scores(scores, layers, "bogus_strategy") == pytest.approx(0.8)
